#!/usr/bin/env python3
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
===============================================================================
SYMPICS POSTGRESQL DATABASE MANAGER — MODULE: CORE & MIGRATION
===============================================================================
Provides connection management, schema initialization, and transactional CRUD
operations for the SYMPICS PostgreSQL database, migration manifest, media assets,
case evidence linkages, and pgvector embeddings.
===============================================================================
"""

import os
import sys
import json
import getpass
import threading
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from psycopg2.pool import ThreadedConnectionPool

try:
    from pgvector.psycopg2 import register_vector
    PGVECTOR_PYTHON_AVAILABLE = True
except ImportError:
    PGVECTOR_PYTHON_AVAILABLE = False

CONFIG_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db_config.json")

_connection_pool = None
_pool_lock = threading.Lock()


class PooledConnectionWrapper:
    """Thread-safe proxy around a pooled PostgreSQL connection."""
    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn

    def close(self):
        if self._conn is not None and self._pool is not None:
            try:
                self._pool.putconn(self._conn)
            except Exception:
                try:
                    self._conn.close()
                except Exception:
                    pass
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __getattr__(self, name):
        if self._conn is None:
            raise psycopg2.InterfaceError("Connection is closed or returned to pool.")
        return getattr(self._conn, name)


def get_default_config():
    """Returns default database connection configuration, prioritizing environment variables."""
    current_user = getpass.getuser()
    return {
        "host": os.environ.get("SYMPICS_PG_HOST", os.environ.get("PGHOST", "")),
        "port": int(os.environ.get("SYMPICS_PG_PORT", os.environ.get("PGPORT", 5432))),
        "database": os.environ.get("SYMPICS_PG_DB", os.environ.get("PGDATABASE", "sympics_db")),
        "user": os.environ.get("SYMPICS_PG_USER", os.environ.get("PGUSER", current_user)),
        "password": os.environ.get("SYMPICS_PG_PASSWORD", os.environ.get("PGPASSWORD", "")),
    }


def load_db_config():
    """Loads database connection configuration from json file or environment defaults."""
    cfg = get_default_config()
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                saved_cfg = json.load(f)
                cfg.update(saved_cfg)
        except Exception:
            pass
    return cfg


def save_db_config(config_dict):
    """Saves database connection parameters to local configuration file."""
    with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(config_dict, f, indent=2)


def get_connection_pool(minconn=4, maxconn=20, config=None):
    """Retrieves or initializes the global ThreadedConnectionPool."""
    global _connection_pool
    if _connection_pool is not None and not _connection_pool.closed:
        return _connection_pool
    with _pool_lock:
        if _connection_pool is None or _connection_pool.closed:
            cfg = config or load_db_config()
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

            _connection_pool = ThreadedConnectionPool(minconn, maxconn, **connect_kwargs)
        return _connection_pool


def get_connection(config=None, autocommit=False, use_pool=True):
    """
    Creates or checks out a PostgreSQL connection with RealDictCursor.
    When use_pool is True (default) and no custom config is provided, returns
    a warm connection from the global ThreadedConnectionPool.
    """
    cfg = config or load_db_config()
    
    if use_pool and config is None:
        try:
            pool = get_connection_pool(config=cfg)
            conn = pool.getconn()
            conn.autocommit = autocommit
            if PGVECTOR_PYTHON_AVAILABLE:
                try:
                    register_vector(conn)
                except Exception:
                    pass
            return PooledConnectionWrapper(pool, conn)
        except Exception:
            pass  # Fallback to direct connection if pool fails

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
    
    if PGVECTOR_PYTHON_AVAILABLE:
        try:
            register_vector(conn)
        except Exception:
            pass
            
    return conn


def test_connection(config=None, maintenance_db="postgres"):
    """
    Attempts to establish a connection to PostgreSQL, trying provided parameters
    and fallback local socket authentication if needed.
    Returns (success_bool, working_config_dict, error_message).
    """
    cfg = config or load_db_config()
    
    # Try 1: User-specified parameters
    try:
        conn = psycopg2.connect(
            dbname=maintenance_db,
            host=cfg.get("host") or None,
            port=cfg.get("port", 5432),
            user=cfg.get("user") or None,
            password=cfg.get("password") or None,
            connect_timeout=3
        )
        conn.close()
        return True, cfg, None
    except Exception as err1:
        # Try 2: Peer socket connection with current OS user
        try:
            current_user = getpass.getuser()
            conn = psycopg2.connect(
                dbname=maintenance_db,
                user=current_user,
                connect_timeout=3
            )
            conn.close()
            fallback_cfg = cfg.copy()
            fallback_cfg["host"] = ""
            fallback_cfg["user"] = current_user
            fallback_cfg["password"] = ""
            return True, fallback_cfg, None
        except Exception:
            pass

        # Try 3: Local socket as 'postgres' user
        try:
            conn = psycopg2.connect(
                dbname=maintenance_db,
                user="postgres",
                connect_timeout=3
            )
            conn.close()
            fallback_cfg = cfg.copy()
            fallback_cfg["host"] = ""
            fallback_cfg["user"] = "postgres"
            fallback_cfg["password"] = ""
            return True, fallback_cfg, None
        except Exception:
            pass

        return False, cfg, str(err1)


def init_db(config=None):
    """
    Initializes the PostgreSQL database with the complete schema:
    1. schema_migration_manifest.sql
    2. schema_core_tables.sql
    """
    cfg = config or load_db_config()
    target_db = cfg.get("database", "sympics_db")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    schema_manifest_file = os.path.join(base_dir, "schema_migration_manifest.sql")
    schema_core_file = os.path.join(base_dir, "schema_core_tables.sql")

    # Step 1: Ensure target database exists
    maintenance_kwargs = {
        "dbname": "postgres",
        "host": cfg.get("host") or None,
        "port": cfg.get("port", 5432),
        "user": cfg.get("user") or None,
        "password": cfg.get("password") or None,
    }
    maintenance_kwargs = {k: v for k, v in maintenance_kwargs.items() if v is not None}

    try:
        m_conn = psycopg2.connect(**maintenance_kwargs)
        m_conn.autocommit = True
        with m_conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
            if not cur.fetchone():
                cur.execute(f'CREATE DATABASE "{target_db}"')
                print(f"[+] Created PostgreSQL database: '{target_db}'")
            else:
                print(f"[*] Database '{target_db}' is active.")
        m_conn.close()
    except Exception as e:
        print(f"[!] Database check notice: {e}")

    # Step 2: Connect to target database and execute DDLs
    conn = get_connection(cfg)
    try:
        with conn.cursor() as cur:
            # Enable vector extension first
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            # 1. Apply Manifest Schema
            if os.path.exists(schema_manifest_file):
                with open(schema_manifest_file, "r", encoding="utf-8") as f:
                    cur.execute(f.read())
                    
            # 2. Apply Core Production Schema
            if os.path.exists(schema_core_file):
                with open(schema_core_file, "r", encoding="utf-8") as f:
                    cur.execute(f.read())

        conn.commit()
        print(f"[+] Successfully applied complete schema to '{target_db}'.")
    finally:
        conn.close()


# =============================================================================
# CORE PRODUCTION ENTITY CRUD OPERATIONS
# =============================================================================

def add_media_asset(asset_dict, conn=None):
    """
    Inserts a canonical physical media asset into `media_assets`.
    Returns the UUID `asset_id`.
    """
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    sql = """
        INSERT INTO media_assets (
            sha256, md5, sha1, file_size_bytes, media_type, mime_type,
            width_pixels, height_pixels, storage_rel_path, storage_abs_path,
            thumb_rel_path, exif_data
        ) VALUES (
            %(sha256)s, %(md5)s, %(sha1)s, %(file_size_bytes)s, %(media_type)s, %(mime_type)s,
            %(width_pixels)s, %(height_pixels)s, %(storage_rel_path)s, %(storage_abs_path)s,
            %(thumb_rel_path)s, %(exif_data)s
        )
        ON CONFLICT (sha256) DO UPDATE SET
            storage_rel_path = EXCLUDED.storage_rel_path,
            storage_abs_path = EXCLUDED.storage_abs_path,
            thumb_rel_path = EXCLUDED.thumb_rel_path
        RETURNING asset_id;
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, asset_dict)
            res = cur.fetchone()
            conn.commit()
            return res["asset_id"] if res else None
    finally:
        if should_close:
            conn.close()


def add_media_embedding(asset_id, vector_l2, model_name="siglip", model_version="base-patch16-224", conn=None):
    """
    Inserts or updates an AI vector embedding into `media_embeddings`.
    """
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    sql = """
        INSERT INTO media_embeddings (
            asset_id, model_name, model_version, dimension_size, embedding_l2
        ) VALUES (
            %s, %s, %s, %s, %s
        )
        ON CONFLICT (asset_id, model_name) DO UPDATE SET
            embedding_l2 = EXCLUDED.embedding_l2;
    """
    try:
        # Convert numpy array / list to vector format
        vec_param = list(vector_l2) if hasattr(vector_l2, "tolist") else vector_l2
        dim_size = len(vec_param)
        
        with conn.cursor() as cur:
            cur.execute(sql, (asset_id, model_name, model_version, dim_size, vec_param))
        conn.commit()
    finally:
        if should_close:
            conn.close()


def add_case_evidence_item(case_id, asset_id, original_filepath, original_filename,
                           source_parent_dir=None, series_tag=None, conn=None):
    """
    Associates an asset with a case, preserving original filename and folder origin.
    """
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    sql = """
        INSERT INTO case_evidence_items (
            case_id, asset_id, original_filepath, original_filename, source_parent_dir, series_tag
        ) VALUES (
            %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (case_id, asset_id) DO UPDATE SET
            original_filepath = EXCLUDED.original_filepath,
            original_filename = EXCLUDED.original_filename,
            source_parent_dir = EXCLUDED.source_parent_dir;
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (case_id, asset_id, original_filepath, original_filename, source_parent_dir, series_tag))
        conn.commit()
    finally:
        if should_close:
            conn.close()


# =============================================================================
# MIGRATION MANIFEST CRUD OPERATIONS
# =============================================================================

def add_manifest_record(record_dict, conn=None):
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    sql = """
        INSERT INTO migration_manifest (
            source_filepath, source_filename, source_parent_dir, file_size_bytes, file_extension,
            source_created_at, source_modified_at, sha256, md5, sha1, status, is_video
        ) VALUES (
            %(source_filepath)s, %(source_filename)s, %(source_parent_dir)s, %(file_size_bytes)s, %(file_extension)s,
            %(source_created_at)s, %(source_modified_at)s, %(sha256)s, %(md5)s, %(sha1)s, %(status)s, %(is_video)s
        )
        ON CONFLICT (source_filepath) DO UPDATE SET
            file_size_bytes = EXCLUDED.file_size_bytes,
            sha256 = EXCLUDED.sha256,
            md5 = EXCLUDED.md5,
            sha1 = EXCLUDED.sha1
        RETURNING manifest_id;
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, record_dict)
            res = cur.fetchone()
            conn.commit()
            return res["manifest_id"] if res else None
    finally:
        if should_close:
            conn.close()


def batch_add_manifest_records(records_list, conn=None):
    if not records_list:
        return 0

    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    cols = [
        "source_filepath", "source_filename", "source_parent_dir", "file_size_bytes", "file_extension",
        "source_created_at", "source_modified_at", "sha256", "md5", "sha1", "status", "is_video"
    ]
    sql = f"""
        INSERT INTO migration_manifest ({", ".join(cols)})
        VALUES %s
        ON CONFLICT (source_filepath) DO UPDATE SET
            file_size_bytes = EXCLUDED.file_size_bytes,
            sha256 = EXCLUDED.sha256,
            md5 = EXCLUDED.md5,
            sha1 = EXCLUDED.sha1,
            status = CASE 
                WHEN migration_manifest.sha256 = EXCLUDED.sha256 AND migration_manifest.status IN ('VERIFIED_COPIED', 'SKIPPED_DUPLICATE') THEN migration_manifest.status
                WHEN migration_manifest.sha256 = EXCLUDED.sha256 AND migration_manifest.status = 'FAILED_CORRUPT' THEN 'FAILED_CORRUPT'
                ELSE 'PENDING'
            END,
            source_modified_at = EXCLUDED.source_modified_at
    """
    tuples = [
        tuple(r.get(c) for c in cols) for r in records_list
    ]

    try:
        with conn.cursor() as cur:
            execute_values(cur, sql, tuples, page_size=1000)
        conn.commit()
        return len(tuples)
    finally:
        if should_close:
            conn.close()


def get_pending_manifest_items(limit=100, conn=None):
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    sql = """
        SELECT * FROM migration_manifest
        WHERE status = 'PENDING'
        ORDER BY manifest_id ASC
        LIMIT %s
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (limit,))
            return cur.fetchall()
    finally:
        if should_close:
            conn.close()


def checkout_pending_manifest_batch(batch_size=32, worker_id=None, conn=None):
    """
    Atomically claims and locks a batch of PENDING records for a worker using SKIP LOCKED.
    Guarantees that multiple concurrent workers never process the same records.
    """
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    w_id = worker_id or f"worker_{os.getpid()}"
    sql = """
        UPDATE migration_manifest
        SET status = 'SCANNING', worker_id = %s
        WHERE manifest_id IN (
            SELECT manifest_id
            FROM migration_manifest
            WHERE status = 'PENDING'
            ORDER BY manifest_id ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        )
        RETURNING *;
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (w_id, batch_size))
            rows = cur.fetchall()
        conn.commit()
        return rows
    finally:
        if should_close:
            conn.close()


def reset_stale_scanning_records(worker_id=None, conn=None):
    """
    Resets records stuck in 'SCANNING' back to 'PENDING' so they can be re-claimed.
    """
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True
    try:
        with conn.cursor() as cur:
            if worker_id:
                cur.execute("UPDATE migration_manifest SET status = 'PENDING' WHERE status = 'SCANNING' AND worker_id = %s;", (worker_id,))
            else:
                cur.execute("UPDATE migration_manifest SET status = 'PENDING' WHERE status = 'SCANNING';")
        conn.commit()
    finally:
        if should_close:
            conn.close()


def get_pending_manifest_count(conn=None):
    """Returns the total number of items remaining in PENDING or SCANNING status."""
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM migration_manifest WHERE status IN ('PENDING', 'SCANNING');")
            r = cur.fetchone()
            return r["cnt"] if r else 0
    finally:
        if should_close:
            conn.close()


def update_manifest_verification(manifest_id, destination_abs_path, destination_rel_path,
                                 dest_size_bytes, dest_sha256, embedding_status='EMBEDDED',
                                 verified=True, processing_time_ms=None, error_msg=None, conn=None):
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    status = 'VERIFIED_COPIED' if verified else 'FAILED_CORRUPT'
    sql = """
        UPDATE migration_manifest SET
            status = %s,
            destination_abs_path = %s,
            destination_rel_path = %s,
            destination_size_bytes = %s,
            destination_sha256 = %s,
            embedding_status = %s,
            processing_time_ms = %s,
            error_message = %s,
            migrated_at = CURRENT_TIMESTAMP,
            verified_at = CURRENT_TIMESTAMP
        WHERE manifest_id = %s
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (
                status, destination_abs_path, destination_rel_path,
                dest_size_bytes, dest_sha256, embedding_status,
                processing_time_ms, error_msg, manifest_id
            ))
        conn.commit()
    finally:
        if should_close:
            conn.close()


def get_migration_summary(conn=None):
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_migration_summary")
            row = cur.fetchone()
            return dict(row) if row else {}
    finally:
        if should_close:
            conn.close()
