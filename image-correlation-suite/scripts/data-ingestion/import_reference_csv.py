#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
===============================================================================
SYMPICS REFERENCE INTELLIGENCE CSV IMPORTER & COLLISION DETECTOR
===============================================================================
Imports reference intelligence CSV hash dumps, populates `reference_catalog_records`,
and executes instant collision queries against `media_assets` in the vault.
===============================================================================
"""

import os
import sys
import csv
import time
import argparse

# Add database module to path
_db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database"))
if _db_dir not in sys.path:
    sys.path.insert(0, _db_dir)

try:
    import db
    from psycopg2.extras import execute_values
except ImportError as e:
    print(f"[ERROR] Could not import required database modules: {e}")
    sys.exit(1)


def print_banner():
    print("===============================================================================")
    print("  SYMPICS - REFERENCE INTELLIGENCE CSV IMPORTER & COLLISION MATCHER")
    print("===============================================================================")


def parse_bool(val):
    if not val:
        return False
    v = str(val).strip().upper()
    return v in ("Y", "YES", "TRUE", "1", "T")


def init_reference_schema():
    """Applies schema_reference_catalog.sql to sympics_db."""
    schema_path = os.path.join(_db_dir, "schema_reference_catalog.sql")
    if not os.path.exists(schema_path):
        print(f"[ERROR] Schema file missing: {schema_path}")
        return False

    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()

    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print("[+] Applied reference catalog schema and collision views to database.")
        return True
    finally:
        conn.close()


def import_reference_csv(csv_filepath, batch_size=1000):
    clean_path = os.path.abspath(os.path.expanduser(csv_filepath))
    if not os.path.isfile(clean_path):
        print(f"[ERROR] CSV file not found: {clean_path}")
        return False

    init_reference_schema()

    print(f"\n[*] Reading Reference CSV: {clean_path}")
    start_time = time.time()
    
    records = []
    total_parsed = 0

    with open(clean_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            md5 = (row.get("MD5") or "").strip().lower()
            sha1 = (row.get("SHA1") or "").strip().lower()
            if not md5:
                continue

            try:
                num_sub = int(row.get("Number of submissions", 1) or 1)
            except ValueError:
                num_sub = 1

            record = (
                md5,
                sha1,
                row.get("ZZ40") or None,
                row.get("PhotoDNA") or None,
                row.get("Lace") or None,
                row.get("Identifier") or row.get("Record ID") or row.get("ID") or "UNKNOWN",
                parse_bool(row.get("Is distributed")),
                parse_bool(row.get("Identified") or row.get("Flag Identified")),
                parse_bool(row.get("Actionable") or row.get("Flag Actionable")),
                row.get("Series name") or row.get("Series") or None,
                row.get("Investigation name") or row.get("Investigation") or None,
                row.get("Agency") or None,
                num_sub,
                parse_bool(row.get("File Available")),
                row.get("Media Type") or "Image",
                parse_bool(row.get("Baseline"))
            )
            records.append(record)
            total_parsed += 1

    print(f"[*] Parsed {len(records):,} reference intelligence entries.")

    # Batch Insert
    conn = db.get_connection()
    sql = """
        INSERT INTO reference_catalog_records (
            md5, sha1, zz40, photodna, lace, identifier, is_distributed,
            flag_identified, flag_actionable, series_name, investigation_name,
            contributing_agency, number_of_submissions, file_available, media_type, is_baseline
        ) VALUES %s
        ON CONFLICT (md5, identifier) DO UPDATE SET
            sha1 = EXCLUDED.sha1,
            flag_identified = EXCLUDED.flag_identified,
            flag_actionable = EXCLUDED.flag_actionable,
            series_name = EXCLUDED.series_name,
            investigation_name = EXCLUDED.investigation_name,
            contributing_agency = EXCLUDED.contributing_agency,
            number_of_submissions = EXCLUDED.number_of_submissions;
    """

    try:
        with conn.cursor() as cur:
            execute_values(cur, sql, records, page_size=batch_size)
        conn.commit()
        print(f"[+] Successfully committed {len(records):,} records to 'reference_catalog_records'.")

        # Step 3: Run Instant Collision Query
        print("\n[*] Checking for Reference Collisions against Ingested Vault Media...")
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_collisions,
                    COUNT(CASE WHEN flag_identified THEN 1 END) as identified_matches,
                    COUNT(CASE WHEN flag_actionable THEN 1 END) as actionable_matches
                FROM v_reference_known_collisions;
            """)
            stats = cur.fetchone() or {}
            
            cur.execute("SELECT * FROM v_reference_known_collisions LIMIT 10;")
            sample_matches = cur.fetchall()

    finally:
        conn.close()

    total_time = time.time() - start_time

    # Summary
    print(f"\n===============================================================================")
    print(f" [+] REFERENCE IMPORT & COLLISION AUDIT COMPLETE (Elapsed: {total_time:.2f}s)")
    print(f"===============================================================================")
    print(f" Records Imported  : {total_parsed:,}")
    print(f" Vault Collisions  : {stats.get('total_collisions', 0):,} MATCHES FOUND IN EVIDENCE")
    print(f" Identified Matches: {stats.get('identified_matches', 0):,} confirmed occurrences")
    print(f" Actionable Matches: {stats.get('actionable_matches', 0):,} actionable occurrences")
    print(f"===============================================================================")

    if sample_matches:
        print("\n[!] Sample Collisions Detected in Vault:")
        for m in sample_matches[:5]:
            print(f"  • File: {m['original_filename']}")
            print(f"    - Series: {m['reference_series']} | ID: {m['reference_id']}")
            print(f"    - Flags: Identified={m['flag_identified']} | Actionable={m['flag_actionable']}")
            print(f"    - Vault Path: {m['storage_rel_path']}")
            print()

    return True


def main():
    print_banner()

    parser = argparse.ArgumentParser(
        description="SYMPICS Reference Intelligence CSV Importer & Collision Matcher."
    )
    parser.add_argument(
        "--csv-file",
        "-f",
        default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "sample-data", "reference_hashes_fake.csv")),
        help="Path to the reference intelligence CSV export file."
    )

    args = parser.parse_args()
    import_reference_csv(args.csv_file)


if __name__ == "__main__":
    main()
