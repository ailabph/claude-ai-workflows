#!/usr/bin/env python3
"""POC 3a: SQLite Session Database

Validate the planner-auto SQLite schema and session lifecycle.

Steps:
  1. Define schema (CREATE TABLE statements):
     - sessions: id, project, phase, status, created_at, updated_at
     - messages: id, session_id, role, content, timestamp
     - context_entries: id, session_id, entry_type, key, value, timestamp
     - plan_drafts: id, session_id, draft_number, content, created_at
     - reviews: id, session_id, review_number, verdict, issues_json,
                summary, raw_response, created_at
  2. Create in-memory DB (and optionally write to temp file for inspection)
  3. Simulate full session lifecycle:
     a. Create session (phase=setup)
     b. Add context entries (files loaded, entities discovered)
     c. Append messages (user/planner conversation)
     d. Update phase to planning
     e. Store plan draft (draft_number=1)
     f. Store review (review_number=1, verdict=NO_GO, issues=[...])
     g. Store revised plan draft (draft_number=2)
     h. Store review (review_number=2, verdict=GO)
     i. Mark session complete
  4. Run query patterns:
     - Get session by ID
     - Get all messages for session (ordered)
     - Get latest plan draft for session
     - Get all reviews for session
     - Get context entries by type
  5. Print summary: table row counts, sample data, query results

Usage:
  python scripts/poc/planner-auto/poc_session_db.py
  python scripts/poc/planner-auto/poc_session_db.py --db-path /tmp/planner_poc.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and enable WAL mode."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id         TEXT PRIMARY KEY,
            project    TEXT NOT NULL,
            phase      TEXT NOT NULL,
            status     TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            timestamp  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS context_entries (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            entry_type TEXT NOT NULL,
            key        TEXT NOT NULL,
            value      TEXT NOT NULL,
            timestamp  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS plan_drafts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id   TEXT NOT NULL REFERENCES sessions(id),
            draft_number INTEGER NOT NULL,
            content      TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            UNIQUE(session_id, draft_number)
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    TEXT NOT NULL REFERENCES sessions(id),
            review_number INTEGER NOT NULL,
            verdict       TEXT NOT NULL,
            issues_json   TEXT NOT NULL,
            summary       TEXT NOT NULL,
            raw_response  TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            UNIQUE(session_id, review_number)
        );
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    """Return current UTC timestamp as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)


# ---------------------------------------------------------------------------
# CRUD functions
# ---------------------------------------------------------------------------

def create_session(conn: sqlite3.Connection, project: str) -> str:
    """Create a new session with phase=setup, status=active. Returns session_id."""
    session_id = uuid.uuid4().hex[:12]
    now = _now()
    conn.execute(
        "INSERT INTO sessions (id, project, phase, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, project, "setup", "active", now, now),
    )
    conn.commit()
    return session_id


def update_session_phase(conn: sqlite3.Connection, session_id: str, phase: str) -> None:
    """Update the phase of a session."""
    conn.execute(
        "UPDATE sessions SET phase = ?, updated_at = ? WHERE id = ?",
        (phase, _now(), session_id),
    )
    conn.commit()


def update_session_status(conn: sqlite3.Connection, session_id: str, status: str) -> None:
    """Update the status of a session."""
    conn.execute(
        "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
        (status, _now(), session_id),
    )
    conn.commit()


def add_message(conn: sqlite3.Connection, session_id: str, role: str, content: str) -> None:
    """Append a message to the conversation log."""
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, role, content, _now()),
    )
    conn.commit()


def add_context_entry(
    conn: sqlite3.Connection,
    session_id: str,
    entry_type: str,
    key: str,
    value: str,
) -> None:
    """Append a context entry."""
    conn.execute(
        "INSERT INTO context_entries (session_id, entry_type, key, value, timestamp) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, entry_type, key, value, _now()),
    )
    conn.commit()


def add_plan_draft(
    conn: sqlite3.Connection,
    session_id: str,
    draft_number: int,
    content: str,
) -> None:
    """Insert a plan draft."""
    conn.execute(
        "INSERT INTO plan_drafts (session_id, draft_number, content, created_at) "
        "VALUES (?, ?, ?, ?)",
        (session_id, draft_number, content, _now()),
    )
    conn.commit()


def add_review(
    conn: sqlite3.Connection,
    session_id: str,
    review_number: int,
    verdict: str,
    issues_json: str,
    summary: str,
    raw_response: str,
) -> None:
    """Insert a review."""
    conn.execute(
        "INSERT INTO reviews (session_id, review_number, verdict, issues_json, "
        "summary, raw_response, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, review_number, verdict, issues_json, summary, raw_response, _now()),
    )
    conn.commit()


def get_session(conn: sqlite3.Connection, session_id: str) -> dict | None:
    """Return session row as dict, or None if not found."""
    row = conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    return _row_to_dict(row) if row else None


def get_messages(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """Return all messages for a session, ordered by timestamp."""
    rows = conn.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp",
        (session_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_latest_plan_draft(conn: sqlite3.Connection, session_id: str) -> dict | None:
    """Return the highest draft_number plan draft for a session."""
    row = conn.execute(
        "SELECT * FROM plan_drafts WHERE session_id = ? "
        "ORDER BY draft_number DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    return _row_to_dict(row) if row else None


def get_all_reviews(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """Return all reviews for a session, ordered by review_number."""
    rows = conn.execute(
        "SELECT * FROM reviews WHERE session_id = ? ORDER BY review_number",
        (session_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_context_entries(
    conn: sqlite3.Connection,
    session_id: str,
    entry_type: str | None = None,
) -> list[dict]:
    """Return context entries, optionally filtered by type."""
    if entry_type is not None:
        rows = conn.execute(
            "SELECT * FROM context_entries WHERE session_id = ? AND entry_type = ? "
            "ORDER BY timestamp",
            (session_id, entry_type),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM context_entries WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Lifecycle test
# ---------------------------------------------------------------------------

def run_lifecycle_test(conn: sqlite3.Connection) -> list[tuple[str, bool, str]]:
    """Simulate a full session lifecycle and verify query results.

    Returns a list of (test_name, passed, detail) tuples.
    """
    results: list[tuple[str, bool, str]] = []

    # a. Create session
    sid = create_session(conn, "planner-auto-poc")

    session = get_session(conn, sid)
    results.append((
        "session_created",
        session is not None and session["phase"] == "setup" and session["status"] == "active",
        f"id={sid}, phase={session['phase']}, status={session['status']}" if session else "None",
    ))

    # b. Add 3 context entries: 2 files, 1 entity
    add_context_entry(conn, sid, "file", "src/main.py", "def main(): ...")
    add_context_entry(conn, sid, "file", "src/models.py", "class User: ...")
    add_context_entry(conn, sid, "entity", "User", "Core domain entity with email, name, role fields")

    entries = get_context_entries(conn, sid)
    results.append((
        "context_entries_added",
        len(entries) == 3,
        f"{len(entries)} entries",
    ))

    # c. Update phase to "context"
    update_session_phase(conn, sid, "context")

    # d. Add 5 messages
    add_message(conn, sid, "user", "I've loaded src/main.py and src/models.py for context.")
    add_message(conn, sid, "planner", "Got it. I see a Flask app with a User model. What feature would you like to build?")
    add_message(conn, sid, "user", "Add user registration with email validation and password hashing.")
    add_message(conn, sid, "planner", "Should registration send a confirmation email, or just validate the format?")
    add_message(conn, sid, "user", "Just validate the format for now. We can add email sending later.")

    # e. Update phase to "discussion"
    update_session_phase(conn, sid, "discussion")

    # f. Update phase to "planning"
    update_session_phase(conn, sid, "planning")

    # g. Add plan draft 1
    plan_v1 = (
        "# User Registration Plan v1\n\n"
        "## Milestone 1: Database Schema\n"
        "- Add email (unique, indexed) and password_hash columns to User model\n"
        "- Create Alembic migration\n"
        "- Add email format validation at model level\n\n"
        "## Milestone 2: Registration Endpoint\n"
        "- POST /api/register accepts {email, password}\n"
        "- Hash password with bcrypt\n"
        "- Return 201 with user ID on success, 409 on duplicate email\n\n"
        "## Milestone 3: Tests & Validation\n"
        "- Unit tests for email validation (valid/invalid formats)\n"
        "- Integration test for registration flow\n"
        "- Edge cases: empty fields, SQL injection attempts, very long inputs"
    )
    add_plan_draft(conn, sid, 1, plan_v1)

    # h. Update phase to "review"
    update_session_phase(conn, sid, "review")

    # i. Add review 1: NO_GO
    review1_issues = json.dumps([
        {
            "severity": "critical",
            "description": "No rate limiting on registration endpoint",
            "rationale": "Public endpoints must have rate limiting to prevent abuse",
        },
        {
            "severity": "major",
            "description": "Missing password strength requirements",
            "rationale": "Registration should enforce minimum password complexity",
        },
    ])
    review1_raw = (
        "NO_GO. The plan has a critical gap: no rate limiting on the public "
        "registration endpoint. Also missing password strength requirements."
    )
    add_review(conn, sid, 1, "NO_GO", review1_issues, "Critical: no rate limiting; Major: no password policy", review1_raw)

    # j. Add plan draft 2: revised
    plan_v2 = (
        "# User Registration Plan v2 (revised)\n\n"
        "## Milestone 1: Database Schema\n"
        "- Add email (unique, indexed) and password_hash columns to User model\n"
        "- Create Alembic migration\n"
        "- Add email format validation at model level\n\n"
        "## Milestone 2: Registration Endpoint\n"
        "- POST /api/register accepts {email, password}\n"
        "- Hash password with bcrypt\n"
        "- Enforce password policy: min 8 chars, 1 uppercase, 1 digit\n"
        "- Add rate limiting: 5 requests/minute per IP\n"
        "- Return 201 with user ID on success, 409 on duplicate, 429 on rate limit\n\n"
        "## Milestone 3: Tests & Validation\n"
        "- Unit tests for email validation and password policy\n"
        "- Integration test for registration flow (success + failures)\n"
        "- Rate limiting integration test\n"
        "- Edge cases: empty fields, SQL injection attempts, very long inputs"
    )
    add_plan_draft(conn, sid, 2, plan_v2)

    # k. Add review 2: GO
    review2_issues = json.dumps([])
    review2_raw = (
        "GO. The revised plan addresses both issues: rate limiting is now "
        "included in Milestone 2, and password strength requirements are defined. "
        "Ready for implementation."
    )
    add_review(conn, sid, 2, "GO", review2_issues, "Plan approved. All issues addressed.", review2_raw)

    # l. Update status to "complete"
    update_session_status(conn, sid, "complete")

    # --- Verification queries ---

    # Verify session state
    session = get_session(conn, sid)
    results.append((
        "session_phase_review",
        session is not None and session["phase"] == "review",
        f"phase={session['phase']}" if session else "None",
    ))
    results.append((
        "session_status_complete",
        session is not None and session["status"] == "complete",
        f"status={session['status']}" if session else "None",
    ))

    # Verify messages
    messages = get_messages(conn, sid)
    msg_roles = [m["role"] for m in messages]
    expected_roles = ["user", "planner", "user", "planner", "user"]
    results.append((
        "messages_count",
        len(messages) == 5,
        f"{len(messages)} messages",
    ))
    results.append((
        "messages_order",
        msg_roles == expected_roles,
        f"roles={msg_roles}",
    ))

    # Verify latest plan draft
    latest_draft = get_latest_plan_draft(conn, sid)
    results.append((
        "latest_plan_draft",
        latest_draft is not None and latest_draft["draft_number"] == 2,
        f"draft_number={latest_draft['draft_number']}" if latest_draft else "None",
    ))

    # Verify reviews
    reviews = get_all_reviews(conn, sid)
    results.append((
        "reviews_count",
        len(reviews) == 2,
        f"{len(reviews)} reviews",
    ))
    results.append((
        "review_1_nogo",
        len(reviews) >= 1 and reviews[0]["verdict"] == "NO_GO",
        f"verdict={reviews[0]['verdict']}" if len(reviews) >= 1 else "no reviews",
    ))
    results.append((
        "review_2_go",
        len(reviews) >= 2 and reviews[1]["verdict"] == "GO",
        f"verdict={reviews[1]['verdict']}" if len(reviews) >= 2 else "< 2 reviews",
    ))

    # Verify context entries by type
    file_entries = get_context_entries(conn, sid, entry_type="file")
    results.append((
        "context_files_only",
        len(file_entries) == 2,
        f"{len(file_entries)} file entries",
    ))

    all_entries = get_context_entries(conn, sid)
    results.append((
        "context_all_entries",
        len(all_entries) == 3,
        f"{len(all_entries)} total entries",
    ))

    # Row counts (informational, always pass)
    table_counts: dict[str, int] = {}
    for table in ("sessions", "messages", "context_entries", "plan_drafts", "reviews"):
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
        table_counts[table] = count

    expected_counts = {
        "sessions": 1,
        "messages": 5,
        "context_entries": 3,
        "plan_drafts": 2,
        "reviews": 2,
    }
    results.append((
        "row_counts_match",
        table_counts == expected_counts,
        ", ".join(f"{t}={c}" for t, c in table_counts.items()),
    ))

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="POC 3a: SQLite Session Database")
    parser.add_argument(
        "--db-path",
        default=":memory:",
        help="Path to SQLite database file (default: in-memory)",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row

    create_schema(conn)
    results = run_lifecycle_test(conn)

    # --- Print results table ---
    print("POC 3a: SQLite Session Database")
    print("\u2550" * 62)

    header = f" {'#':>2} \u2502 {'Test':<30} \u2502 {'Result':<6} \u2502 Detail"
    separator = f"{'':->4}\u253c{'':->32}\u253c{'':->8}\u253c{'':->15}"

    print(header)
    print(separator)

    passed = 0
    for i, (name, ok, detail) in enumerate(results, 1):
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        print(f" {i:>2} \u2502 {name:<30} \u2502 {status:<6} \u2502 {detail}")

    print("\u2550" * 62)
    print(f"Results: {passed}/{len(results)} passed")

    # --- Table row counts ---
    print("\nTable Row Counts:")
    for table in ("sessions", "messages", "context_entries", "plan_drafts", "reviews"):
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
        print(f"  {table + ':':<18} {count}")

    if args.db_path != ":memory:":
        print(f"\nDB saved to: {args.db_path}")

    conn.close()


if __name__ == "__main__":
    main()
