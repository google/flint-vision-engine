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
Integration tests for PostgreSQL SKIP LOCKED dynamic batch queue.
"""
import sys
import os
import pytest

_db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database"))
if _db_dir not in sys.path:
    sys.path.insert(0, _db_dir)

import db


def test_database_connection():
    ok, details, err = db.test_connection()
    assert ok is True
    expected_db = os.environ.get("SYMPICS_PG_DB", os.environ.get("PGDATABASE", "sympics_db"))
    assert details["database"] in ("sympics_db", expected_db)


def test_manifest_status_counts():
    conn = db.get_connection()
    try:
        total = db.get_pending_manifest_count(conn=conn)
        assert isinstance(total, int)
    finally:
        conn.close()
