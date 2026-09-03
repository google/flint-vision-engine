#!/usr/bin/env python3
# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
===============================================================================
SYMPICS VAULT INTEGRITY SCRUBBER & ANTI-BIT ROT ENGINE
===============================================================================
Background integrity verification engine that scans physical files in the
Content-Addressed Storage (CAS) vault, recalculates cryptographic SHA-256
checksums, and validates them against the forensic database ledger.
===============================================================================
"""

import os
import sys
import time
import argparse
from pathlib import Path

# Add database module to path
_db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database"))
if _db_dir not in sys.path:
    sys.path.insert(0, _db_dir)

import db
from sympics.core.hashing import compute_file_hashes


def scrub_vault_integrity(vault_root: str, sample_size: int = None):
    """
    Performs full or sampled cryptographic scrub of all files in 01_Media_Vault.
    """
    conn = db.get_connection()
    vault_media_dir = os.path.join(vault_root, "01_Media_Vault")

    print("\n===============================================================================")
    print(" [*] SYMPICS FORENSIC VAULT INTEGRITY SCRUBBER")
    print("===============================================================================")
    print(f" [*] Target Vault Dir : {vault_media_dir}")

    if not os.path.exists(vault_media_dir):
        print(f" [!] Vault directory does not exist: {vault_media_dir}")
        conn.close()
        return

    # Fetch all registered assets from DB
    with conn.cursor() as cur:
        cur.execute("SELECT asset_id, storage_rel_path, sha256, source_rel_path, file_size_bytes FROM media_assets;")
        registered_assets = cur.fetchall()

    total_assets = len(registered_assets)
    print(f" [*] Total Database Assets Registered : {total_assets:,}")

    if sample_size and sample_size < total_assets:
        import random
        registered_assets = random.sample(registered_assets, sample_size)
        print(f" [*] Performing Random Sample Scrub  : {len(registered_assets):,} assets")
    else:
        print(f" [*] Performing Full Vault Scrub     : {total_assets:,} assets")
    print("-------------------------------------------------------------------------------\n")

    verified_count = 0
    mismatch_count = 0
    missing_count = 0
    total_bytes = 0
    start_time = time.time()

    for idx, asset in enumerate(registered_assets, 1):
        asset_id = asset["asset_id"]
        rel_path = asset["storage_rel_path"]
        expected_sha256 = asset["sha256"]
        filename = asset.get("source_rel_path") or rel_path

        abs_path = os.path.join(vault_root, rel_path)

        if not os.path.exists(abs_path):
            missing_count += 1
            print(f" [!] [-] MISSING FILE: {rel_path} (Asset ID: {asset_id})")
            continue

        try:
            actual_sha256, _, _, file_size = compute_file_hashes(abs_path)
            total_bytes += file_size

            if actual_sha256.lower() == expected_sha256.lower():
                verified_count += 1
            else:
                mismatch_count += 1
                print(f" [!] [!] CHECKSUM CORRUPTION: {rel_path}")
                print(f"     Expected : {expected_sha256}")
                print(f"     Actual   : {actual_sha256}")
        except Exception as e:
            mismatch_count += 1
            print(f" [!] Error reading {rel_path}: {e}")

        if idx % 100 == 0 or idx == len(registered_assets):
            elapsed = time.time() - start_time
            speed = idx / elapsed if elapsed > 0 else 0
            sys.stdout.write(f"\r [*] Scrubbing: {idx:,}/{len(registered_assets):,} | Verified: {verified_count:,} | Corrupt: {mismatch_count} | Missing: {missing_count} | Speed: {speed:.1f} files/s")
            sys.stdout.flush()

    conn.close()
    total_elapsed = time.time() - start_time

    print(f"\n\n===============================================================================")
    print(f" [+] VAULT INTEGRITY SCRUB COMPLETE (Elapsed: {total_elapsed:.2f}s)")
    print(f"===============================================================================")
    print(f"  • Total Assets Checked : {len(registered_assets):,}")
    print(f"  • Cryptographically OK : {verified_count:,} (100% Bit-for-Bit Valid)" if mismatch_count == 0 and missing_count == 0 else f"  • Cryptographically OK : {verified_count:,}")
    print(f"  • Checksum Mismatches  : {mismatch_count}")
    print(f"  • Missing Files        : {missing_count}")
    print(f"  • Data Volume Scrubbed : {total_bytes / (1024 * 1024 * 1024):.2f} GB")
    print("===============================================================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SYMPICS Vault Integrity Scrubber.")
    cand_local = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "future-lan-storage"))
    cand_parent = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "future-lan-storage"))
    default_vault = cand_parent if (os.path.exists(cand_parent) and not os.path.exists(cand_local)) else cand_local
    if os.getenv("SYMPICS_VAULT_ROOT"):
        default_vault = os.path.abspath(os.getenv("SYMPICS_VAULT_ROOT"))
    parser.add_argument("--vault-dir", "-v", default=default_vault, help="Path to SYMPICS storage vault.")
    parser.add_argument("--sample", "-s", type=int, default=None, help="Scrub random sample of N files.")

    args = parser.parse_args()
    scrub_vault_integrity(args.vault_dir, sample_size=args.sample)
