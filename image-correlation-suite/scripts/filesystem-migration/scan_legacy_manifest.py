#!/usr/bin/env python3
# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
===============================================================================
SYMPICS MIGRATION PIPELINE — PHASE 1: READ-ONLY DISCOVERY & MANIFEST SCANNER
===============================================================================
Purpose:
Recursively scans legacy storage directories, computes cryptographic fingerprints
(SHA-256, MD5, SHA-1), captures file timestamps and byte sizes, and populates the
PostgreSQL `migration_manifest` table.

Guarantees:
- 100% Read-Only: NEVER alters, renames, or moves source evidence files.
- Memory-Safe Stream Hashing: Processes multi-gigabyte videos in 64KB blocks.
- Fully Idempotent: Can be safely re-run without creating duplicate records.
===============================================================================
"""

import os
import sys
import time
import hashlib
import datetime
import argparse
import zipfile
from pathlib import Path

# Add database module to path
_db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database"))
if _db_dir not in sys.path:
    sys.path.insert(0, _db_dir)

try:
    import db
except ImportError as e:
    print(f"[ERROR] Could not import db module from {_db_dir}: {e}")
    sys.exit(1)


VALID_IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif", ".heic",
    ".cr3", ".cr2", ".nef", ".arw", ".dng", ".orf", ".rw2", ".pef", ".raf"
}
VALID_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}
ALL_MEDIA_EXTS = VALID_IMAGE_EXTS.union(VALID_VIDEO_EXTS)
VALID_ARCHIVE_EXTS = {".zip"}


def print_banner():
    print("===============================================================================")
    print("  SYMPICS - PHASE 1: READ-ONLY DISCOVERY & MANIFEST SCANNER")
    print("===============================================================================")


def get_input(prompt_text, default_val=None):
    full_prompt = f"{prompt_text} [{default_val}]: " if default_val else f"{prompt_text}: "
    try:
        val = input(full_prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\n[CANCELLED] Operation aborted by user.")
        sys.exit(0)
    return val if val else default_val


def compute_file_hashes(filepath):
    """
    Computes SHA-256, MD5, and SHA-1 hashes simultaneously using 64KB stream blocks.
    Memory footprint remains under a few megabytes even for 50GB video files.
    """
    sha256_h = hashlib.sha256()
    md5_h = hashlib.md5()
    sha1_h = hashlib.sha1()

    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)  # 64 KB block
            if not chunk:
                break
            sha256_h.update(chunk)
            md5_h.update(chunk)
            sha1_h.update(chunk)

    return {
        "sha256": sha256_h.hexdigest().lower(),
        "md5": md5_h.hexdigest().lower(),
        "sha1": sha1_h.hexdigest().lower()
    }


def compute_zip_entry_hashes(zf, zip_info):
    """
    Computes SHA-256, MD5, and SHA-1 hashes directly from an in-stream archive entry.
    Reads in 64KB blocks without extracting files to disk.
    """
    sha256_h = hashlib.sha256()
    md5_h = hashlib.md5()
    sha1_h = hashlib.sha1()

    with zf.open(zip_info, "r") as f:
        while True:
            chunk = f.read(65536)  # 64 KB block
            if not chunk:
                break
            sha256_h.update(chunk)
            md5_h.update(chunk)
            sha1_h.update(chunk)

    return {
        "sha256": sha256_h.hexdigest().lower(),
        "md5": md5_h.hexdigest().lower(),
        "sha1": sha1_h.hexdigest().lower()
    }


def scan_and_catalog_directory(source_dir, batch_size=500, max_gb=None):
    """
    Recursively scans source_dir, extracts file statistics, hashes files & zip archives,
    and batch-inserts records into the migration_manifest table.
    Supports partial test limit via max_gb (e.g. 2048 for 2TB test)
    and stateful resumption.
    """
    clean_source = os.path.abspath(os.path.expanduser(source_dir))
    if not os.path.isdir(clean_source):
        print(f"\n[ERROR] Source directory does not exist or is not a folder: {clean_source}")
        return False

    max_bytes = int(float(max_gb) * 1024 * 1024 * 1024) if max_gb else None

    print(f"\n[*] Source Directory : {clean_source}")
    print(f"[*] Target Database  : {db.load_db_config().get('database', 'sympics_db')}")
    print(f"[*] Operation Mode   : 100% Read-Only Discovery (Files & In-Stream ZIP Archives)")
    if max_gb:
        print(f"[*] Target Test Cap  : {max_gb} GB ({max_bytes:,} bytes)")
    else:
        print(f"[*] Target Test Cap  : FULL DISCOVERY (No Limit)")
    print(f"-------------------------------------------------------------------------------")

    # Step 1: Discover all target media files & zip archives
    print("[*] Stage 1: Scanning directory tree for media files and ZIP archives...")
    discovered_items = []
    total_bytes = 0
    archive_count = 0

    for root, _, files in os.walk(clean_source):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            full_p = os.path.join(root, f)

            if ext in ALL_MEDIA_EXTS:
                try:
                    stat_info = os.stat(full_p)
                    mtime = datetime.datetime.fromtimestamp(stat_info.st_mtime, tz=datetime.timezone.utc)
                    ctime = datetime.datetime.fromtimestamp(stat_info.st_ctime, tz=datetime.timezone.utc)
                    discovered_items.append({
                        "is_zip": False,
                        "filepath": full_p,
                        "source_filename": f,
                        "source_parent_dir": os.path.basename(root),
                        "file_size": stat_info.st_size,
                        "file_extension": ext,
                        "created_at": ctime,
                        "modified_at": mtime,
                        "is_video": ext in VALID_VIDEO_EXTS
                    })
                except Exception as e:
                    print(f"[!] Warning: Could not stat file {full_p}: {e}")

            elif ext in VALID_ARCHIVE_EXTS:
                archive_count += 1
                try:
                    with zipfile.ZipFile(full_p, "r") as zf:
                        zip_base = os.path.splitext(f)[0]
                        for info in zf.infolist():
                            if info.is_dir() or info.filename.endswith("/"):
                                continue
                            base_name = os.path.basename(info.filename)
                            if base_name.startswith(".") or "__MACOSX" in info.filename or base_name == "Thumbs.db":
                                continue
                            inner_ext = os.path.splitext(info.filename)[1].lower()
                            if inner_ext in ALL_MEDIA_EXTS:
                                try:
                                    dt = datetime.datetime(*info.date_time, tzinfo=datetime.timezone.utc)
                                except Exception:
                                    dt = datetime.datetime.now(datetime.timezone.utc)
                                
                                inner_parent = os.path.basename(os.path.dirname(info.filename)) or zip_base
                                discovered_items.append({
                                    "is_zip": True,
                                    "archive_path": full_p,
                                    "zip_info": info,
                                    "filepath": f"{full_p}!{info.filename}",
                                    "source_filename": base_name,
                                    "source_parent_dir": inner_parent,
                                    "file_size": info.file_size,
                                    "file_extension": inner_ext,
                                    "created_at": dt,
                                    "modified_at": dt,
                                    "is_video": inner_ext in VALID_VIDEO_EXTS
                                })
                except Exception as e:
                    print(f"[!] Warning: Could not read archive {full_p}: {e}")

    total_files = len(discovered_items)
    if total_files == 0:
        print(f"\n[!] No supported media files or archives found in '{clean_source}'.")
        return True

    loose_count = sum(1 for item in discovered_items if not item["is_zip"])
    zip_item_count = total_files - loose_count
    print(f"[+] Discovered {total_files:,} total media items ({loose_count:,} loose files, {zip_item_count:,} files inside {archive_count} ZIP archives).\n")

    # Step 2: Pre-check existing manifest for instant incremental scan
    print("[*] Stage 2: Checking existing manifest database records...")
    conn = db.get_connection()
    existing_manifest = {}
    with conn.cursor() as cur:
        cur.execute("SELECT source_filepath, file_size_bytes, sha256, md5, sha1, status FROM migration_manifest;")
        for r in cur.fetchall():
            existing_manifest[r["source_filepath"]] = r

    print(f"[+] Found {len(existing_manifest):,} records already cataloged in database.\n")
    print("[*] Stage 3: Cryptographic fingerprinting & manifest indexing...")

    start_time = time.time()
    records_batch = []
    processed_count = 0
    total_inserted = 0
    skipped_unchanged = 0
    unique_hashes = set()
    failed_files = []
    scanned_volume_bytes = 0

    current_open_zip_path = None
    current_open_zip_obj = None

    try:
        for idx, item in enumerate(discovered_items, 1):
            if max_bytes and scanned_volume_bytes >= max_bytes:
                print(f"\n\n[+] Reached desired test scan limit of {max_gb} GB ({scanned_volume_bytes / (1024**3):.2f} GB processed).")
                break

            fpath = item["filepath"]
            f_size = item["file_size"]
            total_bytes += f_size

            # Check if already cataloged (verified, duplicate, or pending)
            cached = existing_manifest.get(fpath)
            if cached and cached["file_size_bytes"] == f_size and cached["status"] in ('VERIFIED_COPIED', 'SKIPPED_DUPLICATE', 'PENDING'):
                skipped_unchanged += 1
                unique_hashes.add(cached["sha256"])
                processed_count = idx
                continue

            try:
                if item["is_zip"]:
                    arch_path = item["archive_path"]
                    if current_open_zip_path != arch_path:
                        if current_open_zip_obj is not None:
                            current_open_zip_obj.close()
                        current_open_zip_path = arch_path
                        current_open_zip_obj = zipfile.ZipFile(arch_path, "r")
                    
                    hashes = compute_zip_entry_hashes(current_open_zip_obj, item["zip_info"])
                else:
                    hashes = compute_file_hashes(fpath)

                unique_hashes.add(hashes["sha256"])
                scanned_volume_bytes += f_size

                record = {
                    "source_filepath": fpath,
                    "source_filename": item["source_filename"],
                    "source_parent_dir": item["source_parent_dir"],
                    "file_size_bytes": f_size,
                    "file_extension": item["file_extension"],
                    "source_created_at": item["created_at"],
                    "source_modified_at": item["modified_at"],
                    "sha256": hashes["sha256"],
                    "md5": hashes["md5"],
                    "sha1": hashes["sha1"],
                    "status": "PENDING",
                    "is_video": item["is_video"]
                }
                records_batch.append(record)

            except Exception as e:
                failed_files.append((fpath, str(e)))

            # Commit batch
            if len(records_batch) >= batch_size:
                inserted = db.batch_add_manifest_records(records_batch, conn=conn)
                total_inserted += inserted
                records_batch = []

            processed_count = idx

            # Visual progress update
            elapsed = time.time() - start_time
            speed = processed_count / elapsed if elapsed > 0 else 0
            pct = (processed_count / total_files) * 100
            bar_len = 25
            filled = int(bar_len * (processed_count / total_files))
            bar = "█" * filled + "-" * (bar_len - filled)

            sys.stdout.write(
                f"\r [{bar}] {pct:5.1f}% | {processed_count:,}/{total_files:,} items | {skipped_unchanged:,} unchanged | {speed:4.0f} items/s"
            )
            sys.stdout.flush()

        if records_batch:
            inserted = db.batch_add_manifest_records(records_batch, conn=conn)
            total_inserted += inserted

    finally:
        if current_open_zip_obj is not None:
            try:
                current_open_zip_obj.close()
            except Exception:
                pass
        conn.close()

    total_time = time.time() - start_time

    # Step 3: Print Detailed Summary Report
    print(f"\n\n===============================================================================")
    print(f" [+] PHASE 1 DISCOVERY & MANIFEST SCAN COMPLETE (Elapsed: {total_time:.2f}s)")
    print(f"===============================================================================")
    print(f" Source Scanned       : {clean_source}")
    print(f" Total Media Items    : {total_files:,} ({loose_count:,} loose files, {zip_item_count:,} in {archive_count} ZIPs)")
    print(f" Already Verified     : {skipped_unchanged:,} items unchanged (skipped)")
    print(f" Newly Discovered/Mod : {total_inserted:,} items added to PENDING queue")
    print(f" Unique SHA-256s      : {len(unique_hashes):,} distinct physical assets")
    
    duplicate_count = total_files - len(unique_hashes)
    if duplicate_count > 0:
        print(f" Duplicate Files      : {duplicate_count:,} duplicate occurrences detected across folders/archives")
    else:
        print(f" Duplicate Files      : 0 duplicates detected")
        
    print(f" Total Data Volume    : {total_bytes / (1024 * 1024):,.2f} MB ({total_bytes / (1024 * 1024 * 1024):,.3f} GB)")
    print(f" Failed / Corrupt     : {len(failed_files)} items")
    
    if failed_files:
        print("\n[!] Failed Files Log:")
        for fp, err in failed_files[:5]:
            print(f"    - {fp}: {err}")
            
    print(f"===============================================================================\n")

    return True


def main():
    print_banner()

    parser = argparse.ArgumentParser(
        description="SYMPICS Migration Pipeline — Phase 1: Read-Only Legacy Discovery Scanner."
    )
    parser.add_argument(
        "--source-dir",
        "-s",
        help="Path to the legacy evidence directory to scan and catalog."
    )
    parser.add_argument(
        "--max-gb",
        "-g",
        type=float,
        default=None,
        help="Limit scan size in GB for partial testing (e.g. 2048 for 2TB test, default: all)."
    )
    parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=500,
        help="Number of records per database batch commit (default: 500)."
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without prompts (for automation)."
    )

    args = parser.parse_args()

    # Determine default candidate
    cand_local = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "current-lan-storage"))
    cand_parent = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "current-lan-storage"))
    default_dir = cand_parent if (os.path.exists(cand_parent) and not os.path.exists(cand_local)) else cand_local

    source_path = args.source_dir
    max_gb = args.max_gb

    if source_path and not os.path.isabs(source_path):
        if not os.path.exists(source_path) and os.path.exists(os.path.join("..", source_path)):
            source_path = os.path.abspath(os.path.join("..", source_path))
        else:
            source_path = os.path.abspath(source_path)

    if not source_path:
        if not args.non_interactive:
            print("Enter the path of the legacy storage directory you wish to scan:")
            source_path = get_input("Source Directory Path", default_val=default_dir)
            max_gb_str = get_input("Desired scan limit in GB (e.g. 2048 for 2TB test, or Enter for all)", default_val="")
            if max_gb_str:
                try:
                    max_gb = float(max_gb_str)
                except ValueError:
                    max_gb = None
        else:
            source_path = default_dir

    scan_and_catalog_directory(source_path, batch_size=args.batch_size, max_gb=max_gb)


if __name__ == "__main__":
    main()
