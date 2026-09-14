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
SYMPICS Multi-Stream Cryptographic Hashing Engine
==============================================
Calculates SHA-256, MD5, and SHA-1 simultaneously in 64KB streamed chunks.
"""

import hashlib
from typing import Tuple, BinaryIO


def compute_stream_hashes(stream: BinaryIO, chunk_size: int = 65536) -> Tuple[str, str, str, int]:
    """
    Computes (sha256, md5, sha1, byte_count) from a readable binary stream.
    """
    s256 = hashlib.sha256()
    s_md5 = hashlib.md5()
    s_sha1 = hashlib.sha1()
    total_bytes = 0

    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        s256.update(chunk)
        s_md5.update(chunk)
        s_sha1.update(chunk)
        total_bytes += len(chunk)

    return s256.hexdigest(), s_md5.hexdigest(), s_sha1.hexdigest(), total_bytes


def compute_file_hashes(filepath: str, chunk_size: int = 65536) -> Tuple[str, str, str, int]:
    """
    Computes (sha256, md5, sha1, byte_count) for a local filesystem file.
    """
    with open(filepath, "rb") as f:
        return compute_stream_hashes(f, chunk_size=chunk_size)
