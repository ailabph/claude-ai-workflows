"""Review-history context builder and severity filter for the loop engine.

``build_review_context`` constructs the GPT context string for review round N
by pulling the previous round's verdict, issues, and dispositions from the
DB, plus a cumulative list of ALL DEFER dispositions from every prior round.
This prevents the reviewer from re-raising intentionally deferred issues.

``filter_issues`` selects issues whose severity is in the configured set,
defaulting to ``["critical", "major"]``.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from planner_auto.db import (
    get_all_dispositions,
    get_dispositions,
    get_review_by_round,
)
from planner_auto.reviewer.contract import ReviewIssue, Severity

logger = logging.getLogger(__name__)

# Maximum characters of previous plan text to include in history context.
_PREV_PLAN_CAP = 5000


def filter_issues(
    issues: list[ReviewIssue],
    severity_levels: list[str] | None = None,
) -> list[ReviewIssue]:
    """Return the subset of *issues* whose severity matches *severity_levels*.

    All issues are stored in the DB regardless of this filter; only the
    filtered subset is forwarded to the revision prompt.

    Args:
        issues: Full list of issues from a ``ReviewerResponse``.
        severity_levels: Severities to keep.  Defaults to
            ``["critical", "major"]``.  Values are compared
            case-insensitively.

    Returns:
        Filtered list of :class:`ReviewIssue` objects.
    """
    if severity_levels is None:
        severity_levels = ["critical", "major"]
    levels = {s.lower() for s in severity_levels}
    return [i for i in issues if i.severity.value in levels]


def build_review_context(
    conn,
    session_id: str,
    current_round: int,
    prev_plan_text: Optional[str] = None,
) -> Optional[str]:
    """Build the history context string for the current review round.

    Returns ``None`` for round 1 (no prior history).

    For round ≥ 2 constructs a string with two sections:

    **Section A — Previous round context**
      Previous plan text (capped at 5 000 chars), previous review verdict,
      issues, and per-issue dispositions (ACCEPT / DEFER / REJECT).

    **Section B — Cumulative deferred context**
      ALL DEFER dispositions from every prior round combined into a single
      deduplicated list.  The reviewer is instructed never to re-raise
      deferred items in any form.

    Args:
        conn: SQLite connection.
        session_id: Session ID.
        current_round: 1-based round number for the review about to run.
        prev_plan_text: Text of the plan that was reviewed in the previous
            round.  Used directly when available; a DB fallback is attempted
            otherwise.

    Returns:
        Formatted context string, or ``None`` if ``current_round == 1``.
    """
    if current_round <= 1:
        return None

    prev_round = current_round - 1
    prev_review = get_review_by_round(conn, session_id, prev_round)
    if prev_review is None:
        logger.warning(
            "No review found for round %d (session %s) — skipping history context",
            prev_round,
            session_id,
        )
        return None

    review_id = prev_review["id"]
    verdict = prev_review["verdict"] or "UNKNOWN"
    summary = prev_review["summary"] or ""

    # Deserialise issues from the stored JSON.
    issues_raw: list[dict] = []
    if prev_review["issues_json"]:
        try:
            issues_raw = json.loads(prev_review["issues_json"])
        except (json.JSONDecodeError, TypeError):
            pass

    # Dispositions for the previous review (may be empty if validate_feedback
    # was disabled for that round).
    dispositions: list[dict] = get_dispositions(conn, review_id)
    disp_by_index: dict[int, dict] = {d["issue_index"]: d for d in dispositions}

    # ---- Section A: Previous round context --------------------------------
    lines: list[str] = []
    lines.append(f"## Previous Round (Round {prev_round}) Context\n")

    # Previous plan (capped).
    if prev_plan_text:
        plan_snippet = prev_plan_text[:_PREV_PLAN_CAP]
        if len(prev_plan_text) > _PREV_PLAN_CAP:
            plan_snippet += "\n... [truncated]"
        lines.append(f"### Plan reviewed in round {prev_round}:\n")
        lines.append(plan_snippet)
        lines.append("")

    # Previous verdict + summary.
    lines.append(f"### Round {prev_round} verdict: {verdict}")
    if summary:
        lines.append(f"Summary: {summary}")
    lines.append("")

    # Previous issues with dispositions.
    if issues_raw:
        lines.append(f"### Round {prev_round} issues:")
        for idx, issue in enumerate(issues_raw):
            sev = issue.get("severity", "major")
            desc = issue.get("description", "")
            disp_info = ""
            if idx in disp_by_index:
                d = disp_by_index[idx]
                disp_info = f" → {d['disposition']}"
                if d.get("rationale"):
                    disp_info += f" ({d['rationale']})"
            lines.append(f"  [{sev.upper()}] {desc}{disp_info}")
        lines.append("")

    # ---- Section B: Cumulative deferred context ---------------------------
    all_disps = get_all_dispositions(conn, session_id)
    defer_disps = [d for d in all_disps if d["disposition"] == "DEFER"]

    if defer_disps:
        lines.append("## Cumulative Deferred Issues (ALL prior rounds)\n")
        lines.append(
            "The following issues were intentionally deferred in prior rounds "
            "and must NOT be re-raised in any form:\n"
        )
        for d in defer_disps:
            rnum = d.get("round_number", "?")
            # Issue description requires a join — we use the stored
            # issues_json from the round's review.
            rreview = get_review_by_round(conn, session_id, rnum)
            desc = _get_issue_desc(rreview, d["issue_index"])
            rationale = d.get("rationale", "") or ""
            lines.append(
                f"  - [Round {rnum}] {desc}"
                + (f" — deferred because: {rationale}" if rationale else "")
            )
        lines.append("")

    lines.append(
        "INSTRUCTIONS FOR THIS REVIEW:\n"
        "- DEFERRED issues listed above are intentionally out of scope — do not "
        "re-raise them in any form.\n"
        "- ACCEPTED issues from prior rounds should be verified as resolved in "
        "the current plan.\n"
        "- Focus only on genuinely NEW issues not previously raised or deferred."
    )

    result = "\n".join(lines)
    logger.debug(
        "History context: %d chars, %d cumulative defers",
        len(result), len(defer_disps),
    )
    return result


def _get_issue_desc(review_row, issue_index: int) -> str:
    """Extract a single issue description from a review row's issues_json."""
    if review_row is None or not review_row["issues_json"]:
        return "(unknown issue)"
    try:
        issues = json.loads(review_row["issues_json"])
        if 0 <= issue_index < len(issues):
            return issues[issue_index].get("description", "(no description)")
    except (json.JSONDecodeError, TypeError, KeyError):
        pass
    return "(unknown issue)"
