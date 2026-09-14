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
Unit tests for Zip/Tar Slip directory traversal security defenses.
"""
import io
import os
import zipfile
import pytest
from sympics.core.archive import is_safe_path, safe_extract_zip


def test_is_safe_path():
    base = "/tmp/sympics_staging"
    assert is_safe_path(base, "/tmp/sympics_staging/photo.jpg") is True
    assert is_safe_path(base, "/tmp/sympics_staging/sub/photo.jpg") is True
    assert is_safe_path(base, "/tmp/sympics_staging/../etc/passwd") is False
    assert is_safe_path(base, "/etc/passwd") is False


def test_zip_slip_prevention(tmp_path):
    dest_dir = tmp_path / "extracted"
    zip_path = tmp_path / "malicious.zip"

    # Create a malicious zip file containing path traversal
    with zipfile.ZipFile(str(zip_path), "w") as zf:
        zf.writestr("../../malicious.txt", "MALICIOUS_CONTENT")

    with pytest.raises(ValueError, match="Zip Slip"):
        safe_extract_zip(str(zip_path), str(dest_dir))
