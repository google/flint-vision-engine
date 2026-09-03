# Copyright 2026 Google LLC
# Licensed under Apache 2.0

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
