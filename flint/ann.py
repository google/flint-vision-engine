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

"""Clustered Inverted File (IVF) Approximate Nearest Neighbors Index."""

from typing import Optional, Tuple
import numpy as np


class FlintANNIndex:
  """Clustered Inverted File (IVF) index with stabilized spherical k-means."""

  def __init__(self, metric: str = "cosine"):
    self.metric = metric
    self.centroids: Optional[np.ndarray] = None
    self.inv_lists: dict[int, np.ndarray] = {}
    self.num_vectors: int = 0
    self.dim: int = 0
    self.n_clusters: int = 0
    self.n_probe: int = 0

  def build(self, matrix: np.ndarray, max_iters: int = 10) -> "FlintANNIndex":
    """Builds the IVF index using spherical k-means clustering.

    Args:
      matrix: Normalized embedding matrix of shape [N, D].
      max_iters: Maximum clustering iterations.

    Returns:
      Self with trained centroids and inverted lists.
    """
    self.num_vectors, self.dim = matrix.shape
    if self.num_vectors < 64:
      return self  # Datasets under 64 vectors default to exact search

    # Dynamic cluster scaling: k ~ 4*sqrt(N) bounded in [16, 4096]
    k = int(np.clip(int(np.sqrt(self.num_vectors) * 4.0), 16, 4096))
    self.n_clusters = min(k, self.num_vectors)
    self.n_probe = int(np.clip(int(np.sqrt(self.n_clusters)), 1, 64))

    np.random.seed(42)
    init_ids = np.random.choice(
        self.num_vectors, self.n_clusters, replace=False
    )
    self.centroids = matrix[init_ids].copy()

    for _ in range(max_iters):
      sims = np.dot(matrix, self.centroids.T)
      labels = np.argmax(sims, axis=1)
      for c in range(self.n_clusters):
        members = matrix[labels == c]
        if len(members) > 0:
          c_vec = np.mean(members, axis=0)
          c_norm = np.linalg.norm(c_vec)
          if c_norm > 1e-12:
            self.centroids[c] = c_vec / c_norm

    self.inv_lists = {
        c: np.where(labels == c)[0] for c in range(self.n_clusters)
    }
    return self

  def query_candidates(self, query_vec: np.ndarray) -> np.ndarray:
    """Probes nearest centroids and returns candidate indices with empty-list guards.

    Args:
      query_vec: Normalized query embedding of shape [D].

    Returns:
      1D array of candidate indices.
    """
    if self.centroids is None:
      return np.arange(self.num_vectors, dtype=np.int32)

    c_sims = np.dot(self.centroids, query_vec)
    probe_clusters = np.argsort(-c_sims)[: self.n_probe]
    cand_arrays = [
        self.inv_lists[c]
        for c in probe_clusters
        if len(self.inv_lists.get(c, [])) > 0
    ]

    if not cand_arrays:
      return np.empty(0, dtype=np.int32)
    return np.unique(np.concatenate(cand_arrays))


def search_by_multi_vectors(
    sub_matrix: np.ndarray,
    query_matrix: np.ndarray,
    aggregation: str = "max",
) -> Tuple[np.ndarray, np.ndarray]:
  """Pairwise similarity over pre-normalized matrices of shapes [N, D] and [M, D].

  Args:
    sub_matrix: Stored media embedding matrix [N, D].
    query_matrix: Multi-target query matrix [M, D].
    aggregation: 'max' for peak detection, 'mean' for consensus averaging.

  Returns:
    Tuple of (aggregated_scores, best_target_indices).
  """
  sim_matrix = np.dot(sub_matrix, query_matrix.T)
  if aggregation == "max":
    agg_scores = np.max(sim_matrix, axis=1)
  else:
    agg_scores = np.mean(sim_matrix, axis=1)
  best_target_idx = np.argmax(sim_matrix, axis=1)
  return agg_scores, best_target_idx
