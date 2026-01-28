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

        # Add heartbeat_at column if it doesn't exist (for stuck session detection)
        try:
            cursor.execute("""
                ALTER TABLE sessions ADD COLUMN heartbeat_at TIMESTAMP
            """)
        except sqlite3.OperationalError:
            pass

        # Add project_id column if it doesn't exist (for project scoping)
        try:
            cursor.execute("""
                ALTER TABLE sessions ADD COLUMN project_id TEXT
            """)
        except sqlite3.OperationalError:
            pass

        # Add project_remote column if it doesn't exist (for project display)
        try:
            cursor.execute("""
                ALTER TABLE sessions ADD COLUMN project_remote TEXT
            """)
        except sqlite3.OperationalError:
            pass

        # Add auth tracking columns if they don't exist
        for column, col_type in [
            ("auth_source", "TEXT"),
            ("auth_signals", "TEXT"),
            ("auth_detected_at", "TIMESTAMP"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE sessions ADD COLUMN {column} {col_type}")
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Add mcp_config_json column if it doesn't exist (for MCP tool support)
        try:
            cursor.execute("""
                ALTER TABLE sessions ADD COLUMN mcp_config_json TEXT
            """)
        except sqlite3.OperationalError:
            pass  # Column already exists

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

        # Add telegram_message_id column to blockers if it doesn't exist
        try:
            cursor.execute("""
                ALTER TABLE blockers ADD COLUMN telegram_message_id INTEGER
            """)
        except sqlite3.OperationalError:
            pass

        # Telegram state table (for polling cursor)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telegram_state (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                last_update_id INTEGER DEFAULT 0
            )
        """)

        # Initialize telegram_state with a single row if empty
        cursor.execute("""
            INSERT OR IGNORE INTO telegram_state (id, last_update_id) VALUES (1, 0)
        """)

        # Queue items table (for plan queue feature)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queue_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                plan_path TEXT NOT NULL,
                feature_description TEXT,
                position INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                session_id TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP
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

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_queue_items_project_status
            ON queue_items(project_id, status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_queue_items_session_id
            ON queue_items(session_id)
        """)

        # Session errors table (for error tracking and debugging)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                stack_trace TEXT,
                phase TEXT,
                milestone_number INTEGER,
                log_file_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_errors_session_id
            ON session_errors(session_id)
        """)

        # Tool invocations table (SDK 0.1.22+)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tool_invocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                agent TEXT NOT NULL,
                milestone_number INTEGER,
                tool_name TEXT NOT NULL,
                input_summary TEXT,
                output_summary TEXT,
                success INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tool_invocations_session_id
            ON tool_invocations(session_id)
        """)

        # Exploration results table (Phase 1A)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exploration_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                milestone_number INTEGER,
                query TEXT NOT NULL,
                findings TEXT,
                sources_consulted TEXT,
                tokens_used INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                is_partial INTEGER DEFAULT 0,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_exploration_results_session_id
            ON exploration_results(session_id)
        """)

        # Validation results table (Phase 1B)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS validation_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                milestone_number INTEGER,
                validator_name TEXT NOT NULL,
                issues_json TEXT,
                high_count INTEGER DEFAULT 0,
                medium_count INTEGER DEFAULT 0,
                low_count INTEGER DEFAULT 0,
                warning_count INTEGER DEFAULT 0,
                tokens_used INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_validation_results_session_id
            ON validation_results(session_id)
        """)

        conn.commit()


# ============================================================================
# Session CRUD
# ============================================================================

def _sqlite_timestamp() -> str:
    """Get current timestamp in SQLite-friendly format (YYYY-MM-DD HH:MM:SS)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_session(
    feature_description: str,
    planner_model: Optional[str] = None,
    executor_model: Optional[str] = None,
    project_id: Optional[str] = None,
    project_remote: Optional[str] = None,
    auth_info: Optional[Dict[str, Any]] = None,
    mcp_config: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None
) -> str:
    """
    Create a new workflow session. Returns session ID.

    Args:
        feature_description: Description of the feature being implemented
        planner_model: Model for planner agent
        executor_model: Model for executor agent
        project_id: Project identifier (repo root path)
        project_remote: Git remote URL (optional)
        auth_info: Authentication info dict from AuthInfo.to_db_dict()
        mcp_config: MCP configuration dict (raw, with ${VAR} preserved)
        db_path: Custom database path
    """
    import json

    session_id = str(uuid.uuid4())[:8]  # Short ID for CLI convenience
    now = _sqlite_timestamp()

    # Extract auth fields if provided
    auth_source = auth_info.get("auth_source") if auth_info else None
    auth_signals = auth_info.get("auth_signals") if auth_info else None
    auth_detected_at = auth_info.get("auth_detected_at") if auth_info else None

    # Serialize MCP config to JSON
    mcp_config_json = json.dumps(mcp_config) if mcp_config else None

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sessions (
                id, feature_description, planner_model, executor_model,
                heartbeat_at, project_id, project_remote,
                auth_source, auth_signals, auth_detected_at,
                mcp_config_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, feature_description, planner_model, executor_model,
              now, project_id, project_remote,
              auth_source, auth_signals, auth_detected_at,
              mcp_config_json))

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


def get_session_mcp_config(
    session_id: str,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get MCP configuration from a session.

    Args:
        session_id: Session identifier
        db_path: Optional database path

    Returns:
        MCP config dict or None if not set
    """
    import json

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT mcp_config_json FROM sessions WHERE id = ?",
            (session_id,)
        )

        result = cursor.fetchone()
        if result and result[0]:
            return json.loads(result[0])
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


def touch_session(
    session_id: str,
    db_path: Optional[str] = None
) -> None:
    """
    Update heartbeat_at to record activity without state change.

    Use this to signal "process is alive" during long-running operations
    like streaming agent responses.
    """
    now = _sqlite_timestamp()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE sessions
            SET heartbeat_at = ?
            WHERE id = ?
        """, (now, session_id))


def list_sessions(
    db_path: Optional[str] = None,
    status: Optional[str] = None,
    project_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    List sessions, optionally filtered by status and/or project.

    Args:
        db_path: Custom database path
        status: Filter by status (active, paused, completed, failed)
        project_id: Filter by project ID (repo root path)

    Returns:
        List of session dictionaries
    """

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        conditions = []
        params = []

        if status:
            conditions.append("status = ?")
            params.append(status)

        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        cursor.execute(f"""
            SELECT * FROM sessions
            {where_clause}
            ORDER BY created_at DESC
        """, params)

        return [dict(row) for row in cursor.fetchall()]


def get_stuck_sessions(
    db_path: Optional[str] = None,
    inactive_minutes: int = 20
) -> List[Dict[str, Any]]:
    """
    Get sessions that appear to be stuck (ACTIVE but no heartbeat for a while).

    Uses heartbeat_at (falls back to updated_at if NULL) and does datetime
    comparison in Python to avoid SQLite parsing issues.

    Only checks planning/execution phases (not discovery which waits on human,
    or paused/completed which are terminal states).

    Args:
        db_path: Optional database path
        inactive_minutes: Minutes of inactivity to consider stuck (default: 20)

    Returns:
        List of sessions that appear stuck
    """
    from datetime import timedelta

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Get candidate sessions: ACTIVE in planning or execution phase
        cursor.execute("""
            SELECT * FROM sessions
            WHERE status = 'active'
            AND phase IN ('planning', 'execution')
            ORDER BY heartbeat_at DESC, updated_at DESC
        """)

        candidates = [dict(row) for row in cursor.fetchall()]

    # Filter by heartbeat in Python (avoids SQLite datetime parsing issues)
    now = datetime.now()
    threshold = now - timedelta(minutes=inactive_minutes)
    stuck = []

    for session in candidates:
        # Use heartbeat_at if available, fall back to updated_at
        last_activity_str = session.get('heartbeat_at') or session.get('updated_at')

        if not last_activity_str:
            # No timestamp at all - consider stuck
            stuck.append(session)
            continue

        try:
            # Parse timestamp (handle both formats)
            if 'T' in last_activity_str:
                # ISO format: 2025-12-16T04:25:25.123456
                last_activity = datetime.fromisoformat(last_activity_str)
            else:
                # SQLite format: 2025-12-16 04:25:25
                last_activity = datetime.strptime(last_activity_str, "%Y-%m-%d %H:%M:%S")

            if last_activity < threshold:
                stuck.append(session)

        except (ValueError, TypeError):
            # If we can't parse, assume stuck
            stuck.append(session)

    return stuck


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


# ============================================================================
# Telegram State Management
# ============================================================================

def set_blocker_telegram_message_id(
    blocker_id: int,
    telegram_message_id: int,
    db_path: Optional[str] = None
) -> None:
    """
    Store Telegram message ID for a blocker (for reply tracking).

    Args:
        blocker_id: Database blocker ID
        telegram_message_id: Telegram message ID returned from sendMessage
        db_path: Custom database path
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE blockers
            SET telegram_message_id = ?
            WHERE id = ?
        """, (telegram_message_id, blocker_id))


def get_blocker_by_telegram_message_id(
    telegram_message_id: int,
    db_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Find blocker by Telegram message ID.

    Args:
        telegram_message_id: Telegram message ID to lookup
        db_path: Custom database path

    Returns:
        Blocker dict if found, None otherwise
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT b.*, s.project_id
            FROM blockers b
            JOIN sessions s ON b.session_id = s.id
            WHERE b.telegram_message_id = ?
        """, (telegram_message_id,))

        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def get_telegram_last_update_id(db_path: Optional[str] = None) -> int:
    """
    Get the last processed Telegram update ID.

    Args:
        db_path: Custom database path

    Returns:
        Last update ID (0 if not set)
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT last_update_id FROM telegram_state WHERE id = 1
        """)

        row = cursor.fetchone()
        if row:
            return row['last_update_id'] or 0
        return 0


def set_telegram_last_update_id(
    last_update_id: int,
    db_path: Optional[str] = None
) -> None:
    """
    Save the last processed Telegram update ID.

    Args:
        last_update_id: The update ID to store
        db_path: Custom database path
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE telegram_state
            SET last_update_id = ?
            WHERE id = 1
        """, (last_update_id,))


# ============================================================================
# Queue Items Management (Plan Queue Feature)
# ============================================================================

def create_queue_item(
    project_id: str,
    plan_path: str,
    feature_description: str,
    position: int,
    db_path: Optional[str] = None
) -> int:
    """
    Create a new queue item for plan queue feature.

    Args:
        project_id: Project identifier (repo root path)
        plan_path: Path to the plan file
        feature_description: Extracted feature description for the plan
        position: Position in queue (0-based ordering)
        db_path: Custom database path

    Returns:
        Queue item ID
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO queue_items (
                project_id, plan_path, feature_description, position
            )
            VALUES (?, ?, ?, ?)
        """, (project_id, plan_path, feature_description, position))

        return cursor.lastrowid


def list_queue_items(
    project_id: str,
    db_path: Optional[str] = None,
    include_completed: bool = True
) -> List[Dict[str, Any]]:
    """
    List queue items for a project, ordered by position.

    Args:
        project_id: Project identifier (repo root path)
        db_path: Custom database path
        include_completed: If False, exclude completed/failed items

    Returns:
        List of queue item dictionaries
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        if include_completed:
            cursor.execute("""
                SELECT * FROM queue_items
                WHERE project_id = ?
                ORDER BY position ASC
            """, (project_id,))
        else:
            cursor.execute("""
                SELECT * FROM queue_items
                WHERE project_id = ?
                AND status NOT IN ('completed', 'failed')
                ORDER BY position ASC
            """, (project_id,))

        return [dict(row) for row in cursor.fetchall()]


def get_next_queue_item(
    project_id: str,
    db_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Get the next pending queue item for a project (by position).

    Args:
        project_id: Project identifier (repo root path)
        db_path: Custom database path

    Returns:
        Next pending queue item dict, or None if no pending items
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM queue_items
            WHERE project_id = ? AND status = 'pending'
            ORDER BY position ASC
            LIMIT 1
        """, (project_id,))

        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def get_queue_item_by_session_id(
    session_id: str,
    db_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Get queue item by associated session ID (for resume integration).

    Args:
        session_id: Session ID to look up
        db_path: Custom database path

    Returns:
        Queue item dict if found, None otherwise
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM queue_items
            WHERE session_id = ?
        """, (session_id,))

        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def update_queue_item(
    item_id: int,
    db_path: Optional[str] = None,
    status: Optional[str] = None,
    session_id: Optional[str] = None,
    error_message: Optional[str] = None,
    started_at: Optional[str] = None,
    completed_at: Optional[str] = None
) -> bool:
    """
    Update queue item fields.

    Args:
        item_id: Queue item ID
        db_path: Custom database path
        status: New status (pending, running, paused, completed, failed)
        session_id: Associated session ID
        error_message: Error message (for failed status)
        started_at: Timestamp when item started
        completed_at: Timestamp when item completed

    Returns:
        True if update succeeded, False otherwise
    """
    updates = {}
    if status is not None:
        updates["status"] = status
    if session_id is not None:
        updates["session_id"] = session_id
    if error_message is not None:
        updates["error_message"] = error_message
    if started_at is not None:
        updates["started_at"] = started_at
    if completed_at is not None:
        updates["completed_at"] = completed_at

    if not updates:
        return False

    # Build dynamic UPDATE query
    set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
    values = list(updates.values()) + [item_id]

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE queue_items
            SET {set_clause}
            WHERE id = ?
        """, values)

        return cursor.rowcount > 0


def clear_active_queue(
    project_id: str,
    db_path: Optional[str] = None
) -> int:
    """
    Clear all active queue items (pending, running, paused) for a project.

    This is used for queue reset (--queue-reset flag).
    Completed/failed items are retained for history.

    Args:
        project_id: Project identifier (repo root path)
        db_path: Custom database path

    Returns:
        Number of items deleted
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM queue_items
            WHERE project_id = ?
            AND status IN ('pending', 'running', 'paused')
        """, (project_id,))

        return cursor.rowcount


# ============================================================================
# Session Errors
# ============================================================================

def log_session_error(
    session_id: str,
    error_type: str,
    error_message: str,
    stack_trace: Optional[str] = None,
    phase: Optional[str] = None,
    milestone_number: Optional[int] = None,
    log_file_path: Optional[str] = None,
    db_path: Optional[str] = None
) -> int:
    """
    Log an error for a session.

    Args:
        session_id: Session where the error occurred
        error_type: Exception class name (e.g., "AgentError")
        error_message: Error message string
        stack_trace: Full stack trace (optional)
        phase: Phase when error occurred (optional)
        milestone_number: Current milestone when error occurred (optional)
        log_file_path: Path to the error log file (optional)
        db_path: Custom database path

    Returns:
        The error record ID
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO session_errors (
                session_id, error_type, error_message, stack_trace,
                phase, milestone_number, log_file_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (session_id, error_type, error_message, stack_trace,
              phase, milestone_number, log_file_path))

        return cursor.lastrowid


def get_session_errors(
    session_id: str,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all errors for a session, ordered by most recent first.

    Args:
        session_id: Session ID to query
        db_path: Custom database path

    Returns:
        List of error dicts
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM session_errors
            WHERE session_id = ?
            ORDER BY created_at DESC
        """, (session_id,))

        return [dict(row) for row in cursor.fetchall()]


def get_latest_session_error(
    session_id: str,
    db_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Get the most recent error for a session.

    Args:
        session_id: Session ID to query
        db_path: Custom database path

    Returns:
        Error dict or None if no errors
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM session_errors
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (session_id,))

        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


# ============================================================================
# Tool Invocations (SDK 0.1.22+)
# ============================================================================


def save_tool_invocation(
    session_id: str,
    agent: str,
    tool_name: str,
    milestone_number: Optional[int] = None,
    input_summary: Optional[str] = None,
    output_summary: Optional[str] = None,
    success: bool = True,
    db_path: Optional[str] = None
) -> int:
    """
    Save a tool invocation record.

    Args:
        session_id: Session ID
        agent: Agent name (planner/executor)
        tool_name: Name of the tool invoked
        milestone_number: Current milestone number (optional)
        input_summary: Truncated input (optional)
        output_summary: Truncated output (optional)
        success: Whether the tool succeeded
        db_path: Custom database path

    Returns:
        The tool invocation record ID
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tool_invocations (
                session_id, agent, milestone_number, tool_name,
                input_summary, output_summary, success
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (session_id, agent, milestone_number, tool_name,
              input_summary, output_summary, 1 if success else 0))

        return cursor.lastrowid


def save_tool_invocations_batch(
    session_id: str,
    agent: str,
    invocations: List[Dict[str, Any]],
    milestone_number: Optional[int] = None,
    db_path: Optional[str] = None
) -> int:
    """
    Save multiple tool invocations in a batch.

    Args:
        session_id: Session ID
        agent: Agent name (planner/executor)
        invocations: List of invocation dicts with tool_name, input, output, success
        milestone_number: Current milestone number (optional)
        db_path: Custom database path

    Returns:
        Number of records inserted
    """
    if not invocations:
        return 0

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        count = 0
        for inv in invocations:
            tool_name = inv.get('tool_name', inv.get('name', 'unknown'))
            input_summary = _truncate_str(str(inv.get('input', '')), 500)
            output_summary = _truncate_str(str(inv.get('output', '')), 1000)
            success = inv.get('success', True)

            cursor.execute("""
                INSERT INTO tool_invocations (
                    session_id, agent, milestone_number, tool_name,
                    input_summary, output_summary, success
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (session_id, agent, milestone_number, tool_name,
                  input_summary, output_summary, 1 if success else 0))
            count += 1

        return count


def get_tool_invocations(
    session_id: str,
    agent: Optional[str] = None,
    milestone_number: Optional[int] = None,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get tool invocations for a session.

    Args:
        session_id: Session ID to query
        agent: Filter by agent name (optional)
        milestone_number: Filter by milestone (optional)
        db_path: Custom database path

    Returns:
        List of tool invocation dicts
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        query = "SELECT * FROM tool_invocations WHERE session_id = ?"
        params = [session_id]

        if agent:
            query += " AND agent = ?"
            params.append(agent)

        if milestone_number is not None:
            query += " AND milestone_number = ?"
            params.append(milestone_number)

        query += " ORDER BY created_at ASC"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_session_modified_files(
    session_id: str,
    db_path: Optional[str] = None
) -> List[str]:
    """
    Extract file paths from Write/Edit/NotebookEdit tool invocations for a session.

    Parses the input_summary field of tool invocations to extract file paths.
    Only includes file-modifying tools: Write, Edit, MultiEdit, NotebookEdit.

    Args:
        session_id: Session ID to query
        db_path: Custom database path

    Returns:
        List of unique file paths that were modified during the session
    """
    import re

    # Tools that modify files
    FILE_MODIFYING_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT tool_name, input_summary
            FROM tool_invocations
            WHERE session_id = ? AND tool_name IN (?, ?, ?, ?)
            ORDER BY created_at ASC
        """, (session_id, "Write", "Edit", "MultiEdit", "NotebookEdit"))

        rows = cursor.fetchall()

    # Extract file paths from input_summary
    # Common patterns:
    # - "file_path: /path/to/file.py" (Write, Edit)
    # - "notebook_path: /path/to/notebook.ipynb" (NotebookEdit)
    # - "/path/to/file.py: old_string -> new_string" (Edit summary format)
    files = set()

    for row in rows:
        tool_name = row[0]
        input_summary = row[1] or ""

        # Pattern 1: "file_path: /path/to/file" or "notebook_path: /path/to/file"
        match = re.search(r'(?:file_path|notebook_path):\s*([^\s,]+)', input_summary)
        if match:
            files.add(match.group(1))
            continue

        # Pattern 2: Path at start of summary (Edit format: "/path/file.py: ...")
        match = re.match(r'^(/[^\s:]+|[A-Za-z]:\\[^\s:]+)', input_summary)
        if match:
            files.add(match.group(1))
            continue

        # Pattern 3: Look for file-like paths in the summary
        # Match absolute paths or relative paths with extensions
        for match in re.finditer(r'(/[\w\-./]+\.\w+|[\w\-./]+\.\w+)', input_summary):
            path = match.group(1)
            # Filter out obvious non-paths
            if '/' in path or '\\' in path:
                files.add(path)

    return list(files)


def _truncate_str(s: str, max_len: int) -> str:
    """Truncate a string to max_len, adding ... if truncated."""
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."


# ============================================================================
# Exploration Results (Phase 1A)
# ============================================================================

def save_exploration_result(
    session_id: str,
    query: str,
    findings: str,
    sources_consulted: Optional[List[str]] = None,
    tokens_used: int = 0,
    duration_ms: int = 0,
    is_partial: bool = False,
    error: Optional[str] = None,
    milestone_number: Optional[int] = None,
    db_path: Optional[str] = None
) -> int:
    """
    Save an exploration result to the database.

    Args:
        session_id: Session ID
        query: The exploration query
        findings: Structured findings text
        sources_consulted: List of files/sources explored
        tokens_used: Tokens used in exploration
        duration_ms: Duration in milliseconds
        is_partial: Whether results are partial (timeout/limit)
        error: Error message if exploration failed
        milestone_number: Current milestone number
        db_path: Custom database path

    Returns:
        The inserted record ID
    """
    import json

    sources_json = json.dumps(sources_consulted) if sources_consulted else None

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO exploration_results (
                session_id, milestone_number, query, findings,
                sources_consulted, tokens_used, duration_ms,
                is_partial, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, milestone_number, query, findings,
            sources_json, tokens_used, duration_ms,
            1 if is_partial else 0, error
        ))
        return cursor.lastrowid


def get_exploration_results(
    session_id: str,
    milestone_number: Optional[int] = None,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get exploration results for a session.

    Args:
        session_id: Session ID
        milestone_number: Filter by milestone (optional)
        db_path: Custom database path

    Returns:
        List of exploration result dicts
    """
    import json

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        query = "SELECT * FROM exploration_results WHERE session_id = ?"
        params = [session_id]

        if milestone_number is not None:
            query += " AND milestone_number = ?"
            params.append(milestone_number)

        query += " ORDER BY created_at ASC"

        cursor.execute(query, params)
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            # Parse sources JSON
            if d.get('sources_consulted'):
                try:
                    d['sources_consulted'] = json.loads(d['sources_consulted'])
                except json.JSONDecodeError:
                    d['sources_consulted'] = []
            else:
                d['sources_consulted'] = []
            # Convert is_partial to bool
            d['is_partial'] = bool(d.get('is_partial', 0))
            results.append(d)

        return results


# ============================================================================
# Validation Results (Phase 1B)
# ============================================================================

def save_validation_result(
    session_id: str,
    validator_name: str,
    issues_json: Optional[str] = None,
    high_count: int = 0,
    medium_count: int = 0,
    low_count: int = 0,
    warning_count: int = 0,
    tokens_used: int = 0,
    duration_ms: int = 0,
    error: Optional[str] = None,
    milestone_number: Optional[int] = None,
    db_path: Optional[str] = None
) -> int:
    """
    Save a validation result to the database.

    Args:
        session_id: Session ID
        validator_name: Name of the validator
        issues_json: JSON string of issues list
        high_count: Number of HIGH severity issues
        medium_count: Number of MEDIUM severity issues
        low_count: Number of LOW severity issues
        warning_count: Number of WARNING severity issues
        tokens_used: Tokens used in validation
        duration_ms: Duration in milliseconds
        error: Error message if validation failed
        milestone_number: Current milestone number
        db_path: Custom database path

    Returns:
        The inserted record ID
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO validation_results (
                session_id, milestone_number, validator_name, issues_json,
                high_count, medium_count, low_count, warning_count,
                tokens_used, duration_ms, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, milestone_number, validator_name, issues_json,
            high_count, medium_count, low_count, warning_count,
            tokens_used, duration_ms, error
        ))
        return cursor.lastrowid


def save_validation_results_batch(
    session_id: str,
    results: List[Dict[str, Any]],
    milestone_number: Optional[int] = None,
    db_path: Optional[str] = None
) -> int:
    """
    Save multiple validation results in a batch (single transaction).

    Args:
        session_id: Session ID
        results: List of ValidationResult dicts (from ValidationResult.to_dict())
        milestone_number: Current milestone number
        db_path: Custom database path

    Returns:
        Number of records inserted
    """
    import json

    if not results:
        return 0

    # Prepare all rows for batch insert
    rows = []
    for result in results:
        issues = result.get('issues', [])
        issues_json = json.dumps(issues)

        # Count by severity
        high_count = sum(1 for i in issues if i.get('severity') == 'high')
        medium_count = sum(1 for i in issues if i.get('severity') == 'medium')
        low_count = sum(1 for i in issues if i.get('severity') == 'low')
        warning_count = sum(1 for i in issues if i.get('severity') == 'warning')

        rows.append((
            session_id,
            milestone_number,
            result.get('validator_name', 'unknown'),
            issues_json,
            high_count,
            medium_count,
            low_count,
            warning_count,
            result.get('tokens_used', 0),
            result.get('duration_ms', 0),
            result.get('error'),
        ))

    # Single transaction with executemany for efficiency
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT INTO validation_results (
                session_id, milestone_number, validator_name, issues_json,
                high_count, medium_count, low_count, warning_count,
                tokens_used, duration_ms, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        return len(rows)


def get_validation_results(
    session_id: str,
    milestone_number: Optional[int] = None,
    validator_name: Optional[str] = None,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get validation results for a session.

    Args:
        session_id: Session ID
        milestone_number: Filter by milestone (optional)
        validator_name: Filter by validator name (optional)
        db_path: Custom database path

    Returns:
        List of validation result dicts
    """
    import json

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        query = "SELECT * FROM validation_results WHERE session_id = ?"
        params = [session_id]

        if milestone_number is not None:
            query += " AND milestone_number = ?"
            params.append(milestone_number)

        if validator_name:
            query += " AND validator_name = ?"
            params.append(validator_name)

        query += " ORDER BY created_at ASC"

        cursor.execute(query, params)
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            # Parse issues JSON
            if d.get('issues_json'):
                try:
                    d['issues'] = json.loads(d['issues_json'])
                except json.JSONDecodeError:
                    d['issues'] = []
            else:
                d['issues'] = []
            results.append(d)

        return results


def get_validation_summary(
    session_id: str,
    milestone_number: Optional[int] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get aggregated validation summary for a session or milestone.

    Args:
        session_id: Session ID
        milestone_number: Filter by milestone (optional)
        db_path: Custom database path

    Returns:
        Dict with aggregated counts and has_high_severity flag
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        query = """
            SELECT
                SUM(high_count) as total_high,
                SUM(medium_count) as total_medium,
                SUM(low_count) as total_low,
                SUM(warning_count) as total_warning,
                COUNT(*) as validator_count
            FROM validation_results
            WHERE session_id = ?
        """
        params = [session_id]

        if milestone_number is not None:
            query += " AND milestone_number = ?"
            params.append(milestone_number)

        cursor.execute(query, params)
        row = cursor.fetchone()

        if row:
            return {
                "high": row['total_high'] or 0,
                "medium": row['total_medium'] or 0,
                "low": row['total_low'] or 0,
                "warning": row['total_warning'] or 0,
                "validator_count": row['validator_count'] or 0,
                "has_high_severity": (row['total_high'] or 0) > 0,
            }

        return {
            "high": 0,
            "medium": 0,
            "low": 0,
            "warning": 0,
            "validator_count": 0,
            "has_high_severity": False,
        }
