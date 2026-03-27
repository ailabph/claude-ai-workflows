"""
Artifact export for planner-auto sessions.

Exports session data to disk: chat.csv, context-summary.md, and plan-draft-<N>.md files.
Overwrites on re-export (idempotent).
"""

import csv
import io
import os
from typing import Optional

from planner_auto.db import (
    get_all_plan_drafts,
    get_context_entries,
    get_messages,
)


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
