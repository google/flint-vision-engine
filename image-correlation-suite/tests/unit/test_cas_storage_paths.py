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
Unit tests for CAS 2-layer hex path resolution.
"""
from sympics.core.cas_vault import build_cas_rel_path, build_thumbnail_rel_path, get_media_category


def test_build_cas_rel_path_images():
    sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    path = build_cas_rel_path(sha256, ".jpg")
    assert path == f"01_Media_Vault/images/e3/b0/{sha256}.jpg"


def test_build_cas_rel_path_raw():
    sha256 = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    path = build_cas_rel_path(sha256, ".cr3")
    assert path == f"01_Media_Vault/images/12/34/{sha256}.cr3"


def test_build_cas_rel_path_videos():
    sha256 = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    path = build_cas_rel_path(sha256, ".mp4")
    assert path == f"01_Media_Vault/videos/ab/cd/{sha256}.mp4"


def test_build_thumbnail_rel_path():
    sha256 = "99887766554433221100aabbccddeeff99887766554433221100aabbccddeeff"
    path = build_thumbnail_rel_path(sha256)
    assert path == f"02_Keyframe_Vault/thumbs_256px/99/88/{sha256}.webp"
