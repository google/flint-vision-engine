# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
Unit tests for database repository classes and connection management.
"""
from sympics.database.connection import connection_manager
from sympics.database.repositories.asset_repo import MediaAssetRepository
from sympics.database.repositories.manifest_repo import ManifestRepository
from sympics.database.repositories.case_repo import CaseRepository


def test_connection_manager_defaults():
    cfg = connection_manager.get_default_config()
    assert "database" in cfg
    assert cfg["database"] == "sympics_db"


def test_repository_instantiation():
    asset_repo = MediaAssetRepository(connection_manager)
    manifest_repo = ManifestRepository(connection_manager)
    case_repo = CaseRepository(connection_manager)

    assert asset_repo.conn_mgr == connection_manager
    assert manifest_repo.conn_mgr == connection_manager
    assert case_repo.conn_mgr == connection_manager
