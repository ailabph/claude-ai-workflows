#!/usr/bin/env python3
"""POC 1c: Reviewer via OpenCode HTTP Server

Validate GPT-5.4 invocation through OpenCode's HTTP server API.

Prerequisites:
  opencode serve  # run in separate terminal or background

Steps:
  1. Check if opencode server is running (health check)
  2. If not running, print setup instructions and exit
  3. Load same sample plan as POC 1a
  4. Create a new session via HTTP API:
     POST /session
  5. Send review prompt to session:
     POST /session/{id}/message
     Body: structured review prompt with plan content
  6. Poll or stream for response completion
  7. Extract response content
  8. Parse into ReviewerResponse schema
  9. Measure: latency (including server overhead), token usage
  10. Clean up: optionally delete session
  11. Print comparison against POC 1a and 1b results if available

Usage:
  # Terminal 1: start server
  opencode serve

  # Terminal 2: run POC
  python scripts/poc/planner-auto/poc_reviewer_opencode_http.py
  python scripts/poc/planner-auto/poc_reviewer_opencode_http.py --plan path/to/plan.md
  python scripts/poc/planner-auto/poc_reviewer_opencode_http.py --server-url http://localhost:4096
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

# Import POC 2a parser and POC 1a sample plan / system prompt from sibling modules
sys.path.insert(0, str(Path(__file__).parent))
from poc_parse_go_nogo import parse_reviewer_response, ReviewerResponse, Verdict
from poc_reviewer_direct_api import SAMPLE_PLAN, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

REQUEST_TIMEOUT = 120  # seconds


# ---------------------------------------------------------------------------
# Server management
# ---------------------------------------------------------------------------

def check_server(base_url: str) -> bool:
    """Check if the OpenCode HTTP server is running.

    Sends GET /global/health and returns True if the response is 200.
    """
    try:
        resp = requests.get(f"{base_url}/global/health", timeout=5)
        return resp.status_code == 200
    except requests.ConnectionError:
        return False
    except requests.Timeout:
        return False


def _print_server_instructions(base_url: str) -> None:
    """Print setup instructions when the server is not running."""
    print(f"Error: OpenCode server is not running at {base_url}")
    print()
    print("Setup instructions:")
    print("  # Install opencode if you haven't already")
    print("  go install github.com/opencode-ai/opencode@latest")
    print()
    print("  # Start the server in a separate terminal")
    port = base_url.rsplit(":", 1)[-1].rstrip("/")
    print(f"  opencode serve --port {port}")
    print()
    print("  # Then re-run this script")
    print(f"  python {Path(__file__).name}")


# ---------------------------------------------------------------------------
# Core review function
# ---------------------------------------------------------------------------

def run_opencode_review(
    plan_text: str,
    base_url: str,
    model_id: str,
) -> dict:
    """Run a single plan review via the OpenCode HTTP server.

    Args:
        plan_text: The implementation plan text to review.
        base_url: Base URL of the OpenCode HTTP server.
        model_id: The model ID to use (e.g. "gpt-5.4").

    Returns:
        Dict with raw response, parsed result, and metrics matching POC 1a
        structure.
    """
    # 1. Health check
    if not check_server(base_url):
        _print_server_instructions(base_url)
        sys.exit(1)

    session_id: str | None = None

    try:
        # 2. Create session
        create_resp = requests.post(
            f"{base_url}/session",
            json={},
            timeout=REQUEST_TIMEOUT,
        )
        create_resp.raise_for_status()
        session_data = create_resp.json()
        session_id = session_data["id"]

        # 3. Send review message
        user_prompt = USER_PROMPT_TEMPLATE.format(plan_text=plan_text)

        message_resp = requests.post(
            f"{base_url}/session/{session_id}/message",
            headers={"Content-Type": "application/json"},
            json={
                "parts": [{"type": "text", "text": user_prompt}],
                "model": {"providerID": "openai", "modelID": model_id},
                "system": SYSTEM_PROMPT,
            },
            timeout=REQUEST_TIMEOUT,
        )
        message_resp.raise_for_status()
        message_data = message_resp.json()

        # 4. Extract response text from parts
        parts = message_data.get("parts", [])
        text_parts = [p["text"] for p in parts if p.get("type") == "text"]
        raw_response = "\n".join(text_parts)

        # 5. Extract metrics from info
        info = message_data.get("info", {})
        cost_usd = info.get("cost", 0.0)

        tokens_info = info.get("tokens", {})
        tokens = {
            "total": tokens_info.get("total", 0),
            "input": tokens_info.get("input", 0),
            "output": tokens_info.get("output", 0),
        }

        # Calculate latency from server timestamps (milliseconds)
        time_info = info.get("time", {})
        created_ms = time_info.get("created", 0)
        completed_ms = time_info.get("completed", 0)
        if created_ms and completed_ms:
            latency_s = (completed_ms - created_ms) / 1000.0
        else:
            latency_s = 0.0

        # 6. Parse response
        parsed = parse_reviewer_response(raw_response)

        # Detect parse success
        parse_success = not (
            parsed.summary == "Parse failure \u2014 treating as NO_GO"
            and len(parsed.issues) == 1
            and parsed.issues[0].description == "Reviewer output could not be parsed"
        )

        return {
            "raw_response": raw_response,
            "parsed": parsed,
            "latency_s": latency_s,
            "cost_usd": cost_usd,
            "tokens": tokens,
            "parse_success": parse_success,
        }

    except requests.HTTPError as exc:
        resp = exc.response
        status = resp.status_code if resp is not None else "N/A"
        body = resp.text[:500] if resp is not None else ""
        print(f"HTTP error {status}: {body}")
        raise

    finally:
        # 7. Always attempt session cleanup
        if session_id is not None:
            try:
                requests.delete(
                    f"{base_url}/session/{session_id}",
                    timeout=10,
                )
            except Exception:
                pass  # Best-effort cleanup


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_result(result: dict, run_num: int | None = None) -> None:
    """Print formatted results for a single OpenCode HTTP review run."""
    parsed: ReviewerResponse = result["parsed"]
    tokens = result["tokens"]

    label = f"Run {run_num}" if run_num is not None else "OpenCode HTTP Review"
    print(f"\n\u2500\u2500 {label} {'─' * (53 - len(label))}")

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
    print(f"  Cost:         ${result['cost_usd']:.3f}")
    print(
        f"  Tokens:       {tokens['total']:,} "
        f"(input: {tokens['input']:,}, output: {tokens['output']:,})"
    )
    print(f"  Parse OK:     {'Yes' if result['parse_success'] else 'No'}")

    if not result["parse_success"]:
        raw = result.get("raw_response", "")
        print(f"\n  Raw response (first 500 chars):")
        print(f"  {raw[:500]}")


def print_comparison(result: dict) -> None:
    """Print comparison table against POC 1a and 1b baselines."""
    tokens = result["tokens"]

    print(f"\n\u2500\u2500 Comparison {'─' * 43}")
    print(f"{'Adapter':<17}\u2502 {'Latency':>7} \u2502 {'Cost':>7} \u2502 Parse")
    print(f"{'─' * 17}\u253c{'─' * 9}\u253c{'─' * 9}\u253c{'─' * 7}")
    print(f"{'Direct API (1a)':<17}\u2502 {'~14s':>7} \u2502 {'~$0.007':>7} \u2502 3/3")
    print(f"{'Codex MCP (1b)':<17}\u2502 {'~31s':>7} \u2502 {'~$0.035':>7} \u2502 1/1")
    print(
        f"{'OpenCode HTTP':<17}\u2502 "
        f"{result['latency_s']:>5.1f}s \u2502 "
        f"${result['cost_usd']:>5.3f} \u2502 "
        f"{'1/1' if result['parse_success'] else '0/1'}"
    )


def print_consistency_summary(results: list[dict]) -> None:
    """Print a consistency summary across multiple runs."""
    valid = [r for r in results if r.get("parse_success") is not None]
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

    avg_cost = sum(r["cost_usd"] for r in valid) / n_valid
    print(f"Avg cost:     ${avg_cost:.3f}")

    avg_tokens = sum(r["tokens"]["total"] for r in valid) / n_valid
    print(f"Avg tokens:   {avg_tokens:,.0f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="POC 1c: Validate GPT-5.4 as a plan reviewer via OpenCode HTTP server"
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=None,
        help="Path to a plan file (default: use hardcoded sample plan from POC 1a)",
    )
    parser.add_argument(
        "--server-url",
        type=str,
        default="http://127.0.0.1:14096",
        help="OpenCode server URL (default: http://127.0.0.1:14096)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-5.4",
        help="Model ID to use (default: gpt-5.4)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of review runs (default: 1)",
    )
    args = parser.parse_args()

    # Load plan text
    if args.plan is not None:
        plan_path = Path(args.plan)
        if not plan_path.exists():
            print(f"Error: plan file not found: {plan_path}")
            sys.exit(1)
        plan_text = plan_path.read_text()
    else:
        plan_text = SAMPLE_PLAN

    print(f"POC 1c: Reviewer via OpenCode HTTP ({args.model})")
    print(f"{'=' * 56}")
    print(f"Plan length: {len(plan_text):,} chars")
    print(f"Server:      {args.server_url}")
    print(f"Model:       {args.model}")
    print(f"Runs:        {args.runs}")

    results: list[dict] = []

    for i in range(1, args.runs + 1):
        try:
            result = run_opencode_review(plan_text, args.server_url, args.model)
            results.append(result)
            print_result(result, run_num=i if args.runs > 1 else None)
        except Exception as exc:
            print(f"\n\u2500\u2500 Run {i} {'─' * (50 - len(str(i)))}")
            print(f"ERROR: {type(exc).__name__}: {exc}")
            continue

    # Print comparison against POC 1a and 1b baselines (use last successful result)
    if results:
        print_comparison(results[-1])

    # Consistency summary for multiple runs
    if len(results) > 1:
        print_consistency_summary(results)

    # Final status
    print(f"\n{'=' * 56}")
    print(f"Completed {len(results)}/{args.runs} runs successfully.")


if __name__ == "__main__":
    main()
