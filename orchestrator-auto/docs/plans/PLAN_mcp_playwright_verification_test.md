# MCP Playwright Verification Tool Plan (v2)

**Date:** 2026-01-14  
**Purpose:** Provide a repeatable CLI verification that both Planner and Executor agents can access and successfully use Playwright MCP tools.  
**Type:** Custom CLI “tool run” (not a unit test; not part of `pytest`).

---

## Objective

Create a dedicated CLI command that verifies MCP tool passing works in real conditions:

1. **Planner Agent** can use Playwright MCP tools.
2. **Executor Agent** can use Playwright MCP tools.
3. Tool usage is validated via **artifacts and side-effects** (e.g., screenshot file exists), not via “LLM said it worked”.
4. Supports testing against a **purpose-built local test site** (`orchestrator-auto/fixtures/playwright-test-site/`) to avoid flaky public sites.

---

## Non-Goals

- Adding Playwright MCP tools to the orchestrator’s default MCP tool selection logic.
- Adding a `pytest` integration test that runs in CI.
- Validating the full orchestrator state machine (`Orchestrator`) end-to-end.

This tool verifies: **agent → MCP server → browser tools** and that `allowed_tools` / `mcp_servers` wiring is correct.

---

## CLI Interface

### Command

Add a new subcommand:

- `orchestrator test-playwright <role> --test-url <url> [options]`

Where `<role>` is one of:

- `planner`
- `executor`
- `both` (runs planner then executor sequentially)

### Options

- `--test-url TEXT` (required)
  - URL to the test website, e.g. `http://localhost:<PORT>/`.
- `--mcp-config PATH` (optional)
  - MCP config file to use for this run. If omitted, use existing MCP auto-discovery (`.mcp.json` in repo root or `~/.mcp.json`).
- `--out-dir PATH` (optional)
  - Directory to write artifacts into.
  - Default: create a timestamped directory under `./.orchestrator_artifacts/playwright-test/`.
- `--timeout INTEGER` (optional)
  - Overall timeout in seconds for the run (default: 120).
- `--model TEXT` (optional)
  - Override model used by the test agent (default: `claude-sonnet-4-5-20250929`).
- `--verbose` (flag)
  - Print the full agent response.

### Output Contract

- Exit code `0` on success.
- Exit code `1` on failure.
- CLI prints:
  - Which role(s) were tested
  - MCP config source used
  - Artifact output directory
  - A short PASS/FAIL summary

---

## Test Site Requirements

A small deterministic Next.js website exists at `orchestrator-auto/fixtures/playwright-test-site/` to validate browser actions without relying on external sites.

Prereqs for running the site:
- Node.js `>=20`
- npm (`npm ci` recommended)

See: [PLAN_mcp_playwright_test_site_nextjs.md](./PLAN_mcp_playwright_test_site_nextjs.md) for full details.

### Required pages/features

- `/` (home)
  - Contains stable link/button to navigate to `/form`.
  - Triggers both a console warning and error.
  - Triggers at least one successful network request and one failing network request.
- `/form`
  - Contains an input with stable selector/id for username.
  - Optional: password input.

### Selector stability

All interactive elements must have stable identifiers (`data-testid`), so prompts can be deterministic.

Minimum required selectors:
- Home → Form link/button: `data-testid="nav-form"`
- Username input: `data-testid="username"`
- Optional button to trigger errors (if used): `data-testid="trigger-errors"`

### Reference implementation (Next.js)

The test site is located at `orchestrator-auto/fixtures/playwright-test-site/`.

To run it:

```bash
cd orchestrator-auto/fixtures/playwright-test-site
npm ci
npm run dev -- --port <PORT>
```

#### Routes

- `app/page.tsx` (home)
  - On mount, emit:
    - `console.warn("[mcp-test] warn from home")`
    - `console.error("[mcp-test] error from home")`
  - On mount, perform network requests:
    - `fetch("/api/ping")` (200)
    - `fetch("/api/fail")` (500)
  - Include a navigation element:
    - `<a data-testid="nav-form" href="/form">Go to form</a>`

- `app/form/page.tsx` (form)
  - Render an input:
    - `<input data-testid="username" name="username" />`

- `app/api/ping/route.ts`
  - Respond `200` JSON: `{ ok: true, source: "ping" }`

- `app/api/fail/route.ts`
  - Respond `500` JSON: `{ ok: false, source: "fail" }`

Notes:
- The deliberate `500` endpoint + the successful `200` endpoint makes it easy to confirm the MCP network tool captures both success and failure.
- The `[mcp-test]` prefix makes console filtering unambiguous.

---

## MCP Config Fixture

This tool should work with either:

1. An explicit `--mcp-config path/to/.mcp.json`, or
2. Auto-discovered `.mcp.json` / `~/.mcp.json`.

Minimal config example:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-playwright"]
    }
  }
}
```

Note: The orchestrator code stores raw config (with `${VAR}`) in DB, but this tool is **sessionless** and can simply expand at runtime.

---

## Verification Sequence

### Tools required

Use either:

- Minimal explicit tools (recommended to avoid tool-name drift):
  - `mcp__playwright__browser_navigate`
  - `mcp__playwright__browser_snapshot`
  - `mcp__playwright__browser_click`
  - `mcp__playwright__browser_type`
  - `mcp__playwright__browser_console_messages`
  - `mcp__playwright__browser_network_requests`
  - `mcp__playwright__browser_take_screenshot`
  - `mcp__playwright__browser_close`

OR

- Wildcard allowlist:
  - `mcp__playwright__*`

Recommendation: start with minimal explicit list; add tools later as needed.

### Steps

For each role tested:

1. Navigate to `--test-url`.
2. Take snapshot and report visible top-level elements.
3. Click the “go to form” link.
4. Type `testuser` into username input.
5. Collect console messages.
6. Collect network requests.
7. Take screenshot and save to `{out_dir}/{role}_test.png`.
8. Close the browser.

---

## Validation (How the CLI decides PASS/FAIL)

The CLI must validate success via side-effects and basic sanity checks:

- Screenshot file exists at `{out_dir}/{role}_test.png`.
- Screenshot file size > 0 bytes.
- If console/network tools were invoked, their returned data is written to JSON/text artifacts (optional but recommended).
- If the agent reports failures, treat as FAIL.

Important: do not rely on “response contains mcp__playwright”.

---

## Implementation Plan

### Phase 1: CLI wiring

- Add a new command group entry in `orchestrator_auto/cli.py` (alongside other utility commands).
- Parse args and create output directory.

### Phase 2: Core runner

Create a small runner function (new module is fine, but keep it simple):

- Inputs: `role`, `test_url`, `mcp_config_path`, `out_dir`, `timeout`, `model`, `verbose`
- Load MCP config:
  - Prefer `--mcp-config` if provided; else auto-discover.
  - Use existing helpers in `orchestrator_auto/config.py`:
    - `load_mcp_config_raw(...)` + `expand_env_vars(...)`
- Build allowed tools:
  - `build_allowed_tools(mcp_tools=[...])`
- Instantiate agent:
  - `PlannerAgent(...)` or `ExecutorAgent(...)`
  - Set `cwd=out_dir` so MCP screenshot writes land in the expected place.
- Run the verification prompt.
- Post-validate artifacts.
- Always `close()` in a `finally`.

### Phase 3: “both” mode

- Run planner first, then executor.
- Add a short sleep (e.g., 1–2 seconds) between them to reduce MCP process contention.

### Phase 4: Prereq helper script (optional)

Optionally add a script similar to the previous plan (`scripts/check_playwright_mcp.sh`) but positioned as a convenience for humans. This tool should not attempt to install dependencies automatically.

---

## Troubleshooting

- MCP server not available: `npm install -g @anthropic/mcp-server-playwright` (or ensure `npx` works).
- Playwright browsers missing: `npx playwright install chromium`.
- If tool calls fail with “not allowed”: verify `allowed_tools` includes required MCP tools.
- If tool calls fail with “tool not found”: MCP server version mismatch; use wildcard `mcp__playwright__*` temporarily to diagnose.

---

## Acceptance Criteria

- `orchestrator test-playwright planner --test-url http://localhost:<PORT>/` creates `planner_test.png` and exits `0`.
- `orchestrator test-playwright executor --test-url http://localhost:<PORT>/` creates `executor_test.png` and exits `0`.
- `orchestrator test-playwright both --test-url http://localhost:<PORT>/` runs sequentially without hanging browser/MCP processes.
- Clear error messages on failure (MCP config missing, MCP server not startable, tool missing/not allowed, screenshot not created).
