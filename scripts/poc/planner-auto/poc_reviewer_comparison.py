#!/usr/bin/env python3
"""POC 1d: Reviewer Adapter Comparison

Run the same plan through all three reviewer adapters and produce
a comparison report.

Steps:
  1. Load sample plan
  2. Define adapter runners (import from POC 1a, 1b, 1c or inline)
  3. For each adapter:
     a. Run 3 times
     b. Record: latency, token usage, parse success, parsed response
     c. Handle adapter unavailability gracefully (skip with note)
  4. Compute averages
  5. Compare response quality:
     - Do adapters agree on verdict?
     - Do they surface the same issues?
     - Any unique issues found by only one adapter?
  6. Print comparison table
  7. Print recommendation with rationale
  8. Optionally save report to file

Usage:
  export OPENAI_API_KEY="your-key"
  export ANTHROPIC_API_KEY="your-key"
  python scripts/poc/planner-auto/poc_reviewer_comparison.py
  python scripts/poc/planner-auto/poc_reviewer_comparison.py --plan path/to/plan.md
  python scripts/poc/planner-auto/poc_reviewer_comparison.py --output report.md
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

# Sibling imports
sys.path.insert(0, str(Path(__file__).parent))
from poc_parse_go_nogo import ReviewerResponse, Verdict
from poc_reviewer_direct_api import run_review, SAMPLE_PLAN


# ---------------------------------------------------------------------------
# Normalised result type
# ---------------------------------------------------------------------------

NormalResult = dict  # keys: adapter, verdict, issue_count, latency_s, cost_usd, tokens, parse_success, error


def _make_error_result(adapter: str, error: str) -> NormalResult:
    """Return a normalised error result for a failed adapter run."""
    return {
        "adapter": adapter,
        "verdict": "ERROR",
        "issue_count": 0,
        "latency_s": 0.0,
        "cost_usd": 0.0,
        "tokens": 0,
        "parse_success": False,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Adapter wrappers — normalise each to NormalResult
# ---------------------------------------------------------------------------

def run_direct_api(plan_text: str, model: str, client: object) -> NormalResult:
    """Run POC 1a direct API and normalise the result."""
    try:
        raw = run_review(client, plan_text, model)  # type: ignore[arg-type]
        parsed: ReviewerResponse = raw["parsed"]
        return {
            "adapter": "direct_api",
            "verdict": parsed.verdict.value,
            "issue_count": len(parsed.issues),
            "latency_s": raw["latency_s"],
            "cost_usd": raw["estimated_cost_usd"],
            "tokens": raw["total_tokens"],
            "parse_success": raw["parse_success"],
            "error": None,
            "_parsed": parsed,
        }
    except Exception as exc:
        return _make_error_result("direct_api", f"{type(exc).__name__}: {exc}")


def run_codex_mcp(plan_text: str, model: str) -> NormalResult:
    """Run POC 1b Codex MCP and normalise the result."""
    try:
        from poc_reviewer_codex_mcp import run_codex_review
    except ImportError as exc:
        return _make_error_result("codex_mcp", f"Import failed: {exc}")

    try:
        raw = asyncio.run(run_codex_review(plan_text, model))
        if "error" in raw and raw["error"]:
            return _make_error_result("codex_mcp", raw["error"])

        parsed: ReviewerResponse = raw["parsed"]
        cost = raw.get("total_cost_usd") or 0.0
        # Codex MCP doesn't provide granular token counts
        tokens = 0
        usage = raw.get("usage")
        if usage and hasattr(usage, "input_tokens"):
            tokens = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "output_tokens", 0) or 0)

        return {
            "adapter": "codex_mcp",
            "verdict": parsed.verdict.value,
            "issue_count": len(parsed.issues),
            "latency_s": raw["latency_s"],
            "cost_usd": cost,
            "tokens": tokens,
            "parse_success": raw["parse_success"],
            "error": None,
            "_parsed": parsed,
        }
    except Exception as exc:
        return _make_error_result("codex_mcp", f"{type(exc).__name__}: {exc}")


def run_opencode_http(plan_text: str, model: str, server_url: str) -> NormalResult:
    """Run POC 1c OpenCode HTTP and normalise the result."""
    try:
        from poc_reviewer_opencode_http import run_opencode_review
    except ImportError as exc:
        return _make_error_result("opencode_http", f"Import failed: {exc}")

    try:
        raw = run_opencode_review(plan_text, server_url, model)
        parsed: ReviewerResponse = raw["parsed"]
        tokens_dict = raw.get("tokens", {})
        total_tokens = tokens_dict.get("total", 0) if isinstance(tokens_dict, dict) else 0

        return {
            "adapter": "opencode_http",
            "verdict": parsed.verdict.value,
            "issue_count": len(parsed.issues),
            "latency_s": raw["latency_s"],
            "cost_usd": raw.get("cost_usd", 0.0),
            "tokens": total_tokens,
            "parse_success": raw["parse_success"],
            "error": None,
            "_parsed": parsed,
        }
    except Exception as exc:
        return _make_error_result("opencode_http", f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Availability checks
# ---------------------------------------------------------------------------

def check_direct_api_available() -> bool:
    """Direct API is available if OPENAI_API_KEY is set."""
    return bool(os.environ.get("OPENAI_API_KEY"))


def check_codex_available() -> bool:
    """Codex MCP is available if the codex binary is on PATH."""
    return shutil.which("codex") is not None


def check_opencode_available(server_url: str) -> bool:
    """OpenCode HTTP is available if the server responds to health check."""
    try:
        from poc_reviewer_opencode_http import check_server
        return check_server(server_url)
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Run comparison
# ---------------------------------------------------------------------------

def run_comparison(
    plan_text: str,
    runs: int,
    model: str,
    server_url: str,
    *,
    skip_codex: bool = False,
    skip_opencode: bool = False,
) -> dict[str, list[NormalResult]]:
    """Run all available adapters N times each and collect results.

    Returns a dict mapping adapter name to list of normalised results.
    """
    from openai import OpenAI

    results: dict[str, list[NormalResult]] = {
        "direct_api": [],
        "codex_mcp": [],
        "opencode_http": [],
    }

    # --- Direct API ---
    if check_direct_api_available():
        client = OpenAI()
        print(f"\n  Running direct_api ({runs} run{'s' if runs > 1 else ''})...")
        for i in range(1, runs + 1):
            print(f"    Run {i}/{runs}...", end=" ", flush=True)
            result = run_direct_api(plan_text, model, client)
            results["direct_api"].append(result)
            if result["error"]:
                print(f"ERROR: {result['error']}")
            else:
                print(f"verdict={result['verdict']}, {result['latency_s']:.1f}s")
    else:
        print("\n  Skipping direct_api: OPENAI_API_KEY not set")

    # --- Codex MCP ---
    if skip_codex:
        print("\n  Skipping codex_mcp: --skip-codex flag")
    elif check_codex_available():
        print(f"\n  Running codex_mcp ({runs} run{'s' if runs > 1 else ''})...")
        for i in range(1, runs + 1):
            print(f"    Run {i}/{runs}...", end=" ", flush=True)
            result = run_codex_mcp(plan_text, model)
            results["codex_mcp"].append(result)
            if result["error"]:
                print(f"ERROR: {result['error']}")
            else:
                print(f"verdict={result['verdict']}, {result['latency_s']:.1f}s")
    else:
        print("\n  Skipping codex_mcp: 'codex' command not found in PATH")

    # --- OpenCode HTTP ---
    if skip_opencode:
        print("\n  Skipping opencode_http: --skip-opencode flag")
    elif check_opencode_available(server_url):
        print(f"\n  Running opencode_http ({runs} run{'s' if runs > 1 else ''})...")
        for i in range(1, runs + 1):
            print(f"    Run {i}/{runs}...", end=" ", flush=True)
            result = run_opencode_http(plan_text, model, server_url)
            results["opencode_http"].append(result)
            if result["error"]:
                print(f"ERROR: {result['error']}")
            else:
                print(f"verdict={result['verdict']}, {result['latency_s']:.1f}s")
    else:
        print(f"\n  Skipping opencode_http: server not responding at {server_url}")

    return results


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def compute_adapter_stats(results: list[NormalResult]) -> dict:
    """Compute aggregate stats for one adapter's runs.

    Returns dict with: runs, parse_rate, avg_latency, avg_cost, avg_tokens,
    avg_issues, verdict_consistency.
    """
    if not results:
        return {
            "runs": 0,
            "parse_rate": "0/0",
            "avg_latency": 0.0,
            "avg_cost": 0.0,
            "avg_tokens": 0.0,
            "avg_issues": 0.0,
            "verdict_consistency": "N/A",
        }

    n = len(results)
    parse_ok = sum(1 for r in results if r["parse_success"])
    valid = [r for r in results if r["error"] is None]
    n_valid = len(valid)

    avg_latency = sum(r["latency_s"] for r in valid) / n_valid if n_valid else 0.0
    avg_cost = sum(r["cost_usd"] for r in valid) / n_valid if n_valid else 0.0
    avg_tokens = sum(r["tokens"] for r in valid) / n_valid if n_valid else 0.0
    avg_issues = sum(r["issue_count"] for r in valid) / n_valid if n_valid else 0.0

    # Verdict consistency
    verdicts = [r["verdict"] for r in valid]
    verdict_counts = Counter(verdicts)
    if len(verdict_counts) == 1 and n_valid > 0:
        dominant = list(verdict_counts.keys())[0]
        verdict_consistency = f"{n_valid}/{n_valid} {dominant}"
    elif n_valid > 0:
        parts = [f"{count} {v}" for v, count in verdict_counts.most_common()]
        verdict_consistency = ", ".join(parts)
    else:
        verdict_consistency = "N/A"

    return {
        "runs": n,
        "parse_rate": f"{parse_ok}/{n}",
        "avg_latency": avg_latency,
        "avg_cost": avg_cost,
        "avg_tokens": avg_tokens,
        "avg_issues": avg_issues,
        "verdict_consistency": verdict_consistency,
    }


# ---------------------------------------------------------------------------
# Issue overlap analysis
# ---------------------------------------------------------------------------

def _normalise_issue_key(description: str) -> str:
    """Normalise an issue description for overlap comparison."""
    return description.strip().lower()[:50]


def analyze_issue_overlap(all_results: dict[str, list[NormalResult]]) -> str:
    """Analyse which issues are shared across adapters and which are unique.

    Returns a formatted string summary.
    """
    # Collect unique issue descriptions per adapter
    adapter_issues: dict[str, set[str]] = {}
    for adapter, runs in all_results.items():
        if not runs:
            continue
        keys: set[str] = set()
        for run in runs:
            parsed = run.get("_parsed")
            if parsed is None:
                continue
            for issue in parsed.issues:
                keys.add(_normalise_issue_key(issue.description))
        if keys:
            adapter_issues[adapter] = keys

    if len(adapter_issues) < 2:
        return "  Not enough adapters with results for overlap analysis."

    # Find common themes (issues mentioned by 2+ adapters)
    all_keys: set[str] = set()
    for keys in adapter_issues.values():
        all_keys |= keys

    common: list[str] = []
    unique_per_adapter: dict[str, list[str]] = {a: [] for a in adapter_issues}

    for key in sorted(all_keys):
        found_in = [a for a, keys in adapter_issues.items() if key in keys]
        if len(found_in) >= 2:
            common.append(f"    - \"{key}\" (found by: {', '.join(found_in)})")
        else:
            unique_per_adapter[found_in[0]].append(f"    - \"{key}\"")

    lines: list[str] = []

    if common:
        lines.append(f"  Common themes ({len(common)} issues found by 2+ adapters):")
        lines.extend(common)
    else:
        lines.append("  No common themes found across adapters.")

    for adapter, unique in unique_per_adapter.items():
        if unique:
            lines.append(f"\n  Unique to {adapter} ({len(unique)}):")
            lines.extend(unique)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_comparison_table(all_results: dict[str, list[NormalResult]]) -> str:
    """Print and return the formatted comparison table."""
    lines: list[str] = []

    lines.append("")
    lines.append("\u2550\u2550 Adapter Comparison " + "\u2550" * 57)

    header = (
        f"{'Adapter':<17}\u2502 {'Parse Rate':>10} \u2502 "
        f"{'Avg Latency':>11} \u2502 {'Avg Cost':>8} \u2502 "
        f"{'Avg Tokens':>10} \u2502 {'Avg Issues':>10} \u2502 Verdict"
    )
    separator = (
        f"{'─' * 17}\u253c{'─' * 12}\u253c"
        f"{'─' * 13}\u253c{'─' * 10}\u253c"
        f"{'─' * 12}\u253c{'─' * 12}\u253c{'─' * 16}"
    )

    lines.append(header)
    lines.append(separator)

    stats_by_adapter: dict[str, dict] = {}

    for adapter in ["direct_api", "codex_mcp", "opencode_http"]:
        results = all_results.get(adapter, [])
        if not results:
            lines.append(f"{adapter:<17}\u2502 {'(skipped)':>10} \u2502 {'':>11} \u2502 {'':>8} \u2502 {'':>10} \u2502 {'':>10} \u2502")
            continue

        stats = compute_adapter_stats(results)
        stats_by_adapter[adapter] = stats

        tokens_str = f"{stats['avg_tokens']:,.0f}" if stats["avg_tokens"] > 0 else "N/A"

        row = (
            f"{adapter:<17}\u2502 {stats['parse_rate']:>10} \u2502 "
            f"{stats['avg_latency']:>9.1f}s  \u2502 "
            f"${stats['avg_cost']:.3f}  \u2502 "
            f"{tokens_str:>10} \u2502 "
            f"{stats['avg_issues']:>10.1f} \u2502 {stats['verdict_consistency']}"
        )
        lines.append(row)

    lines.append("\u2550" * 77)

    text = "\n".join(lines)
    print(text)
    return text


def print_recommendation(all_results: dict[str, list[NormalResult]]) -> str:
    """Determine and print the recommended adapter. Returns the recommendation string."""
    # Build candidates: only adapters with at least one result
    candidates: list[tuple[str, dict]] = []
    for adapter in ["direct_api", "codex_mcp", "opencode_http"]:
        results = all_results.get(adapter, [])
        if results:
            stats = compute_adapter_stats(results)
            candidates.append((adapter, stats))

    if not candidates:
        msg = "\nNo adapters produced results. Cannot make a recommendation."
        print(msg)
        return msg

    # Sort by: parse_rate descending, then cost ascending, then latency ascending
    def sort_key(item: tuple[str, dict]) -> tuple[float, float, float]:
        _, stats = item
        # Parse rate: extract numerator/denominator for a ratio
        parts = stats["parse_rate"].split("/")
        if len(parts) == 2 and int(parts[1]) > 0:
            parse_ratio = int(parts[0]) / int(parts[1])
        else:
            parse_ratio = 0.0
        return (-parse_ratio, stats["avg_cost"], stats["avg_latency"])

    candidates.sort(key=sort_key)
    best_adapter, best_stats = candidates[0]

    msg = (
        f"\nRecommended: {best_adapter} "
        f"-- {best_stats['parse_rate']} parse, "
        f"lowest cost (${best_stats['avg_cost']:.3f}), "
        f"{best_stats['avg_latency']:.1f}s latency"
    )
    print(msg)
    return msg


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    all_results: dict[str, list[NormalResult]],
    table_text: str,
    recommendation_text: str,
    overlap_text: str,
    model: str,
    runs: int,
) -> str:
    """Generate a full markdown report."""
    lines: list[str] = []
    lines.append("# Reviewer Adapter Comparison Report")
    lines.append("")
    lines.append(f"- **Model:** {model}")
    lines.append(f"- **Runs per adapter:** {runs}")
    lines.append("")

    lines.append("## Comparison Table")
    lines.append("")
    lines.append("```")
    lines.append(table_text.strip())
    lines.append("```")
    lines.append("")

    lines.append("## Issue Overlap Analysis")
    lines.append("")
    lines.append("```")
    lines.append(overlap_text.strip())
    lines.append("```")
    lines.append("")

    lines.append("## Recommendation")
    lines.append("")
    lines.append(recommendation_text.strip())
    lines.append("")

    # Per-adapter detail
    lines.append("## Per-Adapter Detail")
    lines.append("")

    for adapter in ["direct_api", "codex_mcp", "opencode_http"]:
        results = all_results.get(adapter, [])
        if not results:
            lines.append(f"### {adapter}")
            lines.append("")
            lines.append("*Skipped (unavailable)*")
            lines.append("")
            continue

        stats = compute_adapter_stats(results)
        lines.append(f"### {adapter}")
        lines.append("")
        lines.append(f"- Runs: {stats['runs']}")
        lines.append(f"- Parse rate: {stats['parse_rate']}")
        lines.append(f"- Avg latency: {stats['avg_latency']:.1f}s")
        lines.append(f"- Avg cost: ${stats['avg_cost']:.3f}")
        lines.append(f"- Avg tokens: {stats['avg_tokens']:,.0f}")
        lines.append(f"- Avg issues: {stats['avg_issues']:.1f}")
        lines.append(f"- Verdict consistency: {stats['verdict_consistency']}")
        lines.append("")

        for i, result in enumerate(results, 1):
            if result["error"]:
                lines.append(f"**Run {i}:** ERROR - {result['error']}")
            else:
                lines.append(
                    f"**Run {i}:** {result['verdict']}, "
                    f"{result['issue_count']} issues, "
                    f"{result['latency_s']:.1f}s, "
                    f"${result['cost_usd']:.3f}"
                )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="POC 1d: Run the same plan through all three reviewer adapters and compare"
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=None,
        help="Path to a plan file (default: use hardcoded sample plan from POC 1a)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of runs per adapter (default: 3)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-5.4",
        help="Model to use (default: gpt-5.4)",
    )
    parser.add_argument(
        "--server-url",
        type=str,
        default="http://127.0.0.1:14096",
        help="OpenCode server URL (default: http://127.0.0.1:14096)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Save comparison report as markdown to this path",
    )
    parser.add_argument(
        "--skip-codex",
        action="store_true",
        help="Skip Codex MCP adapter even if available",
    )
    parser.add_argument(
        "--skip-opencode",
        action="store_true",
        help="Skip OpenCode HTTP adapter even if available",
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

    print(f"POC 1d: Reviewer Adapter Comparison ({args.model})")
    print(f"{'=' * 60}")
    print(f"Plan length:  {len(plan_text):,} chars")
    print(f"Runs/adapter: {args.runs}")
    print(f"Model:        {args.model}")
    print(f"Server URL:   {args.server_url}")

    # Check what's available
    print(f"\nAdapter availability:")
    print(f"  direct_api:    {'YES' if check_direct_api_available() else 'NO (OPENAI_API_KEY not set)'}")
    codex_ok = check_codex_available()
    print(f"  codex_mcp:     {'YES' if codex_ok else 'NO (codex not in PATH)'}"
          f"{'  [SKIPPED by flag]' if args.skip_codex else ''}")
    opencode_ok = check_opencode_available(args.server_url)
    print(f"  opencode_http: {'YES' if opencode_ok else f'NO (server not responding at {args.server_url})'}"
          f"{'  [SKIPPED by flag]' if args.skip_opencode else ''}")

    # Run comparison
    all_results = run_comparison(
        plan_text,
        args.runs,
        args.model,
        args.server_url,
        skip_codex=args.skip_codex,
        skip_opencode=args.skip_opencode,
    )

    # Check if we got any results at all
    total_runs = sum(len(r) for r in all_results.values())
    if total_runs == 0:
        print("\nNo adapters were available. Nothing to compare.")
        sys.exit(1)

    # Print comparison table
    table_text = print_comparison_table(all_results)

    # Issue overlap analysis
    overlap_text = analyze_issue_overlap(all_results)
    print(f"\n── Issue Overlap Analysis {'─' * 30}")
    print(overlap_text)

    # Recommendation
    recommendation_text = print_recommendation(all_results)

    # Summary
    adapters_run = sum(1 for r in all_results.values() if r)
    successful_runs = sum(
        1 for runs in all_results.values() for r in runs if r["error"] is None
    )
    print(f"\n{'=' * 60}")
    print(f"Adapters tested: {adapters_run}/3")
    print(f"Successful runs: {successful_runs}/{total_runs}")

    # Save report if requested
    if args.output is not None:
        report = generate_report(
            all_results,
            table_text,
            recommendation_text,
            overlap_text,
            args.model,
            args.runs,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        print(f"\nReport saved to: {args.output}")


if __name__ == "__main__":
    main()
