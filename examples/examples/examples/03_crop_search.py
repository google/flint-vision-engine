# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""Example 3: Targeted crop search and alert generation for distinct physical items."""

from PIL import Image
import torch
from transformers import AutoModel, AutoProcessor


def extract_and_embed_crop(
    image_path, bounding_box, model_path="./models/siglip2-naflex"
):
  """Extracts embedding vector for an isolated sub-region (crop).

  Bounding box format: (left, top, right, bottom).
  """
  processor = AutoProcessor.from_pretrained(model_path)
  model = AutoModel.from_pretrained(model_path)
  model.eval()

  image = Image.open(image_path).convert("RGB")
  crop = image.crop(bounding_box)

  inputs = processor(images=crop, return_tensors="pt")
  with torch.no_grad():
    crop_features = model.get_image_features(**inputs)
    crop_vector = crop_features / crop_features.norm(p=2, dim=-1, keepdim=True)

  return crop_vector.squeeze().cpu().numpy().tolist()
