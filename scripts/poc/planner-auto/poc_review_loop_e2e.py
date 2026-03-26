#!/usr/bin/env python3
"""POC 5b: End-to-End Review Loop

Full integration test: plan -> review -> revise -> review -> GO.

Supports two modes:
  - Default: plan -> GPT review -> Claude revise -> GPT review -> ...
  - --self-review: plan -> GPT review -> Claude revise -> Claude self-check
    -> Claude repair (if needed) -> Claude wrap-up -> GPT review -> ...

The self-review mode adds a bounded planner-side quality gate after each
revision (max 3 extra Claude calls per round) to catch issues introduced
by the revision before GPT sees them.

Usage:
  export ANTHROPIC_API_KEY="your-key"
  export OPENAI_API_KEY="your-key"
  python scripts/poc/planner-auto/poc_review_loop_e2e.py
  python scripts/poc/planner-auto/poc_review_loop_e2e.py --self-review
  python scripts/poc/planner-auto/poc_review_loop_e2e.py --feature "Add JWT authentication"
  python scripts/poc/planner-auto/poc_review_loop_e2e.py --max-rounds 3
  python scripts/poc/planner-auto/poc_review_loop_e2e.py --output-dir /tmp/poc_e2e
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from claude_agent_sdk import query
from claude_agent_sdk.types import ClaudeAgentOptions, ResultMessage

# ---------------------------------------------------------------------------
# Sibling POC imports
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent))

# POC 2a -- parser
from poc_parse_go_nogo import ReviewerResponse, Severity, Verdict, parse_reviewer_response

# POC 3a -- DB
from poc_session_db import (
    create_schema,
    create_session,
    update_session_phase,
    update_session_status,
    add_message,
    add_context_entry,
    add_plan_draft,
    add_review,
    get_session,
    get_messages,
    get_latest_plan_draft,
    get_all_reviews,
)

# POC 3b -- artifact export
from poc_artifact_export import export_all

# POC 4a -- planner headless (system prompt + prompt builder)
from poc_planner_headless import PLANNER_SYSTEM_PROMPT, SAMPLE_FILES, build_user_prompt

# POC 1a -- reviewer
from poc_reviewer_direct_api import run_review, SYSTEM_PROMPT as REVIEWER_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_FEATURE = (
    "Add user registration with email validation, password hashing, "
    "and rate limiting"
)

DEFAULT_PLANNER_MODEL = "claude-sonnet-4-6"
DEFAULT_REVIEWER_MODEL = "gpt-5.4"
DEFAULT_MAX_ROUNDS = 5


# ---------------------------------------------------------------------------
# Claude Agent SDK helper
# ---------------------------------------------------------------------------

async def _call_claude(system_prompt: str, user_prompt: str, model: str) -> ResultMessage | None:
    """Call Claude via the Agent SDK and return the ResultMessage."""
    result_msg: ResultMessage | None = None
    async for message in query(
        prompt=user_prompt,
        options=ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=model,
            max_turns=1,
            permission_mode="bypassPermissions",
            stderr=lambda s: None,
        ),
    ):
        if isinstance(message, ResultMessage):
            result_msg = message
    return result_msg


# ---------------------------------------------------------------------------
# Plan generation
# ---------------------------------------------------------------------------

async def generate_initial_plan(feature: str, planner_model: str) -> dict:
    """Generate the initial milestone plan via Claude.

    Returns:
        {"plan_text": str, "duration_ms": int, "cost_usd": float | None}
    """
    user_prompt = build_user_prompt(feature, SAMPLE_FILES)
    result_msg = await _call_claude(PLANNER_SYSTEM_PROMPT, user_prompt, planner_model)

    plan_text = (result_msg.result or "") if result_msg else ""
    duration_ms = result_msg.duration_ms if result_msg else 0
    cost_usd = result_msg.total_cost_usd if result_msg else None

    return {
        "plan_text": plan_text,
        "duration_ms": duration_ms,
        "cost_usd": cost_usd,
    }


# ---------------------------------------------------------------------------
# Plan revision
# ---------------------------------------------------------------------------

def format_issues_for_revision(parsed: ReviewerResponse) -> str:
    """Format reviewer issues as a numbered list for the revision prompt.

    Example output:
        1. [critical] No error handling for API failures
           Rationale: Production services must handle upstream failures gracefully
        2. [major] Missing database migration step
           Rationale: Schema changes require explicit migration scripts
    """
    lines: list[str] = []
    for i, issue in enumerate(parsed.issues, 1):
        lines.append(f"{i}. [{issue.severity.value}] {issue.description}")
        if issue.rationale:
            lines.append(f"   Rationale: {issue.rationale}")
    return "\n".join(lines)


async def revise_plan(current_plan: str, review_issues: ReviewerResponse, planner_model: str) -> dict:
    """Revise a plan based on reviewer feedback via Claude.

    Returns:
        {"plan_text": str, "duration_ms": int, "cost_usd": float | None}
    """
    formatted_issues = format_issues_for_revision(review_issues)

    revision_prompt = (
        "The following implementation plan was reviewed and received a NO_GO verdict.\n"
        "Please revise the plan to address all the issues listed below.\n"
        "Keep the same milestone format (## Milestone N: Name, ### Tasks, ### Deliverables).\n"
        "\n"
        "## Current Plan\n"
        f"{current_plan}\n"
        "\n"
        "## Issues to Address\n"
        f"{formatted_issues}\n"
        "\n"
        "## Instructions\n"
        "Revise the plan to address each issue. Do not remove existing good content.\n"
        "Add missing elements (tests, error handling, etc.) as needed.\n"
        "Return the complete revised plan."
    )

    result_msg = await _call_claude(PLANNER_SYSTEM_PROMPT, revision_prompt, planner_model)

    plan_text = (result_msg.result or "") if result_msg else ""
    duration_ms = result_msg.duration_ms if result_msg else 0
    cost_usd = result_msg.total_cost_usd if result_msg else None

    return {
        "plan_text": plan_text,
        "duration_ms": duration_ms,
        "cost_usd": cost_usd,
    }


# ---------------------------------------------------------------------------
# Self-review steps (bounded: self-check → repair → wrap-up)
# ---------------------------------------------------------------------------

SELF_CHECK_PROMPT_TEMPLATE = """\
You just revised an implementation plan to address reviewer feedback.
Review your OWN revised draft below for problems introduced by the revision:

- Drift from original requirements
- Contradictions between milestones
- Missing validation or error handling you forgot to add
- Unnecessary scope or features that weren't requested
- Duplicated content across milestones

## Revised Plan
{plan}

## Instructions
List any material problems you find. If the plan is clean, say "NO ISSUES FOUND."
Be brief — just list problems, don't rewrite the plan."""

REPAIR_PROMPT_TEMPLATE = """\
Fix the following problems in this implementation plan. Do NOT add any new
scope or features — only fix the listed problems.

## Current Plan
{plan}

## Problems to Fix
{problems}

## Instructions
Return the complete fixed plan. Keep the same milestone format.
Do not add content beyond what's needed to fix the listed problems."""

WRAPUP_PROMPT_TEMPLATE = """\
Tighten this implementation plan for clarity and conciseness:

- Remove duplicated content across milestones
- Consolidate redundant task items
- Preserve all accepted fixes and requirements
- Do NOT add new scope, features, or milestones
- Target the same number of milestones

## Current Plan
{plan}

## Instructions
Return the complete plan, tightened and consistent. Same milestone format."""


async def self_check(plan_text: str, planner_model: str) -> dict:
    """Run a focused self-check on a revised plan.

    Returns:
        {"has_problems": bool, "problems_text": str, "duration_ms": int, "cost_usd": float | None}
    """
    prompt = SELF_CHECK_PROMPT_TEMPLATE.format(plan=plan_text)
    result_msg = await _call_claude(PLANNER_SYSTEM_PROMPT, prompt, planner_model)

    text = (result_msg.result or "") if result_msg else ""
    duration_ms = result_msg.duration_ms if result_msg else 0
    cost_usd = result_msg.total_cost_usd if result_msg else None

    # Determine if problems were found
    no_issues_markers = ["no issues found", "no material problems", "the plan is clean", "no problems"]
    has_problems = not any(marker in text.lower() for marker in no_issues_markers)

    return {
        "has_problems": has_problems,
        "problems_text": text,
        "duration_ms": duration_ms,
        "cost_usd": cost_usd,
    }


async def repair_plan(plan_text: str, problems: str, planner_model: str) -> dict:
    """Fix problems found by self-check without adding new scope.

    Returns:
        {"plan_text": str, "duration_ms": int, "cost_usd": float | None}
    """
    prompt = REPAIR_PROMPT_TEMPLATE.format(plan=plan_text, problems=problems)
    result_msg = await _call_claude(PLANNER_SYSTEM_PROMPT, prompt, planner_model)

    plan_text = (result_msg.result or "") if result_msg else ""
    duration_ms = result_msg.duration_ms if result_msg else 0
    cost_usd = result_msg.total_cost_usd if result_msg else None

    return {"plan_text": plan_text, "duration_ms": duration_ms, "cost_usd": cost_usd}


async def wrapup_plan(plan_text: str, planner_model: str) -> dict:
    """Tighten plan for conciseness and consistency.

    Returns:
        {"plan_text": str, "duration_ms": int, "cost_usd": float | None}
    """
    prompt = WRAPUP_PROMPT_TEMPLATE.format(plan=plan_text)
    result_msg = await _call_claude(PLANNER_SYSTEM_PROMPT, prompt, planner_model)

    plan_text = (result_msg.result or "") if result_msg else ""
    duration_ms = result_msg.duration_ms if result_msg else 0
    cost_usd = result_msg.total_cost_usd if result_msg else None

    return {"plan_text": plan_text, "duration_ms": duration_ms, "cost_usd": cost_usd}


async def run_self_review(plan_text: str, planner_model: str) -> dict:
    """Run the bounded self-review pipeline: self-check → repair → wrap-up.

    Returns:
        {
            "plan_text": str,           # final plan after self-review
            "self_check_found_problems": bool,
            "total_duration_ms": int,
            "total_cost_usd": float,
            "steps_run": int,           # 1 (check only), 2 (check+repair), or 3 (check+repair+wrapup)
        }
    """
    total_duration_ms = 0
    total_cost = 0.0
    current_plan = plan_text

    # Step 1: Self-check
    check_result = await self_check(current_plan, planner_model)
    total_duration_ms += check_result["duration_ms"]
    total_cost += check_result["cost_usd"] or 0.0
    steps_run = 1

    if not check_result["has_problems"]:
        # Clean — still run wrap-up for conciseness
        wrapup_result = await wrapup_plan(current_plan, planner_model)
        current_plan = wrapup_result["plan_text"]
        total_duration_ms += wrapup_result["duration_ms"]
        total_cost += wrapup_result["cost_usd"] or 0.0
        steps_run = 2  # check + wrapup (no repair needed)

        return {
            "plan_text": current_plan,
            "self_check_found_problems": False,
            "total_duration_ms": total_duration_ms,
            "total_cost_usd": total_cost,
            "steps_run": steps_run,
        }

    # Step 2: Repair
    repair_result = await repair_plan(current_plan, check_result["problems_text"], planner_model)
    current_plan = repair_result["plan_text"]
    total_duration_ms += repair_result["duration_ms"]
    total_cost += repair_result["cost_usd"] or 0.0
    steps_run = 2

    # Step 3: Wrap-up
    wrapup_result = await wrapup_plan(current_plan, planner_model)
    current_plan = wrapup_result["plan_text"]
    total_duration_ms += wrapup_result["duration_ms"]
    total_cost += wrapup_result["cost_usd"] or 0.0
    steps_run = 3

    return {
        "plan_text": current_plan,
        "self_check_found_problems": True,
        "total_duration_ms": total_duration_ms,
        "total_cost_usd": total_cost,
        "steps_run": steps_run,
    }


# ---------------------------------------------------------------------------
# DB verification
# ---------------------------------------------------------------------------

def verify_db_consistency(
    conn: sqlite3.Connection,
    session_id: str,
    expected_drafts: int,
    expected_reviews: int,
) -> list[tuple[str, bool, str]]:
    """Verify that the DB state is consistent with the loop outcome.

    Returns a list of (check_name, passed, detail) tuples.
    """
    results: list[tuple[str, bool, str]] = []

    # 1. Session exists and has correct status
    session = get_session(conn, session_id)
    if session is None:
        results.append(("session_exists", False, "session not found"))
        return results

    # If we converged the session should be complete; otherwise active
    results.append((
        "session_exists",
        True,
        f"status={session['status']}",
    ))

    # 2. Plan drafts count
    draft_rows = conn.execute(
        "SELECT COUNT(*) FROM plan_drafts WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    draft_count = draft_rows[0] if draft_rows else 0
    results.append((
        "plan_drafts_count",
        draft_count == expected_drafts,
        f"{draft_count} drafts",
    ))

    # 3. Reviews count
    review_rows = conn.execute(
        "SELECT COUNT(*) FROM reviews WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    review_count = review_rows[0] if review_rows else 0
    results.append((
        "reviews_count",
        review_count == expected_reviews,
        f"{review_count} reviews",
    ))

    # 4. Messages logged (at least the initial plan generation)
    msg_rows = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    msg_count = msg_rows[0] if msg_rows else 0
    results.append((
        "messages_logged",
        msg_count >= 1,
        f"{msg_count} messages",
    ))

    # 5. Latest plan draft number matches expected
    latest = get_latest_plan_draft(conn, session_id)
    latest_num = latest["draft_number"] if latest else 0
    results.append((
        "latest_draft_number",
        latest_num == expected_drafts,
        f"draft_number={latest_num}",
    ))

    return results


# ---------------------------------------------------------------------------
# Artifact export helpers
# ---------------------------------------------------------------------------

def _export_plan(plan_text: str, artifact_num: int, output_dir: Path, suffix: str = "") -> Path:
    """Write a plan artifact file and return its path."""
    filename = f"a-{artifact_num:02d}-plan{suffix}.md"
    path = output_dir / filename
    path.write_text(plan_text, encoding="utf-8")
    return path


def _export_review(review_result: dict, parsed: ReviewerResponse, artifact_num: int, output_dir: Path) -> Path:
    """Write a review artifact file and return its path."""
    filename = f"a-{artifact_num:02d}-review.md"

    lines: list[str] = [
        f"# Review",
        "",
        f"**Verdict:** {parsed.verdict.value}",
        "",
        "## Summary",
        parsed.summary,
        "",
    ]

    if parsed.issues:
        lines.append("## Issues")
        for i, issue in enumerate(parsed.issues, 1):
            lines.append(f"{i}. **[{issue.severity.value}]** {issue.description}")
            if issue.rationale:
                lines.append(f"   - Rationale: {issue.rationale}")
        lines.append("")

    path = output_dir / filename
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run_e2e_loop(
    feature: str,
    max_rounds: int,
    planner_model: str,
    reviewer_model: str,
    conn: sqlite3.Connection,
    session_id: str,
    output_dir: Path,
    self_review: bool = False,
) -> dict:
    """Run the full plan -> review -> revise -> review -> GO loop.

    If self_review=True, adds a bounded self-review pipeline after each
    revision (self-check → repair → wrap-up) before sending to GPT.

    Returns a summary dict with round details, costs, artifacts, etc.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    wall_start = time.time()
    artifacts: list[str] = []
    round_details: list[dict] = []
    total_claude_cost = 0.0
    total_gpt_cost = 0.0

    # Initialize OpenAI client
    gpt_client = OpenAI()

    # ── Step 1: Generate initial plan via Claude ──
    update_session_phase(conn, session_id, "planning")

    plan_result = await generate_initial_plan(feature, planner_model)
    current_plan = plan_result["plan_text"]
    initial_plan_duration_ms = plan_result["duration_ms"]
    initial_plan_cost = plan_result["cost_usd"] or 0.0
    total_claude_cost += initial_plan_cost

    # Store in DB
    draft_num = 1
    add_plan_draft(conn, session_id, draft_num, current_plan)
    add_message(
        conn, session_id, "planner",
        f"Generated initial plan ({initial_plan_duration_ms}ms, "
        f"${initial_plan_cost:.4f}). Draft #{draft_num}.",
    )

    # Export a-01-plan.md
    plan_path = _export_plan(current_plan, 1, output_dir)
    artifacts.append(plan_path.name)

    # ── Step 2: Review loop ──
    update_session_phase(conn, session_id, "review")
    converged = False

    for round_num in range(1, max_rounds + 1):
        round_info: dict = {"round": round_num}

        # ── Review current plan via GPT ──
        review_result = run_review(gpt_client, current_plan, reviewer_model)
        parsed: ReviewerResponse = review_result["parsed"]

        review_latency_s = review_result["latency_s"]
        review_cost = review_result["estimated_cost_usd"]
        total_gpt_cost += review_cost

        round_info["review_verdict"] = parsed.verdict.value
        round_info["review_issue_count"] = len(parsed.issues)
        round_info["review_latency_s"] = review_latency_s
        round_info["review_cost_usd"] = review_cost

        # Store review in DB
        issues_json = json.dumps([
            {
                "severity": iss.severity.value,
                "description": iss.description,
                "rationale": iss.rationale,
            }
            for iss in parsed.issues
        ])
        add_review(
            conn, session_id, round_num,
            parsed.verdict.value, issues_json,
            parsed.summary, review_result["raw_response"],
        )
        add_message(
            conn, session_id, "planner",
            f"Review #{round_num}: {parsed.verdict.value} "
            f"({len(parsed.issues)} issues, {review_latency_s:.1f}s, ${review_cost:.4f}).",
        )

        # Export review artifact: a-{2*round_num:02d}-review.md
        review_artifact_num = 2 * round_num
        review_path = _export_review(review_result, parsed, review_artifact_num, output_dir)
        artifacts.append(review_path.name)

        # ── Check verdict ──
        if parsed.verdict == Verdict.GO:
            # Export final plan: a-{2*draft_num-1:02d}-plan-final.md
            final_artifact_num = 2 * draft_num - 1
            final_path = _export_plan(current_plan, final_artifact_num, output_dir, suffix="-final")
            artifacts.append(final_path.name)

            update_session_status(conn, session_id, "complete")
            converged = True

            round_info["revision_duration_ms"] = None
            round_info["revision_cost_usd"] = None
            round_details.append(round_info)
            break

        # ── NO_GO: Revise plan via Claude ──
        revision_result = await revise_plan(current_plan, parsed, planner_model)
        current_plan = revision_result["plan_text"]
        revision_duration_ms = revision_result["duration_ms"]
        revision_cost = revision_result["cost_usd"] or 0.0
        total_claude_cost += revision_cost

        round_info["revision_duration_ms"] = revision_duration_ms
        round_info["revision_cost_usd"] = revision_cost

        # ── Self-review (if enabled) ──
        self_review_cost = 0.0
        self_review_duration_ms = 0
        self_review_steps = 0
        self_review_found_problems = False

        if self_review:
            sr_result = await run_self_review(current_plan, planner_model)
            current_plan = sr_result["plan_text"]
            self_review_cost = sr_result["total_cost_usd"]
            self_review_duration_ms = sr_result["total_duration_ms"]
            self_review_steps = sr_result["steps_run"]
            self_review_found_problems = sr_result["self_check_found_problems"]
            total_claude_cost += self_review_cost

            add_message(
                conn, session_id, "planner",
                f"Self-review: {'found problems, repaired' if self_review_found_problems else 'clean'} "
                f"({self_review_steps} steps, {self_review_duration_ms}ms, "
                f"${self_review_cost:.4f}).",
            )

        round_info["self_review_cost_usd"] = self_review_cost
        round_info["self_review_duration_ms"] = self_review_duration_ms
        round_info["self_review_steps"] = self_review_steps
        round_info["self_review_found_problems"] = self_review_found_problems

        # Store revised plan in DB (after self-review if enabled)
        draft_num += 1
        add_plan_draft(conn, session_id, draft_num, current_plan)
        add_message(
            conn, session_id, "planner",
            f"Revised plan -> draft #{draft_num} ({revision_duration_ms}ms, "
            f"${revision_cost:.4f}).",
        )

        # Export revised plan: a-{2*draft_num-1:02d}-plan.md
        plan_artifact_num = 2 * draft_num - 1
        plan_path = _export_plan(current_plan, plan_artifact_num, output_dir)
        artifacts.append(plan_path.name)

        round_details.append(round_info)

    else:
        # max_rounds exhausted without GO
        add_message(
            conn, session_id, "planner",
            f"Review loop did not converge after {max_rounds} rounds.",
        )

    wall_end = time.time()
    total_duration_s = wall_end - wall_start
    total_cost = total_claude_cost + total_gpt_cost

    return {
        "rounds": len(round_details),
        "converged": converged,
        "round_details": round_details,
        "total_duration_s": total_duration_s,
        "total_cost_usd": total_cost,
        "total_claude_cost_usd": total_claude_cost,
        "total_gpt_cost_usd": total_gpt_cost,
        "artifacts": artifacts,
        "initial_plan_duration_ms": initial_plan_duration_ms,
        "initial_plan_cost_usd": initial_plan_cost,
    }


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _count_issues_by_severity(round_info: dict, review_result: dict | None = None) -> str:
    """Build a severity breakdown string like '2 critical, 3 major, 2 minor'."""
    # We only have the count in round_details; for the full breakdown we'd
    # need the parsed response. Use the count as fallback.
    count = round_info.get("review_issue_count", 0)
    if count == 0:
        return "0 issues"
    return f"{count} issues"


def print_results(
    feature: str,
    planner_model: str,
    reviewer_model: str,
    summary: dict,
    db_checks: list[tuple[str, bool, str]],
) -> None:
    """Print the full E2E results summary."""
    print()
    print("POC 5b: End-to-End Review Loop")
    print("\u2550" * 55)
    # Truncate feature for display
    display_feature = feature if len(feature) <= 60 else feature[:57] + "..."
    print(f"Feature:  {display_feature}")
    print(f"Planner:  {planner_model}")
    print(f"Reviewer: {reviewer_model}")

    for rd in summary["round_details"]:
        round_num = rd["round"]
        verdict = rd["review_verdict"]
        issue_count = rd["review_issue_count"]
        review_lat = rd["review_latency_s"]
        review_cost = rd["review_cost_usd"]

        print(f"\n\u2500\u2500 Round {round_num} {'─' * (48 - len(str(round_num)))}")

        issue_str = f"{issue_count} issues" if issue_count != 1 else "1 issue"
        print(f"Review:   {verdict} ({issue_str})")

        rev_dur = rd.get("revision_duration_ms")
        rev_cost = rd.get("revision_cost_usd")

        if rev_dur is not None:
            rev_dur_s = rev_dur / 1000.0
            sr_dur = rd.get("self_review_duration_ms", 0) or 0
            sr_dur_s = sr_dur / 1000.0
            sr_cost = rd.get("self_review_cost_usd", 0) or 0.0
            total_lat = review_lat + rev_dur_s + sr_dur_s
            total_round_cost = review_cost + (rev_cost or 0.0) + sr_cost

            if sr_dur > 0:
                sr_problems = rd.get("self_review_found_problems", False)
                sr_steps = rd.get("self_review_steps", 0)
                sr_label = f"self-review: {'repair+wrapup' if sr_problems else 'wrapup'} [{sr_steps} steps]"
                print(
                    f"Latency:  {review_lat:.1f}s (review) + "
                    f"{rev_dur_s:.1f}s (revision) + "
                    f"{sr_dur_s:.1f}s ({sr_label}) = {total_lat:.1f}s"
                )
                print(
                    f"Cost:     ${review_cost:.3f} (review) + "
                    f"${rev_cost or 0:.3f} (revision) + "
                    f"${sr_cost:.3f} (self-review) = ${total_round_cost:.3f}"
                )
            else:
                print(
                    f"Latency:  {review_lat:.1f}s (review) + "
                    f"{rev_dur_s:.1f}s (revision) = {total_lat:.1f}s"
                )
                print(
                    f"Cost:     ${review_cost:.3f} (review) + "
                    f"${rev_cost or 0:.3f} (revision) = ${total_round_cost:.3f}"
                )
        else:
            print(f"Latency:  {review_lat:.1f}s (review)")
            print(f"Cost:     ${review_cost:.3f} (review)")

    # ── Summary ──
    print(f"\n{'═' * 55}")
    rounds = summary["rounds"]
    if summary["converged"]:
        print(f"Result:     CONVERGED in {rounds} round{'s' if rounds != 1 else ''}")
    else:
        print(f"Result:     DID NOT CONVERGE after {rounds} rounds")

    init_dur_s = summary["initial_plan_duration_ms"] / 1000.0
    loop_dur_s = summary["total_duration_s"] - init_dur_s
    print(
        f"Total time: {summary['total_duration_s']:.1f}s "
        f"(plan: {init_dur_s:.1f}s + loop: {loop_dur_s:.1f}s)"
    )
    print(
        f"Total cost: ${summary['total_cost_usd']:.3f} "
        f"(Claude: ${summary['total_claude_cost_usd']:.3f}, "
        f"GPT: ${summary['total_gpt_cost_usd']:.3f})"
    )

    # Artifacts
    print(f"\nArtifacts:")
    for name in summary["artifacts"]:
        print(f"  {name}")

    # DB verification
    print(f"\nDB Verification:")
    for i, (name, passed, detail) in enumerate(db_checks, 1):
        status = "PASS" if passed else "FAIL"
        print(f" {i:>2} \u2502 {name:<22} \u2502 {status:<4} \u2502 {detail}")

    print("\u2550" * 55)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="POC 5b: End-to-End Review Loop (plan -> review -> revise -> GO)"
    )
    parser.add_argument(
        "--feature",
        type=str,
        default=DEFAULT_FEATURE,
        help=f"Feature description (default: '{DEFAULT_FEATURE}')",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=DEFAULT_MAX_ROUNDS,
        help=f"Maximum review/revise rounds (default: {DEFAULT_MAX_ROUNDS})",
    )
    parser.add_argument(
        "--planner-model",
        type=str,
        default=DEFAULT_PLANNER_MODEL,
        help=f"Claude model for planning (default: {DEFAULT_PLANNER_MODEL})",
    )
    parser.add_argument(
        "--reviewer-model",
        type=str,
        default=DEFAULT_REVIEWER_MODEL,
        help=f"GPT model for reviewing (default: {DEFAULT_REVIEWER_MODEL})",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for artifacts (default: temp directory)",
    )
    parser.add_argument(
        "--self-review",
        action="store_true",
        default=False,
        help="Enable bounded self-review after each revision (self-check → repair → wrap-up)",
    )
    args = parser.parse_args()

    # Load .env from repo root for API keys
    repo_root = Path(__file__).resolve().parents[3]
    load_dotenv(repo_root / ".env")

    # Determine output directory
    if args.output_dir is not None:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(tempfile.mkdtemp(prefix="poc_e2e_"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize in-memory DB
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)

    # Create session
    session_id = create_session(conn, "poc-e2e-review-loop")

    print(f"POC 5b: End-to-End Review Loop")
    print(f"{'=' * 55}")
    print(f"Feature:    {args.feature}")
    print(f"Planner:    {args.planner_model}")
    print(f"Reviewer:   {args.reviewer_model}")
    print(f"Max rounds: {args.max_rounds}")
    print(f"Self-review: {'ON' if args.self_review else 'OFF'}")
    print(f"Output:     {output_dir}")
    print(f"Session:    {session_id}")
    print(f"{'=' * 55}")
    print("Running...\n")

    # Run the E2E loop
    summary = asyncio.run(
        run_e2e_loop(
            feature=args.feature,
            max_rounds=args.max_rounds,
            planner_model=args.planner_model,
            reviewer_model=args.reviewer_model,
            conn=conn,
            session_id=session_id,
            output_dir=output_dir,
            self_review=args.self_review,
        )
    )

    # Determine expected counts for DB verification
    # Drafts: 1 initial + 1 per NO_GO round (all rounds except the final GO round, if converged)
    nogo_rounds = sum(
        1 for rd in summary["round_details"]
        if rd["review_verdict"] != "GO"
    )
    expected_drafts = 1 + nogo_rounds
    expected_reviews = summary["rounds"]

    # DB verification
    db_checks = verify_db_consistency(conn, session_id, expected_drafts, expected_reviews)

    # Print results
    print_results(
        args.feature,
        args.planner_model,
        args.reviewer_model,
        summary,
        db_checks,
    )

    print(f"\nOutput directory: {output_dir}")

    conn.close()


if __name__ == "__main__":
    main()
