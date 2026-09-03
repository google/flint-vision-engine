# Copyright 2026 Google LLC
# Licensed under Apache 2.0

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
