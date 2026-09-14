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

# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""FLINT Multimodal Vision Engine.

A high-performance framework for image/video feature extraction, cross-modal
semantic search, targeted crop searching, and keyframe indexing in air-gapped
environments with local SQLite vector persistence.
"""

from flint.db import MediaDatabase
from flint.engine import FlintEngine
from flint.search import crop_search, text_to_image_search, visual_similarity_search
from flint.service import FlintService
from flint.similarity import (
    cosine_similarity,
    dot_product,
    euclidean_distance,
    l2_normalize,
    search_vectors,
)
from flint.video import extract_keyframes_ssim, triage_video

__version__ = "0.2.0"

__all__ = [
    "FlintEngine",
    "FlintService",
    "MediaDatabase",
    "cosine_similarity",
    "dot_product",
    "euclidean_distance",
    "l2_normalize",
    "search_vectors",
    "text_to_image_search",
    "crop_search",
    "visual_similarity_search",
    "triage_video",
    "extract_keyframes_ssim",
]

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

