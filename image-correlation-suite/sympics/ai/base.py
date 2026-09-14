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
