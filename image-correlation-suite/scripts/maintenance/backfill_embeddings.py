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
SYMPICS HIGH-SPEED MULTI-WORKER AI EMBEDDING BACKFILL ENGINE
===============================================================================
Spins up N parallel worker processes to compute and populate missing AI
embeddings (e.g. 'dinov3') across existing vault holdings using PostgreSQL
pgvector.
===============================================================================
"""

import os
import sys
import time
import argparse
from multiprocessing import Process, Queue, Value, cpu_count
from pathlib import Path

# Add database module to path
_db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database"))
if _db_dir not in sys.path:
    sys.path.insert(0, _db_dir)

import db
from embedder_service import VisionEmbedderService

cand_local = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "future-lan-storage"))
cand_parent = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "future-lan-storage"))
VAULT_ROOT = os.getenv("SYMPICS_VAULT_ROOT") or (cand_parent if (os.path.exists(cand_parent) and not os.path.exists(cand_local)) else cand_local)


def worker_process(worker_id, num_workers, model_name, batch_size, progress_counter, total_count):
    """Worker process that loads only the target model and processes its shard."""
    # Configure embedder to only load the target model
    opts = {
        "clip": model_name == "clip",
        "siglip": model_name == "siglip",
        "siglip2_naflex": model_name == "siglip2_naflex",
        "dinov3": model_name == "dinov3"
    }
    
    # Silence startup noise per worker
    embedder = VisionEmbedderService(device="cpu", compute_options=opts)
    
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            # Query only this worker's shard using PostgreSQL hash modulo
            cur.execute("""
                SELECT ma.asset_id, ma.storage_rel_path
                FROM media_assets ma
                LEFT JOIN media_embeddings me 
                    ON ma.asset_id = me.asset_id AND me.model_name = %s
                WHERE me.embedding_id IS NULL 
                  AND ma.media_type = 'IMAGE'
                  AND MOD(ABS(HASHTEXT(ma.asset_id::text)), %s) = %s
                ORDER BY ma.created_at ASC;
            """, (model_name, num_workers, worker_id))
            items = cur.fetchall()

        if not items:
            return

        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            paths = [os.path.join(VAULT_ROOT, it["storage_rel_path"]) for it in batch]
            
            embs_batch = embedder.compute_batch_embeddings(paths)

            with conn.cursor() as cur:
                for it, embs in zip(batch, embs_batch):
                    if embs and model_name in embs and embs[model_name]:
                        vec = embs[model_name]
                        dim = len(vec)
                        ver = "vit-b-16-lvd1689m" if model_name == "dinov3" else "v1"
                        cur.execute("""
                            INSERT INTO media_embeddings (asset_id, model_name, model_version, dimension_size, embedding_l2)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (asset_id, model_name) DO UPDATE SET embedding_l2 = EXCLUDED.embedding_l2;
                        """, (it["asset_id"], model_name, ver, dim, vec))
                conn.commit()

            with progress_counter.get_lock():
                progress_counter.value += len(batch)

    finally:
        conn.close()


def run_parallel_backfill(model_name="dinov3", num_workers=6, batch_size=32):
    model_name = model_name.lower().strip()
    print(f"\n==================================================================")
    print(f"[*] SYMPICS MULTI-WORKER EMBEDDING BACKFILL: {model_name.upper()}")
    print(f"   Workers: {num_workers} | Batch Size: {batch_size} per worker")
    print(f"==================================================================")

    # 1. Count total missing items
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as total
                FROM media_assets ma
                LEFT JOIN media_embeddings me 
                    ON ma.asset_id = me.asset_id AND me.model_name = %s
                WHERE me.embedding_id IS NULL AND ma.media_type = 'IMAGE';
            """, (model_name,))
            total_missing = cur.fetchone()["total"]
    finally:
        conn.close()

    if total_missing == 0:
        print(f"[+] All holdings already have '{model_name}' embeddings! Nothing to do.")
        return

    print(f"[*] Total holdings to process: {total_missing} assets across {num_workers} parallel workers.\n")

    progress_counter = Value('i', 0)
    workers = []
    t_start = time.time()

    # 2. Spawn worker processes
    for w_id in range(num_workers):
        p = Process(
            target=worker_process,
            args=(w_id, num_workers, model_name, batch_size, progress_counter, total_missing)
        )
        p.start()
        workers.append(p)

    # 3. Monitor aggregate progress
    while any(p.is_alive() for p in workers):
        time.sleep(0.5)
        done = progress_counter.value
        pct = (done / total_missing) * 100 if total_missing > 0 else 100.0
        elapsed = time.time() - t_start
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total_missing - done) / rate if rate > 0 else 0
        print(f"   Progress: [{done}/{total_missing}] ({pct:.1f}%) | Throughput: {rate:.1f} img/s | Elapsed: {elapsed:.1f}s | ETA: {eta:.0f}s  ", end="\r")

    for p in workers:
        p.join()

    total_time = time.time() - t_start
    final_done = progress_counter.value
    print(f"\n\n[+] Multi-worker backfill completed successfully!")
    print(f"    - Processed : {final_done} assets")
    print(f"    - Total Time: {total_time:.1f}s ({final_done / total_time:.1f} images/sec aggregate)")
    print(f"    - Model     : {model_name.upper()} (768-dim pgvector HNSW ready)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-worker retroactive AI embedding backfill engine.")
    parser.add_argument("--model", type=str, default="dinov3", help="Target model (dinov3, siglip2_naflex, siglip, clip)")
    parser.add_argument("--workers", type=int, default=6, help="Number of parallel worker processes (default: 6)")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size per worker (default: 32)")
    args = parser.parse_args()

    run_parallel_backfill(model_name=args.model, num_workers=args.workers, batch_size=args.batch_size)
