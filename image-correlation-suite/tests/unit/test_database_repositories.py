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
Unit tests for database repository classes and connection management.
"""
import os
from sympics.database.connection import connection_manager
from sympics.database.repositories.asset_repo import MediaAssetRepository
from sympics.database.repositories.manifest_repo import ManifestRepository
from sympics.database.repositories.case_repo import CaseRepository


def test_connection_manager_defaults():
    cfg = connection_manager.get_default_config()
    assert "database" in cfg
    expected_db = os.environ.get("SYMPICS_PG_DB", os.environ.get("PGDATABASE", "sympics_db"))
    assert cfg["database"] in ("sympics_db", expected_db)


def test_repository_instantiation():
    asset_repo = MediaAssetRepository(connection_manager)
    manifest_repo = ManifestRepository(connection_manager)
    case_repo = CaseRepository(connection_manager)

    assert asset_repo.conn_mgr == connection_manager
    assert manifest_repo.conn_mgr == connection_manager
    assert case_repo.conn_mgr == connection_manager
