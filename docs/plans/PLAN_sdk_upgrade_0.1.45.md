# Claude Agent SDK Upgrade (0.1.25 → 0.1.45) - Implementation Plan

> **Status:** Superseded. The upgrade from 0.1.25 → 0.1.46 has been completed. All milestones in this plan are implemented in the current codebase. For the next upgrade (0.1.46 → 0.1.50), see `orchestrator-auto/docs/proposals/PROPOSAL_sdk_upgrade_0.1.50.md`.

## Overview

Upgrade orchestrator-auto to leverage new Claude Agent SDK features from v0.1.26 through v0.1.45. This includes forward-compatible message parsing, `ThinkingConfig` types replacing the deprecated `max_thinking_tokens`, per-agent `effort` control, and new hook events for tool failure tracking and notification bridging.

**Reference:** `orchestrator-auto/docs/proposals/PROPOSAL_sdk_upgrade_0.1.50.md` (updated from 0.1.45 target)

### Orchestrator Construction Sites

All new parameters (`effort`, `thinking`) must be threaded through **every** path that constructs an `Orchestrator` or agent:

| # | Layer | File | Method | Currently wires models? |
|---|-------|------|--------|------------------------|
| 1 | CLI direct | `cli.py` | `start()` → `Orchestrator(...)` | Yes |
| 2 | CLI queue | `cli.py` → `controllers/queue_controller.py` | `QueueController.__init__()` → `_run_item()` → `Orchestrator(...)` | Yes |
| 3 | CLI watch | `cli.py` → `controllers/watch_controller.py` | `WatchController.__init__()` → `Orchestrator(...)` | Yes |
| 4 | TUI | `tui/app.py` | `OrchestratorTUI._run_orchestrator()` → `Orchestrator(...)` | Yes |
| 5 | TUI watch | `tui/watch_app.py` → `controllers/watch_controller.py` | `WatchTUI` → `WatchController(...)` → `Orchestrator(...)` | Yes |

### DB Persistence Decision

Today, `planner_model` and `executor_model` are stored in the `sessions` table and restored on resume. New `effort` and `thinking` settings follow the same pattern:

- **Add DB columns** via ALTER TABLE (same pattern as existing model columns in `db.py:85-92`)
- **Store on create** in `db.create_session()`
- **Restore on resume** in `engine.py` Orchestrator `__init__()` resume path (lines 149-154)
- **No new resume CLI flags** — settings restore from DB automatically (matching existing model behavior)

---

## Milestone 1: Bump SDK Version and Verify Stability

Raise the minimum SDK version from `>=0.1.25` to `>=0.1.40` to get the forward-compatible message parsing fix (unknown message types like `rate_limit_event` silently skipped instead of crashing) and the `AssistantMessage.error` bug fix from v0.1.28.

### Tasks
- [ ] Update `pyproject.toml` dependency: `"claude-agent-sdk>=0.1.25"` → `"claude-agent-sdk>=0.1.40"`
- [ ] Update `environment.yml` if it pins `claude-agent-sdk` (check and update if present)
- [ ] Run full test suite `pytest tests/ -v` to verify no regressions
- [ ] Verify `agents.py` imports still resolve cleanly (no removed/renamed symbols)
- [ ] Check if any existing code uses `max_thinking_tokens` (currently none, but verify)

### Deliverables
- [ ] `pyproject.toml` updated with `>=0.1.40`
- [ ] `environment.yml` updated (if applicable)
- [ ] All existing tests passing (zero regressions)

---

## Milestone 2: Add `effort` Parameter to Agent System

Add per-agent `effort` control (`"low"` / `"medium"` / `"high"` / `"max"`) so planner and executor can have independent reasoning depth. This is the highest-value feature — it directly impacts cost, speed, and quality.

### Tasks

**agents.py — Core parameter support:**
- [ ] Add `effort` parameter to `BaseAgent.__init__()` (type: `Optional[str]`, default: `None`)
- [ ] Pass `effort` through to `ClaudeAgentOptions` in `BaseAgent._get_options()` when set
- [ ] Thread `effort` through `create_planner_agent()` and `create_executor_agent()` factory functions

**engine.py — Orchestrator wiring:**
- [ ] Add `planner_effort` and `executor_effort` parameters to `Orchestrator.__init__()`
- [ ] Pass effort values through `_create_planner()` (line 366) and `_create_executor()` (line 396)

**DB persistence (db.py):**
- [ ] Add `planner_effort TEXT` and `executor_effort TEXT` columns via ALTER TABLE (same pattern as `planner_model`/`executor_model` at lines 85-92)
- [ ] Add `planner_effort` and `executor_effort` params to `create_session()` INSERT (line 385)
- [ ] Restore effort on resume: add to `Orchestrator.__init__()` resume path alongside model restoration (lines 149-154)

**config.py — Config resolution:**
- [ ] Add `get_planner_effort()` and `get_executor_effort()` helpers (priority: CLI > env var `ORCHESTRATOR_PLANNER_EFFORT` / `ORCHESTRATOR_EXECUTOR_EFFORT` > config file `effort.planner` / `effort.executor` > `None`)

**cli.py — CLI flags (start command, line 1264):**
- [ ] Add `--planner-effort` and `--executor-effort` flags (type: `click.Choice(['low', 'medium', 'high', 'max'])`) to `start` command
- [ ] Wire flags through to `Orchestrator(...)` construction in `start()` (line 1424)

**controllers — Queue and Watch wiring:**
- [ ] Add `planner_effort` and `executor_effort` to `QueueController.__init__()` (`controllers/queue_controller.py:70`) and pass through `_run_item()` (line 428) → `Orchestrator(...)`
- [ ] Add `planner_effort` and `executor_effort` to `WatchController.__init__()` (`controllers/watch_controller.py:96`) and pass through → `Orchestrator(...)`

**TUI — App and Watch wiring:**
- [ ] Add `planner_effort` and `executor_effort` to `OrchestratorTUI.__init__()` (`tui/app.py:120`) and pass through `_run_orchestrator()` (line 238) → `Orchestrator(...)`
- [ ] Add `planner_effort` and `executor_effort` to `WatchTUI.__init__()` (`tui/watch_app.py:261`) and pass through → `WatchController(...)`

**cli.py — Watch command:**
- [ ] Add `--planner-effort` and `--executor-effort` flags to `watch` command (`cli.py:3591`)
- [ ] Wire through `_run_watch_file()` (`cli.py:3773`) and TUI watch construction paths

**Tests:**
- [ ] Write unit tests: `BaseAgent` passes `effort` to `ClaudeAgentOptions` correctly in `tests/test_agents.py`
- [ ] Write unit tests: config resolution priority (CLI > env > config > None) in `tests/test_config.py`
- [ ] Write unit tests: DB column migration and persistence in `tests/test_db.py`

### Deliverables
- [ ] `agents.py` — `BaseAgent`, `create_planner_agent`, `create_executor_agent` accept `effort`
- [ ] `engine.py` — `Orchestrator` passes effort to agent factories and restores from DB on resume
- [ ] `db.py` — `planner_effort`/`executor_effort` columns, stored on create, restored on resume
- [ ] `cli.py` — `--planner-effort` and `--executor-effort` flags on `start` and `watch`
- [ ] `config.py` — `get_planner_effort()`, `get_executor_effort()` with full priority chain
- [ ] `controllers/queue_controller.py` — threads effort through to Orchestrator
- [ ] `controllers/watch_controller.py` — threads effort through to Orchestrator
- [ ] `tui/app.py` — threads effort through to Orchestrator
- [ ] `tui/watch_app.py` — threads effort through to WatchController
- [ ] Tests passing in `test_agents.py`, `test_config.py`, `test_db.py`

---

## Milestone 3: Add `ThinkingConfig` Support

Replace the deprecated `max_thinking_tokens` with the new `ThinkingConfig` types. Support three modes: `adaptive` (Claude decides when to think), `enabled` with explicit budget, and `disabled`. Same wiring pattern as M2 across all construction sites.

### Tasks

**agents.py — Core parameter support:**
- [ ] Import `ThinkingConfig` types: `ThinkingConfigAdaptive`, `ThinkingConfigEnabled`, `ThinkingConfigDisabled` from `claude_agent_sdk`
- [ ] Add `thinking` parameter to `BaseAgent.__init__()` (type: `Optional[Union[str, int, dict]]`, default: `None`)
  - `"adaptive"` → `ThinkingConfigAdaptive()`
  - `"disabled"` → `ThinkingConfigDisabled()`
  - `int` value → `ThinkingConfigEnabled(budget_tokens=value)`
  - `dict` → pass through directly (for advanced config)
- [ ] Add `_resolve_thinking_config()` private method to `BaseAgent` that maps input to SDK types
- [ ] Pass resolved `ThinkingConfig` to `ClaudeAgentOptions` in `_get_options()`
- [ ] Thread `thinking` through `create_planner_agent()` and `create_executor_agent()` factories

**engine.py — Orchestrator wiring:**
- [ ] Add `planner_thinking` and `executor_thinking` to `Orchestrator.__init__()`
- [ ] Pass thinking values through `_create_planner()` and `_create_executor()`

**DB persistence (db.py):**
- [ ] Add `planner_thinking TEXT` and `executor_thinking TEXT` columns via ALTER TABLE
- [ ] Store as serialized string in `create_session()` (e.g., `"adaptive"`, `"disabled"`, `"10000"`)
- [ ] Restore on resume alongside effort/model restoration in `Orchestrator.__init__()` resume path

**config.py — Config resolution:**
- [ ] Add config file support: `thinking:` section with `planner:` and `executor:` keys
- [ ] Add `get_planner_thinking()` and `get_executor_thinking()` helpers (CLI > env > config > None)

**cli.py — CLI flags:**
- [ ] Add `--planner-thinking` and `--executor-thinking` CLI flags to `start` and `watch` (type: `str`, accepting `adaptive`, `disabled`, or integer token budget)

**controllers and TUI — Full wiring (same pattern as M2):**
- [ ] `controllers/queue_controller.py` — accept and thread `planner_thinking`/`executor_thinking`
- [ ] `controllers/watch_controller.py` — accept and thread `planner_thinking`/`executor_thinking`
- [ ] `tui/app.py` — accept and thread through `_run_orchestrator()`
- [ ] `tui/watch_app.py` — accept and thread through → `WatchController`

**Tests:**
- [ ] Write unit tests: `_resolve_thinking_config()` maps all input forms correctly in `tests/test_agents.py`
- [ ] Write unit tests: thinking config resolution and CLI parsing in `tests/test_config.py`
- [ ] Write unit tests: DB persistence round-trip in `tests/test_db.py`

### Deliverables
- [ ] `agents.py` — `ThinkingConfig` imports, `_resolve_thinking_config()`, `thinking` parameter on `BaseAgent`
- [ ] `engine.py` — passes thinking config to agents and restores from DB on resume
- [ ] `db.py` — `planner_thinking`/`executor_thinking` columns, stored and restored
- [ ] `cli.py` — `--planner-thinking` and `--executor-thinking` flags on `start` and `watch`
- [ ] `config.py` — thinking config helpers
- [ ] `controllers/queue_controller.py` — threads thinking through to Orchestrator
- [ ] `controllers/watch_controller.py` — threads thinking through to Orchestrator
- [ ] `tui/app.py` — threads thinking through to Orchestrator
- [ ] `tui/watch_app.py` — threads thinking through to WatchController
- [ ] Tests passing in `test_agents.py`, `test_config.py`, `test_db.py`

---

## Milestone 4: Wire Hooks Plumbing and Add Tool Failure Tracking

**Prerequisite work:** `BaseAgent._get_options()` currently does NOT pass `self.hooks` to `ClaudeAgentOptions` — this is dead code. Before adding `PostToolUseFailure`, we must first wire the existing hooks parameter through, then build the failure tracking on top. Additionally, `db.save_tool_invocation()` / `db.save_tool_invocations_batch()` / `db.get_tool_invocations()` exist but are never called in production — failure data must be persisted to be useful in status views.

### Tasks

**agents.py — Fix existing hooks plumbing (prerequisite):**
- [ ] Verify SDK hook callback signature against installed SDK version: confirm `HookMatcher`, `HookEvent` type literals, and async callback signature `(input_data, tool_use_id, context) -> dict`
- [ ] Import `HookMatcher` from `claude_agent_sdk` (currently zero imports in production code)
- [ ] Wire `self.hooks` through `_get_options()` → `ClaudeAgentOptions(hooks=...)` — the param is accepted at `__init__` (line 134) but never forwarded (gap at line 196-212)

**agents.py — PostToolUseFailure hook:**
- [ ] Add `_tool_failure_count: int` counter to `BaseAgent.__init__()`
- [ ] Create `_on_tool_failure()` async callback matching SDK hook signature
- [ ] Callback appends failure details (tool name, error, timestamp) to `_tool_invocations` list with `success=False`
- [ ] Register `PostToolUseFailure` hook in `_get_options()` via `hooks` dict — merge with any externally-provided `self.hooks`
- [ ] Add `get_tool_failure_count()` and `reset_tool_failure_count()` methods

**DB persistence — Wire existing unused functions:**
- [ ] In `engine.py`, after each milestone execution completes, call `db.save_tool_invocations_batch()` with the executor's `_tool_invocations` data (function exists at `db.py:1266` but is never called)
- [ ] Map `BaseAgent._tool_invocations` list items to the `tool_invocations` table schema: `session_id`, `agent` ("executor"/"planner"), `milestone_number`, `tool_name`, `input_summary`, `output_summary`, `success`
- [ ] Call `executor.clear_tool_invocations()` after persisting (prevent double-write on retry)

**engine.py — Failure reporting:**
- [ ] After milestone execution, log tool failure count (e.g., "Tool failures this milestone: 2") if count > 0
- [ ] Include failure count in milestone status stored in DB (amend `db.update_milestone()` call or add to `executor_report`)

**Tests:**
- [ ] Write unit tests: `_get_options()` now includes hooks when `self.hooks` is set (fix for existing gap)
- [ ] Write unit tests: `PostToolUseFailure` callback increments counter and appends to invocations
- [ ] Write unit tests: `db.save_tool_invocations_batch()` is called after milestone with correct data
- [ ] Write integration test: mock tool failure → verify persisted in DB → verify count in logs

### Deliverables
- [ ] `agents.py` — `HookMatcher` imported, `self.hooks` wired through `_get_options()`, `PostToolUseFailure` registered, `_tool_failure_count` counter
- [ ] `engine.py` — calls `db.save_tool_invocations_batch()` after milestones, logs failure counts
- [ ] `tests/test_agents.py` — hooks plumbing + failure tracking tests passing
- [ ] `tests/test_engine.py` — tool invocation persistence tests passing

---

## Milestone 5: Add `Notification` Hook and Bridge to Telegram

Wire the `Notification` hook event (SDK v0.1.29) to capture SDK notifications (rate limits, warnings) and optionally forward them to Telegram. Includes rate-limiting/debounce to prevent notification spam.

**Design constraint:** SDK `rate_limit_event` notifications can fire frequently during heavy usage. Forwarding each one to Telegram could create a spam loop or hit Telegram's own rate limits. Notifications must be debounced and filtered.

### Tasks

**agents.py — Notification hook:**
- [ ] Create `_on_notification()` async callback matching SDK hook signature
- [ ] Add `_notifications: List[Dict[str, Any]]` to `BaseAgent.__init__()` to capture notification history (type, message, timestamp)
- [ ] Register `Notification` hook in `_get_options()` alongside PostToolUseFailure hook
- [ ] Add `get_notifications()` and `clear_notifications()` methods
- [ ] Add optional `on_notification: Optional[Callable[[str, str], None]]` callback parameter to `BaseAgent.__init__()` for external consumers (called with `(notification_type, message)`)

**engine.py — Notification routing:**
- [ ] Pass a notification callback to executor/planner agents that logs to session logger
- [ ] When `telegram_notifier` is set, route notifications through a debounce filter before forwarding

**telegram.py — Notification method with rate protection:**
- [ ] Add `send_notification(message: str, level: str = "info")` method to `TelegramNotifier` (reuse `_send_message()` with notification prefix icon: info=ℹ️, warning=⚠️, error=❌)
- [ ] Add debounce/dedup logic: skip sending if same notification type was sent within last 60 seconds (use `_last_notification_times: Dict[str, float]` on TelegramNotifier)
- [ ] Add rate-limit handling: if `_send_message()` gets HTTP 429, respect `Retry-After` header and drop notification (log locally instead) — `TelegramNotifier._send_message()` currently has no backoff

**Filtering rules (engine.py):**
- [ ] `rate_limit` notifications → Telegram only if first occurrence in 5 minutes, otherwise log-only
- [ ] `warning` notifications → always forward to Telegram (low frequency)
- [ ] `info` notifications → log-only, never forward to Telegram

**Tests:**
- [ ] Write unit tests: notification capture, callback invocation in `tests/test_agents.py`
- [ ] Write unit tests: debounce logic suppresses duplicate notifications in `tests/test_telegram.py`
- [ ] Write unit tests: filtering rules (rate_limit debounced, warning forwarded, info logged) in `tests/test_engine.py`
- [ ] Write unit tests: HTTP 429 handling in `send_notification()` in `tests/test_telegram.py`

### Deliverables
- [ ] `agents.py` — `Notification` hook wired, `_notifications` list, `on_notification` callback
- [ ] `engine.py` — notification callback with filtering rules, bridges to logger and Telegram
- [ ] `telegram.py` — `send_notification()` with debounce, rate-limit handling
- [ ] `tests/test_agents.py` — notification hook tests passing
- [ ] `tests/test_telegram.py` — debounce + rate-limit tests passing
- [ ] `tests/test_engine.py` — notification filtering tests passing

---

## Milestone 6: Documentation and Cleanup

Update all documentation references to reflect the new SDK version, new CLI flags, and new config options. Archive the superseded proposal.

### Tasks
- [ ] Update `PROPOSAL_sdk_upgrade_0.1.23.md` — add header note: "Superseded by PROPOSAL_sdk_upgrade_0.1.45.md"
- [ ] Update `orchestrator-auto/README.md` — add `--planner-effort`, `--executor-effort`, `--planner-thinking`, `--executor-thinking` to CLI reference sections
- [ ] Update `orchestrator-auto/docs/CLI_REFERENCE.md` — add new flags with descriptions and examples
- [ ] Update `orchestrator-auto/orchestrator_auto/resources/CLI_REFERENCE.md` — mirror the docs version
- [ ] Update config file example in `workflows/CLAUDE_orch_v2.md` — add `effort:` and `thinking:` sections to the example YAML
- [ ] Update `CLAUDE.md` — update SDK version mention if present, add effort/thinking to config priority note
- [ ] Update `PROPOSAL_sdk_upgrade_0.1.45.md` — change status from "Draft" to "Implemented", fill in actual version numbers used
- [ ] Run full test suite one final time to confirm nothing was missed

### Deliverables
- [ ] `PROPOSAL_sdk_upgrade_0.1.23.md` — marked as superseded
- [ ] `README.md` — new CLI flags documented
- [ ] `docs/CLI_REFERENCE.md` — new flags with examples
- [ ] `orchestrator_auto/resources/CLI_REFERENCE.md` — mirrors docs version
- [ ] `workflows/CLAUDE_orch_v2.md` — config example updated
- [ ] `PROPOSAL_sdk_upgrade_0.1.45.md` — status changed to Implemented
- [ ] All tests passing
