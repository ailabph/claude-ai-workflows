# Planner-Auto — Open Issues & Bugs

Tracked issues discovered during development, review, and stress testing.

---

## Critical / Blocking

_(none currently)_

---

## High

### H1: Opus + thinking + SDK subprocess crashes on large prompts
**Found:** POC dogfooding (Plan 1 & Plan 2 generation)
**Symptom:** Empty `ResultMessage.result` or SDK subprocess exits with code 1. Opus uses turns on tool calls instead of generating text.
**Workaround:** `max_turns=0` (unlimited) with thinking, or fall back to Sonnet with `max_turns=1`.
**Root cause:** SDK spawns `claude` subprocess; Opus with thinking is aggressive about tool use. `allowed_tools=[]` crashes the SDK entirely.
**Fix needed:** Text-only mode for plan generation, retry with fallback, or chunked context injection.
**Documented in:** `planner-auto/README.md` Known Issues, `claude/agents/planner-auto-debugger.md`

### H2: Rate limit from SDK subprocess — not the Anthropic API
**Found:** Stress test (2026-03-28), `planner-auto discuss` command
**Symptom:** `Error: Rate limited by API` printed immediately without retry. `sdk_wrapper.py` has 3x retry with 2/4/8s backoff but it didn't fire.
**Root cause confirmed:** The rate limit is NOT from the Anthropic HTTP API — direct API calls via the `anthropic` package work fine (`scripts/check_api_keys.py` passes). The rate limit comes from the **Claude CLI subprocess** that `claude-agent-sdk` spawns. The CLI shares quota with active Claude Code sessions (like this one). When the user is in a Claude Code conversation, the CLI subprocess gets throttled.
**Why retry doesn't work:** The `RateLimitEvent` is emitted inside the SDK's async stream and mapped to `SDKRateLimitError` in `_execute_query()`. But the rate limit may fire before the stream even starts (at subprocess initialization), bypassing the retry loop entirely.
**Fix options:**
1. **Direct API fallback (recommended):** Use the `anthropic` package directly (like `scripts/check_api_keys.py` does) instead of `claude-agent-sdk` subprocess. This avoids the CLI rate limit entirely. The reviewer already uses `openai` directly — the planner should do the same.
2. **Retry at a higher level:** Wrap the entire `query_claude()` call in a retry loop, not just the inner stream iteration.
3. **Session isolation:** Use `--session-id` or `--no-project` flags on the CLI subprocess to avoid quota sharing.
**Impact:** planner-auto is unusable while the user has an active Claude Code session. This is the #1 production blocker.
**Refs:** `planner_auto/sdk_wrapper.py`, `planner_auto/agents.py`, `scripts/check_api_keys.py`

### H3: anyio cancel scope tracebacks on SDK error paths
**Found:** Stress test (2026-03-28), `planner-auto discuss` command
**Symptom:** Multiple `RuntimeError: Attempted to exit cancel scope in a different task than it was entered in` tracebacks printed to stderr on any SDK error (rate limit, timeout, etc.). Noisy and alarming to users but not functionally harmful.
**Root cause:** The `claude-agent-sdk` async generator cleanup doesn't suppress `anyio` cancel scope errors when the stream is interrupted. This is an SDK-level issue, not planner-auto code.
**Fix needed:** Suppress anyio tracebacks in the SDK wrapper's error handling. Options: (a) redirect stderr during SDK calls and filter, (b) wrap the async iteration in a try/except that catches GeneratorExit + RuntimeError from anyio, (c) report upstream to SDK team.
**Refs:** `planner_auto/sdk_wrapper.py`, `claude_agent_sdk/_internal/client.py:142-145`

---

## Medium

### M1: Multiple active Claude sessions cause SDK subprocess conflicts
**Found:** POC dogfooding, stress testing
**Symptom:** Intermittent SDK crashes when other Claude Code sessions are active. "Fatal error in message reader" printed before script starts.
**Workaround:** Close other Claude sessions before running planner-auto.
**Fix needed:** Session isolation in SDK subprocess, or retry on subprocess conflict.

### M2: Stress testing proposal uses fake file paths
**Found:** Stress test (2026-03-28)
**Symptom:** `proposal-stress-testing.md` references `src/app.py` which doesn't exist in this repo.
**Fix needed:** Update proposal to use real repo paths (`planner-auto/planner_auto/cli.py`, etc.).

---

## Low

### L1: anyio version compatibility
**Found:** Stress test tracebacks reference `anyio._backends._asyncio.py:461`
**Note:** The anyio cancel scope issue may be version-specific. Current `anyio` version may conflict with `claude-agent-sdk` expectations. Worth checking if upgrading/pinning anyio resolves the tracebacks.

---

## Resolved

| ID | Issue | Fixed In | How |
|----|-------|----------|-----|
| — | Round numbering starts at 1 on resume | v0.2.0 | Engine queries max existing round |
| — | Disposition indexing mismatch | v0.2.0 | Validate before filter |
| — | CLI config not wired (prompt_mode, effort) | v0.2.0 | Defaults from POC config |
| — | Review metadata all None | v0.2.0 | Adapter populates, engine passes through |
| — | Export naming wrong (plan-final.md) | v0.2.0 | Numbered a-NN-plan-final.md |
| — | Duplicate CLI summary line | v0.3.0 | Engine owns final output |
| — | check --probe wrong signature | v0.3.0 | Correct query_claude args |
| — | Fresh DB misclassified | v0.3.0 | try/except around schema check |
| — | add-context missing observability | v0.3.0 | --verbose + setup_session_logging |
| — | inspect dump not pure JSON | v0.3.0 | Warning to stderr, JSON to stdout |
| — | Atomic persistence (auto-commit) | v0.1.2 | Callers manage transactions |
| — | Timeout not enforced | v0.1.2 | asyncio.wait_for wrapping |
