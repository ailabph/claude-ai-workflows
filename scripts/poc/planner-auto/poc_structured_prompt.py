#!/usr/bin/env python3
"""POC 2b: Structured Prompt Testing

Compare prompt strategies for structured reviewer output.

Steps:
  1. Load sample plan
  2. Define prompt variants:
     a. Free-form: "Review this plan. Is it go or no-go?"
     b. JSON-instructed: "Return your review as JSON with fields:
        verdict, issues, summary"
     c. XML-tagged: "Wrap your verdict in <verdict> tags, issues in
        <issues> tags"
     d. Few-shot: Include an example GO and NO_GO response in the prompt
  3. For each variant, call GPT-5.4 three times
  4. Parse each response using poc_parse_go_nogo parser
  5. Record: parse success/fail, latency, token usage, response quality
  6. Print comparison table:
     - Strategy | Parse Success (N/3) | Avg Latency | Avg Tokens | Notes

Usage:
  export OPENAI_API_KEY="your-key"
  python scripts/poc/planner-auto/poc_structured_prompt.py
  python scripts/poc/planner-auto/poc_structured_prompt.py --plan path/to/plan.md
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Import POC 2a parser and POC 1a sample plan from sibling modules
sys.path.insert(0, str(Path(__file__).parent))
from poc_parse_go_nogo import ReviewerResponse, Severity, Verdict, parse_reviewer_response
from poc_reviewer_direct_api import SAMPLE_PLAN


# ---------------------------------------------------------------------------
# Prompt strategies
# ---------------------------------------------------------------------------

STRATEGIES: list[dict[str, str]] = [
    {
        "name": "free_form",
        "system_prompt": "You are a senior software plan reviewer.",
        "user_prompt_template": (
            "Review this implementation plan. Is it go or no-go for "
            "implementation?\n\n{plan}"
        ),
    },
    {
        "name": "json_instructed",
        "system_prompt": (
            "You are a senior software engineering plan reviewer. Your job is "
            "to evaluate implementation plans for readiness, completeness, and "
            "risk.\n\n"
            "Return a structured JSON response with exactly this schema:\n\n"
            '{{\n'
            '  "verdict": "GO" or "NO_GO",\n'
            '  "issues": [\n'
            '    {{\n'
            '      "severity": "critical" | "major" | "minor",\n'
            '      "description": "Brief description of the issue",\n'
            '      "rationale": "Why this matters and what could go wrong"\n'
            '    }}\n'
            '  ],\n'
            '  "summary": "One-paragraph summary of your overall assessment"\n'
            '}}\n\n'
            "Severity guidelines:\n"
            "- critical: Blocks implementation. Missing error handling, security "
            "gaps, no tests for core logic, architectural flaws.\n"
            "- major: Should be fixed before starting. Missing migration steps, "
            "incomplete API contracts, no rollback strategy.\n"
            "- minor: Nice to have. Style inconsistencies, optional "
            "optimizations, documentation improvements.\n\n"
            "Verdict guidelines:\n"
            "- GO: Plan is ready. May have minor issues but nothing blocking.\n"
            "- NO_GO: Plan has critical or multiple major issues that must be "
            "addressed first.\n\n"
            "Return ONLY the JSON object, no additional text."
        ),
        "user_prompt_template": (
            "Review this plan and return your assessment as JSON:\n\n{plan}"
        ),
    },
    {
        "name": "xml_tagged",
        "system_prompt": (
            "You are a senior software plan reviewer. Return your review using "
            "these XML tags:\n\n"
            "<verdict>GO or NO_GO</verdict>\n"
            "<summary>Your overall assessment</summary>\n"
            "<issues>\n"
            "  <issue>\n"
            "    <severity>critical|major|minor</severity>\n"
            "    <description>Brief description of the issue</description>\n"
            "    <rationale>Why this matters</rationale>\n"
            "  </issue>\n"
            "</issues>\n\n"
            "Severity guidelines:\n"
            "- critical: Blocks implementation. Missing error handling, security "
            "gaps, no tests.\n"
            "- major: Should be fixed first. Incomplete contracts, no rollback.\n"
            "- minor: Nice to have. Style, docs, optional optimizations.\n\n"
            "Use GO if the plan is ready (minor issues only). Use NO_GO if there "
            "are critical or multiple major issues.\n\n"
            "Return ONLY the XML tags, no additional text."
        ),
        "user_prompt_template": "Review this plan:\n\n{plan}",
    },
    {
        "name": "few_shot",
        "system_prompt": (
            "You are a senior software plan reviewer. Evaluate plans for "
            "readiness, completeness, and risk. Return your review as JSON.\n\n"
            "Example 1 (GO):\n"
            "```json\n"
            '{\n'
            '  "verdict": "GO",\n'
            '  "issues": [\n'
            '    {\n'
            '      "severity": "minor",\n'
            '      "description": "Consider adding structured logging",\n'
            '      "rationale": "Helpful for debugging but not blocking"\n'
            '    }\n'
            '  ],\n'
            '  "summary": "Plan is well-structured with clear milestones. '
            'One minor suggestion noted."\n'
            '}\n'
            "```\n\n"
            "Example 2 (NO_GO):\n"
            "```json\n"
            '{\n'
            '  "verdict": "NO_GO",\n'
            '  "issues": [\n'
            '    {\n'
            '      "severity": "critical",\n'
            '      "description": "No error handling for database failures",\n'
            '      "rationale": "Production services must handle upstream '
            'failures gracefully"\n'
            '    },\n'
            '    {\n'
            '      "severity": "major",\n'
            '      "description": "No rollback strategy for deployment",\n'
            '      "rationale": "Failed deploys need a documented recovery path"\n'
            '    }\n'
            '  ],\n'
            '  "summary": "Plan has critical gaps in error handling and lacks a '
            'rollback strategy."\n'
            '}\n'
            "```\n\n"
            "Now review the user's plan in the same format."
        ),
        "user_prompt_template": "{plan}",
    },
]


# ---------------------------------------------------------------------------
# Run function
# ---------------------------------------------------------------------------

def _is_parse_failure(parsed: ReviewerResponse) -> bool:
    """Return True if the parsed result is the canonical parse-failure sentinel."""
    return (
        len(parsed.issues) == 1
        and parsed.issues[0].description == "Reviewer output could not be parsed"
    )


def run_strategy(
    client: OpenAI,
    strategy: dict[str, str],
    plan_text: str,
    model: str,
    runs: int = 3,
) -> list[dict]:
    """Run a prompt strategy N times and collect results.

    Each run returns a dict with raw_response, parsed result, latency,
    token usage, and parse success flag.
    """
    results: list[dict] = []

    for _ in range(runs):
        try:
            user_prompt = strategy["user_prompt_template"].format(plan=plan_text)

            start = time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": strategy["system_prompt"]},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            latency_s = time.time() - start

            raw_response = response.choices[0].message.content or ""
            parsed = parse_reviewer_response(raw_response)

            usage = response.usage
            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else 0
            total_tokens = (
                (usage.total_tokens if usage else 0)
                or (prompt_tokens + completion_tokens)
            )

            results.append({
                "raw_response": raw_response,
                "parsed": parsed,
                "latency_s": latency_s,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "parse_success": not _is_parse_failure(parsed),
            })

        except Exception as exc:
            # Don't crash on individual runs — record the failure
            fail_parsed = ReviewerResponse(
                verdict=Verdict.NO_GO,
                issues=[],
                summary=f"Error: {type(exc).__name__}: {exc}",
            )
            results.append({
                "raw_response": "",
                "parsed": fail_parsed,
                "latency_s": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "parse_success": False,
            })

    return results


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_strategy_detail(strategy_name: str, results: list[dict]) -> None:
    """Print per-strategy run-by-run detail."""
    n = len(results)
    print(f"\n\u2500\u2500 Strategy: {strategy_name} ({n} runs) "
          f"{'─' * max(1, 45 - len(strategy_name))}")
    for i, r in enumerate(results, 1):
        parsed: ReviewerResponse = r["parsed"]
        verdict = parsed.verdict.value
        issue_count = len(parsed.issues)
        latency = r["latency_s"]
        total_tok = r["total_tokens"]
        parse_ok = "OK" if r["parse_success"] else "FAIL"
        print(
            f"Run {i}: {verdict:<6} \u2502 {issue_count} issues \u2502 "
            f"{latency:.1f}s \u2502 {total_tok:,} tok \u2502 Parse: {parse_ok}"
        )


def _compute_strategy_stats(results: list[dict]) -> dict:
    """Compute aggregate statistics for one strategy's results."""
    n = len(results)
    parse_ok_count = sum(1 for r in results if r["parse_success"])

    # For averages, only consider successful runs
    successful = [r for r in results if r["parse_success"]]
    if successful:
        avg_latency = sum(r["latency_s"] for r in successful) / len(successful)
        avg_tokens = sum(r["total_tokens"] for r in successful) / len(successful)
        avg_issues = sum(len(r["parsed"].issues) for r in successful) / len(successful)
    else:
        avg_latency = 0.0
        avg_tokens = 0.0
        avg_issues = 0.0

    # Verdict consistency
    verdicts = [r["parsed"].verdict.value for r in results if r["parse_success"]]
    verdict_counter = Counter(verdicts)
    if verdict_counter:
        most_common_verdict, most_common_count = verdict_counter.most_common(1)[0]
        verdict_consistency = f"{most_common_count}/{parse_ok_count} {most_common_verdict}"
    else:
        verdict_consistency = "N/A"

    return {
        "n": n,
        "parse_ok_count": parse_ok_count,
        "avg_latency": avg_latency,
        "avg_tokens": avg_tokens,
        "avg_issues": avg_issues,
        "verdict_consistency": verdict_consistency,
        "most_common_count": verdict_counter.most_common(1)[0][1] if verdict_counter else 0,
    }


def print_comparison_table(all_results: dict[str, list[dict]]) -> None:
    """Print the final comparison table across all strategies."""
    print(f"\n{'═' * 2} Comparison {'═' * 63}")
    header = (
        f"{'Strategy':<18}\u2502 {'Parse Rate':>10} \u2502 "
        f"{'Avg Latency':>11} \u2502 {'Avg Tokens':>10} \u2502 "
        f"{'Verdict Consistency':>19} \u2502 {'Avg Issues':>10}"
    )
    separator = (
        f"{'─' * 18}\u253c{'─' * 12}\u253c"
        f"{'─' * 13}\u253c{'─' * 12}\u253c"
        f"{'─' * 21}\u253c{'─' * 11}"
    )
    print(header)
    print(separator)

    for strategy_name, results in all_results.items():
        stats = _compute_strategy_stats(results)
        print(
            f"{strategy_name:<18}\u2502 "
            f"{stats['parse_ok_count']}/{stats['n']:>2}        \u2502 "
            f"{stats['avg_latency']:>9.1f}s \u2502 "
            f"{stats['avg_tokens']:>9,.0f} \u2502 "
            f"{stats['verdict_consistency']:>19} \u2502 "
            f"{stats['avg_issues']:>9.1f}"
        )

    print(f"{'═' * 76}")


def pick_recommendation(all_results: dict[str, list[dict]]) -> tuple[str, str]:
    """Pick the best strategy based on parse rate, consistency, latency, and tokens.

    Issue count above ~20 is treated as noisy bullet extraction (free-form),
    not genuine thoroughness. We prefer structured strategies with reasonable
    issue counts, lower latency, and fewer tokens.

    Returns (strategy_name, reason).
    """
    scored: list[tuple[str, float, float, float, float, float]] = []

    for name, results in all_results.items():
        stats = _compute_strategy_stats(results)
        parse_rate = stats["parse_ok_count"] / stats["n"] if stats["n"] else 0.0
        consistency = stats["most_common_count"] / stats["n"] if stats["n"] else 0.0
        avg_issues = stats["avg_issues"]
        avg_latency = stats["avg_latency"]
        avg_tokens = stats["avg_tokens"]
        # Penalize noisy issue counts (>20 is likely bullet extraction noise)
        issue_quality = avg_issues if avg_issues <= 20 else 0.0
        scored.append((name, parse_rate, consistency, issue_quality, -avg_latency, -avg_tokens))

    # Sort: highest parse rate, then consistency, then issue quality, then lowest latency, then lowest tokens
    scored.sort(key=lambda x: (x[1], x[2], x[3], x[4], x[5]), reverse=True)
    best_name = scored[0][0]

    stats = _compute_strategy_stats(all_results[best_name])
    parts: list[str] = []
    parts.append(f"{stats['parse_ok_count']}/{stats['n']} parse rate")
    parts.append(f"{stats['verdict_consistency']} verdict consistency")
    parts.append(f"{stats['avg_issues']:.1f} avg issues")
    parts.append(f"{stats['avg_latency']:.1f}s avg latency")
    parts.append(f"{stats['avg_tokens']:.0f} avg tokens")

    reason = ", ".join(parts)
    return best_name, reason


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="POC 2b: Compare prompt strategies for structured reviewer output"
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
        default=3,
        help="Number of runs per strategy (default: 3)",
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

    # Initialize client
    client = OpenAI()

    print(f"POC 2b: Structured Prompt Comparison ({args.model})")
    print(f"{'═' * 56}")
    print(f"Plan length:  {len(plan_text):,} chars")
    print(f"Runs/strategy: {args.runs}")
    print(f"Strategies:    {len(STRATEGIES)}")

    # Run all strategies
    all_results: dict[str, list[dict]] = {}

    for strategy in STRATEGIES:
        name = strategy["name"]
        print(f"\nRunning strategy: {name} ...")
        results = run_strategy(client, strategy, plan_text, args.model, runs=args.runs)
        all_results[name] = results
        print_strategy_detail(name, results)

    # Comparison table
    print_comparison_table(all_results)

    # Recommendation
    best_name, reason = pick_recommendation(all_results)
    print(f"\nRecommended: {best_name} \u2014 {reason}")


if __name__ == "__main__":
    main()
