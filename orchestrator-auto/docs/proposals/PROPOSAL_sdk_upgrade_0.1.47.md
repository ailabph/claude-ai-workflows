# Proposal: Upgrade to Claude Agent SDK 0.1.47

**Author:** Claude
**Created:** 2026-03-04
**Updated:** 2026-03-06
**Status:** Draft
**SDK Version:** 0.1.25 → 0.1.47
**Supersedes:** `PROPOSAL_sdk_upgrade_0.1.23.md`

---

## Summary

Upgrade orchestrator-auto from `claude-agent-sdk>=0.1.25` to `>=0.1.46` (minimum) and adopt new SDK features available through v0.1.47. The most impactful additions are `ThinkingConfig` types, the `effort` field, enhanced hook events, forward-compatible message parsing, session history functions, runtime MCP management, and typed task messages.

---

## Current State

| Item | Value |
|------|-------|
| `pyproject.toml` pin | `>=0.1.25` |
| Latest available | **0.1.47** (March 6, 2026) |
| Python requirement | 3.10+ |
| Package | `claude-agent-sdk` (renamed from `claude-code-sdk` in v0.1.0) |
| License | MIT (governed by Anthropic Commercial ToS) |
| Bundled CLI | v2.1.70 (in SDK 0.1.47) |

orchestrator-auto currently uses **none** of the new features from v0.1.26+. The `agents.py` `_get_options()` method constructs a basic `ClaudeAgentOptions` with `system_prompt`, `tools`, `model`, `cwd`, `permission_mode`, and optional `mcp_servers` — no `thinking`, `effort`, or hooks.

---

## Complete SDK Changelog (v0.1.25 → v0.1.47)

### Feature Releases

| Version | Date | Feature | PR |
|---------|------|---------|----|
| **v0.1.26** | Jan 30, 2026 | `PostToolUseFailure` hook event type with `PostToolUseFailureHookInput` and `PostToolUseFailureHookSpecificOutput` | [#535](https://github.com/anthropics/claude-agent-sdk-python/pull/535) |
| **v0.1.28** | Feb 3, 2026 | Bug fix: `AssistantMessage.error` field now correctly populated from top-level response (was reading from wrong path) | [#506](https://github.com/anthropics/claude-agent-sdk-python/pull/506) |
| **v0.1.29** | Feb 4, 2026 | 3 new hook events: `Notification`, `SubagentStart`, `PermissionRequest` | [#545](https://github.com/anthropics/claude-agent-sdk-python/pull/545) |
| **v0.1.29** | Feb 4, 2026 | Enhanced hook input/output types (see details below) | [#545](https://github.com/anthropics/claude-agent-sdk-python/pull/545) |
| **v0.1.31** | Feb 6, 2026 | MCP tool annotations via `@tool()` decorator's `annotations` parameter (`ToolAnnotations` re-exported) | [#551](https://github.com/anthropics/claude-agent-sdk-python/pull/551) |
| **v0.1.31** | Feb 6, 2026 | Fix: large agent definitions sent via stdin instead of CLI args (avoids `ARG_MAX` limits) | [#468](https://github.com/anthropics/claude-agent-sdk-python/pull/468) |
| **v0.1.36** | Feb 13, 2026 | `ThinkingConfig` types: `ThinkingConfigAdaptive`, `ThinkingConfigEnabled`, `ThinkingConfigDisabled` | [#565](https://github.com/anthropics/claude-agent-sdk-python/pull/565) |
| **v0.1.36** | Feb 13, 2026 | `effort` field on `ClaudeAgentOptions`: `"low"` / `"medium"` / `"high"` / `"max"` | [#565](https://github.com/anthropics/claude-agent-sdk-python/pull/565) |
| **v0.1.36** | Feb 13, 2026 | Deprecation: `max_thinking_tokens` replaced by `thinking` field | [#565](https://github.com/anthropics/claude-agent-sdk-python/pull/565) |
| **v0.1.40** | Feb 24, 2026 | Forward-compatible message parsing: unknown message types (e.g. `rate_limit_event`) silently skipped instead of raising `MessageParseError` | [#598](https://github.com/anthropics/claude-agent-sdk-python/pull/598) |
| **v0.1.46** | Mar 5, 2026 | `list_sessions()` and `get_session_messages()` top-level functions for session history retrieval | [#622](https://github.com/anthropics/claude-agent-sdk-python/pull/622) |
| **v0.1.46** | Mar 5, 2026 | `add_mcp_server()`, `remove_mcp_server()`, and typed `McpServerStatus` for runtime MCP management | [#620](https://github.com/anthropics/claude-agent-sdk-python/pull/620) |
| **v0.1.46** | Mar 5, 2026 | Typed task messages: `TaskStarted`, `TaskProgress`, `TaskNotification` subclasses | [#621](https://github.com/anthropics/claude-agent-sdk-python/pull/621) |
| **v0.1.46** | Mar 5, 2026 | `ResultMessage.stop_reason` field for inspecting why a conversation turn ended | [#619](https://github.com/anthropics/claude-agent-sdk-python/pull/619) |
| **v0.1.46** | Mar 5, 2026 | Hook input enhancements: `agent_id` and `agent_type` fields added to `PreToolUseHookInput`, `PostToolUseHookInput`, `PostToolUseFailureHookInput` | [#628](https://github.com/anthropics/claude-agent-sdk-python/pull/628) |
| **v0.1.46** | Mar 5, 2026 | Bug fix: string prompt MCP initialization race condition — stdin closed before MCP servers registered | [#630](https://github.com/anthropics/claude-agent-sdk-python/pull/630) |

### CLI-Only Releases

These versions updated only the bundled Claude CLI binary:

| Version | Date | Bundled CLI |
|---------|------|-------------|
| v0.1.25 | Jan 29 | 2.1.23 |
| v0.1.27 | Jan 31 | 2.1.29 |
| v0.1.30 | Feb 5 | 2.1.32 |
| v0.1.32 | Feb 7 | 2.1.36 |
| v0.1.33 | Feb 7 | 2.1.37 |
| v0.1.34 | Feb 10 | 2.1.38 |
| v0.1.35 | Feb 10 | 2.1.39 |
| v0.1.37 | Feb 16 | 2.1.44 |
| v0.1.38 | Feb 18 | 2.1.47 |
| v0.1.39 | Feb 19 | 2.1.49 |
| v0.1.41 | Feb 24 | 2.1.52 |
| v0.1.42 | Feb 25 | 2.1.55 |
| v0.1.43 | Feb 25 | 2.1.56 |
| v0.1.44 | Feb 26 | 2.1.59 |
| v0.1.45 | Mar 3 | 2.1.63 |
| v0.1.47 | Mar 6 | 2.1.70 |

---

## New Types & API Surface (v0.1.26+)

### New `ClaudeAgentOptions` Fields

```python
# v0.1.36 — Extended Thinking (replaces deprecated max_thinking_tokens)
thinking: ThinkingConfig | None = None

# v0.1.36 — Reasoning Effort
effort: Literal["low", "medium", "high", "max"] | None = None
```

### ThinkingConfig Types (v0.1.36)

```python
from claude_agent_sdk import (
    ThinkingConfigAdaptive,   # {"type": "adaptive"} — Claude decides when to think
    ThinkingConfigEnabled,    # {"type": "enabled", "budget_tokens": int} — fixed budget
    ThinkingConfigDisabled,   # {"type": "disabled"} — no thinking
)

# Union type
ThinkingConfig = ThinkingConfigAdaptive | ThinkingConfigEnabled | ThinkingConfigDisabled
```

### New Hook Event Types

| Event | Added | Input Type | Output Type |
|-------|-------|------------|-------------|
| `PostToolUseFailure` | v0.1.26 | `PostToolUseFailureHookInput` | `PostToolUseFailureHookSpecificOutput` |
| `Notification` | v0.1.29 | `NotificationHookInput` | `NotificationHookSpecificOutput` |
| `SubagentStart` | v0.1.29 | `SubagentStartHookInput` | `SubagentStartHookSpecificOutput` |
| `PermissionRequest` | v0.1.29 | `PermissionRequestHookInput` | `PermissionRequestHookSpecificOutput` |

**All 10 hook events (complete list as of v0.1.47):**
`PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `UserPromptSubmit`, `Stop`, `SubagentStop`, `PreCompact`, `Notification`, `SubagentStart`, `PermissionRequest`

### Enhanced Hook Input/Output Fields (v0.1.29, v0.1.46)

| Type | New Field | Added | Description |
|------|-----------|-------|-------------|
| `PreToolUseHookInput` | `tool_use_id` | v0.1.29 | Unique ID for this tool invocation |
| `PreToolUseHookInput` | `agent_id` | v0.1.46 | ID of the agent invoking the tool |
| `PreToolUseHookInput` | `agent_type` | v0.1.46 | Type/role of the agent |
| `PostToolUseHookInput` | `tool_use_id` | v0.1.29 | Unique ID for this tool invocation |
| `PostToolUseHookInput` | `agent_id` | v0.1.46 | ID of the agent invoking the tool |
| `PostToolUseHookInput` | `agent_type` | v0.1.46 | Type/role of the agent |
| `PostToolUseFailureHookInput` | `agent_id` | v0.1.46 | ID of the agent invoking the tool |
| `PostToolUseFailureHookInput` | `agent_type` | v0.1.46 | Type/role of the agent |
| `SubagentStopHookInput` | `agent_id` | v0.1.29 | ID of the subagent |
| `SubagentStopHookInput` | `agent_transcript_path` | v0.1.29 | Path to subagent transcript |
| `SubagentStopHookInput` | `agent_type` | v0.1.29 | Type/role of the subagent |
| `PreToolUseHookSpecificOutput` | `additionalContext` | v0.1.29 | Inject context before tool runs |
| `PostToolUseHookSpecificOutput` | `updatedMCPToolOutput` | v0.1.29 | Modify MCP tool output |

### Session History Functions (v0.1.46)

```python
from claude_agent_sdk import list_sessions, get_session_messages

# List past sessions (returns list of SessionInfo)
sessions = await list_sessions()

# Get messages from a specific session
messages = await get_session_messages(session_id="sess_abc123")
```

### Runtime MCP Management (v0.1.46)

```python
from claude_agent_sdk import add_mcp_server, remove_mcp_server, McpServerStatus

# Add an MCP server at runtime
await add_mcp_server("my-server", config)

# Remove an MCP server
await remove_mcp_server("my-server")

# McpServerStatus typed enum for status checks
```

### Typed Task Messages (v0.1.46)

```python
from claude_agent_sdk import TaskStarted, TaskProgress, TaskNotification

# These are now distinct message subclasses instead of generic dicts,
# enabling isinstance() checks and IDE autocompletion
```

### ResultMessage.stop_reason (v0.1.46)

```python
# Inspect why a conversation turn ended
result: ResultMessage = ...
if result.stop_reason == "max_tokens":
    # Handle token limit
elif result.stop_reason == "end_turn":
    # Normal completion
```

### MCP Tool Annotations (v0.1.31)

```python
from claude_agent_sdk import tool, ToolAnnotations

@tool("read_config", "Read configuration file", {"path": str},
      annotations=ToolAnnotations(
          readOnlyHint=True,
          destructiveHint=False,
          idempotentHint=True,
          openWorldHint=False,
      ))
async def read_config(args):
    ...
```

---

## Complete `ClaudeAgentOptions` Field Reference (v0.1.47)

For completeness, the full options surface:

```python
@dataclass
class ClaudeAgentOptions:
    # Core
    system_prompt: str | SystemPromptPreset | None = None
    tools: list[str] | ToolsPreset | None = None
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    model: str | None = None
    fallback_model: str | None = None
    cwd: str | Path | None = None

    # Permissions
    permission_mode: PermissionMode | None = None       # "default"|"acceptEdits"|"plan"|"bypassPermissions"
    can_use_tool: CanUseTool | None = None

    # Sessions
    resume: str | None = None
    fork_session: bool = False
    continue_conversation: bool = False

    # Limits
    max_turns: int | None = None
    max_budget_usd: float | None = None

    # Extended Thinking (v0.1.36)
    thinking: ThinkingConfig | None = None               # NEW — replaces max_thinking_tokens
    effort: Literal["low", "medium", "high", "max"] | None = None  # NEW
    max_thinking_tokens: int | None = None               # DEPRECATED

    # MCP
    mcp_servers: dict[str, McpServerConfig] | str | Path = field(default_factory=dict)

    # Hooks
    hooks: dict[HookEvent, list[HookMatcher]] | None = None

    # Subagents
    agents: dict[str, AgentDefinition] | None = None

    # Output
    output_format: dict[str, Any] | None = None          # structured output (JSON schema)
    include_partial_messages: bool = False                 # streaming token events

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
    debug_stderr: Any = sys.stderr                        # DEPRECATED
```

---

## Impact Analysis for orchestrator-auto

### Priority 1: High Value, Low Risk

#### 1A. `effort` field → per-agent reasoning control

**What it does:** Controls how deeply Claude reasons before responding. `"low"` is fast/shallow, `"max"` is slow/thorough.

**Why it matters for orchestrator-auto:**
- Planner (Opus) benefits from `effort="high"` or `"max"` — better milestone decomposition
- Executor (Sonnet/Haiku) can use `effort="medium"` — faster execution, lower cost
- Direct cost/speed optimization lever for users

**Implementation sketch:**

```python
# cli.py — new flags
@click.option('--planner-effort', type=click.Choice(['low', 'medium', 'high', 'max']),
              default=None, help='Reasoning effort for planner agent')
@click.option('--executor-effort', type=click.Choice(['low', 'medium', 'high', 'max']),
              default=None, help='Reasoning effort for executor agent')

# agents.py — pass to options
def _get_options(self) -> ClaudeAgentOptions:
    options_kwargs = {
        ...existing...,
    }
    if self.effort:
        options_kwargs["effort"] = self.effort
    self._options = ClaudeAgentOptions(**options_kwargs)
```

**Files affected:** `cli.py`, `agents.py`, `engine.py`, `config.py`
**Risk:** Low — additive, no existing behavior changes

#### 1B. `ThinkingConfig` → replace deprecated `max_thinking_tokens`

**What it does:** Fine-grained control over extended thinking. `ThinkingConfigAdaptive` lets Claude decide when thinking is useful. `ThinkingConfigEnabled(budget_tokens=N)` sets an explicit ceiling. `ThinkingConfigDisabled` turns it off.

**Why it matters:** `max_thinking_tokens` is deprecated. Switching to `ThinkingConfig` is future-proofing. `Adaptive` mode is likely the best default for both planner and executor — Claude allocates thinking budget based on task complexity.

**Implementation sketch:**

```python
# agents.py
from claude_agent_sdk import ThinkingConfigAdaptive, ThinkingConfigEnabled, ThinkingConfigDisabled

class BaseAgent:
    def __init__(self, ..., thinking: Optional[str] = None):
        self.thinking = thinking  # "adaptive" | "disabled" | int (budget tokens)

    def _get_options(self) -> ClaudeAgentOptions:
        options_kwargs = { ...existing... }
        if self.thinking == "adaptive":
            options_kwargs["thinking"] = ThinkingConfigAdaptive()
        elif self.thinking == "disabled":
            options_kwargs["thinking"] = ThinkingConfigDisabled()
        elif isinstance(self.thinking, int):
            options_kwargs["thinking"] = ThinkingConfigEnabled(budget_tokens=self.thinking)
        ...
```

**Files affected:** `agents.py`, `cli.py`, `config.py`
**Risk:** Low — replaces a deprecated field

#### 1C. Bump minimum version to `>=0.1.46`

**What it does:** Gets forward-compatible message parsing (v0.1.40), the `AssistantMessage.error` bug fix (v0.1.28), MCP stdin race condition fix (v0.1.46), and all new v0.1.46 features.

**Why it matters:** Without v0.1.40+, future SDK message types (e.g. `rate_limit_event`) crash the session with `MessageParseError`. The v0.1.46 MCP fix prevents server registration failures when using string prompts. This is a stability fix with zero code changes required.

**Files affected:** `pyproject.toml`
**Risk:** None

#### 1D. `ResultMessage.stop_reason` → smarter turn handling

**What it does:** The `stop_reason` field on `ResultMessage` exposes why a conversation turn ended (e.g. `"end_turn"`, `"max_tokens"`, `"stop_sequence"`).

**Why it matters for orchestrator-auto:**
- `engine.py` can detect `max_tokens` truncation and automatically retry or warn the user
- Distinguishes clean completion from forced stops — improves milestone reliability
- Enables better error reporting in TUI stats panel

**Implementation sketch:**

```python
# engine.py — inspect stop reason after agent turn
async for message in agent.stream():
    if isinstance(message, ResultMessage):
        if message.stop_reason == "max_tokens":
            logger.warning("Agent response truncated — consider increasing token limit")
            # Optionally retry or flag milestone
```

**Files affected:** `engine.py`, optionally `tui/widgets/stats_panel.py`
**Risk:** None — read-only field inspection

---

### Priority 2: Medium Value, Low-Medium Risk

#### 2A. `PostToolUseFailure` hook → tool failure tracking

**What it does:** Fires when a tool invocation fails. Provides typed input/output for handling failures.

**Why it matters for orchestrator-auto:**
- Feed into the tool audit trail (from `PROPOSAL_sdk_upgrade_0.1.23.md` Feature 3)
- Count tool failures per milestone — flag milestones with high failure rates
- Surface failures in TUI watch panel

**Implementation sketch:**

```python
# agents.py
from claude_agent_sdk import HookMatcher

async def _on_tool_failure(input_data, tool_use_id, context):
    tool_name = input_data.get("tool_name", "unknown")
    error = input_data.get("error", "")
    # Log to tool_invocations list or emit event
    return {}

class BaseAgent:
    def _get_options(self) -> ClaudeAgentOptions:
        hooks = {}
        hooks["PostToolUseFailure"] = [
            HookMatcher(matcher="*", hooks=[self._on_tool_failure])
        ]
        options_kwargs["hooks"] = hooks
```

**Files affected:** `agents.py`, optionally `db.py` for persistence
**Risk:** Low — hooks are additive, failure is non-fatal

#### 2B. `Notification` hook → Telegram bridge

**What it does:** Fires on SDK notification events (rate limits, warnings, system messages).

**Why it matters:** orchestrator-auto already has Telegram integration (`telegram.py`). Bridging SDK notifications to Telegram gives users real-time visibility into rate limits or warnings without watching the terminal.

**Implementation sketch:**

```python
async def _on_notification(input_data, tool_use_id, context):
    message = input_data.get("message", "")
    notification_type = input_data.get("type", "info")
    # Emit to TUI or queue for Telegram
    return {}
```

**Files affected:** `agents.py`, `telegram.py`, `engine.py`
**Risk:** Low

#### 2C. `SubagentStart` / `SubagentStop` hooks → TUI visibility

**What it does:** Fires when subagents start/stop. `SubagentStop` now includes `agent_id`, `agent_transcript_path`, and `agent_type`.

**Why it matters:** If orchestrator-auto uses subagents (exploration, validation — per other proposals), these hooks give the TUI watch panel real-time subagent lifecycle visibility. As of v0.1.46, tool-lifecycle hooks (`PreToolUse`, `PostToolUse`, `PostToolUseFailure`) also include `agent_id` and `agent_type`, enabling per-agent tool tracking across the board.

**Files affected:** `agents.py`, `tui/widgets/watch_panel.py`, `tui/widgets/compact_sidebar.py`
**Risk:** Low — only relevant if subagent features are implemented

#### 2D. `list_sessions()` / `get_session_messages()` → session history

**What it does:** Top-level SDK functions to list past sessions and retrieve messages from a specific session ([#622](https://github.com/anthropics/claude-agent-sdk-python/pull/622)).

**Why it matters for orchestrator-auto:**
- Could supplement or replace parts of the SQLite session tracking in `db.py`
- `orchestrator list` and `orchestrator status` could pull richer data directly from the SDK
- Session export (`orchestrator export`) could include full message history without custom persistence
- Useful for `recovery.py` context recovery — retrieve prior session context directly

**Implementation sketch:**

```python
# cli.py — enhanced status command
from claude_agent_sdk import list_sessions, get_session_messages

@cli.command()
@click.argument('session_id')
async def status(session_id):
    messages = await get_session_messages(session_id)
    # Display turn-by-turn history with role, content preview, timestamps
```

**Files affected:** `cli.py`, `db.py`, `recovery.py`
**Risk:** Low — read-only functions, additive

#### 2E. Runtime MCP management → dynamic tool provisioning

**What it does:** `add_mcp_server()` and `remove_mcp_server()` allow adding/removing MCP servers during a running session, with typed `McpServerStatus` for health checks ([#620](https://github.com/anthropics/claude-agent-sdk-python/pull/620)).

**Why it matters for orchestrator-auto:**
- Executor agents could gain or lose MCP tools between milestones based on milestone requirements
- `orchestrator check` could use `McpServerStatus` for MCP health reporting
- Enables "tool provisioning" patterns — only give the executor the tools it needs for each milestone

**Implementation sketch:**

```python
# engine.py — per-milestone MCP provisioning
from claude_agent_sdk import add_mcp_server, remove_mcp_server

async def _provision_mcp_for_milestone(self, milestone):
    required_servers = milestone.get("mcp_servers", [])
    for server_name, config in required_servers:
        await add_mcp_server(server_name, config)
```

**Files affected:** `engine.py`, `agents.py`
**Risk:** Medium — runtime server changes could affect in-flight operations

#### 2F. Typed task messages → TUI progress tracking

**What it does:** `TaskStarted`, `TaskProgress`, `TaskNotification` are now distinct message subclasses instead of generic dicts ([#621](https://github.com/anthropics/claude-agent-sdk-python/pull/621)).

**Why it matters for orchestrator-auto:**
- TUI widgets can use `isinstance()` checks for cleaner message routing
- `TaskProgress` messages could drive the watch panel's per-file progress indicators
- Better type safety means fewer runtime errors from malformed message dicts

**Files affected:** `engine.py`, `tui/widgets/watch_panel.py`, `tui/widgets/stats_panel.py`
**Risk:** Low — better typing for existing message handling

---

### Priority 3: Lower Value or Conditional

#### 3A. MCP tool annotations (v0.1.31)

**When useful:** Only if orchestrator-auto defines custom MCP tools. Annotating tools as `readOnlyHint=True` helps permission decisions.

**Current relevance:** Low — orchestrator-auto doesn't currently define custom MCP tools via `@tool()`.

#### 3B. `additionalContext` in PreToolUse hooks (v0.1.29)

**What it does:** Allows injecting additional context before a tool executes.

**When useful:** Could inject milestone context before Bash/Write operations — e.g., "you are working on milestone 3: user validation".

**Current relevance:** Medium — interesting but not critical.

#### 3C. `updatedMCPToolOutput` in PostToolUse hooks (v0.1.29)

**What it does:** Allows modifying MCP tool output after execution.

**When useful:** Could sanitize sensitive data from tool outputs before they're stored or displayed.

**Current relevance:** Low — orchestrator-auto uses `secrets.py` for this today.

---

## Recommended Implementation Plan

### Phase 1: Stability & Deprecation (No Risk)

| Task | Change | File(s) |
|------|--------|---------|
| Bump minimum SDK version | `>=0.1.25` → `>=0.1.46` | `pyproject.toml` |
| Pin upper bound for safety | `>=0.1.46,<0.2.0` | `pyproject.toml` |
| Verify no regressions | Run `pytest tests/ -v` | — |
| Update `environment.yml` if present | Match version pin | `environment.yml` |

### Phase 2: Effort, Thinking & Stop Reason (Low Risk)

| Task | Change | File(s) |
|------|--------|---------|
| Add `effort` parameter to `BaseAgent` | Accept and pass to `ClaudeAgentOptions` | `agents.py` |
| Add `thinking` parameter to `BaseAgent` | Accept `ThinkingConfig` and pass through | `agents.py` |
| Expose `--planner-effort` / `--executor-effort` CLI flags | Map to agent `effort` field | `cli.py` |
| Expose `--thinking` CLI flag | Map `adaptive`/`disabled`/`<int>` to config types | `cli.py` |
| Support in config file | `planner_effort`, `executor_effort`, `thinking` keys | `config.py` |
| Inspect `ResultMessage.stop_reason` | Detect truncation, improve error handling | `engine.py` |
| Write unit tests | Mock `ClaudeAgentOptions` construction | `tests/test_agents.py` |

### Phase 3: Hook Integration (Low-Medium Risk)

| Task | Change | File(s) |
|------|--------|---------|
| Add `PostToolUseFailure` hook to BaseAgent | Track tool failures | `agents.py` |
| Add `Notification` hook to BaseAgent | Emit to TUI/Telegram | `agents.py`, `telegram.py` |
| Add tool failure count to milestone stats | Display in progress report | `engine.py` |
| Wire notification events to TUI | Show in status panel | `tui/widgets/stats_panel.py` |
| Use typed task messages (`TaskStarted`, `TaskProgress`) | Replace generic dict checks with `isinstance()` | `engine.py`, `tui/widgets/watch_panel.py` |
| Write tests | Mock hook callbacks | `tests/test_agents.py` |

### Phase 4: Session & MCP Enhancements (Medium Risk)

| Task | Change | File(s) |
|------|--------|---------|
| Integrate `list_sessions()` into `orchestrator list` | Supplement SQLite data with SDK session data | `cli.py`, `db.py` |
| Integrate `get_session_messages()` into `orchestrator status` | Show full message history | `cli.py` |
| Evaluate `add_mcp_server()` / `remove_mcp_server()` for per-milestone provisioning | Prototype dynamic MCP management | `engine.py`, `agents.py` |
| Wire `McpServerStatus` into `orchestrator check` | MCP health reporting | `cli.py` |

### Phase 5: Documentation & Cleanup

| Task | Change | File(s) |
|------|--------|---------|
| Archive `PROPOSAL_sdk_upgrade_0.1.23.md` | Mark as superseded | This file |
| Update README SDK version references | Reflect v0.1.46+ | `README.md` |
| Update `CLAUDE.md` if SDK version mentioned | Keep consistent | `CLAUDE.md` |
| Document new CLI flags in CLI reference | `--planner-effort`, `--executor-effort`, `--thinking` | `docs/CLI_REFERENCE.md` |
| Rename this file to `PROPOSAL_sdk_upgrade_0.1.47.md` | Reflect updated target | filesystem |

---

## Features from PROPOSAL_sdk_upgrade_0.1.23 — Status

The prior proposal targeted features from SDK 0.1.17–0.1.23. These are still valid and compatible:

| Feature | SDK Requirement | Still Valid? | Notes |
|---------|----------------|--------------|-------|
| File Rewind (`rewind_files`) | v0.1.17 | Yes | `agents.py` already has `_checkpoint_uuid` fields but no integration in `engine.py` |
| MCP Status (`get_mcp_status`) | v0.1.23 | Yes | Not yet wired into `orchestrator check` or TUI |
| Tool Audit Trail (`tool_use_result`) | v0.1.22 | Yes | `_tool_invocations` field exists in `agents.py` but unused; `PostToolUseFailure` hook (v0.1.26) now provides a better mechanism |

---

## Breaking Changes

**None from v0.1.25 to v0.1.47.** All changes are additive.

One deprecation to address:
- `max_thinking_tokens` → use `thinking` field instead (v0.1.36)

orchestrator-auto does not currently use `max_thinking_tokens`, so no migration needed — just adopt `thinking` directly.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| New SDK version introduces subtle behavior change | Low | Medium | Pin to `>=0.1.46,<0.2.0` for safety |
| Hook callbacks add overhead to hot path | Low | Low | Hooks are async and non-blocking |
| `effort` settings confuse users | Medium | Low | Document clearly; don't expose unless `--planner-effort` explicitly set |
| `ThinkingConfig` types change in future SDK | Low | Low | Use union type, wrap in helper function |
| Runtime MCP changes affect in-flight operations | Low | Medium | Only add/remove servers between milestones, not during execution |
| SDK session functions conflict with SQLite tracking | Low | Low | Use SDK functions to supplement, not replace, existing `db.py` persistence |

---

## References

- [claude-agent-sdk on PyPI](https://pypi.org/project/claude-agent-sdk/)
- [claude-agent-sdk v0.1.47 on PyPI](https://pypi.org/project/claude-agent-sdk/0.1.47/)
- [GitHub: anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)
- [GitHub Releases](https://github.com/anthropics/claude-agent-sdk-python/releases)
- [v0.1.46 Release](https://github.com/anthropics/claude-agent-sdk-python/releases/tag/v0.1.46) — session history, MCP management, typed task messages, stop_reason, hook enhancements
- [v0.1.47 Release](https://github.com/anthropics/claude-agent-sdk-python/releases/tag/v0.1.47) — CLI bump to 2.1.70
- [Agent SDK Overview — Anthropic Docs](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Agent SDK Python Reference — Anthropic Docs](https://platform.claude.com/docs/en/agent-sdk/python)
- Prior proposal: `PROPOSAL_sdk_upgrade_0.1.23.md`

### Key PRs Referenced

| PR | Feature |
|----|---------|
| [#506](https://github.com/anthropics/claude-agent-sdk-python/pull/506) | `AssistantMessage.error` bug fix |
| [#468](https://github.com/anthropics/claude-agent-sdk-python/pull/468) | Large agent definitions via stdin |
| [#535](https://github.com/anthropics/claude-agent-sdk-python/pull/535) | `PostToolUseFailure` hook event |
| [#545](https://github.com/anthropics/claude-agent-sdk-python/pull/545) | `Notification`, `SubagentStart`, `PermissionRequest` hooks + enhanced hook I/O |
| [#551](https://github.com/anthropics/claude-agent-sdk-python/pull/551) | MCP tool annotations |
| [#565](https://github.com/anthropics/claude-agent-sdk-python/pull/565) | `ThinkingConfig` types + `effort` field |
| [#598](https://github.com/anthropics/claude-agent-sdk-python/pull/598) | Forward-compatible message parsing |
| [#619](https://github.com/anthropics/claude-agent-sdk-python/pull/619) | `ResultMessage.stop_reason` |
| [#620](https://github.com/anthropics/claude-agent-sdk-python/pull/620) | Runtime MCP management |
| [#621](https://github.com/anthropics/claude-agent-sdk-python/pull/621) | Typed task messages |
| [#622](https://github.com/anthropics/claude-agent-sdk-python/pull/622) | Session history functions |
| [#628](https://github.com/anthropics/claude-agent-sdk-python/pull/628) | Hook input `agent_id`/`agent_type` fields |
| [#630](https://github.com/anthropics/claude-agent-sdk-python/pull/630) | MCP stdin initialization fix |
