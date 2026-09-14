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
Unit tests for cryptographic multi-stream hashing engine.
"""
import io
import hashlib
from sympics.core.hashing import compute_stream_hashes, compute_file_hashes


def test_compute_stream_hashes_accuracy():
    payload = b"Hello, SYMPICS Forensic Intelligence Platform!" * 1000
    expected_s256 = hashlib.sha256(payload).hexdigest()
    expected_md5 = hashlib.md5(payload).hexdigest()
    expected_sha1 = hashlib.sha1(payload).hexdigest()

    stream = io.BytesIO(payload)
    s256, md5, sha1, size = compute_stream_hashes(stream, chunk_size=128)

    assert s256 == expected_s256
    assert md5 == expected_md5
    assert sha1 == expected_sha1
    assert size == len(payload)


def test_compute_file_hashes(tmp_path):
    test_file = tmp_path / "test_media.bin"
    payload = b"FORENSIC_EVIDENCE_SAMPLE_BYTES_998877"
    test_file.write_bytes(payload)

    expected_s256 = hashlib.sha256(payload).hexdigest()
    s256, md5, sha1, size = compute_file_hashes(str(test_file))

    assert s256 == expected_s256
    assert size == len(payload)
