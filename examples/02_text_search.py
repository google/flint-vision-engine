# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""Example 2: Zero-shot natural language text-to-image search across unindexed media."""

import numpy as np
import torch
from transformers import AutoModel, AutoProcessor


def cosine_similarity(vec1, vec2):
  v1, v2 = np.array(vec1), np.array(vec2)
  return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))


def search(query_vector, database_vectors, threshold=0.85):
  matches = []
  for filepath, db_vec in database_vectors.items():
    score = cosine_similarity(query_vector, db_vec)
    if score >= threshold:
      matches.append((filepath, score))
  return sorted(matches, key=lambda x: x[1], reverse=True)


def text_search(
    text_query, database_vectors, model_path="./models/clip-vit-b-32"
):
  processor = AutoProcessor.from_pretrained(model_path)
  model = AutoModel.from_pretrained(model_path)
  model.eval()

  inputs = processor(
      text=[text_query], padding="max_length", return_tensors="pt"
  )
  with torch.no_grad():
    text_features = model.get_text_features(**inputs)
    text_vector = text_features / text_features.norm(p=2, dim=-1, keepdim=True)
    text_vector = text_vector.squeeze().cpu().numpy().tolist()

  return search(text_vector, database_vectors)
