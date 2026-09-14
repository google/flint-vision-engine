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
SYMPICS AI Vision Package
=======================
Pluggable multi-model vision embedders and WebP thumbnail generators.
"""

from sympics.ai.base import BaseVisionEmbedder
from sympics.ai.clip_embedder import ClipVisionEmbedder
from sympics.ai.siglip_embedder import SigLipVisionEmbedder
from sympics.ai.siglip2_embedder import SigLip2VisionEmbedder
from sympics.ai.ensemble import EnsembleVisionService
from sympics.ai.thumbnailer import generate_thumbnail

__all__ = [
    "BaseVisionEmbedder",
    "ClipVisionEmbedder",
    "SigLipVisionEmbedder",
    "SigLip2VisionEmbedder",
    "EnsembleVisionService",
    "generate_thumbnail",
]
