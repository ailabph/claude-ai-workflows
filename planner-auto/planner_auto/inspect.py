"""
DB inspection helpers for planner-auto CLI.

Each function accepts an open SQLite connection and a session_id,
queries the database, and returns a formatted string ready to print.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from planner_auto.db import (
    CURRENT_SCHEMA_VERSION,
    get_all_dispositions,
    get_all_plan_drafts,
    get_context_entries,
    get_dispositions,
    get_messages,
    get_open_blockers,
    get_review_by_round,
    get_schema_version,
    get_session,
    get_session_config,
)
from planner_auto.loop.history import build_review_context

logger = logging.getLogger(__name__)

_SECURITY_WARNING = (
    "⚠ Output may contain repository content and API responses. "
    "Do not share without redaction."
)


# ---------------------------------------------------------------------------
# Public formatting functions
# ---------------------------------------------------------------------------

def format_reviews_table(conn, session_id: str) -> str:
    """Return a formatted table of all Plan-2 reviews for a session.

    Columns: Round | Verdict | Issues | Model | Cost | Tokens | Created
    """
    rows = conn.execute(
        "SELECT * FROM reviews WHERE session_id=? AND round_number IS NOT NULL "
        "ORDER BY round_number ASC",
        (session_id,),
    ).fetchall()

    if not rows:
        return f"No reviews found for session {session_id}."

    # Header
    lines = [
        f"{'Rnd':<4} {'Verdict':<8} {'Issues':<7} {'Model':<28} {'Cost':>8} {'In/Out':>11} {'Created'}",
        "-" * 85,
    ]

    for r in rows:
        round_num = r["round_number"] or "-"
        verdict = (r["verdict"] or "?")[:8]
        cost_str = f"${r['cost']:.4f}" if r["cost"] is not None else "-"
        model = (r["reviewer_model"] or "-")[:28]

        # Count issues from JSON
        issue_count = 0
        if r["issues_json"]:
            try:
                issue_count = len(json.loads(r["issues_json"]))
            except (json.JSONDecodeError, TypeError):
                issue_count = -1

        tok_in = r["input_tokens"] if r["input_tokens"] is not None else "-"
        tok_out = r["output_tokens"] if r["output_tokens"] is not None else "-"
        tok_str = f"{tok_in}/{tok_out}"

        created = (r["created_at"] or "")[:19]
        lines.append(
            f"{str(round_num):<4} {verdict:<8} {str(issue_count):<7} {model:<28} "
            f"{cost_str:>8} {tok_str:>11} {created}"
        )

    return "\n".join(lines)


def format_dispositions(conn, session_id: str, round_num: Optional[int] = None) -> str:
    """Return a formatted list of issue dispositions.

    If *round_num* is given, shows only that round's dispositions.
    Otherwise shows all dispositions across all rounds.
    """
    if round_num is not None:
        review = get_review_by_round(conn, session_id, round_num)
        if review is None:
            return f"No review found for session {session_id}, round {round_num}."
        disps = get_dispositions(conn, review["id"])
        issues_json = review["issues_json"]
    else:
        disps = get_all_dispositions(conn, session_id)
        issues_json = None

    if not disps:
        label = f"round {round_num}" if round_num is not None else "any round"
        return f"No dispositions found for session {session_id} in {label}."

    lines = [
        f"{'Rnd':<4} {'Idx':<4} {'Disp':<12} {'Rationale':<40} Description",
        "-" * 100,
    ]

    for d in disps:
        rnum = d.get("round_number", round_num or "?")
        idx = d["issue_index"]
        disp = d["disposition"]
        rationale = (d.get("rationale") or "")[:40]

        # Try to pull issue description from the review for this round
        desc = ""
        try:
            if round_num is not None:
                # issues_json already fetched for single-round mode
                if issues_json:
                    issues = json.loads(issues_json)
                    if 0 <= idx < len(issues):
                        desc = issues[idx].get("description", "")[:60]
            else:
                # Multi-round: look up each review's issues_json
                rev = get_review_by_round(conn, session_id, rnum)
                if rev and rev["issues_json"]:
                    issues = json.loads(rev["issues_json"])
                    if 0 <= idx < len(issues):
                        desc = issues[idx].get("description", "")[:60]
        except (json.JSONDecodeError, TypeError, KeyError):
            desc = ""

        lines.append(
            f"{str(rnum):<4} {str(idx):<4} {disp:<12} {rationale:<40} {desc}"
        )

    return "\n".join(lines)


def format_config(conn, session_id: str) -> str:
    """Return a formatted display of the latest session config snapshot."""
    config_row = get_session_config(conn, session_id)
    if config_row is None:
        return f"No config found for session {session_id}."

    try:
        cfg = json.loads(config_row["config_json"])
    except (json.JSONDecodeError, TypeError):
        return f"Config for session {session_id} (unparseable JSON):\n{config_row['config_json']}"

    lines = [f"Session config for {session_id} (snapshot id={config_row['id']}):"]
    for key, value in sorted(cfg.items()):
        lines.append(f"  {key}: {value!r}")
    return "\n".join(lines)


def reconstruct_history(conn, session_id: str, round_num: int) -> str:
    """Reconstruct the review history context for a given round.

    Calls ``build_review_context()`` from loop/history.py so the output
    matches exactly what the engine sends to the reviewer.

    Note: Output is reconstructed from DB state, not stored separately.

    Returns the context string, or an explanation if none exists.
    """
    if round_num <= 1:
        return (
            f"Round {round_num}: no history context (first round has no prior history).\n"
            "Note: output is reconstructed from DB state, not stored."
        )

    context = build_review_context(conn, session_id, current_round=round_num)
    if context is None:
        return (
            f"No history context available for round {round_num} "
            f"(session {session_id}). The previous round's review may be missing.\n"
            "Note: output is reconstructed from DB state, not stored."
        )

    header = "Note: output is reconstructed from DB state, not stored.\n\n"
    return header + context


def format_raw_response(conn, session_id: str, round_num: int) -> str:
    """Return the raw reviewer response for a given round.

    Prepends the security warning since this may contain API response text.
    """
    review = get_review_by_round(conn, session_id, round_num)
    if review is None:
        return f"No review found for session {session_id}, round {round_num}."

    raw = review["raw_response"]
    if not raw:
        return f"No raw response stored for session {session_id}, round {round_num}."

    lines = [
        _SECURITY_WARNING,
        "",
        f"--- Raw response for session {session_id}, round {round_num} ---",
        "",
        raw,
    ]
    return "\n".join(lines)


def dump_session_json(conn, session_id: str) -> str:
    """Return a full JSON dump of all session data across all tables.

    Includes: session metadata, messages, context entries, plan drafts,
    reviews, dispositions, blockers, config, and schema version.

    The security warning is printed to stderr by the caller; the return
    value is pure JSON so it can be piped to ``jq`` or similar tools.
    """
    session = get_session(conn, session_id)
    if session is None:
        return json.dumps({"error": f"Session not found: {session_id}"}, indent=2)

    messages = get_messages(conn, session_id)
    context_entries = get_context_entries(conn, session_id)
    drafts = get_all_plan_drafts(conn, session_id)
    config_row = get_session_config(conn, session_id)
    all_disps = get_all_dispositions(conn, session_id)

    reviews = conn.execute(
        "SELECT * FROM reviews WHERE session_id=? ORDER BY round_number ASC",
        (session_id,),
    ).fetchall()

    # Blockers: open + resolved
    open_blockers = get_open_blockers(conn, session_id)
    resolved_blockers = conn.execute(
        "SELECT * FROM blockers WHERE session_id = ? AND status = 'resolved' "
        "ORDER BY resolved_at ASC",
        (session_id,),
    ).fetchall()

    schema_ver = get_schema_version(conn)

    data = {
        "schema_version": schema_ver,
        "session": dict(session),
        "config": json.loads(config_row["config_json"]) if config_row else None,
        "messages": [dict(m) for m in messages],
        "context_entries": [dict(e) for e in context_entries],
        "plan_drafts": [dict(d) for d in drafts],
        "reviews": [dict(r) for r in reviews],
        "dispositions": all_disps,
        "blockers": {
            "open": [dict(b) for b in open_blockers],
            "resolved": [dict(b) for b in resolved_blockers],
        },
    }

    return json.dumps(data, indent=2, default=str)
