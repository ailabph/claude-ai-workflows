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

# TODO: implement
