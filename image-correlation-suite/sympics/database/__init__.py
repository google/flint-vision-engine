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

"""
SYMPICS Database Package
======================
Repository pattern data access layer for PostgreSQL and pgvector.
"""

from sympics.database.connection import connection_manager, ConnectionManager
from sympics.database.repositories.asset_repo import MediaAssetRepository
from sympics.database.repositories.vector_repo import VectorEmbeddingRepository
from sympics.database.repositories.manifest_repo import ManifestRepository
from sympics.database.repositories.case_repo import CaseRepository

asset_repo = MediaAssetRepository(connection_manager)
vector_repo = VectorEmbeddingRepository(connection_manager)
manifest_repo = ManifestRepository(connection_manager)
case_repo = CaseRepository(connection_manager)

__all__ = [
    "connection_manager",
    "ConnectionManager",
    "MediaAssetRepository",
    "VectorEmbeddingRepository",
    "ManifestRepository",
    "CaseRepository",
    "asset_repo",
    "vector_repo",
    "manifest_repo",
    "case_repo",
]
