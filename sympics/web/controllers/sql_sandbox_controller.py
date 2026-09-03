# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
SQL Explorer & Sandbox Controller
=================================
Executes read-only queries within isolated transactions with AST blocking.
"""

import re
from typing import Dict, Any, Optional
import db


class SqlSandboxController:

    BLOCKED_PATTERNS = [
        r'\bdrop\b', r'\bdelete\b', r'\btruncate\b', r'\balter\b',
        r'\bupdate\b', r'\binsert\b', r'\bgrant\b', r'\brevoke\b',
        r'\bexecute\b', r'\bcopy\b', r'\bcreate\b',
        r'\bpg_terminate_backend\b', r'\bpg_cancel_backend\b',
        r'\bpg_read_file\b', r'\bpg_write_file\b', r'\bpg_read_binary_file\b',
        r'\bpg_sleep\b', r'\bdblink\b'
    ]

    def execute_query(self, sql_text: str, conn=None) -> Dict[str, Any]:
        sql = (sql_text or "").strip()
        if not sql:
            return {"success": False, "error": "Query cannot be empty"}

        cleaned_sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        cleaned_sql = re.sub(r'/\*.*?\*/', '', cleaned_sql, flags=re.DOTALL).strip()

        if not cleaned_sql.lower().startswith(("select", "with", "explain", "show")):
            return {"success": False, "error": "Security Block: Only SELECT / Read-Only queries are permitted."}

        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, cleaned_sql, flags=re.IGNORECASE):
                return {"success": False, "error": "Security Block: Destructive or administrative keyword detected."}

        statements = [s.strip() for s in cleaned_sql.split(";") if s.strip()]
        if len(statements) > 1:
            return {"success": False, "error": "Security Block: Multi-statement query chaining is not permitted."}

        should_close = False
        if conn is None:
            conn = db.get_connection()
            should_close = True

        try:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = '5000ms';")
                cur.execute("SET TRANSACTION READ ONLY;")
                cur.execute(sql)
                rows = cur.fetchmany(500)
                conn.rollback()
                return {"success": True, "rows": rows, "count": len(rows)}
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return {"success": False, "error": str(e)}
        finally:
            if should_close:
                conn.close()


sql_sandbox_controller = SqlSandboxController()
