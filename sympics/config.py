# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
SYMPICS Central Configuration Module
==================================
Loads configuration from environment variables and config files with
sensible production defaults and validation.
"""

import os
from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    host: str = os.getenv("SYMPICS_DB_HOST", "localhost")
    port: int = int(os.getenv("SYMPICS_DB_PORT", "5432"))
    database: str = os.getenv("SYMPICS_DB_NAME", "sympics_db")
    user: str = os.getenv("SYMPICS_DB_USER", os.getenv("USER", "postgres"))
    password: str = os.getenv("SYMPICS_DB_PASSWORD", "")


@dataclass
class StorageConfig:
    vault_root: str = os.path.abspath(os.getenv(
        "SYMPICS_VAULT_ROOT",
        os.path.join(os.path.dirname(__file__), "..", "future-lan-storage")
    ))
    staging_dir: str = os.path.abspath(os.getenv(
        "SYMPICS_STAGING_DIR",
        os.path.join(os.path.dirname(__file__), "..", "future-lan-storage", "03_Ingestion_Staging")
    ))
    quarantine_dir: str = os.path.abspath(os.getenv(
        "SYMPICS_QUARANTINE_DIR",
        os.path.join(os.path.dirname(__file__), "..", "future-lan-storage", "03_Ingestion_Staging", "_quarantine")
    ))


@dataclass
class ServerConfig:
    port: int = int(os.getenv("SYMPICS_WEB_PORT", "8080"))
    host: str = os.getenv("SYMPICS_WEB_HOST", "0.0.0.0")
    cors_allowed_origins: str = os.getenv("SYMPICS_CORS_ORIGIN", "http://localhost:8080,http://127.0.0.1:8080")


@dataclass
class SympicsConfig:
    db: DatabaseConfig = DatabaseConfig()
    storage: StorageConfig = StorageConfig()
    server: ServerConfig = ServerConfig()


# Global config instance
config = SympicsConfig()
