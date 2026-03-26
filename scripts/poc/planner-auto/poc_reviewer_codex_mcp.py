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

# TODO: implement
