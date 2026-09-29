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

import io
import shutil
import collections
# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""High-level service orchestrating FLINT engines, SQLite vector database, and workflows."""

import base64
import csv
import json
from flint.patch_matcher import (
    extract_dense_patch_tokens,
    compute_patch_chamfer_alignment,
    compute_text_patch_localization,
    generate_patch_heatmap_data_url,
    build_patch_matching_forensic_explanation,
)
import os
import re
import time
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
from PIL import Image, ImageOps
from PIL.ExifTags import TAGS, GPSTAGS

from flint.db import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, MediaDatabase
from flint.engine import FlintEngine


import urllib.parse
def clean_path(p: str) -> str:
  if not p:
    return p
  if p.startswith('"') and p.endswith('"'):
    p = p[1:-1].strip()
  if p.startswith("'") and p.endswith("'"):
    p = p[1:-1].strip()
  if p.startswith('file://'):
    p = urllib.parse.unquote(p[7:])
    if (p.startswith('/') or p.startswith('\\')) and sys.platform == 'win32' and len(p) > 2 and p[2] == ':':
      p = p[1:]
  p = p.replace(r'\ ', ' ').replace(r'"', '"').replace(r"'", "'")
  p = os.path.expanduser(p)

  # Check direct path if already existing
  if os.path.exists(p):
    return os.path.abspath(p)

  raw_rel = p.lstrip(r'\/')

  # Check candidates across working directory, parent directory, and workspace sibling folders
  candidates = [
      os.path.normpath(os.path.join(os.getcwd(), p)),
      os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), p)),
      os.path.normpath(os.path.join(os.path.dirname(os.getcwd()), p)),
  ]

  # Check sibling directories under the parent folder (e.g. "../Test Files/known_files")
  try:
    parent_dir = os.path.dirname(os.getcwd())
    if os.path.isdir(parent_dir):
      for entry in os.listdir(parent_dir):
        sub_dir = os.path.join(parent_dir, entry)
        if os.path.isdir(sub_dir) and sub_dir != os.getcwd():
          candidates.append(os.path.normpath(os.path.join(sub_dir, raw_rel)))
          candidates.append(os.path.normpath(os.path.join(sub_dir, os.path.basename(p))))
  except Exception:
    pass

  # Check test_data within package root
  package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  candidates.append(os.path.normpath(os.path.join(package_root, "test_data", p)))

  for cand in candidates:
    if os.path.exists(cand):
      return cand

  return os.path.abspath(p)



def _get_decimal_from_dms(dms, ref):
  try:
    degrees = float(dms[0])
    minutes = float(dms[1])
    seconds = float(dms[2])
    dec = degrees + minutes/60.0 + seconds/3600.0
    if ref in ['S', 'W']:
      dec = -dec
    return dec
  except:
    return None

def extract_exif(filename: str) -> dict:
  try:
    with Image.open(filename) as img:
      exif_data = img.getexif()
      if not exif_data:
        return {}
      labeled = {}
      for k, v in exif_data.items():
        tag = TAGS.get(k, k)
        try:
          if isinstance(v, bytes):
            labeled[tag] = v.decode('utf-8', errors='ignore')
          else:
            labeled[tag] = str(v)
        except:
          labeled[tag] = str(v)
      gps_info = exif_data.get_ifd(0x8825)
      if gps_info:
        gps_dict = {GPSTAGS.get(t, t): gps_info[t] for t in gps_info}
        if 'GPSLatitude' in gps_dict and 'GPSLongitude' in gps_dict:
          lat = _get_decimal_from_dms(gps_dict['GPSLatitude'], gps_dict.get('GPSLatitudeRef', 'N'))
          lon = _get_decimal_from_dms(gps_dict['GPSLongitude'], gps_dict.get('GPSLongitudeRef', 'E'))
          if lat is not None and lon is not None:
            labeled['gps_link'] = f"https://www.google.com/maps?q={lat},{lon}"
      return labeled
  except Exception:
    return {}
def group_matches_by_media(raw_matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
  """
  Groups raw matches so video keyframes are strictly collapsed into a single parent video file card.
  The representative thumbnail/score used for the video is its single highest-scoring keyframe.
  """
  grouped_items = []
  video_map = {}

  for m in raw_matches:
    f_path = clean_path(m.get('file_path', ''))
    v_source = m.get('video_source_path')
    m_type = m.get('media_type', 'image')

    # Detect if this is a video keyframe
    is_keyframe = (
        m_type == 'video_keyframe'
        or (v_source is not None and len(str(v_source).strip()) > 0)
        or ('/keyframes/' in f_path)
        or ('flint_keyframes' in f_path)
        or re.search(r'kf_\d+_\d+\.\d+s\.jpg', f_path) is not None
    )

    if is_keyframe:
      # Determine parent video path
      if v_source:
        v_path = clean_path(v_source)
      elif '/keyframes/' in f_path:
        # e.g. .../.flint_cache/keyframes/IMG_7128/kf_000000_0.00s.jpg -> parent folder IMG_7128
        parent_dir = os.path.dirname(f_path)
        v_folder_name = os.path.basename(parent_dir)
        v_path = f"video://{v_folder_name}"
      else:
        v_path = f"video://{os.path.basename(os.path.dirname(f_path))}"

      if v_path not in video_map:
        v_item = {
            'media_type': 'video',
            'file_path': v_path,
            'video_path': v_path,
            'filename': os.path.basename(v_path).replace('video://', ''),
            'score': m['score'],
            'similarity_pct': m.get('similarity_pct', round(m['score'] * 100, 2)),
            'best_target_label': m.get('best_target_label', ''),
            'best_target_path': m.get('best_target_path', ''),
            'best_target_thumb': m.get('best_target_thumb', ''),
            'query_text': m.get('query_text', ''),
            'is_text_query': m.get('is_text_query', False),
            'all_target_scores': m.get('all_target_scores', []),
            'top_keyframe': m,
            'keyframes': [m],
            'keyframes_count': 1,
            'width': m.get('width', 0),
            'height': m.get('height', 0),
            'exif_data': extract_exif(v_path.replace('video://', '') if 'video://' in v_path else v_path),
        }
        video_map[v_path] = v_item
        grouped_items.append(v_item)
      else:
        v_item = video_map[v_path]
        v_item['keyframes'].append(m)
        v_item['keyframes_count'] = len(v_item['keyframes'])
        # Keep the highest scoring keyframe as the representative
        if m['score'] > v_item['score']:
          v_item['score'] = m['score']
          v_item['similarity_pct'] = m.get('similarity_pct', round(m['score'] * 100, 2))
          v_item['best_target_label'] = m.get('best_target_label', '')
          v_item['best_target_path'] = m.get('best_target_path', '')
          v_item['best_target_thumb'] = m.get('best_target_thumb', '')
          v_item['query_text'] = m.get('query_text', '')
          v_item['is_text_query'] = m.get('is_text_query', False)
          v_item['all_target_scores'] = m.get('all_target_scores', [])
          v_item['top_keyframe'] = m
    else:
      img_item = dict(m)
      img_item['media_type'] = 'image'
      img_item['filename'] = os.path.basename(m['file_path'])
      img_item['exif_data'] = extract_exif(m['file_path'])
      grouped_items.append(img_item)

  # Sort all keyframes inside each video by timestamp and aggregate per-target max scores across keyframes
  for v in video_map.values():
    v['keyframes'].sort(key=lambda k: k.get('timestamp_seconds', 0.0))
    target_best_map = {}
    target_order = []
    for kf in v['keyframes']:
      for ts in kf.get('all_target_scores', []):
        if isinstance(ts, dict):
          t_key = ts.get('target_path') or ts.get('target_label') or ''
          if not t_key:
            continue
          if t_key not in target_best_map:
            target_best_map[t_key] = dict(ts)
            target_order.append(t_key)
          elif ts.get('score', -999.0) > target_best_map[t_key].get('score', -999.0):
            target_best_map[t_key] = dict(ts)
    if target_order:
      v['all_target_scores'] = [target_best_map[k] for k in target_order]

  # Sort all items by overall score descending
  grouped_items.sort(key=lambda x: x['score'], reverse=True)
  return grouped_items


MODEL_CONFIGS = {
    'clip-vit-b-32': {
        'repo_id': 'openai/clip-vit-base-patch32',
        'dir_name': 'clip-vit-b-32',
        'display_name': 'CLIP ViT-B/32 (Fast Baseline)',
        'description': 'Balanced speed and semantic retrieval accuracy (512-dim).',
        'is_vision_only': False,
        'default_metric': 'cosine',
    },
    'siglip-base': {
        'repo_id': 'google/siglip-base-patch16-224',
        'dir_name': 'siglip-base',
        'display_name': 'SigLIP Base (High Accuracy)',
        'description': 'High precision global image representation (768-dim).',
        'is_vision_only': False,
        'default_metric': 'cosine',
    },
    'siglip2-base': {
        'repo_id': 'google/siglip2-base-patch16-224',
        'dir_name': 'siglip2-base',
        'display_name': 'SigLIP2 Base',
        'description': 'Next-gen pairwise sigmoid loss model.',
        'is_vision_only': False,
        'default_metric': 'cosine',
    },
    'siglip2-naflex': {
        'repo_id': 'google/siglip2-base-patch16-naflex',
        'dir_name': 'siglip2-naflex',
        'display_name': 'SigLIP2 NaFlex (Crop Optimized)',
        'description': 'Native aspect ratio preservation for intricate crop matching.',
        'is_vision_only': False,
        'default_metric': 'cosine',
    },
    'mobileclip': {
        'repo_id': 'apple/mobileclip_s0_timm',
        'dir_name': 'mobileclip-s0',
        'display_name': 'mobileCLIP S0 (Ultra Fast)',
        'description': 'Apple FastViT edge architecture for high-speed triage (512-dim).',
        'is_vision_only': False,
        'default_metric': 'cosine',
    },
    'openclip-laion': {
        'repo_id': 'laion/CLIP-ViT-B-32-laion2B-s34B-b79K',
        'dir_name': 'openclip-laion-b-32',
        'display_name': 'OpenCLIP LAION-2B (Ultra Fast)',
        'description': 'High-speed open vision-language model trained on LAION-2B (512-dim).',
        'is_vision_only': False,
        'default_metric': 'cosine',
    },
    'dinov3': {
        'repo_id': 'facebook/dinov3-vitb16-pretrain-lvd1689m',
        'dir_name': 'dinov3-vitb16-pretrain-lvd1689m',
        'display_name': 'DINOv3 ViT-B/16 (Vision Only)',
        'description': 'Dense self-supervised pixel & structural representations (768-dim, vision only).',
        'is_vision_only': True,
        'default_metric': 'cosine',
    },
    'clip-vit-large': {
        'repo_id': 'openai/clip-vit-large-patch14',
        'dir_name': 'clip-vit-large-patch14',
        'display_name': 'CLIP ViT-L/14 (High Precision)',
        'description': 'High resolution 768-dim CLIP representation for fine details.',
        'is_vision_only': False,
        'default_metric': 'cosine',
    },
}



def parse_raw_embedding_query(query: str) -> Optional[Union[np.ndarray, Dict[str, np.ndarray]]]:
  """Detects if query is a serialized vector/embedding string and parses it into numpy float array(s).
  
  Supports:
    1. Standard JSON array: [-0.0033, -0.0460, ...]
    2. Multi-model JSON dict: {"clip-vit-b-32": [...], "siglip2-naflex": [...]}
    3. Prefixed vector strings: "768 dims: [-0.0033, ...]"
    4. Comma / whitespace separated floats: -0.0033, -0.0460, ...
    5. Base64-encoded float32 binary buffers
  """
  if not isinstance(query, str):
    return None

  q = query.strip()
  if not q:
    return None

  # 1. Try standard JSON dict format: {"clip-vit-b-32": [...], ...}
  if q.startswith('{') and q.endswith('}'):
    try:
      d = json.loads(q)
      if isinstance(d, dict):
        parsed_dict = {}
        for k, v in d.items():
          if isinstance(v, (list, tuple)) and len(v) >= 64:
            parsed_dict[k] = np.asarray(v, dtype=np.float32)
        if parsed_dict:
          return parsed_dict
    except Exception:
      pass

  # 2. Try standard JSON array format: [-0.0033, ...]
  if q.startswith('[') and q.endswith(']'):
    try:
      arr = json.loads(q)
      if isinstance(arr, (list, tuple)) and len(arr) >= 64:
        return np.asarray(arr, dtype=np.float32)
    except Exception:
      pass

  # 3. If contains bracketed vector (e.g. "768 dims: [...]" or "[0.1, 0.2, ...]")
  bracket_match = re.search(r'\[(.*?)\]', q, re.DOTALL)
  if bracket_match:
    inner = bracket_match.group(1).strip()
    nums = re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?', inner)
    if len(nums) >= 64:
      try:
        return np.asarray([float(x) for x in nums], dtype=np.float32)
      except Exception:
        pass

  # 4. Try base64-encoded float32 buffer
  if len(q) >= 256 and not re.search(r'[^A-Za-z0-9+/=]', q):
    try:
      raw_bytes = base64.b64decode(q)
      if len(raw_bytes) % 4 == 0:
        vec = np.frombuffer(raw_bytes, dtype=np.float32)
        if len(vec) in (512, 768, 1024, 1152, 1536):
          return vec
    except Exception:
      pass

  # 5. Plain comma or whitespace separated floats with at least 64 numbers
  nums = re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?', q)
  if len(nums) >= 64:
    try:
      return np.asarray([float(x) for x in nums], dtype=np.float32)
    except Exception:
      pass

  return None

class FlintService:
  """Main service layer for FLINT Vision Engine operations."""

  def __init__(
      self,
      models_dir: str = "models",
      databases_dir: str = "databases",
      db_path: Optional[str] = None,
      default_model: str = "clip-vit-b-32",
      device: Optional[str] = None,
  ):
    self.models_dir = clean_path(models_dir)
    os.makedirs(self.models_dir, exist_ok=True)
    self.databases_dir = clean_path(databases_dir)
    os.makedirs(self.databases_dir, exist_ok=True)

    if db_path:
      active_db = clean_path(db_path)
    else:
      active_db = os.path.join(self.databases_dir, "default.sqlite")
      if not os.path.exists(active_db) and os.path.exists("flint_database.sqlite"):
        import shutil
        try:
          shutil.copy2("flint_database.sqlite", active_db)
        except Exception:
          pass

    self.db = MediaDatabase(active_db)
    self.device = device
    self.active_model_key = default_model
    self._loaded_engines: Dict[str, FlintEngine] = {}

    available = self.list_available_models()
    if default_model not in [m['key'] for m in available if m['downloaded']]:
      for m in available:
        if m['downloaded']:
          self.active_model_key = m['key']
          break



  def load_database_investigation(
      self,
      db_name_or_path: Optional[str] = None,
      known_targets: Optional[Union[str, Sequence[str]]] = None,
      search_mode: str = "exact",
  ) -> Dict[str, Any]:
    """Loads all media, keyframes, and model vectors from an existing database into an Investigate dataset."""
    t0 = time.time()
    if db_name_or_path:
      self.set_active_database(db_name_or_path)

    db_filename = os.path.basename(self.db.db_path)
    stats = self.db.get_stats()
    models_stored = stats.get('models_indexed', [])
    if not models_stored:
      models_stored = [self.active_model_key]

    all_db_targets = self.db.get_all_known_targets()
    active_target_paths = []
    if all_db_targets:
      active_target_paths = [t for t in all_db_targets if t.get('file_path') and os.path.exists(clean_path(t['file_path']))]
    elif known_targets:
      if isinstance(known_targets, str):
        active_target_paths = [clean_path(known_targets)]
      else:
        active_target_paths = [clean_path(p) if isinstance(p, str) else p for p in known_targets if p]
    else:
      # Check session file for saved knownPath or reference_targets
      session_file_p = os.path.abspath("flint_session.json")
      if os.path.exists(session_file_p):
        try:
          with open(session_file_p, 'r') as sf:
            s_data = json.load(sf)
            s_known = s_data.get('knownPath') or s_data.get('known_path')
            if s_known and os.path.exists(clean_path(s_known)):
              active_target_paths = [clean_path(s_known)]
            elif s_data.get('knownTargets') and isinstance(s_data.get('knownTargets'), list):
              for t in s_data['knownTargets']:
                tp = clean_path(t.get('file_path') if isinstance(t, dict) else t)
                if tp and os.path.exists(tp):
                  active_target_paths.append(tp)
        except Exception:
          pass

    # If active_target_paths exist, immediately compute similarity matches across the database with zero re-indexing
    if active_target_paths:
      try:
        res = self.search_known_vs_unknown(
            known_input=active_target_paths,
            unknown_folder=None,
            models=models_stored,
            threshold=0.0,
            search_mode=search_mode,
            auto_index=False,
        )
        res['database_name'] = db_filename
        res['known_targets'] = self.db.get_all_known_targets() or res.get('known_targets', [])
        return res
      except Exception:
        pass

    with self.db.get_connection() as conn:
      rows = conn.execute("""
          SELECT m.id, m.file_path, m.file_size, m.media_type, m.timestamp_seconds,
                 m.video_source_path, m.width, m.height, m.indexed_at
          FROM indexed_media m
          ORDER BY m.id ASC
      """).fetchall()

      raw_items = []
      for r in rows:
        d = dict(r)
        d['score'] = 0.0
        d['similarity_pct'] = 0.0
        d['filename'] = os.path.basename(d['file_path'])
        raw_items.append(d)

    matches = group_matches_by_media(raw_items)
    elapsed_ms = (time.time() - t0) * 1000.0

    models_results = {}
    for m in models_stored:
      models_results[m] = {
          'model_key': m,
          'display_name': MODEL_CONFIGS.get(m, {}).get('display_name', m),
          'metric_used': 'cosine',
          'matches': matches,
          'num_matches': len(matches),
      }

    return {
        'success': True,
        'query_type': 'database_archive',
        'database_name': db_filename,
        'primary_model': models_stored[0] if models_stored else self.active_model_key,
        'model_name': models_stored[0] if models_stored else self.active_model_key,
        'models_computed': models_stored,
        'models_results': models_results,
        'threshold': 0.0,
        'metric': 'cosine',
        'aggregation': 'max',
        'duration_ms': round(elapsed_ms, 2),
        'known_targets': self.db.get_all_known_targets(),
        'unknown_folder': f"databases/{db_filename}",
        'total_scanned': len(matches),
        'num_matches': len(matches),
        'raw_matches_count': len(raw_items),
        'matches': matches,
    }

  def list_databases(self) -> List[Dict[str, Any]]:
    """Lists all available SQLite databases in the databases directory with metadata."""
    results = []
    if not os.path.isdir(self.databases_dir):
      return results

    current_active_path = os.path.abspath(self.db.db_path)
    for fname in sorted(os.listdir(self.databases_dir)):
      if fname.endswith(('.sqlite', '.db')):
        full_p = os.path.join(self.databases_dir, fname)
        size_bytes = os.path.getsize(full_p) if os.path.exists(full_p) else 0
        media_count = 0
        models_stored = []
        try:
          temp_db = MediaDatabase(full_p)
          stats = temp_db.get_stats()
          media_count = stats.get('total_media', 0)
          models_stored = stats.get('models_indexed', [])
        except Exception:
          pass

        is_active = os.path.abspath(full_p) == current_active_path
        results.append({
            'filename': fname,
            'path': full_p,
            'size_bytes': size_bytes,
            'size_formatted': f"{size_bytes / (1024*1024):.1f} MB",
            'media_count': media_count,
            'models_stored': models_stored,
            'is_active': is_active,
        })
    return results

  def set_active_database(self, db_name_or_path: str) -> Dict[str, Any]:
    """Switches the active SQLite database to an existing or newly selected database."""
    raw_str = db_name_or_path.strip()
    if os.path.isabs(raw_str):
      full_p = clean_path(raw_str)
    else:
      full_p = os.path.join(self.databases_dir, os.path.basename(raw_str))

    if not full_p.endswith(('.sqlite', '.db')):
      full_p += '.sqlite'

    self.db = MediaDatabase(clean_path(full_p))
    return {
        'success': True,
        'filename': os.path.basename(full_p),
        'path': full_p,
        'stats': self.db.get_stats(),
    }

  def create_database(self, db_name: str) -> Dict[str, Any]:
    """Creates a new named SQLite database in the databases directory and sets it active."""
    cleaned_name = os.path.basename(db_name.strip())
    if not cleaned_name:
      cleaned_name = f"database_{int(time.time())}.sqlite"
    if not cleaned_name.endswith(('.sqlite', '.db')):
      cleaned_name += '.sqlite'

    full_p = os.path.join(self.databases_dir, cleaned_name)
    self.db = MediaDatabase(full_p)
    return {
        'success': True,
        'filename': cleaned_name,
        'path': full_p,
        'stats': self.db.get_stats(),
    }

  def list_available_models(self) -> List[Dict[str, Any]]:
    results = []
    for key, cfg in MODEL_CONFIGS.items():
      local_path = os.path.join(self.models_dir, cfg['dir_name'])
      has_files = (
          os.path.isdir(local_path)
          and len(os.listdir(local_path)) > 0
          and any(f.endswith(('.bin', '.safetensors', '.json')) for f in os.listdir(local_path))
      )
      results.append({
          'key': key,
          'display_name': cfg['display_name'],
          'repo_id': cfg['repo_id'],
          'local_path': local_path,
          'downloaded': has_files,
          'is_active': key == self.active_model_key,
          'description': cfg['description'],
          'is_vision_only': cfg['is_vision_only'],
          'default_metric': cfg['default_metric'],
      })
    return results

  def is_model_available(self, model_key: str) -> bool:
    """Checks if model weights are present on disk or already loaded in memory."""
    if model_key not in MODEL_CONFIGS:
      return False
    if model_key in self._loaded_engines:
      return True
    cfg = MODEL_CONFIGS[model_key]
    local_path = os.path.join(self.models_dir, cfg.get('dir_name', ''))
    return (
        os.path.isdir(local_path)
        and len(os.listdir(local_path)) > 0
        and any(f.endswith(('.bin', '.safetensors', '.json')) for f in os.listdir(local_path))
    )

  def get_engine(self, model_key: Optional[str] = None) -> FlintEngine:
    key = model_key or self.active_model_key
    if key not in MODEL_CONFIGS:
      raise ValueError(f"Unknown model key: {key}")

    if key in self._loaded_engines:
      return self._loaded_engines[key]

    cfg = MODEL_CONFIGS[key]
    local_path = os.path.join(self.models_dir, cfg['dir_name'])
    has_files = (
        os.path.exists(local_path)
        and len(os.listdir(local_path)) > 0
        and any(f.endswith(('.bin', '.safetensors', '.json')) for f in os.listdir(local_path))
    )
    if not has_files:
      if key in ('clip-vit-b-32', 'siglip-base', 'siglip2-base', 'siglip2-naflex'):
        print(f"⬇️ Initializing model '{key}' weights from {cfg['repo_id']}...")
        os.makedirs(local_path, exist_ok=True)
        try:
          from huggingface_hub import snapshot_download
          snapshot_download(cfg['repo_id'], local_dir=local_path)
          print(f"✅ Model '{key}' successfully downloaded to {local_path}")
        except Exception as e:
          raise FileNotFoundError(
              f"Model '{key}' is not downloaded at {local_path} and auto-download failed: {e}. Please download it from the Settings tab."
          )
      else:
        raise FileNotFoundError(
            f"Model '{key}' is not downloaded at {local_path}. Please download it first."
        )

    engine = FlintEngine(
        model_path=local_path,
        device=self.device,
        is_vision_only=cfg['is_vision_only'],
    )
    engine.model_name = key
    self._loaded_engines[key] = engine
    return engine

  def set_active_model(self, model_key: str):
    if model_key not in MODEL_CONFIGS:
      raise ValueError(f"Invalid model key: {model_key}")
    self.active_model_key = model_key
    self.get_engine(model_key)

  def parse_known_inputs(
      self,
      known_input: Union[str, Sequence[str], Image.Image, Sequence[Image.Image]],
      base_dir: Optional[str] = None,
  ) -> List[Dict[str, Any]]:
    targets = []
    if isinstance(known_input, str):
      cleaned = clean_path(known_input)
      if os.path.isdir(cleaned):
        current_base = base_dir or cleaned
        for root, _, files in os.walk(cleaned):
          rel_folder = os.path.relpath(root, current_base)
          folder_group = os.path.basename(root) if (rel_folder != "." and rel_folder != "") else "General"
          for f in sorted(files):
            if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS:
              full_p = os.path.join(root, f)
              targets.append({
                  'label': f,
                  'file_path': full_p,
                  'group_name': folder_group,
                  'source': 'folder',
              })
      elif os.path.isfile(cleaned):
        parent_dir = os.path.basename(os.path.dirname(cleaned)) or "General"
        targets.append({
            'label': os.path.basename(cleaned),
            'file_path': cleaned,
            'group_name': parent_dir,
            'source': 'single_file',
        })
      else:
        raise FileNotFoundError(f"Known input path not found: {cleaned}")
    elif isinstance(known_input, (list, tuple)):
      for item in known_input:
        if isinstance(item, str):
          cleaned_item = clean_path(item)
          if os.path.isfile(cleaned_item):
            parent_dir = os.path.basename(os.path.dirname(cleaned_item)) or "General"
            targets.append({
                'label': os.path.basename(cleaned_item),
                'file_path': cleaned_item,
                'group_name': parent_dir,
                'source': 'list',
            })
          elif os.path.isdir(cleaned_item):
            sub_targets = self.parse_known_inputs(cleaned_item, base_dir=base_dir or os.path.dirname(cleaned_item))
            targets.extend(sub_targets)
        elif isinstance(item, dict):
          if 'file_path' in item:
            item['file_path'] = clean_path(item['file_path'])
            if not item.get('group_name') or item.get('group_name') == 'default':
              parent_dir = os.path.basename(os.path.dirname(item['file_path'])) or "General"
              item['group_name'] = parent_dir
          targets.append(item)
    return targets

  def search_known_vs_unknown(
      self,
      known_input: Union[str, Sequence[str]],
      unknown_folder: Optional[str] = None,
      threshold: float = 0.0,
      metric: str = "cosine",
      aggregation: str = "max",
      top_k: Optional[int] = None,
      recursive: bool = True,
      include_videos: bool = True,
      video_method: str = "ssim",
      video_ssim_threshold: float = 0.65,
      video_interval_seconds: float = 1.0,
      video_uniform_count: int = 10,
      model_key: Optional[str] = None,
      models: Optional[Sequence[str]] = None,
      auto_index: bool = True,
      progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
      search_mode: str = "exact",
  ) -> Dict[str, Any]:
    t0 = time.time()
    
    # Determine all models to compute
    models_to_run = []
    if models:
      for m in models:
        if m in MODEL_CONFIGS and self.is_model_available(m) and m not in models_to_run:
          models_to_run.append(m)
    if not models_to_run:
      primary = (
          model_key
          if (model_key in MODEL_CONFIGS and self.is_model_available(model_key))
          else (self.active_model_key if self.is_model_available(self.active_model_key) else 'clip-vit-b-32')
      )
      models_to_run = [primary]

    primary_model = self.active_model_key if self.active_model_key in models_to_run else models_to_run[0]
    targets_info = self.parse_known_inputs(known_input)
    if not targets_info:
      raise ValueError(f"No valid known image files found in: {known_input}")

    # Automatically persist reference targets in SQLite database archive
    for t in targets_info:
      try:
        t_label = t.get('label') or os.path.splitext(os.path.basename(t['file_path']))[0]
        self.db.add_known_target(
            label=t_label,
            file_path=clean_path(t['file_path']),
            group_name=t.get('group_name', 'default'),
            crop_box=t.get('crop_box'),
        )
      except Exception:
        pass

    unknown_file_paths = []
    if unknown_folder:
      unknown_folder = clean_path(unknown_folder)
      if not os.path.isdir(unknown_folder):
        raise NotADirectoryError(f"Unknown folder not found: {unknown_folder}")
      if recursive:
        for root, _, files in os.walk(unknown_folder):
          for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in IMAGE_EXTENSIONS or (include_videos and ext in VIDEO_EXTENSIONS):
              unknown_file_paths.append(os.path.join(root, f))
      else:
        for f in os.listdir(unknown_folder):
          ext = os.path.splitext(f)[1].lower()
          if ext in IMAGE_EXTENSIONS or (include_videos and ext in VIDEO_EXTENSIONS):
            unknown_file_paths.append(os.path.join(unknown_folder, f))

    models_results = {}
    cross_model_item_scores = collections.defaultdict(dict)

    for m_key in models_to_run:
      try:
        engine = self.get_engine(m_key)
      except Exception as e:
        continue

      m_name = engine.model_name

      # Compute known target embeddings for this model (handling images, crops, and video keyframes)
      known_vectors = []
      for t in targets_info:
        fpath = clean_path(t['file_path'])
        crop_box = t.get('crop_box')
        t_label = t.get('label', os.path.basename(fpath))
        ext = os.path.splitext(fpath)[1].lower()

        if ext in VIDEO_EXTENSIONS:
          # Target is a video: extract keyframes and compute embeddings for all keyframe scenes
          kf_output_dir = os.path.join(self.databases_dir, "flint_keyframes", f"ref_{os.path.splitext(os.path.basename(fpath))[0]}")
          try:
            keyframes = extract_keyframes(
                video_path=fpath,
                method=video_method,
                ssim_threshold=video_ssim_threshold,
                interval_seconds=video_interval_seconds,
                uniform_count=video_uniform_count,
                output_dir=kf_output_dir,
            )
            for kf_idx, kf in enumerate(keyframes):
              kf_p = kf['frame_path']
              if os.path.exists(kf_p):
                vec = engine.compute_image_embedding(kf_p, normalize=True)
                known_vectors.append({
                    'label': f"{t_label} (Frame {kf_idx+1})",
                    'file_path': fpath,
                    'keyframe_path': kf_p,
                    'vector': np.asarray(vec, dtype=np.float32),
                })
          except Exception:
            pass
        elif crop_box:
          vec = engine.extract_crop_embedding(fpath, crop_box, normalize=True)
          known_vectors.append({
              'label': t_label,
              'file_path': fpath,
              'vector': np.asarray(vec, dtype=np.float32),
          })
        else:
          vec = engine.compute_image_embedding(fpath, normalize=True)
          known_vectors.append({
              'label': t_label,
              'file_path': fpath,
              'vector': np.asarray(vec, dtype=np.float32),
          })

      # Index unknown media or ensure database embeddings for this model
      if unknown_folder and auto_index:
        self.db.index_folder(
            unknown_folder,
            engine,
            recursive=recursive,
            include_videos=include_videos,
            video_method=video_method,
            video_ssim_threshold=video_ssim_threshold,
            video_interval_seconds=video_interval_seconds,
            video_uniform_count=video_uniform_count,
            progress_callback=progress_callback,
        )
      elif unknown_folder is None and auto_index:
        self.db.ensure_embeddings_for_model(
            engine,
            model_name=m_name,
            progress_callback=progress_callback,
        )

      # Determine optimal metric for this specific model (based on training objective & research)
      model_metric = MODEL_CONFIGS.get(m_key, {}).get('default_metric', 'cosine') if (not metric or metric == "auto") else metric

      # Search by vector for this model
      raw_matches = self.db.search_by_multi_vectors(
          target_vectors=known_vectors,
          model_name=m_name,
          threshold=threshold,
          metric=model_metric,
          aggregation=aggregation,
          top_k=top_k,
          filter_paths=unknown_file_paths if unknown_folder else None,
      )

      m_grouped = group_matches_by_media(raw_matches)
      for item in m_grouped:
        item_id = item.get('file_path')
        score_pct = item.get('similarity_pct', round(item.get('score', 0.0) * 100, 2))
        cross_model_item_scores[item_id][m_key] = score_pct

      models_results[m_key] = {
          'model_key': m_key,
          'display_name': MODEL_CONFIGS[m_key]['display_name'],
          'metric_used': model_metric,
          'matches': m_grouped,
          'num_matches': len(m_grouped),
      }

    # Attach cross_model_scores to all items in every model result list
    for m_key, res in models_results.items():
      for item in res['matches']:
        item_id = item.get('file_path')
        item['all_model_scores'] = cross_model_item_scores.get(item_id, {})

    primary_res = models_results.get(primary_model) or next(iter(models_results.values()))
    primary_matches = primary_res['matches']
    elapsed_ms = (time.time() - t0) * 1000.0

    query_summary = f"Multi-model visual match ({len(models_to_run)} models, {len(targets_info)} known targets)"
    try:
      self.db.log_search_run(
          query_type="visual_multi_model",
          query_summary=query_summary,
          model_name=primary_model,
          threshold=threshold,
          metric=metric,
          results_count=len(primary_matches),
          duration_ms=elapsed_ms,
      )
    except Exception:
      pass

    return {
        'query_type': 'visual_similarity',
        'primary_model': primary_model,
        'model_name': primary_model,
        'models_computed': list(models_results.keys()),
        'models_results': models_results,
        'threshold': threshold,
        'metric': metric,
        'aggregation': aggregation,
        'duration_ms': round(elapsed_ms, 2),
        'known_targets': [
            {'label': t['label'], 'file_path': t['file_path'], 'crop_box': t.get('crop_box')}
            for t in targets_info
        ],
        'unknown_folder': unknown_folder,
        'total_scanned': len(unknown_file_paths) if unknown_folder else self.db.get_stats()['total_media'],
        'num_matches': len(primary_matches),
        'raw_matches_count': len(primary_matches),
        'matches': primary_matches,
    }

  def search_text(
      self,
      query: str,
      unknown_folder: Optional[str] = None,
      threshold: float = 0.0,
      metric: str = "cosine",
      top_k: Optional[int] = None,
      model_key: Optional[str] = None,
      models: Optional[Sequence[str]] = None,
      search_mode: str = "exact",
  ) -> Dict[str, Any]:
    t0 = time.time()
    
    raw_vec_obj = parse_raw_embedding_query(query)
    is_raw_vector = raw_vec_obj is not None

    # If it's a raw vector, we can match against any model with compatible dimensions (even vision-only models like dinov3)
    if is_raw_vector:
      target_models = []
      if models:
        for m in models:
          if m in MODEL_CONFIGS and self.is_model_available(m) and m not in target_models:
            target_models.append(m)
      if not target_models:
        target_models = [m for m in MODEL_CONFIGS.keys() if self.is_model_available(m)]
        if not target_models:
          target_models = ['clip-vit-b-32']
    else:
      # Natural language text: Filter for valid text-compatible models (strictly excluding vision-only models like dinov3)
      target_models = []
      if models:
        for m in models:
          if m in MODEL_CONFIGS and not MODEL_CONFIGS[m].get('is_vision_only', False) and self.is_model_available(m):
            if m not in target_models:
              target_models.append(m)
      if not target_models:
        primary = model_key if (model_key in MODEL_CONFIGS and not MODEL_CONFIGS[model_key].get('is_vision_only', False) and self.is_model_available(model_key)) else (
            self.active_model_key if (not MODEL_CONFIGS.get(self.active_model_key, {}).get('is_vision_only', False) and self.is_model_available(self.active_model_key)) else 'clip-vit-b-32'
        )
        target_models = [primary]

    primary_model = self.active_model_key if self.active_model_key in target_models else target_models[0]

    filter_paths = None
    if unknown_folder and not unknown_folder.startswith('databases/') and os.path.isdir(clean_path(unknown_folder)):
      unknown_folder = clean_path(unknown_folder)
      filter_paths = []
      for root, _, files in os.walk(unknown_folder):
        for f in files:
          ext = os.path.splitext(f)[1].lower()
          if ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS:
            filter_paths.append(os.path.join(root, f))

    models_results = {}
    for m in target_models:
      engine = self.get_engine(m)
      model_name = engine.model_name
      
      # Note: Database already contains indexed media; querying vectors directly

      if is_raw_vector:
        if isinstance(raw_vec_obj, dict):
          query_vec = raw_vec_obj.get(m) or raw_vec_obj.get(model_name)
          if query_vec is None:
            query_vec = next(iter(raw_vec_obj.values()))
        else:
          query_vec = raw_vec_obj

        # Normalize query vector
        v_norm = np.linalg.norm(query_vec)
        if v_norm > 0:
          query_vec = query_vec / v_norm
      else:
        query_vec = engine.compute_text_embedding(query, normalize=True)

      m_metric = metric if (metric and metric != "auto") else MODEL_CONFIGS.get(m, {}).get('default_metric', 'cosine')

      raw_matches = self.db.search_by_vector(
          query_vector=query_vec,
          model_name=model_name,
          threshold=threshold,
          metric=m_metric,
          top_k=top_k,
          filter_paths=filter_paths,
          search_mode=search_mode,
      )
      text_label = f'Prompt: "{query}"' if not is_raw_vector else 'Raw Vector Query'
      for m_item in raw_matches:
        target_entry = {
            'target_label': text_label,
            'target_path': '',
            'target_thumb': '',
            'query_text': query if not is_raw_vector else '',
            'is_text_query': not is_raw_vector,
            'score': m_item['score'],
            'similarity_pct': m_item.get('similarity_pct', round(m_item['score'] * 100, 2)),
        }
        m_item['best_target_label'] = text_label
        m_item['best_target_path'] = ''
        m_item['best_target_thumb'] = ''
        m_item['query_text'] = query if not is_raw_vector else ''
        m_item['is_text_query'] = not is_raw_vector
        m_item['all_target_scores'] = [target_entry]

      grouped = group_matches_by_media(raw_matches)
      models_results[m] = {
          'model_key': m,
          'display_name': MODEL_CONFIGS.get(m, {}).get('display_name', m),
          'metric_used': m_metric,
          'matches': grouped,
          'num_matches': len(grouped),
      }

    # Open-Vocabulary Text-to-Patch Bounding Box & Heatmap Localization
    for m in target_models:
      try:
        t_engine = self.get_engine(m)
        cand_matches = models_results.get(m, {}).get('matches', [])
        t_vec = query_vec if is_raw_vector else t_engine.compute_text_embedding(query, normalize=True)

        for idx, item in enumerate(cand_matches[:35]):
          cand_p = clean_path(item.get('file_path', ''))
          if not os.path.exists(cand_p):
            continue
          try:
            k_patch_data = extract_dense_patch_tokens(t_engine, cand_p)
            k_patches = k_patch_data['spatial_patches']
            grid_size = k_patch_data['grid_size']

            t_diag = compute_text_patch_localization(t_vec, k_patches, grid_size=grid_size)
            item['patch_matched'] = True
            item['localized_box'] = t_diag['localized_box']
            item['patch_max_score'] = t_diag['max_score']
            item['patch_avg_score'] = t_diag['avg_score']
            item['patch_similarity_pct'] = item.get('similarity_pct', round(item.get('score', 0.0) * 100.0, 2))
            item['patch_heatmap_url'] = generate_patch_heatmap_data_url(t_diag['heatmap_2d'], cand_p, t_diag['localized_box'])
            item['forensic_explanation'] = f"Open-vocabulary text activation for '{query}' localized via {m} dense spatial patch dot products (Peak Patch: {t_diag['max_score']}%, Mean: {t_diag['avg_score']}%)."
          except Exception:
            continue
      except Exception:
        continue

    elapsed_ms = (time.time() - t0) * 1000.0
    primary_matches = models_results[primary_model]['matches']

    desc_query = f"Vector ({len(raw_vec_obj) if hasattr(raw_vec_obj, '__len__') else 1} dims)" if is_raw_vector else f"Text: '{query}'"
    self.db.log_search_run(
        query_type="embedding_vector" if is_raw_vector else "text",
        query_summary=desc_query,
        model_name=primary_model,
        threshold=threshold,
        metric=metric,
        results_count=len(primary_matches),
        duration_ms=elapsed_ms,
    )

    return {
        'query': query,
        'is_raw_vector': is_raw_vector,
        'model_name': primary_model,
        'metric': metric,
        'threshold': threshold,
        'models_computed': list(models_results.keys()),
        'models_results': models_results,
        'matches': primary_matches,
        'num_matches': len(primary_matches),
        'duration_ms': round(elapsed_ms, 2),
        'unknown_folder': unknown_folder or self.db.db_path,
    }

  def search_crop(
      self,
      image_path: Optional[str] = None,
      image_data: Optional[str] = None,
      video_path: Optional[str] = None,
      timestamp_seconds: Optional[float] = None,
      source_filename: Optional[str] = None,
      bounding_box: Union[Tuple[float, float, float, float], List[float]] = (0, 0, 1, 1),
      unknown_folder: Optional[str] = None,
      threshold: float = 0.0,
      metric: str = "cosine",
      top_k: Optional[int] = None,
      model_key: Optional[str] = None,
      models: Optional[Sequence[str]] = None,
      search_mode: str = "exact",
      enable_patch_matching: bool = True,
      remove_background: bool = False,
  ) -> Dict[str, Any]:
    """Performs multi-model crop similarity search with optional DINOv3 Dense Spatial Patch Alignment."""
    t0 = time.time()
    from PIL import Image, ImageOps
    from PIL.ExifTags import TAGS, GPSTAGS
    import io, base64, cv2
    from flint.patch_matcher import (
        extract_dense_patch_tokens,
        compute_patch_chamfer_alignment,
        generate_patch_heatmap_data_url,
        build_patch_matching_forensic_explanation,
    )

    # Determine target models
    target_models = []
    if models:
      for m in models:
        if m in MODEL_CONFIGS and self.is_model_available(m) and m not in target_models:
          target_models.append(m)
    if not target_models:
      primary = (
          self.active_model_key
          if self.is_model_available(self.active_model_key)
          else (model_key if (model_key in MODEL_CONFIGS and self.is_model_available(model_key)) else 'clip-vit-b-32')
      )
      target_models = [primary]

    primary_model = self.active_model_key if self.active_model_key in target_models else target_models[0]

    # Crop extraction with EXIF orientation correction
    snippet_url = ""
    actual_bbox = [0, 0, 100, 100]
    crop_img = None
    try:
      if image_data and len(image_data) > 40:
        if image_data.startswith('data:image'):
          head, b64_str = image_data.split(',', 1)
        else:
          b64_str = image_data
        raw_bytes = base64.b64decode(b64_str)
        raw_img = Image.open(io.BytesIO(raw_bytes))
      elif video_path or (image_path and os.path.splitext(image_path)[1].lower() in VIDEO_EXTENSIONS):
        v_target = video_path or image_path
        v_clean = clean_path(v_target)
        if not os.path.exists(v_clean):
          raise FileNotFoundError(f"Video file not found: {v_clean}")
        
        cap = cv2.VideoCapture(v_clean)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        sec = float(timestamp_seconds or 0.0)
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(sec * fps))
        ret, frame_bgr = cap.read()
        cap.release()
        if not ret or frame_bgr is None:
          raise ValueError(f"Failed to read frame at {sec}s from video {v_clean}")
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        raw_img = Image.fromarray(frame_rgb)
      elif image_path:
        image_path = clean_path(image_path)
        raw_img = Image.open(image_path)
      else:
        raise ValueError("Neither image_path, video_path, nor image_data provided")

      img_trans = ImageOps.exif_transpose(raw_img).convert("RGB")
      w_img, h_img = img_trans.size

      is_normalized = (
          isinstance(bounding_box, (list, tuple))
          and len(bounding_box) == 4
          and max(float(c) for c in bounding_box) <= 1.05
      )

      if is_normalized:
        x1, y1, x2, y2 = [max(0.0, min(1.0, float(c))) for c in bounding_box]
        c_left = int(x1 * w_img)
        c_top = int(y1 * h_img)
        c_right = int(x2 * w_img)
        c_bottom = int(y2 * h_img)
      else:
        x1, y1, x2, y2 = bounding_box
        c_left = int(float(x1))
        c_top = int(float(y1))
        c_right = int(float(x2))
        c_bottom = int(float(y2))

      c_left = max(0, min(c_left, w_img - 8))
      c_top = max(0, min(c_top, h_img - 8))
      c_right = max(c_left + 8, min(c_right, w_img))
      c_bottom = max(c_top + 8, min(c_bottom, h_img))
      actual_bbox = [c_left, c_top, c_right, c_bottom]

      crop_img = img_trans.crop(actual_bbox)
      crop_img.load()

      if remove_background:
        try:
          import cv2, numpy as np
          cv_img = cv2.cvtColor(np.array(crop_img), cv2.COLOR_RGB2BGR)
          c_h, c_w = cv_img.shape[:2]
          if c_h >= 16 and c_w >= 16:
            mask = np.zeros(cv_img.shape[:2], np.uint8)
            bgd_model = np.zeros((1, 65), np.float64)
            fgd_model = np.zeros((1, 65), np.float64)
            margin_x = max(1, int(c_w * 0.04))
            margin_y = max(1, int(c_h * 0.04))
            rect = (margin_x, margin_y, c_w - 2 * margin_x, c_h - 2 * margin_y)
            cv2.grabCut(cv_img, mask, rect, bgd_model, fgd_model, 3, cv2.GC_INIT_WITH_RECT)
            fg_mask = np.where((mask == 2) | (mask == 0), 0, 1).astype('uint8')
            if np.sum(fg_mask) >= (c_h * c_w * 0.05):
              result_cv = cv_img * fg_mask[:, :, np.newaxis]
              result_rgb = cv2.cvtColor(result_cv, cv2.COLOR_BGR2RGB)
              crop_img = Image.fromarray(result_rgb)
        except Exception:
          pass

      buf = io.BytesIO()
      crop_img.save(buf, format="JPEG", quality=90)
      snippet_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
      snippet_url = f"data:image/jpeg;base64,{snippet_b64}"
    except Exception as e:
      snippet_url = ""

    filter_paths = None
    if unknown_folder and not unknown_folder.startswith('databases/') and os.path.isdir(clean_path(unknown_folder)):
      unknown_folder = clean_path(unknown_folder)
      filter_paths = []
      for root, _, files in os.walk(unknown_folder):
        for f in files:
          ext = os.path.splitext(f)[1].lower()
          if ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS:
            filter_paths.append(os.path.join(root, f))

    src_file = source_filename or (os.path.basename(video_path or image_path) if (video_path or image_path) else 'video_frame.jpg')
    src_img = video_path or image_path or source_filename or 'video_frame'

    models_results = {}
    crop_embeddings = {}

    for m in target_models:
      engine = self.get_engine(m)
      model_name = engine.model_name

      # Note: Database already contains indexed media; querying vectors directly

      if crop_img is not None:
        crop_vec = engine.compute_image_embedding(crop_img, normalize=True)
      elif image_path:
        crop_vec = engine.extract_crop_embedding(image_path, actual_bbox, normalize=True)
      else:
        raise ValueError("Cannot extract crop embedding: no crop image or path available")

      m_metric = metric if (metric and metric != "auto") else MODEL_CONFIGS.get(m, {}).get('default_metric', 'cosine')

      raw_matches = self.db.search_by_vector(
          query_vector=crop_vec,
          model_name=model_name,
          threshold=threshold,
          metric=m_metric,
          top_k=top_k,
          filter_paths=filter_paths,
          search_mode=search_mode,
      )
      src_label = f"Crop: {src_file}"
      for m_item in raw_matches:
        target_entry = {
            'target_label': src_label,
            'target_path': image_path or video_path or src_file,
            'target_thumb': "",
            'crop_box': actual_bbox,
            'score': m_item['score'],
            'similarity_pct': m_item.get('similarity_pct', round(m_item['score'] * 100, 2)),
        }
        m_item['best_target_label'] = src_label
        m_item['best_target_path'] = image_path or video_path or src_file
        m_item['best_target_thumb'] = ""
        m_item['all_target_scores'] = [target_entry]

      grouped = group_matches_by_media(raw_matches)
      models_results[m] = {
          'model_key': m,
          'display_name': MODEL_CONFIGS.get(m, {}).get('display_name', m),
          'metric_used': m_metric,
          'matches': grouped,
          'num_matches': len(grouped),
      }
      crop_embeddings[m] = [float(v) for v in crop_vec]

    # Deploy Dense Spatial Patch Alignment & High-Precision Bounding Box Localization
    # DINOv3's self-supervised visual tokens provide the gold-standard spatial correspondence across all model views
    patch_matching_diagnostics = {}
    if enable_patch_matching and self.is_model_available('dinov3'):
      try:
        d_engine = self.get_engine('dinov3')
        if crop_img is not None:
          q_patch_data = extract_dense_patch_tokens(d_engine, crop_img)
          q_patches = q_patch_data['spatial_patches']
          cached_patch_tokens = {}

          for m in target_models:
            cand_matches = models_results.get(m, {}).get('matches', [])
            for idx, item in enumerate(cand_matches[:12]):
              cand_p = clean_path(item.get('file_path', ''))
              if not os.path.exists(cand_p):
                continue
              try:
                if cand_p not in cached_patch_tokens:
                  cached_patch_tokens[cand_p] = extract_dense_patch_tokens(d_engine, cand_p)
                k_patch_data = cached_patch_tokens[cand_p]
                k_patches = k_patch_data['spatial_patches']
                p_diag = compute_patch_chamfer_alignment(q_patches, k_patches, grid_size=k_patch_data['grid_size'])

                item['patch_matched'] = True
                item['patch_chamfer_score'] = p_diag['chamfer_score']
                item['patch_similarity_pct'] = p_diag['chamfer_similarity_pct']
                item['patch_avg_score'] = p_diag['chamfer_similarity_pct']
                item['patch_max_score'] = p_diag['max_patch_score']
                item['localized_box'] = p_diag['localized_box']
                item['patch_heatmap_url'] = generate_patch_heatmap_data_url(p_diag['heatmap_2d'], cand_p, p_diag['localized_box'])
                item['forensic_explanation'] = build_patch_matching_forensic_explanation(
                    crop_info={'bbox': actual_bbox, 'source': source_filename},
                    patch_diagnostics=p_diag,
                    global_score_pct=item.get('similarity_pct', item.get('score', 0.0) * 100),
                )
              except Exception:
                continue

            patch_matching_diagnostics[m] = {
                'enabled': True,
                'model': 'dinov3',
                'display_name': 'DINOv3 Dense Spatial Patch Matcher',
                'num_query_patches': q_patch_data['num_patches'],
                'hidden_dim': q_patch_data['hidden_dim'],
                'explanation_summary': f'High-precision dense spatial patch alignment attached to {m} candidate matches.',
            }
      except Exception:
        pass

    elapsed_ms = (time.time() - t0) * 1000.0
    primary_matches = models_results[primary_model]['matches']

    src_file = source_filename or (os.path.basename(video_path or image_path) if (video_path or image_path) else 'video_frame.jpg')
    src_img = video_path or image_path or source_filename or 'video_frame'

    return {
        'source_image': src_img,
        'source_filename': src_file,
        'bounding_box': actual_bbox,
        'snippet_url': snippet_url,
        'crop_embeddings': crop_embeddings,
        'patch_matching_diagnostics': patch_matching_diagnostics,
        'num_matches': len(primary_matches),
        'duration_ms': round(elapsed_ms, 2),
        'model_name': primary_model,
        'models_computed': target_models,
        'models_results': models_results,
        'matches': primary_matches,
    }

  def triage_video(
      self,
      video_path: str,
      targets_input: Union[str, Sequence[str]],
      method: str = "ssim",
      ssim_threshold: float = 0.65,
      interval_seconds: float = 1.0,
      uniform_count: int = 10,
      similarity_threshold: float = 0.0,
      model_key: Optional[str] = None,
  ) -> Dict[str, Any]:
    t0 = time.time()
    engine = self.get_engine(model_key)
    model_name = engine.model_name

    video_path = clean_path(video_path)
    idx_res = self.db.index_video(
        video_path,
        engine,
        method=method,
        ssim_threshold=ssim_threshold,
        interval_seconds=interval_seconds,
        uniform_count=uniform_count,
    )

    target_info = self.parse_known_inputs(targets_input)
    target_vectors = []
    for t in target_info:
      fpath = clean_path(t['file_path'])
      vec = engine.compute_image_embedding(fpath, normalize=True)
      target_vectors.append({
          'label': t['label'],
          'file_path': fpath,
          'vector': np.asarray(vec, dtype=np.float32),
      })

    matches = self.db.search_by_multi_vectors(
        target_vectors=target_vectors,
        model_name=model_name,
        threshold=similarity_threshold,
        metric="cosine",
        aggregation="max",
    )

    video_matches = [
        m for m in matches if m.get('video_source_path') == os.path.abspath(video_path)
    ]
    video_matches.sort(key=lambda x: x.get('timestamp_seconds', 0.0))

    elapsed_ms = (time.time() - t0) * 1000.0
    return {
        'query_type': 'video_triage',
        'video_path': video_path,
        'keyframes_extracted': idx_res.get('keyframes_indexed', 0),
        'method': method,
        'model_name': model_name,
        'similarity_threshold': similarity_threshold,
        'duration_ms': round(elapsed_ms, 2),
        'targets': [{'label': t['label'], 'file_path': t['file_path']} for t in target_vectors],
        'num_events': len(video_matches),
        'events': video_matches,
    }


  def get_known_target_groups(self) -> List[str]:
    return self.db.get_known_target_groups()

  def add_known_target(
      self,
      file_data: Optional[str] = None,
      image_path: Optional[str] = None,
      filename: Optional[str] = None,
      label: Optional[str] = None,
      group_name: str = "default",
      recompute: bool = True,
      models: Optional[Sequence[str]] = None,
      search_mode: str = "exact",
  ) -> Dict[str, Any]:
    """Uploads and registers a new reference target (image or video) into a folder group and recomputes matches."""
    group_name = (group_name or 'default').strip().replace('/', '_').replace('\\', '_')
    if not group_name:
      group_name = 'default'

    ref_targets_dir = os.path.join(self.databases_dir, "reference_targets", group_name)
    os.makedirs(ref_targets_dir, exist_ok=True)

    saved_path = None
    if file_data and len(file_data) > 40:
      if file_data.startswith('data:'):
        head, b64_str = file_data.split(',', 1)
        mime = head.split(';')[0].replace('data:', '').lower()
      else:
        b64_str = file_data
        mime = ''
      raw_bytes = base64.b64decode(b64_str)
      
      fname = filename or f"target_{int(time.time()*1000)}"
      ext = os.path.splitext(fname)[1].lower()
      if not ext:
        if 'video' in mime or mime in ('video/mp4', 'video/quicktime', 'video/x-matroska', 'video/webm'):
          fname += '.mp4'
        else:
          fname += '.jpg'
        ext = os.path.splitext(fname)[1].lower()

      saved_path = os.path.join(ref_targets_dir, fname)

      if ext in VIDEO_EXTENSIONS or 'video' in mime:
        with open(saved_path, 'wb') as vf:
          vf.write(raw_bytes)
        # Pre-extract keyframes so video thumbnail and keyframes are immediately available
        try:
          kf_dir = os.path.join(ref_targets_dir, f"{os.path.splitext(fname)[0]}_keyframes")
          extract_keyframes(saved_path, method="ssim", output_dir=kf_dir)
        except Exception:
          pass
      else:
        raw_img = Image.open(io.BytesIO(raw_bytes))
        raw_img = ImageOps.exif_transpose(raw_img).convert("RGB")
        saved_path = os.path.join(ref_targets_dir, fname if fname.endswith(('.jpg', '.jpeg', '.png', '.webp')) else f"{fname}.jpg")
        raw_img.save(saved_path, format="JPEG", quality=95)

    elif image_path:
      orig_p = clean_path(image_path)
      if not os.path.exists(orig_p):
        raise FileNotFoundError(f"Reference target file not found: {orig_p}")
      fname = filename or os.path.basename(orig_p)
      saved_path = os.path.join(ref_targets_dir, fname)
      if os.path.abspath(orig_p) != os.path.abspath(saved_path):
        import shutil
        shutil.copy2(orig_p, saved_path)
    else:
      raise ValueError("Neither file_data nor image_path provided")

    target_label = label or os.path.splitext(os.path.basename(saved_path))[0]
    target_id = self.db.add_known_target(
        label=target_label,
        file_path=saved_path,
        group_name=group_name,
    )

    all_targets = self.db.get_all_known_targets()
    all_groups = self.db.get_known_target_groups()

    recomputed_results = None
    if recompute:
      target_paths = [t['file_path'] for t in all_targets if t.get('file_path') and os.path.exists(clean_path(t['file_path']))]
      if target_paths:
        try:
          stats = self.db.get_stats()
          db_models = stats.get('models_indexed', []) or [self.active_model_key]
          recomputed_results = self.search_known_vs_unknown(
              known_input=target_paths,
              unknown_folder=None,
              models=models or db_models,
              threshold=0.0,
              search_mode=search_mode,
              auto_index=False,
          )
        except Exception:
          recomputed_results = self.load_database_investigation(search_mode=search_mode)
      else:
        recomputed_results = self.load_database_investigation(search_mode=search_mode)

      if recomputed_results:
        recomputed_results['known_targets'] = all_targets

    return {
        'success': True,
        'target': {
            'id': target_id,
            'label': target_label,
            'file_path': saved_path,
            'group_name': group_name,
            'is_video': os.path.splitext(saved_path)[1].lower() in VIDEO_EXTENSIONS,
        },
        'groups': all_groups,
        'all_targets': all_targets,
        'recomputed_results': recomputed_results,
    }

  def delete_known_target(
      self,
      target_id: Optional[int] = None,
      file_path: Optional[str] = None,
      group_name: Optional[str] = None,
      delete_group: bool = False,
      recompute: bool = True,
      search_mode: str = "exact",
  ) -> Dict[str, Any]:
    """Deletes a reference target or entire folder group from the database and recomputes matches."""
    deleted_rows = 0
    if delete_group and group_name:
      deleted_rows = self.db.delete_known_target_group(group_name)
      group_dir = os.path.join(self.databases_dir, "reference_targets", group_name)
      if os.path.exists(group_dir) and os.path.isdir(group_dir):
        import shutil
        shutil.rmtree(group_dir, ignore_errors=True)
    else:
      if target_id is not None or file_path is not None:
        self.db.delete_known_target(target_id=target_id, file_path=file_path)
        deleted_rows = 1
        if file_path and "databases/reference_targets" in file_path and os.path.exists(file_path):
          try:
            os.remove(file_path)
          except Exception:
            pass

    all_targets = self.db.get_all_known_targets()
    all_groups = self.db.get_known_target_groups()

    recomputed_results = None
    if recompute:
      target_paths = [t['file_path'] for t in all_targets if t.get('file_path') and os.path.exists(clean_path(t['file_path']))]
      if target_paths:
        try:
          stats = self.db.get_stats()
          db_models = stats.get('models_indexed', []) or [self.active_model_key]
          recomputed_results = self.search_known_vs_unknown(
              known_input=target_paths,
              unknown_folder=None,
              models=db_models,
              threshold=0.0,
              search_mode=search_mode,
              auto_index=False,
          )
        except Exception:
          recomputed_results = self.load_database_investigation(search_mode=search_mode)
      else:
        recomputed_results = self.load_database_investigation(search_mode=search_mode)

      if recomputed_results:
        recomputed_results['known_targets'] = all_targets

    return {
        'success': True,
        'deleted_count': deleted_rows,
        'groups': all_groups,
        'all_targets': all_targets,
        'recomputed_results': recomputed_results,
    }

  def reverse_engineer_image(
      self,
      file_path: Optional[str] = None,
      media_id: Optional[int] = None,
      models: Optional[Sequence[str]] = None,
      include_diffusion: bool = False,
      diffusion_model: str = "sd-variations",
  ) -> Dict[str, Any]:
    """Reverse engineers visual image representations (Neural Semantic Maps + Photorealistic Diffusion)."""
    target_path = None
    if file_path:
      target_path = clean_path(file_path)
    elif media_id:
      with self.db.get_connection() as conn:
        row = conn.execute("SELECT file_path FROM indexed_media WHERE id = ?", (media_id,)).fetchone()
        if row:
          target_path = row[0]

    if not target_path or not os.path.exists(target_path):
      raise FileNotFoundError(f"Media file not found: {target_path}")

    target_models = []
    if models:
      for m in models:
        if m in MODEL_CONFIGS and m not in target_models:
          target_models.append(m)
    if not target_models:
      stats = self.db.get_stats()
      db_models = stats.get('models_indexed', [])
      target_models = [m for m in db_models if m in MODEL_CONFIGS] or ['clip-vit-b-32', 'siglip2-naflex', 'dinov3']

    reconstructions = {}
    
    # 1. Neural Semantic Maps (PCA)
    for m_key in target_models:
      try:
        engine = self.get_engine(m_key)
        inv_res = FlintFeatureInverter.extract_semantic_feature_map(
            engine=engine,
            image_path=target_path,
            model_key=m_key,
        )
        reconstructions[m_key] = inv_res
      except Exception as ex:
        reconstructions[m_key] = {
            'model_key': m_key,
            'model_display': MODEL_CONFIGS.get(m_key, {}).get('display_name', m_key),
            'error': str(ex),
        }

    # 2. Generative Diffusion Recreation (unCLIP / SD Image Variations)
    if include_diffusion or (models and any(m in ("unclip", "unclip-sd21", "sd-variations") for m in models)):
      d_key = diffusion_model if diffusion_model in ("unclip-sd21", "sd-variations") else "sd-variations"
      try:
        diff_res = FlintFeatureInverter.reconstruct_with_diffusion(
            image_path=target_path,
            model_type=d_key,
            device=self.get_engine().device,
        )
        reconstructions[d_key] = diff_res
      except Exception as ex:
        reconstructions[d_key] = {
            'model_key': d_key,
            'model_display': 'unCLIP / Stable Diffusion Variations',
            'is_diffusion': True,
            'error': str(ex),
        }

    return {
        'original_file_path': target_path,
        'original_filename': os.path.basename(target_path),
        'models_computed': list(reconstructions.keys()),
        'reconstructions': reconstructions,
    }

  def export_report(
      self,
      results: Dict[str, Any],
      export_format: str = "html",
      output_path: Optional[str] = None,
  ) -> str:
    if output_path:
      output_path = clean_path(output_path)

    if export_format == "json":
      out_file = output_path or "flint_results.json"
      with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
      return out_file

    elif export_format == "csv":
      out_file = output_path or "flint_results.csv"
      matches = results.get('matches') or results.get('events') or []
      fieldnames = ['score', 'similarity_pct', 'file_path', 'media_type', 'timestamp_seconds', 'best_target_label', 'best_target_path', 'width', 'height']
      with open(out_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for m in matches:
          writer.writerow(m)
      return out_file

    elif export_format == "html":
      out_file = output_path or "flint_triage_report.html"
      matches = results.get('matches') or results.get('events') or []
      q_type = results.get('query_type', 'Search')
      model_name = results.get('model_name', 'CLIP')
      num_matches = results.get('num_matches', len(matches))
      duration = results.get('duration_ms', 0)

      cards_html = []
      for m in matches:
        score_pct = m.get('similarity_pct', round(m.get('score', 0) * 100, 2))
        f_path = clean_path(m.get('file_path', ''))
        ts = m.get('timestamp_seconds', 0.0)
        m_type = m.get('media_type', 'image')
        target_label = m.get('best_target_label', '')
        target_path = clean_path(m.get('best_target_path', '')) if m.get('best_target_path') else ''

        # Use top_keyframe path for video preview if video
        preview_img_path = m.get('top_keyframe', {}).get('file_path') if m_type == 'video' else f_path

        b64_src = ""
        try:
          if preview_img_path and os.path.exists(preview_img_path):
            with Image.open(preview_img_path) as img:
              img.thumbnail((300, 300))
              import io
              buf = io.BytesIO()
              img.save(buf, format="JPEG", quality=80)
              b64_src = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
        except Exception:
          pass

        img_tag = f'<img src="{b64_src}" alt="Match" />' if b64_src else '<div class="no-img">Preview N/A</div>'
        ts_tag = f'<span class="ts-badge">{m.get("keyframes_count", 0)} frames</span>' if m_type == 'video' else ''
        target_info_tag = f'<div class="target-info">Matched Target: <b>{target_label}</b></div>' if target_label else ''

        card = f"""
        <div class="card">
          <div class="img-box">
            {img_tag}
            <span class="badge">{score_pct}% Match</span>
            {ts_tag}
          </div>
          <div class="card-body">
            <div class="label-title" title="{os.path.basename(f_path)}">{os.path.basename(f_path)}</div>
            <div class="meta">{f_path}</div>
            {target_info_tag}
            <div class="dims">Type: {m_type.upper()}</div>
          </div>
        </div>
        """
        cards_html.append(card)

      cards_joined = "".join(cards_html) if cards_html else '<p style="color: #94a3b8;">No matching images found above the selected threshold.</p>'
      html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>FLINT Vision Engine - Triage Report</title>
  <style>
    :root {{ --bg: #0f172a; --card-bg: #1e293b; --text: #f8fafc; --accent: #38bdf8; --border: #334155; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; }}
    .header {{ border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; }}
    h1 {{ margin: 0 0 8px 0; color: #fff; display: flex; align-items: center; gap: 12px; }}
    .stats {{ display: flex; gap: 20px; color: #94a3b8; font-size: 14px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }}
    .card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; transition: transform 0.2s; }}
    .card:hover {{ transform: translateY(-4px); border-color: var(--accent); }}
    .img-box {{ position: relative; width: 100%; height: 200px; background: #000; display: flex; align-items: center; justify-content: center; overflow: hidden; }}
    .img-box img {{ max-width: 100%; max-height: 100%; object-fit: contain; }}
    .badge {{ position: absolute; top: 10px; right: 10px; background: rgba(56, 189, 248, 0.9); color: #000; font-weight: bold; font-size: 12px; padding: 4px 8px; border-radius: 6px; }}
    .ts-badge {{ position: absolute; bottom: 10px; left: 10px; background: rgba(0, 0, 0, 0.75); color: #fff; font-size: 11px; padding: 2px 6px; border-radius: 4px; }}
    .card-body {{ padding: 14px; display: flex; flex-direction: column; gap: 6px; }}
    .label-title {{ font-weight: 600; font-size: 15px; color: #f1f5f9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .meta {{ font-size: 12px; color: #64748b; word-break: break-all; }}
    .target-info {{ font-size: 13px; color: var(--accent); margin-top: 4px; }}
    .dims {{ font-size: 11px; color: #475569; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>⚡ FLINT Triage Report</h1>
    <div class="stats">
      <span>Query: <b>{q_type}</b></span>
      <span>Model: <b>{model_name}</b></span>
      <span>Matches Found: <b>{num_matches}</b></span>
      <span>Duration: <b>{duration} ms</b></span>
    </div>
  </div>
  <div class="grid">
    {cards_joined}
  </div>
</body>
</html>
"""
      with open(out_file, "w") as f:
        f.write(html_doc)
      return out_file

    else:
      raise ValueError(f"Unsupported export format: {export_format}")

from .inversion import FlintFeatureInverter

