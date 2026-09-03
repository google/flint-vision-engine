#!/usr/bin/env python3
# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
===============================================================================
SYMPICS POSTGRESQL WEB DASHBOARD & DATABASE EXPLORER
===============================================================================
A lightweight, zero-dependency web UI (Port 8085) to view and inspect the
SYMPICS PostgreSQL database, live migration manifest records, and schema tables.
Accessible locally and remotely across network / SSH tunnels.
===============================================================================
"""

import os
import sys
import json
import time
import socket
import urllib.parse
import webbrowser
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

DASHBOARD_PORT = 8085


class DashboardHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Quiet logging

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/api/summary":
            try:
                conn = db.get_connection()
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM v_migration_summary;")
                    summary = cur.fetchone() or {}
                    cur.execute("SELECT * FROM v_forensic_integrity_audit;")
                    audit_summary = cur.fetchone() or {}
                    cur.execute("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                        ORDER BY table_name;
                    """)
                    tables = [r["table_name"] for r in cur.fetchall()]
                    table_counts = {}
                    for t in tables:
                        try:
                            cur.execute(f"SELECT COUNT(*) as count FROM {t};")
                            table_counts[t] = cur.fetchone()["count"]
                        except Exception:
                            table_counts[t] = 0
                conn.close()
                self.send_json({"success": True, "summary": summary, "audit": audit_summary, "tables": tables, "table_counts": table_counts})
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, status=500)
            return

        elif path == "/api/manifest":
            limit = int(query.get("limit", [50])[0])
            offset = int(query.get("offset", [0])[0])
            status_filter = query.get("status", ["ALL"])[0]
            search = query.get("search", [""])[0].strip()

            try:
                conn = db.get_connection()
                with conn.cursor() as cur:
                    where_clauses = []
                    params = []

                    if status_filter != "ALL":
                        where_clauses.append("status = %s")
                        params.append(status_filter)

                    if search:
                        where_clauses.append("(source_filename ILIKE %s OR sha256 ILIKE %s OR md5 ILIKE %s OR source_filepath ILIKE %s)")
                        term = f"%{search}%"
                        params.extend([term, term, term, term])

                    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

                    # Count total matching
                    cur.execute(f"SELECT COUNT(*) as total FROM migration_manifest {where_sql}", params)
                    total = cur.fetchone()["total"]

                    # Fetch page
                    params.extend([limit, offset])
                    cur.execute(f"""
                        SELECT * FROM migration_manifest 
                        {where_sql}
                        ORDER BY manifest_id DESC 
                        LIMIT %s OFFSET %s
                    """, params)
                    rows = cur.fetchall()

                conn.close()
                self.send_json({"success": True, "total": total, "rows": rows, "limit": limit, "offset": offset})
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, status=500)
            return

        elif path == "/api/table-schema":
            table_name = query.get("table", ["migration_manifest"])[0]
            try:
                conn = db.get_connection()
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT column_name, data_type, is_nullable, column_default
                        FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = %s
                        ORDER BY ordinal_position;
                    """, (table_name,))
                    columns = cur.fetchall()

                    cur.execute("""
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE schemaname = 'public' AND tablename = %s;
                    """, (table_name,))
                    indexes = cur.fetchall()
                conn.close()
                self.send_json({"success": True, "table": table_name, "columns": columns, "indexes": indexes})
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, status=500)
            return

        elif path == "/api/reference":
            try:
                conn = db.get_connection()
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) as total FROM reference_catalog_records;")
                    total_records = cur.fetchone()["total"]
                    cur.execute("SELECT * FROM v_reference_known_collisions LIMIT 50;")
                    collisions = cur.fetchall()
                    cur.execute("SELECT * FROM reference_catalog_records ORDER BY record_id DESC LIMIT 50;")
                    records = cur.fetchall()
                conn.close()
                self.send_json({"success": True, "total_records": total_records, "collisions": collisions, "records": records})
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, status=500)
            return

        elif path in ("/", "/index.html"):
            self.serve_dashboard_html()
            return
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length).decode("utf-8")) if content_length > 0 else {}
        path = urllib.parse.urlparse(self.path).path

        if path == "/api/query":
            sql = body.get("sql", "").strip()
            if not sql:
                self.send_json({"error": "Query cannot be empty"}, status=400)
                return

            import re
            # Strip SQL single-line and multi-line comments before validating statement type
            cleaned_sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
            cleaned_sql = re.sub(r'/\*.*?\*/', '', cleaned_sql, flags=re.DOTALL).strip()

            if not cleaned_sql.lower().startswith(("select", "with", "explain", "show")):
                self.send_json({"error": "Only SELECT / Read-Only queries are allowed in this console."}, status=400)
                return

            try:
                conn = db.get_connection()
                with conn.cursor() as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
                conn.close()
                self.send_json({"success": True, "rows": rows, "count": len(rows)})
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, status=500)
            return

    def serve_dashboard_html(self):
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SYMPICS PostgreSQL Database Explorer</title>
    <!-- 100% Offline Air-Gapped Ready -->
    <style>
        :root {
            --bg-primary: #0a0e17;
            --card-bg: rgba(20, 27, 45, 0.85);
            --accent-cyan: #00f2fe;
            --accent-blue: #4facfe;
            --accent-green: #10b981;
            --accent-amber: #f59e0b;
            --accent-rose: #f43f5e;
            --text-main: #f8fafc;
            --text-dim: #94a3b8;
            --border: rgba(255, 255, 255, 0.1);
            --border-glow: rgba(0, 242, 254, 0.3);
            --radius: 10px;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
        body { background: var(--bg-primary); color: var(--text-main); padding: 20px; font-size: 13px; }
        header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 16px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
        h1 { font-family: 'Outfit', sans-serif; font-size: 22px; background: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .badge { background: rgba(0, 242, 254, 0.15); border: 1px solid var(--accent-cyan); color: var(--accent-cyan); padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
        
        .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 20px; }
        .stat-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px; display: flex; flex-direction: column; gap: 4px; }
        .stat-card .label { font-size: 11px; text-transform: uppercase; color: var(--text-dim); font-weight: 600; }
        .stat-card .value { font-size: 20px; font-weight: 700; font-family: 'Outfit', sans-serif; color: var(--text-main); }

        .tabs { display: flex; gap: 8px; margin-bottom: 16px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
        .tab-btn { background: transparent; border: none; color: var(--text-dim); padding: 8px 14px; font-weight: 600; cursor: pointer; border-radius: 6px; font-size: 12px; transition: all 0.2s; }
        .tab-btn.active { background: rgba(0, 242, 254, 0.15); color: var(--accent-cyan); border: 1px solid var(--accent-cyan); }

        .panel { background: var(--card-bg); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; margin-bottom: 20px; }
        .controls { display: flex; gap: 12px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }
        input, select, textarea { background: rgba(0, 0, 0, 0.4); border: 1px solid var(--border); color: var(--text-main); padding: 8px 12px; border-radius: 6px; font-size: 12px; outline: none; }
        input:focus, select:focus, textarea:focus { border-color: var(--accent-cyan); }
        .btn { background: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%); color: #0a0e17; font-weight: 700; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 12px; transition: opacity 0.2s; }
        .btn:hover { opacity: 0.9; }

        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 12px; }
        th { background: rgba(0, 0, 0, 0.5); padding: 10px; color: var(--text-dim); font-size: 11px; text-transform: uppercase; font-weight: 600; border-bottom: 1px solid var(--border); }
        td { padding: 10px; border-bottom: 1px solid rgba(255, 255, 255, 0.05); font-family: 'JetBrains Mono', monospace; font-size: 11px; }
        tr:hover { background: rgba(255, 255, 255, 0.03); }

        .tag-status { padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; display: inline-block; }
        .status-PENDING { background: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid #f59e0b; }
        .status-VERIFIED_COPIED { background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981; }
        .status-SKIPPED_DUPLICATE { background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid #38bdf8; }
        .status-FAILED_CORRUPT, .status-FAILED_ERROR { background: rgba(244, 63, 94, 0.2); color: #f43f5e; border: 1px solid #f43f5e; }

        .table-responsive { max-height: 480px; overflow-y: auto; border: 1px solid var(--border); border-radius: 6px; }
        .mono { font-family: 'JetBrains Mono', monospace; }
        .hidden { display: none; }

        /* ERD DIAGRAM STYLES */
        .erd-container { display: flex; flex-direction: column; gap: 20px; }
        .erd-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
        .erd-card { background: rgba(15, 23, 42, 0.9); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.5); transition: transform 0.2s, border-color 0.2s; }
        .erd-card:hover { transform: translateY(-2px); border-color: var(--accent-cyan); }
        .erd-header { padding: 10px 14px; font-weight: 700; font-family: 'Outfit', sans-serif; font-size: 14px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.08); }
        .erd-header.head-core { background: linear-gradient(135deg, rgba(16, 185, 129, 0.25) 0%, rgba(5, 150, 105, 0.1) 100%); color: #34d399; border-top: 3px solid #10b981; }
        .erd-header.head-vector { background: linear-gradient(135deg, rgba(0, 242, 254, 0.25) 0%, rgba(79, 172, 254, 0.1) 100%); color: #00f2fe; border-top: 3px solid #00f2fe; }
        .erd-header.head-case { background: linear-gradient(135deg, rgba(168, 85, 247, 0.25) 0%, rgba(147, 51, 234, 0.1) 100%); color: #c084fc; border-top: 3px solid #a855f7; }
        .erd-header.head-junction { background: linear-gradient(135deg, rgba(56, 189, 248, 0.25) 0%, rgba(2, 132, 199, 0.1) 100%); color: #38bdf8; border-top: 3px solid #38bdf8; }
        .erd-header.head-manifest { background: linear-gradient(135deg, rgba(245, 158, 11, 0.25) 0%, rgba(217, 119, 6, 0.1) 100%); color: #fbbf24; border-top: 3px solid #f59e0b; }
        .erd-header.head-reference { background: linear-gradient(135deg, rgba(244, 63, 94, 0.25) 0%, rgba(225, 29, 72, 0.1) 100%); color: #fb7185; border-top: 3px solid #f43f5e; }
        
        .erd-rows { max-height: 280px; overflow-y: auto; }
        .erd-row { display: flex; justify-content: space-between; align-items: center; padding: 6px 12px; border-bottom: 1px solid rgba(255,255,255,0.03); font-size: 11px; font-family: 'JetBrains Mono', monospace; }
        .erd-row:nth-child(even) { background: rgba(255, 255, 255, 0.015); }
        .erd-col-name { display: flex; align-items: center; gap: 6px; font-weight: 500; }
        .erd-col-type { color: var(--text-dim); font-size: 10px; }
        
        .key-badge { font-size: 9px; font-weight: 700; padding: 2px 5px; border-radius: 3px; text-transform: uppercase; }
        .key-pk { background: rgba(234, 179, 8, 0.25); color: #facc15; border: 1px solid #eab308; }
        .key-fk { background: rgba(56, 189, 248, 0.25); color: #38bdf8; border: 1px solid #0284c7; }
        .key-uq { background: rgba(192, 132, 252, 0.25); color: #c084fc; border: 1px solid #a855f7; }
        .key-idx { background: rgba(16, 185, 129, 0.2); color: #34d399; }
        .key-vec { background: rgba(0, 242, 254, 0.25); color: #00f2fe; border: 1px solid #00f2fe; font-weight: 700; }

        .rel-banner { background: rgba(0,0,0,0.3); border: 1px solid var(--border); border-radius: 8px; padding: 14px; margin-top: 10px; }
        .rel-item { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 12px; font-family: 'JetBrains Mono', monospace; }
        .rel-item:last-child { border-bottom: none; }
        .rel-arrow { color: var(--accent-cyan); font-weight: 700; }
        .rel-cardinality { background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px; font-size: 10px; color: var(--text-dim); }

        /* PRE-CANNED SQL QUERY SIDEBAR & LAYOUT */
        .sql-layout { display: flex; gap: 16px; margin-bottom: 14px; align-items: stretch; }
        .sql-sidebar { flex: 0 0 260px; background: rgba(0, 0, 0, 0.35); border: 1px solid var(--border); border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 8px; max-height: 560px; min-height: 540px; overflow-y: auto; overflow-x: hidden; }
        .sql-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 10px; }
        .precanned-item { background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 8px 10px; cursor: pointer; transition: all 0.15s; display: flex; flex-direction: column; gap: 3px; text-align: left; flex-shrink: 0; }
        .precanned-item:hover { background: rgba(0, 242, 254, 0.12); border-color: var(--accent-cyan); transform: translateX(2px); }
        .precanned-title { font-weight: 600; font-size: 11px; color: var(--text-main); display: flex; justify-content: space-between; align-items: center; }
        .precanned-desc { font-size: 10px; color: var(--text-dim); line-height: 1.2; }
    </style>
</head>
<body>
    <header>
        <div>
            <h1>SYMPICS Database Explorer</h1>
            <p style="color: var(--text-dim); font-size: 12px; margin-top: 3px;">PostgreSQL Master Node • Database: <strong id="db-name" style="color: var(--accent-cyan);">sympics_db</strong></p>
        </div>
        <div style="display: flex; gap: 10px; align-items: center;">
            <button onclick="refreshData()" class="btn" style="padding: 6px 12px; font-size: 11px;"> Refresh</button>
            <span class="badge">STATUS: ONLINE</span>
        </div>
    </header>

    <div class="stat-grid">
        <div class="stat-card">
            <span class="label">Discovered Files</span>
            <span class="value" id="stat-discovered">0</span>
        </div>
        <div class="stat-card">
            <span class="label">Verified Ingested</span>
            <span class="value" id="stat-verified" style="color: var(--accent-green);">0</span>
        </div>
        <div class="stat-card">
            <span class="label">Unique Deduplicated</span>
            <span class="value" id="stat-unique" style="color: var(--accent-cyan);">0</span>
        </div>
        <div class="stat-card">
            <span class="label">Duplicate Occurrences</span>
            <span class="value" id="stat-duplicates" style="color: var(--accent-blue);">0</span>
        </div>
        <div class="stat-card">
            <span class="label">Progress Completed</span>
            <span class="value" id="stat-pct">0.0%</span>
        </div>
    </div>

    <div class="tabs">
        <button class="tab-btn active" onclick="showTab('manifest')"> Migration Manifest Ledger</button>
        <button class="tab-btn" onclick="showTab('schema')"> Database Tables & Schema</button>
        <button class="tab-btn" onclick="showTab('sql')"> SQL Query Console</button>
        <button class="tab-btn" onclick="showTab('erd')"> Schema ERD</button>
    </div>

    <!-- TAB 1: MANIFEST EXPLORER -->
    <div id="tab-manifest" class="panel">
        <div class="controls">
            <input type="text" id="manifest-search" placeholder="Search filename, SHA-256, MD5, or path..." style="width: 320px;" oninput="debounceFetch()">
            <select id="manifest-status" onchange="fetchManifest()">
                <option value="ALL">All Statuses</option>
                <option value="PENDING">PENDING</option>
                <option value="VERIFIED_COPIED">VERIFIED_COPIED</option>
                <option value="SKIPPED_DUPLICATE">SKIPPED_DUPLICATE</option>
                <option value="FAILED_ERROR">FAILED_ERROR</option>
            </select>
            <span id="manifest-count-label" style="color: var(--text-dim); margin-left: auto;">Showing 0 records</span>
        </div>

        <div class="table-responsive">
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Status</th>
                        <th>Filename</th>
                        <th>Size</th>
                        <th>SHA-256 Checksum</th>
                        <th>Hex Vault Destination</th>
                        <th>Scanned At</th>
                    </tr>
                </thead>
                <tbody id="manifest-tbody">
                    <tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 24px;">No files cataloged yet. Run the scanner script to populate the manifest.</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- TAB 2: SCHEMA EXPLORER -->
    <div id="tab-schema" class="panel hidden">
        <div class="controls">
            <label style="font-weight: 600; color: var(--text-dim);">Select Table:</label>
            <select id="schema-table-select" onchange="fetchSchema()"></select>
        </div>
        <h4 style="font-size: 13px; margin-bottom: 8px; color: var(--accent-cyan);">Columns Definition</h4>
        <div class="table-responsive" style="margin-bottom: 16px;">
            <table>
                <thead>
                    <tr><th>Column Name</th><th>Data Type</th><th>Nullable</th><th>Default</th></tr>
                </thead>
                <tbody id="schema-cols-tbody"></tbody>
            </table>
        </div>
        <h4 style="font-size: 13px; margin-bottom: 8px; color: var(--accent-cyan);">Indexes</h4>
        <div class="table-responsive">
            <table>
                <thead><tr><th>Index Name</th><th>Definition</th></tr></thead>
                <tbody id="schema-idx-tbody"></tbody>
            </table>
        </div>
    </div>

    <!-- TAB 3: SQL QUERY CONSOLE -->
    <div id="tab-sql" class="panel hidden">
        <div class="sql-layout">
            <!-- LEFT 25%: Pre-Canned Forensic Queries -->
            <div class="sql-sidebar">
                <div style="font-weight: 700; font-size: 12px; color: var(--accent-cyan); display: flex; align-items: center; justify-content: space-between; padding-bottom: 4px; border-bottom: 1px solid var(--border);">
                    <span> Pre-Canned Queries</span>
                    <span style="font-size: 9px; color: var(--text-dim); text-transform: uppercase;">Click to run</span>
                </div>

                <div class="precanned-item" onclick="loadSQL(0)">
                    <div class="precanned-title"><span> Deduplication Ratio</span><span class="badge" style="font-size: 9px; padding: 1px 5px;">CAS</span></div>
                    <div class="precanned-desc">Overall deduplication ratio across cases.</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(1)">
                    <div class="precanned-title"><span> Multi-Model AI Vectors</span><span class="badge" style="font-size: 9px; padding: 1px 5px; color: #00f2fe; border-color: #00f2fe;">VEC</span></div>
                    <div class="precanned-desc">Vectors by model (CLIP 512, SigLIP 768).</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(2)">
                    <div class="precanned-title"><span> Top Duplicated Files</span><span class="badge" style="font-size: 9px; padding: 1px 5px;">SAVINGS</span></div>
                    <div class="precanned-desc">Assets appearing in the most case folders.</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(3)">
                    <div class="precanned-title"><span>[*] Forensic Audit Verdict</span><span class="badge" style="font-size: 9px; padding: 1px 5px; color: #10b981; border-color: #10b981;">ISO 27037</span></div>
                    <div class="precanned-desc">Full v_forensic_integrity_audit view.</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(4)">
                    <div class="precanned-title"><span> Migration Summary</span><span class="badge" style="font-size: 9px; padding: 1px 5px;">STATS</span></div>
                    <div class="precanned-desc">Summary metrics from v_migration_summary.</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(5)">
                    <div class="precanned-title"><span> Tagged Case Evidence</span><span class="badge" style="font-size: 9px; padding: 1px 5px;">TAGS</span></div>
                    <div class="precanned-desc">Evidence with series or tags assigned.</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(6)">
                    <div class="precanned-title"><span> Action Audit Trail</span><span class="badge" style="font-size: 9px; padding: 1px 5px; color: #c084fc; border-color: #c084fc;">AUDIT</span></div>
                    <div class="precanned-desc">Custody logs in case_evidence_actions.</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(7)">
                    <div class="precanned-title"><span>[!] Reference Collision Alerts</span><span class="badge" style="font-size: 9px; padding: 1px 5px; color: #f43f5e; border-color: #f43f5e;">INTEL</span></div>
                    <div class="precanned-desc">Exact matches with reference intelligence.</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(8)">
                    <div class="precanned-title"><span> Active Unique Cases</span><span class="badge" style="font-size: 9px; padding: 1px 5px; color: #00f2fe; border-color: #00f2fe;">CASES</span></div>
                    <div class="precanned-desc">List all unique cases & evidence counts.</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(9)">
                    <div class="precanned-title"><span> Cross-Case Overlaps</span><span class="badge" style="font-size: 9px; padding: 1px 5px; color: #f59e0b; border-color: #f59e0b;">CROSS-CASE</span></div>
                    <div class="precanned-desc">Assets appearing in multiple distinct cases.</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(10)">
                    <div class="precanned-title"><span> 24-Hour Shift Activity</span><span class="badge" style="font-size: 9px; padding: 1px 5px; color: #10b981; border-color: #10b981;">SHIFT</span></div>
                    <div class="precanned-desc">Evidence actions in the last 24 hours.</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(11)">
                    <div class="precanned-title"><span> Camera & EXIF Cluster</span><span class="badge" style="font-size: 9px; padding: 1px 5px; color: #00f2fe; border-color: #00f2fe;">EXIF</span></div>
                    <div class="precanned-desc">Group photos by camera make & model.</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(12)">
                    <div class="precanned-title"><span> Video Keyframe Breakdown</span><span class="badge" style="font-size: 9px; padding: 1px 5px; color: #c084fc; border-color: #c084fc;">VIDEO</span></div>
                    <div class="precanned-desc">Video durations and sampled keyframes.</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(13)">
                    <div class="precanned-title"><span>[!] Unreviewed Backlog</span><span class="badge" style="font-size: 9px; padding: 1px 5px; color: #f43f5e; border-color: #f43f5e;">BACKLOG</span></div>
                    <div class="precanned-desc">Untagged & unreviewed items by case.</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(14)">
                    <div class="precanned-title"><span> Vector Coverage Health</span><span class="badge" style="font-size: 9px; padding: 1px 5px; color: #00f2fe; border-color: #00f2fe;">EMBEDDINGS</span></div>
                    <div class="precanned-desc">AI embedding indexing coverage check.</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(15)">
                    <div class="precanned-title"><span> Series & Custody Matrix</span><span class="badge" style="font-size: 9px; padding: 1px 5px; color: #10b981; border-color: #10b981;">SERIES</span></div>
                    <div class="precanned-desc">Classification counts across all series.</div>
                </div>

                <div class="precanned-item" onclick="loadSQL(16)">
                    <div class="precanned-title"><span> Geolocation & EXIF GPS</span><span class="badge" style="font-size: 9px; padding: 1px 5px; color: #00f2fe; border-color: #00f2fe;">GEO-INTEL</span></div>
                    <div class="precanned-desc">GPS latitude, longitude, and map links.</div>
                </div>
            </div>

            <!-- RIGHT 75%: Custom SQL Query Editor -->
            <div class="sql-main">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <label style="font-weight: 600; color: var(--text-dim);">Execute Custom Read-Only Query (SELECT ...):</label>
                    <span style="font-size: 11px; color: var(--text-dim); font-family: 'JetBrains Mono', monospace;">Tip: Press Ctrl+Enter to execute</span>
                </div>
                <textarea id="sql-input" rows="8" style="font-family: 'JetBrains Mono', monospace; font-size: 12px; width: 100%; height: 180px; resize: vertical;">SELECT * FROM migration_manifest LIMIT 10;</textarea>
                <div style="display: flex; gap: 8px; align-items: center;">
                    <button onclick="runSQL()" class="btn">[*] Execute Query</button>
                    <button onclick="clearSQL()" class="btn" style="background: rgba(255,255,255,0.08); color: var(--text-dim);"> Clear</button>
                    <button onclick="copySQL()" class="btn" style="background: rgba(255,255,255,0.08); color: var(--text-dim);"> Copy SQL</button>
                </div>
            </div>
        </div>
        <div class="table-responsive">
            <table id="sql-results-table">
                <thead id="sql-thead"></thead>
                <tbody id="sql-tbody"><tr><td style="color: var(--text-dim);">Execute a query to see results here.</td></tr></tbody>
            </table>
        </div>
    </div>

    <!-- TAB 4: ENTITY RELATIONSHIP DIAGRAM (ERD) -->
    <div id="tab-erd" class="panel hidden">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; border-bottom: 1px solid var(--border); padding-bottom: 10px;">
            <div>
                <h3 style="font-family: 'Outfit', sans-serif; font-size: 16px; color: var(--accent-cyan);">SYMPICS Relational Schema Topology (Crow's Foot ERD)</h3>
                <p style="color: var(--text-dim); font-size: 12px; margin-top: 2px;">Visual Entity Relationship Diagram • Content-Addressable Storage, Cases, and pgvector Vector Store</p>
            </div>
            <span class="badge" style="background: rgba(16, 185, 129, 0.15); border-color: var(--accent-green); color: var(--accent-green);">6 CORE ENTITIES • CROW'S FOOT NOTATION</span>
        </div>

        <!-- VISUAL CROW'S FOOT ERD CANVAS -->
        <div style="background: #0d1117; border: 1px solid rgba(255,255,255,0.12); border-radius: 10px; padding: 20px; overflow-x: auto; margin-bottom: 24px; box-shadow: inset 0 2px 10px rgba(0,0,0,0.6);">
            <svg viewBox="0 0 1100 700" width="100%" height="auto" style="min-width: 960px; font-family: 'Inter', -apple-system, sans-serif;">
                <defs>
                    <filter id="shadow" x="-5%" y="-5%" width="110%" height="115%" filterUnits="userSpaceOnUse">
                        <feDropShadow dx="2" dy="4" stdDeviation="4" flood-color="#000" flood-opacity="0.5"/>
                    </filter>
                </defs>

                <!-- RELATIONSHIP LINES -->
                <!-- 1. cases to case_evidence_items (1 : N) -->
                <path d="M 160 230 L 160 380" stroke="#94a3b8" stroke-width="2" fill="none" />
                <!-- 1 (one mandatory) tick -->
                <line x1="150" y1="260" x2="170" y2="260" stroke="#94a3b8" stroke-width="2.5" />
                <line x1="150" y1="268" x2="170" y2="268" stroke="#94a3b8" stroke-width="2.5" />
                <!-- N (crow's foot) fork -->
                <line x1="148" y1="380" x2="160" y2="355" stroke="#94a3b8" stroke-width="2.5" />
                <line x1="172" y1="380" x2="160" y2="355" stroke="#94a3b8" stroke-width="2.5" />

                <!-- 2. media_assets to case_evidence_items (1 : N) -->
                <path d="M 430 460 L 290 460" stroke="#94a3b8" stroke-width="2" fill="none" />
                <!-- 1 (one mandatory) tick -->
                <line x1="400" y1="450" x2="400" y2="470" stroke="#94a3b8" stroke-width="2.5" />
                <line x1="392" y1="450" x2="392" y2="470" stroke="#94a3b8" stroke-width="2.5" />
                <!-- N (crow's foot) fork -->
                <line x1="290" y1="448" x2="315" y2="460" stroke="#94a3b8" stroke-width="2.5" />
                <line x1="290" y1="472" x2="315" y2="460" stroke="#94a3b8" stroke-width="2.5" />

                <!-- 3. media_assets to media_embeddings (1 : N) -->
                <path d="M 690 320 L 810 320" stroke="#94a3b8" stroke-width="2" fill="none" />
                <!-- 1 (one mandatory) tick -->
                <line x1="720" y1="310" x2="720" y2="330" stroke="#94a3b8" stroke-width="2.5" />
                <line x1="728" y1="310" x2="728" y2="330" stroke="#94a3b8" stroke-width="2.5" />
                <!-- N (crow's foot) fork -->
                <line x1="810" y1="308" x2="785" y2="320" stroke="#94a3b8" stroke-width="2.5" />
                <line x1="810" y1="332" x2="785" y2="320" stroke="#94a3b8" stroke-width="2.5" />

                <!-- 4. migration_manifest to media_assets (Bit Hash Cross-Ref) -->
                <path d="M 560 170 L 560 220" stroke="#f59e0b" stroke-width="2" stroke-dasharray="4,4" fill="none" />
                <circle cx="560" cy="170" r="3" fill="#f59e0b" />
                <circle cx="560" cy="220" r="3" fill="#f59e0b" />

                <!-- 5. reference_catalog_records to media_assets (MD5/SHA1 Intel) -->
                <path d="M 790 570 L 610 570 L 610 500" stroke="#f43f5e" stroke-width="2" stroke-dasharray="4,4" fill="none" />
                <circle cx="790" cy="570" r="3" fill="#f43f5e" />
                <circle cx="610" cy="500" r="3" fill="#f43f5e" />

                <!-- TABLE 1: CASES (Purple) -->
                <g filter="url(#shadow)">
                    <rect x="50" y="40" width="220" height="180" rx="6" fill="#1e1b4b" stroke="#a855f7" stroke-width="1.5" />
                    <!-- Header -->
                    <rect x="50" y="40" width="220" height="32" rx="6" fill="#d8b4e2" />
                    <rect x="50" y="66" width="220" height="6" fill="#d8b4e2" />
                    <text x="160" y="61" fill="#3b0764" font-weight="700" font-size="13" text-anchor="middle">cases</text>
                    <!-- Split Divider -->
                    <line x1="90" y1="72" x2="90" y2="220" stroke="rgba(255,255,255,0.15)" stroke-width="1" />
                    <!-- Left Key Column -->
                    <text x="70" y="94" fill="#facc15" font-weight="700" font-size="11" text-anchor="middle">PK</text>
                    <text x="70" y="114" fill="#c084fc" font-weight="700" font-size="11" text-anchor="middle">UQ</text>
                    <!-- Right Fields Column -->
                    <text x="100" y="94" fill="#f8fafc" font-weight="700" font-size="11">case_id</text>
                    <text x="100" y="114" fill="#e2e8f0" font-style="italic" font-size="11">case_number</text>
                    <text x="100" y="134" fill="#cbd5e1" font-size="11">case_name</text>
                    <text x="100" y="154" fill="#cbd5e1" font-size="11">lead_investigator</text>
                    <text x="100" y="174" fill="#cbd5e1" font-size="11">agency_name</text>
                    <text x="100" y="194" fill="#cbd5e1" font-size="11">status</text>
                    <text x="100" y="212" fill="#94a3b8" font-size="10">created_at</text>
                </g>

                <!-- TABLE 2: CASE_EVIDENCE_ITEMS (Yellow/Amber) -->
                <g filter="url(#shadow)">
                    <rect x="50" y="380" width="240" height="240" rx="6" fill="#422006" stroke="#eab308" stroke-width="1.5" />
                    <!-- Header -->
                    <rect x="50" y="380" width="240" height="32" rx="6" fill="#fef08a" />
                    <rect x="50" y="406" width="240" height="6" fill="#fef08a" />
                    <text x="170" y="401" fill="#713f12" font-weight="700" font-size="13" text-anchor="middle">case_evidence_items</text>
                    <!-- Split Divider -->
                    <line x1="90" y1="412" x2="90" y2="620" stroke="rgba(255,255,255,0.15)" stroke-width="1" />
                    <!-- Left Key Column -->
                    <text x="70" y="434" fill="#facc15" font-weight="700" font-size="11" text-anchor="middle">PK</text>
                    <text x="70" y="454" fill="#38bdf8" font-weight="700" font-size="11" text-anchor="middle">FK</text>
                    <text x="70" y="474" fill="#38bdf8" font-weight="700" font-size="11" text-anchor="middle">FK</text>
                    <text x="70" y="494" fill="#c084fc" font-weight="700" font-size="11" text-anchor="middle">UQ</text>
                    <!-- Right Fields Column -->
                    <text x="100" y="434" fill="#f8fafc" font-weight="700" font-size="11">evidence_id</text>
                    <text x="100" y="454" fill="#e2e8f0" font-style="italic" font-size="11">case_id</text>
                    <text x="100" y="474" fill="#e2e8f0" font-style="italic" font-size="11">asset_id</text>
                    <text x="100" y="494" fill="#e2e8f0" font-style="italic" font-size="11">original_filepath</text>
                    <text x="100" y="514" fill="#cbd5e1" font-size="11">original_filename</text>
                    <text x="100" y="534" fill="#cbd5e1" font-size="11">source_parent_dir</text>
                    <text x="100" y="554" fill="#cbd5e1" font-size="11">custody_status</text>
                    <text x="100" y="574" fill="#94a3b8" font-size="10">created_at</text>
                </g>

                <!-- TABLE 3: MEDIA_ASSETS (Sky Blue - Center Hub) -->
                <g filter="url(#shadow)">
                    <rect x="430" y="220" width="260" height="280" rx="6" fill="#082f49" stroke="#0ea5e9" stroke-width="2" />
                    <!-- Header -->
                    <rect x="430" y="220" width="260" height="32" rx="6" fill="#bae6fd" />
                    <rect x="430" y="246" width="260" height="6" fill="#bae6fd" />
                    <text x="560" y="241" fill="#0c4a6e" font-weight="700" font-size="13" text-anchor="middle">media_assets (CAS Hub)</text>
                    <!-- Split Divider -->
                    <line x1="475" y1="252" x2="475" y2="500" stroke="rgba(255,255,255,0.15)" stroke-width="1" />
                    <!-- Left Key Column -->
                    <text x="452" y="274" fill="#facc15" font-weight="700" font-size="11" text-anchor="middle">PK</text>
                    <text x="452" y="294" fill="#c084fc" font-weight="700" font-size="11" text-anchor="middle">UQ</text>
                    <text x="452" y="314" fill="#34d399" font-weight="700" font-size="11" text-anchor="middle">IX</text>
                    <text x="452" y="334" fill="#34d399" font-weight="700" font-size="11" text-anchor="middle">IX</text>
                    <!-- Right Fields Column -->
                    <text x="485" y="274" fill="#f8fafc" font-weight="700" font-size="11">asset_id (UUID)</text>
                    <text x="485" y="294" fill="#e2e8f0" font-style="italic" font-size="11">sha256 (64-hex CAS)</text>
                    <text x="485" y="314" fill="#e2e8f0" font-size="11">md5 (32-hex)</text>
                    <text x="485" y="334" fill="#e2e8f0" font-size="11">sha1 (40-hex)</text>
                    <text x="485" y="354" fill="#cbd5e1" font-size="11">file_size_bytes</text>
                    <text x="485" y="374" fill="#cbd5e1" font-size="11">media_type (IMAGE/VID)</text>
                    <text x="485" y="394" fill="#cbd5e1" font-size="11">storage_rel_path (00/00)</text>
                    <text x="485" y="414" fill="#cbd5e1" font-size="11">thumb_rel_path (WebP)</text>
                    <text x="485" y="434" fill="#34d399" font-size="11">exif_data (JSONB GIN)</text>
                    <text x="485" y="454" fill="#94a3b8" font-size="10">created_at</text>
                </g>

                <!-- TABLE 4: MEDIA_EMBEDDINGS (Cyan/Teal) -->
                <g filter="url(#shadow)">
                    <rect x="810" y="220" width="250" height="220" rx="6" fill="#134e4a" stroke="#14b8a6" stroke-width="1.5" />
                    <!-- Header -->
                    <rect x="810" y="220" width="250" height="32" rx="6" fill="#a5f3fc" />
                    <rect x="810" y="246" width="250" height="6" fill="#a5f3fc" />
                    <text x="935" y="241" fill="#164e63" font-weight="700" font-size="13" text-anchor="middle">media_embeddings (pgvector)</text>
                    <!-- Split Divider -->
                    <line x1="850" y1="252" x2="850" y2="440" stroke="rgba(255,255,255,0.15)" stroke-width="1" />
                    <!-- Left Key Column -->
                    <text x="830" y="274" fill="#facc15" font-weight="700" font-size="11" text-anchor="middle">PK</text>
                    <text x="830" y="294" fill="#38bdf8" font-weight="700" font-size="11" text-anchor="middle">FK</text>
                    <text x="830" y="374" fill="#00f2fe" font-weight="700" font-size="11" text-anchor="middle">VEC</text>
                    <!-- Right Fields Column -->
                    <text x="860" y="274" fill="#f8fafc" font-weight="700" font-size="11">embedding_id</text>
                    <text x="860" y="294" fill="#e2e8f0" font-style="italic" font-size="11">asset_id</text>
                    <text x="860" y="314" fill="#cbd5e1" font-size="11">model_name (SigLIP2)</text>
                    <text x="860" y="334" fill="#cbd5e1" font-size="11">model_version</text>
                    <text x="860" y="354" fill="#cbd5e1" font-size="11">dimension_size (768)</text>
                    <text x="860" y="374" fill="#00f2fe" font-weight="600" font-size="11">embedding_l2 (HNSW)</text>
                    <text x="860" y="394" fill="#94a3b8" font-size="10">created_at</text>
                </g>

                <!-- TABLE 5: MIGRATION_MANIFEST (Mint Green) -->
                <g filter="url(#shadow)">
                    <rect x="430" y="40" width="260" height="130" rx="6" fill="#14532d" stroke="#22c55e" stroke-width="1.5" />
                    <!-- Header -->
                    <rect x="430" y="40" width="260" height="32" rx="6" fill="#bbf7d0" />
                    <rect x="430" y="66" width="260" height="6" fill="#bbf7d0" />
                    <text x="560" y="61" fill="#14532d" font-weight="700" font-size="13" text-anchor="middle">migration_manifest</text>
                    <!-- Split Divider -->
                    <line x1="475" y1="72" x2="475" y2="170" stroke="rgba(255,255,255,0.15)" stroke-width="1" />
                    <!-- Left Key Column -->
                    <text x="452" y="94" fill="#facc15" font-weight="700" font-size="11" text-anchor="middle">PK</text>
                    <text x="452" y="114" fill="#c084fc" font-weight="700" font-size="11" text-anchor="middle">UQ</text>
                    <text x="452" y="134" fill="#34d399" font-weight="700" font-size="11" text-anchor="middle">IX</text>
                    <!-- Right Fields Column -->
                    <text x="485" y="94" fill="#f8fafc" font-weight="700" font-size="11">manifest_id</text>
                    <text x="485" y="114" fill="#e2e8f0" font-style="italic" font-size="11">source_filepath</text>
                    <text x="485" y="134" fill="#cbd5e1" font-size="11">sha256 / md5 / sha1</text>
                    <text x="485" y="154" fill="#fbbf24" font-weight="600" font-size="11">status (VERIFIED/SKIP)</text>
                </g>

                <!-- TABLE 6: REFERENCE_CATALOG_RECORDS (Soft Rose) -->
                <g filter="url(#shadow)">
                    <rect x="790" y="490" width="270" height="170" rx="6" fill="#4c0519" stroke="#f43f5e" stroke-width="1.5" />
                    <!-- Header -->
                    <rect x="790" y="490" width="270" height="32" rx="6" fill="#fecdd3" />
                    <rect x="790" y="516" width="270" height="6" fill="#fecdd3" />
                    <text x="925" y="511" fill="#881337" font-weight="700" font-size="13" text-anchor="middle">reference_catalog_records (Interpol)</text>
                    <!-- Split Divider -->
                    <line x1="835" y1="522" x2="835" y2="660" stroke="rgba(255,255,255,0.15)" stroke-width="1" />
                    <!-- Left Key Column -->
                    <text x="812" y="544" fill="#facc15" font-weight="700" font-size="11" text-anchor="middle">PK</text>
                    <text x="812" y="564" fill="#34d399" font-weight="700" font-size="11" text-anchor="middle">IX</text>
                    <text x="812" y="584" fill="#c084fc" font-weight="700" font-size="11" text-anchor="middle">UQ</text>
                    <!-- Right Fields Column -->
                    <text x="845" y="544" fill="#f8fafc" font-weight="700" font-size="11">record_id</text>
                    <text x="845" y="564" fill="#e2e8f0" font-size="11">md5 / sha1</text>
                    <text x="845" y="584" fill="#e2e8f0" font-style="italic" font-size="11">identifier / series_name</text>
                    <text x="845" y="604" fill="#cbd5e1" font-size="11">flag_identified (BOOL)</text>
                    <text x="845" y="624" fill="#cbd5e1" font-size="11">flag_actionable (BOOL)</text>
                    <text x="845" y="644" fill="#94a3b8" font-size="10">created_at</text>
                </g>
            </svg>
        </div>

        <div class="erd-grid">
            <!-- 1. MEDIA_ASSETS -->
            <div class="erd-card">
                <div class="erd-header head-core">
                    <span>media_assets <small style="font-weight: 400; font-size: 10px; color: var(--text-dim);">(Physical CAS Hub)</small></span>
                    <span class="key-badge key-idx" id="erd-count-media_assets">1,002 rows</span>
                </div>
                <div class="erd-rows">
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-pk">PK</span> asset_id</span>
                        <span class="erd-col-type">UUID</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-uq">UQ</span> sha256</span>
                        <span class="erd-col-type">CHAR(64)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-idx">IDX</span> md5</span>
                        <span class="erd-col-type">CHAR(32)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-idx">IDX</span> sha1</span>
                        <span class="erd-col-type">CHAR(40)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">file_size_bytes</span>
                        <span class="erd-col-type">BIGINT</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">media_type</span>
                        <span class="erd-col-type">VARCHAR(32)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">storage_rel_path</span>
                        <span class="erd-col-type">VARCHAR(512)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">thumb_rel_path</span>
                        <span class="erd-col-type">VARCHAR(512)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-idx">GIN</span> exif_data</span>
                        <span class="erd-col-type">JSONB</span>
                    </div>
                </div>
            </div>

            <!-- 2. MEDIA_EMBEDDINGS -->
            <div class="erd-card">
                <div class="erd-header head-vector">
                    <span>media_embeddings <small style="font-weight: 400; font-size: 10px; color: var(--text-dim);">(pgvector AI)</small></span>
                    <span class="key-badge key-vec" id="erd-count-media_embeddings">229 rows</span>
                </div>
                <div class="erd-rows">
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-pk">PK</span> embedding_id</span>
                        <span class="erd-col-type">UUID</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-fk">FK</span> asset_id</span>
                        <span class="erd-col-type">UUID -> media_assets</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">model_name</span>
                        <span class="erd-col-type">VARCHAR(64)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">model_version</span>
                        <span class="erd-col-type">VARCHAR(64)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">dimension_size</span>
                        <span class="erd-col-type">INTEGER (768)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-vec">HNSW</span> embedding_l2</span>
                        <span class="erd-col-type">vector(768)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">created_at</span>
                        <span class="erd-col-type">TIMESTAMPTZ</span>
                    </div>
                </div>
            </div>

            <!-- 3. CASES -->
            <div class="erd-card">
                <div class="erd-header head-case">
                    <span>cases <small style="font-weight: 400; font-size: 10px; color: var(--text-dim);">(Investigation Container)</small></span>
                    <span class="key-badge key-uq" id="erd-count-cases">1 case</span>
                </div>
                <div class="erd-rows">
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-pk">PK</span> case_id</span>
                        <span class="erd-col-type">UUID</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-uq">UQ</span> case_number</span>
                        <span class="erd-col-type">VARCHAR(128)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">case_name</span>
                        <span class="erd-col-type">VARCHAR(255)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">lead_investigator</span>
                        <span class="erd-col-type">VARCHAR(255)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">agency_name</span>
                        <span class="erd-col-type">VARCHAR(255)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">status</span>
                        <span class="erd-col-type">VARCHAR(64)</span>
                    </div>
                </div>
            </div>

            <!-- 4. CASE_EVIDENCE_ITEMS -->
            <div class="erd-card">
                <div class="erd-header head-junction">
                    <span>case_evidence_items <small style="font-weight: 400; font-size: 10px; color: var(--text-dim);">(Provenance Junction)</small></span>
                    <span class="key-badge key-fk" id="erd-count-case_evidence_items">9,886 items</span>
                </div>
                <div class="erd-rows">
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-pk">PK</span> evidence_id</span>
                        <span class="erd-col-type">UUID</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-fk">FK</span> case_id</span>
                        <span class="erd-col-type">UUID -> cases</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-fk">FK</span> asset_id</span>
                        <span class="erd-col-type">UUID -> media_assets</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-uq">UQ</span> original_filepath</span>
                        <span class="erd-col-type">TEXT</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">original_filename</span>
                        <span class="erd-col-type">VARCHAR(512)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">source_parent_dir</span>
                        <span class="erd-col-type">VARCHAR(512)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">custody_status</span>
                        <span class="erd-col-type">VARCHAR(64)</span>
                    </div>
                </div>
            </div>

            <!-- 5. MIGRATION_MANIFEST -->
            <div class="erd-card">
                <div class="erd-header head-manifest">
                    <span>migration_manifest <small style="font-weight: 400; font-size: 10px; color: var(--text-dim);">(Migration Ledger)</small></span>
                    <span class="key-badge key-pk" id="erd-count-migration_manifest">9,886 rows</span>
                </div>
                <div class="erd-rows">
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-pk">PK</span> manifest_id</span>
                        <span class="erd-col-type">BIGSERIAL</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-uq">UQ</span> source_filepath</span>
                        <span class="erd-col-type">TEXT</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-idx">IDX</span> sha256</span>
                        <span class="erd-col-type">CHAR(64)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-idx">IDX</span> status</span>
                        <span class="erd-col-type">VARCHAR(32)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">destination_abs_path</span>
                        <span class="erd-col-type">TEXT</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">destination_sha256</span>
                        <span class="erd-col-type">CHAR(64) [Readback]</span>
                    </div>
                </div>
            </div>

            <!-- 6. REFERENCE_CATALOG_RECORDS -->
            <div class="erd-card">
                <div class="erd-header head-reference">
                    <span>reference_catalog_records <small style="font-weight: 400; font-size: 10px; color: var(--text-dim);">(Reference Intel)</small></span>
                    <span class="key-badge" style="background: rgba(244,63,94,0.25); color: #fb7185;" id="erd-count-reference_catalog_records">200 entries</span>
                </div>
                <div class="erd-rows">
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-pk">PK</span> record_id</span>
                        <span class="erd-col-type">BIGSERIAL</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-idx">IDX</span> md5</span>
                        <span class="erd-col-type">CHAR(32)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-idx">IDX</span> sha1</span>
                        <span class="erd-col-type">CHAR(40)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name"><span class="key-badge key-uq">UQ</span> identifier</span>
                        <span class="erd-col-type">VARCHAR(128)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">series_name</span>
                        <span class="erd-col-type">VARCHAR(512)</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">flag_identified</span>
                        <span class="erd-col-type">BOOLEAN</span>
                    </div>
                    <div class="erd-row">
                        <span class="erd-col-name">flag_actionable</span>
                        <span class="erd-col-type">BOOLEAN</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- RELATIONSHIP CARDINALITY & FOREIGN KEY FLOW -->
        <div class="rel-banner">
            <h4 style="font-size: 13px; margin-bottom: 10px; color: var(--accent-cyan);">Relational Foreign Key Links & Join Topology</h4>
            <div class="rel-item">
                <span style="color: #34d399; font-weight: 600;">media_assets.asset_id</span>
                <span class="rel-arrow">-></span>
                <span style="color: #00f2fe; font-weight: 600;">media_embeddings.asset_id</span>
                <span class="rel-cardinality">1 : N (CASCADE)</span>
                <span style="color: var(--text-dim); margin-left: auto;">Stores 768-dim SigLIP / SigLIP-2 vectors with HNSW cosine index per physical asset.</span>
            </div>
            <div class="rel-item">
                <span style="color: #34d399; font-weight: 600;">media_assets.asset_id</span>
                <span class="rel-arrow">-></span>
                <span style="color: #38bdf8; font-weight: 600;">case_evidence_items.asset_id</span>
                <span class="rel-cardinality">1 : N (RESTRICT)</span>
                <span style="color: var(--text-dim); margin-left: auto;">Allows one deduplicated physical asset to appear in multiple case files/folders.</span>
            </div>
            <div class="rel-item">
                <span style="color: #c084fc; font-weight: 600;">cases.case_id</span>
                <span class="rel-arrow">-></span>
                <span style="color: #38bdf8; font-weight: 600;">case_evidence_items.case_id</span>
                <span class="rel-cardinality">1 : N (CASCADE)</span>
                <span style="color: var(--text-dim); margin-left: auto;">Groups evidentiary assets, suspect tags, and custody states under case containers.</span>
            </div>
            <div class="rel-item">
                <span style="color: #fbbf24; font-weight: 600;">migration_manifest.sha256</span>
                <span class="rel-arrow"><-></span>
                <span style="color: #34d399; font-weight: 600;">media_assets.sha256</span>
                <span class="rel-cardinality">Exact Bit Hash</span>
                <span style="color: var(--text-dim); margin-left: auto;">Bridges legacy source paths with canonical hex vault paths.</span>
            </div>
            <div class="rel-item">
                <span style="color: #fb7185; font-weight: 600;">reference_catalog_records (md5/sha1)</span>
                <span class="rel-arrow"><-></span>
                <span style="color: #34d399; font-weight: 600;">media_assets (md5/sha1)</span>
                <span class="rel-cardinality">Forensic Intel</span>
                <span style="color: var(--text-dim); margin-left: auto;">Cross-references seized vault evidence with reference intelligence dumps.</span>
            </div>
        </div>
    </div>

    <script>
        let debounceTimer;
        function debounceFetch() {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(fetchManifest, 300);
        }

        function showTab(tabName) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.panel').forEach(p => p.classList.add('hidden'));
            
            if (tabName === 'manifest') {
                document.getElementById('tab-manifest').classList.remove('hidden');
                document.querySelectorAll('.tab-btn')[0].classList.add('active');
                fetchManifest();
            } else if (tabName === 'schema') {
                document.getElementById('tab-schema').classList.remove('hidden');
                document.querySelectorAll('.tab-btn')[1].classList.add('active');
                fetchSchema();
            } else if (tabName === 'sql') {
                document.getElementById('tab-sql').classList.remove('hidden');
                document.querySelectorAll('.tab-btn')[2].classList.add('active');
            } else if (tabName === 'erd') {
                document.getElementById('tab-erd').classList.remove('hidden');
                document.querySelectorAll('.tab-btn')[3].classList.add('active');
            }
        }

        async function refreshData() {
            try {
                const res = await fetch('/api/summary');
                const data = await res.json();
                if (data.success && data.summary) {
                    const s = data.summary;
                    document.getElementById('stat-discovered').textContent = (s.total_files_discovered || 0).toLocaleString();
                    document.getElementById('stat-verified').textContent = (s.verified_copied || 0).toLocaleString();
                    document.getElementById('stat-unique').textContent = (s.total_unique_assets || 0).toLocaleString();
                    document.getElementById('stat-duplicates').textContent = (s.skipped_duplicates || 0).toLocaleString();
                    document.getElementById('stat-pct').textContent = `${s.percent_complete || 0}%`;

                    const tblSelect = document.getElementById('schema-table-select');
                    tblSelect.innerHTML = '';
                    (data.tables || []).forEach(t => {
                        const opt = document.createElement('option');
                        opt.value = t;
                        opt.textContent = t;
                        tblSelect.appendChild(opt);
                    });

                    if (data.table_counts) {
                        for (const [tbl, count] of Object.entries(data.table_counts)) {
                            const badge = document.getElementById(`erd-count-${tbl}`);
                            if (badge) {
                                badge.textContent = `${count.toLocaleString()} ${tbl === 'cases' ? 'case' : 'rows'}`;
                            }
                        }
                    }
                }
                fetchManifest();
            } catch (e) {
                console.error(e);
            }
        }

        async function fetchManifest() {
            const search = document.getElementById('manifest-search').value;
            const status = document.getElementById('manifest-status').value;
            try {
                const res = await fetch(`/api/manifest?search=${encodeURIComponent(search)}&status=${status}&limit=50`);
                const data = await res.json();
                const tbody = document.getElementById('manifest-tbody');
                tbody.innerHTML = '';

                if (data.rows && data.rows.length > 0) {
                    document.getElementById('manifest-count-label').textContent = `Showing ${data.rows.length} of ${data.total} records`;
                    data.rows.forEach(r => {
                        const tr = document.createElement('tr');
                        const szKb = (r.file_size_bytes / 1024).toFixed(1) + ' KB';
                        tr.innerHTML = `
                            <td style="color: var(--text-dim);">${r.manifest_id}</td>
                            <td><span class="tag-status status-${r.status}">${r.status}</span></td>
                            <td style="font-weight: 600; color: var(--text-main);">${r.source_filename}</td>
                            <td style="color: var(--text-dim);">${szKb}</td>
                            <td style="color: var(--accent-cyan);">${r.sha256.substring(0, 16)}...</td>
                            <td style="color: var(--text-dim);">${r.destination_rel_path || 'Pending'}</td>
                            <td style="color: var(--text-dim);">${r.scanned_at ? r.scanned_at.substring(0, 19) : ''}</td>
                        `;
                        tbody.appendChild(tr);
                    });
                } else {
                    document.getElementById('manifest-count-label').textContent = '0 records found';
                    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 20px;">No matching records found.</td></tr>';
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function fetchSchema() {
            const table = document.getElementById('schema-table-select').value || 'migration_manifest';
            try {
                const res = await fetch(`/api/table-schema?table=${table}`);
                const data = await res.json();
                const colsTbody = document.getElementById('schema-cols-tbody');
                const idxTbody = document.getElementById('schema-idx-tbody');
                colsTbody.innerHTML = '';
                idxTbody.innerHTML = '';

                (data.columns || []).forEach(c => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td style="color: var(--accent-cyan); font-weight: 600;">${c.column_name}</td>
                        <td style="color: #38bdf8;">${c.data_type}</td>
                        <td>${c.is_nullable}</td>
                        <td style="color: var(--text-dim);">${c.column_default || 'None'}</td>
                    `;
                    colsTbody.appendChild(tr);
                });

                (data.indexes || []).forEach(idx => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td style="font-weight: 600; color: var(--text-main);">${idx.indexname}</td>
                        <td style="color: var(--text-dim);">${idx.indexdef}</td>
                    `;
                    idxTbody.appendChild(tr);
                });
            } catch (e) {
                console.error(e);
            }
        }

        async function runSQL() {
            const sql = document.getElementById('sql-input').value;
            const thead = document.getElementById('sql-thead');
            const tbody = document.getElementById('sql-tbody');
            thead.innerHTML = '';
            tbody.innerHTML = '<tr><td style="color: var(--accent-cyan);">Executing query...</td></tr>';

            try {
                const res = await fetch('/api/query', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sql })
                });
                const data = await res.json();
                tbody.innerHTML = '';

                if (!data.success) {
                    tbody.innerHTML = `<tr><td style="color: var(--accent-rose);">Error: ${data.error}</td></tr>`;
                    return;
                }

                if (data.rows && data.rows.length > 0) {
                    const cols = Object.keys(data.rows[0]);
                    const htr = document.createElement('tr');
                    cols.forEach(c => {
                        const th = document.createElement('th');
                        th.textContent = c;
                        htr.appendChild(th);
                    });
                    thead.appendChild(htr);

                    data.rows.forEach(r => {
                        const tr = document.createElement('tr');
                        cols.forEach(c => {
                            const td = document.createElement('td');
                            td.textContent = r[c];
                            tr.appendChild(td);
                        });
                        tbody.appendChild(tr);
                    });
                } else {
                    tbody.innerHTML = '<tr><td style="color: var(--text-dim);">Query executed successfully. 0 rows returned.</td></tr>';
                }
            } catch (e) {
                tbody.innerHTML = `<tr><td style="color: var(--accent-rose);">Error: ${e.message}</td></tr>`;
            }
        }

        const precannedQueries = [
            `-- 1. Deduplication Ratio Audit (Physical vs Logical Instances)
SELECT 
    (SELECT COUNT(*) FROM case_evidence_items) AS total_case_evidence_instances,
    (SELECT COUNT(*) FROM media_assets) AS unique_physical_assets,
    ROUND((SELECT COUNT(*)::numeric FROM case_evidence_items) / NULLIF((SELECT COUNT(*) FROM media_assets), 0), 2) AS deduplication_ratio;`,

            `-- 2. Multi-Model AI Vector Embeddings Breakdown
SELECT 
    model_name, 
    model_version, 
    dimension_size, 
    COUNT(*) AS total_vectors 
FROM media_embeddings 
GROUP BY model_name, model_version, dimension_size 
ORDER BY model_name;`,

            `-- 3. Top Duplicated Media Files Across Cases (Identical Hashes, Multiple Filenames)
SELECT 
    a.sha256,
    COUNT(c.evidence_id) AS case_appearances,
    pg_size_pretty(a.file_size_bytes) AS single_file_size,
    pg_size_pretty(a.file_size_bytes * (COUNT(c.evidence_id) - 1)) AS space_saved_by_cas,
    STRING_AGG(DISTINCT c.original_filename, ', ') AS all_filenames
FROM media_assets a
JOIN case_evidence_items c ON a.asset_id = c.asset_id
GROUP BY a.asset_id, a.sha256, a.file_size_bytes
HAVING COUNT(c.evidence_id) > 1
ORDER BY case_appearances DESC
LIMIT 25;`,

            `-- 4. Complete Forensic Integrity Audit View (ISO/IEC 27037)
SELECT * FROM v_forensic_integrity_audit;`,

            `-- 5. Migration Summary View
SELECT * FROM v_migration_summary;`,

            `-- 6. Tagged & Curated Case Evidence Items (Ordered by Most Recent)
SELECT 
    evidence_id, 
    original_filename, 
    source_parent_dir, 
    series_tag, 
    tags, 
    custody_status, 
    last_action,
    last_action_at AS tagged_at
FROM case_evidence_items 
WHERE series_tag IS NOT NULL OR array_length(tags, 1) > 0 
ORDER BY last_action_at DESC 
LIMIT 25;`,

            `-- 7. Forensic Action Audit Trail (With Specific Tag & Series Changes)
SELECT 
    action_id, 
    performed_by, 
    action_type, 
    original_filename, 
    CASE 
        WHEN action_type = 'tag-add' THEN COALESCE('Added tag(s): ' || NULLIF(details->>'added_tags', '[]'), 'Added tag(s): ' || NULLIF(new_value, ''), 'Tags: ' || new_value)
        WHEN action_type = 'tag-delete' THEN COALESCE('Removed tag(s): ' || NULLIF(details->>'removed_tags', '[]'), 'Removed tag(s): ' || NULLIF(previous_value, ''), 'Tags: ' || new_value)
        WHEN action_type = 'series-add' THEN 'Assigned to series: ' || new_value
        WHEN action_type = 'series-delete' THEN 'Removed from series: ' || previous_value
        WHEN action_type = 'ai-tag-confirmed' THEN 'Confirmed AI: ' || COALESCE(NULLIF(new_value, ''), (details->>'tags'), (details->>'series_tag'))
        WHEN action_type = 'ai-tag-rejected' THEN 'Rejected & Cleared: ' || COALESCE(NULLIF(previous_value, ''), (details->>'cleared_tags'), (details->>'cleared_series'))
        WHEN action_type = 'status-change' THEN 'Status: ' || COALESCE(previous_value, 'NONE') || ' -> ' || COALESCE(new_value, 'NONE')
        WHEN action_type = 'notes-update' THEN 'Notes updated'
        ELSE COALESCE(new_value, previous_value, action_type)
    END AS change_description,
    previous_value, 
    new_value, 
    sha256, 
    performed_at 
FROM case_evidence_actions 
ORDER BY performed_at DESC 
LIMIT 25;`,

            `-- 8. Reference Intelligence Watchlist Collisions
SELECT * FROM v_reference_known_collisions LIMIT 25;`,

            `-- 9. Active Unique Cases & Evidence Breakdown
SELECT 
    c.case_number, 
    c.case_name, 
    c.status,
    c.classification_type, 
    c.priority_level, 
    COUNT(cei.evidence_id) AS total_evidence_items, 
    COUNT(DISTINCT cei.series_tag) AS unique_series_count, 
    c.created_at 
FROM cases c 
LEFT JOIN case_evidence_items cei ON c.case_id = cei.case_id 
GROUP BY c.case_id, c.case_number, c.case_name, c.status, c.classification_type, c.priority_level, c.created_at 
ORDER BY c.created_at DESC;`,

            `-- 10. Cross-Case Serial Evidence Overlaps (Multi-Jurisdictional)
SELECT 
    ma.sha256, 
    ma.file_size_bytes, 
    ma.media_type, 
    COUNT(DISTINCT cei.case_id) AS case_count, 
    STRING_AGG(DISTINCT c.case_number, ', ') AS associated_cases, 
    STRING_AGG(DISTINCT cei.series_tag, ', ') AS series_tags 
FROM media_assets ma 
JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id 
JOIN cases c ON cei.case_id = c.case_id 
GROUP BY ma.sha256, ma.file_size_bytes, ma.media_type 
HAVING COUNT(DISTINCT cei.case_id) > 1 
ORDER BY case_count DESC;`,

            `-- 11. 24-Hour Shift Hand-Off Activity
SELECT 
    c.case_number, 
    cei.original_filename, 
    cei.series_tag, 
    cei.custody_status, 
    cei.tags, 
    cei.last_action, 
    cei.last_action_at 
FROM case_evidence_items cei 
JOIN cases c ON cei.case_id = c.case_id 
WHERE cei.last_action_at >= NOW() - INTERVAL '24 hours' 
ORDER BY cei.last_action_at DESC 
LIMIT 25;`,

            `-- 12. Camera & Hardware Attribution from EXIF
SELECT 
    COALESCE(exif_data->>'Make', 'Unknown') AS camera_make, 
    COALESCE(exif_data->>'Model', 'Unknown') AS camera_model, 
    COALESCE(exif_data->>'Software', 'N/A') AS software_version, 
    COUNT(*) AS total_photos, 
    MIN(exif_data->>'DateTimeOriginal') AS earliest_photo, 
    MAX(exif_data->>'DateTimeOriginal') AS latest_photo 
FROM media_assets 
WHERE exif_data IS NOT NULL AND exif_data::text != '{}'::text 
GROUP BY camera_make, camera_model, software_version 
ORDER BY total_photos DESC;`,

            `-- 13. Video Evidence & Keyframe Breakdown
SELECT 
    c.case_number, 
    ma.sha256, 
    ma.duration_seconds, 
    ma.frame_rate, 
    ma.width_pixels || 'x' || ma.height_pixels AS resolution, 
    COUNT(vk.keyframe_id) AS total_keyframes_extracted, 
    ROUND(ma.file_size_bytes / (1024.0 * 1024.0), 2) AS file_size_mb 
FROM media_assets ma 
JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id 
JOIN cases c ON cei.case_id = c.case_id 
LEFT JOIN video_keyframes vk ON ma.asset_id = vk.asset_id 
WHERE ma.media_type = 'VIDEO' 
GROUP BY c.case_number, ma.sha256, ma.duration_seconds, ma.frame_rate, ma.width_pixels, ma.height_pixels, ma.file_size_bytes 
ORDER BY ma.duration_seconds DESC;`,

            `-- 14. Unreviewed Evidence Backlog by Case
SELECT 
    c.case_number, 
    c.priority_level, 
    COUNT(*) AS unreviewed_count, 
    MIN(cei.created_at) AS oldest_unreviewed_date 
FROM case_evidence_items cei 
JOIN cases c ON cei.case_id = c.case_id 
WHERE (cei.series_tag IS NULL OR cei.series_tag = '') 
  AND cei.custody_status IN ('INGESTED', 'UNREVIEWED') 
GROUP BY c.case_number, c.priority_level 
ORDER BY unreviewed_count DESC;`,

            `-- 15. Multi-Model Embedding Completeness Audit
SELECT 
    ma.media_type, 
    COUNT(DISTINCT ma.asset_id) AS total_assets, 
    COUNT(DISTINCT CASE WHEN me.model_name = 'siglip2_naflex' THEN me.asset_id END) AS siglip2_indexed, 
    COUNT(DISTINCT CASE WHEN me.model_name = 'siglip' THEN me.asset_id END) AS siglip_base_indexed, 
    COUNT(DISTINCT CASE WHEN me.model_name = 'clip' THEN me.asset_id END) AS clip_indexed 
FROM media_assets ma 
LEFT JOIN media_embeddings me ON ma.asset_id = me.asset_id 
GROUP BY ma.media_type;`,

            `-- 16. Series Tag & Custody Classification Matrix
SELECT 
    COALESCE(cei.series_tag, 'UNTAGGED') AS series_tag, 
    COUNT(*) AS total_items, 
    COUNT(CASE WHEN cei.custody_status = 'CONFIRMED_MATCH' THEN 1 END) AS confirmed_matches, 
    COUNT(CASE WHEN cei.custody_status = 'CONFIRMED_ACTIONABLE' THEN 1 END) AS actionable_items, 
    COUNT(CASE WHEN cei.custody_status = 'FLAGGED_EXCULPATORY' THEN 1 END) AS exculpatory, 
    COUNT(CASE WHEN cei.custody_status = 'TRIAGED' THEN 1 END) AS triaged 
FROM case_evidence_items cei 
GROUP BY cei.series_tag 
ORDER BY total_items DESC;`,

            `-- 17. Geolocation & EXIF GPS Coordinate Intelligence
SELECT 
    ma.asset_id,
    COALESCE(
        (SELECT cei.original_filename FROM case_evidence_items cei WHERE cei.asset_id = ma.asset_id LIMIT 1),
        split_part(ma.storage_rel_path, '/', -1)
    ) AS filename,
    ma.source_folder,
    ma.gps_latitude,
    ma.gps_longitude,
    ma.gps_altitude,
    'https://www.google.com/maps?q=' || ma.gps_latitude || ',' || ma.gps_longitude AS google_maps_link,
    ma.exif_data->>'Make' AS camera_make,
    ma.exif_data->>'Model' AS camera_model,
    ma.exif_data->>'DateTimeOriginal' AS date_taken
FROM media_assets ma
WHERE ma.gps_latitude IS NOT NULL AND ma.gps_longitude IS NOT NULL
ORDER BY ma.created_at DESC;`
        ];

        function loadSQL(idx) {
            if (precannedQueries[idx]) {
                document.getElementById('sql-input').value = precannedQueries[idx];
                runSQL();
            }
        }

        function clearSQL() {
            document.getElementById('sql-input').value = '';
            document.getElementById('sql-input').focus();
        }

        function copySQL() {
            const sql = document.getElementById('sql-input').value;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(sql);
            } else {
                const ta = document.createElement('textarea');
                ta.value = sql;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
            }
            alert('SQL query copied to clipboard!');
        }

        // Ctrl+Enter or Cmd+Enter to execute query
        document.addEventListener('DOMContentLoaded', () => {
            const sqlBox = document.getElementById('sql-input');
            if (sqlBox) {
                sqlBox.addEventListener('keydown', (e) => {
                    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                        e.preventDefault();
                        runSQL();
                    }
                });
            }
        });

        // Init
        refreshData();
    </script>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))


def start_dashboard(port=DASHBOARD_PORT):
    # Bind to 0.0.0.0 so it is reachable remotely across LAN/VPN or SSH port forward
    HTTPServer.allow_reuse_address = True
    server = HTTPServer(("0.0.0.0", port), DashboardHTTPHandler)
    
    # Try to resolve local LAN IP for convenience
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"

    print(f"\n===============================================================================")
    print(f"  SYMPICS DATABASE EXPLORER WEB UI ACTIVE")
    print(f"===============================================================================")
    print(f"  • Local Access         : http://localhost:{port}")
    print(f"  • Network Access       : http://{local_ip}:{port}")
    print(f"  • Remote SSH Tunnel    : ssh -L {port}:localhost:{port} <user>@<server-ip>")
    print(f"                           Then open http://localhost:{port} in your browser")
    print(f"===============================================================================\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Database Explorer.")


if __name__ == "__main__":
    p = DASHBOARD_PORT
    if len(sys.argv) > 1:
        try:
            p = int(sys.argv[1])
        except ValueError:
            pass
    start_dashboard(port=p)
