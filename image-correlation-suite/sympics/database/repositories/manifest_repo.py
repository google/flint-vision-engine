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
Migration Manifest Repository
=============================
Handles Phase 1 discovery cataloging and atomic SKIP LOCKED batch queue distribution.
"""

from typing import Optional, List, Dict, Any
from psycopg2.extras import execute_values
from sympics.database.repositories.base import BaseRepository


class ManifestRepository(BaseRepository):

    def batch_add_records(self, records_list: List[Dict[str, Any]], conn=None) -> int:
        if not records_list:
            return 0
        c, should_close = self.get_connection(conn)
        try:
            insert_tuples = [
                (
                    r["source_path"], r["filename"], r.get("extension", ""),
                    r.get("size_bytes", 0), r.get("sha256", ""), r.get("md5", ""), r.get("sha1", ""),
                    r.get("status", "PENDING"), r.get("is_archive_entry", False),
                    r.get("archive_path", None), r.get("inner_archive_path", None),
                    r.get("error_message", None)
                ) for r in records_list
            ]
            with c.cursor() as cur:
                execute_values(cur, """
                    INSERT INTO migration_manifest (
                        source_path, filename, extension, size_bytes,
                        sha256, md5, sha1, status, is_archive_entry,
                        archive_path, inner_archive_path, error_message
                    ) VALUES %s
                    ON CONFLICT (source_path) DO UPDATE SET
                        sha256 = EXCLUDED.sha256,
                        md5 = EXCLUDED.md5,
                        sha1 = EXCLUDED.sha1,
                        size_bytes = EXCLUDED.size_bytes,
                        status = CASE WHEN migration_manifest.status = 'VERIFIED_COPIED' THEN 'VERIFIED_COPIED' ELSE EXCLUDED.status END;
                """, insert_tuples, page_size=500)
                count = cur.rowcount
                if not conn:
                    c.commit()
                return count
        finally:
            if should_close:
                c.close()

    def checkout_batch(self, batch_size: int = 32, worker_id: Optional[str] = None, conn=None) -> List[Dict[str, Any]]:
        """Atomically checks out a batch of PENDING records using FOR UPDATE SKIP LOCKED."""
        c, should_close = self.get_connection(conn)
        try:
            with c.cursor() as cur:
                cur.execute("""
                    WITH batch_candidates AS (
                        SELECT manifest_id
                        FROM migration_manifest
                        WHERE status = 'PENDING'
                        ORDER BY manifest_id ASC
                        LIMIT %s
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE migration_manifest
                    SET 
                        status = 'SCANNING',
                        worker_id = %s,
                        claimed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    FROM batch_candidates
                    WHERE migration_manifest.manifest_id = batch_candidates.manifest_id
                    RETURNING migration_manifest.*;
                """, (batch_size, worker_id))
                batch = cur.fetchall()
                if not conn:
                    c.commit()
                return batch
        finally:
            if should_close:
                c.close()

    def reset_stale_scanning(self, worker_id: Optional[str] = None, conn=None) -> int:
        """Resets in-flight SCANNING records back to PENDING."""
        c, should_close = self.get_connection(conn)
        try:
            with c.cursor() as cur:
                if worker_id:
                    cur.execute("""
                        UPDATE migration_manifest
                        SET status = 'PENDING', worker_id = NULL, claimed_at = NULL, updated_at = CURRENT_TIMESTAMP
                        WHERE status = 'SCANNING' AND worker_id = %s;
                    """, (worker_id,))
                else:
                    cur.execute("""
                        UPDATE migration_manifest
                        SET status = 'PENDING', worker_id = NULL, claimed_at = NULL, updated_at = CURRENT_TIMESTAMP
                        WHERE status = 'SCANNING';
                    """)
                count = cur.rowcount
                if not conn:
                    c.commit()
                return count
        finally:
            if should_close:
                c.close()

    def get_pending_count(self, conn=None) -> int:
        c, should_close = self.get_connection(conn)
        try:
            with c.cursor() as cur:
                cur.execute("SELECT count(*) as count FROM migration_manifest WHERE status = 'PENDING';")
                row = cur.fetchone()
                return row["count"] if row else 0
        finally:
            if should_close:
                c.close()

    def update_verification(self, manifest_id: int, dest_abs: str, dest_rel: str, status: str = "VERIFIED_COPIED", error_msg: Optional[str] = None, conn=None) -> bool:
        c, should_close = self.get_connection(conn)
        try:
            with c.cursor() as cur:
                cur.execute("""
                    UPDATE migration_manifest
                    SET 
                        status = %s,
                        destination_abs_path = %s,
                        destination_rel_path = %s,
                        error_message = %s,
                        verified_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE manifest_id = %s;
                """, (status, dest_abs, dest_rel, error_msg, manifest_id))
                if not conn:
                    c.commit()
                return True
        finally:
            if should_close:
                c.close()
