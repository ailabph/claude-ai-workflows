#!/usr/bin/env python3
"""POC 3b: Artifact Export from DB

Generate audit artifacts from a populated SQLite database.

Steps:
  1. Create and populate a test DB (reuse POC 3a schema + test data)
  2. Export functions:
     a. export_chat_csv(session_id, output_dir)
        - Query messages table ordered by timestamp
        - Write CSV: timestamp, role, content
     b. export_context_summary(session_id, output_dir)
        - Query context_entries table
        - Generate markdown summary grouped by entry_type
     c. export_plan_drafts(session_id, output_dir)
        - Query plan_drafts ordered by draft_number
        - Write a-01-plan.md, a-03-plan.md, a-05-plan.md, etc.
     d. export_reviews(session_id, output_dir)
        - Query reviews ordered by review_number
        - Write a-02-review.md, a-04-review.md, etc.
     e. export_final_plan(session_id, output_dir)
        - Find the GO-verdict review, get corresponding plan draft
        - Write a-<N>-plan-final.md
  3. Run all exports to a temp directory
  4. Verify file existence, naming, and content
  5. Run exports again, verify idempotency (files identical)
  6. Print summary: files created, sizes, paths

Usage:
  python scripts/poc/planner-auto/poc_artifact_export.py
  python scripts/poc/planner-auto/poc_artifact_export.py --output-dir /tmp/poc_export
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import tempfile
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# POC 3a imports
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent))
from poc_session_db import (
    create_schema,
    create_session,
    update_session_phase,
    update_session_status,
    add_message,
    add_context_entry,
    add_plan_draft,
    add_review,
    get_messages,
    get_context_entries,
    get_all_reviews,
    get_session,
)


# ---------------------------------------------------------------------------
# Populate test DB
# ---------------------------------------------------------------------------

def populate_test_db(conn: sqlite3.Connection) -> str:
    """Create a fully populated session for export testing.

    Creates a session with 2 files + 1 entity + 1 decision context entries,
    5 messages, 2 plan drafts, and 2 reviews (NO_GO then GO).

    Returns the session_id.
    """
    sid = create_session(conn, "export-poc")

    # Context entries: 2 files, 1 entity, 1 decision
    add_context_entry(conn, sid, "file", "src/main.py", "def main(): ...")
    add_context_entry(conn, sid, "file", "src/models.py", "class User: ...")
    add_context_entry(conn, sid, "entity", "User", "Core domain entity with email, name, role fields")
    add_context_entry(conn, sid, "decision", "auth_approach", "Use JWT tokens for stateless authentication")

    update_session_phase(conn, sid, "context")

    # 5 messages
    add_message(conn, sid, "user", "I've loaded the project files for context.")
    add_message(
        conn, sid, "planner",
        "I see a Flask app with a User model. What feature should we build?",
    )
    add_message(
        conn, sid, "user",
        "Add user registration with email validation, password hashing, and rate limiting.",
    )
    add_message(
        conn, sid, "planner",
        "Should the endpoint return a JWT on successful registration, or require a separate login?",
    )
    add_message(conn, sid, "user", "Require separate login. Registration just creates the account.")

    update_session_phase(conn, sid, "discussion")
    update_session_phase(conn, sid, "planning")

    # Plan draft 1
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
        "## Milestone 3: Tests\n"
        "- Unit tests for email validation\n"
        "- Integration test for registration flow\n"
        "- Edge cases: empty fields, SQL injection attempts"
    )
    add_plan_draft(conn, sid, 1, plan_v1)

    update_session_phase(conn, sid, "review")

    # Review 1: NO_GO
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
    add_review(
        conn, sid, 1, "NO_GO", review1_issues,
        "Critical: no rate limiting; Major: no password policy",
        "NO_GO. Critical gap: no rate limiting on the public registration endpoint. "
        "Also missing password strength requirements.",
    )

    # Plan draft 2 (revised)
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
        "- Return 201 on success, 409 on duplicate, 429 on rate limit\n\n"
        "## Milestone 3: Tests & Validation\n"
        "- Unit tests for email validation and password policy\n"
        "- Integration test for registration flow (success + failures)\n"
        "- Rate limiting integration test\n"
        "- Edge cases: empty fields, SQL injection, long inputs"
    )
    add_plan_draft(conn, sid, 2, plan_v2)

    # Review 2: GO
    review2_issues = json.dumps([])
    add_review(
        conn, sid, 2, "GO", review2_issues,
        "Plan approved. All issues addressed.",
        "GO. The revised plan addresses both issues: rate limiting is now included "
        "in Milestone 2, and password strength requirements are defined.",
    )

    update_session_status(conn, sid, "complete")

    return sid


# ---------------------------------------------------------------------------
# Export functions
# ---------------------------------------------------------------------------

def export_chat_csv(conn: sqlite3.Connection, session_id: str, output_dir: Path) -> Path:
    """Export messages as a CSV file with columns: timestamp, role, content.

    Returns the path to the written file.
    """
    messages = get_messages(conn, session_id)
    out_path = output_dir / "chat.csv"

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(["timestamp", "role", "content"])
        for msg in messages:
            writer.writerow([msg["timestamp"], msg["role"], msg["content"]])

    return out_path


def export_context_summary(conn: sqlite3.Connection, session_id: str, output_dir: Path) -> Path:
    """Export context entries as a markdown summary grouped by entry_type.

    Returns the path to the written file.
    """
    entries = get_context_entries(conn, session_id)

    # Group by entry_type preserving insertion order
    grouped: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        grouped[entry["entry_type"]].append(entry)

    lines: list[str] = ["# Context Summary", ""]

    # Capitalize entry_type for section heading (handle irregular plurals)
    _plurals = {"entity": "Entities", "file": "Files", "decision": "Decisions"}
    for entry_type, items in grouped.items():
        heading = _plurals.get(entry_type, entry_type.capitalize() + "s")
        lines.append(f"## {heading}")
        for item in items:
            lines.append(f"- **{item['key']}**: {item['value']}")
        lines.append("")

    out_path = output_dir / "context-summary.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def export_plan_drafts(conn: sqlite3.Connection, session_id: str, output_dir: Path) -> list[Path]:
    """Export all plan drafts with v1.1 naming convention.

    Draft N -> a-{2*N-1:02d}-plan.md

    Returns list of written file paths.
    """
    rows = conn.execute(
        "SELECT * FROM plan_drafts WHERE session_id = ? ORDER BY draft_number",
        (session_id,),
    ).fetchall()

    paths: list[Path] = []
    for row in rows:
        draft_num = row["draft_number"]
        filename = f"a-{2 * draft_num - 1:02d}-plan.md"
        out_path = output_dir / filename
        out_path.write_text(row["content"], encoding="utf-8")
        paths.append(out_path)

    return paths


def export_reviews(conn: sqlite3.Connection, session_id: str, output_dir: Path) -> list[Path]:
    """Export all reviews with v1.1 naming convention.

    Review N -> a-{2*N:02d}-review.md

    Returns list of written file paths.
    """
    reviews = get_all_reviews(conn, session_id)

    paths: list[Path] = []
    for review in reviews:
        review_num = review["review_number"]
        filename = f"a-{2 * review_num:02d}-review.md"

        lines: list[str] = [
            f"# Review {review_num}",
            "",
            f"**Verdict:** {review['verdict']}",
            "",
            "## Summary",
            review["summary"],
            "",
        ]

        # Parse issues_json and format
        issues = json.loads(review["issues_json"])
        if issues:
            lines.append("## Issues")
            for i, issue in enumerate(issues, 1):
                severity = issue.get("severity", "unknown")
                description = issue.get("description", "")
                rationale = issue.get("rationale", "")
                lines.append(f"{i}. **[{severity}]** {description}")
                if rationale:
                    lines.append(f"   - Rationale: {rationale}")
            lines.append("")

        out_path = output_dir / filename
        out_path.write_text("\n".join(lines), encoding="utf-8")
        paths.append(out_path)

    return paths


def export_final_plan(conn: sqlite3.Connection, session_id: str, output_dir: Path) -> Path | None:
    """Export the final approved plan.

    Finds the first review with verdict='GO', then gets the plan draft
    with the highest draft_number up to that review's review_number.

    Returns path to the written file, or None if no GO review exists.
    """
    reviews = get_all_reviews(conn, session_id)

    go_review = None
    for review in reviews:
        if review["verdict"] == "GO":
            go_review = review
            break

    if go_review is None:
        return None

    # Get the plan draft with highest draft_number <= go_review's review_number
    # Since drafts and reviews interleave: draft N is reviewed by review N,
    # so the corresponding draft_number == review_number
    row = conn.execute(
        "SELECT * FROM plan_drafts WHERE session_id = ? AND draft_number <= ? "
        "ORDER BY draft_number DESC LIMIT 1",
        (session_id, go_review["review_number"]),
    ).fetchone()

    if row is None:
        return None

    draft_num = row["draft_number"]
    filename = f"a-{2 * draft_num - 1:02d}-plan-final.md"
    out_path = output_dir / filename
    out_path.write_text(row["content"], encoding="utf-8")
    return out_path


def export_all(conn: sqlite3.Connection, session_id: str, output_dir: Path) -> list[Path]:
    """Run all export functions and return all generated file paths."""
    output_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []

    paths.append(export_chat_csv(conn, session_id, output_dir))
    paths.append(export_context_summary(conn, session_id, output_dir))
    paths.extend(export_plan_drafts(conn, session_id, output_dir))
    paths.extend(export_reviews(conn, session_id, output_dir))

    final = export_final_plan(conn, session_id, output_dir)
    if final is not None:
        paths.append(final)

    return paths


# ---------------------------------------------------------------------------
# Test function
# ---------------------------------------------------------------------------

def run_export_test(
    conn: sqlite3.Connection,
    session_id: str,
    output_dir: Path,
) -> list[tuple[str, bool, str]]:
    """Run export_all and verify outputs.

    Returns a list of (test_name, passed, detail) tuples.
    """
    results: list[tuple[str, bool, str]] = []

    # --- First export run ---
    paths = export_all(conn, session_id, output_dir)

    # 1. chat.csv exists and is valid CSV with 5 data rows
    chat_path = output_dir / "chat.csv"
    chat_exists = chat_path.exists()
    chat_row_count = 0
    if chat_exists:
        with chat_path.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
            # First row is header, rest are data
            chat_row_count = len(rows) - 1
    results.append((
        "chat_csv_exists",
        chat_exists,
        str(chat_path) if chat_exists else "not found",
    ))
    results.append((
        "chat_csv_row_count",
        chat_row_count == 5,
        f"{chat_row_count} data rows (expected 5)",
    ))

    # 2. context-summary.md exists and has expected sections
    ctx_path = output_dir / "context-summary.md"
    ctx_exists = ctx_path.exists()
    ctx_content = ctx_path.read_text(encoding="utf-8") if ctx_exists else ""
    has_files_section = "## Files" in ctx_content
    has_entities_section = "## Entities" in ctx_content
    results.append((
        "context_summary_exists",
        ctx_exists,
        str(ctx_path) if ctx_exists else "not found",
    ))
    results.append((
        "context_summary_sections",
        has_files_section and has_entities_section,
        f"Files={'yes' if has_files_section else 'no'}, "
        f"Entities={'yes' if has_entities_section else 'no'}",
    ))

    # 3. a-01-plan.md exists and contains plan content
    plan1_path = output_dir / "a-01-plan.md"
    plan1_exists = plan1_path.exists()
    plan1_content = plan1_path.read_text(encoding="utf-8") if plan1_exists else ""
    results.append((
        "a-01-plan_exists",
        plan1_exists and len(plan1_content) > 0,
        f"{len(plan1_content)} bytes" if plan1_exists else "not found",
    ))

    # 4. a-02-review.md exists, contains NO_GO and issue descriptions
    review1_path = output_dir / "a-02-review.md"
    review1_exists = review1_path.exists()
    review1_content = review1_path.read_text(encoding="utf-8") if review1_exists else ""
    has_nogo = "NO_GO" in review1_content
    has_rate_limit = "rate limiting" in review1_content.lower()
    results.append((
        "a-02-review_exists",
        review1_exists,
        str(review1_path) if review1_exists else "not found",
    ))
    results.append((
        "a-02-review_content",
        has_nogo and has_rate_limit,
        f"NO_GO={'yes' if has_nogo else 'no'}, "
        f"rate_limiting={'yes' if has_rate_limit else 'no'}",
    ))

    # 5. a-03-plan.md exists and contains revised plan content
    plan2_path = output_dir / "a-03-plan.md"
    plan2_exists = plan2_path.exists()
    plan2_content = plan2_path.read_text(encoding="utf-8") if plan2_exists else ""
    results.append((
        "a-03-plan_exists",
        plan2_exists and len(plan2_content) > 0,
        f"{len(plan2_content)} bytes" if plan2_exists else "not found",
    ))

    # 6. a-04-review.md exists and contains GO
    review2_path = output_dir / "a-04-review.md"
    review2_exists = review2_path.exists()
    review2_content = review2_path.read_text(encoding="utf-8") if review2_exists else ""
    has_go = "GO" in review2_content
    results.append((
        "a-04-review_exists",
        review2_exists,
        str(review2_path) if review2_exists else "not found",
    ))
    results.append((
        "a-04-review_go_verdict",
        review2_exists and has_go,
        f"GO={'yes' if has_go else 'no'}",
    ))

    # 7. a-03-plan-final.md exists and matches a-03-plan.md content
    final_path = output_dir / "a-03-plan-final.md"
    final_exists = final_path.exists()
    final_content = final_path.read_text(encoding="utf-8") if final_exists else ""
    content_matches = final_content == plan2_content and len(final_content) > 0
    results.append((
        "a-03-plan-final_exists",
        final_exists,
        str(final_path) if final_exists else "not found",
    ))
    results.append((
        "final_plan_matches_draft",
        content_matches,
        f"match={'yes' if content_matches else 'no'} "
        f"({len(final_content)} vs {len(plan2_content)} bytes)",
    ))

    # 8. File naming convention check: no gaps, correct numbering
    expected_files = {
        "chat.csv", "context-summary.md",
        "a-01-plan.md", "a-02-review.md",
        "a-03-plan.md", "a-04-review.md",
        "a-03-plan-final.md",
    }
    actual_files = {p.name for p in paths}
    naming_ok = actual_files == expected_files
    results.append((
        "file_naming_convention",
        naming_ok,
        f"expected={sorted(expected_files)}, actual={sorted(actual_files)}"
        if not naming_ok
        else f"{len(expected_files)} files with correct names",
    ))

    # --- Second export run (idempotency) ---
    # Read all files from first export
    first_contents: dict[str, bytes] = {}
    for p in paths:
        first_contents[p.name] = p.read_bytes()

    # Run export again
    paths2 = export_all(conn, session_id, output_dir)

    # Read all files from second export
    second_contents: dict[str, bytes] = {}
    for p in paths2:
        second_contents[p.name] = p.read_bytes()

    idempotent = first_contents == second_contents
    diff_files = []
    if not idempotent:
        for name in first_contents:
            if name in second_contents and first_contents[name] != second_contents[name]:
                diff_files.append(name)
        for name in second_contents:
            if name not in first_contents:
                diff_files.append(f"+{name}")
        for name in first_contents:
            if name not in second_contents:
                diff_files.append(f"-{name}")

    results.append((
        "idempotency",
        idempotent,
        "identical on re-export" if idempotent else f"differs: {diff_files}",
    ))

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="POC 3b: Artifact Export from DB")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for exported files (default: temp directory)",
    )
    args = parser.parse_args()

    if args.output_dir is not None:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(tempfile.mkdtemp(prefix="poc_export_"))

    output_dir.mkdir(parents=True, exist_ok=True)

    # Create in-memory DB and populate
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    session_id = populate_test_db(conn)

    # Run tests
    results = run_export_test(conn, session_id, output_dir)

    # --- Print results table ---
    print("POC 3b: Artifact Export from DB")
    print("\u2550" * 68)

    header = f" {'#':>2} \u2502 {'Test':<30} \u2502 {'Result':<6} \u2502 Detail"
    separator = f"{'':->4}\u253c{'':->32}\u253c{'':->8}\u253c{'':->22}"

    print(header)
    print(separator)

    passed = 0
    for i, (name, ok, detail) in enumerate(results, 1):
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        print(f" {i:>2} \u2502 {name:<30} \u2502 {status:<6} \u2502 {detail}")

    print("\u2550" * 68)
    print(f"Results: {passed}/{len(results)} passed")

    # --- File listing ---
    print("\nExported files:")
    for p in sorted(output_dir.iterdir()):
        size = p.stat().st_size
        print(f"  {p.name:<30} ({size:,} bytes)")

    print(f"\nOutput directory: {output_dir}")

    if passed < len(results):
        print(f"\n{len(results) - passed} test(s) FAILED. Review output above.")
    else:
        print("\nAll tests passed.")

    conn.close()


if __name__ == "__main__":
    main()
