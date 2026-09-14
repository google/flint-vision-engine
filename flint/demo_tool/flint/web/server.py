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

# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""Standalone HTTP server and REST API for FLINT Vision Engine UI with Live Log Streaming."""

import base64
import email
import email.policy
import collections
import datetime
import io
import json
import mimetypes
import os
import socketserver
import sys
import threading
import time
import traceback
import urllib.parse
from typing import Any, Dict, List, Optional, Sequence, Union, Tuple
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from PIL import Image, ImageOps
try:
  import pillow_heif
  pillow_heif.register_heif_opener()
except Exception:
  pass

from flint.service import FlintService, clean_path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.abspath("uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
SESSION_FILE = os.path.abspath("flint_session.json")

service: Optional[FlintService] = None
download_status: Dict[str, Any] = {'is_downloading': False, 'model': '', 'progress': '', 'error': None}
indexing_status: Dict[str, Any] = {'is_indexing': False, 'current': 0, 'total': 0, 'status': ''}

# Thread-safe in-memory log buffer (stores up to 1000 recent log messages)
_LOG_LOCK = threading.Lock()
_SYSTEM_LOGS: collections.deque = collections.deque(maxlen=1000)
_LOG_COUNTER = 0


def log_event(level: str, message: str, details: Optional[str] = None):
  """Appends a timestamped log entry to the system log buffer."""
  global _LOG_COUNTER
  now = datetime.datetime.now()
  timestamp_str = now.strftime("%H:%M:%S") + f".{int(now.microsecond / 1000):03d}"
  with _LOG_LOCK:
    _LOG_COUNTER += 1
    entry = {
        'id': _LOG_COUNTER,
        'timestamp': timestamp_str,
        'epoch': time.time(),
        'level': level.upper(),  # INFO, SUCCESS, WARN, ERROR
        'message': message,
        'details': details or '',
    }
    _SYSTEM_LOGS.append(entry)
  # Also print to terminal
  prefix = f"[{timestamp_str}] [{level.upper()}]"
  print(f"{prefix} {message}")
  if details:
    print(f"  Details: {details}")


# Initial system startup log
log_event("INFO", "FLINT Vision Engine server initializing...")


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
  daemon_threads = True
  allow_reuse_address = True


class FlintRequestHandler(BaseHTTPRequestHandler):

  def log_message(self, format, *args):
    # Suppress default noisy console access logging
    pass

  def send_json(self, data: Any, status: int = 200):
    body = json.dumps(data, default=str).encode('utf-8')
    self.send_response(status)
    self.send_header('Content-Type', 'application/json')
    self.send_header('Content-Length', str(len(body)))
    self.send_header('Access-Control-Allow-Origin', '*')
    self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    self.end_headers()
    self.wfile.write(body)

  def send_error_json(self, message: str, status: int = 400, details: Optional[str] = None):
    log_event("ERROR", message, details)
    self.send_json({'error': message, 'details': details, 'success': False}, status=status)

  def do_OPTIONS(self):
    self.send_response(200)
    self.send_header('Access-Control-Allow-Origin', '*')
    self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    self.end_headers()

  def do_GET(self):
    parsed = urllib.parse.urlparse(self.path)
    path = parsed.path
    query = urllib.parse.parse_qs(parsed.query)

    if path == '/favicon.ico':
      self.send_response(204)
      self.end_headers()
      return
    elif path == '/' or path == '/index.html':
      self.serve_file(os.path.join(TEMPLATES_DIR, 'index.html'), 'text/html')
    elif path.startswith('/static/'):
      rel_path = path[8:]
      file_path = os.path.join(STATIC_DIR, rel_path)
      mime, _ = mimetypes.guess_type(file_path)
      self.serve_file(file_path, mime or 'text/plain')
    elif path == '/api/status':
      self.handle_api_status()
    elif path == '/api/logs':
      self.handle_api_logs(query)
    elif path == '/api/models':
      self.handle_api_models()
    elif path == '/api/models/download_status':
      self.send_json(download_status)
    elif path == '/api/index/status':
      self.send_json(indexing_status)
    elif path == '/api/database/stats':
      self.handle_db_stats()
    elif path == '/api/database/media':
      self.handle_db_media(query)
    elif path == '/api/media/preview':
      self.handle_media_preview(query)
    elif path == '/api/known_targets':
      self.handle_get_known_targets(query)
    elif path == '/api/databases':
      self.handle_get_databases()
    elif path == '/api/known_targets/groups':
      self.handle_get_target_groups()
    elif path == '/api/session':
      self.handle_get_session()
    else:
      self.send_error_json('Endpoint not found', status=404)

  def do_POST(self):
    parsed = urllib.parse.urlparse(self.path)
    path = parsed.path

    content_type = self.headers.get('Content-Type', '')

    if 'multipart/form-data' in content_type:
      self.handle_multipart_upload(path, content_type)
      return

    content_length = int(self.headers.get('Content-Length', 0))
    raw_body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
    try:
      data = json.loads(raw_body) if raw_body else {}
    except Exception as e:
      self.send_error_json(f'Invalid JSON body: {str(e)}', details=traceback.format_exc())
      return

    if path == '/api/models/set_active':
      self.handle_set_active_model(data)
    elif path == '/api/models/download':
      self.handle_download_model(data)
    elif path == '/api/search/visual':
      self.handle_search_visual(data)
    elif path == '/api/search/text':
      self.handle_search_text(data)
    elif path == '/api/search/crop':
      self.handle_search_crop(data)
    elif path == '/api/search/video_triage':
      self.handle_video_triage(data)
    elif path == '/api/index/folder':
      self.handle_index_folder(data)
    elif path == '/api/databases/set_active':
      self.handle_set_active_database(data)
    elif path == '/api/databases/create':
      self.handle_create_database(data)
    elif path == '/api/databases/load_investigation':
      self.handle_load_database_investigation(data)
    elif path == '/api/database/clear':
      self.handle_clear_db(data)
    elif path == '/api/export':
      self.handle_export(data)
    elif path == '/api/databases':
      self.handle_get_databases()
    elif path == '/api/known_targets/add':
      self.handle_add_known_target(data)
    elif path == '/api/known_targets/delete':
      self.handle_delete_known_target(data)
    elif path == '/api/media/reverse_engineer':
      self.handle_reverse_engineer(data)
    elif path == '/api/session':
      self.handle_save_session(data)
    elif path == '/api/logs/clear':
      with _LOG_LOCK:
        _SYSTEM_LOGS.clear()
      log_event("INFO", "Log console cleared by user.")
      self.send_json({'success': True})
    else:
      self.send_error_json('Endpoint not found', status=404)

  def serve_file(self, filepath: str, content_type: str):
    if not os.path.exists(filepath):
      self.send_error(404, 'File not found')
      return
    with open(filepath, 'rb') as f:
      content = f.read()
    self.send_response(200)
    self.send_header('Content-Type', content_type)
    self.send_header('Content-Length', str(len(content)))
    self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
    self.send_header('Pragma', 'no-cache')
    self.send_header('Expires', '0')
    self.end_headers()
    self.wfile.write(content)

  def handle_api_logs(self, query: Dict[str, Any]):
    since_id = int(query.get('since', [0])[0])
    with _LOG_LOCK:
      if since_id > 0:
        logs = [entry for entry in _SYSTEM_LOGS if entry['id'] > since_id]
      else:
        logs = list(_SYSTEM_LOGS)
    self.send_json({'logs': logs, 'latest_id': _LOG_COUNTER})

  def handle_api_status(self):
    global service
    if not service:
      self.send_error_json('Service uninitialized', 500)
      return
    stats = service.db.get_stats()
    models = service.list_available_models()
    active_m = [m for m in models if m['is_active']]
    device_name = 'Apple Silicon GPU (MPS)' if service.get_engine().device == 'mps' else service.get_engine().device.upper()
    self.send_json({
        'status': 'online',
        'active_model': active_m[0] if active_m else None,
        'device': device_name,
        'stats': stats,
        'models': models,
    })

  def handle_api_models(self):
    global service
    models = service.list_available_models()
    self.send_json({'models': models, 'active': service.active_model_key})

  def handle_set_active_model(self, data: Dict[str, Any]):
    global service
    model_key = data.get('model_key') or data.get('model')
    if not model_key:
      self.send_error_json('Missing model_key')
      return
    try:
      log_event("INFO", f"Switching active foundational model to '{model_key}'...")
      service.set_active_model(model_key)
      log_event("SUCCESS", f"Active model set to '{model_key}' on {service.get_engine().device.upper()}")
      self.send_json({'success': True, 'active_model': model_key})
    except Exception as e:
      self.send_error_json(str(e), details=traceback.format_exc())

  def handle_download_model(self, data: Dict[str, Any]):
    global download_status
    model_key = data.get('model_key') or data.get('model')
    hf_token = data.get('hf_token') or data.get('token') or os.environ.get('HF_TOKEN') or None
    if not model_key:
      self.send_error_json('Missing model_key')
      return

    models = {m['key']: m for m in service.list_available_models()}
    if model_key not in models:
      self.send_error_json(f'Unknown model: {model_key}')
      return

    cfg = models[model_key]

    def _do_download():
      global download_status
      download_status = {'is_downloading': True, 'model': model_key, 'progress': 'Starting download...', 'error': None}
      token_display = "with HuggingFace Token" if hf_token else "public anonymous"
      log_event("INFO", f"Downloading model weights for '{model_key}' from {cfg['repo_id']} ({token_display})...")
      try:
        from huggingface_hub import snapshot_download
        download_status['progress'] = f'Downloading {cfg["repo_id"]}...'
        dl_kwargs = {"local_dir": cfg["local_path"], "token": hf_token}
        if sys.platform == "win32":
          dl_kwargs["local_dir_use_symlinks"] = False
        snapshot_download(cfg["repo_id"], **dl_kwargs)
        download_status = {'is_downloading': False, 'model': model_key, 'progress': 'Download complete!', 'error': None}
        log_event("SUCCESS", f"Model '{model_key}' successfully downloaded to {cfg['local_path']}")
      except Exception as e:
        err_str = str(e)
        if 'gated repo' in err_str.lower() or '401' in err_str or 'restricted' in err_str.lower():
          msg = f"DINOv3 is a gated Meta model. Please accept terms at https://huggingface.co/{cfg['repo_id']} and provide your Hugging Face Token."
        else:
          msg = err_str
        download_status = {'is_downloading': False, 'model': model_key, 'progress': 'Failed', 'error': msg}
        log_event("ERROR", f"Failed to download model '{model_key}': {msg}", traceback.format_exc())

    threading.Thread(target=_do_download, daemon=True).start()
    self.send_json({'success': True, 'message': f'Download started for {model_key}'})

  def handle_multipart_upload(self, path: str, content_type: str):
    if path == '/api/upload':
      content_length = int(self.headers.get('Content-Length', 0))
      body = self.rfile.read(content_length) if content_length > 0 else b''
      header_prefix = f"Content-Type: {content_type}\r\n\r\n".encode("latin1")
      msg_bytes = header_prefix + body
      msg = email.message_from_bytes(msg_bytes, policy=email.policy.default)

      uploaded_files = []
      for part in msg.iter_parts():
        fn = part.get_filename()
        if fn:
          fn = os.path.basename(fn)
          save_p = os.path.join(UPLOAD_DIR, f"{int(time.time()*1000)}_{fn}")
          payload = part.get_payload(decode=True)
          if payload is not None:
            with open(save_p, 'wb') as f:
              f.write(payload)
            uploaded_files.append({
                'filename': fn,
                'path': save_p,
                'size': os.path.getsize(save_p),
            })
            log_event("INFO", f"Uploaded reference file: {fn} ({os.path.getsize(save_p)} bytes)")
      self.send_json({'success': True, 'files': uploaded_files})
    else:
      self.send_error_json('Form endpoint not found', 404)

  def handle_search_visual(self, data: Dict[str, Any]):
    global service
    raw_known = data.get('known_input') or data.get('known_path') or data.get('known_files')
    if isinstance(raw_known, list):
      known_input = [clean_path(f) for f in raw_known if f]
    elif isinstance(raw_known, str):
      known_input = clean_path(raw_known)
    else:
      known_input = None

    raw_unknown = data.get('unknown_folder') if 'unknown_folder' in data else data.get('unknown_path')
    unknown_path = clean_path(raw_unknown) if raw_unknown else None

    threshold = float(data.get('threshold', 0.0))
    metric = data.get('metric', 'cosine')
    aggregation = data.get('aggregation', 'max')
    top_k = int(data.get('top_k', 0)) if data.get('top_k') else None
    if top_k is not None and top_k <= 0:
      top_k = None
    recursive = bool(data.get('recursive', True))
    include_videos = bool(data.get('include_videos', True))
    video_method = str(data.get('video_method', 'ssim'))
    video_ssim_threshold = float(data.get('video_ssim_threshold', 0.65))
    video_interval_seconds = float(data.get('video_interval_seconds', 1.0))
    video_uniform_count = int(data.get('video_uniform_count', 10))
    save_db_name = data.get('save_database_name')
    if save_db_name:
      try:
        service.create_database(save_db_name)
        log_event("INFO", f"Created & activated SQLite archive: {save_db_name}")
      except Exception as e:
        log_event("WARN", f"Could not create database {save_db_name}: {str(e)}")

    models = data.get('models')
    if not models and data.get('model'):
      models = [data.get('model')]
    model_key = models[0] if models else service.active_model_key

    if not known_input:
      self.send_error_json('Please provide a known photo path or upload known photos')
      return

    target_desc = unknown_path if unknown_path else 'Entire SQLite DB'
    log_event(
        "INFO",
        f"Starting Visual Similarity Search [Model: {service.active_model_key}, Metric: {metric}, Threshold: {threshold*100:.0f}%, Target: {target_desc}]"
    )

    try:
      def _cb(p):
        status_msg = p.get('status', '')
        if status_msg:
          log_event("INFO", f"Indexing progress: {status_msg}")

      results = service.search_known_vs_unknown(
          known_input=known_input,
          unknown_folder=unknown_path,
          threshold=threshold,
          metric=metric,
          aggregation=aggregation,
          top_k=top_k,
          recursive=recursive,
          include_videos=include_videos,
          video_method=video_method,
          video_ssim_threshold=video_ssim_threshold,
          video_interval_seconds=video_interval_seconds,
          video_uniform_count=video_uniform_count,
          model_key=model_key,
          models=models,
          search_mode=data.get('search_mode', 'exact'),
          progress_callback=_cb,
      )
      log_event(
          "SUCCESS",
          f"Visual Search complete! Found {results['num_matches']} matches out of {results['total_scanned']} media items in {results['duration_ms']} ms"
      )
      results['success'] = True
      self.send_json(results)
    except Exception as e:
      self.send_error_json(f"Visual Search failed: {str(e)}", details=traceback.format_exc())

  def handle_search_text(self, data: Dict[str, Any]):
    global service
    query = data.get('query')
    if not query:
      self.send_error_json('Please enter a text search query')
      return

    unknown_folder = data.get('unknown_folder') or data.get('unknown_path')
    threshold = float(data.get('threshold', 0.0))
    metric = data.get('metric', 'cosine')
    top_k = int(data.get('top_k')) if data.get('top_k') else None
    model_key = data.get('model')
    models = data.get('models')

    log_event("INFO", f"Executing Text Search for query: '{query}'")
    try:
      results = service.search_text(
          query=query,
          unknown_folder=unknown_folder,
          threshold=threshold,
          metric=metric,
          top_k=top_k,
          model_key=model_key,
          models=models,
          search_mode=data.get('search_mode', 'exact'),
      )
      log_event("SUCCESS", f"Text Search finished: {results['num_matches']} matches in {results['duration_ms']} ms")
      results['success'] = True
      self.send_json(results)
    except Exception as e:
      self.send_error_json(f"Text Search failed: {str(e)}", details=traceback.format_exc())

  def handle_search_crop(self, data: Dict[str, Any]):
    global service
    image_path = clean_path(data.get('image_path')) if data.get('image_path') else None
    image_data = data.get('image_data') or data.get('image_base64')
    video_path = clean_path(data.get('video_path')) if data.get('video_path') else None
    timestamp_seconds = data.get('timestamp_seconds')
    crop_box = data.get('crop_box') or data.get('bounding_box') or [0.0, 0.0, 1.0, 1.0]

    if not image_path and not image_data and not video_path:
      self.send_error_json('Please specify image_path, video_path, or image_data')
      return
    if not isinstance(crop_box, (list, tuple)) or len(crop_box) != 4:
      crop_box = [0.0, 0.0, 1.0, 1.0]

    unknown_path = clean_path(data.get('unknown_folder') or data.get('unknown_path')) if (data.get('unknown_folder') or data.get('unknown_path')) else None
    threshold = float(data.get('threshold', 0.0))
    metric = data.get('metric', 'cosine')
    top_k = int(data.get('top_k', 100)) if data.get('top_k') else None
    model_key = data.get('model') or data.get('model_key')
    models = data.get('models')
    source_filename = data.get('source_filename') or data.get('filename')

    if video_path and not source_filename:
      ts_str = f"{float(timestamp_seconds):.2f}s" if timestamp_seconds is not None else ""
      source_filename = f"{os.path.basename(video_path)} (frame @ {ts_str})"

    desc = source_filename or (os.path.basename(image_path or video_path) if (image_path or video_path) else 'video_frame')
    log_event("INFO", f"Executing Targeted Crop Search on '{desc}' box={crop_box}")
    try:
      results = service.search_crop(
          image_path=image_path,
          image_data=image_data,
          video_path=video_path,
          timestamp_seconds=float(timestamp_seconds) if timestamp_seconds is not None else 0.0,
          source_filename=source_filename,
          bounding_box=tuple(float(c) for c in crop_box),
          unknown_folder=unknown_path,
          threshold=threshold,
          metric=metric,
          top_k=top_k,
          model_key=model_key,
          models=models,
          search_mode=data.get('search_mode', 'exact'),
          remove_background=bool(data.get('remove_background', False)),
      )
      log_event("SUCCESS", f"Crop Search finished: {results['num_matches']} matches across {len(results.get('models_computed', []))} models in {results['duration_ms']} ms")
      results['success'] = True
      self.send_json(results)
    except Exception as e:
      self.send_error_json(f"Crop Search failed: {str(e)}", details=traceback.format_exc())

  def handle_video_triage(self, data: Dict[str, Any]):
    global service
    video_path = clean_path(data.get('video_path')) if data.get('video_path') else None
    targets_input = clean_path(data.get('targets_path')) if data.get('targets_path') else data.get('targets_files')
    method = str(data.get('method', 'ssim'))
    ssim_threshold = float(data.get('ssim_threshold', 0.65))
    interval_seconds = float(data.get('interval_seconds', 1.0))
    uniform_count = int(data.get('uniform_count', 10))
    similarity_threshold = float(data.get('similarity_threshold', 0.0))

    if not video_path or not targets_input:
      self.send_error_json('Please specify video_path and target reference images')
      return

    log_event("INFO", f"Starting Video Triage for '{os.path.basename(video_path)}' (method: {method.upper()})")
    try:
      results = service.triage_video(
          video_path=video_path,
          targets_input=targets_input,
          method=method,
          ssim_threshold=ssim_threshold,
          interval_seconds=interval_seconds,
          uniform_count=uniform_count,
          similarity_threshold=similarity_threshold,
      )
      log_event(
          "SUCCESS",
          f"Video Triage complete: {results['keyframes_extracted']} keyframes extracted, {results['num_events']} target events detected in {results['duration_ms']} ms"
      )
      results['success'] = True
      self.send_json(results)
    except Exception as e:
      self.send_error_json(f"Video Triage failed: {str(e)}", details=traceback.format_exc())

  def handle_index_folder(self, data: Dict[str, Any]):
    global service, indexing_status
    folder_path = clean_path(data.get('folder_path')) if data.get('folder_path') else None
    if not folder_path or not os.path.isdir(folder_path):
      self.send_error_json(f'Directory does not exist: {folder_path}')
      return

    recursive = bool(data.get('recursive', True))
    include_videos = bool(data.get('include_videos', True))
    video_method = str(data.get('video_method', 'ssim'))
    video_ssim_threshold = float(data.get('video_ssim_threshold', 0.65))
    video_interval_seconds = float(data.get('video_interval_seconds', 1.0))
    video_uniform_count = int(data.get('video_uniform_count', 10))

    log_event("INFO", f"Initiating folder indexing into SQLite: '{folder_path}' (recursive={recursive}, include_videos={include_videos})")

    def _do_index():
      global indexing_status
      indexing_status = {'is_indexing': True, 'current': 0, 'total': 0, 'status': 'Scanning folder...'}
      try:
        def _cb(p):
          global indexing_status
          indexing_status = {
              'is_indexing': True,
              'current': p.get('current', 0),
              'total': p.get('total', 0),
              'status': p.get('status', ''),
          }
          log_event("INFO", f"Indexing: {p.get('status', '')}")

        res = service.db.index_folder(
            folder_path,
            service.get_engine(),
            recursive=recursive,
            include_videos=include_videos,
            video_method=video_method,
            video_ssim_threshold=video_ssim_threshold,
            video_interval_seconds=video_interval_seconds,
            video_uniform_count=video_uniform_count,
            progress_callback=_cb,
        )
        indexing_status = {'is_indexing': False, 'current': res['indexed'], 'total': res['total_files'], 'status': f"Indexing complete! Indexed {res['indexed']} items."}
        log_event("SUCCESS", f"Folder indexing finished: {res['indexed']} items indexed, {res['skipped']} skipped in '{folder_path}'")
      except Exception as e:
        indexing_status = {'is_indexing': False, 'current': 0, 'total': 0, 'status': f'Error: {str(e)}'}
        log_event("ERROR", f"Folder indexing error: {str(e)}", details=traceback.format_exc())

    threading.Thread(target=_do_index, daemon=True).start()
    self.send_json({'success': True, 'message': f'Started indexing folder: {folder_path}'})


  def handle_get_databases(self):
    global service
    try:
      dbs = service.list_databases()
      self.send_json({
          'success': True,
          'databases': dbs,
          'active_db': os.path.basename(service.db.db_path),
          'databases_dir': service.databases_dir,
      })
    except Exception as e:
      self.send_error_json(f"Failed to list databases: {str(e)}", details=traceback.format_exc())

  def handle_set_active_database(self, data: Dict[str, Any]):
    global service
    db_name = data.get('name') or data.get('filename') or data.get('path')
    if not db_name:
      self.send_error_json("Please provide database name or path")
      return
    try:
      res = service.set_active_database(db_name)
      log_event("SUCCESS", f"Switched active SQLite database to: {res['filename']} ({res['stats']['total_media']} media)")
      self.send_json(res)
    except Exception as e:
      self.send_error_json(f"Failed to switch database: {str(e)}", details=traceback.format_exc())


  def handle_load_database_investigation(self, data: Dict[str, Any]):
    global service
    db_name = data.get('name') or data.get('filename')
    known_targets = data.get('known_targets')
    try:
      results = service.load_database_investigation(db_name, known_targets=known_targets, search_mode=data.get('search_mode', 'exact'))
      log_event("SUCCESS", f"Loaded database archive into investigation: {results.get('database_name', db_name)} ({results.get('num_matches', len(results.get('matches', [])))} media files)")
      self.send_json(results)
    except Exception as e:
      self.send_error_json(f"Failed to load database investigation: {str(e)}", details=traceback.format_exc())

  def handle_create_database(self, data: Dict[str, Any]):
    global service
    db_name = data.get('name', '').strip()
    if not db_name:
      self.send_error_json("Please provide a name for the new SQLite database")
      return
    try:
      res = service.create_database(db_name)
      log_event("SUCCESS", f"Created new SQLite database: {res['filename']}")
      self.send_json(res)
    except Exception as e:
      self.send_error_json(f"Failed to create database: {str(e)}", details=traceback.format_exc())

  def handle_db_stats(self):
    global service
    stats = service.db.get_stats()
    self.send_json({'success': True, 'stats': stats})

  def handle_db_media(self, query: Dict[str, Any]):
    global service
    limit = int(query.get('limit', [50])[0])
    offset = int(query.get('offset', [0])[0])
    with service.db.get_connection() as conn:
      rows = conn.execute(
          """
          SELECT id, file_path, file_size, media_type, timestamp_seconds,
                 video_source_path, width, height, indexed_at
          FROM indexed_media
          ORDER BY id DESC
          LIMIT ? OFFSET ?
          """,
          (limit, offset),
      ).fetchall()
      items = [dict(r) for r in rows]
    self.send_json({'items': items, 'limit': limit, 'offset': offset})

  def handle_clear_db(self, data: Dict[str, Any]):
    global service
    service.db.clear_database()
    log_event("WARN", "SQLite database media records and embeddings cleared.")
    self.send_json({'success': True, 'message': 'Database cleared'})

  def handle_media_preview(self, query: Dict[str, Any]):
    path_param = clean_path(query.get('path', [''])[0]) if query.get('path', [''])[0] else ''
    thumb = query.get('thumb', ['0'])[0] == '1'
    if not path_param or not os.path.exists(path_param):
      self.send_error(404, 'File not found')
      return

    ext = os.path.splitext(path_param)[1].lower()
    is_video = ext in {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.flv'}

    try:
      if is_video and thumb:
        # Extract frame 0 for video thumbnail
        import cv2
        cap = cv2.VideoCapture(path_param)
        ret, frame = cap.read()
        cap.release()
        if ret and frame is not None:
          # Convert BGR to RGB and create thumbnail
          rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
          pil_img = Image.fromarray(rgb_frame)
          pil_img.thumbnail((320, 320))
          buf = io.BytesIO()
          pil_img.save(buf, format='JPEG', quality=85)
          data = buf.getvalue()
          mime = 'image/jpeg'
        else:
          self.send_error(500, 'Could not decode video frame')
          return

        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, must-revalidate')
        self.end_headers()
        self.wfile.write(data)
        return

      if not is_video and thumb:
        try:
          with Image.open(path_param) as raw_img:
            img = ImageOps.exif_transpose(raw_img)
            # Handle RGBA, Palette (P), LA, CMYK, etc. safely before JPEG compression
            if img.mode in ('RGBA', 'LA', 'P'):
              if img.mode == 'P':
                img = img.convert('RGBA')
              bg = Image.new('RGB', img.size, (15, 23, 42))
              if 'A' in img.getbands():
                bg.paste(img, mask=img.split()[-1])
                img = bg
              else:
                img = img.convert('RGB')
            elif img.mode != 'RGB':
              img = img.convert('RGB')

            img.thumbnail((320, 320))
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=85)
            data = buf.getvalue()
            mime = 'image/jpeg'

          self.send_response(200)
          self.send_header('Content-Type', mime)
          self.send_header('Content-Length', str(len(data)))
          self.send_header('Access-Control-Allow-Origin', '*')
          self.send_header('Cache-Control', 'no-cache, must-revalidate')
          self.end_headers()
          self.wfile.write(data)
          return
        except Exception as e:
          log_event("WARN", f"Thumbnail generation fallback for {os.path.basename(path_param)}: {str(e)}")
          # Fallback: serve original file directly
          pass

      # Handle HEIC/HEIF browser display conversion for full images
      if ext in {'.heic', '.heif'}:
        try:
          with Image.open(path_param) as raw_img:
            img = ImageOps.exif_transpose(raw_img)
            if img.mode != 'RGB':
              img = img.convert('RGB')
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=90)
            data = buf.getvalue()
          self.send_response(200)
          self.send_header('Content-Type', 'image/jpeg')
          self.send_header('Content-Length', str(len(data)))
          self.send_header('Access-Control-Allow-Origin', '*')
          self.send_header('Cache-Control', 'public, max-age=86400')
          self.end_headers()
          self.wfile.write(data)
          return
        except Exception as e:
          pass

      # Full file / video stream with Range support
      mime, _ = mimetypes.guess_type(path_param)
      if is_video and not mime:
        mime = 'video/mp4'
      mime = mime or 'application/octet-stream'
      file_size = os.path.getsize(path_param)

      range_header = self.headers.get('Range')
      if range_header and range_header.startswith('bytes='):
        # Handle HTTP 206 Partial Content for video streaming
        range_val = range_header[6:].strip()
        parts = range_val.split('-')
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
        if end >= file_size:
          end = file_size - 1
        length = end - start + 1

        self.send_response(206)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
        self.send_header('Content-Length', str(length))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

        with open(path_param, 'rb') as f:
          f.seek(start)
          bytes_to_send = length
          while bytes_to_send > 0:
            chunk_size = min(bytes_to_send, 65536)
            chunk = f.read(chunk_size)
            if not chunk:
              break
            self.wfile.write(chunk)
            bytes_to_send -= len(chunk)
      else:
        # HTTP 200 Full content
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(file_size))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, must-revalidate')
        self.end_headers()

        with open(path_param, 'rb') as f:
          while True:
            chunk = f.read(65536)
            if not chunk:
              break
            self.wfile.write(chunk)

    except Exception as e:
      self.send_error(500, f'Error reading media: {str(e)}')

  def handle_get_known_targets(self, query: Dict[str, Any]):
    global service
    path_param = query.get('path', [None])[0]
    group = query.get('group', [None])[0]

    if path_param:
      try:
        targets = service.parse_known_inputs(path_param)
        self.send_json({'success': True, 'targets': targets})
        return
      except Exception as e:
        log_event('WARN', f'Failed to parse known targets path {path_param}: {str(e)}')
        db_targets = service.db.get_known_targets(group_name=group)
        if db_targets:
          log_event('INFO', f'Fell back to {len(db_targets)} reference target(s) from current database archive.')
          for t in db_targets:
            if 'file_path' in t:
              t['file_path'] = clean_path(t['file_path'])
          self.send_json({'success': True, 'targets': db_targets, 'warning': str(e)})
          return
        self.send_error_json(f'Error scanning targets path: {str(e)}')
        return

    targets = service.db.get_known_targets(group_name=group)
    for t in targets:
      if 'file_path' in t:
        t['file_path'] = clean_path(t['file_path'])
    self.send_json({'success': True, 'targets': targets})

  def handle_get_session(self):
    if os.path.exists(SESSION_FILE):
      try:
        with open(SESSION_FILE, 'r') as f:
          session_data = json.load(f)
        self.send_json({'success': True, 'session': session_data})
        return
      except Exception:
        pass
    self.send_json({'success': True, 'session': {}})

  def handle_save_session(self, data: Dict[str, Any]):
    try:
      with open(SESSION_FILE, 'w') as f:
        json.dump(data, f, indent=2)
      self.send_json({'success': True})
    except Exception as e:
      self.send_error_json(f'Error saving session: {str(e)}')

  def handle_export(self, data: Dict[str, Any]):
    global service
    results = data.get('results', {})
    export_format = data.get('format', 'html')
    out_name = f"flint_export_{int(time.time())}.{export_format}"
    out_path = os.path.join(UPLOAD_DIR, out_name)
    try:
      saved_file = service.export_report(results, export_format=export_format, output_path=out_path)
      log_event("SUCCESS", f"Generated {export_format.upper()} report export: {os.path.basename(saved_file)}")
      self.send_json({
          'success': True,
          'download_url': f'/static/../uploads/{os.path.basename(saved_file)}',
          'file_path': saved_file,
          'filename': os.path.basename(saved_file),
      })
    except Exception as e:
      self.send_error_json(str(e), details=traceback.format_exc())



  def handle_get_target_groups(self):
    global service
    if not service:
      self.send_error_json('Service uninitialized', 500)
      return
    try:
      groups = service.get_known_target_groups()
      self.send_json({'groups': groups})
    except Exception as e:
      self.send_error_json(str(e), details=traceback.format_exc())

  def handle_delete_known_target(self, data: Dict[str, Any]):
    global service
    target_id = data.get('target_id')
    file_path = data.get('file_path')
    group_name = data.get('group_name')
    delete_group = bool(data.get('delete_group', False))
    recompute = bool(data.get('recompute', True))
    search_mode = data.get('search_mode', 'exact')

    try:
      res = service.delete_known_target(
          target_id=target_id,
          file_path=file_path,
          group_name=group_name,
          delete_group=delete_group,
          recompute=recompute,
          search_mode=search_mode,
      )
      log_event("SUCCESS", f"Deleted reference target(s) [group: {group_name or 'item'}, count: {res['deleted_count']}]")
      self.send_json(res)
    except Exception as e:
      self.send_error_json(f"Failed to delete reference target: {str(e)}", details=traceback.format_exc())

  def handle_add_known_target(self, data: Dict[str, Any]):
    global service
    if not service:
      self.send_error_json('Service uninitialized', 500)
      return
    try:
      res = service.add_known_target(
          file_data=data.get('file_data'),
          image_path=data.get('image_path'),
          filename=data.get('filename'),
          label=data.get('label'),
          group_name=data.get('group_name', 'default'),
          recompute=data.get('recompute', True),
          models=data.get('models'),
          search_mode=data.get('search_mode', 'exact'),
      )
      log_event("SUCCESS", f"Added reference target '{res['target']['label']}' in folder '{res['target']['group_name']}'")
      self.send_json(res)
    except Exception as e:
      log_event("ERROR", f"Failed to add reference target: {str(e)}")
      self.send_error_json(str(e), details=traceback.format_exc())

  def handle_reverse_engineer(self, data: Dict[str, Any]):
    global service
    if not service:
      self.send_error_json('Service uninitialized', 500)
      return
    try:
      log_event("INFO", "Reverse engineering image representation from embeddings...")
      res = service.reverse_engineer_image(
          file_path=data.get('file_path'),
          media_id=data.get('media_id'),
          models=data.get('models'),
          include_diffusion=bool(data.get('include_diffusion', False)),
          diffusion_model=data.get('diffusion_model', 'sd-variations'),
      )
      log_event("SUCCESS", f"Reverse engineered image across {len(res.get('models_computed', []))} model(s)")
      self.send_json(res)
    except Exception as e:
      log_event("ERROR", f"Reverse engineering failed: {str(e)}")
      self.send_error_json(str(e), details=traceback.format_exc())

def run_server(
    host: str = '127.0.0.1',
    port: int = 8080,
    models_dir: str = 'models',
    databases_dir: str = 'databases',
    db_path: Optional[str] = None,
):
  global service
  service = FlintService(models_dir=models_dir, databases_dir=databases_dir, db_path=db_path)
  server_address = (host, port)
  httpd = ThreadedHTTPServer(server_address, FlintRequestHandler)
  log_event("INFO", f"FLINT Vision Engine server started on http://{host}:{port}")
  log_event("INFO", f"Active Model: {service.active_model_key} | Acceleration: {service.get_engine().device.upper()}")
  log_event("INFO", f"SQLite Database: {service.db.db_path}")
  print('=====================================================')
  print(f'⚡ FLINT Vision Engine UI Running at: http://{host}:{port}')
  print(f'Active Model: {service.active_model_key} | Device: {service.get_engine().device}')
  print(f'Database: {service.db.db_path}')
  print('=====================================================')
  try:
    httpd.serve_forever()
  except KeyboardInterrupt:
    print('\nShutting down FLINT UI server...')
    httpd.server_close()


if __name__ == '__main__':
  run_server()
