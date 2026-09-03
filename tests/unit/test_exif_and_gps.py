# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
Unit tests for EXIF and GPS coordinate parsing.
"""
from sympics.core.exif_parser import dms_to_decimal, sanitize_for_pg_json


def test_dms_to_decimal_north_west():
    # 37° 46' 29.88" N -> 37.774967
    lat = dms_to_decimal((37, 46, 29.88), "N")
    assert abs(lat - 37.774967) < 0.0001

    # 122° 25' 9.84" W -> -122.4194
    lon = dms_to_decimal((122, 25, 9.84), "W")
    assert abs(lon - (-122.4194)) < 0.0001


def test_dms_to_decimal_south_east():
    # 33° 51' 35.88" S -> -33.859967
    lat = dms_to_decimal((33, 51, 35.88), "S")
    assert abs(lat - (-33.859967)) < 0.0001


def test_sanitize_for_pg_json():
    dirty_dict = {
        "title": "Photo\x00_Evidence",
        "nested": ["Camera\u0000_Model", {"exif\x00_tag": "Value\x00"}],
        "count": 42
    }
    clean = sanitize_for_pg_json(dirty_dict)
    assert "\x00" not in str(clean)
    assert "\u0000" not in str(clean)
    assert clean["title"] == "Photo_Evidence"
    assert clean["nested"][0] == "Camera_Model"
    assert clean["nested"][1]["exif_tag"] == "Value"
    assert clean["count"] == 42
