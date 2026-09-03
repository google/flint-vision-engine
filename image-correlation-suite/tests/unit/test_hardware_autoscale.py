# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
Unit tests for hardware auto-discovery and worker count calculation.
"""
from database.hardware_acceleration import probe_hardware, HardwareProfile


def test_probe_hardware_profile():
    prof = probe_hardware()
    assert isinstance(prof, HardwareProfile)
    assert prof.device in ("cuda", "mps", "cpu")
    assert prof.cpu_cores >= 1
    assert prof.ram_gb > 0
    assert prof.recommended_workers >= 1
    assert prof.recommended_batch_size in (16, 32, 64)
    assert prof.recommended_dtype in ("float16", "bfloat16", "float32")
