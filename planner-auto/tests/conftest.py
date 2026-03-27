"""Shared test fixtures for planner-auto."""

import sqlite3

import pytest

from planner_auto.db import init_schema


@pytest.fixture
def db_conn():
    """Provide an in-memory SQLite connection with schema initialized.

    PRAGMAs are applied (WAL not supported on :memory:, but foreign_keys is).
    The connection is closed after the test.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # WAL not meaningful for :memory: but we still set foreign keys
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    yield conn
    conn.close()
