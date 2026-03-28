"""Complexity detection and round-cap calculation for the review loop.

``detect_complexity`` scans the first user message (feature description stored
by Plan 1) and the latest plan draft for complexity keywords, then returns
"standard" or "complex".

``get_max_rounds`` maps (complexity, fast) to the correct cap:

    standard  → 8 rounds
    complex   → 12 rounds
    fast mode → 4 rounds (overrides complexity)
"""

from __future__ import annotations

import logging
from typing import Optional

from planner_auto.db import get_latest_plan_draft, get_messages

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Complexity keywords
# ---------------------------------------------------------------------------

COMPLEX_KEYWORDS: list[str] = [
    "concurrent",
    "lock",
    "retry",
    "backoff",
    "queue",
    "dead-letter",
    "idempotent",
    "dedup",
    "signature",
    "hmac",
    "token",
    "encrypt",
    "state machine",
    "transition",
    "schedule",
    "cron",
    "expir",
]

# ---------------------------------------------------------------------------
# Round caps
# ---------------------------------------------------------------------------

_MAX_ROUNDS_STANDARD = 8
_MAX_ROUNDS_COMPLEX = 12
_MAX_ROUNDS_FAST = 4


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_complexity(conn, session_id: str) -> str:
    """Detect whether the feature is standard or complex.

    Scans two sources for complexity keywords:

    1. **First user message** in ``messages`` for the session
       (the feature description entered during the discussion phase).
    2. **Latest plan draft** content.

    Args:
        conn: SQLite connection.
        session_id: Session ID.

    Returns:
        ``"complex"`` if any complexity keyword is found; ``"standard"``
        otherwise.
    """
    sources: list[tuple[str, str]] = []

    # Source 1: first user message
    messages = get_messages(conn, session_id)
    first_user = next((m for m in messages if m["role"] == "user"), None)
    if first_user:
        sources.append(("first_user_message", first_user["content"]))

    # Source 2: latest plan draft
    draft = get_latest_plan_draft(conn, session_id)
    if draft:
        sources.append(("plan_draft", draft["content"]))

    matched_keywords: list[str] = []
    matched_source: Optional[str] = None

    for source_name, text in sources:
        text_lower = text.lower()
        for kw in COMPLEX_KEYWORDS:
            if kw in text_lower and kw not in matched_keywords:
                matched_keywords.append(kw)
                if matched_source is None:
                    matched_source = source_name

    level = "complex" if matched_keywords else "standard"
    cap = _MAX_ROUNDS_COMPLEX if level == "complex" else _MAX_ROUNDS_STANDARD
    logger.info(
        "Complexity: %s, keywords: %s, cap: %d",
        level,
        matched_keywords or [],
        cap,
    )
    return level


def get_max_rounds(complexity: str, fast: bool = False) -> int:
    """Return the review round cap for the given complexity and mode.

    Args:
        complexity: ``"standard"`` or ``"complex"``.
        fast: If ``True``, returns the fast-mode cap (4) regardless of
            complexity.

    Returns:
        Maximum number of review rounds as an integer.
    """
    if fast:
        return _MAX_ROUNDS_FAST
    if complexity == "complex":
        return _MAX_ROUNDS_COMPLEX
    return _MAX_ROUNDS_STANDARD
