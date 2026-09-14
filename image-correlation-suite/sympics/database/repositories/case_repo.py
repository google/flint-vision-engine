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
Case & Evidence Relationship Repository
=======================================
Handles cases, case_evidence_items, series tags, and chain-of-custody logging.
"""

from typing import Optional, List, Dict, Any
from sympics.database.repositories.base import BaseRepository


class CaseRepository(BaseRepository):

    def get_or_create_case(self, case_number: str, title: Optional[str] = None, conn=None) -> Optional[str]:
        c, should_close = self.get_connection(conn)
        try:
            with c.cursor() as cur:
                cur.execute("""
                    INSERT INTO cases (case_number, title)
                    VALUES (%s, %s)
                    ON CONFLICT (case_number) DO UPDATE SET
                        title = COALESCE(EXCLUDED.title, cases.title)
                    RETURNING case_id;
                """, (case_number, title or f"Case {case_number}"))
                row = cur.fetchone()
                if not conn:
                    c.commit()
                return row["case_id"] if row else None
        finally:
            if should_close:
                c.close()

    def link_evidence_item(self, case_id: str, asset_id: str, original_filepath: str, original_filename: str, source_parent_dir: str = "", custody_status: str = "INGESTED", last_action: str = "ingested", conn=None) -> Optional[str]:
        c, should_close = self.get_connection(conn)
        try:
            with c.cursor() as cur:
                cur.execute("""
                    INSERT INTO case_evidence_items (
                        case_id, asset_id, original_filepath, original_filename,
                        source_parent_dir, custody_status, last_action
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (case_id, asset_id) DO UPDATE SET
                        original_filepath = EXCLUDED.original_filepath,
                        source_parent_dir = EXCLUDED.source_parent_dir,
                        custody_status = EXCLUDED.custody_status,
                        last_action = EXCLUDED.last_action,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING item_id;
                """, (case_id, asset_id, original_filepath, original_filename, source_parent_dir, custody_status, last_action))
                row = cur.fetchone()
                if not conn:
                    c.commit()
                return row["item_id"] if row else None
        finally:
            if should_close:
                c.close()
