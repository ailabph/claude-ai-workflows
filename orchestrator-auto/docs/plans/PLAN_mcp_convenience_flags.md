# Implementation Plan: MCP Convenience Flags

## Overview

Add `--mcp-playwright` and `--mcp-figma` convenience flags for zero-config MCP setup while preserving `--mcp-config` for advanced/custom configurations.

**Goals:**
- Simple CLI for common MCPs: `orchestrator start -f "Feature" --mcp-playwright`
- Composable: `--mcp-playwright --mcp-figma` for both
- Backward compatible: `--mcp-config` still works for custom setups
- Proper agent routing: Playwright → Executor, Figma → Planner (configurable)

---

## Current State

### Existing MCP Configuration Flow

```
CLI (--mcp-config path)
    ↓
engine.py: _load_mcp_from_file()
    ↓
config.py: load_mcp_config_raw() → expand_env_vars()
    ↓
engine.py: _apply_mcp_config()
    ├── inject_headless_mode() if --headless
    ├── inject_mcp_size_guard() for crash prevention
    └── get_agent_mcp_config() for filtering
    ↓
agents.py: PlannerAgent/ExecutorAgent with mcp_servers
```

### Current CLI Flags

```python
@click.option('--mcp-config', type=click.Path(exists=True), help='Path to MCP configuration file')
@click.option('--headless', is_flag=True, help='Run Playwright MCP browser in headless mode')
```

---

## Proposed Design

### New CLI Interface

```bash
# Convenience flags (zero-config)
orchestrator start -f "E2E tests" --mcp-playwright [--headless]
orchestrator start -f "Design review" --mcp-figma
orchestrator start -f "Full stack" --mcp-playwright --mcp-figma

# Advanced/custom (existing)
orchestrator start -f "Feature" --mcp-config custom.mcp.json

# Error: mutually exclusive
orchestrator start -f "Feature" --mcp-playwright --mcp-config x.json  # Error!
```

### Built-in MCP Configurations

**Playwright MCP:**
```python
{
    "command": "npx",
    "args": ["@playwright/mcp@latest"],  # --headless injected if flag set
}
```

**Figma MCP:**
```python
{
    "command": "npx",
    "args": ["@anthropic/mcp-figma@latest"],
    "env": {"FIGMA_ACCESS_TOKEN": "${FIGMA_ACCESS_TOKEN}"}  # From env var
}
```

### Default Agent Routing

| MCP | Default Agent | Rationale |
|-----|---------------|-----------|
| Playwright | Executor | Browser automation is implementation work |
| Figma | Both (Planner + Executor) | Design reference useful for both planning and implementation |

**Configurable via orchestrator section** (for advanced users with `--mcp-config`).

---

## Architecture

### Config Builder Function

New function in `config.py`:

```python
def build_mcp_config(
    playwright: bool = False,
    figma: bool = False,
    headless: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Build MCP configuration from convenience flags.

    Args:
        playwright: Enable Playwright MCP for browser automation
        figma: Enable Figma MCP for design access
        headless: Run Playwright in headless mode

    Returns:
        MCP config dict or None if no MCPs enabled
    """
```

### Engine Integration

Update `Orchestrator.__init__()` to accept convenience flags:

```python
def __init__(
    self,
    feature: str,
    ...,
    mcp_config_path: Optional[str] = None,
    # New convenience flags
    mcp_playwright: bool = False,
    mcp_figma: bool = False,
    headless: bool = False,
):
    # Validate mutual exclusivity
    if mcp_config_path and (mcp_playwright or mcp_figma):
        raise ValueError(
            "Cannot use --mcp-config with --mcp-playwright/--mcp-figma. "
            "Use one or the other."
        )

    # Build config from flags or load from file
    if mcp_playwright or mcp_figma:
        mcp_config = build_mcp_config(
            playwright=mcp_playwright,
            figma=mcp_figma,
            headless=headless,
        )
        self._apply_mcp_config(mcp_config)
    elif mcp_config_path:
        self._load_mcp_from_file(mcp_config_path)
```

### CLI Propagation

Add flags to all relevant commands:
- `start` - primary entry point
- `resume` - may need MCP for resumed sessions
- `respond` - may need MCP when answering blockers
- Queue mode (`_run_queue`, `_handle_queue_mode`)

---

## Implementation Milestones

### Milestone 1: Config Builder

**Goal**: Create `build_mcp_config()` function with built-in MCP definitions.

**File**: `orchestrator_auto/config.py`

**Deliverables**:

```python
# Built-in MCP server definitions
BUILTIN_MCP_SERVERS = {
    "playwright": {
        "command": "npx",
        "args": ["@playwright/mcp@latest"],
    },
    "figma": {
        "command": "npx",
        "args": ["@anthropic/mcp-figma@latest"],
        "env": {"FIGMA_ACCESS_TOKEN": "${FIGMA_ACCESS_TOKEN}"},
    },
}

# Default agent routing
DEFAULT_MCP_ROUTING = {
    "playwright": {
        "agents": ["executor"],  # Playwright primarily for executor
    },
    "figma": {
        "agents": ["planner", "executor"],  # Figma useful for both
    },
}


def build_mcp_config(
    playwright: bool = False,
    figma: bool = False,
    headless: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Build MCP configuration from convenience flags.

    Args:
        playwright: Enable Playwright MCP for browser automation
        figma: Enable Figma MCP for design access
        headless: Run Playwright in headless mode

    Returns:
        MCP config dict compatible with .mcp.json format, or None if no MCPs enabled

    Example return:
        {
            "mcpServers": {
                "playwright": {"command": "npx", "args": ["@playwright/mcp@latest", "--headless"]},
                "figma": {"command": "npx", "args": ["..."], "env": {...}}
            },
            "orchestrator": {
                "planner": {"mcpServers": ["figma"]},
                "executor": {"mcpServers": ["playwright", "figma"]}
            }
        }
    """
    if not playwright and not figma:
        return None

    import copy

    servers = {}
    planner_servers = []
    executor_servers = []

    if playwright:
        server_config = copy.deepcopy(BUILTIN_MCP_SERVERS["playwright"])
        if headless:
            server_config["args"] = server_config.get("args", []) + ["--headless"]
        servers["playwright"] = server_config
        executor_servers.append("playwright")

    if figma:
        servers["figma"] = copy.deepcopy(BUILTIN_MCP_SERVERS["figma"])
        planner_servers.append("figma")
        executor_servers.append("figma")

    config = {"mcpServers": servers}

    # Add orchestrator routing section
    orchestrator_config = {}
    if planner_servers:
        orchestrator_config["planner"] = {"mcpServers": planner_servers}
    if executor_servers:
        orchestrator_config["executor"] = {"mcpServers": executor_servers}

    if orchestrator_config:
        config["orchestrator"] = orchestrator_config

    return config
```

**Tests**:
```python
class TestBuildMcpConfig:
    def test_no_flags_returns_none(self):
        result = build_mcp_config()
        assert result is None

    def test_playwright_only(self):
        result = build_mcp_config(playwright=True)
        assert "playwright" in result["mcpServers"]
        assert "figma" not in result["mcpServers"]
        assert result["orchestrator"]["executor"]["mcpServers"] == ["playwright"]

    def test_figma_only(self):
        result = build_mcp_config(figma=True)
        assert "figma" in result["mcpServers"]
        assert "playwright" not in result["mcpServers"]
        assert "figma" in result["orchestrator"]["planner"]["mcpServers"]
        assert "figma" in result["orchestrator"]["executor"]["mcpServers"]

    def test_both_mcps(self):
        result = build_mcp_config(playwright=True, figma=True)
        assert "playwright" in result["mcpServers"]
        assert "figma" in result["mcpServers"]

    def test_headless_injects_flag(self):
        result = build_mcp_config(playwright=True, headless=True)
        assert "--headless" in result["mcpServers"]["playwright"]["args"]

    def test_figma_has_env_var(self):
        result = build_mcp_config(figma=True)
        assert "${FIGMA_ACCESS_TOKEN}" in str(result["mcpServers"]["figma"]["env"])
```

---

### Milestone 2: Engine Integration

**Goal**: Update `Orchestrator` to accept and process convenience flags.

**File**: `orchestrator_auto/engine.py`

**Changes**:

1. Update `__init__()` signature:
```python
def __init__(
    self,
    feature: str,
    session_id: Optional[str] = None,
    db_path: Optional[str] = None,
    planner_model: Optional[str] = None,
    executor_model: Optional[str] = None,
    mcp_config_path: Optional[str] = None,
    # New parameters
    mcp_playwright: bool = False,
    mcp_figma: bool = False,
    headless: bool = False,
    ...
):
```

2. Add validation and config building:
```python
# Validate mutual exclusivity
if mcp_config_path and (mcp_playwright or mcp_figma):
    raise ValueError(
        "Cannot use --mcp-config with --mcp-playwright/--mcp-figma"
    )

# Store flags for DB persistence
self._mcp_playwright = mcp_playwright
self._mcp_figma = mcp_figma
self._headless = headless

# Build or load MCP config
if mcp_playwright or mcp_figma:
    from .config import build_mcp_config
    mcp_config = build_mcp_config(
        playwright=mcp_playwright,
        figma=mcp_figma,
        headless=headless,
    )
    if mcp_config:
        self._mcp_config_for_db = mcp_config  # Store for persistence
        self._apply_mcp_config(mcp_config)
elif mcp_config_path:
    self._load_mcp_from_file(mcp_config_path)
elif session_id:
    self._load_mcp_from_db()
```

3. Update DB persistence to store convenience flags:
```python
# In session creation, store which flags were used
db.create_session(
    ...,
    mcp_config=self._mcp_config_for_db,
    mcp_flags={
        "playwright": self._mcp_playwright,
        "figma": self._mcp_figma,
        "headless": self._headless,
    }
)
```

**Tests**:
```python
class TestOrchestratorMcpFlags:
    def test_mutual_exclusivity_error(self, temp_db):
        with pytest.raises(ValueError, match="Cannot use --mcp-config"):
            Orchestrator(
                feature="test",
                mcp_config_path="test.json",
                mcp_playwright=True,
                db_path=temp_db,
            )

    def test_playwright_flag_builds_config(self, temp_db):
        orch = Orchestrator(
            feature="test",
            mcp_playwright=True,
            db_path=temp_db,
        )
        assert orch.executor_mcp_config is not None
        assert "playwright" in orch.mcp_servers

    def test_figma_flag_builds_config(self, temp_db):
        orch = Orchestrator(
            feature="test",
            mcp_figma=True,
            db_path=temp_db,
        )
        assert "figma" in orch.mcp_servers
```

---

### Milestone 3: CLI Integration

**Goal**: Add convenience flags to CLI commands.

**File**: `orchestrator_auto/cli.py`

**Changes to `start` command**:

```python
@cli.command()
@click.option('--feature', '-f', required=False, help='Feature description')
# ... existing options ...
@click.option('--mcp-config', type=click.Path(exists=True), help='Path to MCP configuration file (.mcp.json)')
@click.option('--headless', is_flag=True, default=False, help='Run Playwright MCP browser in headless mode')
# New convenience flags
@click.option('--mcp-playwright', is_flag=True, default=False,
              help='Enable Playwright MCP for browser automation')
@click.option('--mcp-figma', is_flag=True, default=False,
              help='Enable Figma MCP for design file access (requires FIGMA_ACCESS_TOKEN env var)')
def start(
    feature: Optional[str],
    ...,
    mcp_config: Optional[str],
    headless: bool,
    mcp_playwright: bool,
    mcp_figma: bool,
    ...
):
    # Validate mutual exclusivity at CLI level
    if mcp_config and (mcp_playwright or mcp_figma):
        raise click.UsageError(
            "Cannot use --mcp-config with --mcp-playwright/--mcp-figma. "
            "Choose one approach:\n"
            "  • Use --mcp-playwright and/or --mcp-figma for built-in configs\n"
            "  • Use --mcp-config for custom configuration"
        )

    # Check Figma token if flag used
    if mcp_figma and not os.environ.get("FIGMA_ACCESS_TOKEN"):
        raise click.UsageError(
            "--mcp-figma requires FIGMA_ACCESS_TOKEN environment variable.\n"
            "Set it with: export FIGMA_ACCESS_TOKEN='your-token'"
        )

    # Create orchestrator with flags
    orch = Orchestrator(
        feature=effective_feature,
        ...,
        mcp_config_path=mcp_config,
        mcp_playwright=mcp_playwright,
        mcp_figma=mcp_figma,
        headless=headless,
    )
```

**Changes to `resume` command**:

```python
@cli.command()
@click.argument('session_id')
# ... existing options ...
@click.option('--mcp-playwright', is_flag=True, default=False,
              help='Enable Playwright MCP (overrides stored config)')
@click.option('--mcp-figma', is_flag=True, default=False,
              help='Enable Figma MCP (overrides stored config)')
def resume(session_id: str, ..., mcp_playwright: bool, mcp_figma: bool):
    # On resume, flags override stored config if specified
    ...
```

**Changes to `respond` command** (similar pattern).

**Changes to queue mode** (`_run_queue`, `_handle_queue_mode`):

```python
def _run_queue(
    ...,
    mcp_config_path: Optional[str] = None,
    mcp_playwright: bool = False,
    mcp_figma: bool = False,
    headless: bool = False,
):
    # Pass flags through to each queue item's Orchestrator
    ...
```

**Tests**:
```python
class TestMcpConvenienceFlags:
    def test_start_with_playwright_flag(self, runner, temp_db):
        with patch('orchestrator_auto.cli.Orchestrator') as mock_orch:
            result = runner.invoke(cli, [
                'start', '-f', 'test', '--mcp-playwright', '-d', temp_db
            ])
            mock_orch.assert_called_once()
            call_kwargs = mock_orch.call_args[1]
            assert call_kwargs['mcp_playwright'] is True

    def test_start_with_figma_flag(self, runner, temp_db, monkeypatch):
        monkeypatch.setenv('FIGMA_ACCESS_TOKEN', 'test-token')
        with patch('orchestrator_auto.cli.Orchestrator') as mock_orch:
            result = runner.invoke(cli, [
                'start', '-f', 'test', '--mcp-figma', '-d', temp_db
            ])
            mock_orch.assert_called_once()
            call_kwargs = mock_orch.call_args[1]
            assert call_kwargs['mcp_figma'] is True

    def test_mutual_exclusivity_error(self, runner, temp_db):
        result = runner.invoke(cli, [
            'start', '-f', 'test',
            '--mcp-playwright', '--mcp-config', 'test.json',
            '-d', temp_db
        ])
        assert result.exit_code != 0
        assert 'Cannot use --mcp-config' in result.output

    def test_figma_requires_token(self, runner, temp_db, monkeypatch):
        monkeypatch.delenv('FIGMA_ACCESS_TOKEN', raising=False)
        result = runner.invoke(cli, [
            'start', '-f', 'test', '--mcp-figma', '-d', temp_db
        ])
        assert result.exit_code != 0
        assert 'FIGMA_ACCESS_TOKEN' in result.output

    def test_both_flags_together(self, runner, temp_db, monkeypatch):
        monkeypatch.setenv('FIGMA_ACCESS_TOKEN', 'test-token')
        with patch('orchestrator_auto.cli.Orchestrator') as mock_orch:
            result = runner.invoke(cli, [
                'start', '-f', 'test',
                '--mcp-playwright', '--mcp-figma',
                '-d', temp_db
            ])
            call_kwargs = mock_orch.call_args[1]
            assert call_kwargs['mcp_playwright'] is True
            assert call_kwargs['mcp_figma'] is True
```

---

### Milestone 4: Health Check Integration

**Goal**: Add MCP convenience flag status to `orchestrator check`.

**File**: `orchestrator_auto/cli.py`

**Changes to `check` command**:

```python
# Add section 6: MCP Availability
click.secho("6. MCP Tools", bold=True)

# Check Playwright MCP
try:
    result = subprocess.run(
        ["npx", "@playwright/mcp@latest", "--version"],
        capture_output=True,
        text=True,
        timeout=30
    )
    if result.returncode == 0:
        click.echo(f"   {click.style('✓', fg='green')} Playwright MCP available")
    else:
        click.echo(f"   {click.style('○', fg='yellow')} Playwright MCP (npx will install on first use)")
except Exception:
    click.echo(f"   {click.style('○', fg='yellow')} Playwright MCP (npx will install on first use)")

# Check Figma MCP
figma_token = os.environ.get("FIGMA_ACCESS_TOKEN")
if figma_token:
    click.echo(f"   {click.style('✓', fg='green')} Figma MCP ready (FIGMA_ACCESS_TOKEN set)")
else:
    click.echo(f"   {click.style('○', fg='yellow')} Figma MCP (set FIGMA_ACCESS_TOKEN to enable)")
```

---

### Milestone 5: Documentation

**Goal**: Update README and help text.

**File**: `README.md`

**Add section**:

```markdown
### MCP Tool Integration

Enable browser automation or design file access with convenience flags:

**Playwright MCP** (browser automation):
```bash
orchestrator start -f "E2E tests" --mcp-playwright
orchestrator start -f "Visual QA" --mcp-playwright --headless
```

**Figma MCP** (design file access):
```bash
export FIGMA_ACCESS_TOKEN="your-token"
orchestrator start -f "Design review" --mcp-figma
```

**Both MCPs together**:
```bash
orchestrator start -f "Full stack feature" --mcp-playwright --mcp-figma
```

**Custom MCP configuration** (advanced):
```bash
orchestrator start -f "Feature" --mcp-config .mcp.json
```

> Note: `--mcp-config` cannot be combined with `--mcp-playwright`/`--mcp-figma`.
> Use one approach or the other.
```

---

## Implementation Checklist

### Milestone 1: Config Builder (~1 hour)
- [ ] Add `BUILTIN_MCP_SERVERS` constant to `config.py`
- [ ] Add `DEFAULT_MCP_ROUTING` constant to `config.py`
- [ ] Implement `build_mcp_config()` function
- [ ] Add unit tests for config builder

### Milestone 2: Engine Integration (~1 hour)
- [ ] Update `Orchestrator.__init__()` signature
- [ ] Add mutual exclusivity validation
- [ ] Integrate `build_mcp_config()` call
- [ ] Update DB persistence for flags
- [ ] Add unit tests for engine

### Milestone 3: CLI Integration (~2 hours)
- [ ] Add `--mcp-playwright` and `--mcp-figma` to `start` command
- [ ] Add flags to `resume` command
- [ ] Add flags to `respond` command
- [ ] Update queue mode functions
- [ ] Add Figma token validation
- [ ] Add helpful error messages
- [ ] Add CLI tests

### Milestone 4: Health Check (~30 min)
- [ ] Add MCP availability section to `check` command
- [ ] Test Playwright MCP detection
- [ ] Test Figma token detection

### Milestone 5: Documentation (~30 min)
- [ ] Update README.md with examples
- [ ] Update CLI help text
- [ ] Add to CHANGELOG.md

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Figma MCP package name changes | Low | Medium | Use `@anthropic/mcp-figma@latest` with version pinning option |
| User confusion about mutual exclusivity | Medium | Low | Clear error messages, examples in help |
| Token not set for Figma | High | Medium | Validate at CLI level with helpful message |
| npx install slow on first use | Medium | Low | Document in help, show progress |
| Agent routing doesn't fit user's needs | Low | Medium | Document `--mcp-config` for custom routing |

---

## Future Enhancements (Not in This Plan)

1. **More MCPs**: `--mcp-github`, `--mcp-slack`, etc.
2. **Agent routing flags**: `--mcp-playwright-agent executor` to customize
3. **MCP version pinning**: `--mcp-playwright-version 1.2.3`
4. **Config generation**: `orchestrator mcp init` to create `.mcp.json`
5. **MCP status in `list`**: Show which MCPs a session uses

---

## Success Metrics

| Metric | Target |
|--------|--------|
| CLI usability | Zero-config for Playwright/Figma |
| Backward compatibility | 100% - existing `--mcp-config` unchanged |
| Test coverage | >90% for new code |
| Documentation | All new flags documented with examples |

---

## References

- Current MCP implementation: `orchestrator_auto/config.py`, `engine.py`
- Playwright MCP: `@playwright/mcp` npm package
- Figma MCP: `@anthropic/mcp-figma` npm package (requires token)
- MCP Safety Plan: `docs/plans/PLAN_mcp_safety_and_cleanup.md`
