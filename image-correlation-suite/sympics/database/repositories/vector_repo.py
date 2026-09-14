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
Vector Embedding Repository
===========================
Handles multi-model embeddings (CLIP, SigLIP, SigLIP-2) and pgvector queries.
"""

from typing import Optional, List, Dict, Any
from sympics.database.repositories.base import BaseRepository


class VectorEmbeddingRepository(BaseRepository):

    def add_embedding(self, asset_id: str, vector: List[float], model_name: str = "siglip", model_version: str = "base-patch16-224", conn=None) -> Optional[str]:
        """Inserts or updates vector embedding for an asset."""
        c, should_close = self.get_connection(conn)
        try:
            dim = len(vector)
            col_name = "embedding_512" if dim == 512 else "embedding_768"
            val_512 = vector if dim == 512 else None
            val_768 = vector if dim == 768 else None

            with c.cursor() as cur:
                cur.execute(f"""
                    INSERT INTO media_embeddings (
                        asset_id, model_name, model_version, {col_name}
                    ) VALUES (
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (asset_id, model_name) DO UPDATE SET
                        {col_name} = EXCLUDED.{col_name},
                        model_version = EXCLUDED.model_version,
                        created_at = CURRENT_TIMESTAMP
                    RETURNING embedding_id;
                """, (asset_id, model_name, model_version, val_512 if dim == 512 else val_768))
                row = cur.fetchone()
                if not conn:
                    c.commit()
                return row["embedding_id"] if row else None
        finally:
            if should_close:
                c.close()

    def search_similar(self, query_vector: List[float], model_name: str = "siglip2_naflex", limit: int = 50, conn=None) -> List[Dict[str, Any]]:
        """Performs pgvector cosine distance search (<=>)."""
        c, should_close = self.get_connection(conn)
        try:
            dim = len(query_vector)
            col_name = "embedding_512" if dim == 512 else "embedding_768"

            with c.cursor() as cur:
                cur.execute(f"""
                    SELECT 
                        ma.asset_id, ma.storage_rel_path, ma.thumb_rel_path, ma.source_rel_path,
                        ma.source_folder, ma.file_size_bytes, ma.width_pixels, ma.height_pixels,
                        ma.gps_latitude, ma.gps_longitude, ma.created_at,
                        1 - (me.{col_name} <=> %s::vector) AS similarity_score
                    FROM media_embeddings me
                    JOIN media_assets ma ON me.asset_id = ma.asset_id
                    WHERE me.model_name = %s AND me.{col_name} IS NOT NULL
                    ORDER BY me.{col_name} <=> %s::vector ASC
                    LIMIT %s;
                """, (query_vector, model_name, query_vector, limit))
                return cur.fetchall()
        finally:
            if should_close:
                c.close()
