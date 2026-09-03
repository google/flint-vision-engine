# Copyright 2026 Google LLC
# Licensed under Apache 2.0

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
