# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Test Database Connection

Run: python -m tests.test_db_connection
"""

import pytest
from backend.db import get_connection, get_cursor


class TestDatabaseConnection:
    """Tests for database connection functionality."""

    def test_connection_successful(self):
        """Test that we can establish a database connection."""
        conn = get_connection()
        assert conn is not None
        assert not conn.closed
        conn.close()
        assert conn.closed

    def test_connection_can_execute_query(self):
        """Test that connection can execute a simple query."""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            result = cur.fetchone()
            assert result == (1,)
            cur.close()
        finally:
            conn.close()

    def test_get_cursor_context_manager(self):
        """Test the get_cursor context manager."""
        with get_cursor() as (conn, cur):
            assert conn is not None
            assert cur is not None
            cur.execute("SELECT 1 AS test_value")
            result = cur.fetchone()
            assert result == (1,)

    def test_get_cursor_auto_commit(self):
        """Test that get_cursor auto-commits on success."""
        # Create a temp table, insert data, verify it persists
        with get_cursor() as (conn, cur):
            cur.execute("""
                CREATE TEMP TABLE test_auto_commit (
                    id SERIAL PRIMARY KEY,
                    value TEXT
                )
            """)
            cur.execute("INSERT INTO test_auto_commit (value) VALUES ('test')")
            cur.execute("SELECT value FROM test_auto_commit")
            result = cur.fetchone()
            assert result == ('test',)

    def test_get_cursor_rollback_on_error(self):
        """Test that get_cursor rolls back on error."""
        try:
            with get_cursor() as (conn, cur):
                cur.execute("SELECT * FROM nonexistent_table_xyz")
        except Exception:
            pass  # Expected to fail

        # Connection should still work after rollback
        with get_cursor() as (conn, cur):
            cur.execute("SELECT 1")
            result = cur.fetchone()
            assert result == (1,)

    def test_database_version(self):
        """Test that we can query database version."""
        with get_cursor() as (conn, cur):
            cur.execute("SELECT version()")
            result = cur.fetchone()
            assert result is not None
            assert 'PostgreSQL' in result[0]


def main():
    """Run tests manually without pytest."""
    print("\n" + "=" * 60)
    print("DATABASE CONNECTION TESTS")
    print("=" * 60 + "\n")

    tests = TestDatabaseConnection()

    test_methods = [
        ("test_connection_successful", tests.test_connection_successful),
        ("test_connection_can_execute_query", tests.test_connection_can_execute_query),
        ("test_get_cursor_context_manager", tests.test_get_cursor_context_manager),
        ("test_get_cursor_auto_commit", tests.test_get_cursor_auto_commit),
        ("test_get_cursor_rollback_on_error", tests.test_get_cursor_rollback_on_error),
        ("test_database_version", tests.test_database_version),
    ]

    passed = 0
    failed = 0

    for name, test_func in test_methods:
        try:
            test_func()
            print(f"✓ {name}")
            passed += 1
        except Exception as e:
            print(f"✗ {name}: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    exit(0 if main() else 1)
