"""
SQLite database operations for orchestrator-auto.

Provides persistence for workflow sessions, messages, milestones, and blockers.
"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import contextmanager


# Default database path
DEFAULT_DB_DIR = Path.home() / ".claude_orchestrator"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "db.sqlite"


def get_db_path(custom_path: Optional[str] = None) -> Path:
    """Get the database path, creating directory if needed."""
    if custom_path:
        db_path = Path(custom_path)
    else:
        db_path = DEFAULT_DB_PATH

    # Create directory if it doesn't exist
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return db_path


@contextmanager
def get_connection(db_path: Optional[str] = None):
    """Get a database connection with automatic cleanup."""
    path = get_db_path(db_path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize database with schema. Safe to call multiple times."""

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                feature_description TEXT NOT NULL,
                phase TEXT NOT NULL DEFAULT 'discovery',
                status TEXT NOT NULL DEFAULT 'active',
                planner_session_id TEXT,
                executor_session_id TEXT,
                plan_path TEXT,
                current_milestone INTEGER DEFAULT 0,
                total_milestones INTEGER DEFAULT 0,
                previous_phase TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add previous_phase column if it doesn't exist (for backwards compatibility)
        try:
            cursor.execute("""
                ALTER TABLE sessions ADD COLUMN previous_phase TEXT
            """)
        except sqlite3.OperationalError:
            # Column already exists
            pass

        # Add model columns if they don't exist (for backwards compatibility)
        try:
            cursor.execute("""
                ALTER TABLE sessions ADD COLUMN planner_model TEXT
            """)
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("""
                ALTER TABLE sessions ADD COLUMN executor_model TEXT
            """)
        except sqlite3.OperationalError:
            pass

        # Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                agent TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                token_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # Milestones table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                number INTEGER NOT NULL,
                name TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                executor_report TEXT,
                planner_feedback TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # Blockers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blockers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                agent TEXT NOT NULL,
                question TEXT NOT NULL,
                response TEXT,
                resolved_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_milestones_session
            ON milestones(session_id)
        """)

        conn.commit()


# ============================================================================
# Session CRUD
# ============================================================================

def create_session(
    feature_description: str,
    planner_model: Optional[str] = None,
    executor_model: Optional[str] = None,
    db_path: Optional[str] = None
) -> str:
    """Create a new workflow session. Returns session ID."""

    session_id = str(uuid.uuid4())[:8]  # Short ID for CLI convenience

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sessions (id, feature_description, planner_model, executor_model)
            VALUES (?, ?, ?, ?)
        """, (session_id, feature_description, planner_model, executor_model))

    return session_id


def get_session(
    session_id: str,
    db_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get session by ID. Returns dict or None if not found."""

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM sessions WHERE id = ?
        """, (session_id,))

        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def update_session(
    session_id: str,
    updates: Dict[str, Any],
    db_path: Optional[str] = None
) -> None:
    """Update session fields. Keys: phase, status, planner_session_id, etc."""

    if not updates:
        return

    # Add updated_at timestamp
    updates = {**updates, "updated_at": datetime.now().isoformat()}

    # Build dynamic UPDATE query
    set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
    values = list(updates.values()) + [session_id]

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE sessions
            SET {set_clause}
            WHERE id = ?
        """, values)


def list_sessions(
    db_path: Optional[str] = None,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List all sessions, optionally filtered by status."""

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        if status:
            cursor.execute("""
                SELECT * FROM sessions
                WHERE status = ?
                ORDER BY created_at DESC
            """, (status,))
        else:
            cursor.execute("""
                SELECT * FROM sessions
                ORDER BY created_at DESC
            """)

        return [dict(row) for row in cursor.fetchall()]


# ============================================================================
# Message Logging
# ============================================================================

def log_message(
    session_id: str,
    phase: str,
    agent: str,
    role: str,
    content: str,
    token_count: Optional[int] = None,
    db_path: Optional[str] = None
) -> int:
    """Log an agent message. Returns message ID."""

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages (
                session_id, phase, agent, role, content, token_count
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, phase, agent, role, content, token_count))

        return cursor.lastrowid


def get_messages(
    session_id: str,
    phase: Optional[str] = None,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get messages for a session, optionally filtered by phase."""

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        if phase:
            cursor.execute("""
                SELECT * FROM messages
                WHERE session_id = ? AND phase = ?
                ORDER BY created_at ASC
            """, (session_id, phase))
        else:
            cursor.execute("""
                SELECT * FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC
            """, (session_id,))

        return [dict(row) for row in cursor.fetchall()]


# ============================================================================
# Milestone Tracking
# ============================================================================

def create_milestone(
    session_id: str,
    number: int,
    name: Optional[str] = None,
    db_path: Optional[str] = None
) -> int:
    """Create a new milestone. Returns milestone ID."""

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO milestones (session_id, number, name)
            VALUES (?, ?, ?)
        """, (session_id, number, name))

        return cursor.lastrowid


def update_milestone(
    milestone_id: int,
    updates: Dict[str, Any],
    db_path: Optional[str] = None
) -> None:
    """Update milestone fields. Keys: status, executor_report, planner_feedback."""

    if not updates:
        return

    # Add updated_at timestamp
    updates = {**updates, "updated_at": datetime.now().isoformat()}

    # Build dynamic UPDATE query
    set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
    values = list(updates.values()) + [milestone_id]

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE milestones
            SET {set_clause}
            WHERE id = ?
        """, values)


def get_milestone(
    session_id: str,
    number: int,
    db_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get milestone by session and number."""

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM milestones
            WHERE session_id = ? AND number = ?
        """, (session_id, number))

        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def get_milestones(
    session_id: str,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get all milestones for a session, ordered by number."""

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM milestones
            WHERE session_id = ?
            ORDER BY number ASC
        """, (session_id,))

        return [dict(row) for row in cursor.fetchall()]


# ============================================================================
# Blocker Management
# ============================================================================

def create_blocker(
    session_id: str,
    agent: str,
    question: str,
    db_path: Optional[str] = None
) -> int:
    """Create a new blocker. Returns blocker ID."""

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO blockers (session_id, agent, question)
            VALUES (?, ?, ?)
        """, (session_id, agent, question))

        return cursor.lastrowid


def resolve_blocker(
    blocker_id: int,
    response: str,
    db_path: Optional[str] = None
) -> None:
    """Mark blocker as resolved with response."""

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE blockers
            SET response = ?, resolved_at = ?
            WHERE id = ?
        """, (response, datetime.now().isoformat(), blocker_id))


def get_unresolved_blockers(
    session_id: str,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get all unresolved blockers for a session."""

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM blockers
            WHERE session_id = ? AND resolved_at IS NULL
            ORDER BY created_at ASC
        """, (session_id,))

        return [dict(row) for row in cursor.fetchall()]


def get_all_blockers(
    session_id: str,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get all blockers (resolved and unresolved) for a session."""

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM blockers
            WHERE session_id = ?
            ORDER BY created_at ASC
        """, (session_id,))

        return [dict(row) for row in cursor.fetchall()]
