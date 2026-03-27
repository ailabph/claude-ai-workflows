"""Tests for the add-context CLI subcommand."""

import json
import os
import sqlite3

import pytest
from click.testing import CliRunner

from planner_auto.cli import cli
from planner_auto.db import (
    get_context_entries,
    get_session,
    init_schema,
    update_session_phase,
)


@pytest.fixture
def runner(tmp_path):
    """Provide a CliRunner with a temp database and work directory."""
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    return runner, ["--db-path", db_path], db_path, tmp_path


def _get_conn(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _create_session(runner_obj, base_args):
    """Helper to create a session and return its ID."""
    r, _, _, _ = runner_obj
    result = r.invoke(cli, [*base_args, "start", "--project", "myapp"])
    return result.output.split("Session created: ")[1].split("\n")[0].strip()


class TestAddContextFile:
    """Tests for add-context --file."""

    def test_stores_utf8_file(self, runner):
        r, base_args, db_path, tmp_path = runner
        sid = _create_session((r, base_args, db_path, tmp_path), base_args)

        # Create a test file
        test_file = tmp_path / "readme.txt"
        test_file.write_text("Hello world!", encoding="utf-8")

        result = r.invoke(cli, [*base_args, "add-context", sid, "--file", str(test_file)])
        assert result.exit_code == 0
        assert "Context added" in result.output

        conn = _get_conn(db_path)
        init_schema(conn)
        entries = get_context_entries(conn, sid, entry_type="file")
        assert len(entries) == 1
        assert entries[0]["entry_key"] == "readme.txt"
        assert entries[0]["content"] == "Hello world!"
        conn.close()

    def test_rejects_file_over_500kb(self, runner):
        r, base_args, db_path, tmp_path = runner
        sid = _create_session((r, base_args, db_path, tmp_path), base_args)

        # Create a file > 500KB
        big_file = tmp_path / "big.txt"
        big_file.write_text("x" * (500 * 1024 + 1), encoding="utf-8")

        result = r.invoke(cli, [*base_args, "add-context", sid, "--file", str(big_file)])
        assert "too large" in result.output.lower() or "Error" in result.output

    def test_rejects_binary_file(self, runner):
        r, base_args, db_path, tmp_path = runner
        sid = _create_session((r, base_args, db_path, tmp_path), base_args)

        # Create a binary file
        bin_file = tmp_path / "binary.dat"
        bin_file.write_bytes(b"\x00\x01\x02\xff\xfe\x80\x81")

        result = r.invoke(cli, [*base_args, "add-context", sid, "--file", str(bin_file)])
        assert "not valid UTF-8" in result.output or "binary" in result.output.lower()

    def test_rejects_nonexistent_file(self, runner):
        r, base_args, db_path, tmp_path = runner
        sid = _create_session((r, base_args, db_path, tmp_path), base_args)

        result = r.invoke(cli, [*base_args, "add-context", sid, "--file", "/nonexistent/file.txt"])
        assert "not found" in result.output.lower() or "Error" in result.output

    def test_upsert_replaces_content(self, runner):
        r, base_args, db_path, tmp_path = runner
        sid = _create_session((r, base_args, db_path, tmp_path), base_args)

        test_file = tmp_path / "readme.txt"
        test_file.write_text("v1", encoding="utf-8")
        r.invoke(cli, [*base_args, "add-context", sid, "--file", str(test_file)])

        test_file.write_text("v2", encoding="utf-8")
        r.invoke(cli, [*base_args, "add-context", sid, "--file", str(test_file)])

        conn = _get_conn(db_path)
        init_schema(conn)
        entries = get_context_entries(conn, sid, entry_type="file")
        assert len(entries) == 1
        assert entries[0]["content"] == "v2"
        conn.close()


class TestAddContextNote:
    """Tests for add-context --note."""

    def test_stores_note_with_auto_key(self, runner):
        r, base_args, db_path, tmp_path = runner
        sid = _create_session((r, base_args, db_path, tmp_path), base_args)

        result = r.invoke(cli, [*base_args, "add-context", sid, "--note", "Use PostgreSQL"])
        assert result.exit_code == 0
        assert "Context added" in result.output

        conn = _get_conn(db_path)
        init_schema(conn)
        entries = get_context_entries(conn, sid, entry_type="note")
        assert len(entries) == 1
        assert entries[0]["entry_key"].startswith("note-")
        assert entries[0]["content"] == "Use PostgreSQL"
        conn.close()

    def test_requires_file_or_note(self, runner):
        r, base_args, db_path, tmp_path = runner
        sid = _create_session((r, base_args, db_path, tmp_path), base_args)

        result = r.invoke(cli, [*base_args, "add-context", sid])
        assert "Provide either" in result.output or "Error" in result.output


class TestAddContextPhaseTransition:
    """Tests for phase advancement on add-context."""

    def test_advances_from_setup_to_context(self, runner):
        r, base_args, db_path, tmp_path = runner
        sid = _create_session((r, base_args, db_path, tmp_path), base_args)

        test_file = tmp_path / "readme.txt"
        test_file.write_text("content", encoding="utf-8")
        result = r.invoke(cli, [*base_args, "add-context", sid, "--file", str(test_file)])
        assert "Phase advanced to CONTEXT" in result.output

        conn = _get_conn(db_path)
        init_schema(conn)
        session = get_session(conn, sid)
        assert session["phase"] == "CONTEXT"
        conn.close()

    def test_blocked_in_discussion_phase(self, runner):
        r, base_args, db_path, tmp_path = runner
        sid = _create_session((r, base_args, db_path, tmp_path), base_args)

        # Move to DISCUSSION
        conn = _get_conn(db_path)
        init_schema(conn)
        update_session_phase(conn, sid, "CONTEXT")
        update_session_phase(conn, sid, "DISCUSSION")
        conn.close()

        test_file = tmp_path / "readme.txt"
        test_file.write_text("content", encoding="utf-8")
        result = r.invoke(cli, [*base_args, "add-context", sid, "--file", str(test_file)])
        assert "Error" in result.output or "not allowed" in result.output.lower()
