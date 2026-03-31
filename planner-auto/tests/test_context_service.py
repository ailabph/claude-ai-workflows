"""Tests for context_service.add_context_entry() library function."""

import sqlite3

import pytest

from planner_auto.context_service import ContextError, add_context_entry
from planner_auto.db import create_session, get_context_entries, get_session, init_schema
from planner_auto.session import SessionManager
from planner_auto.state import Phase


@pytest.fixture
def db_conn():
    """In-memory SQLite connection with schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def session_id(db_conn):
    """Create a session and return its ID."""
    sid = create_session(db_conn, "test-project")
    db_conn.commit()
    return sid


class TestAddFileContext:
    """Tests for add_context_entry with entry_type='file'."""

    def test_valid_file(self, db_conn, session_id, tmp_path):
        test_file = tmp_path / "readme.txt"
        test_file.write_text("Hello world!", encoding="utf-8")

        result = add_context_entry(db_conn, session_id, "file", str(test_file))

        assert result["entry_type"] == "file"
        assert result["key"] == str(test_file.resolve())
        assert result["size"] == len("Hello world!")

        # Verify in DB
        entries = get_context_entries(db_conn, session_id, entry_type="file")
        assert len(entries) == 1
        assert entries[0]["content"] == "Hello world!"

    def test_missing_file(self, db_conn, session_id, tmp_path):
        with pytest.raises(ContextError, match="File not found"):
            add_context_entry(db_conn, session_id, "file", str(tmp_path / "nonexistent.txt"))

    def test_file_too_large(self, db_conn, session_id, tmp_path):
        large_file = tmp_path / "large.txt"
        large_file.write_text("x" * (500 * 1024 + 1), encoding="utf-8")

        with pytest.raises(ContextError, match="File too large"):
            add_context_entry(db_conn, session_id, "file", str(large_file))

    def test_non_utf8_file(self, db_conn, session_id, tmp_path):
        binary_file = tmp_path / "binary.bin"
        binary_file.write_bytes(b"\x80\x81\x82\x83\xff\xfe")

        with pytest.raises(ContextError, match="not valid UTF-8"):
            add_context_entry(db_conn, session_id, "file", str(binary_file))


class TestAddNoteContext:
    """Tests for add_context_entry with entry_type='note'."""

    def test_valid_note(self, db_conn, session_id):
        result = add_context_entry(db_conn, session_id, "note", "This is a test note")

        assert result["entry_type"] == "note"
        assert result["key"].startswith("note-")
        assert result["size"] == len("This is a test note")

        # Verify in DB
        entries = get_context_entries(db_conn, session_id, entry_type="note")
        assert len(entries) == 1
        assert entries[0]["content"] == "This is a test note"


class TestInvalidEntryType:
    """Tests for invalid entry_type."""

    def test_invalid_type(self, db_conn, session_id):
        with pytest.raises(ValueError, match="Invalid entry_type"):
            add_context_entry(db_conn, session_id, "invalid", "content")


class TestPhaseAdvancement:
    """Tests for SETUP → CONTEXT phase advancement."""

    def test_advances_from_setup_to_context(self, db_conn, session_id, tmp_path):
        # Session starts in SETUP
        session = get_session(db_conn, session_id)
        assert session["phase"] == Phase.SETUP.value

        test_file = tmp_path / "file.txt"
        test_file.write_text("content", encoding="utf-8")

        add_context_entry(db_conn, session_id, "file", str(test_file))

        # Should now be in CONTEXT
        session = get_session(db_conn, session_id)
        assert session["phase"] == Phase.CONTEXT.value

    def test_no_double_advance(self, db_conn, session_id, tmp_path):
        """Adding context when already in CONTEXT phase shouldn't fail."""
        # Advance to CONTEXT first
        sm = SessionManager(db_conn)
        sm.advance_phase(session_id, Phase.CONTEXT.value)

        test_file = tmp_path / "file.txt"
        test_file.write_text("content", encoding="utf-8")

        # Should not raise
        result = add_context_entry(db_conn, session_id, "file", str(test_file))
        assert result["entry_type"] == "file"

        session = get_session(db_conn, session_id)
        assert session["phase"] == Phase.CONTEXT.value

    def test_uses_provided_session_manager(self, db_conn, session_id, tmp_path):
        """The sm parameter is used instead of creating a new one."""
        sm = SessionManager(db_conn)

        test_file = tmp_path / "file.txt"
        test_file.write_text("content", encoding="utf-8")

        result = add_context_entry(db_conn, session_id, "file", str(test_file), sm=sm)
        assert result["entry_type"] == "file"

        session = get_session(db_conn, session_id)
        assert session["phase"] == Phase.CONTEXT.value
