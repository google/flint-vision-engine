# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
SYMPICS Unified Evidence Ingestion Pipeline
=========================================
Composable pipeline orchestrating cryptographic hashing, CAS vault copying,
EXIF/GPS metadata parsing, WebP thumbnail generation, and AI vector embeddings.
"""

import os
import shutil
import mimetypes
from typing import Optional, Dict, Any, Tuple, List

from sympics.core.hashing import compute_file_hashes
from sympics.core.cas_vault import build_cas_rel_path, build_thumbnail_rel_path, get_media_category
from sympics.core.exif_parser import extract_exif_metadata, extract_gps_coordinates
from sympics.ai.thumbnailer import generate_thumbnail
from sympics.database import asset_repo, vector_repo, case_repo


class EvidenceIngestionPipeline:
    """Reusable, thread-safe evidence processing and vault ingestion engine."""

    def __init__(
        self,
        vault_root: str,
        asset_repository=None,
        vector_repository=None,
        case_repository=None,
        embedder_service=None
    ):
        self.vault_root = os.path.abspath(vault_root)
        self.asset_repo = asset_repository or asset_repo
        self.vector_repo = vector_repository or vector_repo
        self.case_repo = case_repository or case_repo
        self.embedder_service = embedder_service

    def process_single_evidence(
        self,
        source_path: str,
        source_folder: str = "Master_Vault",
        case_number: Optional[str] = None,
        compute_embeddings: bool = True,
        conn=None
    ) -> Tuple[bool, Optional[str], int, Optional[str]]:
        """
        Ingests a single file into the CAS vault with verification.
        Returns: (success: bool, asset_id: str, bytes_copied: int, error_message: str)
        """
        if not os.path.exists(source_path):
            return False, None, 0, f"Source file not found: {source_path}"

        try:
            # 1. Cryptographic Multi-Stream Hashing
            sha256, md5, sha1, file_size = compute_file_hashes(source_path)
            ext = os.path.splitext(source_path)[1].lower()
            filename = os.path.basename(source_path)

            # 2. Build CAS Vault & Thumbnail Paths
            rel_storage_path = build_cas_rel_path(sha256, ext)
            abs_storage_path = os.path.join(self.vault_root, rel_storage_path)
            rel_thumb_path = build_thumbnail_rel_path(sha256)
            abs_thumb_path = os.path.join(self.vault_root, rel_thumb_path)

            os.makedirs(os.path.dirname(abs_storage_path), exist_ok=True)
            os.makedirs(os.path.dirname(abs_thumb_path), exist_ok=True)

            # 3. Bit-for-Bit Copy if not already present
            bytes_copied = 0
            if not os.path.exists(abs_storage_path):
                shutil.copy2(source_path, abs_storage_path)
                bytes_copied = file_size

                # Readback verification
                dest_sha256, _, _, _ = compute_file_hashes(abs_storage_path)
                if dest_sha256.lower() != sha256.lower():
                    if os.path.exists(abs_storage_path):
                        os.remove(abs_storage_path)
                    return False, None, 0, "Cryptographic readback verification failed"

            # 4. Generate 256px WebP Thumbnail
            if not os.path.exists(abs_thumb_path):
                generate_thumbnail(abs_storage_path, abs_thumb_path, max_dim=256)

            # 5. Extract EXIF & GPS
            width, height, exif_data = extract_exif_metadata(abs_storage_path)
            lat, lon, alt = extract_gps_coordinates(abs_storage_path)
            mime_type, _ = mimetypes.guess_type(source_path)

            # 6. Insert/Update Media Asset Record
            asset_dict = {
                "sha256": sha256,
                "md5": md5,
                "sha1": sha1,
                "file_size_bytes": file_size,
                "mime_type": mime_type or "application/octet-stream",
                "media_type": get_media_category(ext),
                "storage_rel_path": rel_storage_path,
                "storage_abs_path": abs_storage_path,
                "thumb_rel_path": rel_thumb_path,
                "source_rel_path": os.path.relpath(source_path, self.vault_root) if source_path.startswith(self.vault_root) else filename,
                "source_folder": source_folder,
                "width_pixels": width,
                "height_pixels": height,
                "gps_latitude": lat,
                "gps_longitude": lon,
                "gps_altitude": alt,
                "exif_data": exif_data,
                "is_corrupt": False
            }
            asset_id = self.asset_repo.add_asset(asset_dict, conn=conn)

            # 7. AI Vision Embeddings (if enabled and embedder available)
            if compute_embeddings and self.embedder_service and asset_id:
                vectors = self.embedder_service.compute_batch_embeddings([abs_storage_path])
                if vectors and vectors[0]:
                    for model_name, vec in vectors[0].items():
                        self.vector_repo.add_embedding(asset_id, vec, model_name=model_name, conn=conn)

            # 8. Link to Case (if specified)
            if case_number and asset_id:
                case_id = self.case_repo.get_or_create_case(case_number, conn=conn)
                if case_id:
                    self.case_repo.link_evidence_item(
                        case_id=case_id,
                        asset_id=asset_id,
                        original_filepath=source_path,
                        original_filename=filename,
                        source_parent_dir=source_folder,
                        conn=conn
                    )

            return True, asset_id, bytes_copied, None

        except Exception as e:
            return False, None, 0, str(e)
