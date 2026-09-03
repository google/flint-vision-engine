# Copyright 2026 Google LLC
# Licensed under Apache 2.0

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
