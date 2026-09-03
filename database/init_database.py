#!/usr/bin/env python3
# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
===============================================================================
SYMPICS POSTGRESQL DATABASE INITIALIZER
===============================================================================
CLI tool to test PostgreSQL connectivity, create the SYMPICS database, and apply
the Migration Manifest table and schema.
===============================================================================
"""

import os
import sys
import getpass
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db


def print_banner():
    print("===============================================================================")
    print("  SYMPICS - POSTGRESQL DATABASE INITIALIZER (MODULE 1)")
    print("===============================================================================")


def get_input(prompt_text, default_val=None, is_password=False):
    full_prompt = f"{prompt_text} [{default_val}]: " if default_val else f"{prompt_text}: "
    try:
        if is_password:
            val = getpass.getpass(full_prompt)
        else:
            val = input(full_prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\n[CANCELLED] Operation aborted.")
        sys.exit(0)
    return val if val else (default_val or "")


def main():
    print_banner()

    current_cfg = db.load_db_config()
    current_os_user = getpass.getuser()

    print("[*] Detecting available PostgreSQL connection methods...")
    
    # Check if local peer socket connection works right away
    auto_ok, auto_cfg, auto_err = db.test_connection()

    if auto_ok:
        print(f" [+] Auto-detected active PostgreSQL instance!")
        print(f"     Target user: '{auto_cfg.get('user', current_os_user)}' | Database: '{auto_cfg.get('database', 'sympics_db')}'")
        print("\nConnection Options:")
        print("  [1] Recommended: Use Auto-Detected Local PostgreSQL Connection")
        print("  [2] Custom / Manual TCP Connection (Host, Port, User, Password)")
        print()
        choice = get_input("Select Option (1 or 2)", default_val="1")
    else:
        choice = "2"

    if choice == "1" and auto_ok:
        working_cfg = auto_cfg
    else:
        print("\nConfigure manual PostgreSQL connection parameters:")
        print("Press ENTER to accept the bracketed default values.\n")

        host = get_input("PostgreSQL Host (leave blank for local socket, or '127.0.0.1')", default_val=current_cfg.get("host", ""))
        port_str = get_input("PostgreSQL Port", default_val=str(current_cfg.get("port", 5432)))
        database = get_input("Database Name to Create/Use", default_val=current_cfg.get("database", "sympics_db"))
        user = get_input("Username", default_val=current_cfg.get("user", current_os_user))
        password = get_input("Password (leave blank if peer/trust authentication)", default_val="", is_password=False)

        try:
            port = int(port_str)
        except ValueError:
            port = 5432

        manual_cfg = {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password
        }

        print(f"\n[*] Testing connection with provided parameters...")
        success, working_cfg, err = db.test_connection(manual_cfg)

        if not success:
            print(f"\n[ERROR] Could not connect to PostgreSQL server.")
            print(f"Details: {err}")
            print("\nTroubleshooting Tips:")
            print(f" 1. If running locally on Linux, try leaving Host and Password blank and using user '{current_os_user}'.")
            print(" 2. If using TCP '127.0.0.1', verify the password for your user in pg_hba.conf.")
            print(" 3. Ensure the PostgreSQL service is actively running.")
            sys.exit(1)
        else:
            print(" [+] Connection test successful!")

    # Save working config
    db.save_db_config(working_cfg)
    target_database = working_cfg.get("database", "sympics_db")

    # Initialize Database & Apply Migration Manifest Schema
    print(f"\n[*] Initializing database '{target_database}' and applying schema_migration_manifest.sql...")
    try:
        db.init_db(working_cfg)
        print(" [+] 'migration_manifest' table created successfully!")
        print(" [+] 'v_migration_summary' reporting view created successfully!")
    except Exception as e:
        print(f"\n[ERROR] Schema application failed: {e}")
        sys.exit(1)

    # Verify table existence
    try:
        conn = db.get_connection(working_cfg)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'migration_manifest'
                ORDER BY ordinal_position;
            """)
            columns = cur.fetchall()
            print(f"\n[*] Verified 'migration_manifest' table ({len(columns)} columns defined):")
            for col in columns[:8]:
                print(f"    - {col['column_name']} ({col['data_type']})")
            if len(columns) > 8:
                print(f"    - ... and {len(columns) - 8} more columns.")
        conn.close()
    except Exception as e:
        print(f"[!] Verification warning: {e}")

    print(f"\n===============================================================================")
    print(f" [+] DATABASE MODULE 1 INITIALIZATION COMPLETE")
    print(f"===============================================================================")
    print(f" Database Target : {target_database}")
    print(f" Config Saved    : db_config.json")
    print(f" Next Steps      : The migration discovery script can now begin scanning legacy")
    print(f"                   folders and inserting records into 'migration_manifest'.")
    print(f"===============================================================================\n")


if __name__ == "__main__":
    main()
