"""
SQLite database operations for planner-auto.

Provides persistence for planning sessions, messages, context entries,
plan drafts, reviews, blockers, and session config.

All CRUD/query functions accept conn: sqlite3.Connection as their first parameter.

Schema versions:
    1 — Plan 1 schema (original)
    2 — Plan 2 schema: reviews table rebuilt with round_number + reviewer
        metadata columns; review_dispositions table added
"""

import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Default database directory
DEFAULT_DB_DIR = os.path.join(os.path.expanduser("~"), ".planner-auto")
DEFAULT_DB_PATH = os.path.join(DEFAULT_DB_DIR, "planner-auto.db")

# Current schema version
CURRENT_SCHEMA_VERSION = 2


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
    """Create all tables if they don't already exist, then run migrations.

    Creates the v1 schema via CREATE TABLE IF NOT EXISTS, initialises
    schema_version to 1 if empty, then migrates up to CURRENT_SCHEMA_VERSION.

    Args:
        conn: An open SQLite connection (PRAGMAs should already be applied).
    """
    # Create base (v1) tables and schema_version tracker.
    # reviews is created with the v1 schema here; the migration will rebuild it.
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

        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        );
    """)
    # executescript() commits; we're now in a clean state.

    # Initialise version to 1 if the table is empty (fresh install or first
    # run after adding schema_version tracking to an existing v1 database).
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.commit()

    # Run migrations up to the current version.
    current = get_schema_version(conn)
    if current < 2:
        _migrate_v1_to_v2(conn)


# ---------------------------------------------------------------------------
# Schema versioning helpers
# ---------------------------------------------------------------------------

def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version stored in the DB.

    Returns:
        Integer version number (1 for v1 schema, 2 for v2, etc.).
    """
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is None:
        return 1
    version = int(row[0])
    logger.debug("Schema version: %d", version)
    return version


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Overwrite the schema version record.

    Args:
        conn: SQLite connection.
        version: New version number to store.
    """
    count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    if count == 0:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    else:
        conn.execute("UPDATE schema_version SET version = ?", (version,))


# ---------------------------------------------------------------------------
# Internal migration helpers
# ---------------------------------------------------------------------------

def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate the database from schema v1 to v2.

    Changes:
    - Rebuilds the ``reviews`` table with Plan-2 columns (round_number,
      issues_json, summary, raw_response, reviewer_model, cost,
      input_tokens, output_tokens) and makes draft_id nullable.
    - Adds ``UNIQUE(session_id, round_number)``; SQLite permits multiple
      NULL values in a unique index so legacy rows (round_number=NULL)
      do not conflict.
    - Creates the new ``review_dispositions`` table.
    - Preserves all existing review rows (round_number set to NULL).

    Foreign key enforcement is disabled for the duration of the rebuild
    (required by SQLite when dropping/recreating tables with FK refs).
    """
    logger.warning("Migrating schema v1 → v2")

    # Must be outside an open transaction to toggle foreign_keys.
    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        # 1. Create reviews with the full v2 schema.
        conn.execute("""
            CREATE TABLE reviews_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                draft_id INTEGER REFERENCES plan_drafts(id),
                round_number INTEGER,
                verdict TEXT,
                content TEXT,
                issues_json TEXT,
                summary TEXT,
                raw_response TEXT,
                reviewer_model TEXT,
                cost REAL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, round_number)
            )
        """)

        # 2. Copy existing rows; new columns default to NULL.
        conn.execute("""
            INSERT INTO reviews_new
                (id, session_id, draft_id, round_number, verdict, content, created_at)
            SELECT id, session_id, draft_id, NULL, verdict, content, created_at
            FROM reviews
        """)

        # 3. Swap tables.
        conn.execute("DROP TABLE reviews")
        conn.execute("ALTER TABLE reviews_new RENAME TO reviews")

        # 4. Create review_dispositions table (new in v2).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS review_dispositions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id INTEGER REFERENCES reviews(id),
                issue_index INTEGER NOT NULL,
                disposition TEXT NOT NULL
                    CHECK(disposition IN ('ACCEPT', 'DEFER', 'REJECT')),
                rationale TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 5. Update schema version.
        set_schema_version(conn, 2)
        conn.commit()
        logger.info("Schema migration v1 → v2 complete")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


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
    """Add a review for a plan draft (Plan 1 compatibility signature).

    Writes to the v2 ``reviews`` table with ``round_number=NULL`` and all
    Plan-2 columns set to NULL.  This keeps existing callers unchanged.

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


def add_review_v2(
    conn: sqlite3.Connection,
    session_id: str,
    round_number: int,
    verdict: Optional[str],
    issues_json: Optional[str],
    summary: Optional[str],
    raw_response: Optional[str],
    reviewer_model: Optional[str],
    cost: Optional[float],
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    draft_id: Optional[int] = None,
) -> int:
    """Add a Plan-2 review record.

    ``round_number`` is required (enforced in Python) and must be unique
    per session.

    Args:
        conn: SQLite connection.
        session_id: Session ID.
        round_number: 1-based review round number (must be unique per session).
        verdict: Reviewer verdict string (e.g. 'GO', 'NO_GO').
        issues_json: JSON-serialised list of review issues.
        summary: Human-readable review summary.
        raw_response: Raw reviewer response text.
        reviewer_model: Model identifier used for review.
        cost: API cost in USD.
        input_tokens: Input token count.
        output_tokens: Output token count.
        draft_id: Optional FK to plan_drafts.id.

    Returns:
        The inserted row ID.

    Raises:
        ValueError: If round_number is None.
    """
    if round_number is None:
        raise ValueError("round_number is required for add_review_v2")

    cursor = conn.execute(
        """INSERT INTO reviews
            (session_id, draft_id, round_number, verdict, issues_json, summary,
             raw_response, reviewer_model, cost, input_tokens, output_tokens)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            draft_id,
            round_number,
            verdict,
            issues_json,
            summary,
            raw_response,
            reviewer_model,
            cost,
            input_tokens,
            output_tokens,
        ),
    )
    return cursor.lastrowid


def add_disposition(
    conn: sqlite3.Connection,
    review_id: int,
    issue_index: int,
    disposition: str,
    rationale: Optional[str] = None,
) -> int:
    """Add a disposition record for a single review issue.

    Args:
        conn: SQLite connection.
        review_id: FK to reviews.id.
        issue_index: 0-based index of the issue within the review.
        disposition: One of 'ACCEPT', 'DEFER', 'REJECT'.
        rationale: Optional explanation for the disposition.

    Returns:
        The inserted row ID.
    """
    cursor = conn.execute(
        """INSERT INTO review_dispositions
            (review_id, issue_index, disposition, rationale)
           VALUES (?, ?, ?, ?)""",
        (review_id, issue_index, disposition, rationale),
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


def get_review_by_round(
    conn: sqlite3.Connection, session_id: str, round_number: int
) -> Optional[sqlite3.Row]:
    """Get the review row for a specific round number.

    Args:
        conn: SQLite connection.
        session_id: Session ID.
        round_number: Round number to look up.

    Returns:
        The review row or None if not found.
    """
    return conn.execute(
        "SELECT * FROM reviews WHERE session_id = ? AND round_number = ?",
        (session_id, round_number),
    ).fetchone()


def get_dispositions(conn: sqlite3.Connection, review_id: int) -> list[dict]:
    """Get all disposition records for a single review.

    Args:
        conn: SQLite connection.
        review_id: The reviews.id to query.

    Returns:
        List of dicts with keys: id, review_id, issue_index, disposition,
        rationale, created_at.
    """
    rows = conn.execute(
        "SELECT * FROM review_dispositions WHERE review_id = ? ORDER BY issue_index ASC",
        (review_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_all_dispositions(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """Get all disposition records across all reviews for a session.

    Args:
        conn: SQLite connection.
        session_id: Session ID.

    Returns:
        List of dicts ordered by review round_number, then issue_index.
        Each dict includes all review_dispositions columns plus
        ``round_number`` from the parent review.
    """
    rows = conn.execute(
        """SELECT rd.*, r.round_number
           FROM review_dispositions rd
           JOIN reviews r ON rd.review_id = r.id
           WHERE r.session_id = ?
           ORDER BY r.round_number ASC, rd.issue_index ASC""",
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]
