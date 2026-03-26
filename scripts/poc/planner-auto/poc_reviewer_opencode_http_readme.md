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

## Actual Results

- 1/1 run parsed successfully into ReviewerResponse schema (JSON format)
- GPT-5.4 returned NO_GO with 6 well-structured issues
- Latency: 13.8s — comparable to Direct API (14s), much faster than Codex MCP (31s)
- Cost: $0.039 — 5.6x more expensive than Direct API ($0.007) due to OpenCode injecting 10,500+ system tokens
- Token breakdown: 11,237 total (10,507 input, 730 output) — input tokens inflated by OpenCode's own system context
- API flow: `POST /session` → `POST /session/{id}/message` → response is synchronous with full content
- Session cleanup via `DELETE /session/{id}` works reliably
- Server requires separate `opencode serve --port PORT` process running
- `OPENCODE_SERVER_PASSWORD` not set for POC — server runs unsecured

**Comparison across all three adapters:**

| Adapter | Latency | Cost | Parse | Input Tokens |
|---------|---------|------|-------|-------------|
| Direct API (1a) | 14s | $0.007 | 3/3 | 574 |
| Codex MCP (1b) | 31s | $0.035 | 1/1 | N/A (via Claude) |
| OpenCode HTTP (1c) | 14s | $0.039 | 1/1 | 10,507 |

**Key finding:** OpenCode HTTP matches Direct API on latency but is 5.6x costlier because OpenCode prepends its own large system context to every request. For plan-text-only review (no tool access needed), Direct API is the clear winner.
