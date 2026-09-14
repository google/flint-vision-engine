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

"""Approximate Nearest Neighbor (ANN) indexing module for FLINT Vision Engine.

Provides clustered Inverted File (IVF) index and multi-probe candidate retrieval
for sub-linear approximate similarity search across high-dimensional embeddings.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np


class FlintANNIndex:
  """Clustered Inverted File (IVF) ANN index with multi-probe vector retrieval."""

  def __init__(self, metric: str = "cosine", n_clusters: Optional[int] = None, n_probe: Optional[int] = None):
    self.metric = metric
    self.n_clusters = n_clusters
    self.n_probe = n_probe
    self.centroids: Optional[np.ndarray] = None
    self.inv_lists: Dict[int, np.ndarray] = {}
    self.matrix: Optional[np.ndarray] = None
    self.is_trained = False
    self.num_vectors = 0
    self.dim = 0

  def build(self, matrix: np.ndarray, max_iters: int = 10) -> "FlintANNIndex":
    """Builds the IVF ANN index over the provided vector matrix."""
    if matrix is None or matrix.shape[0] == 0:
      self.is_trained = False
      return self

    self.num_vectors, self.dim = matrix.shape
    X = matrix.astype(np.float32)

    if self.metric == "cosine":
      norms = np.linalg.norm(X, axis=1, keepdims=True)
      norms[norms == 0] = 1.0
      self.matrix = X / norms
    else:
      self.matrix = X

    if self.num_vectors < 64:
      # Small database: exact search is optimal
      self.is_trained = True
      self.centroids = None
      return self

    # Determine cluster count: k ~ sqrt(N) bounded in [8, 128]
    if self.n_clusters is None:
      k = int(np.clip(int(np.sqrt(self.num_vectors) * 1.5), 8, 128))
    else:
      k = min(self.n_clusters, self.num_vectors)

    k = max(2, min(k, self.num_vectors))
    self.n_clusters = k

    # Multi-probe parameter
    if self.n_probe is None:
      self.n_probe = max(3, k // 3)
    else:
      self.n_probe = min(self.n_probe, k)

    # Initialize centroids with k-means++ style sampling
    np.random.seed(42)
    init_indices = np.random.choice(self.num_vectors, size=k, replace=False)
    centroids = self.matrix[init_indices].copy()

    # Mini-batch Spherical / Euclidean K-Means
    for _ in range(max_iters):
      if self.metric == "cosine" or self.metric == "dot":
        sims = np.dot(self.matrix, centroids.T)
        labels = np.argmax(sims, axis=1)
      else:
        # Euclidean: compute squared distances to centroids
        # ||x - c||^2 = ||x||^2 - 2 x.c + ||c||^2
        x_sq = np.sum(self.matrix ** 2, axis=1, keepdims=True)
        c_sq = np.sum(centroids ** 2, axis=1, keepdims=True).T
        dists = x_sq - 2 * np.dot(self.matrix, centroids.T) + c_sq
        labels = np.argmin(dists, axis=1)

      for c in range(k):
        members = self.matrix[labels == c]
        if len(members) > 0:
          c_vec = np.mean(members, axis=0)
          if self.metric == "cosine":
            c_norm = np.linalg.norm(c_vec)
            if c_norm > 0:
              c_vec = c_vec / c_norm
          centroids[c] = c_vec

    self.centroids = centroids

    # Build inverted lists
    if self.metric == "cosine" or self.metric == "dot":
      sims = np.dot(self.matrix, centroids.T)
      labels = np.argmax(sims, axis=1)
    else:
      x_sq = np.sum(self.matrix ** 2, axis=1, keepdims=True)
      c_sq = np.sum(centroids ** 2, axis=1, keepdims=True).T
      dists = x_sq - 2 * np.dot(self.matrix, centroids.T) + c_sq
      labels = np.argmin(dists, axis=1)

    self.inv_lists = {c: [] for c in range(k)}
    for idx, l in enumerate(labels):
      self.inv_lists[l].append(idx)

    for c in range(k):
      self.inv_lists[c] = np.array(self.inv_lists[c], dtype=np.int32)

    self.is_trained = True
    return self

  def query_candidates(self, query_vector: np.ndarray, top_k_probe: Optional[int] = None) -> np.ndarray:
    """Returns candidate vector indices to evaluate for a single query."""
    if not self.is_trained or self.centroids is None or self.num_vectors < 64:
      return np.arange(self.num_vectors, dtype=np.int32)

    n_probe = top_k_probe or self.n_probe or max(3, self.n_clusters // 3)
    n_probe = min(n_probe, self.n_clusters)

    q = query_vector.astype(np.float32)
    if self.metric == "cosine":
      q_norm = np.linalg.norm(q)
      if q_norm > 0:
        q = q / q_norm
      c_sims = np.dot(self.centroids, q)
      probe_clusters = np.argsort(-c_sims)[:n_probe]
    elif self.metric == "dot":
      c_sims = np.dot(self.centroids, q)
      probe_clusters = np.argsort(-c_sims)[:n_probe]
    else:
      c_dists = np.linalg.norm(self.centroids - q, axis=1)
      probe_clusters = np.argsort(c_dists)[:n_probe]

    cand_arrays = [self.inv_lists[c] for c in probe_clusters if len(self.inv_lists[c]) > 0]
    if not cand_arrays:
      return np.arange(self.num_vectors, dtype=np.int32)

    candidates = np.unique(np.concatenate(cand_arrays))
    return candidates

  def query_multi_candidates(self, query_matrix: np.ndarray, top_k_probe: Optional[int] = None) -> np.ndarray:
    """Returns candidate vector indices to evaluate for multiple reference vectors."""
    if not self.is_trained or self.centroids is None or self.num_vectors < 64:
      return np.arange(self.num_vectors, dtype=np.int32)

    n_probe = top_k_probe or self.n_probe or max(3, self.n_clusters // 3)
    n_probe = min(n_probe, self.n_clusters)

    Q = query_matrix.astype(np.float32)
    if self.metric == "cosine":
      q_norms = np.linalg.norm(Q, axis=1, keepdims=True)
      q_norms[q_norms == 0] = 1.0
      Q = Q / q_norms

    cand_set = set()
    if self.metric == "cosine" or self.metric == "dot":
      sims = np.dot(Q, self.centroids.T)
      for row in sims:
        top_c = np.argsort(-row)[:n_probe]
        for c in top_c:
          cand_set.update(self.inv_lists[c])
    else:
      for q in Q:
        dists = np.linalg.norm(self.centroids - q, axis=1)
        top_c = np.argsort(dists)[:n_probe]
        for c in top_c:
          cand_set.update(self.inv_lists[c])

    if not cand_set:
      return np.arange(self.num_vectors, dtype=np.int32)

    return np.array(list(cand_set), dtype=np.int32)
