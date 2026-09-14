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

"""High-level search APIs for text, crop, and visual similarity matching."""

from typing import Dict, List, Sequence, Tuple, Union
from flint.engine import FlintEngine
from flint.similarity import search_vectors


def text_to_image_search(
    engine: FlintEngine,
    text_query: str,
    database_vectors: Dict[str, Union[Sequence[float], list]],
    threshold: float = 0.85,
) -> List[Tuple[str, float]]:
  query_vec = engine.compute_text_embedding(text_query, normalize=True)
  return search_vectors(
      query_vec, database_vectors, threshold=threshold, metric="cosine"
  )


def crop_search(
    engine: FlintEngine,
    image_path: str,
    bounding_box: Tuple[int, int, int, int],
    database_vectors: Dict[str, Union[Sequence[float], list]],
    threshold: float = 0.85,
    metric: str = "cosine",
) -> List[Tuple[str, float]]:
  normalize = metric != "dot"
  crop_vec = engine.extract_crop_embedding(
      image_path, bounding_box, normalize=normalize
  )
  return search_vectors(
      crop_vec, database_vectors, threshold=threshold, metric=metric
  )


def visual_similarity_search(
    engine: FlintEngine,
    image_path: str,
    database_vectors: Dict[str, Union[Sequence[float], list]],
    threshold: float = 0.85,
    metric: str = "cosine",
) -> List[Tuple[str, float]]:
  normalize = metric != "dot"
  query_vec = engine.compute_image_embedding(image_path, normalize=normalize)
  return search_vectors(
      query_vec, database_vectors, threshold=threshold, metric=metric
  )
