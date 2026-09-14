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
SYMPICS UNIFIED WEB API SERVICE (STAGE 1: BACKEND QUERY & DISPATCH ENGINE)
===============================================================================
Provides PostgreSQL 16 + pgvector query handlers, multimodal search,
"Top 15 (All)" cross-model comparative search, raw vector query dispatch,
Reference intelligence collision cross-referencing, and Database Explorer APIs.
===============================================================================
"""

import os
import sys
import re
import json
import base64
import io
import time
import shutil
from datetime import datetime
from PIL import Image, ImageOps

def _resolve_vault_path(folder_name="future-lan-storage"):
    if os.getenv("SYMPICS_VAULT_ROOT"):
        return os.path.abspath(os.getenv("SYMPICS_VAULT_ROOT"))
    local_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", folder_name))
    parent_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", folder_name))
    if os.path.exists(parent_path) and not os.path.exists(local_path):
        return parent_path
    return local_path

VAULT_ROOT = _resolve_vault_path("future-lan-storage")

# Add database module to path
_db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "database"))
if _db_dir not in sys.path:
    sys.path.insert(0, _db_dir)

try:
    import db
    import forensic_identity
    from embedder_service import get_embedder
except ImportError as e:
    print(f"[ERROR] Could not import database/embedder modules from {_db_dir}: {e}")
    sys.exit(1)


# =============================================================================
# 1. EVIDENCE MANAGEMENT & GALLERY APIS
# =============================================================================

def get_evidence_list(params, conn=None):
    """
    Returns paginated evidence items with full metadata, case linkage,
    and real-time reference intelligence match status.
    """
    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    limit = min(int(params.get("limit", 100)), 1000)
    offset = max(int(params.get("offset", 0)), 0)
    case_filter = params.get("case_number", "").strip()
    status_filter = params.get("custody_status", "").strip()
    series_filter = (params.get("series") or params.get("series_tag") or params.get("series_name") or "").strip()
    tag_status = params.get("tag_status", "").strip()
    media_type = params.get("media_type", "").strip()
    timeframe = params.get("timeframe", "").strip()
    sort_by = params.get("sort_by", "newest").strip()
    search = params.get("search", "").strip()
    intel_only = str(params.get("intel_only") or params.get("reference_only") or params.get("watchlist_only", "false")).lower() in ("true", "1", "yes")

    where_clauses = []
    sql_params = []

    if case_filter and case_filter != "ALL":
        where_clauses.append("c.case_number = %s")
        sql_params.append(case_filter)

    if status_filter and status_filter != "ALL":
        where_clauses.append("cei.custody_status = %s")
        sql_params.append(status_filter)

    if series_filter and series_filter != "ALL":
        where_clauses.append("cei.series_tag = %s")
        sql_params.append(series_filter)

    if tag_status == "UNLABELED":
        where_clauses.append("((cei.series_tag IS NULL OR cei.series_tag = '') AND (cei.tags IS NULL OR array_length(cei.tags, 1) IS NULL OR array_length(cei.tags, 1) = 0))")
    elif tag_status == "NO_SERIES":
        where_clauses.append("(cei.series_tag IS NULL OR cei.series_tag = '')")
    elif tag_status == "NO_TAGS":
        where_clauses.append("(cei.tags IS NULL OR array_length(cei.tags, 1) IS NULL OR array_length(cei.tags, 1) = 0)")
    elif tag_status == "HAS_SERIES":
        where_clauses.append("(cei.series_tag IS NOT NULL AND cei.series_tag != '')")
    elif tag_status == "HAS_TAGS":
        where_clauses.append("(cei.tags IS NOT NULL AND array_length(cei.tags, 1) > 0)")

    folder = params.get("folder") or params.get("source_folder")
    if folder and folder != "ALL":
        where_clauses.append("""(
            ma.source_folder = %s OR 
            ma.source_folder ILIKE %s OR 
            ma.source_rel_path ILIKE %s
        )""")
        clean_folder = folder.replace(" (Rally)", "").strip()
        sql_params.extend([clean_folder, f"%{clean_folder}%", f"%{clean_folder}%"])

    if media_type and media_type != "ALL":
        where_clauses.append("ma.media_type = %s")
        sql_params.append(media_type.upper())

    if timeframe == "1h":
        where_clauses.append("cei.created_at >= NOW() - INTERVAL '1 hour'")
    elif timeframe == "24h":
        where_clauses.append("cei.created_at >= NOW() - INTERVAL '24 hours'")
    elif timeframe == "7d":
        where_clauses.append("cei.created_at >= NOW() - INTERVAL '7 days'")
    elif timeframe == "30d":
        where_clauses.append("cei.created_at >= NOW() - INTERVAL '30 days'")

    if intel_only:
        where_clauses.append("(ref.identifier IS NOT NULL)")

    if search:
        where_clauses.append("""(
            cei.original_filename ILIKE %s OR 
            ma.sha256 ILIKE %s OR 
            ma.md5 ILIKE %s OR 
            ma.source_folder ILIKE %s OR
            ma.source_rel_path ILIKE %s OR
            cei.source_parent_dir ILIKE %s OR
            ma.storage_rel_path ILIKE %s OR
            cei.series_tag ILIKE %s OR 
            %s = ANY(cei.tags)
        )""")
        term = f"%{search}%"
        sql_params.extend([term, term, term, term, term, term, term, term, search])

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Sort By Clause
    order_clause = "ORDER BY cei.created_at DESC"
    sub_order_clause = "ORDER BY evidence_created_at DESC NULLS LAST"
    if sort_by == "oldest":
        order_clause = "ORDER BY cei.created_at ASC"
        sub_order_clause = "ORDER BY evidence_created_at ASC NULLS LAST"
    elif sort_by == "filename_asc":
        order_clause = "ORDER BY cei.original_filename ASC"
        sub_order_clause = "ORDER BY original_filename ASC"
    elif sort_by == "filename_desc":
        order_clause = "ORDER BY cei.original_filename DESC"
        sub_order_clause = "ORDER BY original_filename DESC"
    elif sort_by == "size_desc":
        order_clause = "ORDER BY ma.file_size_bytes DESC"
        sub_order_clause = "ORDER BY file_size_bytes DESC"
    elif sort_by == "size_asc":
        order_clause = "ORDER BY ma.file_size_bytes ASC"
        sub_order_clause = "ORDER BY file_size_bytes ASC"
    elif sort_by == "last_action_desc":
        order_clause = "ORDER BY cei.last_action_at DESC NULLS LAST"
        sub_order_clause = "ORDER BY last_action_at DESC NULLS LAST"

    is_global_all = not case_filter or case_filter == "ALL"

    try:
        with conn.cursor() as cur:
            # Count Total
            if is_global_all:
                count_query = f"""
                    SELECT COUNT(DISTINCT ma.asset_id) as total
                    FROM media_assets ma
                    LEFT JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id
                    LEFT JOIN cases c ON cei.case_id = c.case_id
                    LEFT JOIN reference_catalog_records ref ON ma.md5 = ref.md5
                    {where_sql};
                """
            else:
                count_query = f"""
                    SELECT COUNT(DISTINCT cei.evidence_id) as total
                    FROM case_evidence_items cei
                    JOIN media_assets ma ON cei.asset_id = ma.asset_id
                    JOIN cases c ON cei.case_id = c.case_id
                    LEFT JOIN reference_catalog_records ref ON ma.md5 = ref.md5
                    {where_sql};
                """
            cur.execute(count_query, sql_params)
            total = cur.fetchone()["total"]

            # Fetch Rows
            data_params = list(sql_params)
            data_params.extend([limit, offset])

            if is_global_all:
                data_query = f"""
                    SELECT * FROM (
                        SELECT DISTINCT ON (ma.asset_id)
                            COALESCE(cei.evidence_id, ma.asset_id) AS evidence_id,
                            ma.asset_id,
                            COALESCE(
                                NULLIF((SELECT cei3.original_filename FROM case_evidence_items cei3 WHERE cei3.asset_id = ma.asset_id AND NOT starts_with(cei3.original_filename, '01_Media_Vault/') LIMIT 1), ''),
                                cei.original_filename,
                                split_part(ma.storage_rel_path, '/', -1)
                            ) AS original_filename,
                            cei.source_parent_dir,
                            cei.series_tag,
                            cei.tags,
                            COALESCE(cei.custody_status, 'INGESTED') AS custody_status,
                            cei.last_action,
                            cei.last_action_at,
                            COALESCE(cei.created_at, ma.created_at) as evidence_created_at,
                            CASE WHEN c.status = 'ACTIVE' THEN c.case_number ELSE NULL END AS case_number,
                            CASE WHEN c.status = 'ACTIVE' THEN c.case_name ELSE NULL END AS case_name,
                            ma.sha256,
                            ma.md5,
                            ma.sha1,
                            ma.file_size_bytes,
                            ma.media_type,
                            ma.width_pixels,
                            ma.height_pixels,
                            ma.storage_rel_path,
                            ma.thumb_rel_path,
                            ma.source_folder,
                            ma.source_rel_path,
                            ma.gps_latitude,
                            ma.gps_longitude,
                            ma.gps_altitude,
                            ref.identifier as ref_identifier,
                            ref.series_name as ref_series_name,
                            ref.flag_identified as ref_flag_identified,
                            ref.flag_actionable as ref_flag_actionable,
                            ref.is_distributed as ref_is_distributed,
                            (SELECT ARRAY_AGG(DISTINCT c2.case_number) FROM case_evidence_items cei2 JOIN cases c2 ON cei2.case_id = c2.case_id WHERE cei2.asset_id = ma.asset_id AND c2.status = 'ACTIVE') AS linked_cases
                        FROM media_assets ma
                        LEFT JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id
                        LEFT JOIN cases c ON cei.case_id = c.case_id
                        LEFT JOIN reference_catalog_records ref ON ma.md5 = ref.md5
                        {where_sql}
                    ) sub
                    {sub_order_clause}
                    LIMIT %s OFFSET %s;
                """
            else:
                data_query = f"""
                    SELECT 
                        cei.evidence_id,
                        cei.asset_id,
                        cei.original_filename,
                        cei.source_parent_dir,
                        cei.series_tag,
                        cei.tags,
                        cei.custody_status,
                        cei.last_action,
                        cei.last_action_at,
                        cei.created_at as evidence_created_at,
                        CASE WHEN c.status = 'ACTIVE' THEN c.case_number ELSE NULL END AS case_number,
                        CASE WHEN c.status = 'ACTIVE' THEN c.case_name ELSE NULL END AS case_name,
                        ma.sha256,
                        ma.md5,
                        ma.sha1,
                        ma.file_size_bytes,
                        ma.media_type,
                        ma.width_pixels,
                        ma.height_pixels,
                        ma.storage_rel_path,
                        ma.thumb_rel_path,
                        ma.source_folder,
                        ma.source_rel_path,
                        ma.gps_latitude,
                        ma.gps_longitude,
                        ma.gps_altitude,
                        ref.identifier as ref_identifier,
                        ref.series_name as ref_series_name,
                        ref.flag_identified as ref_flag_identified,
                        ref.flag_actionable as ref_flag_actionable,
                        ref.is_distributed as ref_is_distributed,
                        (SELECT ARRAY_AGG(DISTINCT c2.case_number) FROM case_evidence_items cei2 JOIN cases c2 ON cei2.case_id = c2.case_id WHERE cei2.asset_id = ma.asset_id AND c2.status = 'ACTIVE') AS linked_cases
                    FROM case_evidence_items cei
                    JOIN media_assets ma ON cei.asset_id = ma.asset_id
                    JOIN cases c ON cei.case_id = c.case_id
                    LEFT JOIN reference_catalog_records ref ON ma.md5 = ref.md5
                    {where_sql}
                    {order_clause}
                    LIMIT %s OFFSET %s;
                """
            cur.execute(data_query, data_params)
            rows = cur.fetchall()

            return {"success": True, "total": total, "rows": rows, "limit": limit, "offset": offset}
    finally:
        if should_close:
            conn.close()


def get_cases_list(conn=None):
    """Returns all active case containers with asset count breakdowns."""
    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    c.case_id,
                    c.case_number,
                    c.case_name,
                    c.classification_type,
                    c.priority_level,
                    c.status,
                    c.created_at,
                    COUNT(cei.evidence_id) as evidence_count
                FROM cases c
                LEFT JOIN case_evidence_items cei ON c.case_id = cei.case_id
                WHERE c.status = 'ACTIVE'
                GROUP BY c.case_id, c.case_number, c.case_name, c.classification_type, c.priority_level, c.status, c.created_at
                ORDER BY c.created_at DESC;
            """)
            cases = cur.fetchall()

            cur.execute("SELECT COUNT(*) AS total FROM media_assets;")
            total_assets = cur.fetchone()["total"]

            return {"success": True, "cases": cases, "total_media_assets": total_assets}
    finally:
        if should_close:
            conn.close()


def create_case(body, conn=None):
    """Creates a new Case / Investigation container in the database."""
    case_number = (body.get("case_number") or "").strip()
    case_name = (body.get("case_name") or "").strip()
    classification_type = body.get("classification_type", "MEDIA_EVIDENCE").upper()
    priority_level = body.get("priority_level", "NORMAL").upper()
    case_notes = body.get("case_notes", "")
    contributing_agency = body.get("contributing_agency", "Agency Office")

    if not case_number:
        return {"success": False, "error": "Case / Investigation number is required"}
    if not case_name:
        case_name = f"Investigation: {case_number}"

    if classification_type not in ('MEDIA_EVIDENCE', 'SERIES_MATCH', 'TERRORISM', 'NARCOTICS', 'GENERAL_CRIMINAL'):
        classification_type = 'MEDIA_EVIDENCE'
    if priority_level not in ('LOW', 'NORMAL', 'HIGH', 'CRITICAL_IMMINENT_HARM'):
        priority_level = 'NORMAL'

    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO cases (
                    case_number, case_name, classification_type, priority_level, 
                    status, contributing_agency, case_notes
                ) VALUES (
                    %s, %s, %s, %s, 'ACTIVE', %s, %s
                )
                ON CONFLICT (case_number) DO UPDATE SET 
                    case_name = EXCLUDED.case_name,
                    classification_type = EXCLUDED.classification_type,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING case_id, case_number, case_name;
            """, (case_number, case_name, classification_type, priority_level, contributing_agency, case_notes))
            row = cur.fetchone()
            conn.commit()
            return {"success": True, "case": row}
    finally:
        if should_close:
            conn.close()


def link_evidence_to_case(body, conn=None):
    """
    Links physical assets or copies evidence items from a source folder/case into a target case container.
    """
    target_case_number = body.get("target_case_number") or body.get("case_number")
    source_case_number = body.get("source_case_number")
    source_folder = body.get("source_folder")
    asset_ids = body.get("asset_ids")
    if not asset_ids and body.get("asset_id"):
        asset_ids = [body.get("asset_id")]

    if not target_case_number:
        return {"success": False, "error": "Target case_number is required"}

    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            # Get target case_id
            cur.execute("SELECT case_id FROM cases WHERE case_number = %s;", (target_case_number,))
            t_row = cur.fetchone()
            if not t_row:
                return {"success": False, "error": f"Target case '{target_case_number}' not found"}
            target_case_id = t_row["case_id"]

            if asset_ids and len(asset_ids) > 0:
                # Link specific assets
                cur.execute("""
                    INSERT INTO case_evidence_items (
                        case_id, asset_id, original_filepath, original_filename,
                        source_parent_dir, custody_status, last_action
                    )
                    SELECT 
                        %s, ma.asset_id, ma.storage_rel_path, 
                        COALESCE(ma.source_rel_path, split_part(ma.storage_rel_path, '/', -1), 'imported_evidence.jpg'),
                        COALESCE(ma.source_folder, 'Master_Vault'),
                        'INGESTED', 'ingested'
                    FROM media_assets ma
                    WHERE ma.asset_id = ANY(%s::uuid[])
                      AND NOT EXISTS (
                          SELECT 1 FROM case_evidence_items existing 
                          WHERE existing.case_id = %s AND existing.asset_id = ma.asset_id
                      );
                """, (target_case_id, asset_ids, target_case_id))
                linked_count = cur.rowcount
            elif source_folder:
                # Link all assets from a specific origin folder
                cur.execute("""
                    INSERT INTO case_evidence_items (
                        case_id, asset_id, original_filepath, original_filename,
                        source_parent_dir, custody_status, last_action
                    )
                    SELECT 
                        %s, ma.asset_id, ma.storage_rel_path, 
                        COALESCE(ma.source_rel_path, split_part(ma.storage_rel_path, '/', -1), 'imported_evidence.jpg'),
                        ma.source_folder,
                        'INGESTED', 'ingested'
                    FROM media_assets ma
                    WHERE ma.source_folder = %s
                      AND NOT EXISTS (
                          SELECT 1 FROM case_evidence_items existing 
                          WHERE existing.case_id = %s AND existing.asset_id = ma.asset_id
                      );
                """, (target_case_id, source_folder, target_case_id))
                linked_count = cur.rowcount
            elif source_case_number and source_case_number != 'ALL':
                # Copy/link all items from another existing case
                cur.execute("""
                    INSERT INTO case_evidence_items (
                        case_id, asset_id, original_filepath, original_filename,
                        source_parent_dir, series_tag, tags, custody_status, last_action
                    )
                    SELECT 
                        %s, cei.asset_id, cei.original_filepath, cei.original_filename,
                        cei.source_parent_dir, cei.series_tag, cei.tags, cei.custody_status, 'ingested'
                    FROM case_evidence_items cei
                    JOIN cases c ON cei.case_id = c.case_id
                    WHERE c.case_number = %s
                      AND NOT EXISTS (
                          SELECT 1 FROM case_evidence_items existing 
                          WHERE existing.case_id = %s AND existing.asset_id = cei.asset_id
                      );
                """, (target_case_id, source_case_number, target_case_id))
                linked_count = cur.rowcount
            else:
                # Link all physical assets from master vault into this case
                cur.execute("""
                    INSERT INTO case_evidence_items (
                        case_id, asset_id, original_filepath, original_filename,
                        source_parent_dir, custody_status, last_action
                    )
                    SELECT 
                        %s, ma.asset_id, ma.storage_rel_path, 
                        COALESCE(ma.source_rel_path, split_part(ma.storage_rel_path, '/', -1), 'imported_evidence.jpg'),
                        COALESCE(ma.source_folder, 'Master_Vault'),
                        'INGESTED', 'ingested'
                    FROM media_assets ma
                    WHERE NOT EXISTS (
                          SELECT 1 FROM case_evidence_items existing 
                          WHERE existing.case_id = %s AND existing.asset_id = ma.asset_id
                    );
                """, (target_case_id, target_case_id))
                linked_count = cur.rowcount

            conn.commit()
            return {"success": True, "linked_count": linked_count, "target_case": target_case_number}
    finally:
        if should_close:
            conn.close()


def get_series_list(case_number=None, conn=None):
    """Returns distinct series names from known_series, case evidence, and hash sets."""
    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            if case_number and case_number != "ALL":
                cur.execute("""
                    SELECT DISTINCT s.series_name FROM (
                        SELECT series_name FROM known_series
                        UNION
                        SELECT cei.series_tag AS series_name 
                        FROM case_evidence_items cei
                        JOIN cases c ON cei.case_id = c.case_id
                        WHERE c.case_number = %s AND cei.series_tag IS NOT NULL AND cei.series_tag != ''
                    ) s
                    WHERE s.series_name IS NOT NULL AND s.series_name != ''
                    ORDER BY series_name ASC;
                """, (case_number,))
            else:
                cur.execute("""
                    SELECT DISTINCT s.series_name FROM (
                        SELECT series_name FROM known_series
                        UNION
                        SELECT series_tag AS series_name FROM case_evidence_items WHERE series_tag IS NOT NULL AND series_tag != ''
                        UNION
                        SELECT series_name FROM known_hash_sets WHERE series_name IS NOT NULL AND series_name != ''
                    ) s
                    WHERE s.series_name IS NOT NULL AND s.series_name != ''
                    ORDER BY series_name ASC;
                """)
            rows = cur.fetchall()
            series_list = [r["series_name"] for r in rows if r["series_name"]]
            return {"success": True, "series_list": series_list}
    finally:
        if should_close:
            conn.close()


def create_series(body, conn=None):
    """Creates and registers a new Series entity in the database."""
    series_name = (body.get("series_name") or "").strip()
    if not series_name:
        return {"success": False, "error": "series_name is required"}
    description = body.get("description", "")
    performed_by = body.get("performed_by") or forensic_identity.get_forensic_performed_by()

    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO known_series (series_name, description, created_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (series_name) DO UPDATE SET 
                    description = COALESCE(NULLIF(EXCLUDED.description, ''), known_series.description)
                RETURNING series_id, series_name, description, created_by, created_at;
            """, (series_name, description, performed_by))
            row = cur.fetchone()
            conn.commit()
            return {"success": True, "series": row}
    finally:
        if should_close:
            conn.close()


def get_folders_list(conn=None):
    """Returns distinct source folders and asset counts from media_assets with hierarchical grouping."""
    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT source_rel_path, source_folder, COUNT(*) as cnt 
                FROM media_assets 
                GROUP BY source_rel_path, source_folder;
            """)
            rows = cur.fetchall()

            folder_map = {}
            for r in rows:
                path = r.get("source_rel_path") or ""
                folder = r.get("source_folder") or "Staging_Root"
                cnt = r["cnt"]

                if "STPR" in path or folder == "STPR":
                    group = "STPR (Rally)"
                elif "small_bundle_" in path:
                    import re
                    m = re.search(r'(small_bundle_\d+)', path)
                    group = m.group(1) if m else folder
                elif "Sunday Drive" in path or folder == "Sunday Drive":
                    group = "Sunday Drive"
                elif "more-photos" in path or folder == "more-photos":
                    group = "more-photos"
                elif "known_files" in path or folder == "known_files":
                    group = "known_files"
                elif "2014-" in folder or "2014_" in folder:
                    group = folder
                else:
                    group = folder

                folder_map[group] = folder_map.get(group, 0) + cnt

            folders = [{"folder_name": k, "asset_count": v} for k, v in sorted(folder_map.items())]
            return {"success": True, "folders": folders}
    finally:
        if should_close:
            conn.close()


def get_known_reference_tree(case_number=None, conn=None):
    """Returns structured Known Set tree grouped by series tag and reference files."""
    if isinstance(case_number, dict):
        case_number = case_number.get("case_number")
    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            if case_number and case_number != "ALL":
                cur.execute("""
                    SELECT 
                        cei.evidence_id,
                        cei.asset_id,
                        cei.original_filename,
                        cei.series_tag,
                        cei.custody_status,
                        ma.thumb_rel_path,
                        ma.storage_rel_path,
                        ma.sha256,
                        ma.md5
                    FROM case_evidence_items cei
                    JOIN media_assets ma ON cei.asset_id = ma.asset_id
                    JOIN cases c ON cei.case_id = c.case_id
                    WHERE cei.series_tag IS NOT NULL AND cei.series_tag != ''
                      AND c.case_number = %s
                    ORDER BY cei.series_tag ASC, cei.original_filename ASC;
                """, (case_number,))
            else:
                cur.execute("""
                    SELECT DISTINCT ON (cei.asset_id, cei.series_tag)
                        cei.evidence_id,
                        cei.asset_id,
                        cei.original_filename,
                        cei.series_tag,
                        cei.custody_status,
                        ma.thumb_rel_path,
                        ma.storage_rel_path,
                        ma.sha256,
                        ma.md5
                    FROM case_evidence_items cei
                    JOIN media_assets ma ON cei.asset_id = ma.asset_id
                    WHERE cei.series_tag IS NOT NULL AND cei.series_tag != ''
                    ORDER BY cei.series_tag ASC, cei.asset_id, cei.original_filename ASC;
                """)
            rows = cur.fetchall()

            tree = {}
            for r in rows:
                s = r["series_tag"]
                if s not in tree:
                    tree[s] = []
                tree[s].append({
                    "evidence_id": r["evidence_id"],
                    "asset_id": r["asset_id"],
                    "filename": r["original_filename"],
                    "thumb_path": r["thumb_rel_path"],
                    "storage_path": r["storage_rel_path"],
                    "sha256": r["sha256"],
                    "md5": r["md5"],
                    "custody_status": r["custody_status"]
                })

            return {"success": True, "tree": tree, "total_series": len(tree), "total_reference_items": len(rows)}
    finally:
        if should_close:
            conn.close()


def export_catalog_data(case_number="ALL", version="1.3", conn=None):
    """Generates standardized case JSON catalog for the case or all assets."""
    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            if not case_number or case_number == "ALL":
                cur.execute("""
                    SELECT 
                        COALESCE(cei.evidence_id, ma.asset_id) as evidence_id,
                        COALESCE(cei.original_filename, split_part(ma.storage_rel_path, '/', -1)) as original_filename,
                        cei.series_tag,
                        cei.tags,
                        cei.analyst_notes,
                        COALESCE(cei.custody_status, 'INGESTED') as custody_status,
                        ma.sha256,
                        ma.md5,
                        ma.sha1,
                        ma.file_size_bytes,
                        ma.media_type,
                        ma.width_pixels,
                        ma.height_pixels,
                        ma.storage_rel_path,
                        ref.identifier as ref_identifier,
                        ref.series_name as ref_series_name
                    FROM media_assets ma
                    LEFT JOIN case_evidence_items cei ON cei.asset_id = ma.asset_id
                    LEFT JOIN reference_catalog_records ref ON ma.md5 = ref.md5;
                """)
            else:
                cur.execute("""
                    SELECT 
                        cei.evidence_id,
                        cei.original_filename,
                        cei.series_tag,
                        cei.tags,
                        cei.analyst_notes,
                        cei.custody_status,
                        ma.sha256,
                        ma.md5,
                        ma.sha1,
                        ma.file_size_bytes,
                        ma.media_type,
                        ma.width_pixels,
                        ma.height_pixels,
                        ma.storage_rel_path,
                        ref.identifier as ref_identifier,
                        ref.series_name as ref_series_name
                    FROM case_evidence_items cei
                    JOIN media_assets ma ON cei.asset_id = ma.asset_id
                    JOIN cases c ON cei.case_id = c.case_id
                    LEFT JOIN reference_catalog_records ref ON ma.md5 = ref.md5
                    WHERE c.case_number = %s;
                """, (case_number,))
            rows = cur.fetchall()

            media_items = []
            for r in rows:
                media_items.append({
                    "MediaID": str(r["evidence_id"]),
                    "FileName": r["original_filename"],
                    "FileSize": r["file_size_bytes"],
                    "SHA256": r["sha256"].strip() if r["sha256"] else None,
                    "MD5": r["md5"].strip() if r["md5"] else None,
                    "SHA1": r["sha1"].strip() if r["sha1"] else None,
                    "Series": r["series_tag"] or r["ref_series_name"] or "",
                    "Tags": r["tags"] or [],
                    "Notes": r["analyst_notes"] or "",
                    "CustodyStatus": r["custody_status"],
                    "RelativeFilePath": r["storage_rel_path"]
                })

            catalog_export = {
                "Catalog_Version": version,
                "Case": case_number,
                "ExportDate": datetime.utcnow().isoformat() + "Z",
                "TotalItems": len(media_items),
                "Media": media_items
            }
            return {"success": True, "catalog": catalog_export}
    finally:
        if should_close:
            conn.close()


def update_evidence_status(body, conn=None):
    """
    Updates series tag, tags, or custody status for an evidence item
    and logs an immutable event in case_evidence_actions.
    """
    evidence_id = body.get("evidence_id")
    if not evidence_id:
        return {"success": False, "error": "evidence_id is required"}

    new_status = body.get("custody_status")
    series_tag = body.get("series_tag")
    tags = body.get("tags")
    notes = body.get("analyst_notes")
    performed_by = body.get("performed_by") or forensic_identity.get_forensic_performed_by()

    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            # 1. Fetch current item state from case_evidence_items
            cur.execute("""
                SELECT cei.*, ma.sha256, ma.md5, ma.sha1 
                FROM case_evidence_items cei
                JOIN media_assets ma ON cei.asset_id = ma.asset_id
                WHERE cei.evidence_id = %s;
            """, (evidence_id,))
            current = cur.fetchone()

            # If not found by evidence_id, check if evidence_id is an asset_id in media_assets!
            if not current:
                cur.execute("""
                    SELECT ma.asset_id, ma.sha256, ma.md5, ma.sha1, ma.storage_rel_path,
                           COALESCE(split_part(ma.storage_rel_path, '/', -1), 'evidence_item') as original_filename
                    FROM media_assets ma
                    WHERE ma.asset_id = %s;
                """, (evidence_id,))
                ma_row = cur.fetchone()
                if ma_row:
                    target_case_num = body.get("case_number")
                    case_id = None
                    if target_case_num and target_case_num != "ALL":
                        cur.execute("SELECT case_id FROM cases WHERE case_number = %s;", (target_case_num,))
                        c_row = cur.fetchone()
                        if c_row:
                            case_id = c_row["case_id"]

                    cur.execute("""
                        INSERT INTO case_evidence_items (
                            case_id, asset_id, original_filepath, original_filename, custody_status
                        ) VALUES (%s, %s, %s, %s, 'INGESTED')
                        RETURNING evidence_id, custody_status, series_tag, tags, analyst_notes;
                    """, (case_id, ma_row["asset_id"], ma_row["storage_rel_path"], ma_row["original_filename"]))
                    created_cei = cur.fetchone()
                    if created_cei:
                        evidence_id = created_cei["evidence_id"]
                        current = created_cei
                        current["sha256"] = ma_row["sha256"]
                        current["md5"] = ma_row["md5"]
                        current["sha1"] = ma_row["sha1"]
                        current["original_filename"] = ma_row["original_filename"]

            if not current:
                return {"success": False, "error": "Evidence item not found"}

            if series_tag:
                cur.execute("""
                    INSERT INTO known_series (series_name, created_by)
                    VALUES (%s, %s)
                    ON CONFLICT (series_name) DO NOTHING;
                """, (series_tag, performed_by))

            update_fields = []
            params = []
            logged_actions = []

            # 1. Custody Status Change
            if new_status and new_status != current.get("custody_status"):
                update_fields.append("custody_status = %s")
                params.append(new_status)
                logged_actions.append({
                    "action_type": "status-change",
                    "previous_value": current.get("custody_status") or "",
                    "new_value": new_status,
                    "details": {"field": "custody_status", "old": current.get("custody_status"), "new": new_status}
                })

            # 2. Series Tag Change
            if series_tag is not None and series_tag != (current.get("series_tag") or ""):
                update_fields.append("series_tag = %s")
                params.append(series_tag)
                act = "series-add" if series_tag else "series-delete"
                logged_actions.append({
                    "action_type": act,
                    "previous_value": current.get("series_tag") or "",
                    "new_value": series_tag or "",
                    "details": {"field": "series_tag", "old": current.get("series_tag"), "new": series_tag}
                })

            # 3. Tags Change (Add / Remove / Clear)
            if tags is not None:
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                elif isinstance(tags, (list, tuple, set)):
                    flattened = []
                    for t in tags:
                        for sub in str(t).split(","):
                            sub = sub.strip()
                            if sub and sub not in flattened:
                                flattened.append(sub)
                    tags = flattened
                else:
                    tags = []
                
                prev_tags = current.get("tags") or []
                if set(prev_tags) != set(tags):
                    update_fields.append("tags = %s")
                    params.append(tags)
                    if len(tags) == 0 and len(prev_tags) > 0:
                        tag_act = "tag-delete"
                    elif set(tags).issubset(set(prev_tags)) or len(tags) < len(prev_tags):
                        tag_act = "tag-delete"
                    elif len(tags) > len(prev_tags):
                        tag_act = "tag-add"
                    else:
                        tag_act = "tag-only"
                    
                    removed = list(set(prev_tags) - set(tags))
                    added = list(set(tags) - set(prev_tags))
                    logged_actions.append({
                        "action_type": tag_act,
                        "previous_value": ", ".join(prev_tags),
                        "new_value": ", ".join(tags),
                        "details": {"field": "tags", "removed_tags": removed, "added_tags": added}
                    })

            # 4. Analyst Notes Change
            if notes is not None and notes != (current.get("analyst_notes") or ""):
                update_fields.append("analyst_notes = %s")
                params.append(notes)
                if not notes:
                    note_act = "notes-delete"
                elif not current.get("analyst_notes"):
                    note_act = "notes-add"
                else:
                    note_act = "notes-update"
                logged_actions.append({
                    "action_type": note_act,
                    "previous_value": current.get("analyst_notes") or "",
                    "new_value": notes or "",
                    "details": {"field": "analyst_notes"}
                })

            if not update_fields:
                return {"success": True, "message": "No changes requested"}

            primary_action = logged_actions[-1]["action_type"] if logged_actions else "status-change"
            update_fields.extend(["last_action = %s", "last_action_at = CURRENT_TIMESTAMP", "updated_at = CURRENT_TIMESTAMP"])
            params.extend([primary_action, evidence_id])

            update_sql = f"UPDATE case_evidence_items SET {', '.join(update_fields)} WHERE evidence_id = %s;"
            cur.execute(update_sql, params)

            # Log audit trail entries for each change
            for act in logged_actions:
                cur.execute("""
                    INSERT INTO case_evidence_actions (
                        evidence_id, action_type, original_filename, sha1, sha256, md5,
                        previous_value, new_value, performed_by, details
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                    );
                """, (
                    evidence_id, act["action_type"], current["original_filename"],
                    current["sha1"], current["sha256"], current["md5"],
                    act["previous_value"], act["new_value"],
                    performed_by, json.dumps(act["details"])
                ))

            conn.commit()
            return {
                "success": True, 
                "evidence_id": evidence_id, 
                "action_type": primary_action,
                "series_tag": series_tag,
                "tags": tags,
                "custody_status": new_status,
                "analyst_notes": notes
            }
    finally:
        if should_close:
            conn.close()


# =============================================================================
# 2. MULTIMODAL PGVECTOR SIMILARITY SEARCH APIS
# =============================================================================

def search_multimodal(body, conn=None):
    """
    Executes high-speed vector similarity search across CLIP, SigLIP Base, or SigLIP-2.
    Supports query types: 'text', 'crop' (base64 image), 'asset_id', or 'vector'.
    """
    query_type = body.get("type", "text").lower()
    model_name = body.get("model", "siglip2_naflex").lower()
    if model_name not in ("clip", "siglip", "siglip2_naflex", "dinov3"):
        model_name = "siglip2_naflex"

    threshold_raw = body.get("threshold")
    threshold = float(threshold_raw) if threshold_raw is not None and str(threshold_raw).strip() != "" else None
    limit = min(int(body.get("limit", 50)), 200)
    case_filter = body.get("case_number", "").strip()

    embedder = get_embedder()
    query_vec = None

    t0 = time.time()

    # 1. Resolve Query Vector
    if query_type == "text":
        text_query = body.get("query", "").strip()
        if not text_query:
            return {"success": False, "error": "Query text cannot be empty"}
        query_vec = embedder.compute_text_embedding(text_query, model_name=model_name)

    elif query_type == "crop":
        b64_data = body.get("image_base64", "")
        if not b64_data:
            return {"success": False, "error": "image_base64 data cannot be empty"}
        try:
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]
            img_bytes = base64.b64decode(b64_data)
            pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            all_embs = embedder.compute_all_embeddings(pil_img)
            query_vec = all_embs.get(model_name)
        except Exception as e:
            return {"success": False, "error": f"Failed to process crop image: {e}"}

    elif query_type == "asset_id":
        asset_id = body.get("asset_id")
        if not asset_id:
            return {"success": False, "error": "asset_id is required"}

        should_close_temp = False
        conn_temp = conn or db.get_connection()
        try:
            with conn_temp.cursor() as cur:
                cur.execute("""
                    SELECT embedding_l2 
                    FROM media_embeddings 
                    WHERE asset_id = %s AND model_name = %s;
                """, (asset_id, model_name))
                row = cur.fetchone()
                if row:
                    query_vec = row["embedding_l2"]
                    if hasattr(query_vec, "tolist"):
                        query_vec = query_vec.tolist()
        finally:
            if conn is None:
                conn_temp.close()

    elif query_type in ("vector", "embedding"):
        raw_vec = body.get("vector") or body.get("embedding")
        if not raw_vec or not isinstance(raw_vec, list):
            return {"success": False, "error": "Valid float vector array is required"}
        query_vec = raw_vec

    if not query_vec:
        return {"success": False, "error": f"Could not generate query vector for model '{model_name}'"}

    # 2. Execute pgvector Cosine Distance Query
    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    where_extra = ""
    sql_params = [list(query_vec), model_name]

    if threshold is not None:
        where_extra += " AND (1 - (me.embedding_l2 <=> %s::vector)) >= %s"
        sql_params.extend([list(query_vec), threshold])

    if case_filter and case_filter != "ALL":
        where_extra += " AND c.case_number = %s"
        sql_params.append(case_filter)
        join_clause = "JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id JOIN cases c ON cei.case_id = c.case_id"
    else:
        join_clause = "LEFT JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id LEFT JOIN cases c ON cei.case_id = c.case_id"

    sql_params.extend([list(query_vec), limit])

    try:
        with conn.cursor() as cur:
            if not case_filter or case_filter == "ALL":
                threshold_sql = "AND (1 - (me.embedding_l2 <=> %s::vector)) >= %s" if threshold is not None else ""
                sql_params = [list(query_vec), model_name]
                if threshold is not None:
                    sql_params.extend([list(query_vec), threshold])
                sql_params.extend([list(query_vec), limit])

                query = f"""
                    WITH top_matches AS (
                        SELECT 
                            me.asset_id,
                            1 - (me.embedding_l2 <=> %s::vector) AS similarity_score
                        FROM media_embeddings me
                        WHERE me.model_name = %s {threshold_sql}
                        ORDER BY me.embedding_l2 <=> %s::vector ASC
                        LIMIT %s
                    )
                    SELECT * FROM (
                        SELECT DISTINCT ON (tm.asset_id)
                            tm.asset_id,
                            COALESCE(cei.evidence_id, ma.asset_id) AS evidence_id,
                            COALESCE(
                                NULLIF((SELECT cei3.original_filename FROM case_evidence_items cei3 WHERE cei3.asset_id = ma.asset_id AND NOT starts_with(cei3.original_filename, '01_Media_Vault/') LIMIT 1), ''),
                                cei.original_filename,
                                split_part(ma.storage_rel_path, '/', -1)
                            ) AS original_filename,
                            cei.source_parent_dir,
                            cei.series_tag,
                            cei.tags,
                            COALESCE(cei.custody_status, 'INGESTED') AS custody_status,
                            CASE WHEN c.status = 'ACTIVE' THEN c.case_number ELSE NULL END AS case_number,
                            ma.storage_rel_path,
                            ma.thumb_rel_path,
                            ma.file_size_bytes,
                            ma.width_pixels,
                            ma.height_pixels,
                            ma.source_folder,
                            ma.source_rel_path,
                            ref.identifier as ref_identifier,
                            ref.series_name as ref_series_name,
                            ref.flag_identified as ref_flag_identified,
                            ref.flag_actionable as ref_flag_actionable,
                            tm.similarity_score
                        FROM top_matches tm
                        JOIN media_assets ma ON tm.asset_id = ma.asset_id
                        LEFT JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id
                        LEFT JOIN cases c ON cei.case_id = c.case_id
                        LEFT JOIN reference_catalog_records ref ON ma.md5 = ref.md5
                        ORDER BY tm.asset_id, tm.similarity_score DESC
                    ) sub
                    ORDER BY similarity_score DESC;
                """
            else:
                query = f"""
                    SELECT * FROM (
                        SELECT DISTINCT ON (ma.asset_id)
                            ma.asset_id,
                            COALESCE(cei.evidence_id, ma.asset_id) AS evidence_id,
                            COALESCE(
                                NULLIF((SELECT cei3.original_filename FROM case_evidence_items cei3 WHERE cei3.asset_id = ma.asset_id AND NOT starts_with(cei3.original_filename, '01_Media_Vault/') LIMIT 1), ''),
                                cei.original_filename,
                                split_part(ma.storage_rel_path, '/', -1)
                            ) AS original_filename,
                            cei.source_parent_dir,
                            cei.series_tag,
                            cei.tags,
                            COALESCE(cei.custody_status, 'INGESTED') AS custody_status,
                            CASE WHEN c.status = 'ACTIVE' THEN c.case_number ELSE NULL END AS case_number,
                            ma.storage_rel_path,
                            ma.thumb_rel_path,
                            ma.file_size_bytes,
                            ma.width_pixels,
                            ma.height_pixels,
                            ma.source_folder,
                            ma.source_rel_path,
                            ref.identifier as ref_identifier,
                            ref.series_name as ref_series_name,
                            ref.flag_identified as ref_flag_identified,
                            ref.flag_actionable as ref_flag_actionable,
                            1 - (me.embedding_l2 <=> %s::vector) AS similarity_score
                        FROM media_embeddings me
                        JOIN media_assets ma ON me.asset_id = ma.asset_id
                        {join_clause}
                        LEFT JOIN reference_catalog_records ref ON ma.md5 = ref.md5
                        WHERE me.model_name = %s
                          {where_extra}
                        ORDER BY ma.asset_id, (me.embedding_l2 <=> %s::vector) ASC
                    ) sub
                    ORDER BY similarity_score DESC
                    LIMIT %s;
                """
            cur.execute(query, sql_params)
            results = cur.fetchall()
            elapsed_ms = (time.time() - t0) * 1000

            return {
                "success": True,
                "model": model_name,
                "query_type": query_type,
                "count": len(results),
                "elapsed_ms": round(elapsed_ms, 2),
                "results": results,
                "query_vector": list(query_vec)
            }
    finally:
        if should_close:
            conn.close()


def execute_crop_search(body, conn=None):
    """
    Crops an image region based on normalized coordinates (x, y, width, height)
    or base64 data, computes vector embeddings, and runs pgvector similarity search.
    Supports single model or 'top15' multi-model search.
    """
    img_path = body.get("path") or body.get("storage_rel_path")
    asset_id = body.get("asset_id")
    x = float(body.get("x", 0.0))
    y = float(body.get("y", 0.0))
    width = float(body.get("width", 1.0))
    height = float(body.get("height", 1.0))
    model_type = body.get("model", "siglip2_naflex").lower()
    case_number = body.get("case_number", "").strip()
    top_k = min(int(body.get("limit", 50)), 100)

    # 1. Locate physical master image on disk and thumbnail
    actual_path = None
    thumb_path = None

    if asset_id:
        should_close = False
        if conn is None:
            conn = db.get_connection()
            should_close = True
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT storage_rel_path, thumb_rel_path FROM media_assets WHERE asset_id = %s;", (asset_id,))
                row = cur.fetchone()
                if row:
                    if row.get("thumb_rel_path"):
                        cand_thumb = os.path.join(VAULT_ROOT, row["thumb_rel_path"].lstrip("/"))
                        if os.path.isfile(cand_thumb):
                            thumb_path = cand_thumb
                    if row.get("storage_rel_path"):
                        cand = os.path.join(VAULT_ROOT, row["storage_rel_path"].lstrip("/"))
                        if os.path.isfile(cand):
                            actual_path = cand
        finally:
            if should_close:
                conn.close()
                conn = None

    if not actual_path and img_path:
        clean_rel = img_path.lstrip("/").replace("..", "")
        cand = os.path.join(VAULT_ROOT, clean_rel)
        if os.path.isfile(cand):
            actual_path = cand
        elif os.path.isfile(img_path):
            actual_path = img_path

    if not actual_path or not os.path.exists(actual_path):
        return {"success": False, "error": f"Image file not found: {img_path or asset_id}"}

    try:
        # Fast Image Loading: Always prioritize fast WebP keyframe/thumbnail for sub-millisecond decode
        img = None
        
        # 1. Try DB thumb_path directly
        if thumb_path and os.path.isfile(thumb_path):
            try:
                img = Image.open(thumb_path).convert("RGB")
            except Exception:
                img = None

        # 2. Try conventional 02_Keyframe_Vault structure
        if img is None:
            filename_no_ext = os.path.splitext(os.path.basename(actual_path))[0]
            if len(filename_no_ext) >= 4:
                prefix1 = filename_no_ext[:2]
                prefix2 = filename_no_ext[2:4]
                thumb_target = os.path.join(VAULT_ROOT, "02_Keyframe_Vault", "thumbs_256px", prefix1, prefix2, f"{filename_no_ext}.webp")
                if os.path.isfile(thumb_target):
                    try:
                        img = Image.open(thumb_target).convert("RGB")
                    except Exception:
                        img = None

        # 3. Fallback to master file only if no thumbnail exists
        if img is None:
            from sympics.core.raw_extractor import load_image_or_raw
            img = load_image_or_raw(actual_path)

        if img is None:
            return {"success": False, "error": f"Failed to decode image: {actual_path}"}

        w, h = img.size

        left = int(x * w)
        top = int(y * h)
        right = int((x + width) * w)
        bottom = int((y + height) * h)

        left = max(0, min(left, w - 1))
        top = max(0, min(top, h - 1))
        right = max(left + 1, min(right, w))
        bottom = max(top + 1, min(bottom, h))

        cropped_img = img.crop((left, top, right, bottom))

        # Generate snippet data URL for frontend banner
        buf = io.BytesIO()
        cropped_img.save(buf, format="JPEG", quality=90)
        snippet_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        snippet_url = f"data:image/jpeg;base64,{snippet_b64}"

        crop_info = {
            "snippet_url": snippet_url,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "filename": os.path.basename(actual_path),
            "source_path": img_path
        }

        embedder = get_embedder()

        # If model_type is top15, compute all models for comparative matrix
        if model_type == "top15":
            res = multi_model_compare({
                "type": "crop",
                "image_base64": snippet_url,
                "top_k": 15,
                "case_number": case_number
            }, conn=conn)
            res["crop_info"] = crop_info
            return res
        else:
            # High-speed single-model evaluation (3x faster on CPU)
            target_vec = embedder.compute_single_image_embedding(cropped_img, model_name=model_type)
            if not target_vec:
                return {"success": False, "error": f"Failed to compute embedding for {model_type}"}

            res = search_multimodal({
                "type": "vector",
                "vector": target_vec,
                "model": model_type,
                "limit": top_k,
                "case_number": case_number
            }, conn=conn)
            res["crop_info"] = crop_info
            return res

    except Exception as e:
        return {"success": False, "error": f"Crop processing error: {e}"}


def multi_model_compare(body, conn=None):
    """
    "Top 15 (All)" Comparative Search.
    Computes query vectors across CLIP, SigLIP, and SigLIP-2, and executes
    simultaneous pgvector queries, returning side-by-side results and raw vectors.
    """
    query_type = body.get("type", "asset_id").lower()
    top_k = min(int(body.get("top_k", 15)), 50)

    embedder = get_embedder()
    query_vectors = {}

    # 1. Compute Vectors for all 3 models
    if query_type == "text":
        text = body.get("query", "").strip()
        if not text:
            return {"success": False, "error": "Query text cannot be empty"}
        query_vectors = embedder.compute_all_text_embeddings(text)

    elif query_type == "crop":
        b64_data = body.get("image_base64", "")
        if not b64_data:
            return {"success": False, "error": "image_base64 is required"}
        if "," in b64_data:
            b64_data = b64_data.split(",", 1)[1]
        img_bytes = base64.b64decode(b64_data)
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        query_vectors = embedder.compute_all_embeddings(pil_img)

    elif query_type == "asset_id":
        asset_id = body.get("asset_id")
        if not asset_id:
            return {"success": False, "error": "asset_id is required"}

        conn_temp = conn or db.get_connection()
        try:
            with conn_temp.cursor() as cur:
                cur.execute("""
                    SELECT model_name, embedding_l2 
                    FROM media_embeddings 
                    WHERE asset_id = %s;
                """, (asset_id,))
                for r in cur.fetchall():
                    vec = r["embedding_l2"]
                    query_vectors[r["model_name"]] = vec.tolist() if hasattr(vec, "tolist") else vec
        finally:
            if conn is None:
                conn_temp.close()

    if not query_vectors:
        return {"success": False, "error": "Could not obtain comparison vectors"}

    # 2. Run similarity search for each model
    results_by_model = {}
    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    case_filter = body.get("case_number", "").strip()
    where_extra = ""
    if case_filter and case_filter != "ALL":
        where_extra = "AND c.case_number = %s"
        join_clause = "JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id JOIN cases c ON cei.case_id = c.case_id"
    else:
        join_clause = "LEFT JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id LEFT JOIN cases c ON cei.case_id = c.case_id"

    try:
        with conn.cursor() as cur:
            for model_name, vec in query_vectors.items():
                if not vec:
                    continue

                if not case_filter or case_filter == "ALL":
                    sql_params = [list(vec), model_name, list(vec), top_k]
                    query = f"""
                        WITH top_matches AS (
                            SELECT 
                                me.asset_id,
                                1 - (me.embedding_l2 <=> %s::vector) AS similarity_score
                            FROM media_embeddings me
                            WHERE me.model_name = %s
                            ORDER BY me.embedding_l2 <=> %s::vector ASC
                            LIMIT %s
                        )
                        SELECT * FROM (
                            SELECT DISTINCT ON (tm.asset_id)
                                tm.asset_id,
                                COALESCE(cei.evidence_id, ma.asset_id) AS evidence_id,
                                COALESCE(
                                    NULLIF((SELECT cei3.original_filename FROM case_evidence_items cei3 WHERE cei3.asset_id = ma.asset_id AND NOT starts_with(cei3.original_filename, '01_Media_Vault/') LIMIT 1), ''),
                                    cei.original_filename,
                                    split_part(ma.storage_rel_path, '/', -1)
                                ) AS original_filename,
                                cei.source_parent_dir,
                                cei.series_tag,
                                cei.tags,
                                COALESCE(cei.custody_status, 'INGESTED') AS custody_status,
                                CASE WHEN c.status = 'ACTIVE' THEN c.case_number ELSE NULL END AS case_number,
                                ma.file_size_bytes,
                                ma.thumb_rel_path,
                                ma.storage_rel_path,
                                ma.source_folder,
                                ma.source_rel_path,
                                ref.identifier as ref_identifier,
                                ref.series_name as ref_series_name,
                                ref.flag_identified as ref_flag_identified,
                                tm.similarity_score
                            FROM top_matches tm
                            JOIN media_assets ma ON tm.asset_id = ma.asset_id
                            LEFT JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id
                            LEFT JOIN cases c ON cei.case_id = c.case_id
                            LEFT JOIN reference_catalog_records ref ON ma.md5 = ref.md5
                            ORDER BY tm.asset_id, tm.similarity_score DESC
                        ) sub
                        ORDER BY similarity_score DESC;
                    """
                else:
                    sql_params = [list(vec), model_name, case_filter, list(vec), top_k]
                    query = f"""
                        SELECT * FROM (
                            SELECT DISTINCT ON (ma.asset_id)
                                ma.asset_id,
                                COALESCE(cei.evidence_id, ma.asset_id) AS evidence_id,
                                COALESCE(
                                    NULLIF((SELECT cei3.original_filename FROM case_evidence_items cei3 WHERE cei3.asset_id = ma.asset_id AND NOT starts_with(cei3.original_filename, '01_Media_Vault/') LIMIT 1), ''),
                                    cei.original_filename,
                                    split_part(ma.storage_rel_path, '/', -1)
                                ) AS original_filename,
                                cei.source_parent_dir,
                                cei.series_tag,
                                cei.tags,
                                COALESCE(cei.custody_status, 'INGESTED') AS custody_status,
                                CASE WHEN c.status = 'ACTIVE' THEN c.case_number ELSE NULL END AS case_number,
                                ma.file_size_bytes,
                                ma.thumb_rel_path,
                                ma.storage_rel_path,
                                ma.source_folder,
                                ma.source_rel_path,
                                ref.identifier as ref_identifier,
                                ref.series_name as ref_series_name,
                                ref.flag_identified as ref_flag_identified,
                                1 - (me.embedding_l2 <=> %s::vector) AS similarity_score
                            FROM media_embeddings me
                            JOIN media_assets ma ON me.asset_id = ma.asset_id
                            {join_clause}
                            LEFT JOIN reference_catalog_records ref ON ma.md5 = ref.md5
                            WHERE me.model_name = %s
                              {where_extra}
                            ORDER BY ma.asset_id, (me.embedding_l2 <=> %s::vector) ASC
                        ) sub
                        ORDER BY similarity_score DESC
                        LIMIT %s;
                    """
                cur.execute(query, sql_params)
                results_by_model[model_name] = cur.fetchall()

        return {
            "success": True,
            "top_k": top_k,
            "models": list(results_by_model.keys()),
            "results": results_by_model,
            "query_vectors": query_vectors
        }
    finally:
        if should_close:
            conn.close()


def execute_series_collision_scan(body, conn=None):
    """
    Part Two: Series Cross-Vault Collision Engine.
    Takes a series name (e.g. 'Known_SeriesX'), retrieves all reference target vectors
    and hashes belonging to this series, and performs an exhaustive pgvector HNSW
    cosine similarity query & hash collision scan across all physical holdings in media_assets.
    """
    series_name = (body.get("series_name") or "").strip()
    if not series_name:
        return {"success": False, "error": "series_name is required"}

    threshold = float(body.get("threshold", 0.75))
    limit_per_target = min(int(body.get("limit_per_target", 30)), 100)
    model_name = body.get("model", "siglip2_naflex").lower()

    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            # 1. Fetch all reference targets in this series with vectors
            cur.execute("""
                SELECT DISTINCT ON (ma.asset_id)
                    ma.asset_id,
                    COALESCE(cei.original_filename, split_part(ma.storage_rel_path, '/', -1)) AS filename,
                    ma.storage_rel_path,
                    ma.thumb_rel_path,
                    ma.sha256,
                    ma.md5,
                    ma.source_folder,
                    ma.source_rel_path,
                    me.embedding_l2
                FROM media_assets ma
                LEFT JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id
                LEFT JOIN media_embeddings me ON ma.asset_id = me.asset_id AND me.model_name = %s
                WHERE (cei.series_tag = %s OR ma.source_folder = %s)
                  AND me.embedding_l2 IS NOT NULL;
            """, (model_name, series_name, series_name))
            targets = cur.fetchall()

            if not targets:
                # Check if raw targets exist without embeddings
                cur.execute("""
                    SELECT DISTINCT ON (ma.asset_id)
                        ma.asset_id,
                        COALESCE(cei.original_filename, split_part(ma.storage_rel_path, '/', -1)) AS filename,
                        ma.storage_rel_path,
                        ma.thumb_rel_path,
                        ma.sha256,
                        ma.md5,
                        ma.source_folder,
                        ma.source_rel_path
                    FROM media_assets ma
                    LEFT JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id
                    WHERE cei.series_tag = %s OR ma.source_folder = %s;
                """, (series_name, series_name))
                raw_targets = cur.fetchall()
                if not raw_targets:
                    return {"success": False, "error": f"No evidence items found in Series '{series_name}'"}
                return {
                    "success": True,
                    "series_name": series_name,
                    "targets_count": len(raw_targets),
                    "total_collisions": 0,
                    "collisions": [],
                    "message": f"Series '{series_name}' has {len(raw_targets)} items, but no {model_name} vectors indexed yet."
                }

            target_asset_ids = [str(t["asset_id"]) for t in targets]
            collisions_map = {}

            # 2. For each target, query pgvector for cross-vault nearest neighbors
            for t in targets:
                t_vec = t["embedding_l2"]
                t_id = str(t["asset_id"])
                t_fn = t["filename"]
                t_thumb = t["thumb_rel_path"] or t["storage_rel_path"]

                # Convert vector to list format if necessary
                vec_list = t_vec.tolist() if hasattr(t_vec, "tolist") else list(t_vec)

                cur.execute("""
                    SELECT 
                        ma.asset_id,
                        COALESCE(
                            (SELECT cei2.original_filename FROM case_evidence_items cei2 WHERE cei2.asset_id = ma.asset_id AND NOT starts_with(cei2.original_filename, '01_Media_Vault/') LIMIT 1),
                            split_part(ma.storage_rel_path, '/', -1)
                        ) AS original_filename,
                        ma.storage_rel_path,
                        ma.thumb_rel_path,
                        ma.sha256,
                        ma.md5,
                        ma.source_folder,
                        ma.source_rel_path,
                        ma.media_type,
                        ma.gps_latitude,
                        ma.gps_longitude,
                        (SELECT cei3.series_tag FROM case_evidence_items cei3 WHERE cei3.asset_id = ma.asset_id AND cei3.series_tag IS NOT NULL LIMIT 1) AS current_series_tag,
                        (SELECT ARRAY_AGG(DISTINCT c2.case_number) FROM case_evidence_items cei2 JOIN cases c2 ON cei2.case_id = c2.case_id WHERE cei2.asset_id = ma.asset_id AND c2.status = 'ACTIVE') AS linked_cases,
                        1 - (me.embedding_l2 <=> %s::vector) AS similarity_score
                    FROM media_embeddings me
                    JOIN media_assets ma ON me.asset_id = ma.asset_id
                    WHERE me.model_name = %s
                      AND ma.asset_id != ALL(%s::uuid[])
                      AND 1 - (me.embedding_l2 <=> %s::vector) >= %s
                    ORDER BY similarity_score DESC
                    LIMIT %s;
                """, (vec_list, model_name, target_asset_ids, vec_list, threshold, limit_per_target))
                matches = cur.fetchall()

                for m in matches:
                    m_id = str(m["asset_id"])
                    sim = float(m["similarity_score"])
                    if m_id not in collisions_map or sim > collisions_map[m_id]["similarity_score"]:
                        collisions_map[m_id] = {
                            "asset_id": m_id,
                            "original_filename": m["original_filename"],
                            "storage_rel_path": m["storage_rel_path"],
                            "thumb_rel_path": m["thumb_rel_path"],
                            "sha256": m["sha256"],
                            "md5": m["md5"],
                            "source_folder": m["source_folder"],
                            "source_rel_path": m["source_rel_path"],
                            "media_type": m["media_type"],
                            "gps_latitude": m["gps_latitude"],
                            "gps_longitude": m["gps_longitude"],
                            "current_series_tag": m["current_series_tag"],
                            "linked_cases": m["linked_cases"] or [],
                            "similarity_score": sim,
                            "matched_target_id": t_id,
                            "matched_target_filename": t_fn,
                            "matched_target_thumb": t_thumb
                        }

            # Sort overall collisions by similarity descending
            sorted_collisions = sorted(collisions_map.values(), key=lambda x: x["similarity_score"], reverse=True)

            return {
                "success": True,
                "series_name": series_name,
                "model": model_name,
                "threshold": threshold,
                "targets_count": len(targets),
                "total_collisions": len(sorted_collisions),
                "collisions": sorted_collisions
            }
    finally:
        if should_close:
            conn.close()


# =============================================================================
# 3. INTELLIGENCE, TELEMETRY & DATABASE EXPLORER APIS
# =============================================================================

def get_reference_collisions_list(limit=100, conn=None):
    """Returns all active vault collisions against reference intelligence."""
    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM v_reference_known_collisions 
                ORDER BY reference_import_date DESC 
                LIMIT %s;
            """, (limit,))
            collisions = cur.fetchall()

            cur.execute("SELECT COUNT(*) as total FROM reference_catalog_records;")
            total_catalog = cur.fetchone()["total"]

            return {"success": True, "total_catalog_records": total_catalog, "collisions": collisions}
    finally:
        if should_close:
            conn.close()


def get_telemetry_status(vault_root, staging_dir, conn=None):
    """Returns live intake queue depth, GPU hardware status, staging files, recent ingested evidence, and forensic audit stats."""
    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        # Ingestion Staging files
        staging_files = []
        if os.path.exists(staging_dir):
            for root, dirs, files in os.walk(staging_dir):
                if "_quarantine" in root:
                    continue
                for f in sorted(files):
                    if f.startswith((".", "_")):
                        continue
                    fp = os.path.join(root, f)
                    try:
                        st = os.stat(fp)
                        staging_files.append({
                            "filename": f,
                            "rel_path": os.path.relpath(fp, staging_dir),
                            "file_size_bytes": st.st_size,
                            "modified_time": datetime.fromtimestamp(st.st_mtime).isoformat()
                        })
                    except Exception:
                        pass

        staging_queue_count = len(staging_files)

        # Quarantine files
        quarantine_dir = os.path.join(staging_dir, "_quarantine")
        quarantine_files = []
        if os.path.exists(quarantine_dir):
            for root, dirs, files in os.walk(quarantine_dir):
                for f in sorted(files):
                    if f.startswith(".") or f.endswith(".error.json"):
                        continue
                    fp = os.path.join(root, f)
                    err_json = fp + ".error.json"
                    err_info = {}
                    if os.path.exists(err_json):
                        try:
                            with open(err_json, "r", encoding="utf-8") as ef:
                                err_info = json.load(ef)
                        except Exception:
                            pass
                    try:
                        st = os.stat(fp)
                        quarantine_files.append({
                            "filename": f,
                            "rel_path": os.path.relpath(fp, staging_dir),
                            "file_size_bytes": st.st_size,
                            "error": err_info.get("error", "Ingestion error"),
                            "quarantined_at": err_info.get("quarantined_at", datetime.fromtimestamp(st.st_mtime).isoformat())
                        })
                    except Exception:
                        pass

        quarantine_count = len(quarantine_files)

        # Embedder status without forcing heavyweight model load if not yet initialized
        import embedder_service
        if embedder_service._global_embedder is not None:
            dev = getattr(embedder_service._global_embedder, "device", "cpu").upper()
            dt = str(getattr(embedder_service._global_embedder, "dtype", "float32"))
        else:
            try:
                import torch
                dev = "CUDA" if torch.cuda.is_available() else "CPU"
                dt = "float16" if dev == "CUDA" else "float32"
            except Exception:
                dev, dt = "CPU", "float32"

        gpu_info = {
            "device": dev,
            "dtype": dt,
            "active_models": ["CLIP (512)", "SigLIP Base (768)", "SigLIP-2 NaFlex (768)", "DINOv3 (768)"]
        }

        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_forensic_integrity_audit;")
            audit = cur.fetchone() or {}

            cur.execute("SELECT model_name, dimension_size, count(*) as count FROM media_embeddings GROUP BY model_name, dimension_size;")
            vector_breakdown = cur.fetchall()

            # Latest 25 ingested evidence items
            cur.execute("""
                SELECT 
                    COALESCE(cei.evidence_id, ma.asset_id) AS evidence_id,
                    COALESCE(
                        cei.original_filename,
                        ma.source_rel_path,
                        split_part(ma.storage_rel_path, '/', -1)
                    ) AS original_filename,
                    ma.source_folder,
                    ma.source_rel_path,
                    ma.asset_id,
                    ma.sha256,
                    ma.md5,
                    ma.file_size_bytes,
                    ma.width_pixels,
                    ma.height_pixels,
                    ma.mime_type,
                    ma.storage_rel_path,
                    ma.thumb_rel_path,
                    COALESCE(cei.custody_status, 'INGESTED') AS custody_status,
                    cei.series_tag,
                    cei.tags,
                    ma.created_at,
                    ref.identifier as ref_identifier,
                    ref.series_name as ref_series_name,
                    (
                        SELECT json_agg(json_build_object('model', me.model_name, 'dim', me.dimension_size))
                        FROM media_embeddings me
                        WHERE me.asset_id = ma.asset_id
                    ) as embeddings,
                    (
                        SELECT ARRAY_AGG(DISTINCT c2.case_number)
                        FROM case_evidence_items cei2
                        JOIN cases c2 ON cei2.case_id = c2.case_id
                        WHERE cei2.asset_id = ma.asset_id AND c2.status = 'ACTIVE'
                    ) AS linked_cases
                FROM media_assets ma
                LEFT JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id
                LEFT JOIN reference_catalog_records ref ON ma.md5 = ref.md5
                ORDER BY ma.created_at DESC
                LIMIT 25;
            """)
            recent_ingested = cur.fetchall()

            return {
                "success": True,
                "staging_queue_count": staging_queue_count,
                "quarantine_count": quarantine_count,
                "staging_files": staging_files,
                "quarantine_files": quarantine_files,
                "recent_ingested": recent_ingested,
                "gpu_status": gpu_info,
                "audit": audit,
                "vector_breakdown": vector_breakdown
            }
    finally:
        if should_close:
            conn.close()


def retry_quarantine_files(staging_dir):
    """Moves files from _quarantine back to 03_Ingestion_Staging to retry intake."""
    quarantine_dir = os.path.join(staging_dir, "_quarantine")
    if not os.path.exists(quarantine_dir):
        return {"success": True, "requeued_count": 0, "message": "Quarantine folder is empty."}

    requeued = []
    for root, dirs, files in os.walk(quarantine_dir):
        for f in files:
            if f.startswith(".") or f.endswith(".error.json"):
                continue
            src_fp = os.path.join(root, f)
            dest_fp = os.path.join(staging_dir, f)
            if os.path.exists(dest_fp):
                base, ext = os.path.splitext(f)
                dest_fp = os.path.join(staging_dir, f"{base}_retry_{int(time.time())}{ext}")
            try:
                shutil.move(src_fp, dest_fp)
                requeued.append(f)
            except Exception as e:
                print(f"[ERROR] Could not requeue {src_fp}: {e}")

            err_json = src_fp + ".error.json"
            if os.path.exists(err_json):
                try:
                    os.remove(err_json)
                except Exception:
                    pass

    return {
        "success": True,
        "requeued_count": len(requeued),
        "requeued_files": requeued
    }


def get_erd_stats(conn=None):
    """Returns exact live row counts for all core schema entities."""
    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM media_assets) as count_media_assets,
                    (SELECT COUNT(*) FROM media_embeddings) as count_media_embeddings,
                    (SELECT COUNT(*) FROM cases) as count_cases,
                    (SELECT COUNT(*) FROM case_evidence_items) as count_case_evidence_items,
                    (SELECT COUNT(*) FROM migration_manifest) as count_migration_manifest,
                    (SELECT COUNT(*) FROM reference_catalog_records) as count_reference_catalog_records,
                    (SELECT COUNT(*) FROM video_keyframes) as count_video_keyframes;
            """)
            return {"success": True, "counts": cur.fetchone()}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if should_close:
            conn.close()


def execute_sql_query(sql_text, conn=None):
    """
    Executes safe read-only SELECT queries inside an isolated READ ONLY transaction
    with strict keyword blocking and statement timeouts.
    """
    sql = (sql_text or "").strip()
    if not sql:
        return {"success": False, "error": "Query cannot be empty"}

    # 1. Strip SQL single-line and multi-line comments
    cleaned_sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
    cleaned_sql = re.sub(r'/\*.*?\*/', '', cleaned_sql, flags=re.DOTALL).strip()

    # 2. Enforce starting keyword
    if not cleaned_sql.lower().startswith(("select", "with", "explain", "show")):
        return {"success": False, "error": "Security Block: Only SELECT / Read-Only queries are permitted."}

    # 3. Block destructive and administrative keywords/functions
    blocked_patterns = [
        r'\bdrop\b', r'\bdelete\b', r'\btruncate\b', r'\balter\b',
        r'\bupdate\b', r'\binsert\b', r'\bgrant\b', r'\brevoke\b',
        r'\bexecute\b', r'\bcopy\b', r'\bcreate\b',
        r'\bpg_terminate_backend\b', r'\bpg_cancel_backend\b',
        r'\bpg_read_file\b', r'\bpg_write_file\b', r'\bpg_read_binary_file\b',
        r'\bpg_sleep\b', r'\bdblink\b'
    ]
    for pattern in blocked_patterns:
        if re.search(pattern, cleaned_sql, flags=re.IGNORECASE):
            return {"success": False, "error": f"Security Block: Destructive or administrative keyword detected."}

    # 4. Check for chained statement semicolons followed by non-whitespace
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
            conn.rollback()  # Always rollback to guarantee zero state modification
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


def get_table_schema_info(table_name, conn=None):
    """Returns columns and indexes definition for the Schema Explorer."""
    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position;
            """, (table_name,))
            columns = cur.fetchall()

            cur.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = %s;
            """, (table_name,))
            indexes = cur.fetchall()

            return {"success": True, "table": table_name, "columns": columns, "indexes": indexes}
    finally:
        if should_close:
            conn.close()


# =============================================================================
# 9. AI AUTO-TRIAGE & VERIFICATION QUEUE APIS
# =============================================================================

def get_ai_triage_queue(params, conn=None):
    """
    Returns all AI auto-tagged evidence items paired with their matched reference image.
    """
    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    case_filter = params.get("case_number", "").strip()
    status_filter = params.get("review_status", "PENDING_REVIEW").strip()
    series_filter = (params.get("series") or params.get("series_tag") or params.get("series_name") or "").strip()
    model_filter = (params.get("model") or params.get("model_name") or "").strip()

    where_clauses = ["cei.ai_match_score IS NOT NULL"]
    sql_params = []

    if case_filter and case_filter != "ALL":
        where_clauses.append("c.case_number = %s")
        sql_params.append(case_filter)

    if status_filter and status_filter != "ALL":
        where_clauses.append("cei.ai_review_status = %s")
        sql_params.append(status_filter)

    if series_filter and series_filter != "ALL":
        where_clauses.append("(cei.ai_suggested_series = %s OR cei.series_tag = %s OR ref_cei.series_tag = %s)")
        sql_params.extend([series_filter, series_filter, series_filter])

    if model_filter and model_filter != "ALL":
        where_clauses.append("cei.ai_model_name = %s")
        sql_params.append(model_filter)

    where_sql = " AND ".join(where_clauses)

    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT 
                    cei.evidence_id,
                    cei.case_id,
                    c.case_number,
                    cei.original_filename,
                    cei.series_tag,
                    cei.tags,
                    cei.custody_status,
                    cei.ai_suggested_series,
                    cei.ai_suggested_tags,
                    cei.ai_match_score,
                    cei.ai_review_status,
                    cei.ai_model_name,
                    cei.last_action_at,
                    ma.storage_rel_path,
                    ma.thumb_rel_path,
                    ma.sha256,
                    ma.file_size_bytes,
                    -- Matched Reference Evidence Item Details
                    ref_cei.evidence_id AS ref_evidence_id,
                    ref_cei.original_filename AS ref_filename,
                    ref_cei.series_tag AS ref_series_tag,
                    ref_cei.tags AS ref_tags,
                    ref_ma.storage_rel_path AS ref_storage_rel_path,
                    ref_ma.thumb_rel_path AS ref_thumb_rel_path
                FROM case_evidence_items cei
                LEFT JOIN cases c ON cei.case_id = c.case_id
                JOIN media_assets ma ON cei.asset_id = ma.asset_id
                LEFT JOIN case_evidence_items ref_cei ON cei.ai_match_evidence_id = ref_cei.evidence_id
                LEFT JOIN media_assets ref_ma ON ref_cei.asset_id = ref_ma.asset_id
                WHERE {where_sql}
                ORDER BY cei.ai_match_score DESC, cei.last_action_at DESC
                LIMIT 200;
            """, sql_params)
            rows = cur.fetchall()
            return {"success": True, "count": len(rows), "items": rows}
    finally:
        if should_close:
            conn.close()


def confirm_ai_triage(body, conn=None):
    """Analyst confirms an AI auto-tag match."""
    evidence_id = body.get("evidence_id")
    if not evidence_id:
        return {"success": False, "error": "evidence_id is required"}

    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE case_evidence_items
                SET ai_review_status = 'CONFIRMED',
                    custody_status = 'TRIAGED',
                    last_action = 'ai-tag-confirmed',
                    last_action_at = CURRENT_TIMESTAMP
                WHERE evidence_id = %s
                RETURNING original_filename, sha256_placeholder:
            """ if False else """
                UPDATE case_evidence_items cei
                SET series_tag = COALESCE(cei.series_tag, cei.ai_suggested_series),
                    tags = CASE WHEN cei.tags IS NULL OR array_length(cei.tags, 1) IS NULL OR array_length(cei.tags, 1) = 0 THEN cei.ai_suggested_tags ELSE cei.tags END,
                    ai_review_status = 'CONFIRMED',
                    custody_status = 'TRIAGED',
                    last_action = 'ai-tag-confirmed',
                    last_action_at = CURRENT_TIMESTAMP
                FROM media_assets ma
                WHERE cei.asset_id = ma.asset_id AND cei.evidence_id = %s
                RETURNING cei.original_filename, ma.sha256, cei.series_tag, cei.tags;
            """, (evidence_id,))
            row = cur.fetchone()
            if not row:
                return {"success": False, "error": "Evidence item not found"}

            tags_str = ", ".join(row["tags"]) if row.get("tags") else ""
            series_str = row.get("series_tag") or ""
            items_desc = []
            if series_str:
                items_desc.append(f"series: {series_str}")
            if tags_str:
                items_desc.append(f"tags: {tags_str}")
            new_val = "; ".join(items_desc) or "CONFIRMED"

            cur.execute("""
                INSERT INTO case_evidence_actions (
                    evidence_id, action_type, original_filename, sha256, previous_value, new_value, performed_by, details
                ) VALUES (
                    %s, 'ai-tag-confirmed', %s, %s, %s, %s, 'analyst', %s::jsonb
                );
            """, (evidence_id, row["original_filename"], row["sha256"], "", new_val, json.dumps({
                "series_tag": row["series_tag"],
                "tags": row["tags"],
                "action": "confirmed"
            })))
            conn.commit()
            return {"success": True, "evidence_id": evidence_id, "status": "CONFIRMED"}
    finally:
        if should_close:
            conn.close()


def reject_ai_triage(body, conn=None):
    """Analyst rejects an AI auto-tag match, clearing tags and marking rejected."""
    evidence_id = body.get("evidence_id")
    if not evidence_id:
        return {"success": False, "error": "evidence_id is required"}

    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            # Fetch previous state before clearing
            cur.execute("""
                SELECT cei.original_filename, ma.sha256, cei.series_tag, cei.tags
                FROM case_evidence_items cei
                JOIN media_assets ma ON cei.asset_id = ma.asset_id
                WHERE cei.evidence_id = %s;
            """, (evidence_id,))
            prev_row = cur.fetchone()
            if not prev_row:
                return {"success": False, "error": "Evidence item not found"}

            cur.execute("""
                UPDATE case_evidence_items
                SET series_tag = NULL,
                    tags = '{}'::text[],
                    ai_review_status = 'REJECTED',
                    custody_status = 'INGESTED',
                    last_action = 'ai-tag-rejected',
                    last_action_at = CURRENT_TIMESTAMP
                WHERE evidence_id = %s;
            """, (evidence_id,))

            prev_tags_str = ", ".join(prev_row["tags"]) if prev_row.get("tags") else ""
            prev_series_str = prev_row.get("series_tag") or ""
            items_desc = []
            if prev_series_str:
                items_desc.append(f"series: {prev_series_str}")
            if prev_tags_str:
                items_desc.append(f"tags: {prev_tags_str}")
            prev_val = "; ".join(items_desc) or "REJECTED"

            cur.execute("""
                INSERT INTO case_evidence_actions (
                    evidence_id, action_type, original_filename, sha256, previous_value, new_value, performed_by, details
                ) VALUES (
                    %s, 'ai-tag-rejected', %s, %s, %s, %s, 'analyst', %s::jsonb
                );
            """, (evidence_id, prev_row["original_filename"], prev_row["sha256"], prev_val, "CLEARED", json.dumps({
                "cleared_series": prev_row.get("series_tag"),
                "cleared_tags": prev_row.get("tags"),
                "reason": "analyst_rejected"
            })))
            conn.commit()
            return {"success": True, "evidence_id": evidence_id, "status": "REJECTED"}
    finally:
        if should_close:
            conn.close()


def run_ai_autotagger_batch(body, conn=None):
    """
    Runs the AI Visual Auto-Classifier across all untagged items at a given threshold.
    Matches untagged media assets against all labeled reference items (or a targeted series).
    """
    model_name = (body.get("model") or body.get("model_name") or "siglip2_naflex").lower().strip()
    if model_name not in ("siglip2_naflex", "siglip", "clip", "dinov3"):
        model_name = "siglip2_naflex"

    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            # 1. Fetch reference exemplar vectors
            ref_filter = "target_cei.series_tag IS NOT NULL OR (target_cei.tags IS NOT NULL AND array_length(target_cei.tags, 1) > 0)"
            ref_params = [model_name]
            if target_series and target_series != "ALL":
                ref_filter = "target_cei.series_tag = %s"
                ref_params.append(target_series)

            cur.execute(f"""
                SELECT DISTINCT ON (target_cei.evidence_id)
                    target_cei.evidence_id,
                    target_cei.series_tag,
                    target_cei.tags,
                    target_cei.original_filename,
                    me_target.embedding_l2
                FROM case_evidence_items target_cei
                JOIN media_embeddings me_target ON target_cei.asset_id = me_target.asset_id
                WHERE me_target.model_name = %s
                  AND ({ref_filter});
            """, ref_params)
            reference_items = cur.fetchall()

            if not reference_items:
                return {"success": False, "error": f"No tagged reference exemplars found for model '{model_name}' to compare against."}

            # Ensure default active case exists for enrolling new assets
            cur.execute("SELECT case_id FROM cases WHERE status = 'ACTIVE' ORDER BY created_at DESC LIMIT 1;")
            c_row = cur.fetchone()
            if not c_row:
                cur.execute("SELECT case_id FROM cases ORDER BY created_at DESC LIMIT 1;")
                c_row = cur.fetchone()
            default_case_id = c_row["case_id"] if c_row else None

            # 2. For each reference exemplar, find top matching unclassified media assets
            auto_tagged_count = 0
            scanned_total = 0

            cur.execute("SELECT COUNT(*) as cnt FROM media_assets;")
            scanned_total = cur.fetchone()["cnt"]

            for ref in reference_items:
                ref_vec = ref["embedding_l2"]
                ref_ev_id = ref["evidence_id"]
                ref_series = ref["series_tag"]
                ref_tags = ref["tags"] or []

                # Find all media_assets with similarity >= threshold
                cur.execute("""
                    SELECT ma.asset_id, ma.storage_rel_path,
                           COALESCE(split_part(ma.storage_rel_path, '/', -1), 'evidence_item') AS original_filename,
                           1 - (me.embedding_l2 <=> %s::vector) AS similarity_score,
                           cei.evidence_id, cei.series_tag, cei.ai_review_status
                    FROM media_assets ma
                    JOIN media_embeddings me ON ma.asset_id = me.asset_id
                    LEFT JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id
                    WHERE me.model_name = %s
                      AND (cei.evidence_id IS NULL OR cei.evidence_id != %s)
                      AND (cei.series_tag IS NULL OR cei.series_tag = '')
                      AND (cei.ai_review_status IS NULL OR cei.ai_review_status IN ('NONE', 'PENDING_REVIEW'))
                      AND (1 - (me.embedding_l2 <=> %s::vector)) >= %s
                    ORDER BY similarity_score DESC
                    LIMIT 50;
                """, (ref_vec, model_name, ref_ev_id, ref_vec, threshold))
                candidates = cur.fetchall()

                for cand in candidates:
                    sim = float(cand["similarity_score"])
                    ev_id = cand["evidence_id"]

                    if not ev_id:
                        # Insert into case_evidence_items as unconfirmed suggestion
                        cur.execute("""
                            INSERT INTO case_evidence_items (
                                case_id, asset_id, original_filepath, original_filename,
                                series_tag, tags, custody_status,
                                ai_suggested_series, ai_suggested_tags, ai_match_score,
                                ai_match_evidence_id, ai_review_status, ai_model_name, last_action, last_action_at
                            ) VALUES (
                                NULL, %s, %s, %s,
                                NULL, '{}'::text[], 'INGESTED',
                                %s, %s, %s,
                                %s, 'PENDING_REVIEW', %s, 'ai-auto-tagged', CURRENT_TIMESTAMP
                            )
                            RETURNING evidence_id;
                        """, (
                            cand["asset_id"], cand["storage_rel_path"], cand["original_filename"],
                            ref_series, ref_tags, sim,
                            ref_ev_id, model_name
                        ))
                        auto_tagged_count += 1
                    elif ev_id:
                        cur.execute("""
                            UPDATE case_evidence_items
                            SET ai_suggested_series = %s,
                                ai_suggested_tags = %s,
                                ai_match_score = %s,
                                ai_match_evidence_id = %s,
                                ai_review_status = 'PENDING_REVIEW',
                                ai_model_name = %s,
                                last_action = 'ai-auto-tagged',
                                last_action_at = CURRENT_TIMESTAMP
                            WHERE evidence_id = %s;
                        """, (
                            ref_series, ref_tags, sim, ref_ev_id, model_name,
                            ev_id
                        ))
                        auto_tagged_count += 1

            conn.commit()
            return {
                "success": True,
                "scanned_count": scanned_total,
                "auto_tagged_count": auto_tagged_count,
                "reference_count": len(reference_items)
            }
    finally:
        if should_close:
            conn.close()


def delete_case(body, conn=None):
    """Soft-deletes / archives a case workspace container. Retains all metadata, links, and audit history."""
    case_number = body.get("case_number")
    if not case_number:
        return {"success": False, "error": "case_number is required"}

    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE cases 
                SET status = 'INACTIVE', deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE case_number = %s
                RETURNING case_id;
            """, (case_number,))
            row = cur.fetchone()
            if not row:
                return {"success": False, "error": f"Case '{case_number}' not found"}
            conn.commit()
            return {"success": True, "deleted_case": case_number, "archived": True}
    finally:
        if should_close:
            conn.close()


def export_case_workspace(case_number, conn=None):
    """Exports full case metadata, evidence items, and audit log."""
    if not case_number:
        return {"success": False, "error": "case_number is required"}

    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM cases WHERE case_number = %s;", (case_number,))
            case_info = cur.fetchone()
            if not case_info:
                return {"success": False, "error": f"Case '{case_number}' not found"}

            c_dict = dict(case_info)
            if c_dict.get("created_at"):
                c_dict["created_at"] = str(c_dict["created_at"])
            if c_dict.get("case_id"):
                c_dict["case_id"] = str(c_dict["case_id"])

            cur.execute("""
                SELECT 
                    cei.evidence_id, cei.original_filename, cei.original_filepath,
                    cei.series_tag, cei.tags, cei.custody_status, cei.analyst_notes,
                    cei.ai_match_score, cei.ai_review_status, cei.last_action, cei.last_action_at,
                    ma.sha256, ma.md5, ma.sha1, ma.file_size_bytes, ma.media_type,
                    ma.width_pixels, ma.height_pixels, ma.duration_seconds
                FROM case_evidence_items cei
                JOIN media_assets ma ON cei.asset_id = ma.asset_id
                WHERE cei.case_id = %s
                ORDER BY cei.created_at ASC;
            """, (c_dict["case_id"],))
            items = [dict(r) for r in cur.fetchall()]
            for item in items:
                for k in ("evidence_id", "last_action_at"):
                    if item.get(k):
                        item[k] = str(item[k])

            return {
                "success": True,
                "version": "1.0",
                "exported_at": datetime.utcnow().isoformat() + "Z",
                "case": c_dict,
                "evidence_count": len(items),
                "evidence": items
            }
    finally:
        if should_close:
            conn.close()


def import_known_hash_set(body, conn=None):
    """
    Imports known hashes (.txt, .csv, or .json) into known_hash_sets table.
    """
    raw_content = body.get("raw_content", "")
    hashes_list = body.get("hashes", [])
    series_name = body.get("series_name", "Imported Hash Set")
    source_file = body.get("source_file", "manual_import.txt")
    category = body.get("category", "KNOWN_MATCH")

    entries = []
    if raw_content:
        lines = raw_content.strip().splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",") if p.strip()]
            h_val = parts[0].lower()
            s_name = parts[1] if len(parts) > 1 else series_name

            if len(h_val) == 64:
                entries.append((h_val, "SHA256", s_name, source_file, category))
            elif len(h_val) == 32:
                entries.append((h_val, "MD5", s_name, source_file, category))
            elif len(h_val) == 40:
                entries.append((h_val, "SHA1", s_name, source_file, category))

    if hashes_list:
        for item in hashes_list:
            if isinstance(item, str):
                h_val = item.strip().lower()
                s_name = series_name
            elif isinstance(item, dict):
                h_val = (item.get("hash") or item.get("hash_value") or item.get("sha256") or item.get("md5") or item.get("sha1") or "").strip().lower()
                s_name = item.get("series_name") or series_name
            else:
                continue

            if len(h_val) == 64:
                entries.append((h_val, "SHA256", s_name, source_file, category))
            elif len(h_val) == 32:
                entries.append((h_val, "MD5", s_name, source_file, category))
            elif len(h_val) == 40:
                entries.append((h_val, "SHA1", s_name, source_file, category))

    if not entries:
        return {"success": False, "error": "No valid MD5, SHA-1, or SHA-256 hashes found in input"}

    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            inserted = 0
            for h_val, h_type, s_name, src, cat in entries:
                cur.execute("""
                    INSERT INTO known_hash_sets (hash_value, hash_type, series_name, source_file, category)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (hash_value, hash_type) DO UPDATE 
                    SET series_name = COALESCE(EXCLUDED.series_name, known_hash_sets.series_name);
                """, (h_val, h_type, s_name, src, cat))
                inserted += 1
            conn.commit()
            return {"success": True, "imported_count": inserted, "total_parsed": len(entries)}
    finally:
        if should_close:
            conn.close()


def import_reference_targets(body, conn=None):
    """
    Ingests reference images or catalogs from a folder into the Known Reference Set.
    """
    folder_path = body.get("folder_path")
    series_name = body.get("series_name", "Known Reference Series")
    case_number = body.get("case_number")

    if not folder_path or not os.path.exists(folder_path):
        return {"success": False, "error": f"Folder path '{folder_path}' does not exist"}

    from pathlib import Path
    import hashlib
    from PIL import Image
    import shutil

    valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    files = [f for f in Path(folder_path).rglob("*") if f.suffix.lower() in valid_exts]

    if not files:
        return {"success": False, "error": f"No supported image files found in '{folder_path}'"}

    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        from embedder_service import get_embedder
        embedder = get_embedder()
        vault_root = VAULT_ROOT

        imported_count = 0
        with conn.cursor() as cur:
            case_name_target = case_number or "REFERENCE-LIBRARY"
            cur.execute("SELECT case_id FROM cases WHERE case_number = %s;", (case_name_target,))
            c_row = cur.fetchone()
            if c_row:
                case_id = c_row["case_id"]
            else:
                cur.execute("INSERT INTO cases (case_number, case_name, classification_type, case_notes) VALUES (%s, %s, 'MEDIA_EVIDENCE', 'Known reference targets library') RETURNING case_id;", (case_name_target, f"Library: {case_name_target}"))
                case_id = cur.fetchone()["case_id"]

            for f_path in files:
                abs_f = str(f_path)
                with open(abs_f, "rb") as f:
                    content = f.read()
                sha256 = hashlib.sha256(content).hexdigest()
                md5 = hashlib.md5(content).hexdigest()
                sha1 = hashlib.sha1(content).hexdigest()
                f_size = len(content)

                prefix1, prefix2 = sha256[0:2], sha256[2:4]
                ext = f_path.suffix.lower()
                rel_vault = f"01_Media_Vault/images/{prefix1}/{prefix2}/{sha256}{ext}"
                abs_vault = os.path.join(vault_root, rel_vault)
                rel_thumb = f"02_Keyframe_Vault/thumbs_256px/{prefix1}/{prefix2}/{sha256}.webp"
                abs_thumb = os.path.join(vault_root, rel_thumb)

                os.makedirs(os.path.dirname(abs_vault), exist_ok=True)
                os.makedirs(os.path.dirname(abs_thumb), exist_ok=True)

                if not os.path.exists(abs_vault):
                    shutil.copyfile(abs_f, abs_vault)

                if not os.path.exists(abs_thumb):
                    with Image.open(abs_vault) as img:
                        if img.mode in ("RGBA", "LA", "P"):
                            img = img.convert("RGB")
                        img.thumbnail((256, 256), Image.Resampling.LANCZOS)
                        img.save(abs_thumb, "WEBP", quality=85)

                embs = embedder.compute_all_embeddings(abs_vault)

                cur.execute("""
                    INSERT INTO media_assets (
                        sha256, md5, sha1, file_size_bytes, media_type, mime_type,
                        storage_rel_path, storage_abs_path, thumb_rel_path
                    ) VALUES (%s, %s, %s, %s, 'IMAGE', 'image/jpeg', %s, %s, %s)
                    ON CONFLICT (sha256) DO UPDATE SET storage_rel_path = EXCLUDED.storage_rel_path
                    RETURNING asset_id;
                """, (sha256, md5, sha1, f_size, rel_vault, abs_vault, rel_thumb))
                asset_id = cur.fetchone()["asset_id"]

                for m_name, dim, ver in [("clip", 512, "vit-b-32"), ("siglip", 768, "base-patch16-224"), ("siglip2_naflex", 768, "base-patch16-naflex")]:
                    if m_name in embs and embs[m_name]:
                        cur.execute(f"""
                            INSERT INTO media_embeddings (asset_id, model_name, model_version, dimension_size, embedding_l2)
                            VALUES (%s, '{m_name}', '{ver}', {dim}, %s)
                            ON CONFLICT (asset_id, model_name) DO UPDATE SET embedding_l2 = EXCLUDED.embedding_l2;
                        """, (asset_id, embs[m_name]))

                cur.execute("""
                    INSERT INTO case_evidence_items (
                        case_id, asset_id, original_filepath, original_filename,
                        series_tag, custody_status, last_action
                    ) VALUES (%s, %s, %s, %s, %s, 'KNOWN_REFERENCE', 'create-reference-series')
                    ON CONFLICT (case_id, original_filepath) DO UPDATE
                    SET series_tag = EXCLUDED.series_tag, custody_status = 'KNOWN_REFERENCE';
                """, (case_id, asset_id, abs_f, f_path.name, series_name))
                imported_count += 1

            conn.commit()
            return {"success": True, "imported_count": imported_count, "series_name": series_name}
    finally:
        if should_close:
            conn.close()


def audit_dependencies():
    """
    Performs full system dependency audit:
    Inspects PyTorch, Vision Encoders, HuggingFace models, OpenCV, Database Drivers,
    GPU/CUDA hardware acceleration, and pgvector extension status.
    """
    import platform
    import sys
    import importlib

    deps_manifest = [
        {"name": "torch", "import_name": "torch", "desc": "PyTorch Deep Learning & AI Vision Tensor Runtime", "category": "AI Framework", "min_ver": "2.0.0"},
        {"name": "transformers", "import_name": "transformers", "desc": "HuggingFace SigLIP, SigLIP-2 & CLIP Vision-Language Models", "category": "AI Models", "min_ver": "4.45.0"},
        {"name": "huggingface_hub", "import_name": "huggingface_hub", "desc": "HuggingFace Model Hub Client & Weights Downloader", "category": "AI Models", "min_ver": "0.20.0"},
        {"name": "opencv-python", "import_name": "cv2", "desc": "OpenCV Video Keyframe & Computer Vision Engine", "category": "Vision / Video", "min_ver": "4.7.0"},
        {"name": "pillow", "import_name": "PIL", "desc": "Pillow Image Transform & EXIF Processing Engine", "category": "Vision / Image", "min_ver": "9.0.0"},
        {"name": "numpy", "import_name": "numpy", "desc": "Dense Matrix & High-Performance Array Engine", "category": "Math / Arrays", "min_ver": "1.24.0"},
        {"name": "scipy", "import_name": "scipy", "desc": "Scientific Computing & Cosine Distance Algorithms", "category": "Math / Arrays", "min_ver": "1.10.0"},
        {"name": "psycopg2", "import_name": "psycopg2", "desc": "PostgreSQL 16 High-Speed Relational Driver", "category": "Database Driver", "min_ver": "2.9.0"},
        {"name": "pgvector", "import_name": "pgvector", "desc": "PostgreSQL HNSW Vector Search Extension Integration", "category": "Database Driver", "min_ver": "0.2.0"},
        {"name": "timm", "import_name": "timm", "desc": "PyTorch Image Models (Optional for experimental architectures)", "category": "AI Framework", "min_ver": "1.0.0"},
        {"name": "torchvision", "import_name": "torchvision", "desc": "PyTorch Computer Vision Models & Utilities", "category": "AI Framework", "min_ver": "0.15.0"},
        {"name": "accelerate", "import_name": "accelerate", "desc": "HuggingFace Accelerate Hardware Dispatcher", "category": "AI Framework", "min_ver": "0.26.0"},
    ]

    results = []
    healthy_count = 0
    missing_count = 0

    for dep in deps_manifest:
        try:
            mod = importlib.import_module(dep["import_name"])
            ver = getattr(mod, "__version__", "Installed")
            results.append({
                "name": dep["name"],
                "import_name": dep["import_name"],
                "description": dep["desc"],
                "category": dep["category"],
                "installed": True,
                "version": str(ver),
                "min_version": dep["min_ver"],
                "status": "HEALTHY"
            })
            healthy_count += 1
        except Exception as e:
            is_critical = dep["name"] in ("torch", "transformers", "opencv-python", "pillow", "numpy", "psycopg2", "pgvector")
            results.append({
                "name": dep["name"],
                "import_name": dep["import_name"],
                "description": dep["desc"],
                "category": dep["category"],
                "installed": False,
                "version": "Not Found",
                "min_version": dep["min_ver"],
                "status": "MISSING" if is_critical else "OPTIONAL",
                "error": str(e)
            })
            if is_critical:
                missing_count += 1

    # Hardware & PyTorch Engine Telemetry
    cuda_available = False
    cuda_device_name = "CPU (Software Mode)"
    cuda_device_count = 0
    torch_version = "Unknown"
    try:
        import torch
        torch_version = torch.__version__
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            cuda_device_count = torch.cuda.device_count()
            cuda_device_name = f"{torch.cuda.get_device_name(0)} ({cuda_device_count} GPU{'s' if cuda_device_count > 1 else ''})"
    except Exception:
        pass

    # pgvector database check
    pgvector_db_status = "UNKNOWN"
    try:
        conn = db.get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
            row = cur.fetchone()
            if row:
                pgvector_db_status = f"Active (pgvector v{row['extversion']})"
        conn.close()
    except Exception as e:
        pgvector_db_status = f"Error: {e}"

    return {
        "success": True,
        "environment": {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "torch_version": torch_version,
            "cuda_available": cuda_available,
            "cuda_device_name": cuda_device_name,
            "cuda_device_count": cuda_device_count,
            "pgvector_db_status": pgvector_db_status
        },
        "total_packages": len(deps_manifest),
        "healthy_count": healthy_count,
        "critical_missing_count": missing_count,
        "packages": results
    }


def get_reference_set_items(params, conn=None):
    """
    Fetches all reference exemplar items belonging to a given series.
    """
    series_name = (params.get("series") or params.get("series_name") or params.get("series_tag") or "").strip()
    if not series_name:
        return {"success": False, "error": "series parameter is required"}

    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    cei.evidence_id,
                    cei.asset_id,
                    cei.original_filename,
                    cei.series_tag,
                    cei.tags,
                    cei.custody_status,
                    ma.storage_rel_path,
                    ma.thumb_rel_path,
                    ma.sha256,
                    ma.file_size_bytes,
                    ma.media_type,
                    cei.created_at
                FROM case_evidence_items cei
                JOIN media_assets ma ON cei.asset_id = ma.asset_id
                WHERE cei.series_tag = %s
                ORDER BY cei.created_at ASC, cei.original_filename ASC;
            """, (series_name,))
            items = cur.fetchall()
            return {
                "success": True,
                "series_name": series_name,
                "count": len(items),
                "items": items
            }
    finally:
        if should_close:
            conn.close()


def match_reference_set_nearest_neighbors(body, conn=None):
    """
    Computes nearest neighbors across ALL media holdings against a set of selected reference exemplars.
    Uses Max-Similarity pooling over the ensemble of reference vectors.
    Returns up to `limit` (default 1000) nearest neighbors.
    """
    series_name = (body.get("series_name") or body.get("series") or body.get("series_tag") or "").strip()
    selected_evidence_ids = body.get("selected_evidence_ids") or []
    model_name = (body.get("model") or body.get("model_name") or "siglip2_naflex").lower().strip()
    if model_name not in ("siglip2_naflex", "siglip", "clip", "dinov3"):
        model_name = "siglip2_naflex"

    limit = min(int(body.get("limit", 250)), 2000)
    threshold = float(body.get("threshold", 0.0))

    should_close = False
    if conn is None:
        conn = db.get_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            # 1. Resolve reference vectors
            ref_where = ["me.model_name = %s"]
            ref_params = [model_name]

            if selected_evidence_ids:
                ref_where.append("cei.evidence_id = ANY(%s::uuid[])")
                ref_params.append(selected_evidence_ids)
            elif series_name and series_name != "ALL":
                ref_where.append("cei.series_tag = %s")
                ref_params.append(series_name)
            else:
                ref_where.append("cei.series_tag IS NOT NULL")

            ref_where_sql = " AND ".join(ref_where)

            cur.execute(f"""
                SELECT cei.evidence_id AS ref_evidence_id,
                       cei.original_filename AS ref_filename,
                       cei.series_tag AS ref_series_tag,
                       ma_ref.storage_rel_path AS ref_storage_rel_path,
                       ma_ref.thumb_rel_path AS ref_thumb_rel_path,
                       me.embedding_l2 AS ref_vec
                FROM case_evidence_items cei
                JOIN media_assets ma_ref ON cei.asset_id = ma_ref.asset_id
                JOIN media_embeddings me ON cei.asset_id = me.asset_id
                WHERE {ref_where_sql};
            """, ref_params)
            ref_exemplars = cur.fetchall()

            if not ref_exemplars:
                return {
                    "success": False,
                    "error": f"No vector embeddings found for the selected reference items using model '{model_name}'."
                }

            ref_ids = [str(r["ref_evidence_id"]) for r in ref_exemplars]

            # 2. Multi-Vector Nearest Neighbor Query with HNSW acceleration
            cur.execute(f"""
                WITH ref_vectors AS (
                    SELECT cei.evidence_id AS ref_evidence_id,
                           cei.original_filename AS ref_filename,
                           cei.series_tag AS ref_series_tag,
                           ma_ref.storage_rel_path AS ref_storage_rel_path,
                           ma_ref.thumb_rel_path AS ref_thumb_rel_path,
                           me.embedding_l2 AS ref_vec
                    FROM case_evidence_items cei
                    JOIN media_assets ma_ref ON cei.asset_id = ma_ref.asset_id
                    JOIN media_embeddings me ON cei.asset_id = me.asset_id
                    WHERE cei.evidence_id = ANY(%s::uuid[])
                      AND me.model_name = %s
                ),
                top_matches_per_ref AS (
                    SELECT rv.ref_evidence_id,
                           rv.ref_filename,
                           rv.ref_series_tag,
                           rv.ref_storage_rel_path,
                           rv.ref_thumb_rel_path,
                           m.asset_id,
                           (1 - (m.embedding_l2 <=> rv.ref_vec)) AS similarity
                    FROM ref_vectors rv
                    CROSS JOIN LATERAL (
                        SELECT me.asset_id, me.embedding_l2
                        FROM media_embeddings me
                        WHERE me.model_name = %s
                        ORDER BY me.embedding_l2 <=> rv.ref_vec
                        LIMIT %s
                    ) m
                ),
                ranked_assets AS (
                    SELECT DISTINCT ON (asset_id)
                        asset_id,
                        ref_evidence_id,
                        ref_filename,
                        ref_series_tag,
                        ref_storage_rel_path,
                        ref_thumb_rel_path,
                        similarity
                    FROM top_matches_per_ref
                    WHERE similarity >= %s
                    ORDER BY asset_id, similarity DESC
                )
                SELECT 
                    ra.asset_id,
                    ra.similarity,
                    ra.ref_evidence_id,
                    ra.ref_filename,
                    ra.ref_series_tag,
                    ra.ref_storage_rel_path,
                    ra.ref_thumb_rel_path,
                    ma.sha256,
                    ma.storage_rel_path,
                    ma.thumb_rel_path,
                    ma.file_size_bytes,
                    ma.media_type,
                    cei.evidence_id,
                    COALESCE(cei.original_filename, split_part(ma.storage_rel_path, '/', -1)) AS original_filename,
                    cei.series_tag,
                    cei.tags,
                    cei.custody_status,
                    cei.ai_review_status
                FROM ranked_assets ra
                JOIN media_assets ma ON ra.asset_id = ma.asset_id
                LEFT JOIN case_evidence_items cei ON ra.asset_id = cei.asset_id
                ORDER BY ra.similarity DESC
                LIMIT %s;
            """, (ref_ids, model_name, model_name, limit, threshold, limit))

            rows = cur.fetchall()

            return {
                "success": True,
                "series_name": series_name,
                "model": model_name,
                "reference_count": len(ref_exemplars),
                "results_count": len(rows),
                "limit": limit,
                "items": rows
            }
    finally:
        if should_close:
            conn.close()


