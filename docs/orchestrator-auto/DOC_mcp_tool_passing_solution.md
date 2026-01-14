# MCP Tool Passing to Executor Agents: Solution Proposal

**Date:** 2026-01-14 (Updated - Rev 3)
**Author:** Claude Code Investigation
**Related:** `DOC_mcp_tool_passing_investigation.md`

---

## Executive Summary

This document proposes a comprehensive solution to enable MCP (Model Context Protocol) tools in orchestrator-auto's executor and planner agents. The solution involves:

1. **Code changes** to `agents.py`, `engine.py`, `db.py`, `config.py`, and `cli.py`
2. **Configuration options** via `.mcp.json` file or CLI flags
3. **Per-agent tool scoping** (different tools for planner vs executor)
4. **Session persistence** for MCP config (supports resume/respond workflows)
5. **Queue/watch mode support** for batch MCP workflows
6. **Documentation updates** for MCP-enabled workflows

**Estimated complexity:** Medium (6 files, ~250 lines of code)
**Backward compatible:** Yes (all changes are additive with sensible defaults)

---

## Table of Contents

1. [Solution Overview](#1-solution-overview)
2. [Architecture Design](#2-architecture-design)
3. [Implementation Plan](#3-implementation-plan)
4. [Code Changes](#4-code-changes)
5. [Configuration Options](#5-configuration-options)
6. [CLI Interface Changes](#6-cli-interface-changes)
7. [Testing Strategy](#7-testing-strategy)
8. [Migration Guide](#8-migration-guide)
9. [Alternative Approaches](#9-alternative-approaches)
10. [Open Questions](#10-open-questions)

---

## 1. Solution Overview

### 1.1 Goals

| Goal | Description |
|------|-------------|
| **Enable MCP tools** | Executor/Planner agents can use Playwright, Figma, etc. |
| **Per-agent scoping** | Different MCP servers for different agents |
| **Config-driven** | Use `.mcp.json` files (consistent with Claude Code) |
| **CLI override** | Pass MCP config via command line |
| **Resume continuity** | MCP config persists across resume/respond |
| **Queue/watch support** | MCP works in batch workflows |
| **Backward compatible** | Existing workflows work unchanged |

### 1.2 Non-Goals

- Automatic MCP server discovery/installation
- Runtime MCP server addition (must be configured at agent start)
- MCP server health monitoring
- MCP tool permission UI (using `bypassPermissions`)

### 1.3 Success Criteria

- Executor agent can use `mcp__playwright__browser_navigate` and related tools
- Planner agent can use `mcp__figma__get_screenshot` if configured
- E2E test workflow from `use-case-01-playright.md` completes successfully
- `orchestrator resume` restores MCP config from session
- Queue mode propagates MCP config to all sessions
- All existing tests pass
- No breaking changes to CLI or API

---

## 2. Architecture Design

### 2.1 Configuration Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Configuration Sources                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   CLI Flags              Project Config          Global Config          │
│   --mcp-config           .mcp.json               ~/.mcp.json            │
│        │                      │                       │                 │
│        └──────────────────────┼───────────────────────┘                 │
│                               ▼                                         │
│                    ┌──────────────────────┐                             │
│                    │   Config Loader      │                             │
│                    │   (config.py)        │                             │
│                    │   + env var expand   │                             │
│                    └──────────────────────┘                             │
│                               │                                         │
│                               ▼                                         │
│                    ┌──────────────────────┐                             │
│                    │   DB Persistence     │  ◄── Resume loads from DB   │
│                    │   (sessions table)   │                             │
│                    └──────────────────────┘                             │
│                               │                                         │
│                    ┌──────────┴──────────┐                              │
│                    ▼                     ▼                              │
│           ┌─────────────────┐   ┌─────────────────┐                     │
│           │  Planner MCP    │   │  Executor MCP   │                     │
│           │  (optional)     │   │  (optional)     │                     │
│           └─────────────────┘   └─────────────────┘                     │
│                    │                     │                              │
│                    ▼                     ▼                              │
│           ┌─────────────────┐   ┌─────────────────┐                     │
│           │  PlannerAgent   │   │  ExecutorAgent  │                     │
│           │  mcp_servers={} │   │  mcp_servers={} │                     │
│           └─────────────────┘   └─────────────────┘                     │
│                    │                     │                              │
│                    ▼                     ▼                              │
│           ┌─────────────────┐   ┌─────────────────┐                     │
│           │ ClaudeSDKClient │   │ ClaudeSDKClient │                     │
│           │ connects to MCP │   │ connects to MCP │                     │
│           └─────────────────┘   └─────────────────┘                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Per-Agent MCP Scoping

Support different MCP configurations for planner vs executor:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-playwright"]
    },
    "figma": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-figma"]
    }
  },
  "orchestrator": {
    "planner": {
      "mcpServers": ["figma"],
      "tools": ["mcp__figma__*"]
    },
    "executor": {
      "mcpServers": ["playwright"],
      "tools": ["mcp__playwright__*"]
    }
  }
}
```

### 2.3 Tool Inheritance Model

```
Global MCP Servers (mcpServers)
        │
        ├──▶ Planner: planner.mcpServers filter (or all if not specified)
        │
        └──▶ Executor: executor.mcpServers filter (or all if not specified)
```

### 2.4 Session Persistence Model

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  start command  │────▶│  Load MCP from  │────▶│  Persist to DB  │
│  --mcp-config   │     │  file + expand  │     │  mcp_config_json│
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ resume command  │────▶│  Load MCP from  │────▶│  Create agents  │
│ (no --mcp flag) │     │  DB session     │     │  with MCP       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## 3. Implementation Plan

### 3.1 Milestones

| # | Milestone | Files | Effort | Notes |
|---|-----------|-------|--------|-------|
| 1 | Add `mcp_servers` to BaseAgent | `agents.py` | Small | Core plumbing |
| 2 | Add tool list helper | `agents.py` | Small | `build_allowed_tools()` |
| 3 | Add MCP config loading with env expansion | `config.py` | Medium | Handle `${VAR}` |
| 4 | Add `mcp_config_json` to sessions table | `db.py` | Small | Persist for resume |
| 5 | Pass MCP config in engine + load from DB | `engine.py` | Medium | Resume support |
| 6 | Add CLI flags to start/resume/respond | `cli.py` | Medium | No `-m` conflict |
| 7 | Thread MCP through queue/watch modes | `cli.py` | Medium | Batch support |
| 8 | Update documentation | `AGENTS.md`, `README.md` | Small | |
| 9 | Add tests | `tests/` | Medium | |

### 3.2 Dependencies

```
Milestone 1, 2 ───▶ Milestone 5 ───▶ Milestone 6, 7
                         │
Milestone 3 ─────────────┤
                         │
Milestone 4 ─────────────┘
                         │
                         ▼
                  Milestone 8, 9
```

---

## 4. Code Changes

### 4.1 agents.py Changes

#### 4.1.1 Add MCP Type Imports and Helper

```python
# At top of file, add:
from typing import Optional, Dict, Any, List, Callable, Union

# Define MCP config type (matches SDK)
McpServerConfig = Dict[str, Any]  # {"command": str, "args": list, "env": dict}
McpServersConfig = Dict[str, McpServerConfig]  # {"playwright": {...}, "figma": {...}}


def build_allowed_tools(
    base_tools: Optional[List[str]] = None,
    mcp_tools: Optional[List[str]] = None,
) -> List[str]:
    """
    Build the allowed tools list by combining base tools with MCP tools.

    This helper ensures clean import boundaries - engine.py doesn't need
    to import DEFAULT_TOOLS directly.

    Args:
        base_tools: Base tool list (default: DEFAULT_TOOLS)
        mcp_tools: Additional MCP tool patterns to add

    Returns:
        Combined list of allowed tools
    """
    tools = list(base_tools or DEFAULT_TOOLS)
    if mcp_tools:
        tools.extend(mcp_tools)
    return tools
```

#### 4.1.2 Update BaseAgent.__init__()

```python
class BaseAgent:
    """Base class for orchestrator agents."""

    def __init__(
        self,
        system_prompt: str,
        allowed_tools: Optional[List[str]] = None,
        model: str = "claude-sonnet-4-5-20250929",
        session_id: str = "default",
        hooks: Optional[Dict[str, Any]] = None,
        cwd: Optional[Path] = None,
        mcp_servers: Optional[Union[McpServersConfig, str]] = None,  # NEW
    ):
        """
        Initialize the agent.

        Args:
            system_prompt: System prompt defining agent role and behavior
            allowed_tools: List of allowed tools (default: Read, Write, Edit, Bash, Glob, Grep)
            model: Claude model to use
            session_id: Session ID for the agent
            hooks: Optional hooks configuration
            cwd: Working directory for agent (default: current directory)
            mcp_servers: MCP server configuration dict or path to .mcp.json file  # NEW
        """
        self.system_prompt = system_prompt
        self.allowed_tools = allowed_tools or DEFAULT_TOOLS
        self.model = model
        self.session_id = session_id
        self.hooks = hooks
        self.cwd = cwd or Path.cwd()
        self.mcp_servers = mcp_servers  # NEW
        self._options: Optional[ClaudeAgentOptions] = None
        # ... rest unchanged
```

#### 4.1.3 Update _get_options()

```python
def _get_options(self) -> ClaudeAgentOptions:
    """Get or create agent options."""
    if self._options is None:
        options_kwargs = {
            "system_prompt": self.system_prompt,
            "tools": self.allowed_tools,
            "model": self.model,
            "cwd": self.cwd,
            "permission_mode": "bypassPermissions",
        }

        # Add MCP servers if configured
        if self.mcp_servers:
            options_kwargs["mcp_servers"] = self.mcp_servers

        self._options = ClaudeAgentOptions(**options_kwargs)
    return self._options
```

#### 4.1.4 Update PlannerAgent and ExecutorAgent

```python
class PlannerAgent(BaseAgent):
    def __init__(
        self,
        model: str = "claude-opus-4-5-20251101",
        session_id: str = "planner",
        mcp_servers: Optional[Union[McpServersConfig, str]] = None,  # NEW
        **kwargs
    ):
        super().__init__(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            model=model,
            session_id=session_id,
            mcp_servers=mcp_servers,  # NEW
            **kwargs
        )


class ExecutorAgent(BaseAgent):
    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        session_id: str = "executor",
        mcp_servers: Optional[Union[McpServersConfig, str]] = None,  # NEW
        **kwargs
    ):
        super().__init__(
            system_prompt=EXECUTOR_SYSTEM_PROMPT,
            model=model,
            session_id=session_id,
            mcp_servers=mcp_servers,  # NEW
            **kwargs
        )
```

#### 4.1.5 Update Factory Functions

```python
def create_planner_agent(
    model: Optional[str] = None,
    session_id: str = "planner",
    hooks: Optional[Dict[str, Any]] = None,
    cwd: Optional[Path] = None,
    mcp_servers: Optional[Union[McpServersConfig, str]] = None,  # NEW
    allowed_tools: Optional[List[str]] = None,  # NEW
) -> PlannerAgent:
    """Factory function to create a Planner agent."""
    kwargs = {"session_id": session_id}
    if model:
        kwargs["model"] = model
    if hooks:
        kwargs["hooks"] = hooks
    if cwd:
        kwargs["cwd"] = cwd
    if mcp_servers:
        kwargs["mcp_servers"] = mcp_servers
    if allowed_tools:
        kwargs["allowed_tools"] = allowed_tools

    return PlannerAgent(**kwargs)


def create_executor_agent(
    model: Optional[str] = None,
    session_id: str = "executor",
    hooks: Optional[Dict[str, Any]] = None,
    cwd: Optional[Path] = None,
    mcp_servers: Optional[Union[McpServersConfig, str]] = None,  # NEW
    allowed_tools: Optional[List[str]] = None,  # NEW
) -> ExecutorAgent:
    """Factory function to create an Executor agent."""
    kwargs = {"session_id": session_id}
    if model:
        kwargs["model"] = model
    if hooks:
        kwargs["hooks"] = hooks
    if cwd:
        kwargs["cwd"] = cwd
    if mcp_servers:
        kwargs["mcp_servers"] = mcp_servers
    if allowed_tools:
        kwargs["allowed_tools"] = allowed_tools

    return ExecutorAgent(**kwargs)
```

### 4.2 config.py Changes

Add MCP configuration loading **with environment variable expansion**:

```python
import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List


def expand_env_vars(obj: Any) -> Any:
    """
    Recursively expand environment variables in a config object.

    Supports ${VAR} and $VAR syntax in string values.

    Args:
        obj: Config object (dict, list, or scalar)

    Returns:
        Object with environment variables expanded
    """
    if isinstance(obj, dict):
        return {k: expand_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [expand_env_vars(item) for item in obj]
    elif isinstance(obj, str):
        # Expand ${VAR} syntax
        pattern = r'\$\{([^}]+)\}'
        def replace(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))
        expanded = re.sub(pattern, replace, obj)
        # Also expand $VAR syntax (but not $$)
        expanded = os.path.expandvars(expanded)
        return expanded
    else:
        return obj


def load_mcp_config_raw(
    mcp_config_path: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Load MCP configuration from file WITHOUT environment variable expansion.

    Use this when you need to store config in DB (preserves ${VAR} for security).
    Call expand_env_vars() separately for runtime use.

    Priority:
    1. Explicit path (--mcp-config flag)
    2. Project .mcp.json
    3. Global ~/.mcp.json

    Returns:
        Tuple of (mcp_servers, planner_config, executor_config)
        - mcp_servers: Full MCP server definitions (${VAR} preserved)
        - planner_config: Planner-specific MCP settings
        - executor_config: Executor-specific MCP settings
    """
    config_path = None

    # Priority 1: Explicit path
    if mcp_config_path:
        config_path = Path(mcp_config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"MCP config not found: {mcp_config_path}")

    # Priority 2: Project .mcp.json
    if not config_path and project_root:
        project_mcp = project_root / ".mcp.json"
        if project_mcp.exists():
            config_path = project_mcp

    # Priority 3: Global ~/.mcp.json
    if not config_path:
        global_mcp = Path.home() / ".mcp.json"
        if global_mcp.exists():
            config_path = global_mcp

    if not config_path:
        return None, None, None

    # Load and parse (NO env var expansion - preserves ${VAR})
    with open(config_path) as f:
        config = json.load(f)

    mcp_servers = config.get("mcpServers", {})
    orchestrator_config = config.get("orchestrator", {})
    planner_config = orchestrator_config.get("planner", {})
    executor_config = orchestrator_config.get("executor", {})

    return mcp_servers, planner_config, executor_config


def load_mcp_config(
    mcp_config_path: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Load MCP configuration from file WITH environment variable expansion.

    Convenience wrapper that loads raw config and expands env vars.
    For DB storage, use load_mcp_config_raw() instead.

    Returns:
        Tuple of (mcp_servers, planner_config, executor_config) with ${VAR} expanded
    """
    raw_servers, planner_cfg, executor_cfg = load_mcp_config_raw(
        mcp_config_path, project_root
    )

    if raw_servers:
        # Expand env vars for runtime use
        expanded = expand_env_vars({
            "servers": raw_servers,
            "planner": planner_cfg,
            "executor": executor_cfg,
        })
        return expanded["servers"], expanded["planner"], expanded["executor"]

    return None, None, None


def filter_mcp_servers(
    mcp_servers: Dict[str, Any],
    server_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Filter MCP servers to only include specified names.

    Args:
        mcp_servers: Full MCP server configuration
        server_names: List of server names to include (None = all)

    Returns:
        Filtered MCP server configuration
    """
    if server_names is None:
        return mcp_servers

    return {
        name: config
        for name, config in mcp_servers.items()
        if name in server_names
    }


def get_agent_mcp_config(
    mcp_servers: Dict[str, Any],
    agent_config: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Get MCP configuration for a specific agent.

    Args:
        mcp_servers: Full MCP server configuration
        agent_config: Agent-specific configuration (planner or executor)

    Returns:
        Tuple of (filtered_mcp_servers, tool_list)
    """
    # Filter to agent's allowed servers
    server_names = agent_config.get("mcpServers")  # List of server names
    filtered_servers = filter_mcp_servers(mcp_servers, server_names)

    # Get tool list (or generate from servers)
    tools = agent_config.get("tools", [])
    if not tools and filtered_servers:
        # Auto-generate wildcard tools for each server
        tools = [f"mcp__{name}__*" for name in filtered_servers.keys()]

    return filtered_servers, tools
```

### 4.3 db.py Changes

Add MCP config column to sessions table:

```python
# In init_db() - add column to sessions table
def init_db(db_path: Optional[str] = None) -> None:
    """Initialize database schema."""
    with get_connection(db_path) as conn:
        # ... existing schema ...

        # Add mcp_config_json column if not exists (migration)
        try:
            conn.execute("""
                ALTER TABLE sessions
                ADD COLUMN mcp_config_json TEXT
            """)
        except sqlite3.OperationalError:
            # Column already exists
            pass


# Update create_session() to accept mcp_config
def create_session(
    feature_description: str,
    planner_model: Optional[str] = None,
    executor_model: Optional[str] = None,
    project_id: Optional[str] = None,
    project_remote: Optional[str] = None,
    auth_info: Optional[Dict[str, Any]] = None,
    mcp_config: Optional[Dict[str, Any]] = None,  # NEW
    db_path: Optional[str] = None,
) -> str:
    """Create a new session."""
    session_id = str(uuid.uuid4())[:8]

    # Serialize MCP config to JSON
    mcp_config_json = json.dumps(mcp_config) if mcp_config else None

    with get_connection(db_path) as conn:
        conn.execute("""
            INSERT INTO sessions (
                id, feature_description, phase, status,
                planner_model, executor_model,
                project_id, project_remote,
                auth_source, auth_signals, auth_detected_at,
                mcp_config_json,
                created_at, updated_at
            ) VALUES (?, ?, 'discovery', 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, feature_description,
            planner_model, executor_model,
            project_id, project_remote,
            # Use correct auth dict keys (from AuthInfo.to_db_dict())
            auth_info.get("auth_source") if auth_info else None,
            auth_info.get("auth_signals") if auth_info else None,  # Already JSON string
            auth_info.get("auth_detected_at") if auth_info else None,
            mcp_config_json,  # NEW
            datetime.now().isoformat(),
            datetime.now().isoformat(),
        ))

    return session_id


# Add helper to get MCP config from session
def get_session_mcp_config(
    session_id: str,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get MCP configuration from a session.

    Args:
        session_id: Session identifier
        db_path: Optional database path

    Returns:
        MCP config dict or None if not set
    """
    with get_connection(db_path) as conn:
        result = conn.execute(
            "SELECT mcp_config_json FROM sessions WHERE id = ?",
            (session_id,)
        ).fetchone()

        if result and result[0]:
            return json.loads(result[0])
        return None
```

### 4.4 engine.py Changes

Update agent creation to use MCP config with proper imports and DB persistence:

```python
# Add imports at top of file
from .agents import (
    create_planner_agent,
    create_executor_agent,
    PlannerAgent,
    ExecutorAgent,
    build_allowed_tools,  # NEW - helper for tool list
)


class Orchestrator:
    def __init__(
        self,
        feature_description: Optional[str] = None,
        session_id: Optional[str] = None,
        db_path: Optional[str] = None,
        plan_path: Optional[str] = None,
        on_output: Optional[Callable[[str], None]] = None,
        show_activity: bool = True,
        planner_model: Optional[str] = None,
        executor_model: Optional[str] = None,
        telegram_notifier: Optional["TelegramNotifier"] = None,
        debug: bool = False,
        mcp_config_path: Optional[str] = None,  # NEW
    ):
        # ... existing code ...

        # MCP configuration
        self.mcp_servers = None
        self.planner_mcp_config = None
        self.executor_mcp_config = None
        self._mcp_config_for_db = None  # Store for DB persistence

        # Load MCP config based on context
        if session_id:
            # RESUMING: Load MCP config from DB first
            self._load_mcp_from_db(session_id)

        # If explicit path provided or creating new session, load from file
        if mcp_config_path or (feature_description and not session_id):
            self._load_mcp_from_file(mcp_config_path)

    def _load_mcp_from_db(self, session_id: str) -> None:
        """Load MCP configuration from database session."""
        try:
            mcp_config = db.get_session_mcp_config(session_id, self.db_path)
            if mcp_config:
                # Expand env vars at runtime (raw config stored in DB - see Section 10.5)
                from .config import expand_env_vars
                mcp_config = expand_env_vars(mcp_config)
                self._apply_mcp_config(mcp_config)
                if self._debug:
                    self._output(f"  (Loaded MCP config from session)\n")
        except Exception as e:
            if self._debug:
                self._output(f"  (Failed to load MCP from DB: {e})\n")

    def _load_mcp_from_file(self, mcp_config_path: Optional[str]) -> None:
        """Load MCP configuration from file."""
        try:
            from .config import load_mcp_config_raw, expand_env_vars, find_repo_root

            project_root = find_repo_root()

            # Load RAW config (${VAR} unexpanded) for DB storage
            raw_servers, raw_planner_cfg, raw_executor_cfg = load_mcp_config_raw(
                mcp_config_path=mcp_config_path,
                project_root=project_root,
            )

            if raw_servers:
                # Store RAW config for DB persistence (security - see Section 10.5)
                self._mcp_config_for_db = {
                    "servers": raw_servers,
                    "planner": raw_planner_cfg,
                    "executor": raw_executor_cfg,
                }

                # Expand env vars for runtime use
                expanded_config = expand_env_vars(self._mcp_config_for_db)
                self._apply_mcp_config(expanded_config)

        except FileNotFoundError:
            raise  # Let explicit path errors bubble up
        except Exception as e:
            if self._debug:
                self._output(f"  (MCP config load failed: {e})\n")

    def _apply_mcp_config(self, mcp_config: Dict[str, Any]) -> None:
        """Apply loaded MCP configuration."""
        from .config import get_agent_mcp_config

        mcp_servers = mcp_config.get("servers", {})
        planner_cfg = mcp_config.get("planner", {})
        executor_cfg = mcp_config.get("executor", {})

        if mcp_servers:
            self.mcp_servers = mcp_servers

            # Get planner MCP config
            planner_servers, planner_tools = get_agent_mcp_config(
                mcp_servers, planner_cfg or {}
            )
            if planner_servers:
                self.planner_mcp_config = {
                    "servers": planner_servers,
                    "tools": planner_tools,
                }

            # Get executor MCP config
            executor_servers, executor_tools = get_agent_mcp_config(
                mcp_servers, executor_cfg or {}
            )
            if executor_servers:
                self.executor_mcp_config = {
                    "servers": executor_servers,
                    "tools": executor_tools,
                }

    # Update session creation to persist MCP config
    # In the section where db.create_session() is called:
    self.session_id = db.create_session(
        feature_description=feature_description,
        planner_model=planner_model,
        executor_model=executor_model,
        project_id=project_id,
        project_remote=project_remote,
        auth_info=auth_info.to_db_dict(),
        mcp_config=self._mcp_config_for_db,  # NEW
        db_path=db_path
    )


    # Update _create_planner - use build_allowed_tools helper
    def _create_planner(self) -> PlannerAgent:
        """Create or return existing planner agent."""
        if self.planner is None:
            planner_session_id = f"{self.session_id}-planner"
            kwargs = {"session_id": planner_session_id}
            if self.planner_model:
                kwargs["model"] = self.planner_model

            # Add MCP configuration if available
            if self.planner_mcp_config:
                kwargs["mcp_servers"] = self.planner_mcp_config["servers"]
                # Use helper to build tool list (avoids DEFAULT_TOOLS import)
                kwargs["allowed_tools"] = build_allowed_tools(
                    mcp_tools=self.planner_mcp_config["tools"]
                )

            self.planner = create_planner_agent(**kwargs)
            register_recovery_hook(
                self.planner,
                session_id=self.session_id,
                agent_role="PLANNER",
                db_path=self.db_path
            )
        return self.planner


    # Update _create_executor - use build_allowed_tools helper
    def _create_executor(self) -> ExecutorAgent:
        """Create or return existing executor agent."""
        if self.executor is None:
            executor_session_id = f"{self.session_id}-executor"
            kwargs = {"session_id": executor_session_id}
            if self.executor_model:
                kwargs["model"] = self.executor_model

            # Add MCP configuration if available
            if self.executor_mcp_config:
                kwargs["mcp_servers"] = self.executor_mcp_config["servers"]
                # Use helper to build tool list (avoids DEFAULT_TOOLS import)
                kwargs["allowed_tools"] = build_allowed_tools(
                    mcp_tools=self.executor_mcp_config["tools"]
                )

            self.executor = create_executor_agent(**kwargs)
            register_recovery_hook(
                self.executor,
                session_id=self.session_id,
                agent_role="EXECUTOR",
                db_path=self.db_path
            )
        return self.executor
```

### 4.5 cli.py Changes

Add MCP config flag to **all session entrypoints** (start, resume, respond) and thread through queue/watch modes.

**Important:** Use `--mcp-config` only (no `-m` short flag to avoid conflict with `--model/-m` in chat command).

> ⚠️ **Implementation Note:** The CLI snippets below are **intent-based pseudocode** showing where to add MCP config handling. Actual implementation must follow the existing `cli.py` patterns:
> - `respond` command has its own implementation (does NOT delegate to `resume`)
> - `watch` command takes `plans_dir` as a positional argument, not `--queue-dir`
> - Parameter threading must match actual function signatures
>
> Use these snippets as guidance for the changes needed, not as copy-paste code.

```python
# === START COMMAND ===
@click.option(
    "--mcp-config",
    type=click.Path(exists=True),
    help="Path to MCP configuration file (.mcp.json)",
)
def start(
    feature,
    plan,
    queue,
    planner_model,
    executor_model,
    auto_commit,
    telegram,
    mcp_config,  # NEW - no short flag
):
    """Start a new orchestration session."""

    if queue:
        # Thread MCP config through queue mode
        _handle_queue_mode(
            plans=queue,
            planner_model=planner_model,
            executor_model=executor_model,
            auto_commit=auto_commit,
            telegram=telegram,
            mcp_config_path=mcp_config,  # NEW
        )
        return

    orchestrator = Orchestrator(
        feature_description=feature,
        plan_path=plan,
        planner_model=planner_model,
        executor_model=executor_model,
        telegram_notifier=telegram_notifier,
        mcp_config_path=mcp_config,  # NEW
    )
    # ... rest unchanged


# === RESUME COMMAND ===
@click.option(
    "--mcp-config",
    type=click.Path(exists=True),
    help="Path to MCP configuration file (overrides saved config)",
)
def resume(
    session_id,
    answer,
    db_path,
    show_activity,
    telegram,
    force,
    auto_commit,
    smart_commit,
    auto_commit_model,
    debug,
    mcp_config,  # NEW
):
    """Resume a paused session."""
    # ... existing validation code ...

    orchestrator = Orchestrator(
        session_id=session_id,
        db_path=db_path,
        show_activity=show_activity,
        telegram_notifier=telegram_notifier,
        debug=debug,
        mcp_config_path=mcp_config,  # NEW - overrides DB if provided
    )
    # ... rest unchanged


# === RESPOND COMMAND ===
@click.option(
    "--mcp-config",
    type=click.Path(exists=True),
    help="Path to MCP configuration file (overrides saved config)",
)
def respond(
    session_id,
    answer,
    db_path,
    telegram,
    mcp_config,  # NEW
):
    """Respond to a blocker (alias for resume with answer)."""
    # ... existing code ...

    orchestrator = Orchestrator(
        session_id=session_id,
        db_path=db_path,
        telegram_notifier=telegram_notifier,
        mcp_config_path=mcp_config,  # NEW
    )
    # ... rest unchanged


# === QUEUE MODE HANDLER ===
def _handle_queue_mode(
    plans: List[str],
    planner_model: Optional[str],
    executor_model: Optional[str],
    auto_commit: bool,
    telegram: bool,
    mcp_config_path: Optional[str] = None,  # NEW
):
    """Handle queue mode execution."""
    for plan_path in plans:
        # ... existing queue item handling ...

        orchestrator = Orchestrator(
            feature_description=feature,
            plan_path=plan_path,
            planner_model=planner_model,
            executor_model=executor_model,
            telegram_notifier=telegram_notifier,
            mcp_config_path=mcp_config_path,  # NEW - propagate to each session
        )
        # ... rest unchanged


# === WATCH COMMAND ===
@click.option(
    "--mcp-config",
    type=click.Path(exists=True),
    help="Path to MCP configuration file for all watched sessions",
)
def watch(
    queue_dir,
    auto_convert,
    planner_model,
    executor_model,
    auto_commit,
    telegram,
    mcp_config,  # NEW
):
    """Watch a directory for plan files and run them."""
    # ... existing watch loop ...

    for plan_file in new_plans:
        orchestrator = Orchestrator(
            feature_description=extract_feature(plan_file),
            plan_path=str(plan_file),
            planner_model=planner_model,
            executor_model=executor_model,
            telegram_notifier=telegram_notifier,
            mcp_config_path=mcp_config,  # NEW - propagate to each session
        )
        # ... rest unchanged
```

---

## 5. Configuration Options

### 5.1 Basic .mcp.json

Minimal configuration for Playwright only:

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

### 5.2 Multi-Server with Agent Scoping

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
    },
    "github": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-github"]
    }
  },
  "orchestrator": {
    "planner": {
      "mcpServers": ["figma", "github"],
      "tools": ["mcp__figma__*", "mcp__github__search_*"]
    },
    "executor": {
      "mcpServers": ["playwright"],
      "tools": ["mcp__playwright__*"]
    }
  }
}
```

### 5.3 Executor-Only Configuration

For E2E testing workflows:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-playwright"]
    }
  },
  "orchestrator": {
    "executor": {
      "mcpServers": ["playwright"]
    }
  }
}
```

### 5.4 Environment Variable Substitution

Environment variables are automatically expanded using `${VAR}` syntax:

```json
{
  "mcpServers": {
    "figma": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-figma"],
      "env": {
        "FIGMA_ACCESS_TOKEN": "${FIGMA_ACCESS_TOKEN}"
      }
    },
    "custom": {
      "command": "${HOME}/bin/my-mcp-server",
      "args": ["--config", "${MCP_CONFIG_DIR}/custom.json"]
    }
  }
}
```

**Expansion happens at load time** in `config.py:expand_env_vars()`, so the resolved values are what gets stored in the database and passed to agents.

---

## 6. CLI Interface Changes

### 6.1 New Flags

**Note:** Using `--mcp-config` only (no `-m` short flag) to avoid conflict with `--model/-m` in chat command.

```bash
# Start with explicit MCP config file
orchestrator start -f "Feature" --mcp-config ./my-mcp.json

# Combined with other options
orchestrator start -f "E2E Tests" \
  --mcp-config .mcp.json \
  --plan docs/e2e-plan.md \
  -pm opus -em sonnet

# Resume with MCP override (useful if config file moved)
orchestrator resume abc123 --mcp-config /new/path/.mcp.json

# Respond with MCP override
orchestrator respond abc123 "yes" --mcp-config .mcp.json

# Queue mode with MCP
orchestrator start --queue plan1.md plan2.md --mcp-config .mcp.json

# Watch mode with MCP
orchestrator watch --queue-dir plans/ --mcp-config .mcp.json
```

### 6.2 Auto-Discovery (No Flags Needed)

If `.mcp.json` exists in project root or `~/.mcp.json`:

```bash
# Automatically loads .mcp.json if present
orchestrator start -f "Feature with Playwright"

# Resume automatically loads MCP config from session DB
orchestrator resume abc123
```

### 6.3 Check Command Enhancement

```bash
# Show MCP configuration status
orchestrator check

# Output:
# ✓ Authentication: API Key detected
# ✓ Dependencies: All installed
# ✓ API: Connected
# ✓ MCP Config: .mcp.json found
#   - playwright: npx @anthropic/mcp-server-playwright
#   - figma: npx @anthropic/mcp-server-figma (env: FIGMA_ACCESS_TOKEN)
```

---

## 7. Testing Strategy

### 7.1 Unit Tests

```python
# tests/test_agents.py

def test_base_agent_accepts_mcp_servers():
    """BaseAgent should accept mcp_servers parameter."""
    mcp_config = {
        "playwright": {
            "command": "npx",
            "args": ["@anthropic/mcp-server-playwright"]
        }
    }
    agent = BaseAgent(
        system_prompt="Test",
        mcp_servers=mcp_config,
    )
    assert agent.mcp_servers == mcp_config


def test_build_allowed_tools_combines_lists():
    """build_allowed_tools should combine base and MCP tools."""
    tools = build_allowed_tools(mcp_tools=["mcp__playwright__*"])
    assert "Read" in tools  # Base tool
    assert "mcp__playwright__*" in tools  # MCP tool


def test_build_allowed_tools_defaults_to_default_tools():
    """build_allowed_tools should use DEFAULT_TOOLS when no base provided."""
    tools = build_allowed_tools()
    assert tools == DEFAULT_TOOLS
```

### 7.2 Config Loading Tests

```python
# tests/test_config.py

def test_expand_env_vars_substitutes_variables(monkeypatch):
    """Should expand ${VAR} syntax in config."""
    monkeypatch.setenv("MY_TOKEN", "secret123")

    config = {"env": {"TOKEN": "${MY_TOKEN}"}}
    expanded = expand_env_vars(config)

    assert expanded["env"]["TOKEN"] == "secret123"


def test_expand_env_vars_leaves_unset_unchanged():
    """Should leave ${VAR} unchanged if not set."""
    config = {"env": {"TOKEN": "${UNDEFINED_VAR}"}}
    expanded = expand_env_vars(config)

    assert expanded["env"]["TOKEN"] == "${UNDEFINED_VAR}"


def test_load_mcp_config_expands_env_vars(tmp_path, monkeypatch):
    """Should expand env vars when loading config."""
    monkeypatch.setenv("FIGMA_TOKEN", "fig_123")

    config = {
        "mcpServers": {
            "figma": {
                "command": "npx",
                "env": {"FIGMA_ACCESS_TOKEN": "${FIGMA_TOKEN}"}
            }
        }
    }
    config_file = tmp_path / ".mcp.json"
    config_file.write_text(json.dumps(config))

    servers, _, _ = load_mcp_config(mcp_config_path=str(config_file))

    assert servers["figma"]["env"]["FIGMA_ACCESS_TOKEN"] == "fig_123"
```

### 7.3 DB Persistence Tests

```python
# tests/test_db.py

def test_create_session_with_mcp_config(tmp_path):
    """Should persist MCP config to database."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)

    mcp_config = {
        "servers": {"playwright": {"command": "npx"}},
        "executor": {"mcpServers": ["playwright"]}
    }

    session_id = create_session(
        feature_description="Test",
        mcp_config=mcp_config,
        db_path=db_path,
    )

    loaded = get_session_mcp_config(session_id, db_path)
    assert loaded == mcp_config


def test_resume_loads_mcp_from_db(tmp_path):
    """Orchestrator should load MCP config from DB on resume."""
    # Setup: create session with MCP config
    db_path = str(tmp_path / "test.db")
    init_db(db_path)

    mcp_config = {"servers": {"playwright": {"command": "npx"}}}
    session_id = create_session(
        feature_description="Test",
        mcp_config=mcp_config,
        db_path=db_path,
    )

    # Resume without explicit MCP path
    orchestrator = Orchestrator(
        session_id=session_id,
        db_path=db_path,
    )

    assert orchestrator.mcp_servers == {"playwright": {"command": "npx"}}
```

### 7.4 Integration Tests

```python
# tests/test_integration.py

@pytest.mark.integration
def test_queue_mode_propagates_mcp_config(tmp_path):
    """Queue mode should pass MCP config to all sessions."""
    # Create MCP config
    mcp_config = tmp_path / ".mcp.json"
    mcp_config.write_text(json.dumps({
        "mcpServers": {"playwright": {"command": "npx"}}
    }))

    # Create plan files
    plan1 = tmp_path / "plan1.md"
    plan1.write_text("# Plan 1\n## Milestone 1: Test")

    # Run queue mode (mocked)
    # Verify each session has MCP config
```

---

## 8. Migration Guide

### 8.1 For Existing Workflows

Existing workflows without MCP continue to work unchanged:

```bash
# This still works exactly as before
orchestrator start -f "Feature without MCP"
```

### 8.2 Adding MCP to Existing Workflow

1. Create `.mcp.json` in project root:

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

2. Install MCP server:

```bash
npm install -g @anthropic/mcp-server-playwright
```

3. Run orchestrator (auto-discovers config):

```bash
orchestrator start -f "E2E Tests with Playwright"
```

### 8.3 Database Migration

The `mcp_config_json` column is added automatically on first use via `ALTER TABLE`. Existing sessions will have `NULL` for this column, which is handled gracefully (no MCP tools for those sessions).

### 8.4 Updating System Prompts

Update prompts to document available MCP tools:

```python
# prompts.py - Add to EXECUTOR_SYSTEM_PROMPT

EXECUTOR_MCP_ADDENDUM = """
## MCP Tools

In addition to standard tools, you may have access to MCP-provided tools:

### Playwright Browser Tools (if available)
- `mcp__playwright__browser_navigate` - Navigate to URL
- `mcp__playwright__browser_click` - Click element
- `mcp__playwright__browser_type` - Type text
- `mcp__playwright__browser_snapshot` - Get page accessibility snapshot
- `mcp__playwright__browser_close` - Close browser

IMPORTANT: Always close the browser before completing your milestone report.
"""
```

---

## 9. Alternative Approaches

### 9.1 Approach A: CLI Tool Passthrough (Current Proposal)

**Pros:**
- Clean separation of concerns
- Per-agent MCP scoping
- Config-file driven (version controllable)
- Resume/queue support via DB persistence

**Cons:**
- Requires MCP servers to be installed
- Each agent spawns own MCP server processes

### 9.2 Approach B: Shared MCP Server Pool

Share MCP servers between agents:

```python
class MCPServerPool:
    """Shared pool of MCP server connections."""

    def __init__(self, config: Dict[str, Any]):
        self.servers = {}
        for name, server_config in config.items():
            self.servers[name] = self._start_server(server_config)

    def get_server(self, name: str):
        return self.servers.get(name)
```

**Pros:**
- Single server instance per type
- Lower resource usage

**Cons:**
- More complex lifecycle management
- SDK may not support shared connections

### 9.3 Approach C: Use Playwright CLI Instead

Skip MCP, use Playwright CLI via Bash:

```bash
# In executor
npx playwright test --project=chromium
```

**Pros:**
- No MCP integration needed
- Works with existing tools

**Cons:**
- Less interactive (batch mode only)
- Can't do step-by-step browser control
- Not aligned with user's MCP workflow

### 9.4 Recommendation

**Approach A (Current Proposal)** is recommended because:
1. Aligns with Claude Code's MCP architecture
2. Matches user's expectation from direct Claude Code usage
3. Enables per-agent tool scoping
4. Supports resume/queue workflows via DB persistence
5. Most flexible for future MCP servers

---

## 10. Open Questions

### 10.1 MCP Server Lifecycle

**Question:** Should MCP servers be started once per orchestrator run, or once per agent?

**Current Proposal:** Per-agent (SDK manages lifecycle in `__aenter__`/`__aexit__`)

**Alternative:** Pre-start servers in engine, share connections

### 10.2 Error Handling

**Question:** How should MCP server startup failures be handled?

**Options:**
1. Fail fast - abort workflow if MCP server fails to start
2. Graceful degradation - continue without MCP tools, warn user
3. Retry logic - attempt reconnection

**Recommendation:** Option 2 with clear warning

### 10.3 Config Override on Resume

**Question:** Should `--mcp-config` on resume completely replace or merge with DB config?

**Current Proposal:** Complete replacement (simpler semantics)

**Alternative:** Deep merge (more complex, edge cases)

### 10.4 ~~Config File Location~~ (Resolved)

Using standard `.mcp.json` with `orchestrator` section (consistent with Claude Code).

### 10.5 Security: Raw vs Expanded Config Storage (Resolved)

**Question:** Should we store expanded env vars (secrets in plaintext) or raw config with `${VAR}` in the database?

**Decision:** Store **RAW config** (with `${VAR}` syntax) in the database.

**Rationale:**
- **Security risk:** Expanded configs would store secrets like `FIGMA_ACCESS_TOKEN` in plaintext in `~/.claude_orchestrator/db.sqlite`
- **Runtime expansion:** Expand env vars on each load (during `_load_mcp_from_db()` and `_load_mcp_from_file()`)
- **Consistency:** Resume sessions get current env values, not stale secrets from session creation time

**Implementation:**
```python
# In db.py create_session() - store RAW config
mcp_config_json = json.dumps(mcp_config) if mcp_config else None  # ${VAR} preserved

# In engine.py _load_mcp_from_db() - expand on load
mcp_config = db.get_session_mcp_config(session_id, self.db_path)
if mcp_config:
    from .config import expand_env_vars
    mcp_config = expand_env_vars(mcp_config)  # Expand ${VAR} at runtime
    self._apply_mcp_config(mcp_config)
```

**Trade-off:** If env var is unset at resume time, the `${VAR}` literal will be passed to MCP server (which will likely fail). This is acceptable as it surfaces configuration issues clearly rather than silently using stale secrets.

---

## 11. Summary

This proposal enables MCP tools in orchestrator-auto agents through:

| Change | Location | Impact | Notes |
|--------|----------|--------|-------|
| Add `mcp_servers` param | `agents.py` | Low | Core plumbing |
| Add `build_allowed_tools()` | `agents.py` | Low | Clean import boundary |
| MCP config loading + env expansion | `config.py` | Medium | Handle `${VAR}` |
| Add `mcp_config_json` column | `db.py` | Low | Resume support |
| Engine integration + DB load | `engine.py` | Medium | Uses helper, loads from DB |
| CLI flags (start/resume/respond) | `cli.py` | Medium | No `-m` conflict |
| Queue/watch mode threading | `cli.py` | Medium | Batch support |
| Documentation | `AGENTS.md` | Low | |

**Total estimated effort:** 6-8 hours of implementation + testing

**Risk level:** Low (all changes are additive and backward-compatible)

**Next steps:**
1. Review this updated proposal
2. Approve or request changes
3. Implement in order:
   - `agents.py` (add mcp_servers + build_allowed_tools)
   - `config.py` (add loader with env expansion)
   - `db.py` (add mcp_config_json column)
   - `engine.py` (load from file/DB, use helper)
   - `cli.py` (add flags to all commands, thread through queue/watch)
   - tests
4. Update documentation
5. Test with `use-case-01-playright.md` workflow
