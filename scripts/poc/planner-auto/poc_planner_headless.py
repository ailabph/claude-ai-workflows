#!/usr/bin/env python3
"""POC 4a: Planner Headless (Claude Agent SDK)

Validate Claude Agent SDK for headless milestone plan generation.

Steps:
  1. Define system prompt that requires CLAUDE_orch_v2.md plan format:
     - ## Milestone N: Name
     - ### Tasks (checkbox list)
     - ### Deliverables (checkbox list)
     - Sequential numbering, 3-5 milestones
  2. Load 2-3 sample context files
  3. Construct user prompt: context files + feature description
  4. Invoke Claude via Agent SDK (headless, non-interactive)
  5. Capture full response
  6. Validate output:
     a. Contains milestone headers matching ## Milestone N: pattern
     b. Has 3-5 milestones
     c. Each milestone has tasks and deliverables
  7. Optionally run through orchestrator-auto's milestone parser
     to verify compatibility
  8. Print: plan output, validation results, latency, token usage

Usage:
  export ANTHROPIC_API_KEY="your-key"
  python scripts/poc/planner-auto/poc_planner_headless.py
  python scripts/poc/planner-auto/poc_planner_headless.py --feature "Add user auth with JWT"
"""

from __future__ import annotations

import argparse
import asyncio
import re
from typing import Any

from claude_agent_sdk import query
from claude_agent_sdk.types import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_FEATURE = (
    "Add user registration with email validation, password hashing, "
    "and rate limiting"
)

DEFAULT_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """\
You are a senior software engineer creating an implementation plan for an \
automated orchestrator. The plan will be executed by a coding agent, so it \
must be precise, scoped, and follow the format exactly.

## Output Format

```markdown
# <Feature Name> - Implementation Plan

## Overview
[What we're building and why — 2-3 sentences. No filler.]

## Milestone 1: <Name>
[1-2 sentence description of this milestone's goal]

### Tasks
- [ ] <Concrete task — 1 sentence max>
- [ ] <Concrete task — 1 sentence max>

### Deliverables
- [ ] <Verifiable output (file created, test passing, endpoint working)>
- [ ] <Verifiable output>

## Milestone 2: <Name>
...
```

## Strict Rules

Format:
- Use `## Milestone N: Name` headers, sequential numbering starting at 1
- Each milestone MUST have `### Tasks` with `- [ ]` checkbox items
- Each milestone MUST have `### Deliverables` with `- [ ]` checkbox items
- 3-5 milestones total. No more, no fewer.

Size constraints:
- Max 5-8 tasks per milestone. If you need more, split into two milestones.
- Max 1-2 sentences per task. No multi-paragraph task descriptions.
- Max 3-5 deliverables per milestone.
- Total plan MUST be under 3,000 words. Aim for 1,500-2,000.

Scope constraints:
- Implement ONLY what was requested. Do not add adjacent features.
- If the request is "add user registration", do NOT also add login, JWT auth, \
password reset, or admin endpoints unless explicitly asked.
- Each milestone produces independently runnable, tested code.
- Scope each milestone to roughly 5-15 minutes of executor work.

Quality:
- Be specific about file paths and function names.
- Include test requirements in every milestone, not just the last one.
- Name the error handling strategy, don't just say "add error handling".
- Output ONLY the plan. No commentary before or after.
"""

# ---------------------------------------------------------------------------
# Sample context files (simulating codebase context)
# ---------------------------------------------------------------------------

SAMPLE_FILES: dict[str, str] = {
    "src/app.py": '''\
from flask import Flask
from src.models import db

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
app.config["SECRET_KEY"] = "dev-secret-key"
db.init_app(app)


@app.route("/health")
def health():
    return {"status": "ok"}


@app.route("/api/users", methods=["GET"])
def list_users():
    from src.models import User
    users = User.query.all()
    return {"users": [u.to_dict() for u in users]}


if __name__ == "__main__":
    app.run(debug=True)
''',
    "src/models.py": '''\
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
        }
''',
    "tests/test_app.py": '''\
import pytest
from src.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
''',
}


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_user_prompt(feature: str, context_files: dict[str, str]) -> str:
    """Build the user prompt combining context files and feature description."""
    parts: list[str] = ["## Context Files\n"]

    for filepath, content in context_files.items():
        parts.append(f"### {filepath}")
        parts.append(f"```python\n{content}```\n")

    parts.append("## Feature Request")
    parts.append(feature)
    parts.append(
        "\nCreate a comprehensive implementation plan following "
        "the milestone format specified in your instructions."
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Plan validation
# ---------------------------------------------------------------------------

_MILESTONE_HEADER_RE = re.compile(r"^## Milestone (\d+):\s*.+", re.MULTILINE)
_TASKS_HEADER_RE = re.compile(r"^### Tasks\s*$", re.MULTILINE)
_DELIVERABLES_HEADER_RE = re.compile(r"^### Deliverables\s*$", re.MULTILINE)
_CHECKBOX_RE = re.compile(r"^\s*- \[ \]\s+.+", re.MULTILINE)


def validate_plan(plan_text: str) -> list[tuple[str, bool, str]]:
    """Validate a milestone plan against the expected format.

    Returns a list of (check_name, passed, detail) tuples.
    """
    checks: list[tuple[str, bool, str]] = []

    # 1. Plan starts with # header
    stripped = plan_text.strip()
    starts_with_header = stripped.startswith("#")
    checks.append((
        "starts_with_header",
        starts_with_header,
        "Plan starts with '#'" if starts_with_header else "Plan does not start with '#'",
    ))

    # 2. Count milestone headers
    milestone_matches = list(_MILESTONE_HEADER_RE.finditer(plan_text))
    milestone_count = len(milestone_matches)
    checks.append((
        "milestone_count",
        3 <= milestone_count <= 5,
        f"Found {milestone_count} milestone(s) (expected 3-5)",
    ))

    # 3. Sequential numbering
    numbers = [int(m.group(1)) for m in milestone_matches]
    expected = list(range(1, milestone_count + 1))
    sequential = numbers == expected
    checks.append((
        "sequential_numbering",
        sequential,
        f"Numbers: {numbers}" + ("" if sequential else f" (expected {expected})"),
    ))

    # 4. Per-milestone checks: Tasks and Deliverables sections with checkboxes
    # Split plan text into milestone sections for per-milestone validation
    milestone_sections: list[str] = []
    for i, match in enumerate(milestone_matches):
        start = match.start()
        end = milestone_matches[i + 1].start() if i + 1 < len(milestone_matches) else len(plan_text)
        milestone_sections.append(plan_text[start:end])

    for i, section in enumerate(milestone_sections, 1):
        # Check for ### Tasks section
        has_tasks_header = bool(_TASKS_HEADER_RE.search(section))
        checks.append((
            f"milestone_{i}_has_tasks",
            has_tasks_header,
            f"Milestone {i}: {'has' if has_tasks_header else 'MISSING'} ### Tasks section",
        ))

        # Check for at least one checkbox item in Tasks
        # Get the Tasks section text (between ### Tasks and the next ###)
        tasks_match = _TASKS_HEADER_RE.search(section)
        if tasks_match:
            tasks_start = tasks_match.end()
            # Find next ### header or end of section
            next_header = re.search(r"^### ", section[tasks_start:], re.MULTILINE)
            tasks_end = tasks_start + next_header.start() if next_header else len(section)
            tasks_text = section[tasks_start:tasks_end]
            task_checkboxes = _CHECKBOX_RE.findall(tasks_text)
            has_task_items = len(task_checkboxes) > 0
        else:
            task_checkboxes = []
            has_task_items = False

        checks.append((
            f"milestone_{i}_task_items",
            has_task_items,
            f"Milestone {i}: {len(task_checkboxes)} task checkbox(es)",
        ))

        # Check for ### Deliverables section
        has_deliv_header = bool(_DELIVERABLES_HEADER_RE.search(section))
        checks.append((
            f"milestone_{i}_has_deliverables",
            has_deliv_header,
            f"Milestone {i}: {'has' if has_deliv_header else 'MISSING'} ### Deliverables section",
        ))

        # Check for at least one checkbox item in Deliverables
        deliv_match = _DELIVERABLES_HEADER_RE.search(section)
        if deliv_match:
            deliv_start = deliv_match.end()
            next_header = re.search(r"^### |^## ", section[deliv_start:], re.MULTILINE)
            deliv_end = deliv_start + next_header.start() if next_header else len(section)
            deliv_text = section[deliv_start:deliv_end]
            deliv_checkboxes = _CHECKBOX_RE.findall(deliv_text)
            has_deliv_items = len(deliv_checkboxes) > 0
        else:
            deliv_checkboxes = []
            has_deliv_items = False

        checks.append((
            f"milestone_{i}_deliverable_items",
            has_deliv_items,
            f"Milestone {i}: {len(deliv_checkboxes)} deliverable checkbox(es)",
        ))

    return checks


# ---------------------------------------------------------------------------
# Run function
# ---------------------------------------------------------------------------

async def run_planner(
    feature: str = DEFAULT_FEATURE,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Run the headless planner and return structured results.

    Returns:
        Dict with keys: plan_text, duration_ms, total_cost_usd, usage,
        num_turns, is_error, validation.
    """
    prompt = build_user_prompt(feature, SAMPLE_FILES)

    result_msg: ResultMessage | None = None

    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            model=model,
            max_turns=1,
            permission_mode="bypassPermissions",
            stderr=lambda s: None,
        ),
    ):
        if isinstance(message, ResultMessage):
            result_msg = message

    # Extract plan text from ResultMessage.result (plain string)
    result_text = (result_msg.result or "") if result_msg else ""
    duration_ms = result_msg.duration_ms if result_msg else 0
    total_cost_usd = result_msg.total_cost_usd if result_msg else None
    usage = result_msg.usage if result_msg else None
    is_error = result_msg.is_error if result_msg else True
    num_turns = result_msg.num_turns if result_msg else 0

    # Validate the plan
    validation = validate_plan(result_text) if result_text else []

    return {
        "plan_text": result_text,
        "duration_ms": duration_ms,
        "total_cost_usd": total_cost_usd,
        "usage": usage,
        "num_turns": num_turns,
        "is_error": is_error,
        "validation": validation,
    }


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_validation_table(validation: list[tuple[str, bool, str]]) -> None:
    """Print validation results as a formatted table."""
    print(f"\n{'=' * 70}")
    print("Validation Results")
    print(f"{'=' * 70}")

    header = f"{'#':>2} | {'Check':<32} | {'Result':<6} | Detail"
    separator = f"{'':->3}+{'':->34}+{'':->8}+{'':->24}"
    print(header)
    print(separator)

    passed = 0
    for i, (name, ok, detail) in enumerate(validation, 1):
        status = "PASS" if ok else "FAIL"
        print(f"{i:>2} | {name:<32} | {status:<6} | {detail}")
        if ok:
            passed += 1

    total = len(validation)
    print(f"{'=' * 70}")
    print(f"Results: {passed}/{total} passed")

    if passed < total:
        print(f"{total - passed} check(s) FAILED.")
    else:
        print("All checks passed.")


def print_metrics(result: dict[str, Any]) -> None:
    """Print timing, cost, and usage metrics."""
    duration_s = result["duration_ms"] / 1000.0 if result["duration_ms"] else 0.0
    cost = result["total_cost_usd"]
    turns = result["num_turns"]

    print(f"\nMetrics:")
    print(f"  Duration:    {duration_s:.1f}s")
    print(f"  Cost:        ${cost:.4f}" if cost is not None else "  Cost:        N/A")
    print(f"  Turns:       {turns}")

    if result["usage"]:
        usage = result["usage"]
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", "?")
            output_tokens = usage.get("output_tokens", "?")
            print(f"  Input tok:   {input_tokens}")
            print(f"  Output tok:  {output_tokens}")

    if result["is_error"]:
        print("  Status:      ERROR")
    else:
        print("  Status:      OK")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="POC 4a: Headless milestone plan generation via Claude Agent SDK"
    )
    parser.add_argument(
        "--feature",
        type=str,
        default=DEFAULT_FEATURE,
        help=f"Feature description (default: '{DEFAULT_FEATURE}')",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL})",
    )
    args = parser.parse_args()

    print(f"POC 4a: Planner Headless ({args.model})")
    print(f"{'=' * 56}")
    print(f"Feature: {args.feature}")
    print(f"Model:   {args.model}")
    print(f"Context: {len(SAMPLE_FILES)} file(s)")

    result = asyncio.run(run_planner(feature=args.feature, model=args.model))

    # Print generated plan
    print(f"\n{'=' * 70}")
    print("Generated Plan")
    print(f"{'=' * 70}")
    if result["plan_text"]:
        print(result["plan_text"])
    else:
        print("(no plan generated)")

    # Print validation results
    print_validation_table(result["validation"])

    # Print metrics
    print_metrics(result)


if __name__ == "__main__":
    main()
