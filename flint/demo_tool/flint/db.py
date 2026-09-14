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

from flint.ann import FlintANNIndex
# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""Zero-dependency SQLite vector and metadata storage for edge vision inference."""

import collections
import contextlib
import datetime
import hashlib
import io
import json
import os
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, Generator, List, Optional, Sequence, Tuple, Union
import numpy as np
from PIL import Image, ImageOps
try:
  import pillow_heif
  pillow_heif.register_heif_opener()
except Exception:
  pass

from flint.video import extract_keyframes

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff', '.tif', '.gif', '.heic', '.heif'}
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v', '.flv'}


def compute_file_hash(filepath: str) -> str:
  """Computes a fast SHA-256 / mtime-size digest for file identification."""
  try:
    stat = os.stat(filepath)
    hasher = hashlib.sha256()
    hasher.update(f"{stat.st_size}_{stat.st_mtime}".encode('utf-8'))
    with open(filepath, 'rb') as f:
      chunk = f.read(65536)
      hasher.update(chunk)
    return hasher.hexdigest()
  except Exception:
    return hashlib.sha256(filepath.encode('utf-8')).hexdigest()


class MediaDatabase:
  """SQLite-backed metadata and raw float32 vector store for FLINT Vision Engine."""

  def __init__(self, db_path: str = "flint_database.sqlite"):
    self.db_path = os.path.abspath(db_path)
    self._local = threading.local()
    self._lock = threading.Lock()
    self._matrix_cache: Dict[str, Dict[str, Any]] = {}
    self._ann_cache: Dict[str, FlintANNIndex] = {}
    self._init_db()

  @contextlib.contextmanager
  def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
    if not hasattr(self._local, "conn") or self._local.conn is None:
      conn = sqlite3.connect(self.db_path, timeout=60.0)
      conn.row_factory = sqlite3.Row
      conn.execute("PRAGMA journal_mode=WAL;")
      conn.execute("PRAGMA synchronous=NORMAL;")
      self._local.conn = conn
    try:
      yield self._local.conn
    except Exception:
      if hasattr(self._local, "conn") and self._local.conn:
        self._local.conn.rollback()
      raise

  def _init_db(self):
    with self.get_connection() as conn:
      conn.execute("""
          CREATE TABLE IF NOT EXISTS indexed_media (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              file_path TEXT UNIQUE NOT NULL,
              file_hash TEXT NOT NULL,
              file_size INTEGER NOT NULL,
              file_mtime REAL NOT NULL,
              media_type TEXT DEFAULT 'image',
              video_source_path TEXT,
              timestamp_seconds REAL DEFAULT 0.0,
              width INTEGER,
              height INTEGER,
              indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
          )
      """)

      conn.execute("""
          CREATE TABLE IF NOT EXISTS embeddings (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              media_id INTEGER NOT NULL,
              model_name TEXT NOT NULL,
              vector BLOB NOT NULL,
              dimension INTEGER NOT NULL,
              is_normalized INTEGER DEFAULT 1,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY(media_id) REFERENCES indexed_media(id) ON DELETE CASCADE,
              UNIQUE(media_id, model_name)
          )
      """)

      conn.execute("""
          CREATE TABLE IF NOT EXISTS known_targets (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              label TEXT NOT NULL,
              file_path TEXT NOT NULL,
              crop_box_json TEXT,
              group_name TEXT DEFAULT 'default',
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
          )
      """)

      conn.execute("""
          CREATE TABLE IF NOT EXISTS search_runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              query_type TEXT,
              query_summary TEXT,
              model_name TEXT,
              threshold REAL,
              metric TEXT,
              results_count INTEGER,
              duration_ms REAL,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
          )
      """)

      conn.execute("CREATE INDEX IF NOT EXISTS idx_media_type ON indexed_media(media_type);")
      conn.execute("CREATE INDEX IF NOT EXISTS idx_embed_model ON embeddings(model_name);")
      conn.execute("CREATE INDEX IF NOT EXISTS idx_embed_media ON embeddings(media_id);")
      conn.commit()

      # Auto-migrate schema if columns are missing in existing tables
      try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(known_targets)")
        cols = [r[1] for r in cur.fetchall()]
        if 'crop_box_json' not in cols:
          cur.execute("ALTER TABLE known_targets ADD COLUMN crop_box_json TEXT;")
        if 'group_name' not in cols:
          cur.execute("ALTER TABLE known_targets ADD COLUMN group_name TEXT DEFAULT 'default';")
        conn.commit()
      except Exception:
        pass

  def _invalidate_cache(self, model_name: Optional[str] = None):
    with self._lock:
      if model_name:
        self._matrix_cache.pop(model_name, None)
      else:
        self._matrix_cache.clear()

  def index_image(
      self,
      file_path: str,
      engine: Any,
      model_name: Optional[str] = None,
  ) -> bool:
    file_path = os.path.abspath(file_path)
    model = model_name or getattr(engine, "model_name", "default")
    if not os.path.exists(file_path):
      return False

    with self.get_connection() as conn:
      row = conn.execute(
          """
          SELECT e.id FROM embeddings e
          JOIN indexed_media m ON e.media_id = m.id
          WHERE m.file_path = ? AND e.model_name = ?
          """,
          (file_path, model),
      ).fetchone()
      if row:
        return False

      w, h = 0, 0
      try:
        with Image.open(file_path) as raw_img:
          img = ImageOps.exif_transpose(raw_img)
          w, h = img.size
      except Exception:
        pass

      size_bytes = os.path.getsize(file_path)
      mtime = os.path.getmtime(file_path)
      f_hash = compute_file_hash(file_path)

      cursor = conn.execute(
          """
          INSERT INTO indexed_media (file_path, file_hash, file_size, file_mtime, media_type, width, height)
          VALUES (?, ?, ?, ?, 'image', ?, ?)
          ON CONFLICT(file_path) DO UPDATE SET
              file_hash=excluded.file_hash, file_size=excluded.file_size,
              file_mtime=excluded.file_mtime, width=excluded.width, height=excluded.height
          RETURNING id
          """,
          (file_path, f_hash, size_bytes, mtime, w, h),
      )
      media_id = cursor.fetchone()["id"]

      vec = engine.compute_image_embedding(file_path, normalize=True)
      vec_np = np.asarray(vec, dtype=np.float32)
      conn.execute(
          """
          INSERT INTO embeddings (media_id, model_name, dimension, vector, is_normalized)
          VALUES (?, ?, ?, ?, 1)
          ON CONFLICT(media_id, model_name) DO UPDATE SET vector=excluded.vector
          """,
          (media_id, model, len(vec_np), vec_np.tobytes()),
      )
      conn.commit()

    self._invalidate_cache(model)
    return True

  def index_video(
      self,
      video_path: str,
      engine: Any,
      model_name: Optional[str] = None,
      method: str = "ssim",
      ssim_threshold: float = 0.65,
      interval_seconds: float = 1.0,
      uniform_count: int = 10,
      output_dir: Optional[str] = None,
  ) -> Dict[str, Any]:
    video_path = os.path.abspath(video_path)
    model = model_name or getattr(engine, "model_name", "default")
    if not os.path.exists(video_path):
      raise FileNotFoundError(f"Video file not found: {video_path}")

    out_folder = output_dir or os.path.join(os.path.dirname(self.db_path), "flint_keyframes")
    os.makedirs(out_folder, exist_ok=True)

    raw_keyframes = extract_keyframes(
        video_path=video_path,
        method=method,
        ssim_threshold=ssim_threshold,
        interval_seconds=interval_seconds,
        uniform_count=uniform_count,
    )

    if not raw_keyframes:
      return {'keyframes_indexed': 0, 'video_path': video_path}

    v_basename = os.path.splitext(os.path.basename(video_path))[0]
    saved_keyframes = []

    with self.get_connection() as conn:
      for timestamp, frame_idx, frame_img in raw_keyframes:
        frame_filename = f"{v_basename}_frame_{frame_idx}_{timestamp:.2f}s.jpg"
        frame_path = os.path.join(out_folder, frame_filename)
        frame_img.save(frame_path, format="JPEG", quality=85)
        w, h = frame_img.size
        size_bytes = os.path.getsize(frame_path)
        mtime = os.path.getmtime(frame_path)
        f_hash = compute_file_hash(frame_path)

        cursor = conn.execute(
            """
            INSERT INTO indexed_media (
                file_path, file_hash, file_size, file_mtime, media_type,
                video_source_path, timestamp_seconds, width, height
            ) VALUES (?, ?, ?, ?, 'video_keyframe', ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                file_hash=excluded.file_hash, file_size=excluded.file_size,
                file_mtime=excluded.file_mtime, timestamp_seconds=excluded.timestamp_seconds
            RETURNING id
            """,
            (frame_path, f_hash, size_bytes, mtime, video_path, timestamp, w, h),
        )
        media_id = cursor.fetchone()["id"]

        vec = engine.compute_image_embedding(frame_img, normalize=True)
        vec_np = np.asarray(vec, dtype=np.float32)
        conn.execute(
            """
            INSERT INTO embeddings (media_id, model_name, dimension, vector, is_normalized)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(media_id, model_name) DO UPDATE SET vector=excluded.vector
            """,
            (media_id, model, len(vec_np), vec_np.tobytes()),
        )
        saved_keyframes.append({
            'frame_path': frame_path,
            'timestamp': timestamp,
            'frame_index': frame_idx,
        })
      conn.commit()

    self._invalidate_cache(model)
    return {
        'keyframes_indexed': len(saved_keyframes),
        'video_path': video_path,
        'method': method,
        'keyframes': saved_keyframes,
    }

  def index_folder(
      self,
      folder_path: str,
      engine: Any,
      model_name: Optional[str] = None,
      recursive: bool = True,
      include_videos: bool = True,
      video_method: str = "ssim",
      video_ssim_threshold: float = 0.65,
      video_interval_seconds: float = 1.0,
      video_uniform_count: int = 10,
      batch_size: int = 32,
      progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
  ) -> Dict[str, Any]:
    folder_path = os.path.abspath(folder_path)
    model = model_name or getattr(engine, "model_name", "default")
    if not os.path.exists(folder_path):
      raise FileNotFoundError(f"Folder path not found: {folder_path}")

    image_files = []
    video_files = []

    if recursive:
      for root, _, files in os.walk(folder_path):
        for f in files:
          ext = os.path.splitext(f)[1].lower()
          if ext in IMAGE_EXTENSIONS:
            image_files.append(os.path.join(root, f))
          elif include_videos and ext in VIDEO_EXTENSIONS:
            video_files.append(os.path.join(root, f))
    else:
      for f in os.listdir(folder_path):
        full_p = os.path.join(folder_path, f)
        if os.path.isfile(full_p):
          ext = os.path.splitext(f)[1].lower()
          if ext in IMAGE_EXTENSIONS:
            image_files.append(full_p)
          elif include_videos and ext in VIDEO_EXTENSIONS:
            video_files.append(full_p)

    total_items = len(image_files) + len(video_files)
    indexed_count = 0
    skipped_count = 0

    with self.get_connection() as conn:
      existing_rows = conn.execute(
          """
          SELECT m.file_path FROM indexed_media m
          JOIN embeddings e ON m.id = e.media_id
          WHERE e.model_name = ?
          """,
          (model,),
      ).fetchall()
      existing_paths = set(r["file_path"] for r in existing_rows)

    unindexed_images = [p for p in image_files if p not in existing_paths]
    skipped_count += len(image_files) - len(unindexed_images)

    for i in range(0, len(unindexed_images), batch_size):
      chunk = unindexed_images[i : i + batch_size]
      embeddings = engine.compute_image_embeddings_batch(chunk, normalize=True)

      with self.get_connection() as conn:
        for fpath, vec in zip(chunk, embeddings):
          w, h = 0, 0
          try:
            with Image.open(fpath) as img:
              w, h = img.size
          except Exception:
            pass

          size_bytes = os.path.getsize(fpath) if os.path.exists(fpath) else 0
          mtime = os.path.getmtime(fpath) if os.path.exists(fpath) else 0.0
          f_hash = compute_file_hash(fpath)

          cursor = conn.execute(
              """
              INSERT INTO indexed_media (file_path, file_hash, file_size, file_mtime, media_type, width, height)
              VALUES (?, ?, ?, ?, 'image', ?, ?)
              ON CONFLICT(file_path) DO UPDATE SET
                  file_hash=excluded.file_hash, file_size=excluded.file_size,
                  file_mtime=excluded.file_mtime, width=excluded.width, height=excluded.height
              RETURNING id
              """,
              (fpath, f_hash, size_bytes, mtime, w, h),
          )
          media_id = cursor.fetchone()["id"]

          vec_np = np.asarray(vec, dtype=np.float32)
          conn.execute(
              """
              INSERT INTO embeddings (media_id, model_name, dimension, vector, is_normalized)
              VALUES (?, ?, ?, ?, 1)
              ON CONFLICT(media_id, model_name) DO UPDATE SET vector=excluded.vector
              """,
              (media_id, model, len(vec_np), vec_np.tobytes()),
          )
          indexed_count += 1
        conn.commit()

      if progress_callback:
        progress_callback({
            'total': total_items,
            'current': indexed_count + skipped_count,
            'status': f"Indexed {indexed_count}/{len(unindexed_images)} images...",
        })

    with self.get_connection() as conn:
      existing_vids = conn.execute(
          """
          SELECT DISTINCT m.video_source_path FROM indexed_media m
          JOIN embeddings e ON m.id = e.media_id
          WHERE m.video_source_path IS NOT NULL AND e.model_name = ?
          """,
          (model,),
      ).fetchall()
      existing_vid_paths = set(r["video_source_path"] for r in existing_vids)

    unindexed_videos = [v for v in video_files if v not in existing_vid_paths]
    skipped_count += len(video_files) - len(unindexed_videos)

    for vpath in unindexed_videos:
      if progress_callback:
        progress_callback({
            'total': total_items,
            'current': indexed_count + skipped_count,
            'status': f"Extracting keyframes from video: {os.path.basename(vpath)}...",
        })
      v_res = self.index_video(
          vpath,
          engine,
          model_name=model,
          method=video_method,
          ssim_threshold=video_ssim_threshold,
          interval_seconds=video_interval_seconds,
          uniform_count=video_uniform_count,
      )
      indexed_count += v_res.get('keyframes_indexed', 0)

    self._invalidate_cache(model)
    return {
        'total_files': total_items,
        'indexed': indexed_count,
        'skipped': skipped_count,
        'model_name': model,
    }

  def _load_matrix(self, model_name: str) -> Dict[str, Any]:
    with self._lock:
      if model_name in self._matrix_cache:
        return self._matrix_cache[model_name]

    with self.get_connection() as conn:
      rows = conn.execute(
          """
          SELECT m.id, m.file_path, m.media_type, m.video_source_path,
                 m.timestamp_seconds, m.width, m.height, e.vector, e.dimension
          FROM indexed_media m
          JOIN embeddings e ON m.id = e.media_id
          WHERE e.model_name = ?
          ORDER BY m.id ASC
          """,
          (model_name,),
      ).fetchall()

      if not rows:
        empty = {
            'matrix': np.empty((0, 512), dtype=np.float32),
            'media_ids': [],
            'file_paths': [],
            'metadata': [],
        }
        return empty

      vectors = []
      media_ids = []
      file_paths = []
      metadata = []

      for r in rows:
        vec = np.frombuffer(r["vector"], dtype=np.float32)
        vectors.append(vec)
        media_ids.append(r["id"])
        file_paths.append(r["file_path"])
        metadata.append({
            'id': r["id"],
            'file_path': r["file_path"],
            'media_type': r["media_type"],
            'video_source_path': r["video_source_path"],
            'timestamp_seconds': r["timestamp_seconds"],
            'width': r["width"],
            'height': r["height"],
        })

      matrix = np.vstack(vectors).astype(np.float32)
      cache_obj = {
          'matrix': matrix,
          'media_ids': media_ids,
          'file_paths': file_paths,
          'metadata': metadata,
      }
      self._matrix_cache[model_name] = cache_obj
      return cache_obj

  def _get_ann_index(self, model_name: str, metric: str = "cosine") -> FlintANNIndex:
    key = f"{model_name}_{metric}"
    if key not in self._ann_cache:
      cache_obj = self._load_matrix(model_name)
      matrix = cache_obj['matrix']
      self._ann_cache[key] = FlintANNIndex(metric=metric).build(matrix)
    return self._ann_cache[key]

  def search_by_vector(
      self,
      query_vector: Union[Sequence[float], np.ndarray],
      model_name: str,
      threshold: float = 0.0,
      metric: str = "cosine",
      top_k: Optional[int] = None,
      filter_paths: Optional[Sequence[str]] = None,
      search_mode: str = "exact",
  ) -> List[Dict[str, Any]]:
    cache_obj = self._load_matrix(model_name)
    matrix = cache_obj['matrix']
    if matrix.shape[0] == 0:
      return []

    q_vec = np.asarray(query_vector, dtype=np.float32)
    metadata = cache_obj['metadata']
    is_ann = search_mode.lower() in ("ann", "approx", "approximate") and matrix.shape[0] >= 64

    if is_ann:
      ann_idx = self._get_ann_index(model_name, metric=metric)
      cand_indices = ann_idx.query_candidates(q_vec)
      sub_matrix = matrix[cand_indices]
    else:
      cand_indices = np.arange(matrix.shape[0], dtype=np.int32)
      sub_matrix = matrix

    if metric == "cosine":
      q_norm = np.linalg.norm(q_vec)
      if q_norm > 0:
        q_vec = q_vec / q_norm
      m_norms = np.linalg.norm(sub_matrix, axis=1, keepdims=True)
      m_norms[m_norms == 0] = 1.0
      normed_m = sub_matrix / m_norms
      scores = np.dot(normed_m, q_vec)
      if threshold <= 0.0:
        valid_mask = np.ones(scores.shape[0], dtype=bool)
      else:
        valid_mask = scores >= threshold
      local_indices = np.where(valid_mask)[0]
      sorted_local_idx = local_indices[np.argsort(-scores[local_indices])]
      sorted_idx = cand_indices[sorted_local_idx]
      mapped_scores = {cand_indices[i]: float(scores[i]) for i in local_indices}

    elif metric == "dot":
      scores = np.dot(sub_matrix, q_vec)
      if threshold <= 0.0:
        valid_mask = np.ones(scores.shape[0], dtype=bool)
      else:
        valid_mask = scores >= threshold
      local_indices = np.where(valid_mask)[0]
      sorted_local_idx = local_indices[np.argsort(-scores[local_indices])]
      sorted_idx = cand_indices[sorted_local_idx]
      mapped_scores = {cand_indices[i]: float(scores[i]) for i in local_indices}

    elif metric == "euclidean":
      diff = sub_matrix - q_vec
      dists = np.linalg.norm(diff, axis=1)
      if threshold <= 0.0:
        valid_mask = np.ones(dists.shape[0], dtype=bool)
      else:
        valid_mask = dists <= threshold
      local_indices = np.where(valid_mask)[0]
      sorted_local_idx = local_indices[np.argsort(dists[local_indices])]
      sorted_idx = cand_indices[sorted_local_idx]
      mapped_scores = {cand_indices[i]: float(dists[i]) for i in local_indices}

    else:
      raise ValueError(f"Unsupported metric: {metric}")

    if filter_paths:
      filter_set = set(os.path.abspath(p) for p in filter_paths)
      sorted_idx = [idx for idx in sorted_idx if os.path.abspath(metadata[idx]['file_path']) in filter_set or (metadata[idx].get('video_source_path') and os.path.abspath(metadata[idx]['video_source_path']) in filter_set)]

    if top_k is not None and top_k > 0:
      sorted_idx = sorted_idx[:top_k]

    results = []
    for idx in sorted_idx:
      meta = dict(metadata[idx])
      score_val = mapped_scores.get(idx, 0.0)
      meta['score'] = score_val
      meta['similarity_pct'] = round(score_val * 100, 2) if metric != "euclidean" else round(max(0, (1 - score_val)) * 100, 2)
      results.append(meta)

    return results

  def search_by_multi_vectors(
      self,
      target_vectors: List[Dict[str, Any]],
      model_name: str,
      threshold: float = 0.0,
      metric: str = "cosine",
      aggregation: str = "max",
      top_k: Optional[int] = None,
      filter_paths: Optional[Sequence[str]] = None,
      search_mode: str = "exact",
  ) -> List[Dict[str, Any]]:
    cache_obj = self._load_matrix(model_name)
    matrix = cache_obj['matrix']
    if matrix.shape[0] == 0 or not target_vectors:
      return []

    metadata = cache_obj['metadata']
    q_matrix = np.vstack([t['vector'] for t in target_vectors]).astype(np.float32)
    is_ann = search_mode.lower() in ("ann", "approx", "approximate") and matrix.shape[0] >= 64

    if is_ann:
      ann_idx = self._get_ann_index(model_name, metric=metric)
      cand_indices = ann_idx.query_multi_candidates(q_matrix)
      sub_matrix = matrix[cand_indices]
    else:
      cand_indices = np.arange(matrix.shape[0], dtype=np.int32)
      sub_matrix = matrix

    if metric == "cosine":
      q_norms = np.linalg.norm(q_matrix, axis=1, keepdims=True)
      q_norms[q_norms == 0] = 1.0
      normed_q = q_matrix / q_norms

      m_norms = np.linalg.norm(sub_matrix, axis=1, keepdims=True)
      m_norms[m_norms == 0] = 1.0
      normed_m = sub_matrix / m_norms

      sim_matrix = np.dot(normed_m, normed_q.T)

      if aggregation == "max":
        agg_scores = np.max(sim_matrix, axis=1)
        best_target_idx = np.argmax(sim_matrix, axis=1)
      else:
        agg_scores = np.mean(sim_matrix, axis=1)
        best_target_idx = np.argmax(sim_matrix, axis=1)

      if threshold <= 0.0:
        valid_mask = np.ones(agg_scores.shape[0], dtype=bool)
      else:
        valid_mask = agg_scores >= threshold
      local_indices = np.where(valid_mask)[0]
      sorted_local_idx = local_indices[np.argsort(-agg_scores[local_indices])]
      sorted_idx = cand_indices[sorted_local_idx]

    elif metric == "dot":
      sim_matrix = np.dot(sub_matrix, q_matrix.T)
      if aggregation == "max":
        agg_scores = np.max(sim_matrix, axis=1)
        best_target_idx = np.argmax(sim_matrix, axis=1)
      else:
        agg_scores = np.mean(sim_matrix, axis=1)
        best_target_idx = np.argmax(sim_matrix, axis=1)

      if threshold <= 0.0:
        valid_mask = np.ones(agg_scores.shape[0], dtype=bool)
      else:
        valid_mask = agg_scores >= threshold
      local_indices = np.where(valid_mask)[0]
      sorted_local_idx = local_indices[np.argsort(-agg_scores[local_indices])]
      sorted_idx = cand_indices[sorted_local_idx]

    elif metric == "euclidean":
      dists_list = []
      for q in q_matrix:
        d = np.linalg.norm(sub_matrix - q, axis=1)
        dists_list.append(d)
      sim_matrix = np.column_stack(dists_list)

      if aggregation == "max":
        agg_scores = np.min(sim_matrix, axis=1)
        best_target_idx = np.argmin(sim_matrix, axis=1)
      else:
        agg_scores = np.mean(sim_matrix, axis=1)
        best_target_idx = np.argmin(sim_matrix, axis=1)

      if threshold <= 0.0:
        valid_mask = np.ones(agg_scores.shape[0], dtype=bool)
      else:
        valid_mask = agg_scores <= threshold
      local_indices = np.where(valid_mask)[0]
      sorted_local_idx = local_indices[np.argsort(agg_scores[local_indices])]
      sorted_idx = cand_indices[sorted_local_idx]

    else:
      raise ValueError(f"Unsupported metric: {metric}")

    if filter_paths:
      filter_set = set(os.path.abspath(p) for p in filter_paths)
      filtered_local_pairs = [(idx, l_idx) for idx, l_idx in zip(sorted_idx, sorted_local_idx) if os.path.abspath(metadata[idx]['file_path']) in filter_set or (metadata[idx].get('video_source_path') and os.path.abspath(metadata[idx]['video_source_path']) in filter_set)]
      if filtered_local_pairs:
        sorted_idx, sorted_local_idx = zip(*filtered_local_pairs)
      else:
        sorted_idx, sorted_local_idx = [], []

    if top_k is not None and top_k > 0:
      sorted_idx = sorted_idx[:top_k]
      sorted_local_idx = sorted_local_idx[:top_k]

    results = []
    for idx, l_idx in zip(sorted_idx, sorted_local_idx):
      meta = dict(metadata[idx])
      score_val = float(agg_scores[l_idx])
      t_idx = int(best_target_idx[l_idx])
      best_t = target_vectors[t_idx]

      meta['score'] = score_val
      meta['similarity_pct'] = round(score_val * 100, 2) if metric != "euclidean" else round(max(0, (1 - score_val)) * 100, 2)
      meta['best_target_label'] = best_t.get('label', '')
      meta['best_target_path'] = best_t.get('file_path', '')

      item_target_scores = []
      for t_i, t_obj in enumerate(target_vectors):
        t_score = float(sim_matrix[l_idx, t_i])
        t_pct = round(t_score * 100, 2) if metric != "euclidean" else round(max(0, (1 - t_score)) * 100, 2)
        item_target_scores.append({
            'target_label': t_obj.get('label', ''),
            'target_path': t_obj.get('file_path', ''),
            'score': t_score,
            'similarity_pct': t_pct,
        })
      meta['all_target_scores'] = item_target_scores

      results.append(meta)

    return results

  def search_cross_models(
      self,
      target_vectors_by_model: Dict[str, List[Dict[str, Any]]],
      threshold: float = 0.0,
      metric: str = "auto",
      aggregation: str = "max",
      top_k: Optional[int] = None,
      filter_paths: Optional[Sequence[str]] = None,
      search_mode: str = "exact",
  ) -> Dict[str, Any]:
    # No circular import
    models_results = {}
    for m_key, t_vecs in target_vectors_by_model.items():
      if not t_vecs:
        continue
      m_config = MODEL_CONFIGS.get(m_key, {})
      m_name = m_config.get('name', m_key)
      m_metric = metric if (metric and metric != "auto") else m_config.get('default_metric', 'cosine')

      matches = self.search_by_multi_vectors(
          target_vectors=t_vecs,
          model_name=m_name,
          threshold=threshold,
          metric=m_metric,
          aggregation=aggregation,
          top_k=top_k,
          filter_paths=filter_paths,
          search_mode=search_mode,
      )
      models_results[m_key] = {
          'model_key': m_key,
          'display_name': m_config.get('display_name', m_key),
          'metric_used': m_metric,
          'matches': matches,
          'num_matches': len(matches),
      }
    return models_results

  def ensure_embeddings_for_model(
      self,
      engine: Any,
      model_name: Optional[str] = None,
      progress_callback: Optional[Callable[[int, int, str], None]] = None,
  ) -> int:
    """Ensures all indexed media in the SQLite database have embeddings for the specified model."""
    model = model_name or getattr(engine, "model_name", "default")
    with self.get_connection() as conn:
      rows = conn.execute(
          """
          SELECT m.id, m.file_path, m.media_type
          FROM indexed_media m
          LEFT JOIN embeddings e ON m.id = e.media_id AND e.model_name = ?
          WHERE e.id IS NULL
          ORDER BY m.id ASC
          """,
          (model,),
      ).fetchall()

    if not rows:
      return 0

    total = len(rows)
    computed = 0
    for idx, row in enumerate(rows):
      media_id = row["id"]
      f_path = row["file_path"]
      m_type = row["media_type"]
      
      if progress_callback:
        progress_callback(idx + 1, total, f"Computing embeddings for {os.path.basename(f_path)}")

      if not os.path.exists(f_path):
        continue

      try:
        vec = engine.compute_image_embedding(f_path, normalize=True)
        vec_np = np.asarray(vec, dtype=np.float32)
        with self.get_connection() as conn:
          conn.execute(
              """
              INSERT INTO embeddings (media_id, model_name, dimension, vector, is_normalized)
              VALUES (?, ?, ?, ?, 1)
              ON CONFLICT(media_id, model_name) DO UPDATE SET vector=excluded.vector
              """,
              (media_id, model, len(vec_np), vec_np.tobytes()),
          )
          conn.commit()
        computed += 1
      except Exception:
        continue

    self._invalidate_cache(model)
    return computed

  def get_stats(self) -> Dict[str, Any]:
    # No circular import
    with self.get_connection() as conn:
      cur = conn.cursor()
      cur.execute("SELECT COUNT(*) FROM indexed_media")
      total_media = cur.fetchone()[0]

      cur.execute("SELECT COUNT(*) FROM indexed_media WHERE media_type = 'image'")
      total_images = cur.fetchone()[0]

      cur.execute("SELECT COUNT(*) FROM indexed_media WHERE media_type = 'video'")
      total_videos = cur.fetchone()[0]

      cur.execute("SELECT COUNT(*) FROM indexed_media WHERE media_type = 'video_keyframe'")
      total_keyframes = cur.fetchone()[0]

      cur.execute("SELECT COUNT(DISTINCT model_name) FROM embeddings")
      models_count = cur.fetchone()[0]

      cur.execute("SELECT DISTINCT model_name FROM embeddings")
      raw_models = [r[0] for r in cur.fetchall()]

      models_indexed = list(raw_models)

      return {
          'total_media': total_media,
          'total_images': total_images,
          'total_videos': total_videos,
          'total_keyframes': total_keyframes,
          'models_indexed_count': models_count,
          'models_indexed': models_indexed,
          'db_path': self.db_path,
          'db_size_bytes': os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0,
      }

  def log_search_run(
      self,
      query_type: str,
      query_summary: str,
      model_name: str,
      threshold: float,
      metric: str,
      results_count: int,
      duration_ms: float,
  ) -> int:
    with self.get_connection() as conn:
      cur = conn.cursor()
      cur.execute(
          """
          INSERT INTO search_runs (query_type, query_summary, model_name, threshold, metric, results_count, duration_ms)
          VALUES (?, ?, ?, ?, ?, ?, ?)
          """,
          (query_type, query_summary, model_name, threshold, metric, results_count, duration_ms),
      )
      conn.commit()
      return cur.lastrowid

  def get_known_targets(self, group_name: Optional[str] = None) -> List[Dict[str, Any]]:
    targets = self.get_all_known_targets()
    if group_name:
      return [t for t in targets if t.get('group_name') == group_name]
    return targets

  def clear_database(self):
    with self.get_connection() as conn:
      conn.execute("DELETE FROM embeddings")
      conn.execute("DELETE FROM indexed_media")
      conn.execute("DELETE FROM search_runs")
      conn.execute("DELETE FROM sqlite_sequence")
      conn.commit()
    self._invalidate_cache()

  def delete_known_target(self, target_id: Optional[int] = None, file_path: Optional[str] = None) -> bool:
    with self.get_connection() as conn:
      cur = conn.cursor()
      if target_id is not None:
        cur.execute("DELETE FROM known_targets WHERE id = ?", (target_id,))
      elif file_path is not None:
        cur.execute("DELETE FROM known_targets WHERE file_path = ?", (file_path,))
      else:
        return False
      conn.commit()
      return cur.rowcount > 0

  def delete_known_target_group(self, group_name: str) -> int:
    with self.get_connection() as conn:
      cur = conn.cursor()
      cur.execute("DELETE FROM known_targets WHERE group_name = ?", (group_name,))
      conn.commit()
      return cur.rowcount

  def add_known_target(
      self,
      label: str,
      file_path: str,
      group_name: str = "default",
      crop_box: Optional[Any] = None,
  ) -> int:
    crop_json = json.dumps(crop_box) if crop_box else None
    clean_p = os.path.abspath(file_path)
    with self.get_connection() as conn:
      cur = conn.cursor()
      cur.execute(
          "SELECT id FROM known_targets WHERE file_path = ? OR file_path = ?",
          (file_path, clean_p),
      )
      row = cur.fetchone()
      if row:
        cur.execute(
            """
            UPDATE known_targets 
            SET label = ?, file_path = ?, group_name = ?, crop_box_json = ?
            WHERE id = ?
            """,
            (label, clean_p, group_name, crop_json, row[0]),
        )
        conn.commit()
        return row[0]

      cur.execute(
          """
          INSERT INTO known_targets (label, file_path, group_name, crop_box_json)
          VALUES (?, ?, ?, ?)
          """,
          (label, clean_p, group_name, crop_json),
      )
      conn.commit()
      return cur.lastrowid

  def get_known_target_groups(self) -> List[str]:
    with self.get_connection() as conn:
      cur = conn.cursor()
      cur.execute("SELECT DISTINCT group_name FROM known_targets WHERE group_name IS NOT NULL ORDER BY group_name ASC")
      return [r[0] for r in cur.fetchall() if r[0]]

  def get_all_known_targets(self) -> List[Dict[str, Any]]:
    with self.get_connection() as conn:
      cur = conn.cursor()
      cur.execute(
          """
          SELECT id, label, file_path, group_name, crop_box_json, created_at
          FROM known_targets
          ORDER BY group_name ASC, label ASC
          """
      )
      rows = cur.fetchall()
      return [dict(r) for r in rows]
