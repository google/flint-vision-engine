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
