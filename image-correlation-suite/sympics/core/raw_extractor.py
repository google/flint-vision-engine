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
SYMPICS Pure-Python Camera RAW Embedded Preview Extractor
======================================================
Fast in-stream extraction of embedded high-resolution JPEGs from Canon (.CR3, .CR2),
Nikon (.NEF), Sony (.ARW), Adobe (.DNG), and Fuji (.RAF) camera RAW files.
"""

import io
import os
from typing import Optional
from PIL import Image

CAMERA_RAW_EXTS = {
    ".cr3", ".cr2", ".nef", ".arw", ".dng", ".orf", ".rw2", ".pef", ".raf"
}


def extract_embedded_raw_jpeg(filepath: str) -> Optional[Image.Image]:
    """
    Scans a Camera RAW file for embedded full-resolution JPEG preview payloads.
    Returns PIL Image or None.
    """
    try:
        file_size = os.path.getsize(filepath)
        scan_limit = min(file_size, 64 * 1024 * 1024)  # Scan up to first 64MB

        with open(filepath, "rb") as f:
            data = f.read(scan_limit)

        candidates = []
        pos = 0
        while True:
            start_idx = data.find(b"\xFF\xD8\xFF", pos)
            if start_idx == -1:
                break
            end_idx = data.find(b"\xFF\xD9", start_idx + 3)
            if end_idx != -1:
                jpeg_len = (end_idx + 2) - start_idx
                if jpeg_len > 32 * 1024:  # Ignore tiny icon previews (<32KB)
                    candidates.append((start_idx, end_idx + 2, jpeg_len))
                pos = end_idx + 2
            else:
                pos = start_idx + 3

        if not candidates:
            return None

        # Pick the largest embedded JPEG (full resolution preview)
        candidates.sort(key=lambda x: x[2], reverse=True)
        best_start, best_end, _ = candidates[0]
        jpeg_bytes = data[best_start:best_end]

        img = Image.open(io.BytesIO(jpeg_bytes))
        img.load()
        return img
    except Exception:
        return None


def load_image_or_raw(filepath: str) -> Optional[Image.Image]:
    """
    Loads an image from filepath, transparently decoding standard images (JPEG, PNG, TIFF)
    or extracting the embedded preview from Camera RAW files.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext in CAMERA_RAW_EXTS:
        raw_img = extract_embedded_raw_jpeg(filepath)
        if raw_img is not None:
            return raw_img

    try:
        img = Image.open(filepath)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        return img
    except Exception:
        return None
