# Copyright 2026 Google LLC
# Licensed under Apache 2.0

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
