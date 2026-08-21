# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""FLINT Multimodal Vision Engine.

A high-performance framework for image/video feature extraction, cross-modal
semantic search, targeted crop searching, and keyframe indexing in air-gapped
environments.
"""

from flint.engine import FlintEngine
from flint.search import crop_search, text_to_image_search, visual_similarity_search
from flint.similarity import (
    cosine_similarity,
    dot_product,
    euclidean_distance,
    l2_normalize,
    search_vectors,
)
from flint.video import extract_keyframes_ssim, triage_video

__version__ = "0.1.0"

__all__ = [
    "FlintEngine",
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
