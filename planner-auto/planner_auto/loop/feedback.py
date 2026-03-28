"""Feedback validation — asks Claude to ACCEPT, DEFER, or REJECT each issue.

``validate_feedback`` bridges the reviewer's output and the planner by
having Claude assess whether each issue should be fixed (ACCEPT), skipped
as out-of-scope (DEFER), or dismissed as inapplicable (REJECT).

Each disposition is stored in ``review_dispositions`` for use in future
review-context history (preventing the reviewer from re-raising deferred
items).  The function returns a new ``ReviewerResponse`` containing only
the ACCEPT issues, which is what the revision prompt receives.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from planner_auto.db import add_disposition
from planner_auto.reviewer.contract import ReviewIssue, ReviewerResponse, Severity, Verdict
from planner_auto.sdk_wrapper import query_claude

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System / user prompt templates
# ---------------------------------------------------------------------------

_FEEDBACK_SYSTEM_PROMPT = """\
You are an experienced software architect helping a planning team decide
which reviewer issues to address in the next revision.

For each numbered issue, decide one of:
- ACCEPT  — the planner should fix this in the next revision
- DEFER   — valid concern but intentionally out of scope for this iteration
- REJECT  — not applicable, already addressed, or not a real problem

Respond ONLY with a JSON array, no other text:
[
  {"index": 0, "disposition": "ACCEPT",  "rationale": "..."},
  {"index": 1, "disposition": "DEFER",   "rationale": "..."},
  {"index": 2, "disposition": "REJECT",  "rationale": "..."}
]"""

_FEEDBACK_USER_TEMPLATE = """\
Plan being reviewed:
---
{plan_text}
---

Reviewer issues to assess:
{issues_list}

Provide your ACCEPT / DEFER / REJECT assessment as a JSON array."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def validate_feedback(
    plan_text: str,
    review: ReviewerResponse,
    planner_model: str,
    conn,
    review_id: int,
    backend: str | None = None,
) -> ReviewerResponse:
    """Ask Claude to ACCEPT, DEFER, or REJECT each reviewer issue.

    Stores one ``review_dispositions`` row per issue, then returns a new
    ``ReviewerResponse`` whose ``issues`` list contains only the ACCEPT
    issues (passed to the revision prompt).

    Args:
        plan_text: The current plan draft text.
        review: The ``ReviewerResponse`` from the reviewer adapter.
        planner_model: Claude model to use for disposition assessment.
        conn: SQLite connection (used to store dispositions).
        review_id: The DB row-id of the current review (FK for dispositions).

    Returns:
        A new ``ReviewerResponse`` with ``verdict`` preserved and ``issues``
        containing only ACCEPT items.
    """
    if not review.issues:
        return ReviewerResponse(verdict=review.verdict, issues=[], summary=review.summary)

    # Build the issues list for the prompt.
    issue_lines: list[str] = []
    for idx, issue in enumerate(review.issues):
        guidance = (
            f"\n   Guidance: {issue.resolution_guidance}"
            if issue.resolution_guidance
            else ""
        )
        issue_lines.append(
            f"{idx}. [{issue.severity.value.upper()}] {issue.description}"
            f"\n   Rationale: {issue.rationale}{guidance}"
        )

    user_content = _FEEDBACK_USER_TEMPLATE.format(
        plan_text=plan_text,
        issues_list="\n".join(issue_lines),
    )

    raw_response = await query_claude(
        messages=[{"role": "user", "content": user_content}],
        system_prompt=_FEEDBACK_SYSTEM_PROMPT,
        model=planner_model,
        backend=backend,
    )

    dispositions = _parse_dispositions(raw_response, len(review.issues))

    # Store dispositions in DB and collect ACCEPT issues.
    accept_issues: list[ReviewIssue] = []
    for idx, issue in enumerate(review.issues):
        disp = dispositions.get(idx, {"disposition": "ACCEPT", "rationale": ""})
        disposition_value = disp.get("disposition", "ACCEPT").upper()
        rationale = disp.get("rationale", "") or ""

        add_disposition(conn, review_id, idx, disposition_value, rationale or None)
        logger.info(
            "Issue %d: %s — %s", idx, disposition_value, issue.description[:60]
        )

        if disposition_value == "ACCEPT":
            accept_issues.append(issue)

    return ReviewerResponse(
        verdict=review.verdict,
        issues=accept_issues,
        summary=review.summary,
        keep=review.keep,
        trim=review.trim,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_dispositions(raw_text: str, issue_count: int) -> dict[int, dict]:
    """Parse Claude's JSON response into a dict of {index: {disposition, rationale}}.

    Falls back to regex if JSON parsing fails; defaults to ACCEPT for any
    issue whose disposition cannot be determined.

    Args:
        raw_text: Raw text response from Claude.
        issue_count: Total number of issues (used for fallback defaults).

    Returns:
        Dict mapping issue index to ``{"disposition": str, "rationale": str}``.
    """
    result: dict[int, dict] = {}

    # Stage 1: JSON (possibly inside a markdown fence).
    parsed = _try_json(raw_text)
    if parsed is not None:
        for item in parsed:
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            if not isinstance(idx, int):
                continue
            disposition = str(item.get("disposition", "ACCEPT")).upper()
            if disposition not in ("ACCEPT", "DEFER", "REJECT"):
                disposition = "ACCEPT"
            result[idx] = {
                "disposition": disposition,
                "rationale": str(item.get("rationale", "") or ""),
            }
        return result

    # Stage 2: Regex fallback — look for "0: ACCEPT" / "Issue 0 — DEFER" patterns.
    for idx in range(issue_count):
        pattern = rf"(?:issue\s+)?{idx}[:\s\-]+\s*(ACCEPT|DEFER|REJECT)"
        m = re.search(pattern, raw_text, re.IGNORECASE)
        if m:
            result[idx] = {
                "disposition": m.group(1).upper(),
                "rationale": "",
            }

    # Default unmatched issues to ACCEPT (conservative — better to fix than ignore).
    for idx in range(issue_count):
        if idx not in result:
            result[idx] = {"disposition": "ACCEPT", "rationale": ""}

    return result


def _try_json(text: str) -> list | None:
    """Try to parse a JSON array from *text* (including markdown fences)."""
    # Try markdown-fenced first.
    fence_match = re.search(r"```(?:json)?\s*\n(\[.*?\])\s*\n```", text, re.DOTALL)
    candidate = fence_match.group(1) if fence_match else text.strip()

    try:
        data = json.loads(candidate)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, ValueError):
        pass

    # Try extracting the outermost JSON array from anywhere in the text.
    bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
    if bracket_match:
        try:
            data = json.loads(bracket_match.group(0))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    return None
