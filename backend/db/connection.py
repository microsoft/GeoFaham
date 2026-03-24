# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Database connection utilities - shared by all db scripts.
Uses the same connection pool as crud module when available.
"""
import os
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv(override=True)

# Database configuration from environment variables
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'qe_exp2')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'password')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')


def get_connection():
    """Get a new database connection."""
    import psycopg2
    return psycopg2.connect(
        host=POSTGRES_HOST,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        port=POSTGRES_PORT
    )


@contextmanager
def get_cursor():
    """Context manager for database cursor with auto-commit."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        yield conn, cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
