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
SYMPICS UNIFIED WEB SERVER (PORT 8080)
===============================================================================
Single-port production web server hosting the SYMPICS Forensic Studio,
REST API dispatch engine, CAS thumbnail/media static streaming, and
embedded Database Explorer.
===============================================================================
"""

import os
import sys
import json
import urllib.parse
import mimetypes
import socketserver
import time
import shutil
from http.server import BaseHTTPRequestHandler, HTTPServer

_app_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.abspath(os.path.join(_app_dir, ".."))

if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

_db_dir = os.path.join(_root_dir, "database")
if _db_dir not in sys.path:
    sys.path.insert(0, _db_dir)

import api_service
import db

# Load .env configuration if present
_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.path.exists(_env_path):
    with open(_env_path, "r", encoding="utf-8", errors="ignore") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k, _v = _k.strip(), _v.strip().strip("'\"")
                if _k not in os.environ:
                    os.environ[_k] = _v

def _resolve_vault_path(folder_name="future-lan-storage"):
    if os.getenv("SYMPICS_VAULT_ROOT"):
        return os.path.abspath(os.getenv("SYMPICS_VAULT_ROOT"))
    local_path = os.path.join(_root_dir, folder_name)
    parent_path = os.path.join(_root_dir, "..", folder_name)
    if os.path.exists(parent_path) and not os.path.exists(local_path):
        return os.path.abspath(parent_path)
    return os.path.abspath(local_path)

DEFAULT_PORT = int(os.getenv("SYMPICS_WEB_PORT", "8080"))
DEFAULT_HOST = os.getenv("SYMPICS_WEB_HOST", "0.0.0.0")
VAULT_ROOT = _resolve_vault_path("future-lan-storage")
STAGING_DIR = os.getenv("SYMPICS_STAGING_DIR") or os.path.join(VAULT_ROOT, "03_Ingestion_Staging")


class SympicsHTTPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Concise logging for API endpoints
        pass

    def get_cors_origin(self):
        origin = self.headers.get("Origin", "")
        if not origin:
            return "*"
        # Automatically allow any localhost or 127.0.0.1 port
        if origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:"):
            return origin
        # Automatically allow any LAN IP / hostname matching the server's active port
        if f":{DEFAULT_PORT}" in origin:
            return origin
        # Check explicit custom origins if configured
        custom = os.getenv("SYMPICS_CORS_ORIGIN", "")
        if custom:
            allowed = [x.strip() for x in custom.split(",") if x.strip()]
            if origin in allowed or "*" in allowed:
                return origin
        return "null"

    def send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", self.get_cors_origin())
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Sympics-Client")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", self.get_cors_origin())
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Sympics-Client")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        flat_query = {k: v[0] for k, v in query.items()}

        # 1. API: Evidence Gallery Listing
        if path == "/api/evidence":
            res = api_service.get_evidence_list(flat_query)
            self.send_json(res, status=200 if res.get("success") else 500)
            return

        # 2. API: Case Containers List
        elif path == "/api/cases":
            res = api_service.get_cases_list()
            self.send_json(res)
            return

        # 3. API: Reference Intelligence Known Collisions
        elif path == "/api/reference/collisions":
            limit = int(flat_query.get("limit", 100))
            res = api_service.get_reference_collisions_list(limit=limit)
            self.send_json(res)
            return

        # 4. API: Live Telemetry & Health Status
        elif path == "/api/telemetry":
            try:
                res = api_service.get_telemetry_status(VAULT_ROOT, STAGING_DIR)
            except Exception as e:
                res = {"success": True, "warning": str(e)}
            self.send_json(res)
            return

        # 4b. API: ERD Entity Counts
        elif path == "/api/erd-stats":
            res = api_service.get_erd_stats()
            self.send_json(res)
            return

        # 5. API: Table Schema Explorer
        elif path == "/api/table-schema":
            table_name = flat_query.get("table", "media_assets")
            res = api_service.get_table_schema_info(table_name)
            self.send_json(res)
            return

        # 6. API: Series List
        elif path in ("/api/series-list", "/api/series"):
            case_num = flat_query.get("case_number")
            res = api_service.get_series_list(case_number=case_num)
            self.send_json(res)
            return

        # 6b. API: Source Folders List
        elif path in ("/api/folders-list", "/api/folders"):
            res = api_service.get_folders_list()
            self.send_json(res)
            return

        # 7. API: Known Reference Tree
        elif path == "/api/reference-tree":
            case_num = flat_query.get("case_number")
            res = api_service.get_known_reference_tree(case_number=case_num)
            self.send_json(res)
            return

        # 7b. API: Reference Set Exemplar Items
        elif path == "/api/reference-set/items":
            res = api_service.get_reference_set_items(flat_query)
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 8. API: Case Catalog Export
        elif path == "/api/export-catalog":
            case_num = flat_query.get("case_number", "ALL")
            ver = flat_query.get("version", "1.3")
            res = api_service.export_catalog_data(case_number=case_num, version=ver)
            self.send_json(res)
            return

        # 8b. API: AI Auto-Triage Queue
        elif path == "/api/ai-triage/queue":
            res = api_service.get_ai_triage_queue(flat_query)
            self.send_json(res)
            return

        # 8c. API: Case Workspace Full Export
        elif path == "/api/cases/export-workspace":
            case_num = flat_query.get("case_number", "ALL")
            res = api_service.export_case_workspace(case_num)
            self.send_json(res)
            return

        # 8d. API: Dependency Studio Audit
        elif path == "/api/dependencies/audit":
            res = api_service.audit_dependencies()
            self.send_json(res)
            return

        # 9. Static CAS Media & Thumbnail Serving
        elif path.startswith(("/01_Media_Vault/", "/02_Keyframe_Vault/", "/thumbs/", "/media/")):
            self.serve_static_vault_file(path)
            return

        # 9b. Documentation Portal
        elif path == "/docs" or path.startswith("/docs/"):
            self.serve_docs(path)
            return

        # 10. Web UI Entry Point
        elif path in ("/", "/index.html"):
            self.serve_ui_shell()
            return

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(content_length).decode("utf-8")) if content_length > 0 else {}
        except Exception as e:
            self.send_json({"success": False, "error": f"Malformed JSON: {e}"}, status=400)
            return

        # 1. API: Create New Case / Investigation
        if path in ("/api/create-case", "/api/cases/create"):
            res = api_service.create_case(body)
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 1a. API: Delete Case Workspace
        elif path == "/api/cases/delete":
            res = api_service.delete_case(body)
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 1b. API: Link Evidence into Case Container
        elif path in ("/api/cases/link-evidence", "/api/cases/link-single"):
            res = api_service.link_evidence_to_case(body)
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 1c. API: AI Auto-Triage Confirm
        elif path == "/api/ai-triage/confirm":
            res = api_service.confirm_ai_triage(body)
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 1d. API: AI Auto-Triage Reject
        elif path == "/api/ai-triage/reject":
            res = api_service.reject_ai_triage(body)
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 1e. API: AI Auto-Triage Run Batch
        elif path == "/api/ai-triage/run-batch":
            res = api_service.run_ai_autotagger_batch(body)
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 1f. API: Import Known Hash Set (.txt, .csv, .json)
        elif path == "/api/import-hash-set":
            res = api_service.import_known_hash_set(body)
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 1g. API: Import Known Reference Targets (Folder)
        elif path == "/api/import-reference-targets":
            res = api_service.import_reference_targets(body)
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 1h. API: Retry Quarantined Ingestion Files
        elif path == "/api/telemetry/retry-quarantine":
            res = api_service.retry_quarantine_files(STAGING_DIR)
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 2. API: Multimodal Search (Text, Crop, Asset ID)
        elif path == "/api/search":
            t0 = time.time()
            res = api_service.search_multimodal(body)
            elapsed = (time.time() - t0) * 1000
            m = body.get("model", "unknown")
            t = body.get("type", "text")
            print(f"   [/api/search] type={t} model={m} -> {elapsed:.1f}ms | results={len(res.get('results', []))}")
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 3. API: Interactive Image Crop Search
        elif path == "/api/crop-search":
            t0 = time.time()
            res = api_service.execute_crop_search(body)
            elapsed = (time.time() - t0) * 1000
            m = body.get("model", "unknown")
            print(f"   [/api/crop-search] model={m} asset={body.get('asset_id') or body.get('path')} -> {elapsed:.1f}ms | success={res.get('success')}")
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 4. API: Search by Raw Embedding (Paste Vector)
        elif path == "/api/search-by-embedding":
            t0 = time.time()
            body["type"] = "vector"
            res = api_service.search_multimodal(body)
            elapsed = (time.time() - t0) * 1000
            print(f"   [/api/search-by-embedding] model={body.get('model')} -> {elapsed:.1f}ms")
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 4b. API: Multi-Exemplar Reference Set Nearest Neighbors (Top 1000)
        elif path == "/api/reference-set/nearest-neighbors":
            t0 = time.time()
            res = api_service.match_reference_set_nearest_neighbors(body)
            elapsed = (time.time() - t0) * 1000
            print(f"   [/api/reference-set/nearest-neighbors] series={body.get('series_name')} model={body.get('model')} -> {elapsed:.1f}ms")
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 4. API: "Top 15 (All)" Multi-Model Comparative Matrix
        elif path == "/api/multi-model-compare":
            t0 = time.time()
            res = api_service.multi_model_compare(body)
            elapsed = (time.time() - t0) * 1000
            print(f"   [/api/multi-model-compare] type={body.get('type')} -> {elapsed:.1f}ms")
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 5. API: Update Evidence Status / Series Tag / Tags
        elif path in ("/api/evidence/update", "/api/update-series"):
            res = api_service.update_evidence_status(body)
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 5b. API: Create Known Series
        elif path in ("/api/series/create", "/api/create-series"):
            res = api_service.create_series(body)
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 5c. API: Series Cross-Vault Collision Scan
        elif path in ("/api/series/collision-scan", "/api/collision-scan"):
            res = api_service.execute_series_collision_scan(body)
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        # 6. API: Safe Read-Only SQL Query Console
        elif path == "/api/query":
            sql = body.get("sql", "")
            res = api_service.execute_sql_query(sql)
            self.send_json(res, status=200 if res.get("success") else 400)
            return

        else:
            self.send_response(404)
            self.end_headers()

    def serve_static_vault_file(self, url_path):
        """Serves thumbnails or original media directly from the CAS vault."""
        clean_rel = url_path.lstrip("/").replace("..", "")
        abs_target = os.path.realpath(os.path.join(VAULT_ROOT, clean_rel))
        real_vault = os.path.realpath(VAULT_ROOT)

        # Security check: Ensure file stays strictly within VAULT_ROOT
        if not (abs_target.startswith(real_vault + os.sep) or abs_target == real_vault) or not os.path.isfile(abs_target):
            self.send_response(404)
            self.end_headers()
            return

        # Prevent serving sensitive dotfiles (.env, .git, etc.)
        for part in clean_rel.split("/"):
            if part.startswith("."):
                self.send_response(403)
                self.end_headers()
                return

        mime_type, _ = mimetypes.guess_type(abs_target)
        mime_type = mime_type or "application/octet-stream"

        # If requesting a Camera RAW file, serve its corresponding WebP thumbnail
        ext = os.path.splitext(abs_target)[1].lower()
        if ext in (".cr3", ".cr2", ".nef", ".arw", ".dng", ".raf", ".rw2"):
            filename_no_ext = os.path.splitext(os.path.basename(abs_target))[0]
            if len(filename_no_ext) >= 4:
                prefix1 = filename_no_ext[:2]
                prefix2 = filename_no_ext[2:4]
                thumb_target = os.path.join(real_vault, "02_Keyframe_Vault", "thumbs_256px", prefix1, prefix2, f"{filename_no_ext}.webp")
                if os.path.isfile(thumb_target):
                    abs_target = thumb_target
                    mime_type = "image/webp"

        try:
            file_size = os.path.getsize(abs_target)
            with open(abs_target, "rb") as f:
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(file_size))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                shutil.copyfileobj(f, self.wfile, length=65536)
        except Exception:
            self.send_response(500)
            self.end_headers()

    def serve_ui_shell(self):
        """Serves the Stage 2 Unified Web UI."""
        index_path = os.path.join(_app_dir, "index.html")
        if os.path.exists(index_path):
            with open(index_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(content)
            return

        # Fallback if index.html missing
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"SYMPICS Web Server Active. index.html not found.")

    def serve_docs(self, path):
        """Serves the generated offline HTML documentation."""
        rel_path = path[len("/docs"):]
        if not rel_path or rel_path == "/":
            rel_path = "/index.html"
        rel_path = rel_path.lstrip("/")

        docs_html_dir = os.path.join(_root_dir, "docs", "html")
        target_file = os.path.join(docs_html_dir, rel_path)

        if not os.path.abspath(target_file).startswith(docs_html_dir):
            self.send_response(403)
            self.end_headers()
            return

        if not os.path.isfile(target_file):
            self.send_response(404)
            self.end_headers()
            return

        mime_type, _ = mimetypes.guess_type(target_file)
        mime_type = mime_type or "text/html"

        try:
            with open(target_file, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", f"{mime_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_response(500)
            self.end_headers()


class ReusableThreadingServer(socketserver.ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_server(port=DEFAULT_PORT):
    # Pre-warm AI Vision Multi-Model Engine in RAM so first user request is instant
    print("[*] Pre-warming Multi-Model AI Vision Engine in memory...")
    try:
        from embedder_service import get_embedder
        _ = get_embedder()
        print("[+] AI Vision Multi-Model Engine pre-warmed and ready in RAM.")
    except Exception as e:
        print(f"[!] Warning: Could not pre-warm embedder: {e}")

    server = ReusableThreadingServer(("0.0.0.0", port), SympicsHTTPHandler)
    print(f"\n===============================================================================")
    print(f"  SYMPICS UNIFIED WEB SERVER ACTIVE ON PORT {port}")
    print(f"===============================================================================")
    print(f"  • Local Access         : http://localhost:{port}")
    print(f"  • Network Host         : http://0.0.0.0:{port}")
    print(f"  • Remote SSH Tunnel    : ssh -L {port}:localhost:{port} <user>@<server-ip>")
    print(f"                           Then open http://localhost:{port} in your browser")
    print(f"  • Backend Mode         : Multi-Model AI Engine + pgvector Similarity Search")
    print(f"===============================================================================\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SYMPICS Unified Web Server.")
        server.server_close()


if __name__ == "__main__":
    start_server()
