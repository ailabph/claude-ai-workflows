# Direct Anthropic API Fallback - Implementation Plan

## Overview
Replace the Claude CLI subprocess (`claude-agent-sdk`) with direct Anthropic API calls as the default backend for all planner-auto Claude interactions. Backend selection happens inside `sdk_wrapper.py` via a `backend=` parameter. Auth-aware defaulting: `ANTHROPIC_API_KEY` → direct, OAuth only → sdk. All Anthropic exceptions mapped to existing `SDKError` hierarchy. No CLI error handling changes.

## Milestone 1: Direct API Backend in sdk_wrapper.py

Add the direct Anthropic API backend alongside the existing SDK backend inside `sdk_wrapper.py`. Auth-aware default resolution. Error contract preserved.

### Tasks
- [ ] Add `anthropic>=0.40.0` to `planner-auto/pyproject.toml` dependencies.
- [ ] Add `resolve_default_backend() -> str` to `sdk_wrapper.py`: checks `ANTHROPIC_API_KEY` → "direct", only `CLAUDE_CODE_OAUTH_TOKEN` → "sdk", both → "direct", neither → "direct".
- [ ] Add `_execute_direct(prompt, system_prompt, model, max_tokens, timeout_sec, thinking, thinking_budget) -> tuple[str, dict]` to `sdk_wrapper.py`: calls `anthropic.AsyncAnthropic().messages.create()`, extracts text blocks, returns `(text, usage_info)`. Error mapping: `AuthenticationError` → `SDKAuthError`, `RateLimitError` → `SDKRateLimitError`, `APITimeoutError`/`APIConnectionError` → `SDKTimeoutError`, `BadRequestError` (thinking) → internal fallback, `BadRequestError` (other) → `SDKResponseError`, other `APIError` → `SDKResponseError`, empty response → `SDKResponseError`.
- [ ] Add thinking fallback inside `_execute_direct()`: catch `BadRequestError` with "thinking" in message, retry without thinking, log warning.
- [ ] Rename existing SDK stream code to `_execute_sdk()` (was `_execute_query()`). No logic changes.
- [ ] Update `query_claude()` signature: add `backend: str | None = None` parameter. Dispatch: if `backend` is None, call `resolve_default_backend()`. Route to `_execute_direct()` or `_execute_sdk()`. Return type stays `str`.
- [ ] Add effort-to-thinking mapping for direct backend: `None`/`"low"` → no thinking; `"medium"` → `budget=10000`; `"high"` → `budget=20000`; `"max"` → `budget=50000`.
- [ ] Shared retry logic: `_with_retries()` wraps either backend. Rate limit 3x (2/4/8s), timeout 1x (2s), auth immediate. Both backends raise the same `SDKError` subclasses so retry logic is identical.
- [ ] Create `tests/test_direct_backend.py`: direct backend dispatched when `backend="direct"`, SDK dispatched when `backend="sdk"`, `resolve_default_backend()` with API key / OAuth / both / neither, error mapping for all 6 Anthropic exception types, thinking fallback, empty response, effort-to-thinking mapping, retry logic. 14+ tests.

### Deliverables
- [ ] `_execute_direct()` implemented with full error mapping to `SDKError` hierarchy
- [ ] `_execute_sdk()` renamed from `_execute_query()` (no logic changes)
- [ ] `query_claude()` dispatches based on `backend=` param
- [ ] `resolve_default_backend()` auth-aware
- [ ] `anthropic` in `pyproject.toml`
- [ ] `pytest tests/test_direct_backend.py` passes with 14+ tests

## Milestone 2: Caller Wiring and Session Config

Wire the `backend=` parameter through `agents.py`, `loop/engine.py`, and CLI commands. Persist backend choice in session config.

### Tasks
- [ ] Add `backend: str = "direct"` parameter to `agents.py: discuss()`, `synthesize_context()`, `generate_plan()`. Pass through to `query_claude(..., backend=backend)`. ~3 lines per function.
- [ ] Add `"claude_backend"` to engine config in `loop/engine.py`. Revision calls pass `backend=self.config.get("claude_backend", "direct")` to `query_claude()`.
- [ ] Update `cli.py: start` command: add `--claude-backend` option (choices: "direct", "sdk", default: None for auto-detect). Call `resolve_default_backend()` if not provided. Store in `session_config.config_json["claude_backend"]`. Log the resolved backend. Print warning if user forces `--claude-backend direct` with OAuth only.
- [ ] Update `cli.py` session-aware commands (`discuss`, `generate`, `review`): read `session_config["claude_backend"]` from DB, pass to agents/engine as `backend=`. Fallback to `resolve_default_backend()` if not in config (backward compat for pre-existing sessions).
- [ ] Update existing tests: `test_agents.py` mock calls gain `backend=` in signature (~4 assertions). `test_review_cli.py` engine config includes `claude_backend`. `test_cli.py` start command stores backend in config.
- [ ] Create `tests/test_backend_wiring.py`: verify `discuss()` passes backend to `query_claude`, `generate_plan()` passes backend, engine revision passes backend from config, CLI reads backend from session config, `--claude-backend` flag persisted, auto-detect from auth works. 8+ tests.

### Deliverables
- [ ] `agents.py` functions accept and pass `backend=`
- [ ] `loop/engine.py` reads `claude_backend` from config
- [ ] CLI `start` stores backend in session config (auto-detected or explicit)
- [ ] CLI `discuss`/`generate`/`review` read backend from session config
- [ ] `pytest tests/test_backend_wiring.py` passes with 8+ tests
- [ ] All existing tests still pass

## Milestone 3: Check Command, Observability, and Integration

Update the `check` command for backend-aware validation. Add observability. Run full test suite.

### Tasks
- [ ] Update `cli.py: check` command: validate both backends when installed. Default backend readiness = pass/fail. Optional backend = informational ("available" or "unavailable (optional)"). Show auth detection result ("direct: ANTHROPIC_API_KEY detected" or "sdk: OAuth token detected"). Add `--claude-backend` option to `--probe` for testing specific backend. Add `--session <id>` to validate session-specific backend.
- [ ] Add `anthropic` import check alongside existing `openai` and `claude_agent_sdk` checks.
- [ ] Update observability: log `backend=` in `query_claude()` at DEBUG level. Log `resolve_default_backend()` result at INFO in `start`. Record `claude_backend` in session config (already done in M2).
- [ ] Update `tests/test_check.py`: verify both-backend validation, default backend determines pass/fail, optional backend informational, `--probe` with `--claude-backend`, `--session` validation. 6+ new tests.
- [ ] Run full suite `pytest tests/` confirming all Plan 1 + Plan 2 + Observability + Direct API tests pass together.
- [ ] Manual smoke test: with active Claude Code session, run `planner-auto discuss <id> "test message" --done` and verify it works via direct backend (the original blocker).

### Deliverables
- [ ] `check` validates both backends, pass/fail based on default
- [ ] `--probe --claude-backend` and `--session` options working
- [ ] Backend logged in session logs and config
- [ ] `pytest tests/` passes with all tests green
- [ ] Manual smoke test confirms direct API works alongside active Claude Code session
