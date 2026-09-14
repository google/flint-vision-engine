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
Telemetry & System Health Controller
====================================
Gathers storage metrics, database connection health, queue depths, and ERD stats.
"""

import os
import shutil
from typing import Dict, Any
import db


class TelemetryController:

    def get_telemetry_status(self, vault_root: str, staging_dir: str, conn=None) -> Dict[str, Any]:
        should_close = False
        if conn is None:
            conn = db.get_connection()
            should_close = True

        try:
            # Disk space
            disk_usage = shutil.disk_usage(vault_root) if os.path.exists(vault_root) else shutil.disk_usage("/")
            free_gb = disk_usage.free / (1024 ** 3)
            total_gb = disk_usage.total / (1024 ** 3)

            # Database stats
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) as count FROM media_assets;")
                total_assets = cur.fetchone()["count"]

                cur.execute("SELECT count(*) as count FROM media_embeddings;")
                total_embeddings = cur.fetchone()["count"]

                cur.execute("SELECT count(*) as count FROM cases;")
                total_cases = cur.fetchone()["count"]

                cur.execute("SELECT count(*) as count FROM migration_manifest WHERE status = 'PENDING';")
                pending_manifest = cur.fetchone()["count"]

            # Staging count
            staging_count = 0
            if os.path.exists(staging_dir):
                for _, _, files in os.walk(staging_dir):
                    staging_count += len(files)

            return {
                "success": True,
                "disk": {
                    "free_gb": round(free_gb, 2),
                    "total_gb": round(total_gb, 2),
                    "percent_free": round((free_gb / total_gb) * 100, 1) if total_gb > 0 else 0
                },
                "counts": {
                    "total_assets": total_assets,
                    "total_embeddings": total_embeddings,
                    "total_cases": total_cases,
                    "pending_manifest": pending_manifest,
                    "staging_files": staging_count
                }
            }
        finally:
            if should_close:
                conn.close()

    def get_erd_stats(self, conn=None) -> Dict[str, Any]:
        should_close = False
        if conn is None:
            conn = db.get_connection()
            should_close = True

        try:
            with conn.cursor() as cur:
                stats = {}
                tables = ["cases", "media_assets", "media_embeddings", "case_evidence_items", "migration_manifest"]
                for t in tables:
                    try:
                        cur.execute(f"SELECT count(*) as count FROM {t};")
                        stats[t] = cur.fetchone()["count"]
                    except Exception:
                        stats[t] = 0
                return {"success": True, "stats": stats}
        finally:
            if should_close:
                conn.close()


telemetry_controller = TelemetryController()
