# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
CLIP Vision Embedder (OpenAI ViT-B/32 - 512-dim)
"""

from typing import List
from PIL import Image
import torch
from transformers import AutoProcessor, AutoModel
from sympics.ai.base import BaseVisionEmbedder


class ClipVisionEmbedder(BaseVisionEmbedder):

    def __init__(self, device: str = "cpu", dtype: torch.dtype = torch.float32):
        self._device = device
        self._dtype = dtype
        self.processor = AutoProcessor.from_pretrained("openai/clip-vit-base-patch32")
        self.model = AutoModel.from_pretrained("openai/clip-vit-base-patch32", torch_dtype=dtype).to(device)
        self.model.eval()

    @property
    def model_name(self) -> str:
        return "clip"

    @property
    def dimension(self) -> int:
        return 512

    @property
    def model_version(self) -> str:
        return "openai/clip-vit-base-patch32"

    def _extract_tensor(self, out) -> torch.Tensor:
        if isinstance(out, torch.Tensor):
            return out
        if hasattr(out, "pooler_output") and out.pooler_output is not None:
            return out.pooler_output
        if hasattr(out, "image_embeds") and out.image_embeds is not None:
            return out.image_embeds
        if hasattr(out, "text_embeds") and out.text_embeds is not None:
            return out.text_embeds
        if isinstance(out, (tuple, list)):
            return out[0]
        return out

    def embed_image(self, image: Image.Image) -> List[float]:
        return self.embed_image_batch([image])[0]

    def embed_image_batch(self, images: List[Image.Image]) -> List[List[float]]:
        inputs = self.processor(images=images, return_tensors="pt").to(self._device)
        with torch.no_grad():
            out = self.model.get_image_features(**inputs)
            feats = self._extract_tensor(out)
            feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
            return feats.cpu().float().numpy().tolist()

    def embed_text(self, text: str) -> List[float]:
        inputs = self.processor(text=[text], return_tensors="pt", padding=True).to(self._device)
        with torch.no_grad():
            out = self.model.get_text_features(**inputs)
            feats = self._extract_tensor(out)
            feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
            return feats.cpu().float().numpy()[0].tolist()
