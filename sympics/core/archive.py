# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
SYMPICS Safe Archive Extractor & Zip Slip Defender
===============================================
Extracts ZIP and TAR archives while preventing directory traversal attacks.
"""

import os
import zipfile
import tarfile
from typing import List


def is_safe_path(base_dir: str, target_path: str) -> bool:
    """Verifies that target_path resolves strictly within base_dir."""
    base = os.path.realpath(base_dir)
    target = os.path.realpath(target_path)
    return target.startswith(base + os.sep) or target == base


def safe_extract_zip(zip_path: str, dest_dir: str) -> List[str]:
    """Extracts a ZIP archive while defending against Zip Slip path traversal."""
    extracted_files = []
    os.makedirs(dest_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            target_path = os.path.join(dest_dir, member.filename)
            if not is_safe_path(dest_dir, target_path):
                raise ValueError(f"Security Alert: Blocked Zip Slip path traversal in {member.filename}")
            zf.extract(member, dest_dir)
            extracted_files.append(target_path)

    return extracted_files


def safe_extract_tar(tar_path: str, dest_dir: str) -> List[str]:
    """Extracts a TAR archive while defending against path traversal."""
    extracted_files = []
    os.makedirs(dest_dir, exist_ok=True)

    with tarfile.open(tar_path, "r:*") as tf:
        for member in tf.getmembers():
            target_path = os.path.join(dest_dir, member.name)
            if not is_safe_path(dest_dir, target_path):
                raise ValueError(f"Security Alert: Blocked Tar path traversal in {member.name}")
            tf.extract(member, dest_dir)
            extracted_files.append(target_path)

    return extracted_files
