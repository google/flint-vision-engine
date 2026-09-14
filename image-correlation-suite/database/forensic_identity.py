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
SYMPICS FORENSIC IDENTITY & HARDWARE ATTRIBUTION MODULE (ISO/IEC 27037)
===============================================================================
Captures logged-in OS / LDAP examiner identity and immutable machine hardware ID
(Motherboard DMI UUID, Linux machine-id, Windows csproduct UUID) to establish
cryptographic and physical station attribution for all audit trail actions.
===============================================================================
"""

import os
import getpass
import platform
import subprocess
import uuid

_CACHED_STATION_ID = None
_CACHED_EXAMINER_USER = None


def get_examiner_username():
    """Returns the authenticated OS user or LDAP username."""
    global _CACHED_EXAMINER_USER
    if _CACHED_EXAMINER_USER:
        return _CACHED_EXAMINER_USER

    for fn in [
        lambda: getpass.getuser(),
        lambda: os.getlogin(),
        lambda: os.environ.get("USER"),
        lambda: os.environ.get("USERNAME"),
        lambda: os.environ.get("LOGNAME"),
        lambda: os.environ.get("LDAP_USER")
    ]:
        try:
            u = fn()
            if u and str(u).strip():
                _CACHED_EXAMINER_USER = str(u).strip()
                return _CACHED_EXAMINER_USER
        except Exception:
            pass

    _CACHED_EXAMINER_USER = "examiner"
    return _CACHED_EXAMINER_USER


def get_hardware_station_id():
    """
    Returns the immutable hardware Motherboard UUID or Machine UUID.
    Supports Linux DMI/sysfs, Windows WMIC/PowerShell, and MAC fallback.
    """
    global _CACHED_STATION_ID
    if _CACHED_STATION_ID:
        return _CACHED_STATION_ID

    # 1. Linux DMI Product UUID (Motherboard / BIOS UUID)
    try:
        dmi_path = "/sys/class/dmi/id/product_uuid"
        if os.path.exists(dmi_path):
            with open(dmi_path, "r") as f:
                val = f.read().strip()
                if val and val.lower() not in ("none", "00000000-0000-0000-0000-000000000000"):
                    _CACHED_STATION_ID = val
                    return _CACHED_STATION_ID
    except Exception:
        pass

    # 2. Linux /etc/machine-id
    try:
        if os.path.exists("/etc/machine-id"):
            with open("/etc/machine-id", "r") as f:
                val = f.read().strip()
                if val:
                    _CACHED_STATION_ID = val
                    return _CACHED_STATION_ID
    except Exception:
        pass

    # 3. Windows WMIC / PowerShell ComputerSystemProduct UUID
    if platform.system() == "Windows":
        try:
            out = subprocess.check_output(
                "wmic csproduct get uuid",
                shell=True, text=True, stderr=subprocess.DEVNULL, timeout=2
            )
            lines = [l.strip() for l in out.splitlines() if l.strip() and "UUID" not in l.upper()]
            if lines and lines[0]:
                _CACHED_STATION_ID = lines[0]
                return _CACHED_STATION_ID
        except Exception:
            pass

        try:
            out = subprocess.check_output(
                'powershell -Command "(Get-CimInstance Win32_ComputerSystemProduct).UUID"',
                shell=True, text=True, stderr=subprocess.DEVNULL, timeout=2
            )
            val = out.strip()
            if val:
                _CACHED_STATION_ID = val
                return _CACHED_STATION_ID
        except Exception:
            pass

    # 4. Fallback: Hardware MAC Address Node
    try:
        node = uuid.getnode()
        _CACHED_STATION_ID = f"STATION-{node:012x}"
        return _CACHED_STATION_ID
    except Exception:
        _CACHED_STATION_ID = "STATION-UNKNOWN"
        return _CACHED_STATION_ID


def get_forensic_performed_by():
    """Returns formatted forensic attribution string, e.g. 'analyst@29fe77cb-b792-7a6a-94f7-95f9956c6aea'."""
    user = get_examiner_username()
    station = get_hardware_station_id()
    return f"{user}@{station}"
