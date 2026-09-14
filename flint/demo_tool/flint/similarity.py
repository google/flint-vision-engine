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

"""Vector similarity and distance metrics for embedding comparison."""

from typing import Dict, List, Sequence, Tuple, Union
import numpy as np


def l2_normalize(vec: Union[np.ndarray, Sequence[float]]) -> np.ndarray:
  arr = np.asarray(vec, dtype=np.float32)
  norm = np.linalg.norm(arr)
  if norm == 0:
    return arr
  return arr / norm


def cosine_similarity(
    vec1: Union[np.ndarray, Sequence[float]],
    vec2: Union[np.ndarray, Sequence[float]],
) -> float:
  v1 = np.asarray(vec1, dtype=np.float32)
  v2 = np.asarray(vec2, dtype=np.float32)
  denom = np.linalg.norm(v1) * np.linalg.norm(v2)
  if denom == 0:
    return 0.0
  return float(np.dot(v1, v2) / denom)


def dot_product(
    vec1: Union[np.ndarray, Sequence[float]],
    vec2: Union[np.ndarray, Sequence[float]],
) -> float:
  v1 = np.asarray(vec1, dtype=np.float32)
  v2 = np.asarray(vec2, dtype=np.float32)
  return float(np.dot(v1, v2))


def euclidean_distance(
    vec1: Union[np.ndarray, Sequence[float]],
    vec2: Union[np.ndarray, Sequence[float]],
) -> float:
  v1 = np.asarray(vec1, dtype=np.float32)
  v2 = np.asarray(vec2, dtype=np.float32)
  return float(np.linalg.norm(v1 - v2))


def search_vectors(
    query_vector: Union[np.ndarray, Sequence[float]],
    database_vectors: Dict[str, Union[np.ndarray, Sequence[float]]],
    threshold: float = 0.85,
    metric: str = "cosine",
) -> List[Tuple[str, float]]:
  matches = []
  for filepath, db_vec in database_vectors.items():
    if metric == "cosine":
      score = cosine_similarity(query_vector, db_vec)
      if score >= threshold:
        matches.append((filepath, score))
    elif metric == "dot":
      score = dot_product(query_vector, db_vec)
      if score >= threshold:
        matches.append((filepath, score))
    elif metric == "euclidean":
      dist = euclidean_distance(query_vector, db_vec)
      if dist <= threshold:
        matches.append((filepath, dist))

  reverse = metric != "euclidean"
  return sorted(matches, key=lambda x: x[1], reverse=reverse)
