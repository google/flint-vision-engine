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
SYMPICS HIGH-SPEED PARALLEL MIGRATION & INGESTION WORKER
===============================================================================
High-performance, multi-threaded worker that consumes 'PENDING' records from
`migration_manifest`, generates AI embeddings (SigLIP) in lightweight mini-batches,
writes 256px WebP thumbnails across thread pools, copies media to the 2-layer hex
vault, performs readback verification, and updates progress in real time.
===============================================================================
"""

import os
import sys
import time
import shutil
import hashlib
import mimetypes
import json
import argparse
import zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Add database module to path
_db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database"))
if _db_dir not in sys.path:
    sys.path.insert(0, _db_dir)

try:
    import db
    from embedder_service import get_embedder, VisionEmbedderService, load_image_or_raw
    from hardware_acceleration import probe_hardware, print_hardware_banner
    from PIL import Image
except ImportError as e:
    print(f"[ERROR] Could not import required modules from {_db_dir}: {e}")
    sys.exit(1)


def print_banner():
    print("===============================================================================")
    print("  SYMPICS - HIGH-SPEED MULTI-THREADED INGESTION WORKER")
    print("===============================================================================")


def compute_sha256(filepath):
    sha256_h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sha256_h.update(chunk)
    return sha256_h.hexdigest().lower()


def check_source_exists(source_path):
    """Checks whether the file or its parent zip archive exists."""
    if "!" in source_path:
        zip_path, _ = source_path.split("!", 1)
        return os.path.exists(zip_path)
    return os.path.exists(source_path)


def extract_or_copy_source(source_path, dest_abs_path):
    """
    Safely copies a loose file or extracts an archive entry directly to destination.
    """
    if "!" in source_path:
        zip_path, inner_name = source_path.split("!", 1)
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"Parent archive not found: {zip_path}")
        with zipfile.ZipFile(zip_path, "r") as zf:
            with zf.open(inner_name, "r") as src, open(dest_abs_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
    else:
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source file not found: {source_path}")
        shutil.copy2(source_path, dest_abs_path)


def extract_gps_coordinates(filepath):
    """Extracts (latitude, longitude, altitude) as float degrees/meters from EXIF GPSInfo."""
    try:
        img = load_image_or_raw(filepath)
        if not img:
            return None, None, None
        raw_exif = img._getexif() if hasattr(img, "_getexif") else None
        if not raw_exif:
            return None, None, None
        from PIL.ExifTags import TAGS, GPSTAGS
        gps_info = None
        for tag_id, val in raw_exif.items():
            if TAGS.get(tag_id, str(tag_id)) == "GPSInfo":
                gps_info = val
                break
            if not gps_info or not isinstance(gps_info, dict):
                return None, None, None
            gps_tags = {}
            for k, v in gps_info.items():
                gps_tags[GPSTAGS.get(k, str(k))] = v

            def _to_degrees(val):
                if not val:
                    return 0.0
                d = float(val[0])
                m = float(val[1])
                s = float(val[2])
                return d + (m / 60.0) + (s / 3600.0)

            lat, lon, alt = None, None, None
            if "GPSLatitude" in gps_tags and "GPSLatitudeRef" in gps_tags:
                lat = _to_degrees(gps_tags["GPSLatitude"])
                if str(gps_tags["GPSLatitudeRef"]).upper() == "S":
                    lat = -lat

            if "GPSLongitude" in gps_tags and "GPSLongitudeRef" in gps_tags:
                lon = _to_degrees(gps_tags["GPSLongitude"])
                if str(gps_tags["GPSLongitudeRef"]).upper() == "W":
                    lon = -lon

            if "GPSAltitude" in gps_tags:
                alt = float(gps_tags["GPSAltitude"])

            return lat, lon, alt
    except Exception:
        return None, None, None


def process_single_item(item, clean_vault, existing_vault_assets, case_id, embedder=None, conn=None):
    """
    Processes a single manifest item:
    1. In-memory deduplication check (O(1) microsecond).
    2. Safe physical copy / archive extraction to 2-layer hex vault.
    3. Forensic readback SHA-256 verification.
    4. WebP thumbnail generation & EXIF/GPS parsing.
    5. AI vector generation.
    6. Database commit.
    """
    m_id = item["manifest_id"]
    source_path = item["source_filepath"]
    source_sha256 = item["sha256"].strip()
    source_md5 = item["md5"].strip()
    source_sha1 = (item["sha1"] or "").strip()
    source_size = item["file_size_bytes"]
    source_ext = item["file_extension"]
    source_filename = item["source_filename"]
    source_parent_dir = item["source_parent_dir"]
    is_video = item.get("is_video", False)
    t0 = time.time()

    if not check_source_exists(source_path):
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE migration_manifest SET
                    status = 'FAILED_CORRUPT', error_message = %s, migrated_at = CURRENT_TIMESTAMP
                WHERE manifest_id = %s;
            """, (f"Source file/archive not found: {source_path}", m_id))
        conn.commit()
        return False, 0, f"Source missing: {source_filename}"

    h1 = source_sha256[0:2]
    h2 = source_sha256[2:4]
    media_sub = "videos" if is_video else "images"
    rel_media_path = os.path.join("01_Media_Vault", media_sub, h1, h2, f"{source_sha256}{source_ext}")
    abs_media_path = os.path.join(clean_vault, rel_media_path)
    rel_thumb_path = os.path.join("02_Keyframe_Vault", "thumbs_256px", h1, h2, f"{source_sha256}.webp")
    abs_thumb_path = os.path.join(clean_vault, rel_thumb_path)

    # 1. Fast In-Memory Deduplication
    if source_sha256 in existing_vault_assets:
        if case_id:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO case_evidence_items (case_id, asset_id, original_filepath, original_filename, source_parent_dir)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (case_id, original_filepath) DO NOTHING;
                """, (case_id, asset_id, source_path, source_filename, source_parent_dir))
                conn.commit()

        with conn.cursor() as cur:
            cur.execute("""
                UPDATE migration_manifest SET
                    status = 'SKIPPED_DUPLICATE', destination_abs_path = %s, destination_rel_path = %s,
                    destination_size_bytes = %s, destination_sha256 = %s, embedding_status = 'SKIPPED',
                    processing_time_ms = %s, migrated_at = CURRENT_TIMESTAMP, verified_at = CURRENT_TIMESTAMP
                WHERE manifest_id = %s;
            """, (abs_media_path, rel_media_path, source_size, source_sha256, int((time.time() - t0)*1000), m_id))
        conn.commit()
        return True, source_size, None

    try:
        os.makedirs(os.path.dirname(abs_media_path), exist_ok=True)
        os.makedirs(os.path.dirname(abs_thumb_path), exist_ok=True)

        # 2. Safe Physical Copy / Archive Extraction
        extract_or_copy_source(source_path, abs_media_path)

        # 3. Forensic Readback Check
        dest_size = os.path.getsize(abs_media_path)
        dest_sha256 = compute_sha256(abs_media_path)

        if dest_sha256 != source_sha256 or dest_size != source_size:
            raise ValueError(f"Readback hash mismatch! Expected {source_sha256}, got {dest_sha256}")

        # 4. Thumbnail & EXIF
        width, height, exif_data = VisionEmbedderService.generate_thumbnail(abs_media_path, abs_thumb_path)

        # 5. AI Vector Embedding
        embs = {}
        if embedder is not None and not is_video:
            embs = embedder.compute_all_embeddings(abs_media_path)

        mime_type, _ = mimetypes.guess_type(source_filename)
        mime_type = mime_type or "application/octet-stream"

        lat, lon, alt = extract_gps_coordinates(abs_media_path) if not is_video else (None, None, None)

        # 6. Database Commit
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO media_assets (
                    sha256, md5, sha1, file_size_bytes, media_type, mime_type,
                    width_pixels, height_pixels, storage_rel_path, storage_abs_path,
                    thumb_rel_path, source_folder, source_rel_path,
                    gps_latitude, gps_longitude, gps_altitude, exif_data
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (sha256) DO UPDATE SET
                    storage_rel_path = EXCLUDED.storage_rel_path,
                    source_folder = COALESCE(EXCLUDED.source_folder, media_assets.source_folder),
                    source_rel_path = COALESCE(EXCLUDED.source_rel_path, media_assets.source_rel_path),
                    gps_latitude = COALESCE(EXCLUDED.gps_latitude, media_assets.gps_latitude),
                    gps_longitude = COALESCE(EXCLUDED.gps_longitude, media_assets.gps_longitude)
                RETURNING asset_id;
            """, (
                source_sha256, source_md5, source_sha1 or None,
                dest_size, "VIDEO" if is_video else "IMAGE", mime_type,
                width, height, rel_media_path, abs_media_path,
                rel_thumb_path, source_parent_dir, source_path,
                lat, lon, alt, json.dumps(exif_data)
            ))
            new_asset_id = cur.fetchone()["asset_id"]
            existing_vault_assets[source_sha256] = new_asset_id

            # Insert all 3 models into media_embeddings
            if embs:
                if "clip" in embs and embs["clip"]:
                    cur.execute("""
                        INSERT INTO media_embeddings (asset_id, model_name, model_version, dimension_size, embedding_l2)
                        VALUES (%s, 'clip', 'vit-b-32', 512, %s)
                        ON CONFLICT (asset_id, model_name) DO UPDATE SET embedding_l2 = EXCLUDED.embedding_l2;
                    """, (new_asset_id, embs["clip"]))

                if "siglip" in embs and embs["siglip"]:
                    cur.execute("""
                        INSERT INTO media_embeddings (asset_id, model_name, model_version, dimension_size, embedding_l2)
                        VALUES (%s, 'siglip', 'base-patch16-224', 768, %s)
                        ON CONFLICT (asset_id, model_name) DO UPDATE SET embedding_l2 = EXCLUDED.embedding_l2;
                    """, (new_asset_id, embs["siglip"]))

                if "siglip2_naflex" in embs and embs["siglip2_naflex"]:
                    cur.execute("""
                        INSERT INTO media_embeddings (asset_id, model_name, model_version, dimension_size, embedding_l2)
                        VALUES (%s, 'siglip2_naflex', 'base-patch16-naflex', 768, %s)
                        ON CONFLICT (asset_id, model_name) DO UPDATE SET embedding_l2 = EXCLUDED.embedding_l2;
                    """, (new_asset_id, embs["siglip2_naflex"]))

            if case_id:
                cur.execute("""
                    INSERT INTO case_evidence_items (case_id, asset_id, original_filepath, original_filename, source_parent_dir)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (case_id, original_filepath) DO NOTHING;
                """, (case_id, new_asset_id, source_path, source_filename, source_parent_dir))

            cur.execute("""
                UPDATE migration_manifest SET
                    status = 'VERIFIED_COPIED', destination_abs_path = %s, destination_rel_path = %s,
                    destination_size_bytes = %s, destination_sha256 = %s,
                    embedding_status = %s, processing_time_ms = %s,
                    migrated_at = CURRENT_TIMESTAMP, verified_at = CURRENT_TIMESTAMP
                WHERE manifest_id = %s;
            """, (
                abs_media_path, rel_media_path, dest_size, dest_sha256,
                'EMBEDDED' if embs else 'SKIPPED',
                int((time.time() - t0)*1000), m_id
            ))

        conn.commit()
        return True, dest_size, None

    except Exception as e:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE migration_manifest SET
                    status = 'FAILED_ERROR', error_message = %s,
                    processing_time_ms = %s, migrated_at = CURRENT_TIMESTAMP
                WHERE manifest_id = %s;
            """, (str(e), int((time.time() - t0)*1000), m_id))
        conn.commit()
        return False, 0, str(e)


def process_batch_items(batch, clean_vault, existing_vault_assets, case_id, embedder=None, conn=None):
    """
    Processes a batch of manifest items concurrently:
      1. Prepares thumbnails, hashes, and copies files / extracts archive items.
      2. Runs batch embedding extraction across all 3 AI models.
      3. Performs transactional database commit for all items.
    """
    results = []
    embed_items = []
    embed_paths = []

    for item in batch:
        m_id = item["manifest_id"]
        source_path = item["source_filepath"]
        source_sha256 = item["sha256"].strip()
        source_md5 = item["md5"].strip()
        source_sha1 = (item["sha1"] or "").strip()
        source_size = item["file_size_bytes"]
        source_ext = item["file_extension"]
        source_filename = item["source_filename"]
        source_parent_dir = item["source_parent_dir"]
        is_video = item.get("is_video", False)
        t0 = time.time()

        if not check_source_exists(source_path):
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE migration_manifest SET
                        status = 'FAILED_CORRUPT', error_message = %s, migrated_at = CURRENT_TIMESTAMP
                    WHERE manifest_id = %s;
                """, (f"Source file/archive not found: {source_path}", m_id))
            conn.commit()
            results.append((False, 0, f"Source missing: {source_filename}"))
            continue

        h1 = source_sha256[0:2]
        h2 = source_sha256[2:4]
        media_sub = "videos" if is_video else "images"
        rel_media_path = os.path.join("01_Media_Vault", media_sub, h1, h2, f"{source_sha256}{source_ext}")
        abs_media_path = os.path.join(clean_vault, rel_media_path)
        rel_thumb_path = os.path.join("02_Keyframe_Vault", "thumbs_256px", h1, h2, f"{source_sha256}.webp")
        abs_thumb_path = os.path.join(clean_vault, rel_thumb_path)

        # 1. In-Memory Deduplication
        if source_sha256 in existing_vault_assets:
            asset_id = existing_vault_assets[source_sha256]
            if case_id:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO case_evidence_items (case_id, asset_id, original_filepath, original_filename, source_parent_dir)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (case_id, original_filepath) DO NOTHING;
                    """, (case_id, asset_id, source_path, source_filename, source_parent_dir))

            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE migration_manifest SET
                        status = 'SKIPPED_DUPLICATE', destination_abs_path = %s, destination_rel_path = %s,
                        destination_size_bytes = %s, destination_sha256 = %s, embedding_status = 'SKIPPED',
                        processing_time_ms = %s, migrated_at = CURRENT_TIMESTAMP, verified_at = CURRENT_TIMESTAMP
                    WHERE manifest_id = %s;
                """, (abs_media_path, rel_media_path, source_size, source_sha256, int((time.time() - t0)*1000), m_id))
            conn.commit()
            results.append((True, source_size, None))
            continue

        try:
            os.makedirs(os.path.dirname(abs_media_path), exist_ok=True)
            os.makedirs(os.path.dirname(abs_thumb_path), exist_ok=True)

            # 2. Safe Physical Copy / Archive Extraction
            extract_or_copy_source(source_path, abs_media_path)

            # 3. Forensic Readback Check
            dest_size = os.path.getsize(abs_media_path)
            dest_sha256 = compute_sha256(abs_media_path)
            if dest_sha256 != source_sha256 or dest_size != source_size:
                raise ValueError(f"Readback hash mismatch! Expected {source_sha256}, got {dest_sha256}")

            # 4. Thumbnail & EXIF & GPS
            width, height, exif_data = VisionEmbedderService.generate_thumbnail(abs_media_path, abs_thumb_path)
            lat, lon, alt = extract_gps_coordinates(abs_media_path) if not is_video else (None, None, None)

            mime_type, _ = mimetypes.guess_type(source_filename)
            mime_type = mime_type or "application/octet-stream"

            item_ctx = {
                "m_id": m_id,
                "source_path": source_path,
                "source_filename": source_filename,
                "source_parent_dir": source_parent_dir,
                "source_sha256": source_sha256,
                "source_md5": source_md5,
                "source_sha1": source_sha1,
                "dest_size": dest_size,
                "dest_sha256": dest_sha256,
                "rel_media_path": rel_media_path,
                "abs_media_path": abs_media_path,
                "rel_thumb_path": rel_thumb_path,
                "width": width,
                "height": height,
                "exif_data": exif_data,
                "lat": lat,
                "lon": lon,
                "alt": alt,
                "is_video": is_video,
                "mime_type": mime_type,
                "t0": t0
            }
            embed_items.append(item_ctx)
            if not is_video:
                embed_paths.append(abs_media_path)
            else:
                embed_paths.append(abs_thumb_path)
        except Exception as e:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE migration_manifest SET
                        status = 'FAILED_CORRUPT', error_message = %s, migrated_at = CURRENT_TIMESTAMP
                    WHERE manifest_id = %s;
                """, (str(e), m_id))
            conn.commit()
            results.append((False, 0, str(e)))

    # Compute Batch Embeddings
    batch_embs = []
    if embedder is not None and embed_paths:
        batch_embs = embedder.compute_batch_embeddings(embed_paths)
    else:
        batch_embs = [{} for _ in embed_paths]

    # Commit all batch items to database
    with conn.cursor() as cur:
        for idx, item_ctx in enumerate(embed_items):
            embs = batch_embs[idx] if idx < len(batch_embs) else {}
            try:
                cur.execute("""
                    INSERT INTO media_assets (
                        sha256, md5, sha1, file_size_bytes, media_type, mime_type,
                        width_pixels, height_pixels, storage_rel_path, storage_abs_path,
                        thumb_rel_path, source_folder, source_rel_path,
                        gps_latitude, gps_longitude, gps_altitude, exif_data
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (sha256) DO UPDATE SET
                        storage_rel_path = EXCLUDED.storage_rel_path,
                        source_folder = COALESCE(EXCLUDED.source_folder, media_assets.source_folder),
                        source_rel_path = COALESCE(EXCLUDED.source_rel_path, media_assets.source_rel_path),
                        gps_latitude = COALESCE(EXCLUDED.gps_latitude, media_assets.gps_latitude),
                        gps_longitude = COALESCE(EXCLUDED.gps_longitude, media_assets.gps_longitude)
                    RETURNING asset_id;
                """, (
                    item_ctx["source_sha256"], item_ctx["source_md5"], item_ctx["source_sha1"] or None,
                    item_ctx["dest_size"], "VIDEO" if item_ctx["is_video"] else "IMAGE", item_ctx["mime_type"],
                    item_ctx["width"], item_ctx["height"], item_ctx["rel_media_path"], item_ctx["abs_media_path"],
                    item_ctx["rel_thumb_path"], item_ctx["source_parent_dir"], item_ctx["source_path"],
                    item_ctx["lat"], item_ctx["lon"], item_ctx["alt"], json.dumps(item_ctx["exif_data"])
                ))
                new_asset_id = cur.fetchone()["asset_id"]
                existing_vault_assets[item_ctx["source_sha256"]] = new_asset_id

                if embs:
                    if "clip" in embs and embs["clip"]:
                        cur.execute("""
                            INSERT INTO media_embeddings (asset_id, model_name, model_version, dimension_size, embedding_l2)
                            VALUES (%s, 'clip', 'vit-b-32', 512, %s)
                            ON CONFLICT (asset_id, model_name) DO UPDATE SET embedding_l2 = EXCLUDED.embedding_l2;
                        """, (new_asset_id, embs["clip"]))

                    if "siglip" in embs and embs["siglip"]:
                        cur.execute("""
                            INSERT INTO media_embeddings (asset_id, model_name, model_version, dimension_size, embedding_l2)
                            VALUES (%s, 'siglip', 'base-patch16-224', 768, %s)
                            ON CONFLICT (asset_id, model_name) DO UPDATE SET embedding_l2 = EXCLUDED.embedding_l2;
                        """, (new_asset_id, embs["siglip"]))

                    if "siglip2_naflex" in embs and embs["siglip2_naflex"]:
                        cur.execute("""
                            INSERT INTO media_embeddings (asset_id, model_name, model_version, dimension_size, embedding_l2)
                            VALUES (%s, 'siglip2_naflex', 'base-patch16-naflex', 768, %s)
                            ON CONFLICT (asset_id, model_name) DO UPDATE SET embedding_l2 = EXCLUDED.embedding_l2;
                        """, (new_asset_id, embs["siglip2_naflex"]))

                if case_id:
                    cur.execute("""
                        INSERT INTO case_evidence_items (case_id, asset_id, original_filepath, original_filename, source_parent_dir)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (case_id, original_filepath) DO NOTHING;
                    """, (case_id, new_asset_id, item_ctx["source_path"], item_ctx["source_filename"], item_ctx["source_parent_dir"]))

                cur.execute("""
                    UPDATE migration_manifest SET
                        status = 'VERIFIED_COPIED', destination_abs_path = %s, destination_rel_path = %s,
                        destination_size_bytes = %s, destination_sha256 = %s,
                        embedding_status = %s, processing_time_ms = %s,
                        migrated_at = CURRENT_TIMESTAMP, verified_at = CURRENT_TIMESTAMP
                    WHERE manifest_id = %s;
                """, (
                    item_ctx["abs_media_path"], item_ctx["rel_media_path"], item_ctx["dest_size"], item_ctx["dest_sha256"],
                    'EMBEDDED' if embs else 'SKIPPED',
                    int((time.time() - item_ctx["t0"])*1000), item_ctx["m_id"]
                ))
                results.append((True, item_ctx["dest_size"], None))
            except Exception as e:
                results.append((False, 0, str(e)))

    conn.commit()
    return results


def process_vault_migration(vault_root_dir, case_number=None, compute_embeddings=True, batch_size=8, max_gb=None):
    clean_vault = os.path.abspath(os.path.expanduser(vault_root_dir))
    if not os.path.isdir(clean_vault):
        print(f"\n[ERROR] Destination vault does not exist: {clean_vault}")
        return False

    max_bytes = int(float(max_gb) * 1024 * 1024 * 1024) if max_gb else None
    worker_id = f"{os.uname().nodename}_{os.getpid()}"

    print("[*] Initializing Core Database Schema...")
    db.init_db()

    conn = db.get_connection()
    case_id = None
    if case_number:
        with conn.cursor() as cur:
            cur.execute("SELECT case_id FROM cases WHERE case_number = %s;", (case_number,))
            r = cur.fetchone()
            if r:
                case_id = r["case_id"]
            else:
                cur.execute("INSERT INTO cases (case_number, case_name, classification_type) VALUES (%s, %s, 'MEDIA_EVIDENCE') RETURNING case_id;", (case_number, f"Migration Case: {case_number}"))
                case_id = cur.fetchone()["case_id"]
                conn.commit()
        print(f"[+] Linked to Case Container: '{case_number}' ({case_id})")
    else:
        print(f"[+] Ingesting into Master Media Vault (Unassigned Case)")

    # Pre-load existing physical hashes into memory cache
    print("[*] Pre-loading existing vault asset index into memory cache...")
    existing_vault_assets = {}
    with conn.cursor() as cur:
        cur.execute("SELECT sha256, asset_id FROM media_assets;")
        for r in cur.fetchall():
            existing_vault_assets[r["sha256"].strip()] = r["asset_id"]
    print(f"[+] Cached {len(existing_vault_assets):,} existing physical assets in RAM.")

    # Reset any stale SCANNING records from previous dead runs
    db.reset_stale_scanning_records(conn=conn)

    # Check pending records
    total_pending = db.get_pending_manifest_count(conn=conn)
    if total_pending == 0:
        print("\n[!] No 'PENDING' records found in migration_manifest.")
        conn.close()
        return True

    print(f"\n[*] Worker ID           : {worker_id}")
    print(f"[*] Queue Remaining     : {total_pending:,} pending evidence records")
    print(f"[*] Batch Size          : {batch_size} files / batch (Dynamic SKIP LOCKED Queue)")
    print(f"[*] AI Embedding Mode   : {'Active (CLIP 512 + SigLIP Base 768 + SigLIP-2 NaFlex 768)' if compute_embeddings else 'Fast Disk-Only (No AI)'}")
    print(f"[*] Destination Vault   : {clean_vault}")
    if max_gb:
        print(f"[*] Test Migration Cap  : {max_gb} GB ({max_bytes:,} bytes)")
    else:
        print(f"[*] Test Migration Cap  : FULL INGESTION (No Limit)")
    print(f"-------------------------------------------------------------------------------")

    embedder = None
    if compute_embeddings:
        print("[*] Initializing AI Multi-Model Vision Embedders (CLIP + SigLIP + SigLIP-2)...")
        embedder = get_embedder()

    start_total_time = time.time()
    total_verified = 0
    total_failed = 0
    total_bytes = 0
    processed_count = 0

    print("\n Starting Real-Time Ingestion & Verification Loop...\n")

    try:
        while True:
            if max_bytes and total_bytes >= max_bytes:
                print(f"\n\n[+] Reached desired test migration cap of {max_gb} GB ({total_bytes / (1024**3):.2f} GB migrated).")
                break

            # Atomically check out next batch using PostgreSQL SKIP LOCKED
            batch = db.checkout_pending_manifest_batch(batch_size=batch_size, worker_id=worker_id, conn=conn)
            if not batch:
                break

            batch_results = process_batch_items(
                batch, clean_vault, existing_vault_assets, case_id,
                embedder=embedder, conn=conn
            )

            for success, b_migrated, err in batch_results:
                if success:
                    total_verified += 1
                    total_bytes += b_migrated
                else:
                    total_failed += 1

            processed_count += len(batch)

            # Real-time visual progress counter
            elapsed_total = time.time() - start_total_time
            speed = processed_count / elapsed_total if elapsed_total > 0 else 0
            remaining = db.get_pending_manifest_count(conn=conn)

            sys.stdout.write(
                f"\r [+] Worker {worker_id} | Ingested: {processed_count:,} files | Queue Remaining: {remaining:,} | Speed: {speed:5.1f} files/s | Batch: {len(batch)} files"
            )
            sys.stdout.flush()

    except KeyboardInterrupt:
        print(f"\n\n[!] Worker interrupted by user. Releasing in-progress batch back to PENDING...")
        db.reset_stale_scanning_records(worker_id=worker_id, conn=conn)

    finally:
        conn.close()

    total_time = time.time() - start_total_time

    print(f"\n\n===============================================================================")
    print(f" INGESTION & AUDIT COMPLETE (Elapsed: {total_time:.2f}s | Speed: {processed_count/total_time if total_time > 0 else 0:.1f} files/s)")
    print(f"===============================================================================")
    print(f" Total Processed    : {processed_count:,} files")
    print(f" Verified & Ingested: {total_verified:,} files")
    print(f" Failed / Corrupt   : {total_failed:,} files")
    print(f" Total Vault Volume : {total_bytes / (1024 * 1024):,.2f} MB ({total_bytes / (1024 * 1024 * 1024):,.3f} GB)")
    print(f" Database Target    : media_assets, media_embeddings (pgvector), case_evidence_items")
    print(f"===============================================================================\n")

    return True


def run_supervisor(vault_dir, case_number=None, compute_embeddings=True, workers=None, batch_size=None, max_gb=None):
    """
    Supervises a pool of parallel worker processes, dynamically scaling across hardware cores.
    """
    import subprocess

    prof = probe_hardware()
    actual_workers = workers if workers is not None else prof.recommended_workers
    actual_batch = batch_size if batch_size is not None else prof.recommended_batch_size

    print_banner()
    print_hardware_banner(prof)

    print(f"[*] Initializing SYMPICS Supervised Worker Pool ({actual_workers} parallel workers)...")
    print(f"[*] Target Destination  : {vault_dir}")
    print(f"[*] Concurrency Mode    : PostgreSQL 'FOR UPDATE SKIP LOCKED' Dynamic Queue")
    print(f"[*] Batch Size / Worker : {actual_batch} items")
    print(f"[*] AI Embedding Mode   : {'Active (CLIP + SigLIP + SigLIP-2)' if compute_embeddings else 'Fast Disk-Only'}")
    print("-------------------------------------------------------------------------------\n")

    # Reset any stale scanning records before launch
    db.reset_stale_scanning_records()
    total_pending = db.get_pending_manifest_count()
    if total_pending == 0:
        print("[!] No 'PENDING' records found in migration_manifest. Queue is clear.\n")
        return True

    processes = []
    script_path = os.path.abspath(__file__)

    for i in range(1, actual_workers + 1):
        cmd = [
            sys.executable, script_path,
            "--single-process",
            "--worker-num", str(i),
            "--vault-dir", vault_dir,
            "--batch-size", str(actual_batch)
        ]
        if case_number:
            cmd.extend(["--case-number", case_number])
        if not compute_embeddings:
            cmd.append("--fast-copy-only")
        if max_gb:
            cmd.extend(["--max-gb", str(max_gb)])

        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        processes.append(p)

    print(f"[+] Successfully spawned {len(processes)} parallel workers. Monitoring live throughput...\n")

    start_time = time.time()
    initial_pending = total_pending
    processed = 0

    try:
        while True:
            alive = sum(1 for p in processes if p.poll() is None)
            remaining = db.get_pending_manifest_count()
            elapsed = time.time() - start_time
            processed = max(0, initial_pending - remaining)
            speed = processed / elapsed if elapsed > 0 else 0.0

            pct = ((initial_pending - remaining) / initial_pending * 100) if initial_pending > 0 else 100.0
            bar_len = 25
            filled = int(bar_len * (pct / 100))
            bar = "█" * filled + "-" * (bar_len - filled)

            sys.stdout.write(
                f"\r [{bar}] {pct:5.1f}% | Processed: {processed:,}/{initial_pending:,} | Remaining: {remaining:,} | Active Workers: {alive}/{actual_workers} | Speed: {speed:5.1f} files/s"
            )
            sys.stdout.flush()

            if remaining == 0 or alive == 0:
                break

            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\n\n[!] Received Ctrl+C. Gracefully terminating all worker processes...")
        for p in processes:
            p.terminate()
        for p in processes:
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()
        db.reset_stale_scanning_records()
        print("[+] All workers cleanly terminated and in-flight batches released.")
        return False

    for p in processes:
        p.wait()

    total_time = time.time() - start_time
    print(f"\n\n===============================================================================")
    print(f" [+] SUPERVISED MIGRATION COMPLETE (Elapsed: {total_time:.2f}s | Speed: {processed/total_time if total_time > 0 else 0:.1f} files/s)")
    print(f"===============================================================================\n")
    return True


def main():
    parser = argparse.ArgumentParser(description="SYMPICS High-Speed Parallel Migration & Ingestion Worker.")
    parser.add_argument("--vault-dir", "-v", help="Destination SYMPICS Storage Vault path.")
    parser.add_argument("--case-number", "-c", default=None, help="Optional case container name to link migrated evidence.")
    parser.add_argument("--max-gb", "-g", type=float, default=None, help="Limit migration size in GB for partial testing.")
    parser.add_argument("--workers", "-w", type=int, default=None, help="Number of parallel worker processes (default: auto-detected).")
    parser.add_argument("--batch-size", "-b", type=int, default=None, help="Batch size per worker (default: auto-detected).")
    parser.add_argument("--single-process", "-s", action="store_true", help="Run a single worker in the foreground.")
    parser.add_argument("--worker-num", type=int, default=1, help=argparse.SUPPRESS)
    parser.add_argument("--fast-copy-only", action="store_true", help="Skip AI embeddings for maximum copy speed.")

    args = parser.parse_args()

    cand_local = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "future-lan-storage"))
    cand_parent = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "future-lan-storage"))
    default_vault = cand_parent if (os.path.exists(cand_parent) and not os.path.exists(cand_local)) else cand_local
    vault_path = args.vault_dir or os.getenv("SYMPICS_VAULT_ROOT") or default_vault
    if vault_path and not os.path.isabs(vault_path):
        if not os.path.exists(vault_path) and os.path.exists(os.path.join("..", vault_path)):
            vault_path = os.path.abspath(os.path.join("..", vault_path))
        else:
            vault_path = os.path.abspath(vault_path)

    if args.single_process:
        print_banner()
        prof = probe_hardware()
        actual_batch = args.batch_size if args.batch_size is not None else prof.recommended_batch_size
        process_vault_migration(
            vault_path,
            case_number=args.case_number,
            compute_embeddings=not args.fast_copy_only,
            batch_size=actual_batch,
            max_gb=args.max_gb
        )
    else:
        run_supervisor(
            vault_path,
            case_number=args.case_number,
            compute_embeddings=not args.fast_copy_only,
            workers=args.workers,
            batch_size=args.batch_size,
            max_gb=args.max_gb
        )


if __name__ == "__main__":
    main()
