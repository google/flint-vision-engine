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
Shared Pytest Fixtures for SYMPICS Test Suite
"""
import io
import os
import sys
import pytest
from PIL import Image

# Ensure project root is in sys.path
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

_db_dir = os.path.join(_root, "database")
if _db_dir not in sys.path:
    sys.path.insert(0, _db_dir)


@pytest.fixture
def sample_rgb_image(tmp_path):
    """Creates a sample 100x100 RGB JPEG image for testing."""
    img_path = tmp_path / "sample.jpg"
    img = Image.new("RGB", (100, 100), color=(73, 109, 137))
    img.save(str(img_path), "JPEG")
    return str(img_path)


@pytest.fixture
def sample_binary_data():
    """Returns sample binary payload."""
    return b"SYMPICS_FORENSIC_INTEGRITY_TEST_PAYLOAD_1234567890"
