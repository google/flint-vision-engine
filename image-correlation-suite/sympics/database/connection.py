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
SYMPICS Database Connection Manager
=================================
Manages PostgreSQL connections, authentication fallback, and pgvector type registration.
"""

import os
import json
import getpass
from typing import Optional, Dict, Any, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from pgvector.psycopg2 import register_vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False

CONFIG_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database", "db_config.json"))


class ConnectionManager:
    """Manages PostgreSQL connection lifecycle and configuration."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or CONFIG_FILE_PATH

    def get_default_config(self) -> Dict[str, Any]:
        current_user = getpass.getuser()
        return {
            "host": os.environ.get("SYMPICS_PG_HOST", os.environ.get("PGHOST", "")),
            "port": int(os.environ.get("SYMPICS_PG_PORT", os.environ.get("PGPORT", 5432))),
            "database": os.environ.get("SYMPICS_PG_DB", os.environ.get("PGDATABASE", "sympics_db")),
            "user": os.environ.get("SYMPICS_PG_USER", os.environ.get("PGUSER", current_user)),
            "password": os.environ.get("SYMPICS_PG_PASSWORD", os.environ.get("PGPASSWORD", "")),
        }

    def load_config(self) -> Dict[str, Any]:
        cfg = self.get_default_config()
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg.update(json.load(f))
            except Exception:
                pass
        return cfg

    def save_config(self, config_dict: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2)

    def get_connection(self, config: Optional[Dict[str, Any]] = None, autocommit: bool = False):
        cfg = config or self.load_config()
        connect_kwargs = {
            "dbname": cfg.get("database", "sympics_db"),
            "cursor_factory": RealDictCursor
        }
        if cfg.get("host"):
            connect_kwargs["host"] = cfg["host"]
        if cfg.get("port"):
            connect_kwargs["port"] = cfg["port"]
        if cfg.get("user"):
            connect_kwargs["user"] = cfg["user"]
        if cfg.get("password"):
            connect_kwargs["password"] = cfg["password"]

        conn = psycopg2.connect(**connect_kwargs)
        conn.autocommit = autocommit

        if PGVECTOR_AVAILABLE:
            try:
                register_vector(conn)
            except Exception:
                pass
        return conn

    def test_connection(self, config: Optional[Dict[str, Any]] = None) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        cfg = config or self.load_config()
        try:
            conn = self.get_connection(config=cfg)
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
            conn.close()
            return True, cfg, None
        except Exception as e:
            # Fallback to local peer socket if TCP failed
            if cfg.get("host"):
                fallback_cfg = dict(cfg)
                fallback_cfg["host"] = ""
                try:
                    conn = self.get_connection(config=fallback_cfg)
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1;")
                    conn.close()
                    self.save_config(fallback_cfg)
                    return True, fallback_cfg, None
                except Exception:
                    pass
            return False, cfg, str(e)


# Default global instance
connection_manager = ConnectionManager()
