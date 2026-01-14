# MCP Tool Passing to Executor Agents: Investigation Report

**Date:** 2026-01-14
**Context:** Executor agents in orchestrator-auto cannot access MCP tools (e.g., Playwright browser automation)
**Related Issue:** `use-case/use-case-01-playright.md` - Executor blocked with "MCP Playwright tools are not available"

---

## Executive Summary

The orchestrator-auto's executor agents **cannot currently use MCP tools** because the agent creation code does not pass MCP server configurations to the Claude Agent SDK. This is a **configuration gap**, not an SDK limitation—the SDK fully supports MCP tool passing.

**Root Cause:** `ClaudeAgentOptions` in `agents.py` is created without the `mcp_servers` parameter.

**Impact:** Any workflow requiring browser automation, Figma integration, or other MCP-provided tools will fail at the executor stage.

---

## 1. How MCP Tools Work in Claude Code

### 1.1 MCP Server Configuration

MCP (Model Context Protocol) servers provide external tools to Claude. Configuration is typically stored in `.mcp.json`:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-playwright"]
    },
    "figma": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-figma"],
      "env": {
        "FIGMA_ACCESS_TOKEN": "${FIGMA_ACCESS_TOKEN}"
      }
    }
  }
}
```

### 1.2 Server Types Supported

The Claude Agent SDK supports four MCP server types:

| Type | Description | Config Fields |
|------|-------------|---------------|
| **stdio** | Local command execution | `command`, `args`, `env` |
| **sse** | Server-Sent Events over HTTP | `url`, `headers` |
| **http** | Standard HTTP server | `url`, `headers` |
| **sdk** | Programmatic SDK-managed | `name`, `instance` |

### 1.3 Tool Naming Convention

When MCP tools are loaded, they're prefixed with the server name:

```
mcp__<server_name>__<tool_name>
```

Examples:
- `mcp__playwright__browser_navigate`
- `mcp__playwright__browser_click`
- `mcp__playwright__browser_close`
- `mcp__figma__get_screenshot`

### 1.4 Tool Flow: Configuration → Agent Availability

```
┌─────────────────┐     ┌──────────────────────┐     ┌────────────────────┐
│   .mcp.json     │────▶│  ClaudeAgentOptions  │────▶│  ClaudeSDKClient   │
│   (or dict)     │     │  mcp_servers={...}   │     │  connects to MCP   │
└─────────────────┘     └──────────────────────┘     └────────────────────┘
                                                              │
                                                              ▼
                                                     ┌────────────────────┐
                                                     │  Tools available:  │
                                                     │  mcp__*__*         │
                                                     └────────────────────┘
```

---

## 2. Claude Agent SDK MCP Support

### 2.1 ClaudeAgentOptions Parameters

The SDK's `ClaudeAgentOptions` class accepts MCP configuration:

```python
from claude_agent_sdk.types import ClaudeAgentOptions

options = ClaudeAgentOptions(
    system_prompt="...",
    model="claude-sonnet-4-5-20250929",
    tools=["Read", "Write", "mcp__playwright__browser_navigate"],
    mcp_servers={                          # ← MCP server config
        "playwright": {
            "command": "npx",
            "args": ["@anthropic/mcp-server-playwright"]
        }
    },
    permission_mode="bypassPermissions",
)
```

### 2.2 Three Ways to Provide MCP Config

```python
# Way 1: Direct dictionary
options = ClaudeAgentOptions(
    mcp_servers={"playwright": {"command": "npx", "args": [...]}}
)

# Way 2: File path (SDK loads and parses)
options = ClaudeAgentOptions(
    mcp_servers=".mcp.json"
)

# Way 3: Auto-discovery from project settings
options = ClaudeAgentOptions(
    settings="project"  # Loads .mcp.json + .claude/settings.json
)
```

### 2.3 Tool Name Patterns

The `tools` parameter supports wildcards for MCP tools:

```python
tools=[
    "Read",                           # Standard tool
    "mcp__playwright__*",             # All Playwright tools
    "mcp__figma__get_screenshot",     # Specific Figma tool
]
```

---

## 3. Current orchestrator-auto Implementation

### 3.1 Agent Creation Code

**File:** `orchestrator-auto/orchestrator_auto/agents.py`

```python
# Lines 23-30: Hardcoded tool list
DEFAULT_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
]

# Lines 84-94: ClaudeAgentOptions creation - NO mcp_servers parameter
def _get_options(self) -> ClaudeAgentOptions:
    if self._options is None:
        self._options = ClaudeAgentOptions(
            system_prompt=self.system_prompt,
            tools=self.allowed_tools,
            model=self.model,
            cwd=self.cwd,
            permission_mode="bypassPermissions",
            # ❌ MISSING: mcp_servers parameter
        )
    return self._options
```

### 3.2 BaseAgent Constructor

```python
# Lines 36-44: No mcp_servers parameter
def __init__(
    self,
    system_prompt: str,
    allowed_tools: Optional[List[str]] = None,
    model: str = "claude-sonnet-4-5-20250929",
    session_id: str = "default",
    hooks: Optional[Dict[str, Any]] = None,
    cwd: Optional[Path] = None,
    # ❌ MISSING: mcp_servers parameter
):
```

### 3.3 Factory Functions

```python
# Lines 305-331, 334-360: Factory functions don't accept mcp_servers
def create_planner_agent(...) -> PlannerAgent:
    # No mcp_servers handling

def create_executor_agent(...) -> ExecutorAgent:
    # No mcp_servers handling
```

### 3.4 Engine Orchestration

**File:** `orchestrator-auto/orchestrator_auto/engine.py`

```python
# Lines 231-246: Agent creation doesn't pass MCP config
def _create_planner(self) -> PlannerAgent:
    planner_session_id = f"{self.session_id}-planner"
    kwargs = {"session_id": planner_session_id}
    if self.planner_model:
        kwargs["model"] = self.planner_model
    self.planner = create_planner_agent(**kwargs)
    # ❌ No mcp_servers passed
```

---

## 4. Why MCP Tools Are Not Available

### 4.1 The Gap

| Component | Current State | Required State |
|-----------|--------------|----------------|
| `BaseAgent.__init__()` | No `mcp_servers` param | Accept `mcp_servers` param |
| `_get_options()` | No `mcp_servers` in options | Pass `mcp_servers` to SDK |
| Factory functions | Don't accept `mcp_servers` | Accept and pass through |
| `Orchestrator` | Doesn't load MCP config | Load from `.mcp.json` or CLI |
| `engine.py` | Doesn't pass to agents | Pass config to agent creation |

### 4.2 Illustrated Gap

```
User's Claude Code Session          Orchestrator Executor Agent
┌─────────────────────────┐         ┌─────────────────────────┐
│ Has MCP tools:          │         │ Has tools:              │
│ • mcp__playwright__*    │         │ • Read                  │
│ • mcp__figma__*         │         │ • Write                 │
│ • Read, Write, etc.     │         │ • Edit                  │
│                         │         │ • Bash                  │
│ (from .mcp.json config) │         │ • Glob, Grep            │
└─────────────────────────┘         └─────────────────────────┘
         │                                    │
         │                                    │
         ▼                                    ▼
   MCP tools available ✅             MCP tools missing ❌
```

### 4.3 Session vs Agent Scope

**Critical Finding:** MCP tools are **per-agent, not per-session**.

- Each agent instance creates its own `ClaudeSDKClient`
- Each client independently connects to MCP servers
- Parent session's MCP configuration is NOT automatically inherited
- Each agent must be explicitly configured with `mcp_servers`

---

## 5. Evidence from Use Case

### 5.1 User Session (Works)

From `use-case-01-playright.md`, lines 135-180:

```
⏺ playwright - Navigate to a URL (MCP)(url: "http://localhost:3000/login")
⎿  ### Ran Playwright code
   await page.goto('http://localhost:3000/login');

⏺ playwright - Click (MCP)(element: "User menu button", ref: "e72")
⎿  ### Ran Playwright code
   await page.getByRole('button', { name: 'E Elmer Staff...' }).click();
```

The user's direct Claude Code session has MCP Playwright tools available.

### 5.2 Executor Agent (Fails)

From `use-case-01-playright.md`, lines 344-370:

```
⏸ Workflow paused - executor needs input:

MCP Playwright tools are not available in my current environment

I don't have access to MCP Playwright tools (browser_navigate, browser_click,
browser_fill, browser_close, etc.) in my available toolset.

The plan document specifies using MCP Playwright for browser-based E2E testing...

However, my available tools are:
- Bash (terminal commands)
- Glob (file pattern matching)
- Grep (content search)
- Read (file reading)
- Edit (file editing)
- Write (file writing)
```

The executor agent only has `DEFAULT_TOOLS` because no MCP config was passed.

---

## 6. Permission System Context

### 6.1 Current Permission Mode

The orchestrator uses `permission_mode="bypassPermissions"`:

```python
# agents.py line 92
permission_mode="bypassPermissions",  # Auto-approve all operations
```

This means:
- Standard Claude Code permissions (`.claude/settings.json`) are ignored
- All tool calls are auto-approved
- MCP tools would also be auto-approved **if they were configured**

### 6.2 MCP Tool Permissions

When using Claude Code directly, MCP tool permissions can be set:

```json
// .claude/settings.json
{
  "permissions": {
    "allow": [
      "mcp__playwright__*",
      "mcp__figma__*"
    ]
  }
}
```

With `bypassPermissions`, these settings are ignored—but the tools must still be configured via `mcp_servers` to be available.

---

## 7. Related Codebase Patterns

### 7.1 Existing MCP Documentation

The repository has documentation for MCP-based workflows:

| File | Description |
|------|-------------|
| `CLAUDE_visual_qa_workflow.md` | Browser MCP for visual QA |
| `CLAUDE_visual_qa_workflow_ref.md` | MCP installation guide |
| `CLAUDE_orchestrator_figma_visual_qa.md` | Figma + Browser MCP integration |

These documents assume MCP tools are available, but don't address the orchestrator gap.

### 7.2 Workflow Pattern from Documentation

From `CLAUDE_orchestrator_figma_visual_qa.md`:

```
Orchestrator Role: Uses Figma MCP to fetch specs
Executor Role: Can open browsers, interact, take screenshots
```

This pattern assumes both roles have appropriate MCP access—currently only true for direct Claude Code sessions.

---

## 8. Technical Constraints

### 8.1 SDK Requirements

- `mcp_servers` must be passed at `ClaudeAgentOptions` creation time
- Cannot be added after client initialization
- Server connections are established during `__aenter__()`

### 8.2 Process Model

- MCP servers run as separate processes (stdio type)
- Each agent's SDK client manages its own MCP connections
- Connections are cleaned up on `__aexit__()`

### 8.3 Backward Compatibility

Adding MCP support should be backward compatible:
- `mcp_servers` parameter defaults to `None` or `{}`
- Existing workflows without MCP continue to work
- No changes to CLI interface required (can use config files)

---

## 9. Summary

### What's Working
- Claude Agent SDK fully supports MCP configuration
- MCP tools work in direct Claude Code sessions
- Orchestrator architecture is extensible

### What's Missing
- `mcp_servers` parameter in `BaseAgent`
- MCP config loading in orchestrator
- Passing MCP config from engine to agents

### Required Changes
1. Add `mcp_servers` parameter to `BaseAgent.__init__()`
2. Pass `mcp_servers` to `ClaudeAgentOptions` in `_get_options()`
3. Update factory functions to accept `mcp_servers`
4. Load MCP config in `Orchestrator` (from `.mcp.json` or CLI)
5. Pass loaded config to agent creation in `engine.py`

---

## 10. Next Steps

See companion document: **DOC_mcp_tool_passing_solution.md** for comprehensive implementation proposal.
