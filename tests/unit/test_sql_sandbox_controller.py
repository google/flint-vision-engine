# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
Unit tests for SqlSandboxController security rules and validation.
"""
from sympics.web.controllers.sql_sandbox_controller import sql_sandbox_controller


def test_sql_sandbox_blocks_drop():
    res = sql_sandbox_controller.execute_query("DROP TABLE media_assets;")
    assert res["success"] is False
    assert "Security Block" in res["error"]


def test_sql_sandbox_blocks_delete():
    res = sql_sandbox_controller.execute_query("DELETE FROM media_assets WHERE 1=1;")
    assert res["success"] is False
    assert "Security Block" in res["error"]


def test_sql_sandbox_blocks_truncate():
    res = sql_sandbox_controller.execute_query("TRUNCATE TABLE media_assets;")
    assert res["success"] is False
    assert "Security Block" in res["error"]


def test_sql_sandbox_blocks_chaining():
    res = sql_sandbox_controller.execute_query("SELECT 1; DROP TABLE media_assets;")
    assert res["success"] is False
    assert "Security Block" in res["error"]


def test_sql_sandbox_blocks_admin_functions():
    res = sql_sandbox_controller.execute_query("SELECT pg_read_file('/etc/passwd');")
    assert res["success"] is False
    assert "Security Block" in res["error"]
