#!/usr/bin/env python3
"""POC 5b: End-to-End Review Loop

Full integration test: plan → review → revise → review → GO.

Steps:
  1. Initialize session DB (POC 3a schema)
  2. Create session
  3. Generate initial plan:
     - Use Claude Agent SDK (headless) with a feature description
     - Store as plan_drafts (draft_number=1)
     - Export a-01-plan.md
  4. Review loop (max 5 rounds):
     a. Send current plan to GPT-5.4 via Direct API (POC 1a approach)
     b. Parse response into ReviewerResponse (POC 2a parser)
     c. Store review in DB, export a-<N>-review.md
     d. If GO: break loop
     e. If NO_GO:
        - Feed issues to Claude with revision prompt
        - Claude produces revised plan
        - Store as plan_drafts (draft_number++), export a-<N>-plan.md
        - Continue loop
  5. On GO:
     - Mark final plan, export a-<N>-plan-final.md
     - Mark session complete
  6. Print summary:
     - Rounds taken
     - Issues found and resolved per round
     - Total latency, token usage, cost (Claude + GPT combined)
     - List of all exported artifacts
  7. Verify DB consistency: all drafts, reviews, messages present

Usage:
  export ANTHROPIC_API_KEY="your-key"
  export OPENAI_API_KEY="your-key"
  python scripts/poc/planner-auto/poc_review_loop_e2e.py
  python scripts/poc/planner-auto/poc_review_loop_e2e.py --feature "Add JWT authentication"
  python scripts/poc/planner-auto/poc_review_loop_e2e.py --max-rounds 3
  python scripts/poc/planner-auto/poc_review_loop_e2e.py --output-dir /tmp/poc_e2e
"""

# TODO: implement
