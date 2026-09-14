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

# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""Core inference engine for local, offline foundational vision models."""

import os
from typing import List, Optional, Sequence, Tuple, Union
import numpy as np
from PIL import Image, ImageOps
try:
  import pillow_heif
  pillow_heif.register_heif_opener()
except Exception:
  pass
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

    self.model_path = os.path.abspath(model_path)
    clean_p = self.model_path.rstrip("/").rstrip("\\")
    self.model_name = os.path.basename(clean_p)
    self.is_vision_only = is_vision_only

    self.is_timm = False
    config_file = os.path.join(self.model_path, "config.json")
    if os.path.exists(config_file):
      try:
        with open(config_file, "r") as f:
          cfg_data = json.load(f)
          if "architecture" in cfg_data and "fastvit" in str(cfg_data["architecture"]).lower():
            self.is_timm = True
      except Exception:
        pass
    if "mobileclip" in self.model_name.lower():
      self.is_timm = True

    if self.is_timm:
      import timm
      self.model = timm.create_model("hf_hub:apple/mobileclip_s0_timm", pretrained=False)
      bin_p = os.path.join(self.model_path, "pytorch_model.bin")
      pt_p = os.path.join(self.model_path, "mobileclip_s0.pt")
      if os.path.exists(bin_p):
        state = torch.load(bin_p, map_location="cpu")
        self.model.load_state_dict(state, strict=False)
      elif os.path.exists(pt_p):
        state = torch.load(pt_p, map_location="cpu")
        img_state = {}
        for k, v in state.items():
          if k.startswith("image_encoder.model."):
            img_state[k[len("image_encoder.model."):]] = v
        self.model.load_state_dict(img_state if img_state else state, strict=False)
      self.model = self.model.to(self.device).eval()
      data_cfg = timm.data.resolve_model_data_config(self.model)
      self.timm_transform = timm.data.create_transform(**data_cfg, is_training=False)
      self.processor = None
    else:
      try:
        self.processor = AutoProcessor.from_pretrained(
            self.model_path, local_files_only=True
        )
      except Exception:
        from transformers import AutoImageProcessor
        self.processor = AutoImageProcessor.from_pretrained(
            self.model_path, local_files_only=True
        )
      self.model = AutoModel.from_pretrained(
          self.model_path, local_files_only=True
      ).to(self.device)
      self.model.eval()

  def compute_image_embedding(
      self,
      image_input: Union[str, Image.Image],
      normalize: bool = True,
  ) -> List[float]:
    """Extracts an embedding vector for a given image."""
    res = self.compute_image_embeddings_batch([image_input], normalize=normalize)
    return res[0]

  def compute_image_embeddings_batch(
      self,
      image_inputs: Sequence[Union[str, Image.Image]],
      batch_size: int = 32,
      normalize: bool = True,
  ) -> List[List[float]]:
    """Extracts embedding vectors for a batch of images."""
    if not image_inputs:
      return []

    if getattr(self, "is_timm", False):
      all_features = []
      for i in range(0, len(image_inputs), batch_size):
        batch = image_inputs[i : i + batch_size]
        tensors = []
        for item in batch:
          if isinstance(item, str):
            with Image.open(item) as raw_img:
              img = ImageOps.exif_transpose(raw_img).convert("RGB")
              tensors.append(self.timm_transform(img))
          else:
            img = ImageOps.exif_transpose(item).convert("RGB")
            tensors.append(self.timm_transform(img))

        batch_t = torch.stack(tensors).to(self.device)
        with torch.no_grad():
          features = self.model(batch_t)
          if normalize:
            features = features / features.norm(p=2, dim=-1, keepdim=True)
          batch_vectors = features.cpu().numpy()
          for vec in batch_vectors:
            all_features.append(vec.tolist())
      return all_features

    all_features = []
    for i in range(0, len(image_inputs), batch_size):
      batch = image_inputs[i : i + batch_size]
      pil_images = []
      for item in batch:
        if isinstance(item, str):
          with Image.open(item) as raw_img:
            img = ImageOps.exif_transpose(raw_img).convert("RGB")
            img.load()
        elif isinstance(item, Image.Image):
          img = ImageOps.exif_transpose(item).convert("RGB")
          img.load()
        else:
          img = item

        # Prevent HuggingFace channel ambiguity on degenerate/small 1-pixel crops
        if isinstance(img, Image.Image) and (img.size[0] < 10 or img.size[1] < 10):
          img = img.resize((max(224, img.size[0]), max(224, img.size[1])), Image.Resampling.BILINEAR)

        pil_images.append(img)

      inputs = self.processor(images=pil_images, return_tensors="pt").to(self.device)
      with torch.no_grad():
        if hasattr(self.model, "get_image_features"):
          features = self.model.get_image_features(**inputs)
          if not isinstance(features, torch.Tensor):
            features = getattr(features, "image_embeds", getattr(features, "pooler_output", features))
            if not isinstance(features, torch.Tensor) and hasattr(features, "last_hidden_state"):
              features = features.last_hidden_state[:, 0]
        else:
          outputs = self.model(**inputs)
          features = getattr(
              outputs, "pooler_output", outputs.last_hidden_state[:, 0]
          )

        if normalize:
          features = features / features.norm(p=2, dim=-1, keepdim=True)

        batch_vectors = features.cpu().numpy()
        for vec in batch_vectors:
          all_features.append(vec.tolist())

    return all_features

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
        if not isinstance(text_features, torch.Tensor):
          text_features = getattr(text_features, "text_embeds", getattr(text_features, "pooler_output", text_features))
          if not isinstance(text_features, torch.Tensor) and hasattr(text_features, "last_hidden_state"):
            text_features = text_features.last_hidden_state[:, 0]
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
      bounding_box: Union[Tuple[float, float, float, float], List[float]],
      normalize: bool = True,
  ) -> List[float]:
    """Extracts an embedding vector for an isolated sub-region (crop) with EXIF orientation correction."""
    if isinstance(image_input, str):
      with Image.open(image_input) as raw_img:
        img = ImageOps.exif_transpose(raw_img).convert("RGB")
    else:
      img = ImageOps.exif_transpose(image_input).convert("RGB")

    w, h = img.size

    # Check if normalized coordinates (e.g. 0.0 to 1.0 fractions)
    is_normalized = (
        isinstance(bounding_box, (list, tuple))
        and len(bounding_box) == 4
        and max(float(c) for c in bounding_box) <= 1.05
    )

    if is_normalized:
      x1, y1, x2, y2 = [max(0.0, min(1.0, float(c))) for c in bounding_box]
      left = int(x1 * w)
      top = int(y1 * h)
      right = int(x2 * w)
      bottom = int(y2 * h)
    else:
      x1, y1, x2, y2 = bounding_box
      left = int(float(x1))
      top = int(float(y1))
      right = int(float(x2))
      bottom = int(float(y2))

    # Guard bounds and guarantee valid crop dimensions (at least 8x8 pixels)
    left = max(0, min(left, w - 8))
    top = max(0, min(top, h - 8))
    right = max(left + 8, min(right, w))
    bottom = max(top + 8, min(bottom, h))

    crop = img.crop((left, top, right, bottom))
    crop = crop.convert("RGB")
    crop.load()
    return self.compute_image_embedding(crop, normalize=normalize)


