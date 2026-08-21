from dataclasses import dataclass
from typing import List, Union, Optional
import numpy as np
from PIL import Image
import torch
from transformers import AutoProcessor, AutoModel

@dataclass
class EmbeddingResult:
    embeddings: np.ndarray
    dimension: int
    modality: str

class VisionEngine:
    def __init__(self, model_name="google/siglip-base-patch16-224", device=None):
        self.device = device or ("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))
        self.processor = AutoProcessor.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(self.device)
        self.model.eval()
    @torch.no_grad()
    def embed_images(self, images):
        if isinstance(images, Image.Image): images = [images]
        inputs = self.processor(images=images, return_tensors="pt").to(self.device)
        out = self.model.get_image_features(**inputs) if hasattr(self.model, "get_image_features") else self.model.vision_model(**inputs).pooler_output
        emb = out.detach().cpu().numpy()
        emb = emb / np.clip(np.linalg.norm(emb, axis=-1, keepdims=True), 1e-12, None)
        return EmbeddingResult(emb, emb.shape[-1], "image")
    @torch.no_grad()
    def embed_text(self, texts):
        if isinstance(texts, str): texts = [texts]
        inputs = self.processor(text=texts, padding="max_length", truncation=True, return_tensors="pt").to(self.device)
        out = self.model.get_text_features(**inputs) if hasattr(self.model, "get_text_features") else self.model.text_model(**inputs).pooler_output
        emb = out.detach().cpu().numpy()
        emb = emb / np.clip(np.linalg.norm(emb, axis=-1, keepdims=True), 1e-12, None)
        return EmbeddingResult(emb, emb.shape[-1], "text")
