# Proposal: Upgrade to Claude Agent SDK 0.1.50

**Author:** Claude
**Created:** 2026-03-04
**Updated:** 2026-03-23
**Status:** Draft (revised per review feedback)
**SDK Version:** 0.1.46 → 0.1.50
**Supersedes:** `PROPOSAL_sdk_upgrade_0.1.23.md`, prior version of this file (0.1.47 target)

---

## Summary

Bump orchestrator-auto from `claude-agent-sdk>=0.1.46,<0.2.0` to `>=0.1.50,<0.2.0` and adopt a **narrowed set** of new SDK features: typed `RateLimitEvent` handling and carefully-scoped live token usage via delta-style updates. Session management features (`tag_session`, `rename_session`, `get_session_info`) and `AgentDefinition` enhancements are deferred until prerequisite work is done.

### Scope Decision

This proposal was narrowed after review. The original version proposed session tagging, `AgentDefinition` enhancements, and naive per-turn usage — all of which have blockers in the current codebase. See [Review Findings](#review-findings--rejected-items) for details.

**In scope:**
- Dependency bump (`pyproject.toml`, `environment.yml`)
- `RateLimitEvent` message handling in `agents.py`
- Delta-style live token usage from `AssistantMessage.usage` (separate from existing `on_token_usage` path)

**Deferred (with prerequisites documented):**
- Session tagging/renaming — requires capturing the real SDK session UUID first
- `AgentDefinition.mcpServers` — requires rewriting `ExploreSubAgent` from standalone client to sub-agent pattern
- `get_session_info()` — depends on session UUID capture

---

## Current State

| Item | Value |
|------|-------|
| `pyproject.toml` pin | `>=0.1.46,<0.2.0` (line 13) |
| `environment.yml` pin | `>=0.1.46,<0.2.0` (line 9) |
| Latest available | **0.1.50** (March 20, 2026) |
| Python requirement | 3.10+ |
| Package | `claude-agent-sdk` (renamed from `claude-code-sdk` in v0.1.0) |
| License | MIT (governed by Anthropic Commercial ToS) |
| Bundled CLI | v2.1.81 (in SDK 0.1.50) |

orchestrator-auto already uses SDK features through v0.1.46: `effort`, `ThinkingConfig`, `PostToolUseFailure`/`Notification` hooks, `ResultMessage.stop_reason`, `rewind_files()`, `get_mcp_status()`, and `tool_use_result` tracking.

---

## SDK Changelog (v0.1.46 → v0.1.50)

### Already Adopted (v0.1.25 → v0.1.46)

Features from prior SDK versions that orchestrator-auto **already uses**:

| Version | Feature | Status in orchestrator-auto |
|---------|---------|----------------------------|
| v0.1.17 | `UserMessage.uuid`, `rewind_files()` | `agents.py` — checkpoint/rewind on milestone rejection |
| v0.1.22 | `tool_use_result` field | `agents.py` — `_tool_invocations` tracking |
| v0.1.23 | `get_mcp_status()` | `agents.py` — MCP health checks |
| v0.1.26 | `PostToolUseFailure` hook | `agents.py` — `_on_tool_failure()` callback |
| v0.1.29 | `Notification` hook | `agents.py` — `_on_notification()` callback |
| v0.1.36 | `ThinkingConfig` types | `agents.py` — `_resolve_thinking_config()` |
| v0.1.36 | `effort` field | `agents.py` + `cli.py` — `--planner-effort`/`--executor-effort` |
| v0.1.40 | Forward-compatible message parsing | Implicit (unknown message types silently skipped) |
| v0.1.46 | `ResultMessage.stop_reason` | `agents.py` — `_last_stop_reason` tracking |
| v0.1.46 | Hook `agent_id`/`agent_type` fields | Available but not yet extracted in hook callbacks |

### New in v0.1.47–v0.1.50 (Not Yet Adopted)

| Version | Date | Feature | PR |
|---------|------|---------|----|
| **v0.1.47** | Mar 6, 2026 | CLI-only bump to v2.1.70 | — |
| **v0.1.48** | Mar 7, 2026 | Bug fix: `include_partial_messages=True` not delivering `input_json_delta` events (regression in v0.1.36–v0.1.47). Fixed via `CLAUDE_CODE_ENABLE_FINE_GRAINED_TOOL_STREAMING` env var | [#644](https://github.com/anthropics/claude-agent-sdk-python/pull/644) |
| **v0.1.49** | Mar 17, 2026 | `AgentDefinition`: added `skills`, `memory`, `mcpServers` fields for richer sub-agent configuration | [#684](https://github.com/anthropics/claude-agent-sdk-python/pull/684) |
| **v0.1.49** | Mar 17, 2026 | Per-turn `usage` preserved on `AssistantMessage` (previously only on `ResultMessage`) | [#685](https://github.com/anthropics/claude-agent-sdk-python/pull/685) |
| **v0.1.49** | Mar 17, 2026 | `tag_session()` — tag running sessions with Unicode-sanitized metadata | [#670](https://github.com/anthropics/claude-agent-sdk-python/pull/670) |
| **v0.1.49** | Mar 17, 2026 | `rename_session()` — rename sessions after creation | [#668](https://github.com/anthropics/claude-agent-sdk-python/pull/668) |
| **v0.1.49** | Mar 17, 2026 | Typed `RateLimitEvent` message — distinct message subclass for rate limit events (replaces generic notification pattern) | [#648](https://github.com/anthropics/claude-agent-sdk-python/pull/648) |
| **v0.1.49** | Mar 17, 2026 | Reverted 0.1.48 env-var workaround for fine-grained streaming — now handled upstream | [#671](https://github.com/anthropics/claude-agent-sdk-python/pull/671) |
| **v0.1.49** | Mar 17, 2026 | `CLAUDE_CODE_ENTRYPOINT`: default-if-absent semantics matching TS SDK | [#686](https://github.com/anthropics/claude-agent-sdk-python/pull/686) |
| **v0.1.49** | Mar 17, 2026 | Added macOS x86_64 wheel to published matrix | [#661](https://github.com/anthropics/claude-agent-sdk-python/pull/661) |
| **v0.1.49** | Mar 17, 2026 | Docs: clarified `allowed_tools` as a permission allowlist (not a tool set) | [#649](https://github.com/anthropics/claude-agent-sdk-python/pull/649) |
| **v0.1.50** | Mar 20, 2026 | `get_session_info()` — retrieve session metadata including `tag` and `created_at` | [#667](https://github.com/anthropics/claude-agent-sdk-python/pull/667) |
| **v0.1.50** | Mar 20, 2026 | `SDKSessionInfo`: added `tag` and `created_at` fields | [#667](https://github.com/anthropics/claude-agent-sdk-python/pull/667) |
| **v0.1.50** | Mar 20, 2026 | CLI bump to v2.1.81 | — |

### CLI-Only Releases (v0.1.46+)

| Version | Bundled CLI |
|---------|-------------|
| v0.1.46 | 2.1.69 |
| v0.1.47 | 2.1.70 |
| v0.1.48 | 2.1.71 |
| v0.1.49 | 2.1.77 |
| v0.1.50 | 2.1.81 |

---

## New Types & API Surface (v0.1.47–v0.1.50)

### Typed `RateLimitEvent` Message (v0.1.49)

A distinct message subclass for rate limit events, replacing the generic notification pattern:

```python
from claude_agent_sdk import RateLimitEvent

async for message in client.receive_messages():
    if isinstance(message, RateLimitEvent):
        logger.warning(f"Rate limited: {message}")
```

### Per-Turn `AssistantMessage.usage` (v0.1.49)

Token usage is now preserved on each `AssistantMessage`, not just `ResultMessage`:

```python
async for message in client.receive_messages():
    if isinstance(message, AssistantMessage):
        if hasattr(message, 'usage') and message.usage:
            input_tokens = message.usage.get("input_tokens", 0)
            output_tokens = message.usage.get("output_tokens", 0)
```

### Session Tagging & Renaming (v0.1.49)

Top-level helper functions (not client instance methods):

```python
from claude_agent_sdk import tag_session, rename_session

# Tag a session (requires SDK session UUID, not orchestrator's local label)
tag_session(
    session_id="550e8400-e29b-41d4-a716-446655440000",
    tag="workflow:auth-feature",   # Unicode-sanitized; pass None to clear
    directory="/path/to/project",  # optional
)

# Rename a session
rename_session(
    session_id="550e8400-e29b-41d4-a716-446655440000",
    title="Auth Feature - M3 in progress",
    directory="/path/to/project",  # optional
)
```

**Note:** These are **top-level functions** that take `session_id: str` and operate directly on session JSONL files — they do not require a `ClaudeSDKClient` instance. However, the `session_id` must be the real SDK session UUID, which orchestrator-auto does not currently capture. See [Review Findings](#session-tagging--renaming--deferred) for why this is deferred.

### `get_session_info()` (v0.1.50)

Also a top-level function:

```python
from claude_agent_sdk import get_session_info

info = get_session_info(session_id="<SDK session UUID>")
# Returns SDKSessionInfo with tag, created_at, summary, etc.
```

### Enhanced `SDKSessionInfo` (v0.1.50)

```python
@dataclass
class SDKSessionInfo:
    session_id: str
    summary: str
    last_modified: int       # Milliseconds since epoch
    file_size: int           # Bytes
    custom_title: str | None
    first_prompt: str | None
    git_branch: str | None
    cwd: str | None
    tag: str | None          # NEW in v0.1.50
    created_at: int | None   # NEW in v0.1.50 — milliseconds since epoch
```

### Enriched `AgentDefinition` (v0.1.49)

New optional fields added to `AgentDefinition`. orchestrator-auto does not currently use `AgentDefinition` or the `agents=` parameter anywhere — `ExploreSubAgent` (`explore.py:204`) creates a standalone `ClaudeSDKClient`. See [Review Findings](#agentdefinition-enhancements--deferred) for why this is deferred.

Documented field types (from SDK source `types.py:42-52`):

| Field | Type | Added |
|-------|------|-------|
| `description` | `str` | existing |
| `prompt` | `str` | existing |
| `tools` | `list[str] \| None` | existing |
| `model` | `str \| None` | existing |
| `skills` | `list[str] \| None` | v0.1.49 |
| `memory` | `dict \| None` | v0.1.49 |
| `mcpServers` | `list[dict] \| None` | v0.1.49 |

### Fine-Grained Tool Streaming Fix (v0.1.48, reverted in v0.1.49)

- v0.1.48: Fixed `include_partial_messages=True` not delivering `input_json_delta` events (regression in v0.1.36–v0.1.47)
- v0.1.49: Reverted the env-var workaround — fix is now handled upstream in the CLI

---

## Previously Adopted Types (v0.1.26–v0.1.46, for reference)

<details>
<summary>Click to expand — already implemented in orchestrator-auto</summary>

### ThinkingConfig Types (v0.1.36)

```python
from claude_agent_sdk import (
    ThinkingConfigAdaptive,   # {"type": "adaptive"} — Claude decides when to think
    ThinkingConfigEnabled,    # {"type": "enabled", "budget_tokens": int} — fixed budget
    ThinkingConfigDisabled,   # {"type": "disabled"} — no thinking
)
```

### Hook Event Types (v0.1.26–v0.1.29)

| Event | Added | Input Type |
|-------|-------|------------|
| `PostToolUseFailure` | v0.1.26 | `PostToolUseFailureHookInput` |
| `Notification` | v0.1.29 | `NotificationHookInput` |
| `SubagentStart` | v0.1.29 | `SubagentStartHookInput` |
| `PermissionRequest` | v0.1.29 | `PermissionRequestHookInput` |

**All 10 hook events:**
`PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `UserPromptSubmit`, `Stop`, `SubagentStop`, `PreCompact`, `Notification`, `SubagentStart`, `PermissionRequest`

### Session History (v0.1.46)

```python
from claude_agent_sdk import list_sessions, get_session_messages
```

### Runtime MCP Management (v0.1.46)

```python
from claude_agent_sdk import add_mcp_server, remove_mcp_server, McpServerStatus
```

### Typed Task Messages (v0.1.46)

```python
from claude_agent_sdk import TaskStarted, TaskProgress, TaskNotification
```

### ResultMessage.stop_reason (v0.1.46)

```python
result.stop_reason  # "end_turn", "max_tokens", etc.
```

</details>

---

## Complete `ClaudeAgentOptions` Field Reference (v0.1.50)

For completeness, the full options surface as of v0.1.50:

```python
@dataclass
class ClaudeAgentOptions:
    # Core
    system_prompt: str | SystemPromptPreset | None = None
    tools: list[str] | ToolsPreset | None = None         # Exact tool set (overrides defaults)
    allowed_tools: list[str] = field(default_factory=list)  # Permission allowlist (auto-approve)
    disallowed_tools: list[str] = field(default_factory=list)  # Always deny (highest priority)
    model: str | None = None
    fallback_model: str | None = None                     # Automatic fallback on failure
    cwd: str | Path | None = None

    # Permissions
    permission_mode: PermissionMode | None = None         # "default"|"acceptEdits"|"plan"|"bypassPermissions"
    can_use_tool: CanUseTool | None = None                # Custom permission callback

    # Sessions
    resume: str | None = None
    fork_session: bool = False
    continue_conversation: bool = False

    # Limits
    max_turns: int | None = None
    max_budget_usd: float | None = None                   # Hard cost cap per session

    # Extended Thinking (v0.1.36)
    thinking: ThinkingConfig | None = None                # Replaces deprecated max_thinking_tokens
    effort: Literal["low", "medium", "high", "max"] | None = None

    # MCP
    mcp_servers: dict[str, McpServerConfig] | str | Path = field(default_factory=dict)

    # Hooks
    hooks: dict[HookEvent, list[HookMatcher]] | None = None

    # Subagents (AgentDefinition enhanced in v0.1.49: +skills, +memory, +mcpServers)
    agents: dict[str, AgentDefinition] | None = None

    # Output
    output_format: dict[str, Any] | None = None           # Structured output (JSON schema validation)
    include_partial_messages: bool = False                  # Streaming token events (fixed in v0.1.49)

    # Settings
    setting_sources: list[SettingSource] | None = None    # "user"|"project"|"local"
    settings: str | None = None

    # Environment
    env: dict[str, str] = field(default_factory=dict)
    add_dirs: list[str | Path] = field(default_factory=list)
    extra_args: dict[str, str | None] = field(default_factory=dict)
    cli_path: str | Path | None = None
    max_buffer_size: int | None = None
    user: str | None = None
    betas: list[SdkBeta] = field(default_factory=list)

    # Plugins & Sandbox
    plugins: list[SdkPluginConfig] = field(default_factory=list)
    sandbox: SandboxSettings | None = None

    # File Operations
    enable_file_checkpointing: bool = False

    # Misc
    permission_prompt_tool_name: str | None = None
    stderr: Callable[[str], None] | None = None

    # DEPRECATED
    max_thinking_tokens: int | None = None                # Use thinking instead
    debug_stderr: Any = sys.stderr                        # Use stderr callback instead
```

### New Top-Level Functions (v0.1.49–v0.1.50)

These are module-level helpers, not `ClaudeSDKClient` instance methods:

```python
from claude_agent_sdk import tag_session, rename_session, get_session_info

# v0.1.49
def tag_session(session_id: str, tag: str | None, directory: str | None = None) -> None
def rename_session(session_id: str, title: str, directory: str | None = None) -> None

# v0.1.50
def get_session_info(session_id: str, directory: str | None = None) -> SDKSessionInfo | None
```

### New Message Type (v0.1.49)

```python
from claude_agent_sdk import RateLimitEvent

# Message union is now:
# UserMessage | AssistantMessage | SystemMessage | ResultMessage | RateLimitEvent | StreamEvent
```

---

## Implementation Plan (Narrowed Scope)

### Phase 1: Version Bump (No Risk)

| Task | Change | File(s) |
|------|--------|---------|
| Bump minimum SDK version | `>=0.1.46,<0.2.0` → `>=0.1.50,<0.2.0` | `pyproject.toml` (line 13) |
| Update `environment.yml` pin | `>=0.1.46,<0.2.0` → `>=0.1.50,<0.2.0` | `environment.yml` (line 9) |
| Verify no regressions | Run `pytest tests/ -v` | — |

### Phase 2: RateLimitEvent Support (Low Risk)

Add `RateLimitEvent` isinstance check to the message loop in `BaseAgent.send_message_async()`.

**Where:** `agents.py:364` — the `async for message in client.receive_messages()` loop.

**Implementation:**

```python
# agents.py — add before the AssistantMessage branch (line 372)
from claude_agent_sdk import RateLimitEvent

async for message in client.receive_messages():
    # Capture UUID from UserMessage (SDK 0.1.17+)
    if isinstance(message, UserMessage):
        ...existing...
    elif isinstance(message, RateLimitEvent):
        # Typed rate limit handling (SDK 0.1.49+)
        logger.warning(f"Rate limited: {message}")
        if self.on_notification:
            self.on_notification({
                "type": "rate_limit",
                "message": str(message),
                "timestamp": time.time(),
            })
    elif isinstance(message, AssistantMessage):
        ...existing...
    elif isinstance(message, ResultMessage):
        ...existing...
```

**Why before AssistantMessage:** `RateLimitEvent` is a distinct message type, not a subclass of `AssistantMessage`. Placing it early prevents it from falling through to the `break` on `ResultMessage`.

| Task | File(s) |
|------|---------|
| Import `RateLimitEvent` from `claude_agent_sdk` | `agents.py` (line 14–24, imports block) |
| Add `isinstance(message, RateLimitEvent)` branch | `agents.py` (line 372, before `AssistantMessage` branch) |
| Log rate limit event and forward to `on_notification` callback | `agents.py` (same branch) |
| Write unit test: `RateLimitEvent` is logged and forwarded | `tests/test_agents.py` |

### Phase 3: Delta-Style Live Token Usage (Low Risk, Careful Scoping)

**Problem:** Naively calling `self.on_token_usage()` from `AssistantMessage.usage` would double-count tokens, inflate API call counts, and break cost tracking. Current consumers all treat each `on_token_usage` callback as a completed API call:
- `agents.py:384–396` — fires once per `ResultMessage`, includes `cost_usd`
- `tui/widgets/stats_panel.py:150–161` — `add_tokens()` increments `self._api_calls += 1`
- `tui/watch_app.py:1373–1384` — `on_tokens_used()` increments `self._session_api_calls += 1`

**Solution:** Introduce a **separate** callback for delta-style live updates that does NOT use the existing `on_token_usage` path. Keep `ResultMessage.usage` as the sole source of truth for final totals, cost, and API call counts.

**Implementation:**

```python
# agents.py — new callback (does NOT replace on_token_usage)

class BaseAgent:
    def __init__(self, ...,
                 on_live_tokens: Optional[Callable[[Dict[str, Any]], None]] = None):
        ...existing...
        self.on_live_tokens = on_live_tokens  # NEW: delta-only, no cost/api_calls

    async def send_message_async(self, ...):
        async for message in client.receive_messages():
            ...existing UserMessage handling...
            elif isinstance(message, AssistantMessage):
                # Emit live token delta (SDK 0.1.49+)
                if self.on_live_tokens and hasattr(message, 'usage') and message.usage:
                    self.on_live_tokens({
                        "input_tokens": message.usage.get("input_tokens", 0),
                        "output_tokens": message.usage.get("output_tokens", 0),
                        "thinking_tokens": message.usage.get("thinking_tokens", 0),
                        "is_live": True,  # Signal: per-turn snapshot, NOT a delta — do not accumulate
                    })
                ...existing text extraction...
            elif isinstance(message, ResultMessage):
                ...existing on_token_usage (unchanged, remains source of truth)...
```

**Consumer contract:**
- `on_token_usage` (existing): fires once per `ResultMessage`. Contains `cost_usd`, final totals. Consumers increment API call counts.
- `on_live_tokens` (new): fires per `AssistantMessage` during streaming. Contains per-turn usage snapshots (not deltas — do not accumulate), no `cost_usd`. Consumers update transient progress display only — never increment API call counts or cumulative totals.

**TUI guardrail:** Any TUI wiring of `on_live_tokens` MUST use a transient/live-only display method. It MUST NOT call:
- `StatsPanel.add_tokens()` (`tui/widgets/stats_panel.py:150`) — this increments `self._api_calls += 1`
- `WatchTUI.on_tokens_used()` (`tui/watch_app.py:1373`) — this increments `self._session_api_calls += 1`

Both of those are final accounting paths reserved for `on_token_usage` / `ResultMessage`. A new `StatsPanel.update_live_tokens()` method should update a transient display label only, with no side effects on counters or totals.

| Task | File(s) |
|------|---------|
| Add `on_live_tokens` parameter to `BaseAgent.__init__()` | `agents.py` (line 136) |
| Emit delta from `AssistantMessage.usage` via `on_live_tokens` | `agents.py` (line 372, inside `AssistantMessage` branch) |
| Do NOT modify existing `on_token_usage` path | `agents.py` (line 384–396, unchanged) |
| Thread `on_live_tokens` through `create_planner_agent()` / `create_executor_agent()` | `agents.py` (factory functions) |
| Thread through `Orchestrator.__init__()` → agent factories | `engine.py` |
| (Optional) Wire to TUI `StatsPanel` for live display | `tui/widgets/stats_panel.py` — new `update_live_tokens()` method (transient display only, MUST NOT call `add_tokens()` or touch `_api_calls`/`_cost`/`_tokens` counters) |
| Write unit test: `on_live_tokens` fires per `AssistantMessage`, `on_token_usage` fires once per `ResultMessage` | `tests/test_agents.py` |
| Write unit test: `StatsPanel.add_tokens()` still only called from `ResultMessage` path | `tests/test_stats_panel.py` |
| Write unit test: `StatsPanel.update_live_tokens()` does NOT increment `_api_calls` or `_cost` | `tests/test_stats_panel.py` |

### Phase 4: Documentation

| Task | File(s) |
|------|---------|
| Update README SDK version reference | `orchestrator-auto/README.md` (Dependencies table) |
| Update root `CLAUDE.md` SDK version if mentioned | `CLAUDE.md` |
| Mark `PROPOSAL_sdk_upgrade_0.1.23.md` as superseded | `docs/proposals/PROPOSAL_sdk_upgrade_0.1.23.md` |

**Not needed:**
- ~~Update `orchestrator-auto/CLAUDE.md`~~ — file does not exist under `orchestrator-auto/`
- ~~Rename this file~~ — already named `PROPOSAL_sdk_upgrade_0.1.50.md`

---

## Review Findings & Rejected Items

### Session Tagging & Renaming — Deferred

**Problem:** `tag_session()`, `rename_session()`, and `get_session_info()` are top-level SDK helper functions that require the real SDK session UUID as a parameter. orchestrator-auto does not capture this UUID.

**Evidence:**
- `engine.py:380` creates `f"{self.session_id}-planner"` — this is a local label passed to `BaseAgent.__init__()`, not the SDK session UUID
- `engine.py:416` creates `f"{self.session_id}-executor"` — same pattern
- `agents.py:176` stores `self.session_id` from the constructor — this is the local label
- `agents.py:364` streams messages but never extracts `session_id` from `ResultMessage` or any other message type
- `db.py:62–63` has `planner_session_id` and `executor_session_id` columns — these store the local labels, not SDK UUIDs

**Prerequisite:** Before session tagging can work, `BaseAgent` must capture the real SDK session UUID from `ResultMessage.session_id` (available since SDK 0.1.0) and store it. The orchestrator must then persist this UUID in the DB alongside the local label.

**Estimated work:** ~2 hours for UUID capture + DB migration + tests. Can be a separate proposal.

### Per-Turn AssistantMessage.usage — Overcounting Risk (Addressed)

**Problem:** The original proposal sketched calling `self.on_token_usage()` from `AssistantMessage.usage`. This would double-count because every consumer treats each `on_token_usage` callback as a completed API call:

| Consumer | File | Line | What it does per callback |
|----------|------|------|--------------------------|
| `StatsPanel.add_tokens()` | `tui/widgets/stats_panel.py` | 160 | `self._api_calls += 1` |
| `WatchTUI.on_tokens_used()` | `tui/watch_app.py` | 1383 | `self._session_api_calls += 1` |
| `BaseAgent.send_message_async()` | `agents.py` | 385 | Fires `on_token_usage` with `cost_usd` |

**Resolution:** Phase 3 introduces a separate `on_live_tokens` callback that does not touch the existing `on_token_usage` path. See implementation details above.

### AgentDefinition Enhancements — Deferred

**Problem:** `ExploreSubAgent` (`explore.py:204`) creates a standalone `ClaudeSDKClient(options)` directly. It does not use `AgentDefinition` or the `agents=` parameter on `ClaudeAgentOptions`. No production code in the repo uses `AgentDefinition` at all.

**Evidence:**
- `grep -r "AgentDefinition" orchestrator-auto/orchestrator_auto/` — zero matches
- `grep -r "agents=" orchestrator-auto/orchestrator_auto/` — zero matches
- `explore.py:204–216` constructs `ClaudeAgentOptions` and `ClaudeSDKClient` directly

**Prerequisite:** Rewriting `ExploreSubAgent` to use the sub-agent pattern (`agents=` parameter) is a separate, non-trivial change. It would alter the agent lifecycle, context isolation, and error handling. This should be its own proposal.

### Cleanup Items — Corrected

- ~~Update `orchestrator-auto/CLAUDE.md`~~ — does not exist; removed from plan
- ~~Rename this file to `PROPOSAL_sdk_upgrade_0.1.50.md`~~ — already done; removed from plan

---

## Features from Prior Proposals — Status

### PROPOSAL_sdk_upgrade_0.1.23 (v0.1.17–v0.1.23 features)

| Feature | Status | Notes |
|---------|--------|-------|
| File Rewind (`rewind_files`) | **Implemented** | `agents.py` — checkpoint/rewind integrated with `engine.py` milestone rejection |
| MCP Status (`get_mcp_status`) | **Implemented** | `agents.py` — `get_mcp_status_async()` method |
| Tool Audit Trail (`tool_use_result`) | **Implemented** | `agents.py` — `_tool_invocations` tracking + `db.save_tool_invocations_batch()` |

### Prior version of this proposal (v0.1.26–v0.1.46 features)

| Feature | Status | Notes |
|---------|--------|-------|
| `effort` field | **Implemented** | `agents.py` + `cli.py` — `--planner-effort`/`--executor-effort` flags |
| `ThinkingConfig` types | **Implemented** | `agents.py` — `_resolve_thinking_config()` with `adaptive`/`enabled`/`disabled` |
| `PostToolUseFailure` hook | **Implemented** | `agents.py` — `_on_tool_failure()` callback |
| `Notification` hook | **Implemented** | `agents.py` — `_on_notification()` callback |
| `ResultMessage.stop_reason` | **Implemented** | `agents.py` — `_last_stop_reason` tracking with `max_tokens` warning |
| Forward-compatible message parsing | **Implicit** | Enabled by `>=0.1.40` minimum version |
| `list_sessions()` / `get_session_messages()` | **Available, not used** | Could supplement `orchestrator list`/`status` |
| Runtime MCP management | **Available, not used** | `add_mcp_server()`/`remove_mcp_server()` |
| Typed task messages | **Available, not used** | `TaskStarted`/`TaskProgress`/`TaskNotification` |
| Hook `agent_id`/`agent_type` fields | **Available, not extracted** | Could enable per-agent tool tracking |

---

## Future Work (Out of Scope)

Items documented here for future proposals, not part of this upgrade:

| Item | Prerequisite | Estimated Effort |
|------|-------------|-----------------|
| Session tagging (`tag_session`/`rename_session`) | Capture SDK session UUID from `ResultMessage.session_id` in `BaseAgent`; persist in DB | ~2 hours |
| `get_session_info()` integration | Same as above (needs SDK session UUID) | ~1 hour (after prerequisite) |
| `AgentDefinition` for `ExploreSubAgent` | Rewrite `explore.py` from standalone `ClaudeSDKClient` to sub-agent pattern via `agents=` | ~4 hours (separate proposal) |
| `include_partial_messages` for TUI | Audit message volume; add throttling to TUI adapter | ~3 hours |
| `max_budget_usd` CLI flag | Straightforward wiring, no blockers | ~1 hour |
| `fallback_model` CLI flag | Straightforward wiring, no blockers | ~1 hour |
| ~~Haiku 3 → Haiku 4.5 migration~~ | ~~Update `MODEL_ALIASES` in `config.py`~~ | **Done** (v1.10.0) |

---

## Breaking Changes

**None from v0.1.46 to v0.1.50.** All changes are additive.

Deprecations already addressed:
- `max_thinking_tokens` → orchestrator-auto uses `thinking` field (adopted in prior upgrade)
- `debug_stderr` → orchestrator-auto doesn't use this

### Model Deprecation Warning

~~**Claude Haiku 3 (`claude-3-5-haiku-20241022`) retirement: April 19, 2026.**~~ **Resolved** — `haiku` alias migrated to `claude-haiku-4-5-20251001` in v1.10.0.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| New SDK version introduces subtle behavior change | Low | Medium | Pin to `>=0.1.50,<0.2.0` for safety |
| `RateLimitEvent` message type falls through existing `isinstance` chain | Low | Low | Add as explicit branch before `AssistantMessage` check |
| `on_live_tokens` callback adds overhead to hot path | Low | Low | Callback is optional (`None` by default); no work done if not set |
| Consumers accidentally subscribe to `on_live_tokens` thinking it replaces `on_token_usage` | Medium | Medium | Docstring explicitly states "delta-only, no cost, no API call count"; `is_delta: True` flag in payload |
| ~~Haiku 3 retirement breaks `haiku` model alias~~ | — | — | **Resolved** — migrated to `claude-haiku-4-5-20251001` in v1.10.0 |

---

## References

- [claude-agent-sdk on PyPI](https://pypi.org/project/claude-agent-sdk/)
- [claude-agent-sdk v0.1.50 on PyPI](https://pypi.org/project/claude-agent-sdk/0.1.50/)
- [GitHub: anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)
- [GitHub Releases](https://github.com/anthropics/claude-agent-sdk-python/releases)
- [CHANGELOG.md](https://github.com/anthropics/claude-agent-sdk-python/blob/main/CHANGELOG.md)
- [Agent SDK Overview — Anthropic Docs](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Agent SDK Python Reference — Anthropic Docs](https://platform.claude.com/docs/en/agent-sdk/python)
- Prior proposals: `PROPOSAL_sdk_upgrade_0.1.23.md`

### Key PRs Referenced (v0.1.47–v0.1.50)

| PR | Feature |
|----|---------|
| [#644](https://github.com/anthropics/claude-agent-sdk-python/pull/644) | Fine-grained tool streaming fix (`include_partial_messages`) |
| [#648](https://github.com/anthropics/claude-agent-sdk-python/pull/648) | Typed `RateLimitEvent` message |
| [#649](https://github.com/anthropics/claude-agent-sdk-python/pull/649) | Docs: `allowed_tools` clarification |
| [#661](https://github.com/anthropics/claude-agent-sdk-python/pull/661) | macOS x86_64 wheel |
| [#667](https://github.com/anthropics/claude-agent-sdk-python/pull/667) | `get_session_info()` + `SDKSessionInfo.tag`/`created_at` |
| [#668](https://github.com/anthropics/claude-agent-sdk-python/pull/668) | `rename_session()` |
| [#670](https://github.com/anthropics/claude-agent-sdk-python/pull/670) | `tag_session()` with Unicode sanitization |
| [#671](https://github.com/anthropics/claude-agent-sdk-python/pull/671) | Reverted streaming env-var workaround (fixed upstream) |
| [#684](https://github.com/anthropics/claude-agent-sdk-python/pull/684) | `AgentDefinition.skills`/`memory`/`mcpServers` |
| [#685](https://github.com/anthropics/claude-agent-sdk-python/pull/685) | Per-turn `AssistantMessage.usage` |
| [#686](https://github.com/anthropics/claude-agent-sdk-python/pull/686) | `CLAUDE_CODE_ENTRYPOINT` default-if-absent semantics |

### Key PRs Referenced (v0.1.25–v0.1.46, already adopted)

| PR | Feature |
|----|---------|
| [#535](https://github.com/anthropics/claude-agent-sdk-python/pull/535) | `PostToolUseFailure` hook event |
| [#545](https://github.com/anthropics/claude-agent-sdk-python/pull/545) | `Notification`, `SubagentStart`, `PermissionRequest` hooks |
| [#565](https://github.com/anthropics/claude-agent-sdk-python/pull/565) | `ThinkingConfig` types + `effort` field |
| [#598](https://github.com/anthropics/claude-agent-sdk-python/pull/598) | Forward-compatible message parsing |
| [#619](https://github.com/anthropics/claude-agent-sdk-python/pull/619) | `ResultMessage.stop_reason` |
| [#620](https://github.com/anthropics/claude-agent-sdk-python/pull/620) | Runtime MCP management |
| [#621](https://github.com/anthropics/claude-agent-sdk-python/pull/621) | Typed task messages |
| [#622](https://github.com/anthropics/claude-agent-sdk-python/pull/622) | Session history functions |
| [#628](https://github.com/anthropics/claude-agent-sdk-python/pull/628) | Hook input `agent_id`/`agent_type` fields |
| [#630](https://github.com/anthropics/claude-agent-sdk-python/pull/630) | MCP stdin initialization fix |
