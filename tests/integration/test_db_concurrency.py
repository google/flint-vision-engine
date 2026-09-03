# Copyright 2026 Google LLC
# Licensed under Apache 2.0

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
    assert details["database"] == "sympics_db"


def test_manifest_status_counts():
    conn = db.get_connection()
    try:
        total = db.get_pending_manifest_count(conn=conn)
        assert isinstance(total, int)
    finally:
        conn.close()
