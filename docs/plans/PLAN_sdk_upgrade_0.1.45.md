# Claude Agent SDK Upgrade (0.1.25 → 0.1.45) - Implementation Plan

## Overview

Upgrade orchestrator-auto to leverage new Claude Agent SDK features from v0.1.26 through v0.1.45. This includes forward-compatible message parsing, `ThinkingConfig` types replacing the deprecated `max_thinking_tokens`, per-agent `effort` control, and new hook events for tool failure tracking and notification bridging.

**Reference:** `orchestrator-auto/docs/proposals/PROPOSAL_sdk_upgrade_0.1.45.md`

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
- [ ] Add `effort` parameter to `BaseAgent.__init__()` in `agents.py` (type: `Optional[str]`, default: `None`)
- [ ] Pass `effort` through to `ClaudeAgentOptions` in `BaseAgent._get_options()` when set
- [ ] Thread `effort` through `create_planner_agent()` and `create_executor_agent()` factory functions in `agents.py`
- [ ] Add `planner_effort` and `executor_effort` parameters to `Orchestrator.__init__()` in `engine.py`
- [ ] Pass effort values through `_create_planner()` and `_create_executor()` in `engine.py`
- [ ] Add `--planner-effort` and `--executor-effort` CLI flags (type: `click.Choice(['low', 'medium', 'high', 'max'])`) to `start` and `watch` commands in `cli.py`
- [ ] Add `get_planner_effort()` and `get_executor_effort()` config helpers in `config.py` (priority: CLI > env var `ORCHESTRATOR_PLANNER_EFFORT` > config file `effort.planner` > `None`)
- [ ] Wire CLI flags through `_start_workflow()` and `_run_queue_item()` in `cli.py`
- [ ] Add config file support: `effort:` section with `planner:` and `executor:` keys in `config.py`
- [ ] Write unit tests: `BaseAgent` passes `effort` to `ClaudeAgentOptions` correctly in `tests/test_agents.py`
- [ ] Write unit tests: config resolution priority (CLI > env > config > None) in `tests/test_config.py`

### Deliverables
- [ ] `agents.py` — `BaseAgent`, `create_planner_agent`, `create_executor_agent` accept `effort` parameter
- [ ] `engine.py` — `Orchestrator` passes effort to agent factories
- [ ] `cli.py` — `--planner-effort` and `--executor-effort` flags on `start` and `watch`
- [ ] `config.py` — `get_planner_effort()`, `get_executor_effort()` with full priority chain
- [ ] `tests/test_agents.py` — effort parameter tests passing
- [ ] `tests/test_config.py` — effort config resolution tests passing

---

## Milestone 3: Add `ThinkingConfig` Support

Replace the deprecated `max_thinking_tokens` with the new `ThinkingConfig` types. Support three modes: `adaptive` (Claude decides when to think), `enabled` with explicit budget, and `disabled`. This future-proofs thinking control and provides finer granularity.

### Tasks
- [ ] Import `ThinkingConfig` types in `agents.py`: `ThinkingConfigAdaptive`, `ThinkingConfigEnabled`, `ThinkingConfigDisabled` from `claude_agent_sdk`
- [ ] Add `thinking` parameter to `BaseAgent.__init__()` (type: `Optional[Union[str, int, dict]]`, default: `None`)
  - `"adaptive"` → `ThinkingConfigAdaptive()`
  - `"disabled"` → `ThinkingConfigDisabled()`
  - `int` value → `ThinkingConfigEnabled(budget_tokens=value)`
  - `dict` → pass through directly (for advanced config)
- [ ] Add `_resolve_thinking_config()` private method to `BaseAgent` that maps input to SDK types
- [ ] Pass resolved `ThinkingConfig` to `ClaudeAgentOptions` in `_get_options()`
- [ ] Thread `thinking` through `create_planner_agent()` and `create_executor_agent()` factories
- [ ] Add `planner_thinking` and `executor_thinking` to `Orchestrator.__init__()` in `engine.py`
- [ ] Add `--planner-thinking` and `--executor-thinking` CLI flags to `start` and `watch` (type: `str`, accepting `adaptive`, `disabled`, or integer token budget)
- [ ] Add config file support: `thinking:` section with `planner:` and `executor:` keys in `config.py`
- [ ] Write unit tests: `_resolve_thinking_config()` maps all input forms correctly in `tests/test_agents.py`
- [ ] Write unit tests: thinking config resolution and CLI parsing in `tests/test_config.py`

### Deliverables
- [ ] `agents.py` — `ThinkingConfig` imports, `_resolve_thinking_config()`, `thinking` parameter on `BaseAgent`
- [ ] `engine.py` — passes thinking config to agents
- [ ] `cli.py` — `--planner-thinking` and `--executor-thinking` flags
- [ ] `config.py` — thinking config helpers
- [ ] `tests/test_agents.py` — thinking config resolution tests passing
- [ ] `tests/test_config.py` — thinking config CLI/config tests passing

---

## Milestone 4: Add `PostToolUseFailure` Hook for Tool Failure Tracking

Wire the `PostToolUseFailure` hook event (SDK v0.1.26) into the agent system. This captures tool execution failures in real-time, feeding into the existing `_tool_invocations` tracking and enabling failure-count reporting per milestone.

### Tasks
- [ ] Import `HookMatcher` from `claude_agent_sdk` in `agents.py`
- [ ] Add `_tool_failure_count` counter to `BaseAgent.__init__()`
- [ ] Create `_on_tool_failure()` async callback in `BaseAgent` that increments counter and appends failure details to `_tool_invocations`
- [ ] Register `PostToolUseFailure` hook in `_get_options()` via `hooks` parameter (matcher: `"*"` for all tools)
- [ ] Add `get_tool_failure_count()` method to `BaseAgent`
- [ ] Add `reset_tool_failure_count()` method (called when advancing milestones)
- [ ] Log tool failure count in milestone progress output in `engine.py` (e.g., "Tool failures this milestone: 2")
- [ ] Write unit tests: hook registration, failure counting, invocation tracking in `tests/test_agents.py`

### Deliverables
- [ ] `agents.py` — `PostToolUseFailure` hook wired, `_tool_failure_count`, `get_tool_failure_count()`
- [ ] `engine.py` — logs tool failure count after milestone execution
- [ ] `tests/test_agents.py` — tool failure hook tests passing

---

## Milestone 5: Add `Notification` Hook and Bridge to Telegram

Wire the `Notification` hook event (SDK v0.1.29) to capture SDK notifications (rate limits, warnings) and optionally forward them to Telegram. This gives users visibility into operational issues without watching the terminal.

### Tasks
- [ ] Create `_on_notification()` async callback in `BaseAgent` that stores notification events
- [ ] Add `_notifications` list to `BaseAgent.__init__()` to capture notification history
- [ ] Register `Notification` hook in `_get_options()` alongside the existing PostToolUseFailure hook
- [ ] Add `get_notifications()` and `clear_notifications()` methods to `BaseAgent`
- [ ] Add optional `on_notification` callback parameter to `BaseAgent.__init__()` for external consumers
- [ ] In `engine.py`, pass a notification callback that logs to session logger and optionally sends to Telegram
- [ ] In `engine.py`, when `telegram_notifier` is set, forward rate-limit and warning notifications via `telegram_notifier.send_notification()`
- [ ] Add `send_notification(message: str, level: str)` method to `TelegramNotifier` in `telegram.py` (reuse existing `_send_message()` with a notification prefix)
- [ ] Write unit tests: notification capture, callback invocation in `tests/test_agents.py`
- [ ] Write unit tests: Telegram notification forwarding in `tests/test_telegram.py`

### Deliverables
- [ ] `agents.py` — `Notification` hook wired, `_notifications` list, `on_notification` callback
- [ ] `engine.py` — notification callback bridges to logger and Telegram
- [ ] `telegram.py` — `send_notification()` method
- [ ] `tests/test_agents.py` — notification tests passing
- [ ] `tests/test_telegram.py` — notification forwarding tests passing

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
