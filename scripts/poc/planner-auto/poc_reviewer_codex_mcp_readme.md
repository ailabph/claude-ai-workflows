# POC 1b: Reviewer via Codex MCP

## Purpose

Validate that GPT-5.4 can be invoked from within Claude's agent loop via the Codex MCP server, and that the response can be captured and parsed into the `ReviewerResponse` schema.

## What This Tests

- Codex MCP server setup (`npm install -g @openai/codex`, `claude mcp add codex`)
- Invoking GPT-5.4 through MCP tool from Claude's agent loop
- Response capture from MCP tool output
- Whether GPT has tool access (can it read repo files through MCP?)
- Latency comparison against Direct API (POC 1a)

## Input

Same sample plan as POC 1a for fair comparison.

## Ideal Result

- Codex MCP setup documented step-by-step
- GPT invoked successfully through MCP
- Response parseable into ReviewerResponse schema
- Latency and token cost measured
- Comparison notes against POC 1a results

## Dependencies

- `@openai/codex` (npm global install)
- Codex MCP server configured in Claude
- `claude-agent-sdk`
- `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` env vars

## Actual Results

- 1/1 run parsed successfully
- GPT-5.4 returned NO_GO with 5 well-structured issues via Codex MCP
- Latency: 30.9s (2.2x slower than Direct API due to Claude->Codex->GPT round-trip)
- Cost: $0.035 (5x more expensive than Direct API -- pays for both Claude and GPT tokens)
- 3 turns required (Claude sends to Codex, Codex returns, Claude relays)
- Key finding: `codex login --with-api-key` required for auth -- SDK env passthrough to MCP server subprocesses is unreliable
- Key finding: Claude sometimes paraphrases GPT's response instead of relaying JSON verbatim -- prompt tuning needed for reliable parse
- Comparison: Direct API is faster, cheaper, and more reliable for plan-text-only review. Codex MCP's advantage (GPT tool access) wasn't needed for this use case.
