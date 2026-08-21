# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""Core inference engine for local, offline foundational vision models."""

import os
from typing import List, Optional, Tuple, Union
import numpy as np
from PIL import Image
import torch
from transformers import AutoModel, AutoProcessor


class FlintEngine:
  """Model-agnostic feature extraction engine for local offline execution.

  Designed for zero-shot image embeddings, text embeddings, and crop extraction
  without runtime internet access.
  """

  def __init__(
      self,
      model_path: str,
      device: Optional[str] = None,
      is_vision_only: bool = False,
  ):
    """Initializes the engine from a local directory.

    Args:
        model_path: Path to the local model weights folder.
        device: Target device ('cuda', 'mps', 'cpu'). Auto-selected if None.
        is_vision_only: Set True for vision-only models like DINOv3 (disables
          text queries).
    """
    if not os.path.exists(model_path):
      raise FileNotFoundError(
          f"Local model path '{model_path}' not found. Ensure models are"
          " downloaded prior to running in air-gapped environments."
      )

    if device is None:
      if torch.cuda.is_available():
        self.device = "cuda"
      elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        self.device = "mps"
      else:
        self.device = "cpu"
    else:
      self.device = device

    self.model_path = model_path
    self.is_vision_only = is_vision_only

    self.processor = AutoProcessor.from_pretrained(
        model_path, local_files_only=True
    )
    self.model = AutoModel.from_pretrained(
        model_path, local_files_only=True
    ).to(self.device)
    self.model.eval()

  def compute_image_embedding(
      self,
      image_input: Union[str, Image.Image],
      normalize: bool = True,
  ) -> List[float]:
    """Extracts an embedding vector for a given image."""
    if isinstance(image_input, str):
      image = Image.open(image_input).convert("RGB")
    else:
      image = image_input.convert("RGB")

    inputs = self.processor(images=image, return_tensors="pt").to(self.device)
    with torch.no_grad():
      if hasattr(self.model, "get_image_features"):
        features = self.model.get_image_features(**inputs)
      else:
        outputs = self.model(**inputs)
        features = getattr(
            outputs, "pooler_output", outputs.last_hidden_state[:, 0]
        )

      if normalize:
        features = features / features.norm(p=2, dim=-1, keepdim=True)

    return features.squeeze().cpu().numpy().tolist()

  def compute_text_embedding(
      self,
      text_query: str,
      normalize: bool = True,
  ) -> List[float]:
    """Computes a semantic embedding vector for a text query."""
    if self.is_vision_only:
      raise NotImplementedError(
          "Text embedding computation is not supported for vision-only models"
          " (e.g., DINOv3)."
      )

    inputs = self.processor(
        text=[text_query], padding="max_length", return_tensors="pt"
    ).to(self.device)
    with torch.no_grad():
      if hasattr(self.model, "get_text_features"):
        text_features = self.model.get_text_features(**inputs)
      else:
        outputs = self.model(**inputs)
        text_features = getattr(
            outputs, "pooler_output", outputs.last_hidden_state[:, 0]
        )

      if normalize:
        text_features = text_features / text_features.norm(
            p=2, dim=-1, keepdim=True
        )

    return text_features.squeeze().cpu().numpy().tolist()

  def extract_crop_embedding(
      self,
      image_input: Union[str, Image.Image],
      bounding_box: Tuple[int, int, int, int],
      normalize: bool = True,
  ) -> List[float]:
    """Extracts an embedding vector for an isolated sub-region (crop)."""
    if isinstance(image_input, str):
      image = Image.open(image_input).convert("RGB")
    else:
      image = image_input.convert("RGB")

    crop = image.crop(bounding_box)
    return self.compute_image_embedding(crop, normalize=normalize)
