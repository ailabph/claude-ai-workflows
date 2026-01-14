# MCP Playwright Test Site

A minimal Next.js fixture for validating Playwright MCP tool passing via the orchestrator.

## Purpose

This site provides deterministic test scenarios for MCP Playwright verification:

- **Console messages**: Emits `[mcp-test]` prefixed warn/error on home page load
- **Network requests**: Triggers `/api/ping` (200) and `/api/fail` (500) on home page load
- **Form input**: Provides a username input with `data-testid="username"`

## Running

```bash
npm ci
npm run dev -- --port <PORT>
```

Then open http://localhost:<PORT>/

## Test Selectors

| Selector | Location | Description |
|----------|----------|-------------|
| `data-testid="nav-form"` | Home page | Link to form page |
| `data-testid="username"` | Form page | Username input |

## API Endpoints

| Endpoint | Status | Response |
|----------|--------|----------|
| `/api/ping` | 200 | `{ "ok": true, "source": "ping" }` |
| `/api/fail` | 500 | `{ "ok": false, "source": "fail" }` |

## Console Messages

On home page load:
- `console.warn("[mcp-test] warn from home")`
- `console.error("[mcp-test] error from home")`
