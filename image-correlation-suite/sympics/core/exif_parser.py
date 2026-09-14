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
SYMPICS EXIF & GPS Metadata Parser
================================
Extracts camera settings, timestamps, and converts EXIF GPSInfo (DMS) to decimal degrees.
"""

from typing import Tuple, Optional, Dict, Any
from PIL import Image, ExifTags
from sympics.core.raw_extractor import load_image_or_raw


def sanitize_for_pg_json(obj: Any) -> Any:
    """Recursively removes null bytes (\\x00) to prevent Postgres JSON errors."""
    if isinstance(obj, dict):
        return {str(k).replace("\x00", "").replace("\u0000", ""): sanitize_for_pg_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_pg_json(item) for item in obj]
    elif isinstance(obj, str):
        return obj.replace("\x00", "").replace("\u0000", "")
    return str(obj).replace("\x00", "").replace("\u0000", "") if not isinstance(obj, (int, float, bool)) else obj


def dms_to_decimal(dms: Tuple, ref: str) -> Optional[float]:
    """Converts (Degrees, Minutes, Seconds) tuple to decimal degrees with N/S/E/W sign."""
    if not dms or len(dms) < 3:
        return None

    def to_f(v):
        if isinstance(v, (int, float)):
            return float(v)
        if hasattr(v, "numerator") and hasattr(v, "denominator"):
            return v.numerator / v.denominator if v.denominator != 0 else 0.0
        return float(v)

    try:
        deg = to_f(dms[0])
        minutes = to_f(dms[1])
        seconds = to_f(dms[2])
        dec = deg + (minutes / 60.0) + (seconds / 3600.0)
        if ref in ("S", "W"):
            dec = -dec
        return round(dec, 6)
    except Exception:
        return None


def extract_exif_metadata(filepath: str) -> Tuple[Optional[int], Optional[int], Dict[str, Any]]:
    """Extracts width, height, and sanitized EXIF dictionary."""
    width, height = None, None
    exif_data = {}
    try:
        img = load_image_or_raw(filepath)
        if img:
            width, height = img.size
            raw_exif = img._getexif() if hasattr(img, "_getexif") else None
            if raw_exif:
                for tag_id, val in raw_exif.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    if isinstance(val, (bytes, bytearray)):
                        try:
                            val = val.decode("utf-8", errors="ignore")
                        except Exception:
                            val = f"<binary {len(val)} bytes>"
                    elif hasattr(val, "values"):
                        val = str(val)
                    elif not isinstance(val, (str, int, float, bool, list, dict)):
                        val = str(val)
                    exif_data[str(tag_name)] = val
    except Exception:
        pass
    return width, height, sanitize_for_pg_json(exif_data)


def extract_gps_coordinates(filepath: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Extracts (latitude, longitude, altitude) in decimal degrees/meters."""
    try:
        img = load_image_or_raw(filepath)
        if not img:
            return None, None, None
        raw_exif = img._getexif() if hasattr(img, "_getexif") else None
        if not raw_exif:
            return None, None, None

        gps_info = None
        for tag_id, val in raw_exif.items():
            if ExifTags.TAGS.get(tag_id) == "GPSInfo":
                gps_info = val
                break

        if not gps_info or not isinstance(gps_info, dict):
            return None, None, None

        lat = dms_to_decimal(gps_info.get(2), gps_info.get(1))
        lon = dms_to_decimal(gps_info.get(4), gps_info.get(3))
        alt = None
        if 6 in gps_info:
            raw_alt = gps_info[6]
            if hasattr(raw_alt, "numerator") and hasattr(raw_alt, "denominator"):
                alt = raw_alt.numerator / raw_alt.denominator if raw_alt.denominator != 0 else None
            elif isinstance(raw_alt, (int, float)):
                alt = float(raw_alt)
            if alt is not None:
                alt = round(float(alt), 2)

        return lat, lon, alt
    except Exception:
        return None, None, None
