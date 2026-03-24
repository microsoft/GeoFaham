# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Database utilities module.
"""
from backend.db.connection import get_connection, get_cursor

__all__ = ['get_connection', 'get_cursor']
