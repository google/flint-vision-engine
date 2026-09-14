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
Ensemble Vision Service (Dependency Injection)
==============================================
Manages a pluggable collection of BaseVisionEmbedder models.
"""

from typing import List, Dict, Any, Optional
from PIL import Image
from sympics.ai.base import BaseVisionEmbedder
from sympics.core.raw_extractor import load_image_or_raw


class EnsembleVisionService:
    """Orchestrates multi-model vision embeddings across injected embedder instances."""

    def __init__(self, embedders: Optional[List[BaseVisionEmbedder]] = None, device: str = "cpu"):
        self.device = device
        self.embedders = embedders or []

    def add_embedder(self, embedder: BaseVisionEmbedder) -> None:
        self.embedders.append(embedder)

    def compute_image_embeddings(self, image: Image.Image) -> Dict[str, List[float]]:
        """Returns {model_name: vector} for all registered embedders."""
        return {emb.model_name: emb.embed_image(image) for emb in self.embedders}

    def compute_batch_embeddings(self, filepaths: List[str]) -> List[Optional[Dict[str, List[float]]]]:
        """Loads images and computes multi-model embeddings for all files."""
        loaded_images = []
        valid_indices = []

        for idx, fp in enumerate(filepaths):
            img = load_image_or_raw(fp)
            if img is not None:
                loaded_images.append(img)
                valid_indices.append(idx)

        if not loaded_images:
            return [None] * len(filepaths)

        results = [None] * len(filepaths)
        model_batch_vectors = {}

        for emb in self.embedders:
            model_batch_vectors[emb.model_name] = emb.embed_image_batch(loaded_images)

        for i, original_idx in enumerate(valid_indices):
            results[original_idx] = {
                m_name: vectors[i] for m_name, vectors in model_batch_vectors.items()
            }

        return results
