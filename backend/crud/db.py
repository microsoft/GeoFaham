# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import os
import logging
from contextlib import contextmanager
from psycopg2 import pool

logger = logging.getLogger(__name__)

DB_POOL: pool.SimpleConnectionPool | None = None

# Database configuration from environment variables with defaults
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'qe_exp2')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'password')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
def init_db_pool():
    global DB_POOL
    if DB_POOL is None:
        DB_POOL = pool.SimpleConnectionPool(
            1, 10,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB
        )

@contextmanager
def get_conn_cursor():
    if DB_POOL is None:
        init_db_pool()
    conn = DB_POOL.getconn()
    cur = conn.cursor()
    try:
        yield conn, cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        DB_POOL.putconn(conn)


if __name__ == "__main__":
    with get_conn_cursor() as (conn, cur):
        cur.execute('SELECT 1')
        print(cur.fetchone()) 
        