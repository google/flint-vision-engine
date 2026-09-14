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
SYMPICS Content-Addressed Storage (CAS) Vault Path Resolver
=========================================================
Resolves deterministic 2-layer hex paths for images, videos, and archives.
"""

import os
from typing import Tuple

IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif", ".gif", ".heic",
    ".cr3", ".cr2", ".nef", ".arw", ".dng", ".orf", ".rw2", ".pef", ".raf"
}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v"}
ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".tbz2"}


def get_media_category(extension: str) -> str:
    """Returns media subfolder category: 'images', 'videos', 'documents', or 'archives'."""
    ext = extension.lower()
    if ext in IMAGE_EXTS:
        return "images"
    elif ext in VIDEO_EXTS:
        return "videos"
    elif ext in ARCHIVE_EXTS:
        return "archives"
    return "documents"


def build_cas_rel_path(sha256: str, extension: str) -> str:
    """
    Constructs relative CAS path: 01_Media_Vault/<category>/<xx>/<yy>/<sha256><ext>
    Example: 01_Media_Vault/images/ab/cd/abcdef123456...jpg
    """
    clean_hash = sha256.lower().strip()
    ext = extension.lower()
    if not ext.startswith("."):
        ext = "." + ext

    category = get_media_category(ext)
    l1 = clean_hash[:2]
    l2 = clean_hash[2:4]

    return f"01_Media_Vault/{category}/{l1}/{l2}/{clean_hash}{ext}"


def build_thumbnail_rel_path(sha256: str) -> str:
    """
    Constructs relative thumbnail path: 02_Keyframe_Vault/thumbs_256px/<xx>/<yy>/<sha256>.webp
    """
    clean_hash = sha256.lower().strip()
    l1 = clean_hash[:2]
    l2 = clean_hash[2:4]
    return f"02_Keyframe_Vault/thumbs_256px/{l1}/{l2}/{clean_hash}.webp"
