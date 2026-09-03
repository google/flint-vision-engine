# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
Media Asset Repository
======================
Handles CRUD operations and duplicate checks for media_assets table.
"""

import json
from typing import Optional, Dict, Any, List
from sympics.database.repositories.base import BaseRepository


class MediaAssetRepository(BaseRepository):

    def add_asset(self, asset_dict: Dict[str, Any], conn=None) -> Optional[str]:
        """Inserts or updates a physical media asset. Returns asset_id."""
        c, should_close = self.get_connection(conn)
        try:
            with c.cursor() as cur:
                cur.execute("""
                    INSERT INTO media_assets (
                        sha256, md5, sha1, file_size_bytes, mime_type, media_type,
                        storage_rel_path, storage_abs_path, thumb_rel_path,
                        source_rel_path, source_folder,
                        width_pixels, height_pixels, duration_seconds, frame_rate,
                        gps_latitude, gps_longitude, gps_altitude,
                        exif_data, is_corrupt
                    ) VALUES (
                        %(sha256)s, %(md5)s, %(sha1)s, %(file_size_bytes)s, %(mime_type)s, %(media_type)s,
                        %(storage_rel_path)s, %(storage_abs_path)s, %(thumb_rel_path)s,
                        %(source_rel_path)s, %(source_folder)s,
                        %(width_pixels)s, %(height_pixels)s, %(duration_seconds)s, %(frame_rate)s,
                        %(gps_latitude)s, %(gps_longitude)s, %(gps_altitude)s,
                        %(exif_data)s::jsonb, %(is_corrupt)s
                    )
                    ON CONFLICT (sha256) DO UPDATE SET
                        storage_rel_path = EXCLUDED.storage_rel_path,
                        storage_abs_path = EXCLUDED.storage_abs_path,
                        thumb_rel_path = COALESCE(EXCLUDED.thumb_rel_path, media_assets.thumb_rel_path),
                        source_rel_path = COALESCE(EXCLUDED.source_rel_path, media_assets.source_rel_path),
                        source_folder = COALESCE(EXCLUDED.source_folder, media_assets.source_folder)
                    RETURNING asset_id;
                """, {
                    "sha256": asset_dict["sha256"].lower().strip(),
                    "md5": asset_dict.get("md5"),
                    "sha1": asset_dict.get("sha1"),
                    "file_size_bytes": asset_dict.get("file_size_bytes", 0),
                    "mime_type": asset_dict.get("mime_type"),
                    "media_type": asset_dict.get("media_type", "image"),
                    "storage_rel_path": asset_dict["storage_rel_path"],
                    "storage_abs_path": asset_dict.get("storage_abs_path"),
                    "thumb_rel_path": asset_dict.get("thumb_rel_path"),
                    "source_rel_path": asset_dict.get("source_rel_path"),
                    "source_folder": asset_dict.get("source_folder"),
                    "width_pixels": asset_dict.get("width_pixels"),
                    "height_pixels": asset_dict.get("height_pixels"),
                    "duration_seconds": asset_dict.get("duration_seconds"),
                    "frame_rate": asset_dict.get("frame_rate"),
                    "gps_latitude": asset_dict.get("gps_latitude"),
                    "gps_longitude": asset_dict.get("gps_longitude"),
                    "gps_altitude": asset_dict.get("gps_altitude"),
                    "exif_data": json.dumps(asset_dict.get("exif_data") or {}),
                    "is_corrupt": asset_dict.get("is_corrupt", False),
                })
                row = cur.fetchone()
                if not conn:
                    c.commit()
                return row["asset_id"] if row else None
        finally:
            if should_close:
                c.close()

    def get_by_sha256(self, sha256: str, conn=None) -> Optional[Dict[str, Any]]:
        c, should_close = self.get_connection(conn)
        try:
            with c.cursor() as cur:
                cur.execute("SELECT * FROM media_assets WHERE sha256 = %s;", (sha256.lower().strip(),))
                return cur.fetchone()
        finally:
            if should_close:
                c.close()

    def get_existing_assets_cache(self, conn=None) -> Dict[str, str]:
        """Returns in-memory cache mapping {sha256: asset_id}."""
        c, should_close = self.get_connection(conn)
        try:
            with c.cursor() as cur:
                cur.execute("SELECT sha256, asset_id FROM media_assets;")
                return {r["sha256"].strip().lower(): str(r["asset_id"]) for r in cur.fetchall()}
        finally:
            if should_close:
                c.close()
