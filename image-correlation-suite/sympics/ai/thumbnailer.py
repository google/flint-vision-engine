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
SYMPICS High-Speed WebP Thumbnail Generator
=========================================
Generates 256px WebP previews using LANCZOS anti-aliasing.
"""

import os
from PIL import Image
from sympics.core.raw_extractor import load_image_or_raw


def generate_thumbnail(source_path: str, dest_thumb_path: str, max_dim: int = 256) -> bool:
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
    except Exception:
        return False
