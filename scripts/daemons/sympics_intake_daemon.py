#!/usr/bin/env python3
# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
===============================================================================
SYMPICS REAL-TIME AUTOMATED SERVER INTAKE DAEMON
===============================================================================
Continuous 24/7 background service monitoring `03_Ingestion_Staging` drop-folders.
Performs write-stability checks, cryptographic triple-hashing, atomic CAS vault
routing, 256px WebP thumbnail generation, GPU multi-model vector embeddings
(CLIP 512, SigLIP Base 768, SigLIP-2 NaFlex 768), real-time reference watchlist
collision alerts, and ISO/IEC 27037 compliant audit logging.
===============================================================================
"""

import os
import sys
import time
import shutil
import hashlib
import mimetypes
import json
import signal
import argparse
import traceback
import zipfile
import tarfile
from datetime import datetime
from pathlib import Path

# Add database module to path
_db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database"))
if _db_dir not in sys.path:
    sys.path.insert(0, _db_dir)

try:
    import db
    from embedder_service import get_embedder, VisionEmbedderService, load_image_or_raw
    from hardware_acceleration import probe_hardware, print_hardware_banner
    from PIL import Image, ExifTags
except ImportError as e:
    print(f"[ERROR] Could not import required modules: {e}")
    sys.exit(1)

SUPPORTED_IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif", ".gif", ".heic",
    ".cr3", ".cr2", ".nef", ".arw", ".dng", ".orf", ".rw2", ".pef", ".raf"
}
SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v"}
SUPPORTED_ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".tbz2"}
ALL_MEDIA_EXTS = SUPPORTED_IMAGE_EXTS | SUPPORTED_VIDEO_EXTS

# Global flag for graceful termination
_RUNNING = True


def sig_handler(signum, frame):
    global _RUNNING
    print(f"\n[!] Received signal {signum}. Initiating graceful shutdown of SYMPICS Intake Daemon...")
    _RUNNING = False


def print_banner():
    print("===============================================================================")
    print("  SYMPICS - AUTOMATED SERVER INTAKE & MULTI-MODEL AI DAEMON")
    print("===============================================================================")


def compute_triple_hashes(filepath, chunk_size=65536):
    """Computes SHA-256, MD5, and SHA-1 simultaneously in 64KB blocks."""
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()

    with open(filepath, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
            md5.update(chunk)
            sha1.update(chunk)

    return sha256.hexdigest(), md5.hexdigest(), sha1.hexdigest()


def sanitize_for_pg_json(obj):
    """Recursively removes null bytes (\u0000) and unprintable binary from dict/list/string."""
    if isinstance(obj, str):
        return obj.replace("\x00", "").replace("\u0000", "")
    elif isinstance(obj, bytes):
        try:
            return obj.decode("utf-8", errors="ignore").replace("\x00", "").replace("\u0000", "")
        except Exception:
            return f"<binary {len(obj)} bytes>"
    elif isinstance(obj, dict):
        return {str(k).replace("\x00", "").replace("\u0000", ""): sanitize_for_pg_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [sanitize_for_pg_json(v) for v in obj]
    elif isinstance(obj, (int, float, bool)) or obj is None:
        return obj
    else:
        return str(obj).replace("\x00", "").replace("\u0000", "")


def extract_image_metadata(filepath):
    """Extracts width, height, and EXIF metadata safely."""
    width, height = None, None
    exif_data = {}
    try:
        img = load_image_or_raw(filepath)
        if img:
            width, height = img.size
            raw_exif = img._getexif() if hasattr(img, "_getexif") else None
            if raw_exif:
                for tag_id, val in raw_exif.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    if isinstance(val, (bytes, bytearray)):
                        try:
                            val = val.decode("utf-8", errors="ignore")
                        except Exception:
                            val = f"<binary {len(val)} bytes>"
                    elif hasattr(val, "values"):
                        val = str(val)
                    elif not isinstance(val, (str, int, float, bool, list, dict)):
                        val = str(val)
                    exif_data[str(tag_name)] = val
    except Exception:
        pass
    return width, height, sanitize_for_pg_json(exif_data)


def generate_thumbnail(source_path, dest_thumb_path, max_dim=256):
    """Generates a fast 256px WebP thumbnail."""
    try:
        os.makedirs(os.path.dirname(dest_thumb_path), exist_ok=True)
        img = load_image_or_raw(source_path)
        if img is None:
            return False
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        img.save(dest_thumb_path, "WEBP", quality=85)
        return True
    except Exception as e:
        return False


def extract_video_keyframes(video_path, dest_thumb_path, keyframes_dir, interval_sec=1.0, max_frames=120):
    """
    Extracts keyframes from video at interval_sec intervals using OpenCV.
    Returns: duration_sec, fps, width, height, list of (frame_idx, timestamp_sec, frame_abs_path)
    """
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return 0.0, 0.0, None, None, []

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration_sec = total_frames / fps if fps > 0 else 0.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

        frame_interval = max(1, int(fps * interval_sec))
        os.makedirs(keyframes_dir, exist_ok=True)
        os.makedirs(os.path.dirname(dest_thumb_path), exist_ok=True)

        keyframes = []
        frame_idx = 0
        extracted_count = 0
        saved_primary = False

        while cap.isOpened() and extracted_count < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_interval == 0:
                timestamp_sec = frame_idx / fps
                frame_filename = f"frame_{extracted_count:04d}_{int(timestamp_sec*1000)}ms.webp"
                frame_abs_path = os.path.join(keyframes_dir, frame_filename)

                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb_frame)
                pil_img.thumbnail((256, 256), Image.Resampling.LANCZOS)
                pil_img.save(frame_abs_path, "WEBP", quality=85)

                if not saved_primary:
                    pil_img.save(dest_thumb_path, "WEBP", quality=85)
                    saved_primary = True

                keyframes.append((extracted_count, timestamp_sec, frame_abs_path))
                extracted_count += 1

            frame_idx += 1

        cap.release()

        if not saved_primary and keyframes:
            shutil.copyfile(keyframes[0][2], dest_thumb_path)

        return duration_sec, fps, width, height, keyframes
    except Exception as ve:
        print(f"  [!] Video extraction error for {video_path}: {ve}")
        return 0.0, 0.0, None, None, []


def quarantine_file(staging_root, file_path, error_msg, alt_path=None):
    """Moves unreadable or corrupted files to the _quarantine directory."""
    try:
        target_path = file_path
        if not os.path.exists(target_path) and alt_path and os.path.exists(alt_path):
            target_path = alt_path

        if not os.path.exists(target_path):
            print(f"  [!] File not found for quarantine: {file_path} (alt: {alt_path})")
            return

        today_str = datetime.now().strftime("%Y%m%d")
        quarantine_dir = os.path.join(staging_root, "_quarantine", today_str)
        os.makedirs(quarantine_dir, exist_ok=True)

        filename = os.path.basename(file_path)
        dest_path = os.path.join(quarantine_dir, filename)

        # Avoid collision in quarantine
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(filename)
            dest_path = os.path.join(quarantine_dir, f"{base}_{int(time.time())}{ext}")

        shutil.move(target_path, dest_path)

        # Write companion error log
        err_log_path = dest_path + ".error.json"
        with open(err_log_path, "w", encoding="utf-8") as f:
            json.dump({
                "original_path": file_path,
                "quarantined_at": datetime.utcnow().isoformat() + "Z",
                "error": error_msg,
                "traceback": traceback.format_exc()
            }, f, indent=2)

        print(f"  [!] [!]  QUARANTINED corrupted file: {filename} -> {os.path.relpath(dest_path, staging_root)}")
    except Exception as qe:
        print(f"  [CRITICAL] Failed to quarantine file {file_path}: {qe}")


def extract_gps_coordinates(filepath):
    """
    Extracts (latitude, longitude, altitude) as float degrees/meters from EXIF GPSInfo.
    """
    try:
        img = load_image_or_raw(filepath)
        if not img:
            return None, None, None
        raw_exif = img._getexif() if hasattr(img, "_getexif") else None
        if not raw_exif:
            return None, None, None

            gps_info = None
            for tag_id, val in raw_exif.items():
                if ExifTags.TAGS.get(tag_id) == "GPSInfo":
                    gps_info = val
                    break

            if not gps_info:
                return None, None, None

            def dms_to_decimal(dms, ref):
                if not dms or len(dms) < 3:
                    return None
                def to_f(v):
                    if isinstance(v, (int, float)):
                        return float(v)
                    if hasattr(v, "numerator") and hasattr(v, "denominator"):
                        return v.numerator / v.denominator if v.denominator != 0 else 0.0
                    return float(v)

                deg = to_f(dms[0])
                minutes = to_f(dms[1])
                seconds = to_f(dms[2])
                dec = deg + (minutes / 60.0) + (seconds / 3600.0)
                if ref in ("S", "W"):
                    dec = -dec
                return round(dec, 6)

            lat = dms_to_decimal(gps_info.get(2), gps_info.get(1))
            lon = dms_to_decimal(gps_info.get(4), gps_info.get(3))
            alt = None
            if 6 in gps_info:
                raw_alt = gps_info[6]
                if hasattr(raw_alt, "numerator") and hasattr(raw_alt, "denominator"):
                    alt = raw_alt.numerator / raw_alt.denominator if raw_alt.denominator != 0 else None
                elif isinstance(raw_alt, (int, float)):
                    alt = float(raw_alt)
                if alt is not None:
                    alt = round(float(alt), 2)

            return lat, lon, alt
    except Exception:
        return None, None, None


def safe_unpack_archive(archive_path, staging_root):
    """
    Safely unpacks a .zip, .tar, or .tar.gz archive into a subfolder of staging_root
    named after the archive stem (e.g. batchA.zip -> 03_Ingestion_Staging/batchA/).
    Guards against Zip Slip (path traversal) vulnerabilities.
    """
    fname = os.path.basename(archive_path)
    if fname.lower().endswith(".tar.gz") or fname.lower().endswith(".tar.bz2"):
        stem = fname.rsplit(".", 2)[0]
    else:
        stem = os.path.splitext(fname)[0]

    parent_dir = os.path.dirname(archive_path)
    dest_dir = os.path.join(parent_dir, stem)
    os.makedirs(dest_dir, exist_ok=True)

    unpacked_count = 0
    ext = os.path.splitext(fname)[1].lower()

    try:
        if ext == ".zip":
            with zipfile.ZipFile(archive_path, 'r') as zf:
                for member in zf.infolist():
                    target_path = os.path.abspath(os.path.join(dest_dir, member.filename))
                    if not target_path.startswith(os.path.abspath(dest_dir)):
                        print(f"  [SECURITY WARNING] Skipped dangerous zip member path traversal: {member.filename}")
                        continue
                    if member.is_dir():
                        os.makedirs(target_path, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with zf.open(member) as src, open(target_path, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        unpacked_count += 1

        elif ext in (".tar", ".gz", ".tgz", ".bz2", ".tbz2"):
            mode = "r:*"
            with tarfile.open(archive_path, mode) as tf:
                for member in tf.getmembers():
                    target_path = os.path.abspath(os.path.join(dest_dir, member.name))
                    if not target_path.startswith(os.path.abspath(dest_dir)):
                        print(f"  [SECURITY WARNING] Skipped dangerous tar member path traversal: {member.name}")
                        continue
                    if member.isdir():
                        os.makedirs(target_path, exist_ok=True)
                    elif member.isfile():
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with tf.extractfile(member) as src, open(target_path, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        unpacked_count += 1

        os.remove(archive_path)
        print(f"\n  [UNPACK]  Successfully extracted archive '{fname}' ({unpacked_count} files) -> {os.path.relpath(dest_dir, staging_root)}/\n")
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to extract archive {archive_path}: {e}")
        quarantine_file(staging_root, archive_path, f"Corrupted or invalid archive: {e}")
        return False


class SYMPICSIntakeDaemon:
    def __init__(self, staging_dir, vault_root, poll_interval=2.0, stability_delay=2.0, compute_ai=True):
        self.staging_dir = os.path.abspath(staging_dir)
        self.vault_root = os.path.abspath(vault_root)
        self.poll_interval = poll_interval
        self.stability_delay = stability_delay
        self.compute_ai = compute_ai

        # Staging & Vault structure paths
        self.media_vault = os.path.join(self.vault_root, "01_Media_Vault")
        self.keyframe_vault = os.path.join(self.vault_root, "02_Keyframe_Vault")
        self.quarantine_dir = os.path.join(self.staging_dir, "_quarantine")
        self.processing_dir = os.path.join(self.staging_dir, "_processing")

        # In-memory tracking for write stability: {filepath: (last_size, last_mtime, first_seen)}
        self.file_tracker = {}
        # In-memory cache of physical assets: {sha256: asset_id}
        self.existing_assets = {}
        # Embedder service reference
        self.embedder = None

    def initialize(self):
        """Initializes database schema, caches existing assets, and loads AI models."""
        print("[*] Initializing SYMPICS PostgreSQL Database Connection...")
        db.init_db()
        conn = db.get_connection()

        # Cache existing physical assets
        with conn.cursor() as cur:
            cur.execute("SELECT sha256, asset_id FROM media_assets;")
            for r in cur.fetchall():
                self.existing_assets[r["sha256"].strip()] = r["asset_id"]
        print(f"[+] Cached {len(self.existing_assets):,} existing physical assets in RAM.")

        # Ensure directory structures exist
        os.makedirs(self.staging_dir, exist_ok=True)
        os.makedirs(self.quarantine_dir, exist_ok=True)
        os.makedirs(os.path.join(self.media_vault, "images"), exist_ok=True)
        os.makedirs(os.path.join(self.media_vault, "videos"), exist_ok=True)
        os.makedirs(os.path.join(self.keyframe_vault, "thumbs_256px"), exist_ok=True)

        if self.compute_ai:
            print("[*] Initializing Multi-Model AI Vision Embedder (CLIP 512 + SigLIP Base 768 + SigLIP-2 NaFlex 768)...")
            self.embedder = get_embedder()
            print(f"[+] AI Engine active on device: {self.embedder.device.upper()}")
        else:
            print("[*] AI Embedding Mode: DISABLED (Fast Disk-Only Mode)")

        conn.close()
        print(f"\n[*] SYMPICS Intake Daemon is active and watching:")
        print(f"    Drop Folder : {self.staging_dir}")
        print(f"    Master Vault: {self.vault_root}")
        print(f"   ⏱ Poll Interval: {self.poll_interval}s | Stability Delay: {self.stability_delay}s\n")

    def scan_staging_directory(self):
        """Scans the staging folder recursively, returning stable files ready for intake."""
        ready_files = []
        current_time = time.time()
        seen_paths = set()

        for root, dirs, files in os.walk(self.staging_dir):
            # Ignore quarantine, processing, and hidden folders
            dirs[:] = [d for d in dirs if not d.startswith((".", "_")) and d != "_quarantine"]

            for file in files:
                if file.startswith((".", "_")) or file.endswith((".error.json", ".part", ".crdownload", ".tmp")):
                    continue

                full_path = os.path.join(root, file)
                ext = os.path.splitext(file)[1].lower()
                is_archive = ext in SUPPORTED_ARCHIVE_EXTS
                if ext not in ALL_MEDIA_EXTS and not is_archive:
                    continue

                seen_paths.add(full_path)

                try:
                    stat = os.stat(full_path)
                    cur_size = stat.st_size
                    cur_mtime = stat.st_mtime

                    # Check if 0-byte file (might still be opening)
                    if cur_size == 0 and (current_time - cur_mtime > 10.0):
                        quarantine_file(self.staging_dir, full_path, "Zero-byte empty file")
                        continue

                    # Write-Stability Tracking
                    if full_path not in self.file_tracker:
                        self.file_tracker[full_path] = (cur_size, cur_mtime, current_time)
                        continue

                    last_size, last_mtime, first_seen = self.file_tracker[full_path]

                    if cur_size != last_size or cur_mtime != last_mtime:
                        # File is actively being copied over LAN / SCP / rsync
                        self.file_tracker[full_path] = (cur_size, cur_mtime, current_time)
                        continue

                    # File size is static. Check stability duration threshold.
                    if (current_time - cur_mtime >= self.stability_delay) and (current_time - first_seen >= self.stability_delay):
                        if is_archive:
                            # Safely extract archive into staging folder
                            safe_unpack_archive(full_path, self.staging_dir)
                            if full_path in self.file_tracker:
                                del self.file_tracker[full_path]
                            continue
                        ready_files.append(full_path)

                except FileNotFoundError:
                    pass
                except Exception as e:
                    print(f"[!] Error inspecting staging file {full_path}: {e}")

        # Clean up tracker for files that disappeared
        for p in list(self.file_tracker.keys()):
            if p not in seen_paths:
                del self.file_tracker[p]

        return ready_files

    def process_file(self, file_path, conn):
        """Processes a single verified evidence file through the 8-stage intake pipeline."""
        t0 = time.time()
        filename = os.path.basename(file_path)
        rel_to_staging = os.path.relpath(file_path, self.staging_dir)
        path_parts = rel_to_staging.split(os.sep)

        # 1. Determine Folder Provenance (Lexicon: Folders are NOT cases)
        if len(path_parts) > 1:
            source_folder = path_parts[-2]  # Immediate parent directory name (e.g. batchA)
            source_rel_path = rel_to_staging
        else:
            source_folder = "Staging_Root"
            source_rel_path = filename

        # 2. Cryptographic Fingerprinting
        sha256, md5, sha1 = compute_triple_hashes(file_path)
        file_size = os.path.getsize(file_path)
        ext = os.path.splitext(filename)[1].lower()
        is_video = ext in SUPPORTED_VIDEO_EXTS
        media_type = "VIDEO" if is_video else "IMAGE"
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "application/octet-stream"

        prefix1 = sha256[0:2]
        prefix2 = sha256[2:4]
        sub_folder = "videos" if is_video else "images"
        rel_vault_path = os.path.join("01_Media_Vault", sub_folder, prefix1, prefix2, f"{sha256}{ext}")
        abs_vault_path = os.path.join(self.vault_root, rel_vault_path)

        rel_thumb_path = os.path.join("02_Keyframe_Vault", "thumbs_256px", prefix1, prefix2, f"{sha256}.webp")
        abs_thumb_path = os.path.join(self.vault_root, rel_thumb_path)

        # 3. CAS Deduplication Check
        if sha256 in self.existing_assets:
            asset_id = self.existing_assets[sha256]
            with conn.cursor() as cur:
                # Log custody audit action
                cur.execute("""
                    INSERT INTO case_evidence_actions (
                        asset_id, action_type, original_filename, sha1, sha256, md5, performed_by, details
                    ) VALUES (
                        %s, 'ingested', %s, %s, %s, %s, 'sympics_intake_daemon',
                        %s::jsonb
                    );
                """, (
                    asset_id, filename, sha1, sha256, md5,
                    json.dumps({"status": "DEDUPLICATED", "source_folder": source_folder, "source_staging": rel_to_staging})
                ))
            conn.commit()

            # Clean up duplicate staging file
            try:
                os.remove(file_path)
            except Exception:
                pass

            if file_path in self.file_tracker:
                del self.file_tracker[file_path]

            elapsed = (time.time() - t0) * 1000
            print(f"  [DEDUP]   '{filename}' matched physical asset {sha256[:16]}... (Folder: {source_folder}, 0B added, {elapsed:.1f}ms)")
            return True

        # 4. Fast 256px WebP Thumbnail & EXIF / Video Keyframe Extraction
        width, height, exif_data = None, None, {}
        gps_lat, gps_lon, gps_alt = None, None, None
        duration_sec, fps = 0.0, 0.0
        video_keyframes_list = []

        if not is_video:
            width, height, exif_data = extract_image_metadata(file_path)
            gps_lat, gps_lon, gps_alt = extract_gps_coordinates(file_path)
            generate_thumbnail(file_path, abs_thumb_path, max_dim=256)
        else:
            keyframes_rel_dir = os.path.join("02_Keyframe_Vault", "keyframes", prefix1, prefix2, sha256)
            keyframes_abs_dir = os.path.join(self.vault_root, keyframes_rel_dir)
            duration_sec, fps, width, height, video_keyframes_list = extract_video_keyframes(
                file_path, abs_thumb_path, keyframes_abs_dir, interval_sec=1.0, max_frames=120
            )

        # 5. GPU Multi-Model AI Vector Embeddings
        embs = {}
        if self.embedder is not None:
            target_to_embed = file_path if not is_video else abs_thumb_path
            if os.path.exists(target_to_embed):
                embs = self.embedder.compute_all_embeddings(target_to_embed)

        # 6. Brand New Asset: Atomic Placement in CAS Hex Vault
        os.makedirs(os.path.dirname(abs_vault_path), exist_ok=True)
        shutil.move(file_path, abs_vault_path)

        if file_path in self.file_tracker:
            del self.file_tracker[file_path]

        # 7. PostgreSQL Database Transaction
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO media_assets (
                    sha256, md5, sha1, file_size_bytes, media_type, mime_type,
                    width_pixels, height_pixels, duration_seconds, frame_rate,
                    storage_rel_path, storage_abs_path, thumb_rel_path, exif_data,
                    source_folder, source_rel_path, gps_latitude, gps_longitude, gps_altitude
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (sha256) DO UPDATE SET 
                    storage_rel_path = EXCLUDED.storage_rel_path,
                    source_folder = COALESCE(media_assets.source_folder, EXCLUDED.source_folder),
                    source_rel_path = COALESCE(media_assets.source_rel_path, EXCLUDED.source_rel_path),
                    gps_latitude = COALESCE(media_assets.gps_latitude, EXCLUDED.gps_latitude),
                    gps_longitude = COALESCE(media_assets.gps_longitude, EXCLUDED.gps_longitude),
                    gps_altitude = COALESCE(media_assets.gps_altitude, EXCLUDED.gps_altitude)
                RETURNING asset_id;
            """, (
                sha256, md5, sha1, file_size, media_type, mime_type,
                width, height, duration_sec, fps,
                rel_vault_path, abs_vault_path, rel_thumb_path, json.dumps(exif_data),
                source_folder, source_rel_path, gps_lat, gps_lon, gps_alt
            ))
            asset_id = cur.fetchone()["asset_id"]
            self.existing_assets[sha256] = asset_id

            # Insert Video Keyframes if video
            if video_keyframes_list:
                for k_idx, k_ts, k_path in video_keyframes_list:
                    k_rel = os.path.relpath(k_path, self.vault_root)
                    cur.execute("""
                        INSERT INTO video_keyframes (asset_id, frame_index, timestamp_seconds, storage_rel_path)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (asset_id, frame_index) DO NOTHING;
                    """, (asset_id, k_idx, k_ts, k_rel))

            # Insert AI Embeddings
            if embs:
                if "clip" in embs and embs["clip"]:
                    cur.execute("""
                        INSERT INTO media_embeddings (asset_id, model_name, model_version, dimension_size, embedding_l2)
                        VALUES (%s, 'clip', 'vit-b-32', 512, %s)
                        ON CONFLICT (asset_id, model_name) DO UPDATE SET embedding_l2 = EXCLUDED.embedding_l2;
                    """, (asset_id, embs["clip"]))

                if "siglip" in embs and embs["siglip"]:
                    cur.execute("""
                        INSERT INTO media_embeddings (asset_id, model_name, model_version, dimension_size, embedding_l2)
                        VALUES (%s, 'siglip', 'base-patch16-224', 768, %s)
                        ON CONFLICT (asset_id, model_name) DO UPDATE SET embedding_l2 = EXCLUDED.embedding_l2;
                    """, (asset_id, embs["siglip"]))

                if "siglip2_naflex" in embs and embs["siglip2_naflex"]:
                    cur.execute("""
                        INSERT INTO media_embeddings (asset_id, model_name, model_version, dimension_size, embedding_l2)
                        VALUES (%s, 'siglip2_naflex', 'base-patch16-naflex', 768, %s)
                        ON CONFLICT (asset_id, model_name) DO UPDATE SET embedding_l2 = EXCLUDED.embedding_l2;
                    """, (asset_id, embs["siglip2_naflex"]))

                if "dinov3" in embs and embs["dinov3"]:
                    cur.execute("""
                        INSERT INTO media_embeddings (asset_id, model_name, model_version, dimension_size, embedding_l2)
                        VALUES (%s, 'dinov3', 'vit-b-16-lvd1689m', 768, %s)
                        ON CONFLICT (asset_id, model_name) DO UPDATE SET embedding_l2 = EXCLUDED.embedding_l2;
                    """, (asset_id, embs["dinov3"]))

            # 8. Real-Time Known Hash Collision Check (Reference Intelligence + Custom Hash Sets)
            cur.execute("""
                SELECT identifier, series_name, flag_identified, flag_actionable, contributing_agency
                FROM reference_catalog_records
                WHERE md5 = %s OR sha1 = %s;
            """, (md5, sha1))
            intel_matches = cur.fetchall()

            cur.execute("""
                SELECT hash_value, hash_type, series_name, source_file, category
                FROM known_hash_sets
                WHERE hash_value = %s OR hash_value = %s OR hash_value = %s;
            """, (sha256, md5, sha1))
            hash_set_matches = cur.fetchall()

            collision_details = {"status": "NEW_PHYSICAL_ASSET", "source_folder": source_folder, "source_rel_path": source_rel_path}
            if intel_matches:
                m = intel_matches[0]
                collision_details["intel_alert"] = {
                    "identifier": m["identifier"],
                    "series_name": m["series_name"],
                    "flag_identified": m["flag_identified"],
                    "flag_actionable": m["flag_actionable"]
                }
                print(f"\n  [!] [INTELLIGENCE COLLISION DETECTED] File: '{filename}'")
                print(f"     • Series: {m['series_name']} | Reference ID: {m['identifier']}")
                print(f"     • Status Flags: Identified={m['flag_identified']} | Actionable={m['flag_actionable']}")
                print(f"     • Contributing Agency: {m['contributing_agency']}\n")

            if hash_set_matches:
                hm = hash_set_matches[0]
                collision_details["known_hash_alert"] = {
                    "hash_value": hm["hash_value"],
                    "series_name": hm["series_name"],
                    "source_file": hm["source_file"],
                    "category": hm["category"]
                }
                print(f"\n  [!] [KNOWN HASH SET MATCH] File: '{filename}' -> Series: {hm['series_name']} ({hm['source_file']})\n")

            # Log Forensic Audit Trail
            cur.execute("""
                INSERT INTO case_evidence_actions (
                    asset_id, action_type, original_filename, sha1, sha256, md5, performed_by, details
                ) VALUES (
                    %s, 'ingested', %s, %s, %s, %s, 'sympics_intake_daemon', %s::jsonb
                );
            """, (asset_id, filename, sha1, sha256, md5, json.dumps(collision_details)))

        conn.commit()
        elapsed = (time.time() - t0) * 1000
        print(f"  [INGEST]  '{filename}' -> {rel_vault_path} (Folder: {source_folder}, 3 Vectors, {elapsed:.1f}ms)")
        return True

    def run(self):
        """Main continuous background execution loop."""
        self.initialize()
        conn = db.get_connection()

        try:
            while _RUNNING:
                ready_files = self.scan_staging_directory()

                if ready_files:
                    print(f"[*] Found {len(ready_files)} stable evidence item(s) in staging queue...")
                    for file_path in ready_files:
                        if not _RUNNING:
                            break
                        try:
                            self.process_file(file_path, conn)
                        except Exception as e:
                            print(f"[!] Processing failed for {file_path}: {e}")
                            quarantine_file(self.staging_dir, file_path, str(e))
                            conn.rollback()

                time.sleep(self.poll_interval)

        finally:
            conn.close()
            print("[+] SYMPICS Intake Daemon cleanly terminated.")


def main():
    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    print_banner()
    print_hardware_banner()

    default_staging = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "future-lan-storage", "03_Ingestion_Staging"))
    default_vault = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "future-lan-storage"))

    parser = argparse.ArgumentParser(
        description="SYMPICS Real-Time Automated Server Intake & Multi-Model AI Daemon."
    )
    parser.add_argument("--staging-dir", "-s", default=default_staging, help="Drop directory to watch.")
    parser.add_argument("--vault-dir", "-v", default=default_vault, help="Master CAS storage vault root.")
    parser.add_argument("--poll-interval", "-p", type=float, default=2.0, help="Seconds between scan sweeps.")
    parser.add_argument("--stability-delay", "-d", type=float, default=2.0, help="Seconds file must remain static.")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI embedding calculation (Fast disk-only mode).")

    args = parser.parse_args()

    daemon = SYMPICSIntakeDaemon(
        staging_dir=args.staging_dir,
        vault_root=args.vault_dir,
        poll_interval=args.poll_interval,
        stability_delay=args.stability_delay,
        compute_ai=not args.no_ai
    )

    daemon.run()


if __name__ == "__main__":
    main()
