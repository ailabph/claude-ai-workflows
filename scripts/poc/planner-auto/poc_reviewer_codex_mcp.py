#!/usr/bin/env python3
"""POC 1b: Reviewer via Codex MCP

Validate GPT-5.4 invocation through Codex MCP within Claude's agent loop.

Prerequisites:
  npm install -g @openai/codex
  claude mcp add codex -s user -- codex mcp-server

Steps:
  1. Load same sample plan as POC 1a
  2. Invoke Claude via Agent SDK with:
     - System prompt: "You are a plan review coordinator"
     - User prompt: "Use the Codex MCP tool to ask GPT-5.4 to review
       this plan for go/no-go"
     - MCP config including codex server
  3. Claude invokes GPT through MCP tool
  4. Capture Claude's response (which includes GPT's review)
  5. Parse into ReviewerResponse schema
  6. Measure: total latency, token usage (both Claude and GPT),
     estimated cost
  7. Note whether GPT accessed repo files through MCP tools
  8. Print comparison against POC 1a results if available

Usage:
  export OPENAI_API_KEY="your-key"
  export ANTHROPIC_API_KEY="your-key"
  python scripts/poc/planner-auto/poc_reviewer_codex_mcp.py
  python scripts/poc/planner-auto/poc_reviewer_codex_mcp.py --plan path/to/plan.md
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

from claude_agent_sdk import query
from claude_agent_sdk.types import (
    AssistantMessage,
    ClaudeAgentOptions,
    McpStdioServerConfig,
    ResultMessage,
)

# Import POC 2a parser and POC 1a sample plan from sibling modules
sys.path.insert(0, str(Path(__file__).parent))
from poc_parse_go_nogo import parse_reviewer_response, ReviewerResponse, Verdict
from poc_reviewer_direct_api import SAMPLE_PLAN


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

COORDINATOR_SYSTEM_PROMPT = """\
You are a plan review coordinator. Your job is to send the implementation plan \
to the Codex tool for a go/no-go review by GPT, then relay GPT's structured \
review back to me exactly as GPT returns it.

Instructions:
1. Use the Codex MCP tool to ask GPT to review the plan
2. Tell GPT to return its review as JSON with this schema:
   {"verdict": "GO" or "NO_GO", "issues": [{"severity": "critical|major|minor", \
    "description": "...", "rationale": "..."}], "summary": "..."}
3. Return GPT's JSON response to me verbatim, without modification

Do NOT add your own analysis. Just relay GPT's review."""

USER_PROMPT_TEMPLATE = """\
Please send the following implementation plan to the Codex tool for a go/no-go \
review by GPT. Ask GPT to return a structured JSON review.

---
{plan_text}
---"""


# ---------------------------------------------------------------------------
# Core review function
# ---------------------------------------------------------------------------

async def run_codex_review(plan_text: str, model: str) -> dict:
    """Run a single plan review via the Codex MCP tool within Claude's agent loop.

    Args:
        plan_text: The implementation plan text to review.
        model: The Claude model to use as the coordinator.

    Returns:
        Dict with raw response, parsed result, and metrics.
    """
    # Locate the codex binary
    codex_path = shutil.which("codex")
    if codex_path is None:
        print("Error: 'codex' command not found in PATH.")
        print()
        print("Setup instructions:")
        print("  npm install -g @openai/codex")
        print()
        print("Then verify it's available:")
        print("  codex --version")
        sys.exit(1)

    # Verify OPENAI_API_KEY is set (Codex needs it to authenticate with OpenAI)
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable is not set.")
        print()
        print("The Codex MCP server requires an OpenAI API key to invoke GPT.")
        print("  export OPENAI_API_KEY=\"your-key\"")
        sys.exit(1)

    user_prompt = USER_PROMPT_TEMPLATE.format(plan_text=plan_text)

    # Note: Codex MCP server authenticates via stored credentials from `codex login`.
    # If you get 401 errors, run: echo "$OPENAI_API_KEY" | codex login --with-api-key
    options = ClaudeAgentOptions(
        system_prompt=COORDINATOR_SYSTEM_PROMPT,
        model=model,
        max_turns=5,  # needs multiple turns: Claude sends to Codex, gets response back
        permission_mode="bypassPermissions",
        mcp_servers={
            "codex": McpStdioServerConfig(
                command=codex_path,
                args=["mcp-server"],
            ),
        },
        stderr=lambda s: None,
    )

    result_msg: ResultMessage | None = None
    assistant_messages: list[AssistantMessage] = []

    try:
        async for message in query(prompt=user_prompt, options=options):
            if isinstance(message, AssistantMessage):
                assistant_messages.append(message)
            if isinstance(message, ResultMessage):
                result_msg = message
    except Exception as exc:
        return {
            "raw_response": "",
            "parsed": parse_reviewer_response(""),
            "latency_s": 0.0,
            "total_cost_usd": None,
            "usage": None,
            "parse_success": False,
            "num_turns": 0,
            "error": f"MCP connection failed: {type(exc).__name__}: {exc}",
        }

    # Extract response text
    raw_response = (result_msg.result or "") if result_msg else ""
    latency_s = (result_msg.duration_ms / 1000.0) if result_msg else 0.0
    total_cost_usd = result_msg.total_cost_usd if result_msg else None
    usage = result_msg.usage if result_msg else None
    num_turns = result_msg.num_turns if result_msg else 0

    # Parse the response through the POC 2a parser
    parsed = parse_reviewer_response(raw_response)

    # Detect whether Claude actually invoked the Codex tool or reviewed itself
    parse_success = not (
        parsed.summary == "Parse failure \u2014 treating as NO_GO"
        and len(parsed.issues) == 1
        and parsed.issues[0].description == "Reviewer output could not be parsed"
    )

    result: dict = {
        "raw_response": raw_response,
        "parsed": parsed,
        "latency_s": latency_s,
        "total_cost_usd": total_cost_usd,
        "usage": usage,
        "parse_success": parse_success,
        "num_turns": num_turns,
    }

    # Note if Claude didn't seem to use Codex (low turn count may indicate self-review)
    if num_turns <= 1 and parse_success:
        result["note"] = (
            "Warning: Claude completed in 1 turn. It may have reviewed the plan "
            "itself instead of invoking the Codex MCP tool."
        )

    return result


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_result(result: dict, run_num: int | None = None) -> None:
    """Print formatted results for a single Codex MCP review run."""
    parsed: ReviewerResponse = result["parsed"]

    label = f"Run {run_num}" if run_num is not None else "Codex MCP Review"
    print(f"\n\u2500\u2500 {label} {'─' * (53 - len(label))}")

    if "error" in result:
        print(f"ERROR: {result['error']}")
        return

    print(f"Verdict:    {parsed.verdict.value}")
    print(f"Summary:    {parsed.summary}")

    if parsed.issues:
        print(f"Issues ({len(parsed.issues)}):")
        for issue in parsed.issues:
            print(f"  [{issue.severity.value}] {issue.description}")
            if issue.rationale:
                print(f"{'':14}Rationale: {issue.rationale}")
    else:
        print("Issues:     None")

    print()
    print("Metrics:")
    print(f"  Latency:      {result['latency_s']:.1f}s")
    if result["total_cost_usd"] is not None:
        print(f"  Cost:         ${result['total_cost_usd']:.4f}")
    else:
        print("  Cost:         N/A")
    print(f"  Turns:        {result['num_turns']}")
    print(f"  Parse OK:     {'Yes' if result['parse_success'] else 'No'}")

    if result.get("note"):
        print(f"\n  Note: {result['note']}")

    if not result["parse_success"]:
        raw = result.get("raw_response", "")
        print(f"\n  Raw response (first 500 chars):")
        print(f"  {raw[:500]}")


def print_comparison(result: dict) -> None:
    """Print comparison against POC 1a direct API baseline."""
    print(f"\n\u2500\u2500 Comparison vs Direct API (POC 1a baseline) {'─' * 10}")
    print("Note: Direct API baseline from POC 1a:")
    print("  Avg latency: ~14s, Avg cost: ~$0.007, Parse: 3/3")
    print()
    print("Codex MCP result:")

    latency = result["latency_s"]
    if latency > 0:
        ratio = latency / 14.0
        print(
            f"  Latency: {latency:.1f}s ({ratio:.1f}x "
            f"{'slower' if ratio > 1 else 'faster'} "
            "\u2014 expected due to Claude+GPT round-trip)"
        )
    else:
        print("  Latency: N/A")

    if result["total_cost_usd"] is not None:
        print(
            f"  Cost: ${result['total_cost_usd']:.4f} "
            "(higher \u2014 pays for both Claude and GPT tokens)"
        )
    else:
        print("  Cost: N/A")

    print(f"  Parse: {'OK' if result['parse_success'] else 'FAILED'}")


def print_consistency_summary(results: list[dict]) -> None:
    """Print a consistency summary across multiple runs."""
    # Filter out error runs
    valid = [r for r in results if "error" not in r]
    n = len(results)
    n_valid = len(valid)

    verdicts = [r["parsed"].verdict.value for r in valid]
    parse_successes = sum(1 for r in valid if r["parse_success"])

    unique_verdicts = set(verdicts)
    if len(unique_verdicts) == 1 and n_valid > 0:
        consistency_str = f"{n_valid}/{n_valid} consistent"
    elif n_valid > 0:
        consistency_str = f"{len(unique_verdicts)} distinct verdicts"
    else:
        consistency_str = "no valid runs"

    print(f"\n\u2500\u2500 Consistency Summary ({n} runs) {'─' * (30 - len(str(n)))}")

    if n_valid == 0:
        print("  No successful runs to summarize.")
        return

    print(f"Verdicts:     {', '.join(verdicts)} ({consistency_str})")
    print(f"Parse rate:   {parse_successes}/{n_valid} successful")

    avg_latency = sum(r["latency_s"] for r in valid) / n_valid
    print(f"Avg latency:  {avg_latency:.1f}s")

    costs = [r["total_cost_usd"] for r in valid if r["total_cost_usd"] is not None]
    if costs:
        avg_cost = sum(costs) / len(costs)
        print(f"Avg cost:     ${avg_cost:.4f}")
    else:
        print("Avg cost:     N/A")

    avg_turns = sum(r["num_turns"] for r in valid) / n_valid
    print(f"Avg turns:    {avg_turns:.1f}")

    if n_valid < n:
        print(f"Errors:       {n - n_valid}/{n} runs failed")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="POC 1b: Validate GPT-5.4 invocation through Codex MCP within Claude's agent loop"
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=None,
        help="Path to a plan file (default: use hardcoded sample plan from POC 1a)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-6",
        help="Claude model for the coordinator (default: claude-sonnet-4-6). "
             "GPT model is determined by Codex.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of review runs (default: 1)",
    )
    args = parser.parse_args()

    # Load .env from repo root
    repo_root = Path(__file__).resolve().parents[3]
    load_dotenv(repo_root / ".env")

    # Load plan text
    if args.plan is not None:
        plan_path = Path(args.plan)
        if not plan_path.exists():
            print(f"Error: plan file not found: {plan_path}")
            sys.exit(1)
        plan_text = plan_path.read_text()
    else:
        plan_text = SAMPLE_PLAN

    print(f"POC 1b: Reviewer via Codex MCP ({args.model})")
    print(f"{'=' * 56}")
    print(f"Plan length: {len(plan_text):,} chars")
    print(f"Runs:        {args.runs}")
    print(f"Coordinator: {args.model}")
    print(f"Reviewer:    GPT (via Codex MCP)")

    results: list[dict] = []

    for i in range(1, args.runs + 1):
        try:
            result = asyncio.run(run_codex_review(plan_text, args.model))
            results.append(result)
            print_result(result, run_num=i if args.runs > 1 else None)
        except Exception as exc:
            print(f"\n\u2500\u2500 Run {i} {'─' * (50 - len(str(i)))}")
            print(f"ERROR: {type(exc).__name__}: {exc}")
            continue

    # Print comparison against POC 1a baseline (use last successful result)
    valid_results = [r for r in results if "error" not in r]
    if valid_results:
        print_comparison(valid_results[-1])

    # Consistency summary for multiple runs
    if len(results) > 1:
        print_consistency_summary(results)

    # Final status
    print(f"\n{'=' * 56}")
    print(f"Completed {len(results)}/{args.runs} runs successfully.")


if __name__ == "__main__":
    main()
