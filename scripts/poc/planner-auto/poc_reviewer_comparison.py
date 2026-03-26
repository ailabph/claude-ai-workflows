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

# TODO: implement
