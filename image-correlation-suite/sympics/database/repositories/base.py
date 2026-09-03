# Copyright 2026 Google LLC
# Licensed under Apache 2.0

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
