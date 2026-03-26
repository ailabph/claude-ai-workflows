#!/usr/bin/env python3
"""POC 1a: Reviewer Direct API

Validate GPT-5.4 as a plan reviewer via the OpenAI API.

Steps:
  1. Load a sample milestone plan (hardcoded or from file)
  2. Construct a review prompt that requests structured GO/NO_GO output
  3. Call GPT-5.4 via OpenAI SDK
  4. Capture raw response
  5. Attempt to parse response into ReviewerResponse schema:
     - verdict: GO | NO_GO
     - issues: [{ severity: critical|major|minor, description, rationale }]
     - summary: str
  6. Print results: parsed response, latency, token usage, estimated cost
  7. Optionally run 3 times to test consistency

Usage:
  export OPENAI_API_KEY="your-key"
  python scripts/poc/planner-auto/poc_reviewer_direct_api.py
  python scripts/poc/planner-auto/poc_reviewer_direct_api.py --plan path/to/plan.md
  python scripts/poc/planner-auto/poc_reviewer_direct_api.py --runs 3
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Import POC 2a parser from sibling module
sys.path.insert(0, str(Path(__file__).parent))
from poc_parse_go_nogo import ReviewerResponse, Verdict, parse_reviewer_response


# ---------------------------------------------------------------------------
# Sample plan (intentionally flawed for reviewer to critique)
# ---------------------------------------------------------------------------

SAMPLE_PLAN = """\
# Implementation Plan: Add Product Search API

## Milestone 1: Database Schema & Model Layer
- Add `products` table with columns: id, name, description, price, category, created_at
- Add `product_tags` join table for many-to-many tag relationships
- Create SQLAlchemy models for Product and ProductTag
- Add Alembic migration script for the new tables
- Seed script with 50 sample products for development

Deliverables: Migration runs cleanly, models import without errors, seed data loads.

## Milestone 2: Search Endpoint & Query Logic
- Implement GET /api/v1/products/search endpoint
- Support query parameters: q (text search), category, min_price, max_price, tags
- Full-text search using PostgreSQL tsvector on name + description
- Pagination with limit/offset (default 20 per page)
- Return results sorted by relevance score

Deliverables: Endpoint returns filtered results, pagination works, relevance sorting is correct.

## Milestone 3: Integration & Deployment
- Add OpenAPI/Swagger documentation for the new endpoint
- Configure CORS for frontend consumption
- Add Redis caching layer for frequent queries (TTL: 5 min)
- Update CI pipeline to include the new migration
- Deploy to staging environment and run smoke tests

Deliverables: Swagger docs accessible, caching reduces repeat query latency, staging deploy succeeds.
"""

# NOTE: Deliberate gaps in this plan:
# - Milestone 2 has NO error handling (what if DB is down? invalid params?)
# - Milestone 2 has NO unit/integration tests
# - Milestone 3 jumps straight to deployment with no load testing or rollback strategy


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a senior software engineering plan reviewer. Your job is to evaluate \
implementation plans for readiness, completeness, and risk.

Review the plan provided by the user and return a structured JSON response with \
exactly this schema:

{
  "verdict": "GO" or "NO_GO",
  "issues": [
    {
      "severity": "critical" | "major" | "minor",
      "description": "Brief description of the issue",
      "rationale": "Why this matters and what could go wrong"
    }
  ],
  "summary": "One-paragraph summary of your overall assessment"
}

Severity guidelines:
- critical: Blocks implementation. Missing error handling, security gaps, no tests \
for core logic, architectural flaws that would require rework.
- major: Should be fixed before starting. Missing migration steps, incomplete API \
contracts, no rollback strategy, gaps in observability.
- minor: Nice to have. Style inconsistencies, optional optimizations, documentation \
improvements.

Verdict guidelines:
- GO: Plan is ready for implementation. May have minor issues but nothing blocking.
- NO_GO: Plan has critical or multiple major issues that must be addressed first.

Be thorough but concise. Focus on practical engineering risks, not theoretical ones. \
Return ONLY the JSON object, no additional text."""

USER_PROMPT_TEMPLATE = """\
Please review the following implementation plan and provide your structured \
GO/NO_GO assessment:

---
{plan_text}
---"""


# ---------------------------------------------------------------------------
# Core review function
# ---------------------------------------------------------------------------

def run_review(client: OpenAI, plan_text: str, model: str) -> dict:
    """Run a single plan review via the OpenAI API.

    Returns a dict with raw response, parsed result, and metrics.
    """
    user_prompt = USER_PROMPT_TEMPLATE.format(plan_text=plan_text)

    start = time.time()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,  # low temp for consistency
    )
    latency_s = time.time() - start

    raw_response = response.choices[0].message.content or ""
    parsed = parse_reviewer_response(raw_response)

    # Token usage
    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    total_tokens = (usage.total_tokens if usage else 0) or (prompt_tokens + completion_tokens)

    # Estimated cost (approximate GPT-5.4 pricing — placeholder rates)
    # Input: ~$2.00/1M tokens, Output: ~$8.00/1M tokens
    estimated_cost_usd = (prompt_tokens * 2.00 / 1_000_000) + (completion_tokens * 8.00 / 1_000_000)

    # Parse success: True unless we got the canonical parse-failure response
    parse_success = not (
        parsed.summary == "Parse failure — treating as NO_GO"
        and len(parsed.issues) == 1
        and parsed.issues[0].description == "Reviewer output could not be parsed"
    )

    return {
        "raw_response": raw_response,
        "parsed": parsed,
        "latency_s": latency_s,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": estimated_cost_usd,
        "parse_success": parse_success,
    }


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_result(run_num: int, result: dict) -> None:
    """Print formatted results for a single review run."""
    parsed: ReviewerResponse = result["parsed"]

    print(f"\n── Run {run_num} {'─' * (50 - len(str(run_num)))}")
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
    print(
        f"  Tokens:       {result['total_tokens']:,} "
        f"(prompt: {result['prompt_tokens']:,}, "
        f"completion: {result['completion_tokens']:,})"
    )
    print(f"  Est. cost:    ${result['estimated_cost_usd']:.4f}")
    print(f"  Parse OK:     {'Yes' if result['parse_success'] else 'No'}")


def print_consistency_summary(results: list[dict]) -> None:
    """Print a consistency summary across multiple runs."""
    n = len(results)
    verdicts = [r["parsed"].verdict.value for r in results]
    parse_successes = sum(1 for r in results if r["parse_success"])

    # Check consistency
    unique_verdicts = set(verdicts)
    if len(unique_verdicts) == 1:
        consistency_str = f"{n}/{n} consistent"
    else:
        consistency_str = f"{len(unique_verdicts)} distinct verdicts"

    avg_latency = sum(r["latency_s"] for r in results) / n
    avg_tokens = sum(r["total_tokens"] for r in results) / n
    avg_cost = sum(r["estimated_cost_usd"] for r in results) / n

    print(f"\n── Consistency Summary ({n} runs) {'─' * (30 - len(str(n)))}")
    print(f"Verdicts:     {', '.join(verdicts)} ({consistency_str})")
    print(f"Parse rate:   {parse_successes}/{n} successful")
    print(f"Avg latency:  {avg_latency:.1f}s")
    print(f"Avg tokens:   {avg_tokens:,.0f}")
    print(f"Avg cost:     ${avg_cost:.4f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="POC 1a: Validate GPT-5.4 as a plan reviewer via OpenAI API"
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=None,
        help="Path to a plan file (default: use hardcoded sample plan)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of review runs (default: 1)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-5.4",
        help="OpenAI model to use (default: gpt-5.4)",
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

    # Initialize client (auto-reads OPENAI_API_KEY from env)
    client = OpenAI()

    print(f"POC 1a: Reviewer Direct API ({args.model})")
    print(f"{'═' * 56}")
    print(f"Plan length: {len(plan_text):,} chars")
    print(f"Runs:        {args.runs}")

    results: list[dict] = []

    for i in range(1, args.runs + 1):
        try:
            result = run_review(client, plan_text, args.model)
            results.append(result)
            print_result(i, result)
        except Exception as exc:
            print(f"\n── Run {i} {'─' * (50 - len(str(i)))}")
            print(f"ERROR: {type(exc).__name__}: {exc}")
            continue

    # Consistency summary for multiple runs
    if len(results) > 1:
        print_consistency_summary(results)

    # Final status
    print(f"\n{'═' * 56}")
    print(f"Completed {len(results)}/{args.runs} runs successfully.")


if __name__ == "__main__":
    main()
