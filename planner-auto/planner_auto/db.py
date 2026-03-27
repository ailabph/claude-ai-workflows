"""
SQLite database operations for planner-auto.

Provides persistence for planning sessions, messages, context entries,
plan drafts, reviews, blockers, and session config.

All CRUD/query functions accept conn: sqlite3.Connection as their first parameter.
"""

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Optional


# Default database directory
DEFAULT_DB_DIR = os.path.join(os.path.expanduser("~"), ".planner-auto")
DEFAULT_DB_PATH = os.path.join(DEFAULT_DB_DIR, "planner-auto.db")


def open_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and foreign keys enabled.

    Creates ~/.planner-auto/ if it doesn't exist. Applies PRAGMAs
    on every opened connection.

    Args:
        db_path: Optional path to database file. Defaults to
                 ~/.planner-auto/planner-auto.db

    Returns:
        sqlite3.Connection with row_factory set to sqlite3.Row
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all 7 tables if they don't already exist.

    Args:
        conn: An open SQLite connection (PRAGMAs should already be applied).
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            project TEXT NOT NULL,
            phase TEXT NOT NULL DEFAULT 'SETUP',
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session_id
            ON messages(session_id, id);

        CREATE TABLE IF NOT EXISTS context_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            entry_key TEXT NOT NULL,
            entry_type TEXT NOT NULL CHECK(entry_type IN ('file', 'note', 'synthesis')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, entry_key, entry_type)
        );

        CREATE TABLE IF NOT EXISTS session_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS plan_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            draft_number INTEGER NOT NULL,
            content TEXT NOT NULL,
            model TEXT NOT NULL,
            config_snapshot_id INTEGER REFERENCES session_config(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, draft_number)
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            draft_id INTEGER NOT NULL REFERENCES plan_drafts(id),
            verdict TEXT,
            content TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS blockers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            source TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT,
            status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'resolved')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT
        );
    """)
    conn.commit()


@contextmanager
def transaction(conn: sqlite3.Connection):
    """Context manager for atomic multi-operation transactions.

    Usage::

        with transaction(conn):
            add_message(conn, sid, "user", text)
            add_message(conn, sid, "assistant", reply)
        # both rows committed together, or both rolled back on error

    Since CRUD functions no longer auto-commit, callers that perform a
    single operation can simply call ``conn.commit()`` afterwards.  Use
    this wrapper when two or more operations must succeed or fail as a unit.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ---------------------------------------------------------------------------
# CRUD functions
# ---------------------------------------------------------------------------

def create_session(conn: sqlite3.Connection, project: str) -> str:
    """Create a new session and return its ID.

    Args:
        conn: SQLite connection.
        project: Project name.

    Returns:
        The generated session ID (UUID hex string).
    """
    session_id = uuid.uuid4().hex[:8]
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO sessions (id, project, phase, status, created_at, updated_at) "
        "VALUES (?, ?, 'SETUP', 'ACTIVE', ?, ?)",
        (session_id, project, now, now),
    )
    return session_id


def update_session_phase(conn: sqlite3.Connection, session_id: str, phase: str) -> None:
    """Update the phase of a session.

    Args:
        conn: SQLite connection.
        session_id: Session ID.
        phase: New phase value.
    """
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE sessions SET phase = ?, updated_at = ? WHERE id = ?",
        (phase, now, session_id),
    )


def update_session_status(conn: sqlite3.Connection, session_id: str, status: str) -> None:
    """Update the status of a session.

    Args:
        conn: SQLite connection.
        session_id: Session ID.
        status: New status value.
    """
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, session_id),
    )


def add_message(conn: sqlite3.Connection, session_id: str, role: str, content: str) -> int:
    """Add a message to a session.

    Args:
        conn: SQLite connection.
        session_id: Session ID.
        role: 'user' or 'assistant'.
        content: Message content.

    Returns:
        The inserted message row ID.
    """
    cursor = conn.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content),
    )
    return cursor.lastrowid


def add_context_entry(
    conn: sqlite3.Connection,
    session_id: str,
    key: str,
    entry_type: str,
    content: str,
) -> int:
    """Add or update a context entry (UPSERT on unique constraint).

    Args:
        conn: SQLite connection.
        session_id: Session ID.
        key: Entry key (e.g. filename or timestamp).
        entry_type: One of 'file', 'note', 'synthesis'.
        content: Entry content.

    Returns:
        The inserted/updated row ID.
    """
    cursor = conn.execute(
        "INSERT INTO context_entries (session_id, entry_key, entry_type, content) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(session_id, entry_key, entry_type) "
        "DO UPDATE SET content = excluded.content, created_at = CURRENT_TIMESTAMP",
        (session_id, key, entry_type, content),
    )
    return cursor.lastrowid


def add_plan_draft(
    conn: sqlite3.Connection,
    session_id: str,
    content: str,
    model: str,
    config_snapshot_id: Optional[int] = None,
) -> int:
    """Add a plan draft with auto-incremented draft_number per session.

    Args:
        conn: SQLite connection.
        session_id: Session ID.
        content: Plan draft content.
        model: Model used for generation.
        config_snapshot_id: Optional reference to session_config row.

    Returns:
        The inserted row ID.
    """
    row = conn.execute(
        "SELECT COALESCE(MAX(draft_number), 0) + 1 AS next_num "
        "FROM plan_drafts WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    next_num = row["next_num"]

    cursor = conn.execute(
        "INSERT INTO plan_drafts (session_id, draft_number, content, model, config_snapshot_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, next_num, content, model, config_snapshot_id),
    )
    return cursor.lastrowid


def add_review(
    conn: sqlite3.Connection,
    session_id: str,
    draft_id: int,
    verdict: Optional[str],
    content: Optional[str],
) -> int:
    """Add a review for a plan draft.

    Args:
        conn: SQLite connection.
        session_id: Session ID.
        draft_id: The plan_drafts row ID being reviewed.
        verdict: Review verdict (e.g. 'approve', 'reject').
        content: Review content/comments.

    Returns:
        The inserted row ID.
    """
    cursor = conn.execute(
        "INSERT INTO reviews (session_id, draft_id, verdict, content) VALUES (?, ?, ?, ?)",
        (session_id, draft_id, verdict, content),
    )
    return cursor.lastrowid


def create_blocker(
    conn: sqlite3.Connection,
    session_id: str,
    source: str,
    question: str,
) -> int:
    """Create a new open blocker.

    Args:
        conn: SQLite connection.
        session_id: Session ID.
        source: Source of the blocker (e.g. 'planner', 'executor').
        question: The blocking question.

    Returns:
        The inserted row ID.
    """
    cursor = conn.execute(
        "INSERT INTO blockers (session_id, source, question) VALUES (?, ?, ?)",
        (session_id, source, question),
    )
    return cursor.lastrowid


def resolve_blocker(conn: sqlite3.Connection, blocker_id: int, answer: str) -> None:
    """Resolve an open blocker by providing an answer.

    Args:
        conn: SQLite connection.
        blocker_id: The blocker row ID.
        answer: The answer resolving the blocker.
    """
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE blockers SET answer = ?, status = 'resolved', resolved_at = ? WHERE id = ?",
        (answer, now, blocker_id),
    )


def save_session_config(
    conn: sqlite3.Connection,
    session_id: str,
    config_json: str,
) -> int:
    """Save a session config snapshot.

    Args:
        conn: SQLite connection.
        session_id: Session ID.
        config_json: JSON string of the config.

    Returns:
        The inserted row ID.
    """
    cursor = conn.execute(
        "INSERT INTO session_config (session_id, config_json) VALUES (?, ?)",
        (session_id, config_json),
    )
    return cursor.lastrowid


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_session(conn: sqlite3.Connection, session_id: str) -> Optional[sqlite3.Row]:
    """Get a session by ID.

    Returns:
        The session row or None if not found.
    """
    return conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()


def get_messages(conn: sqlite3.Connection, session_id: str) -> list:
    """Get all messages for a session, ordered by insertion order (id ASC).

    Returns:
        List of message rows.
    """
    return conn.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()


def get_context_entries(
    conn: sqlite3.Connection,
    session_id: str,
    entry_type: Optional[str] = None,
) -> list:
    """Get context entries for a session, optionally filtered by type.

    Args:
        conn: SQLite connection.
        session_id: Session ID.
        entry_type: Optional filter ('file', 'note', 'synthesis').

    Returns:
        List of context entry rows.
    """
    if entry_type is not None:
        return conn.execute(
            "SELECT * FROM context_entries WHERE session_id = ? AND entry_type = ?",
            (session_id, entry_type),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM context_entries WHERE session_id = ?",
        (session_id,),
    ).fetchall()


def get_latest_plan_draft(conn: sqlite3.Connection, session_id: str) -> Optional[sqlite3.Row]:
    """Get the latest plan draft for a session.

    Returns:
        The latest plan draft row or None.
    """
    return conn.execute(
        "SELECT * FROM plan_drafts WHERE session_id = ? ORDER BY draft_number DESC LIMIT 1",
        (session_id,),
    ).fetchone()


def get_all_plan_drafts(conn: sqlite3.Connection, session_id: str) -> list:
    """Get all plan drafts for a session, ordered by draft number.

    Returns:
        List of plan draft rows.
    """
    return conn.execute(
        "SELECT * FROM plan_drafts WHERE session_id = ? ORDER BY draft_number ASC",
        (session_id,),
    ).fetchall()


def get_open_blockers(conn: sqlite3.Connection, session_id: str) -> list:
    """Get all open (unresolved) blockers for a session.

    Returns:
        List of open blocker rows.
    """
    return conn.execute(
        "SELECT * FROM blockers WHERE session_id = ? AND status = 'open'",
        (session_id,),
    ).fetchall()


def get_session_config(conn: sqlite3.Connection, session_id: str) -> Optional[sqlite3.Row]:
    """Get the latest session config for a session.

    Returns:
        The latest session_config row or None.
    """
    return conn.execute(
        "SELECT * FROM session_config WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
