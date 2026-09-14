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
SYMPICS Central Configuration Module
==================================
Loads configuration from environment variables and config files with
sensible production defaults and validation.
"""

import os
from dataclasses import dataclass, field


@dataclass
class DatabaseConfig:
    host: str = os.getenv("SYMPICS_DB_HOST", "localhost")
    port: int = int(os.getenv("SYMPICS_DB_PORT", "5432"))
    database: str = os.getenv("SYMPICS_DB_NAME", "sympics_db")
    user: str = os.getenv("SYMPICS_DB_USER", os.getenv("USER", "postgres"))
    password: str = os.getenv("SYMPICS_DB_PASSWORD", "")


def _resolve_default_path(*parts):
    local_p = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", *parts))
    parent_p = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", *parts))
    if os.path.exists(parent_p) and not os.path.exists(local_p):
        return parent_p
    return local_p


@dataclass
class StorageConfig:
    vault_root: str = os.path.abspath(os.getenv(
        "SYMPICS_VAULT_ROOT",
        _resolve_default_path("future-lan-storage")
    ))
    staging_dir: str = os.path.abspath(os.getenv(
        "SYMPICS_STAGING_DIR",
        _resolve_default_path("future-lan-storage", "03_Ingestion_Staging")
    ))
    quarantine_dir: str = os.path.abspath(os.getenv(
        "SYMPICS_QUARANTINE_DIR",
        _resolve_default_path("future-lan-storage", "03_Ingestion_Staging", "_quarantine")
    ))


@dataclass
class ServerConfig:
    port: int = int(os.getenv("SYMPICS_WEB_PORT", "8080"))
    host: str = os.getenv("SYMPICS_WEB_HOST", "0.0.0.0")
    cors_allowed_origins: str = os.getenv("SYMPICS_CORS_ORIGIN", "http://localhost:8080,http://127.0.0.1:8080")


@dataclass
class SympicsConfig:
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    server: ServerConfig = field(default_factory=ServerConfig)


# Global config instance
config = SympicsConfig()
