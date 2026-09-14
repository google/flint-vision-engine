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
SYMPICS Multi-Model Vision Embedder Service
=========================================
Wraps CLIP (512d), SigLIP Base (768d), and SigLIP-2 NaFlex (768d) embeddings.
"""

from database.embedder_service import (
    VisionEmbedderService,
    get_embedder,
    extract_embedded_raw_jpeg,
    load_image_or_raw
)
from sympics.ai.thumbnailer import generate_thumbnail

__all__ = [
    "VisionEmbedderService",
    "get_embedder",
    "extract_embedded_raw_jpeg",
    "load_image_or_raw",
    "generate_thumbnail"
]
