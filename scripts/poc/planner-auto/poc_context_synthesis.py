#!/usr/bin/env python3
"""POC 4b: On-Demand Context Synthesis

Validate on-demand context synthesis from DB for plan generation.

Steps:
  1. Create and populate test DB (reuse POC 3a schema):
     - 5-8 context_entries (files with summaries)
     - 10-15 messages (simulated user/planner conversation with
       requirements, decisions, clarification loops, greetings)
  2. Query all context_entries and messages for session
  3. Build synthesis prompt for Claude:
     - "Given this conversation history and loaded files, produce
       a structured context summary covering: files and their purpose,
       key entities, user requirements, decisions made, open questions"
  4. Invoke Claude (headless, cheap model like haiku)
  5. Capture synthesized output
  6. Validate:
     a. Under 2000 tokens
     b. Contains references to loaded files
     c. Captures key decisions from conversation
     d. Omits noise (greetings, repetitive clarifications)
  7. Print: synthesized context, token count, latency

Usage:
  export ANTHROPIC_API_KEY="your-key"
  python scripts/poc/planner-auto/poc_context_synthesis.py
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from claude_agent_sdk import query
from claude_agent_sdk.types import ClaudeAgentOptions, ResultMessage

# Import DB helpers from POC 3a
sys.path.insert(0, str(Path(__file__).parent))
from poc_session_db import (
    create_schema,
    create_session,
    update_session_phase,
    add_message,
    add_context_entry,
    get_messages,
    get_context_entries,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

SYNTHESIS_SYSTEM_PROMPT = """\
You are a context synthesizer. Your job is to distill noisy conversation \
history and project file metadata into a structured, concise summary that \
another AI agent can use to generate an implementation plan.

Be ruthless about discarding noise: greetings, filler, repetitive \
clarifications, and small talk add no value. Extract only signal.

Output ONLY the markdown summary. No extra commentary or preamble."""


# ---------------------------------------------------------------------------
# Populate test DB
# ---------------------------------------------------------------------------

def populate_rich_test_db(conn: sqlite3.Connection) -> str:
    """Create a session with realistically noisy conversation data.

    Adds 6 context entries and 15 messages simulating a user/planner
    conversation about adding user registration to a Flask app.

    Returns:
        The session_id of the created session.
    """
    session_id = create_session(conn, "flask-registration-poc")
    update_session_phase(conn, session_id, "discussion")

    # --- 6 context entries ---
    context_entries = [
        ("file", "src/app.py",
         "Flask application with health endpoint and user listing"),
        ("file", "src/models.py",
         "SQLAlchemy User model with id, username, email, created_at"),
        ("file", "src/config.py",
         "Configuration with DATABASE_URL, SECRET_KEY, DEBUG flag"),
        ("file", "tests/test_app.py",
         "Existing tests for health and list_users endpoints"),
        ("file", "requirements.txt",
         "Flask, SQLAlchemy, pytest, bcrypt"),
        ("entity", "User",
         "Core domain entity: id (int PK), username (str unique), "
         "email (str unique), created_at (datetime)"),
    ]
    for entry_type, key, value in context_entries:
        add_context_entry(conn, session_id, entry_type, key, value)

    # --- 15 messages (realistic conversation with noise) ---
    messages = [
        ("user",
         "Hi, I need help adding a feature to this Flask app"),
        ("planner",
         "Hello! I see you've loaded several files. Let me review them. "
         "What feature would you like to add?"),
        ("user",
         "User registration"),
        ("planner",
         "Got it. Could you be more specific about what the registration "
         "should include?"),
        ("user",
         "Oh wait, let me also add the requirements.txt file"),
        ("planner",
         "Thanks, I see requirements.txt now. So for registration - what "
         "fields should the registration form accept?"),
        ("user",
         "Email and password. The username should be derived from the "
         "email (everything before @)"),
        ("planner",
         "Interesting approach for username. Should we validate the "
         "email format?"),
        ("user",
         "Yes definitely. Also hash the passwords - I see bcrypt is "
         "already in requirements"),
        ("planner",
         "Good catch on bcrypt. What about rate limiting? Public "
         "registration endpoints are targets for abuse."),
        ("user",
         "Yes, add rate limiting. Let's do 5 requests per minute per IP"),
        ("planner",
         "Should registration return a JWT token or just a success response?"),
        ("user",
         "Hmm, good question. Let's just return success with the user ID "
         "for now. We can add JWT later"),
        ("planner",
         "Makes sense - keep it simple. Any specific error responses "
         "you want?"),
        ("user",
         "Standard REST - 400 for bad input, 409 for duplicate email, "
         "429 for rate limit"),
    ]
    for role, content in messages:
        add_message(conn, session_id, role, content)

    return session_id


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_synthesis_prompt(
    messages: list[dict],
    context_entries: list[dict],
) -> str:
    """Construct the synthesis prompt from DB records.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        context_entries: List of context entry dicts with 'entry_type',
            'key', and 'value' keys.

    Returns:
        The full prompt string to send to Claude.
    """
    parts: list[str] = []

    parts.append(
        "Given the following conversation history and loaded project files, "
        "produce a structured context summary. Extract only the important "
        "information — skip greetings, small talk, and repetitive "
        "clarifications."
    )

    # Loaded files section
    parts.append("\n## Loaded Files")
    for entry in context_entries:
        label = entry["entry_type"]
        key = entry["key"]
        value = entry["value"]
        parts.append(f"- **[{label}] {key}**: {value}")

    # Conversation history section
    parts.append("\n## Conversation History")
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        parts.append(f"- {role}: {content}")

    # Required output format
    parts.append("\n## Required Output Format")
    parts.append(
        "Produce a markdown summary with these sections:\n"
        "- **Files & Purpose**: What each file does and why it matters\n"
        "- **Key Entities**: Domain objects and their attributes\n"
        "- **Requirements**: What the user wants built (be specific)\n"
        "- **Decisions Made**: Explicit choices made during conversation\n"
        "- **Open Questions**: Anything unresolved\n"
        "\nBe concise. Target under 500 words."
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Synthesis runner
# ---------------------------------------------------------------------------

async def run_synthesis(
    conn: sqlite3.Connection,
    session_id: str,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Query the DB, build a prompt, invoke Claude, and return results.

    Args:
        conn: SQLite connection with session data.
        session_id: The session to synthesize context for.
        model: Claude model to use for synthesis.

    Returns:
        Dict with keys: synthesis_text, duration_ms, total_cost_usd,
        usage, word_count, char_count.
    """
    messages = get_messages(conn, session_id)
    context_entries = get_context_entries(conn, session_id)

    prompt = build_synthesis_prompt(messages, context_entries)

    result_msg: ResultMessage | None = None
    t0 = time.monotonic()

    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            system_prompt=SYNTHESIS_SYSTEM_PROMPT,
            model=model,
            max_turns=1,
            permission_mode="bypassPermissions",
            stderr=lambda s: None,
        ),
    ):
        if isinstance(message, ResultMessage):
            result_msg = message

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    synthesis_text = (result_msg.result or "") if result_msg else ""
    total_cost_usd = result_msg.total_cost_usd if result_msg else None
    usage = result_msg.usage if result_msg else None
    # Prefer SDK-reported duration if available, else use our wall-clock
    duration_ms = result_msg.duration_ms if result_msg and result_msg.duration_ms else elapsed_ms

    word_count = len(synthesis_text.split())
    char_count = len(synthesis_text)

    return {
        "synthesis_text": synthesis_text,
        "duration_ms": duration_ms,
        "total_cost_usd": total_cost_usd,
        "usage": usage,
        "word_count": word_count,
        "char_count": char_count,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_synthesis(
    text: str,
    context_entries: list[dict],
    messages: list[dict],
) -> list[tuple[str, bool, str]]:
    """Validate the synthesized context against expected quality checks.

    Args:
        text: The synthesized context text from Claude.
        context_entries: Original context entries from the DB.
        messages: Original messages from the DB.

    Returns:
        List of (check_name, passed, detail) tuples.
    """
    checks: list[tuple[str, bool, str]] = []
    lower_text = text.lower()
    word_count = len(text.split())

    # 1. Under 500 words
    checks.append((
        "under_500_words",
        word_count <= 500,
        f"{word_count} words" + ("" if word_count <= 500 else " (exceeds 500)"),
    ))

    # 2. Has Files section header
    has_files = bool(re.search(r"(?i)(files|purpose)", text))
    checks.append((
        "has_files_section",
        has_files,
        "Found Files/Purpose header" if has_files else "Missing Files/Purpose header",
    ))

    # 3. Has Requirements section header
    has_req = bool(re.search(r"(?i)requirements", text))
    checks.append((
        "has_requirements_section",
        has_req,
        "Found Requirements header" if has_req else "Missing Requirements header",
    ))

    # 4. Has Decisions section header
    has_dec = bool(re.search(r"(?i)decisions", text))
    checks.append((
        "has_decisions_section",
        has_dec,
        "Found Decisions header" if has_dec else "Missing Decisions header",
    ))

    # 5. References app.py
    refs_app = "app.py" in lower_text or "flask app" in lower_text
    checks.append((
        "references_app_py",
        refs_app,
        "Mentions app.py or Flask app" if refs_app else "No reference to app.py",
    ))

    # 6. References models.py
    refs_models = "models.py" in lower_text or "user model" in lower_text
    checks.append((
        "references_models_py",
        refs_models,
        "Mentions models.py or User model" if refs_models else "No reference to models.py",
    ))

    # 7. Captures email validation requirement
    captures_email = bool(
        re.search(r"(?i)email.{0,20}valid", text)
        or re.search(r"(?i)valid.{0,20}email", text)
    )
    checks.append((
        "captures_email_validation",
        captures_email,
        "Mentions email validation" if captures_email else "Missing email validation requirement",
    ))

    # 8. Captures rate limiting
    captures_rate = bool(
        re.search(r"(?i)rate.{0,10}limit", text)
        or "5 requests" in lower_text
        or "per minute" in lower_text
    )
    checks.append((
        "captures_rate_limiting",
        captures_rate,
        "Mentions rate limiting" if captures_rate else "Missing rate limiting requirement",
    ))

    # 9. Captures username derived from email
    captures_username = bool(
        re.search(r"(?i)username.{0,30}email", text)
        or re.search(r"(?i)email.{0,30}username", text)
        or re.search(r"(?i)deriv.{0,20}username", text)
        or re.search(r"(?i)username.{0,30}before.{0,5}@", text)
        or re.search(r"(?i)before.{0,5}@", text)
    )
    checks.append((
        "captures_username_from_email",
        captures_username,
        "Mentions deriving username from email" if captures_username
        else "Missing username-from-email requirement",
    ))

    # 10. Captures JWT decision (deferred)
    captures_jwt = bool(
        re.search(r"(?i)jwt.{0,30}(later|defer|not|simple|success)", text)
        or re.search(r"(?i)(later|defer).{0,30}jwt", text)
        or re.search(r"(?i)success.{0,20}user.{0,5}id", text)
        or re.search(r"(?i)user.{0,5}id.{0,20}success", text)
        or re.search(r"(?i)no.{0,5}jwt", text)
        or re.search(r"(?i)return.{0,30}user.{0,5}id", text)
    )
    checks.append((
        "captures_jwt_decision",
        captures_jwt,
        "Mentions JWT deferred / success with user ID" if captures_jwt
        else "Missing JWT deferral decision",
    ))

    # 11. Omits greeting noise
    # Check that standalone greetings ("Hi" / "Hello") are not present.
    # We look for "Hi," or "Hello!" at word boundaries — typical greeting patterns.
    has_greeting_noise = bool(
        re.search(r"(?i)\bhi[,!]?\s+(i need|how|there)", text)
        or re.search(r"(?i)\bhello[,!]?\s+(i see|how|there|!)", text)
    )
    checks.append((
        "omits_greeting_noise",
        not has_greeting_noise,
        "No greeting noise detected" if not has_greeting_noise
        else "Contains greeting noise (Hi/Hello patterns from conversation)",
    ))

    return checks


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_validation_table(checks: list[tuple[str, bool, str]]) -> None:
    """Print validation results as a formatted table."""
    print(f"\n{'=' * 74}")
    print("Validation Results")
    print(f"{'=' * 74}")

    header = f"{'#':>2} | {'Check':<32} | {'Result':<6} | Detail"
    separator = f"{'':->3}+{'':->34}+{'':->8}+{'':->28}"
    print(header)
    print(separator)

    passed = 0
    for i, (name, ok, detail) in enumerate(checks, 1):
        status = "PASS" if ok else "FAIL"
        print(f"{i:>2} | {name:<32} | {status:<6} | {detail}")
        if ok:
            passed += 1

    total = len(checks)
    print(f"{'=' * 74}")
    print(f"Results: {passed}/{total} passed")

    if passed < total:
        print(f"{total - passed} check(s) FAILED.")
    else:
        print("All checks passed.")


def print_metrics(result: dict[str, Any]) -> None:
    """Print timing, cost, and usage metrics."""
    duration_s = result["duration_ms"] / 1000.0 if result["duration_ms"] else 0.0
    cost = result["total_cost_usd"]

    print(f"\nMetrics:")
    print(f"  Duration:    {duration_s:.1f}s")
    print(f"  Cost:        ${cost:.6f}" if cost is not None else "  Cost:        N/A")
    print(f"  Word count:  {result['word_count']}")
    print(f"  Char count:  {result['char_count']}")

    if result["usage"]:
        usage = result["usage"]
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", "?")
            output_tokens = usage.get("output_tokens", "?")
            print(f"  Input tok:   {input_tokens}")
            print(f"  Output tok:  {output_tokens}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="POC 4b: On-demand context synthesis from session DB"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL})",
    )
    args = parser.parse_args()

    print(f"POC 4b: Context Synthesis ({args.model})")
    print(f"{'=' * 56}")

    # 1. Set up in-memory DB and populate
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)

    session_id = populate_rich_test_db(conn)
    messages = get_messages(conn, session_id)
    context_entries = get_context_entries(conn, session_id)

    print(f"Session:   {session_id}")
    print(f"Messages:  {len(messages)}")
    print(f"Context:   {len(context_entries)} entries")
    print(f"Model:     {args.model}")

    # 2. Run synthesis
    result = asyncio.run(run_synthesis(conn, session_id, model=args.model))

    # 3. Print the full synthesized context
    print(f"\n{'=' * 74}")
    print("Synthesized Context")
    print(f"{'=' * 74}")
    if result["synthesis_text"]:
        print(result["synthesis_text"])
    else:
        print("(no synthesis produced)")

    # 4. Validate
    checks = validate_synthesis(
        result["synthesis_text"],
        context_entries,
        messages,
    )
    print_validation_table(checks)

    # 5. Print metrics
    print_metrics(result)

    conn.close()


if __name__ == "__main__":
    main()
