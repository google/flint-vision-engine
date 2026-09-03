#!/usr/bin/env python3
# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
===============================================================================
SYMPICS UNIFIED — CLEAN SLATE PROTOCOL SCRIPT
===============================================================================
Resets the SYMPICS system to a completely pristine / clean slate state:
  1. Truncates all evidence, media assets, vector embeddings, and case tables.
  2. Clears all files/subfolders in 'future-lan-storage' and recreates the
     canonical directory skeleton.
===============================================================================
"""

import os
import sys
import shutil
import psycopg2

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STORAGE_ROOT = os.path.join(PROJECT_ROOT, "future-lan-storage")

TABLES_TO_TRUNCATE = [
    "case_evidence_actions",
    "case_evidence_items",
    "media_embeddings",
    "video_keyframes",
    "migration_manifest",
    "comparison_matches",
    "known_images",
    "unknown_images",
    "known_hash_sets",
    "workspaces",
    "media_assets",
    "cases"
]

CANONICAL_DIRECTORIES = [
    os.path.join(STORAGE_ROOT, "01_Media_Vault", "images"),
    os.path.join(STORAGE_ROOT, "01_Media_Vault", "thumbnails"),
    os.path.join(STORAGE_ROOT, "01_Media_Vault", "keyframes"),
    os.path.join(STORAGE_ROOT, "01_Media_Vault", "derived"),
    os.path.join(STORAGE_ROOT, "02_Known_Hash_Sets"),
    os.path.join(STORAGE_ROOT, "03_Ingestion_Staging"),
    os.path.join(STORAGE_ROOT, "03_Ingestion_Staging", "_quarantine"),
    os.path.join(STORAGE_ROOT, "04_Export_Packages"),
    os.path.join(STORAGE_ROOT, "05_Audit_Logs"),
]


def reset_database():
    print("\n[*] Connecting to PostgreSQL 'sympics_db'...")
    conn = psycopg2.connect("dbname=sympics_db")
    cur = conn.cursor()

    print("[*] Truncating database tables...")
    for table in TABLES_TO_TRUNCATE:
        try:
            cur.execute(f"TRUNCATE TABLE {table} CASCADE;")
            print(f"  [+] Truncated '{table}'")
        except Exception as e:
            print(f"  [!] Warning on '{table}': {e}")
            conn.rollback()

    conn.commit()

    # Check table counts
    print("\n[*] Verifying Database State:")
    for table in TABLES_TO_TRUNCATE:
        try:
            cur.execute(f"SELECT count(*) FROM {table};")
            count = cur.fetchone()[0]
            print(f"  - {table}: {count} rows")
        except Exception:
            pass

    cur.close()
    conn.close()


def reset_storage_directories():
    print(f"\n[*] Resetting storage vault at: {STORAGE_ROOT}...")
    if os.path.exists(STORAGE_ROOT):
        for item in os.listdir(STORAGE_ROOT):
            item_path = os.path.join(STORAGE_ROOT, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    print(f"  [x] Removed directory: {item}/")
                else:
                    os.remove(item_path)
                    print(f"  [x] Removed file: {item}")
            except Exception as e:
                print(f"  [!] Error removing {item}: {e}")

    print("\n[*] Recreating canonical storage directory structure...")
    for d in CANONICAL_DIRECTORIES:
        os.makedirs(d, exist_ok=True)
        rel = os.path.relpath(d, STORAGE_ROOT)
        print(f"  [+] Created: future-lan-storage/{rel}")


def main():
    print("=" * 78)
    print("           SYMPICS UNIFIED — CLEAN SLATE PROTOCOL")
    print("=" * 78)
    
    reset_database()
    reset_storage_directories()
    
    print("\n" + "=" * 78)
    print(" [+] CLEAN SLATE COMPLETE: All tables cleared & storage vault initialized.")
    print("=" * 78)


if __name__ == "__main__":
    main()
