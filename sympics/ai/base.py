# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
Base Vision Embedder Interface (Strategy Pattern)
=================================================
Abstract base class defining the contract for all AI vision embedders.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from PIL import Image


class BaseVisionEmbedder(ABC):
    """Abstract interface for multi-modal vision embedding models."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifier name stored in database (e.g. 'clip', 'siglip', 'siglip2_naflex')."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector embedding dimension (e.g. 512, 768)."""
        pass

    @property
    @abstractmethod
    def model_version(self) -> str:
        """Model checkpoint version identifier."""
        pass

    @abstractmethod
    def embed_image(self, image: Image.Image) -> List[float]:
        """Generates normalized vector embedding for a single PIL image."""
        pass

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Generates normalized vector embedding for a text query prompt."""
        pass

    @abstractmethod
    def embed_image_batch(self, images: List[Image.Image]) -> List[List[float]]:
        """Generates normalized vector embeddings for a batch of PIL images."""
        pass
