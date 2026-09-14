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
Integration tests for SYMPICS Web Server REST APIs and Security Sandbox.
"""
import urllib.request
import json
import pytest


def make_request(path, method="GET", body=None):
    url = f"http://localhost:8080{path}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8")) if e.fp else {}


def test_telemetry_endpoint():
    status, data = make_request("/api/telemetry")
    assert status == 200
    assert data["success"] is True


def test_sql_sandbox_safe_query():
    status, data = make_request("/api/query", method="POST", body={"sql": "SELECT count(*) as total FROM media_assets;"})
    assert status == 200
    assert data["success"] is True
    assert "rows" in data


def test_sql_sandbox_blocks_destructive():
    # Destructive DROP should return error
    status, data = make_request("/api/query", method="POST", body={"sql": "DROP TABLE media_assets;"})
    assert data["success"] is False
    assert "Security Block" in data["error"]


def test_sql_sandbox_blocks_chaining():
    status, data = make_request("/api/query", method="POST", body={"sql": "SELECT 1; DROP TABLE media_assets;"})
    assert data["success"] is False
    assert "Security Block" in data["error"]
