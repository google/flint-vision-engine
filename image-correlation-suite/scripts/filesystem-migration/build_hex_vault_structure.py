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
SYMPICS ENTERPRISE STORAGE VAULT INITIALIZER
===============================================================================
This script builds the high-performance two-layer hexadecimal folder structure
(00/00 through ff/ff = 65,536 buckets) on your local or network storage drive.

Features:
- Completely standalone (uses only standard Python libraries, no pip install needed).
- Works seamlessly on Windows, Linux, and Network Attached Storage (SMB/NFS/UNC).
- Step-by-step interactive prompts with permission and path validation.
- Real-time visual progress counter.
- Automated integrity verification check upon completion.
===============================================================================
"""

import os
import sys
import time
import argparse
import json
from pathlib import Path


def print_banner():
    print("===============================================================================")
    print("  SYMPICS - TWO-LAYER HEXADECIMAL STORAGE VAULT BUILDER")
    print("===============================================================================")


def get_user_input(prompt_text, default_val=None):
    """Clean interactive input wrapper supporting default values."""
    if default_val:
        full_prompt = f"{prompt_text} [{default_val}]: "
    else:
        full_prompt = f"{prompt_text}: "
    
    try:
        user_val = input(full_prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\n[CANCELLED] Operation aborted by user.")
        sys.exit(0)
        
    if not user_val and default_val:
        return default_val
    return user_val


def validate_and_prep_path(target_path_str):
    """Validates the target path, creates parent if needed, and tests write permissions."""
    clean_path = os.path.abspath(os.path.expanduser(target_path_str))
    
    print(f"\n[*] Checking target location: {clean_path}")
    
    try:
        os.makedirs(clean_path, exist_ok=True)
    except Exception as e:
        print(f"\n[ERROR] Cannot create target directory at '{clean_path}'.")
        print(f"Reason: {e}")
        print("Please check drive letter, network share permissions, or run as Administrator.")
        return None

    # Test write permissions with a temporary marker file
    test_file = os.path.join(clean_path, ".sympics_write_test.tmp")
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("test_permission")
        if os.path.exists(test_file):
            os.remove(test_file)
    except Exception as e:
        print(f"\n[ERROR] Write permission denied in target directory '{clean_path}'.")
        print(f"Details: {e}")
        print("Please ensure your user account has WRITE/MODIFY permissions on this folder or drive.")
        return None

    return clean_path


def build_two_layer_hex_tree(root_dir, category_name="Media Vault"):
    """
    Builds the 65,536 directory tree (00/00 to ff/ff) inside root_dir.
    Displays an interactive real-time progress bar.
    """
    hex_chars = [f"{i:02x}" for i in range(256)]  # ['00', '01', ..., 'fe', 'ff']
    total_folders = 256 * 256  # 65,536

    print(f"\n-------------------------------------------------------------------------------")
    print(f" Building 65,536 Hexadecimal Buckets for: {category_name}")
    print(f" Destination: {root_dir}")
    print(f"-------------------------------------------------------------------------------")
    
    start_time = time.time()
    created_count = 0
    
    # Progress visualization loop
    for i, h1 in enumerate(hex_chars):
        level1_path = os.path.join(root_dir, h1)
        for h2 in hex_chars:
            target_folder = os.path.join(level1_path, h2)
            os.makedirs(target_folder, exist_ok=True)
            created_count += 1
            
        # Update progress on every outer hex bucket (every 256 folders)
        pct = (created_count / total_folders) * 100
        elapsed = time.time() - start_time
        speed = created_count / elapsed if elapsed > 0 else 0
        bar_len = 30
        filled = int(bar_len * (created_count / total_folders))
        bar = "█" * filled + "-" * (bar_len - filled)
        
        sys.stdout.write(
            f"\r [{bar}] {pct:5.1f}% | Progress: {created_count:,}/{total_folders:,} folders | Speed: {speed:5.0f} folders/sec"
        )
        sys.stdout.flush()
        
    total_time = time.time() - start_time
    print(f"\n[+] Finished building {created_count:,} folders in {total_time:.2f} seconds.")


def verify_structure(root_dir):
    """Performs a strict mathematical verification check to ensure all 65,536 buckets exist."""
    print("\n[*] Running Automated Integrity Verification...")
    hex_chars = [f"{i:02x}" for i in range(256)]
    missing = []
    
    for h1 in hex_chars:
        for h2 in hex_chars:
            expected_folder = os.path.join(root_dir, h1, h2)
            if not os.path.isdir(expected_folder):
                missing.append(f"{h1}/{h2}")
                
    if not missing:
        print(" [+] VERIFICATION PASSED: All 65,536 subdirectories verified and ready for evidence storage.")
        return True
    else:
        print(f" [[-]] VERIFICATION FAILED: Found {len(missing)} missing directories.")
        if len(missing) <= 5:
            print(f" Missing folders: {', '.join(missing)}")
        return False


def main():
    print_banner()

    parser = argparse.ArgumentParser(
        description="SYMPICS Storage Vault Initializer — Builds the 65,536 two-layer hex directory tree."
    )
    parser.add_argument(
        "--target-dir",
        "-t",
        help="Absolute path where the SYMPICS storage structure will be created."
    )
    parser.add_argument(
        "--structure-type",
        "-s",
        choices=["full_sympics", "vault_only"],
        default="full_sympics",
        help="Type of structure: 'full_sympics' (Media + Thumbs + Staging + Exports) or 'vault_only' (Single 65k hex tree)."
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without confirmation prompts (useful for automated scripts)."
    )

    args = parser.parse_args()

    # Step 1: Determine Destination Path
    target_path = args.target_dir
    if target_path and not os.path.isabs(target_path):
        if not os.path.exists(target_path) and os.path.exists(os.path.join("..", target_path)):
            target_path = os.path.join("..", target_path)

    if not target_path:
        print("Please enter the destination path where you want to build the new storage structure.")
        print("Examples:")
        print("  - Windows Local:   D:\\SYMPICSStorage   or   E:\\LAN_Storage")
        print("  - Windows Network: \\\\STORAGE-SERVER\\SYMPICSData")
        print("  - Linux/Mac:       /mnt/storage/SYMPICSData")
        print()
        
        # Suggest current working directory or standard default
        cand_local = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "future-lan-storage"))
        cand_parent = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "future-lan-storage"))
        default_candidate = cand_parent if (os.path.exists(cand_parent) and not os.path.exists(cand_local)) else cand_local
        target_path = get_user_input("Enter Target Directory Path", default_val=default_candidate)

    # Step 2: Validate Target Path
    validated_path = validate_and_prep_path(target_path)
    if not validated_path:
        print("\n[ABORTED] Please resolve path/permission issues and run the script again.")
        sys.exit(1)

    # Step 3: Choose Structure Layout
    struct_type = args.structure_type
    if not args.non_interactive and not args.target_dir:
        print("\nSelect the type of folder structure you want to generate:")
        print("  [1] Recommended: Full SYMPICS Enterprise Storage Suite")
        print("      - 01_Media_Vault/images/ (65,536 Hex Folders)")
        print("      - 01_Media_Vault/videos/ (65,536 Hex Folders)")
        print("      - 02_Keyframe_Vault/thumbs_256px/ (65,536 Hex Folders)")
        print("      - 02_Keyframe_Vault/video_frames/")
        print("      - 03_Ingestion_Staging/ (For USB and Reference CSV drops)")
        print("      - 04_Case_Exports/ (For Standard Case JSON and Court Packages)")
        print("  [2] Custom / Standalone Hex Vault Only")
        print("      - Direct (65,536 Hex Folders directly inside your chosen directory)")
        print()
        
        choice = get_user_input("Choose Option (1 or 2)", default_val="1")
        struct_type = "full_sympics" if choice == "1" else "vault_only"

    # Step 4: Final Confirmation
    print(f"\n===============================================================================")
    print(f" STORAGE INITIALIZATION SUMMARY")
    print(f"===============================================================================")
    print(f" Target Path     : {validated_path}")
    print(f" Layout Structure: {'Full SYMPICS Enterprise Suite' if struct_type == 'full_sympics' else 'Standalone Vault Only'}")
    print(f" Total Buckets   : {'196,608 (3 x 65,536 Trees)' if struct_type == 'full_sympics' else '65,536 Folders'}")
    print(f" Disk Space Used : 0 MB (Zero extra bytes used until media is ingested)")
    print(f"===============================================================================")

    if not args.non_interactive:
        confirm = get_user_input("Proceed with building folder structure? (yes/no)", default_val="yes").lower()
        if confirm not in ("y", "yes"):
            print("\n[ABORTED] Operation cancelled by user.")
            sys.exit(0)

    # Step 5: Execution
    print("\n[*] Starting Storage Vault Generation...")
    start_total_time = time.time()

    if struct_type == "full_sympics":
        # Create Core Parent Trees
        media_images_path = os.path.join(validated_path, "01_Media_Vault", "images")
        media_videos_path = os.path.join(validated_path, "01_Media_Vault", "videos")
        thumbs_path = os.path.join(validated_path, "02_Keyframe_Vault", "thumbs_256px")
        video_frames_path = os.path.join(validated_path, "02_Keyframe_Vault", "video_frames")
        staging_path = os.path.join(validated_path, "03_Ingestion_Staging")
        exports_path = os.path.join(validated_path, "04_Case_Exports")

        os.makedirs(video_frames_path, exist_ok=True)
        os.makedirs(staging_path, exist_ok=True)
        os.makedirs(exports_path, exist_ok=True)

        # Build Hex Trees
        build_two_layer_hex_tree(media_images_path, category_name="Primary Images Vault (01_Media_Vault/images)")
        verify_structure(media_images_path)

        build_two_layer_hex_tree(media_videos_path, category_name="Primary Videos Vault (01_Media_Vault/videos)")
        verify_structure(media_videos_path)

        build_two_layer_hex_tree(thumbs_path, category_name="Fast UI Thumbnails Vault (02_Keyframe_Vault/thumbs_256px)")
        verify_structure(thumbs_path)

    else:
        # Standalone Vault
        build_two_layer_hex_tree(validated_path, category_name="Standalone Vault")
        verify_structure(validated_path)

    # Step 6: Write Manifest / Metadata Marker
    marker_file = os.path.join(validated_path, ".sympics_vault_manifest.json")
    manifest_data = {
        "sympics_storage_version": "4.0",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "structure_type": struct_type,
        "nesting_level": 2,
        "total_hex_buckets_per_tree": 65536,
        "status": "READY_FOR_EVIDENCE_INGESTION"
    }
    with open(marker_file, "w", encoding="utf-8") as mf:
        json.dump(manifest_data, mf, indent=2)

    total_elapsed = time.time() - start_total_time

    # Step 7: Completion Notice
    print(f"\n===============================================================================")
    print(f" [+] STORAGE INITIALIZATION COMPLETE (Elapsed: {total_elapsed:.2f}s)")
    print(f"===============================================================================")
    print(f" Master Vault Path : {validated_path}")
    print(f" Manifest Status   : Ready for Evidence Ingestion")
    print(f" Next Steps        : You can now point SYMPICS Ingestion Engine / Ingestion Studio")
    print(f"                     to this location as the destination Master Storage LAN.")
    print(f"===============================================================================\n")


if __name__ == "__main__":
    main()
