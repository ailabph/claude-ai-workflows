#!/usr/bin/env python3
"""POC 5a: Failure Paths and Session Recovery

Validate session model behavior under reviewer failure scenarios.

Steps:
  1. Create test DB with POC 3a schema
  2. Create a session in review phase with a plan draft stored
  3. Define simulated reviewer responses:
     a. Timeout (no response within threshold)
     b. Malformed output (random text, no verdict)
     c. Partial response (truncated JSON)
     d. Network error (simulated exception)
  4. For each failure scenario:
     a. Attempt reviewer invocation (simulated)
     b. On failure: retry once
     c. On second failure: pause session, create blocker record
     d. Verify DB state: session.status=paused, blocker exists
     e. Simulate human intervention: resolve blocker
     f. Resume session
     g. Verify DB state: session.status=active, blocker resolved
  5. Test malformed output path specifically:
     a. Feed malformed response through parser
     b. Verify it returns NO_GO with parse-failure issue
     c. Verify planner receives the parse-failure as a reviewable issue
  6. Print summary: scenario, expected state, actual state, pass/fail

Usage:
  python scripts/poc/planner-auto/poc_failure_paths.py
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Sibling imports
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent))
from poc_session_db import (
    create_schema,
    create_session,
    update_session_phase,
    update_session_status,
    add_plan_draft,
    add_review,
    get_session,
)
from poc_parse_go_nogo import parse_reviewer_response, ReviewerResponse, Verdict


# ---------------------------------------------------------------------------
# Blockers table (extends POC 3a schema)
# ---------------------------------------------------------------------------

def create_blockers_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blockers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            source TEXT NOT NULL,  -- 'reviewer_timeout', 'reviewer_malformed', 'reviewer_error'
            question TEXT NOT NULL,  -- description of what went wrong
            answer TEXT,  -- human's response (NULL until resolved)
            status TEXT NOT NULL DEFAULT 'open',  -- 'open', 'resolved'
            created_at TEXT NOT NULL,
            resolved_at TEXT
        )
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Blocker CRUD helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    """Return current UTC timestamp as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def create_blocker(conn: sqlite3.Connection, session_id: str, source: str, question: str) -> int:
    """Insert an open blocker and return its id."""
    cur = conn.execute(
        "INSERT INTO blockers (session_id, source, question, status, created_at) "
        "VALUES (?, ?, ?, 'open', ?)",
        (session_id, source, question, _now()),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def resolve_blocker(conn: sqlite3.Connection, blocker_id: int, answer: str) -> None:
    """Resolve a blocker with the human's answer."""
    conn.execute(
        "UPDATE blockers SET answer = ?, status = 'resolved', resolved_at = ? WHERE id = ?",
        (answer, _now(), blocker_id),
    )
    conn.commit()


def get_open_blockers(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """Return all open blockers for a session."""
    rows = conn.execute(
        "SELECT * FROM blockers WHERE session_id = ? AND status = 'open' ORDER BY created_at",
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Simulated reviewer
# ---------------------------------------------------------------------------

def simulate_reviewer(scenario: str) -> str | None:
    """Simulate a reviewer response for a given failure scenario.

    Returns the raw reviewer output string, None for timeout, or raises
    ConnectionError for network_error.
    """
    if scenario == "timeout":
        return None
    if scenario == "malformed":
        return "asdf 1234 !@#$ random noise ~~~ {{{ ]]]"
    if scenario == "partial_json":
        return '{"verdict": "GO", "issues": [{"severity": "minor", "desc'
    if scenario == "network_error":
        raise ConnectionError("Simulated network failure")
    if scenario == "success":
        return (
            '{"verdict": "GO", "issues": [], '
            '"summary": "Plan looks good. Ready to proceed."}'
        )
    raise ValueError(f"Unknown scenario: {scenario}")


# ---------------------------------------------------------------------------
# Review attempt with retry logic
# ---------------------------------------------------------------------------

def _classify_failure(scenario: str, error: str | None) -> tuple[str, str]:
    """Return (blocker_source, blocker_question) for a failure scenario."""
    if scenario == "timeout":
        return (
            "reviewer_timeout",
            "Reviewer did not respond within the timeout window (2 attempts). "
            "Please check reviewer availability and retry.",
        )
    if scenario == "malformed":
        return (
            "reviewer_malformed",
            "Reviewer returned malformed output that could not be parsed (2 attempts). "
            "Raw output was not a valid review. Please inspect and retry.",
        )
    if scenario == "partial_json":
        return (
            "reviewer_malformed",
            "Reviewer returned truncated JSON that could not be parsed (2 attempts). "
            "The response was cut off mid-stream. Please retry.",
        )
    if scenario == "network_error":
        return (
            "reviewer_error",
            f"Reviewer invocation raised a network error (2 attempts): {error}",
        )
    return ("reviewer_error", f"Unknown failure: {error}")


def _single_attempt(scenario: str) -> tuple[bool, ReviewerResponse | None, str | None]:
    """Execute one reviewer attempt.

    Returns (success, parsed_response_or_None, error_message_or_None).
    """
    try:
        raw = simulate_reviewer(scenario)
    except ConnectionError as exc:
        return False, None, str(exc)

    if raw is None:
        return False, None, "Timeout: no response received"

    parsed = parse_reviewer_response(raw)

    # A parse failure (NO_GO with "could not be parsed" critical issue) is a failure
    if (
        parsed.verdict == Verdict.NO_GO
        and parsed.issues
        and "could not be parsed" in parsed.issues[0].description.lower()
    ):
        return False, parsed, "Malformed: reviewer output could not be parsed"

    return True, parsed, None


def attempt_review(conn: sqlite3.Connection, session_id: str, scenario: str) -> dict:
    """Attempt a review with retry-once logic.

    Returns a dict with: attempts, final_status, parsed, blocker_id, error.
    """
    # Attempt 1
    success, parsed, error = _single_attempt(scenario)
    if success:
        return {
            "attempts": 1,
            "final_status": "success",
            "parsed": parsed,
            "blocker_id": None,
            "error": None,
        }

    # Attempt 1 failed — retry once
    success2, parsed2, error2 = _single_attempt(scenario)
    if success2:
        return {
            "attempts": 2,
            "final_status": "success",
            "parsed": parsed2,
            "blocker_id": None,
            "error": None,
        }

    # Both attempts failed — pause session and create blocker
    update_session_status(conn, session_id, "paused")

    source, question = _classify_failure(scenario, error2 or error)
    blocker_id = create_blocker(conn, session_id, source, question)

    return {
        "attempts": 2,
        "final_status": "paused",
        "parsed": parsed2 or parsed,  # keep the parsed result if any (e.g. malformed)
        "blocker_id": blocker_id,
        "error": error2 or error,
    }


# ---------------------------------------------------------------------------
# Resume function
# ---------------------------------------------------------------------------

def resume_session(conn: sqlite3.Connection, session_id: str, blocker_id: int, answer: str) -> None:
    """Resolve a blocker and resume the session to active status."""
    resolve_blocker(conn, blocker_id, answer)
    update_session_status(conn, session_id, "active")


# ---------------------------------------------------------------------------
# Helper: create a session in review phase with a plan draft
# ---------------------------------------------------------------------------

def _create_review_session(conn: sqlite3.Connection, label: str) -> str:
    """Create a fresh session in review phase with a stored plan draft."""
    sid = create_session(conn, f"poc5a-{label}")
    update_session_phase(conn, sid, "review")
    add_plan_draft(conn, sid, 1, f"# Test plan for {label}\n\n## Milestone 1\n- Task A\n- Task B")
    return sid


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------

def run_tests(conn: sqlite3.Connection) -> list[tuple[str, bool, str]]:
    """Run all failure-path test scenarios. Returns (test_name, passed, detail) tuples."""
    results: list[tuple[str, bool, str]] = []

    # -----------------------------------------------------------------------
    # Timeout scenario
    # -----------------------------------------------------------------------
    sid = _create_review_session(conn, "timeout")
    result = attempt_review(conn, sid, "timeout")

    results.append((
        "timeout_retry_count",
        result["attempts"] == 2,
        f"attempts={result['attempts']}",
    ))

    session = get_session(conn, sid)
    results.append((
        "timeout_session_paused",
        session is not None and session["status"] == "paused",
        f"status={session['status']}" if session else "None",
    ))

    blockers = get_open_blockers(conn, sid)
    results.append((
        "timeout_blocker_created",
        len(blockers) == 1 and blockers[0]["source"] == "reviewer_timeout",
        f"source={blockers[0]['source']}" if blockers else "no blockers",
    ))

    # Resume
    resume_session(conn, sid, result["blocker_id"], "Reviewer is back online, please retry.")
    session = get_session(conn, sid)
    results.append((
        "timeout_resume_active",
        session is not None and session["status"] == "active",
        f"status={session['status']}" if session else "None",
    ))

    blockers = get_open_blockers(conn, sid)
    results.append((
        "timeout_blocker_resolved",
        len(blockers) == 0,
        f"open_blockers={len(blockers)}",
    ))

    # -----------------------------------------------------------------------
    # Malformed scenario
    # -----------------------------------------------------------------------
    sid = _create_review_session(conn, "malformed")
    result = attempt_review(conn, sid, "malformed")

    results.append((
        "malformed_retry_count",
        result["attempts"] == 2,
        f"attempts={result['attempts']}",
    ))

    session = get_session(conn, sid)
    results.append((
        "malformed_session_paused",
        session is not None and session["status"] == "paused",
        f"status={session['status']}" if session else "None",
    ))

    # Verify parse failure produces NO_GO with "could not be parsed" issue
    parsed = result["parsed"]
    parse_ok = (
        parsed is not None
        and parsed.verdict == Verdict.NO_GO
        and len(parsed.issues) >= 1
        and "could not be parsed" in parsed.issues[0].description.lower()
    )
    results.append((
        "malformed_parse_failure",
        parse_ok,
        f"verdict={parsed.verdict.value}, issues={len(parsed.issues)}" if parsed else "no parsed result",
    ))

    # Resume
    resume_session(conn, sid, result["blocker_id"], "Acknowledged. Will re-run with fixed reviewer.")
    session = get_session(conn, sid)
    results.append((
        "malformed_resume_active",
        session is not None and session["status"] == "active",
        f"status={session['status']}" if session else "None",
    ))

    # -----------------------------------------------------------------------
    # Partial JSON scenario
    # -----------------------------------------------------------------------
    sid = _create_review_session(conn, "partial_json")
    result = attempt_review(conn, sid, "partial_json")

    results.append((
        "partial_json_retry_count",
        result["attempts"] == 2,
        f"attempts={result['attempts']}",
    ))

    session = get_session(conn, sid)
    results.append((
        "partial_json_session_paused",
        session is not None and session["status"] == "paused",
        f"status={session['status']}" if session else "None",
    ))

    # Resume
    resume_session(conn, sid, result["blocker_id"], "Noted. Retrying with longer timeout.")
    session = get_session(conn, sid)
    results.append((
        "partial_json_resume_active",
        session is not None and session["status"] == "active",
        f"status={session['status']}" if session else "None",
    ))

    # -----------------------------------------------------------------------
    # Network error scenario
    # -----------------------------------------------------------------------
    sid = _create_review_session(conn, "network_error")
    result = attempt_review(conn, sid, "network_error")

    results.append((
        "network_error_retry_count",
        result["attempts"] == 2,
        f"attempts={result['attempts']}",
    ))

    session = get_session(conn, sid)
    results.append((
        "network_error_session_paused",
        session is not None and session["status"] == "paused",
        f"status={session['status']}" if session else "None",
    ))

    # Resume
    resume_session(conn, sid, result["blocker_id"], "Network restored. Please retry.")
    session = get_session(conn, sid)
    results.append((
        "network_error_resume_active",
        session is not None and session["status"] == "active",
        f"status={session['status']}" if session else "None",
    ))

    # -----------------------------------------------------------------------
    # Success scenario
    # -----------------------------------------------------------------------
    sid = _create_review_session(conn, "success")
    result = attempt_review(conn, sid, "success")

    results.append((
        "success_single_attempt",
        result["attempts"] == 1 and result["blocker_id"] is None,
        f"attempts={result['attempts']}, blocker_id={result['blocker_id']}",
    ))

    session = get_session(conn, sid)
    results.append((
        "success_stays_active",
        session is not None and session["status"] == "active",
        f"status={session['status']}" if session else "None",
    ))

    blockers = get_open_blockers(conn, sid)
    results.append((
        "success_no_blocker",
        len(blockers) == 0,
        f"open_blockers={len(blockers)}",
    ))

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    create_schema(conn)
    create_blockers_table(conn)

    results = run_tests(conn)

    # --- Print results table ---
    print("POC 5a: Failure Paths and Session Recovery")
    print("\u2550" * 68)

    header = f" {'#':>2} \u2502 {'Test':<32} \u2502 {'Result':<6} \u2502 Detail"
    separator = f"{'':->4}\u253c{'':->34}\u253c{'':->8}\u253c{'':->20}"

    print(header)
    print(separator)

    passed = 0
    for i, (name, ok, detail) in enumerate(results, 1):
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        print(f" {i:>2} \u2502 {name:<32} \u2502 {status:<6} \u2502 {detail}")

    print("\u2550" * 68)
    print(f"Results: {passed}/{len(results)} passed")

    if passed < len(results):
        print(f"\n{len(results) - passed} test(s) FAILED. Review output above.")
    else:
        print("\nAll tests passed.")

    conn.close()


if __name__ == "__main__":
    main()
