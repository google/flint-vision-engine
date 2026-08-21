# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""Example 1: Computing normalized image embeddings for media archives."""

import os
from PIL import Image
import torch
from transformers import AutoModel, AutoProcessor


def compute_embedding(image_path, model_path="./models/siglip2-base"):
  """Extracts an L2-normalized image embedding using local model weights."""
  processor = AutoProcessor.from_pretrained(model_path)
  model = AutoModel.from_pretrained(model_path)
  model.eval()

  image = Image.open(image_path).convert("RGB")
  inputs = processor(images=image, return_tensors="pt")

  with torch.no_grad():
    features = model.get_image_features(**inputs)
    # L2 Normalize the vector for Cosine Similarity
    features = features / features.norm(p=2, dim=-1, keepdim=True)

  return features.squeeze().cpu().numpy().tolist()


def main():
  # Example usage with sample image
  sample_image = "./evidence_raw/sample.jpg"

  if os.path.exists(sample_image):
    print(f"Computing embedding for {sample_image}...")
    vector = compute_embedding(sample_image)
    print(f"Extraction complete! Vector dimension: {len(vector)}")
    print(f"Vector preview (first 5 elements): {vector[:5]}")
  else:
    print(f"Add an image at {sample_image} to run local inference.")


if __name__ == "__main__":
  main()
