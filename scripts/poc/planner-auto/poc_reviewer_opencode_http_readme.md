# POC 1c: Reviewer via OpenCode HTTP Server

## Purpose

Validate that GPT-5.4 can be invoked through OpenCode's HTTP server API (`opencode serve`) and that the response can be captured and parsed into the `ReviewerResponse` schema.

## What This Tests

- `opencode serve` startup and session API
- Creating a session and sending a message via HTTP
- Response capture from the HTTP API
- Whether GPT has tool access (file read/write) through the server
- Latency comparison against Direct API (POC 1a) and Codex MCP (POC 1b)

## Input

Same sample plan as POC 1a and 1b for fair comparison.

## Ideal Result

- OpenCode server starts and accepts requests
- Session created, review prompt sent, response received
- Response parseable into ReviewerResponse schema
- Server lifecycle management documented (start, health check, stop)
- Latency and token cost measured
- Comparison notes against POC 1a and 1b results

## Dependencies

- `opencode` CLI installed
- `requests` Python package
- `OPENCODE_SERVER_PASSWORD` env var (optional)
- `OPENAI_API_KEY` configured in OpenCode
