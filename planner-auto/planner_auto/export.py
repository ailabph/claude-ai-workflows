"""
Artifact export for planner-auto sessions.

Exports session data to disk: chat.csv, context-summary.md, plan-draft-<N>.md,
and (Plan 2) interleaved review+plan artifacts plus .kafra handoff.

Overwrites on re-export (idempotent).
"""

import csv
import json
import logging
import os
from typing import Optional

from planner_auto.db import (
    get_all_plan_drafts,
    get_context_entries,
    get_messages,
    get_session_config,
)
from planner_auto.git_utils import discover_repo_root

logger = logging.getLogger("planner-auto.export")


DEFAULT_SESSIONS_DIR = os.path.join(os.path.expanduser("~"), ".planner-auto", "sessions")


def export_session(
    session_id: str,
    conn,
    output_dir: Optional[str] = None,
) -> list[str]:
    """Export session artifacts to disk.

    Creates the output directory and writes:
    - chat.csv: message history (id, timestamp, role, content) ordered by id
    - context-summary.md: context entries grouped by type
    - plan-draft-<N>.md: one file per plan draft

    Overwrites existing files on re-export (idempotent).

    Args:
        session_id: Session ID.
        conn: SQLite connection.
        output_dir: Override output directory. Defaults to
                    ~/.planner-auto/sessions/<session-id>/

    Returns:
        List of file paths created.
    """
    if output_dir is None:
        output_dir = os.path.join(DEFAULT_SESSIONS_DIR, session_id)

    os.makedirs(output_dir, exist_ok=True)

    created_files = []

    # Export chat.csv
    chat_path = _export_chat_csv(session_id, conn, output_dir)
    created_files.append(chat_path)

    # Export context-summary.md
    context_path = _export_context_summary(session_id, conn, output_dir)
    created_files.append(context_path)

    # Export plan drafts
    draft_paths = _export_plan_drafts(session_id, conn, output_dir)
    created_files.extend(draft_paths)

    return created_files


def _export_chat_csv(session_id: str, conn, output_dir: str) -> str:
    """Export messages to chat.csv ordered by id."""
    messages = get_messages(conn, session_id)
    path = os.path.join(output_dir, "chat.csv")

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "timestamp", "role", "content"])
        for msg in messages:
            writer.writerow([
                msg["id"],
                msg["created_at"],
                msg["role"],
                msg["content"],
            ])

    return path


def _export_context_summary(session_id: str, conn, output_dir: str) -> str:
    """Export context entries to context-summary.md grouped by type."""
    entries = get_context_entries(conn, session_id)
    path = os.path.join(output_dir, "context-summary.md")

    # Group by type
    grouped: dict[str, list] = {}
    for entry in entries:
        entry_type = entry["entry_type"]
        if entry_type not in grouped:
            grouped[entry_type] = []
        grouped[entry_type].append(entry)

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Context Summary — Session {session_id}\n\n")

        for entry_type in ["file", "note", "synthesis"]:
            if entry_type not in grouped:
                continue
            f.write(f"## {entry_type.capitalize()}s\n\n")
            for entry in grouped[entry_type]:
                f.write(f"### {entry['entry_key']}\n\n")
                f.write(f"{entry['content']}\n\n")

    return path


def _export_plan_drafts(session_id: str, conn, output_dir: str) -> list[str]:
    """Export one file per plan draft as plan-draft-<N>.md."""
    drafts = get_all_plan_drafts(conn, session_id)
    paths = []

    for draft in drafts:
        filename = f"plan-draft-{draft['draft_number']}.md"
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(draft["content"])
        paths.append(path)

    return paths


# ---------------------------------------------------------------------------
# Plan 2: review artifact export and .kafra handoff
# ---------------------------------------------------------------------------

def export_review_artifacts(
    session_id: str,
    conn,
    output_dir: Optional[str] = None,
    fast_mode: bool = False,
) -> list[str]:
    """Export interleaved review + plan artifact files from the DB.

    Naming convention (matches what the engine writes during execution):

    - ``a-01-plan.md``                — initial plan draft (first draft in DB)
    - ``a-{2*N:02d}-review.md``       — review for round N
    - ``a-{2*N+1:02d}-plan.md``       — plan revision after round N
    - ``plan-final.md``               — latest / final plan draft

    When ``fast_mode=True`` every file is prefixed with ``[FAST MODE]\\n\\n``.

    Args:
        session_id: Session ID.
        conn: SQLite connection.
        output_dir: Override output directory.  Defaults to
                    ``~/.planner-auto/sessions/<session-id>/``.
        fast_mode: If ``True``, prepend ``[FAST MODE]`` header to each file.

    Returns:
        List of file paths written.
    """
    if output_dir is None:
        output_dir = os.path.join(DEFAULT_SESSIONS_DIR, session_id)
    os.makedirs(output_dir, exist_ok=True)

    fast_header = "[FAST MODE]\n\n" if fast_mode else ""
    paths: list[str] = []

    # Query Plan-2 reviews (round_number IS NOT NULL), ordered by round.
    reviews = conn.execute(
        "SELECT * FROM reviews WHERE session_id=? AND round_number IS NOT NULL "
        "ORDER BY round_number ASC",
        (session_id,),
    ).fetchall()

    drafts = get_all_plan_drafts(conn, session_id)

    # Initial plan — first draft in DB.
    if drafts:
        init_path = os.path.join(output_dir, "a-01-plan.md")
        with open(init_path, "w", encoding="utf-8") as f:
            f.write(fast_header + drafts[0]["content"])
        paths.append(init_path)

    # Interleave reviews with plan revisions.
    for rev in reviews:
        round_num = rev["round_number"]

        # Review file.
        review_path = os.path.join(output_dir, f"a-{2 * round_num:02d}-review.md")
        with open(review_path, "w", encoding="utf-8") as f:
            f.write(fast_header + _format_review_export(rev))
        paths.append(review_path)

        # Plan revision: draft at index round_num in the drafts list.
        # drafts[0] = initial plan; drafts[1] = revision after round 1; etc.
        if round_num < len(drafts):
            plan_path = os.path.join(output_dir, f"a-{2 * round_num + 1:02d}-plan.md")
            with open(plan_path, "w", encoding="utf-8") as f:
                f.write(fast_header + drafts[round_num]["content"])
            paths.append(plan_path)

    # Final plan (latest draft).
    if drafts:
        final_path = os.path.join(output_dir, "plan-final.md")
        with open(final_path, "w", encoding="utf-8") as f:
            f.write(fast_header + drafts[-1]["content"])
        paths.append(final_path)

    return paths


def kafra_handoff(
    session_id: str,
    conn,
    final_plan_text: str,
    project: str,
    repo_root: Optional[str] = None,
) -> Optional[str]:
    """Copy the final plan to ``{repo_root}/.kafra/a-01-plans/{project}.md``.

    Discovery order for repo root:

    1. Explicit ``repo_root`` argument (highest priority).
    2. ``repo_root`` stored in the session's ``session_config.config_json``.
    3. ``discover_repo_root()`` from the current working directory (fallback).

    Args:
        session_id: Session ID (used for config lookup).
        conn: SQLite connection.
        final_plan_text: Content of the final plan to write.
        project: Project name (used as the filename).
        repo_root: Explicit repository root override.

    Returns:
        Absolute path to the written file, or ``None`` if no repo root was
        found (handoff skipped with a warning log).
    """
    # Step 1: explicit argument already set.
    if repo_root is None:
        # Step 2: session config.
        config_row = get_session_config(conn, session_id)
        if config_row:
            try:
                cfg = json.loads(config_row["config_json"])
                repo_root = cfg.get("repo_root")
            except (json.JSONDecodeError, TypeError):
                pass

    # Step 3: cwd fallback discovery.
    if repo_root is None:
        repo_root = discover_repo_root()

    if repo_root is None:
        logger.warning(
            "kafra_handoff: no repo root found — skipping handoff for session %s",
            session_id,
        )
        return None

    kafra_dir = os.path.join(repo_root, ".kafra", "a-01-plans")
    os.makedirs(kafra_dir, exist_ok=True)
    dest = os.path.join(kafra_dir, f"{project}.md")

    with open(dest, "w", encoding="utf-8") as f:
        f.write(final_plan_text)

    logger.info("kafra_handoff: wrote %s", dest)
    return dest


def _format_review_export(review_row) -> str:
    """Format a DB review row as a Markdown artifact string."""
    verdict = review_row["verdict"] or "UNKNOWN"
    round_num = review_row["round_number"] or "?"

    lines: list[str] = [
        f"# Review — Round {round_num}",
        "",
        f"**Verdict:** {verdict}",
        "",
    ]

    if review_row["summary"]:
        lines += ["## Summary", "", review_row["summary"], ""]

    issues_json = review_row["issues_json"]
    if issues_json:
        try:
            issues = json.loads(issues_json)
            if issues:
                lines += ["## Issues", ""]
                for idx, issue in enumerate(issues, 1):
                    sev = issue.get("severity", "major").upper()
                    desc = issue.get("description", "")
                    rationale = issue.get("rationale", "")
                    guidance = issue.get("resolution_guidance", "")
                    target = issue.get("target_section", "")
                    lines.append(f"### {idx}. [{sev}] {desc}")
                    if rationale:
                        lines.append(f"**Rationale:** {rationale}")
                    if guidance:
                        lines.append(f"**Guidance:** {guidance}")
                    if target:
                        lines.append(f"**Section:** {target}")
                    lines.append("")
        except (json.JSONDecodeError, TypeError):
            pass

    return "\n".join(lines)
