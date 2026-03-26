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
