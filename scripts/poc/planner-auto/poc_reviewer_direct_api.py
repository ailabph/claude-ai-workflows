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

# TODO: implement
