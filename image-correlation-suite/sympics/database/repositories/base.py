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
Base Repository Interface
"""
from abc import ABC
from typing import Optional
from sympics.database.connection import connection_manager


class BaseRepository(ABC):
    """Abstract base repository providing connection lifecycle management."""

    def __init__(self, conn_mgr=None):
        self.conn_mgr = conn_mgr or connection_manager

    def get_connection(self, conn=None):
        if conn is not None:
            return conn, False
        return self.conn_mgr.get_connection(), True
