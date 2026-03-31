"""Context service: reusable context-write logic for TUI and CLI.

Extracts the file/note validation and storage logic from cli.py into
a library function that returns data instead of calling click.echo().
"""

import logging
import os
import sqlite3
from datetime import datetime
from typing import Optional

from planner_auto.db import add_context_entry as db_add_context_entry, get_session
from planner_auto.session import SessionManager
from planner_auto.state import Phase

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 500 * 1024  # 500 KB


class ContextError(Exception):
    """Raised when a context entry cannot be added."""


def add_context_entry(
    conn: sqlite3.Connection,
    session_id: str,
    entry_type: str,
    path_or_content: str,
    *,
    sm: Optional[SessionManager] = None,
) -> dict:
    """Add a context entry (file or note) to a session.

    This is a reusable library function — no click.echo() calls.
    The caller decides how to present the result.

    Args:
        conn: SQLite connection.
        session_id: Session ID.
        entry_type: One of 'file' or 'note'.
        path_or_content: For 'file': path to the file. For 'note': note content.
        sm: Optional SessionManager for phase advancement. If None, a new one
            is created from conn.

    Returns:
        Dict with keys: entry_type, key, size.

    Raises:
        ContextError: If validation fails (missing file, too large, non-UTF-8).
        ValueError: If entry_type is invalid.
    """
    if entry_type not in ("file", "note"):
        raise ValueError(f"Invalid entry_type: {entry_type!r}. Must be 'file' or 'note'.")

    if entry_type == "file":
        result = _add_file(conn, session_id, path_or_content)
    else:
        result = _add_note(conn, session_id, path_or_content)

    # Advance phase SETUP → CONTEXT if needed
    session = get_session(conn, session_id)
    if session and session["phase"] == Phase.SETUP.value:
        if sm is None:
            sm = SessionManager(conn)
        sm.advance_phase(session_id, Phase.CONTEXT.value)

    conn.commit()

    logger.info(
        "Context entry added: type=%s, key=%s, size=%d (session=%s)",
        result["entry_type"], result["key"], result["size"], session_id,
    )
    return result


def _add_file(conn: sqlite3.Connection, session_id: str, file_path: str) -> dict:
    """Validate and store a file as context."""
    abs_path = os.path.abspath(file_path)

    if not os.path.exists(abs_path):
        raise ContextError(f"File not found: {file_path}")

    file_size = os.path.getsize(abs_path)
    if file_size > MAX_FILE_SIZE:
        raise ContextError(
            f"File too large ({file_size} bytes). Maximum is {MAX_FILE_SIZE} bytes (500KB)."
        )

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        raise ContextError("File is not valid UTF-8 (binary files are not supported).")

    key = abs_path
    db_add_context_entry(conn, session_id, key, "file", content)

    return {"entry_type": "file", "key": key, "size": len(content)}


def _add_note(conn: sqlite3.Connection, session_id: str, content: str) -> dict:
    """Store a note as context with auto-generated key."""
    key = f"note-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    db_add_context_entry(conn, session_id, key, "note", content)

    return {"entry_type": "note", "key": key, "size": len(content)}
