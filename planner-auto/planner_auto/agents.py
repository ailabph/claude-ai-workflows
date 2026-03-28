"""
Agent functions for discussion, context synthesis, and plan generation.

Persistence contracts:
- discuss(): Both user and assistant messages committed together only on success.
- synthesize_context(): Synthesis entry committed only on success.
- generate_plan(): Config snapshot and plan draft committed together only on success.
"""

import json
import logging
import sqlite3
import time
from datetime import datetime
from typing import Optional

from planner_auto.db import (
    add_context_entry,
    add_message,
    add_plan_draft,
    get_context_entries,
    get_messages,
    get_session_config,
    save_session_config,
    transaction,
)
from planner_auto.errors import CommandNotAllowedError
from planner_auto.prompts import (
    PLANNER_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
    prompt_version_hash,
)
from planner_auto.sdk_wrapper import query_claude
from planner_auto.session import SessionManager

logger = logging.getLogger(__name__)

DISCUSSION_SYSTEM_PROMPT = """\
You are a helpful planning assistant. You are in a discussion phase with the user \
to clarify requirements, understand constraints, and gather context before creating \
an implementation plan. Ask clarifying questions, summarize what you understand, \
and help the user think through their feature request.
"""

DEFAULT_MODEL = "claude-sonnet-4-6"
SYNTHESIS_MODEL = "claude-haiku-4-5-20251001"


async def discuss(
    session_id: str,
    user_input: str,
    conn: sqlite3.Connection,
    backend: str | None = None,
) -> str:
    """Send a discussion message and get Claude's response.

    Persistence contract: both user and assistant messages are committed
    together in a single transaction only on successful SDK response.
    On SDK failure, nothing is committed.

    Args:
        session_id: Session ID.
        user_input: The user's message.
        conn: SQLite connection.

    Returns:
        The assistant's response text.

    Raises:
        CommandNotAllowedError: If discuss is not allowed in current phase/status.
        SDKError subclasses: On SDK failures.
    """
    sm = SessionManager(conn)
    sm.check_command(session_id, "discuss")

    # Load message history
    existing_messages = get_messages(conn, session_id)
    messages = [
        {"role": row["role"], "content": row["content"]}
        for row in existing_messages
    ]
    messages.append({"role": "user", "content": user_input})

    # Call SDK — if this fails, nothing is persisted
    logger.info("Calling Claude for discussion, model=%s", DEFAULT_MODEL)
    _discuss_t0 = time.monotonic()
    response = await query_claude(
        messages=messages,
        system_prompt=DISCUSSION_SYSTEM_PROMPT,
        model=DEFAULT_MODEL,
        backend=backend,
    )
    _duration_ms = int((time.monotonic() - _discuss_t0) * 1000)
    logger.info("Claude responded, %d chars, %dms", len(response), _duration_ms)

    # Commit both messages together atomically on success
    with transaction(conn):
        add_message(conn, session_id, "user", user_input)
        add_message(conn, session_id, "assistant", response)

    return response


async def synthesize_context(
    session_id: str,
    conn: sqlite3.Connection,
    backend: str | None = None,
) -> str:
    """Synthesize context entries and messages into a summary.

    Queries all context_entries (excluding prior syntheses) and messages,
    builds a synthesis prompt, calls Claude with Haiku.
    Commits synthesis entry only on success.

    Args:
        session_id: Session ID.
        conn: SQLite connection.

    Returns:
        The synthesis text.
    """
    # Gather context (excluding prior syntheses)
    file_entries = get_context_entries(conn, session_id, entry_type="file")
    note_entries = get_context_entries(conn, session_id, entry_type="note")
    messages = get_messages(conn, session_id)

    # Build synthesis input
    parts = []

    if file_entries:
        parts.append("## Project Files")
        for entry in file_entries:
            parts.append(f"### {entry['entry_key']}\n```\n{entry['content']}\n```")

    if note_entries:
        parts.append("## Notes")
        for entry in note_entries:
            parts.append(f"- {entry['content']}")

    if messages:
        parts.append("## Discussion History")
        for msg in messages:
            parts.append(f"**{msg['role'].capitalize()}**: {msg['content']}")

    synthesis_input = "\n\n".join(parts)

    synthesis_messages = [{"role": "user", "content": synthesis_input}]

    # Call SDK — if this fails, nothing is persisted
    logger.info("Calling Claude for synthesis, model=%s", SYNTHESIS_MODEL)
    synthesis = await query_claude(
        messages=synthesis_messages,
        system_prompt=SYNTHESIS_SYSTEM_PROMPT,
        model=SYNTHESIS_MODEL,
        backend=backend,
    )
    logger.info("Context synthesized, %d words", len(synthesis.split()))

    # Commit synthesis entry only on success (no UPSERT — syntheses accumulate)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    key = f"synthesis-{timestamp}"
    add_context_entry(conn, session_id, key, "synthesis", synthesis)
    conn.commit()

    return synthesis


async def generate_plan(
    session_id: str,
    conn: sqlite3.Connection,
    model: str = DEFAULT_MODEL,
    backend: str | None = None,
) -> str:
    """Generate an implementation plan via context synthesis + planning.

    1. Calls synthesize_context() to create a fresh synthesis.
    2. Calls Claude with PLANNER_SYSTEM_PROMPT to generate the plan.
    3. Persistence contract: config snapshot and plan draft are committed
       together in a single transaction only after successful SDK response.

    Args:
        session_id: Session ID.
        conn: SQLite connection.
        model: Model to use for plan generation.

    Returns:
        The generated plan text.

    Raises:
        SDKError subclasses: On SDK failures.
    """
    # Step 1: Synthesize context
    synthesis = await synthesize_context(session_id, conn, backend=backend)

    # Step 2: Get first user message for feature description
    messages = get_messages(conn, session_id)
    feature_description = ""
    for msg in messages:
        if msg["role"] == "user":
            feature_description = msg["content"]
            break

    # Build plan generation prompt
    plan_prompt = (
        f"## Context Synthesis\n{synthesis}\n\n"
        f"## Feature Description\n{feature_description}\n\n"
        f"Generate an implementation plan following the format specified in your system prompt."
    )

    plan_messages = [{"role": "user", "content": plan_prompt}]

    # Call SDK — if this fails, nothing is persisted
    logger.info("Calling Claude for plan generation, model=%s", model)
    _t0 = time.monotonic()
    plan_content = await query_claude(
        messages=plan_messages,
        system_prompt=PLANNER_SYSTEM_PROMPT,
        model=model,
        backend=backend,
    )
    _duration_ms = int((time.monotonic() - _t0) * 1000)
    logger.info("Claude responded, %d chars, %dms", len(plan_content), _duration_ms)

    # Step 3: Commit config snapshot and plan draft atomically on success
    # Preserve existing session config fields (especially claude_backend)
    existing_config = get_session_config(conn, session_id)
    preserved = {}
    if existing_config:
        try:
            preserved = json.loads(existing_config["config_json"])
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    config = {
        **preserved,  # preserve claude_backend and other session-level settings
        "model": model,
        "prompt_hashes": {
            "planner": prompt_version_hash(PLANNER_SYSTEM_PROMPT),
            "synthesis": prompt_version_hash(SYNTHESIS_SYSTEM_PROMPT),
        },
        "feature_description": feature_description,
    }
    with transaction(conn):
        config_id = save_session_config(conn, session_id, json.dumps(config))
        add_plan_draft(conn, session_id, plan_content, model, config_snapshot_id=config_id)

    return plan_content
