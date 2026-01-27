# Implementation Plan: Watch TUI Layout v2 (Option A)

**Status:** Draft (Revised)
**Created:** 2026-01-27
**Revised:** 2026-01-27
**Author:** Claude

## Revision Notes

This plan has been revised to address the following issues identified during review:

1. **CLI Integration**: Corrected to target `orchestrator watch` command (not `start --watch`)
2. **Keybinding Conflicts**: Changed agent toggle keys to avoid conflicts with existing bindings
3. **Test Strategy**: Aligned with existing sync instantiation test patterns

---

## Overview

Transform the Watch TUI from a 3-column layout with dual agent panels to a condensed 2-column layout with a single toggleable agent view. Design for future `--verbose` flag compatibility.

## Current Layout Issues

1. **Left sidebar is cramped** - 5 sections (Watch, Status, Files, Git, Milestones) compete for space
2. **Agent panels are too narrow** - Code/output is hard to read with 50% width each
3. **Information hierarchy unclear** - Equal visual weight to everything
4. **Log panel underutilized** - Could show more context

## Existing Keybinding Constraints

**Current WATCH_BINDINGS (must not conflict):**
| Key | Action | Description |
|-----|--------|-------------|
| `p` | `toggle_pause` | Pause/resume polling |
| `tab` | `focus_next` | Navigate to next panel |
| `shift+tab` | `focus_prev` | Navigate to previous panel |
| `j` / `k` | `scroll_down` / `scroll_up` | Scroll focused panel |
| `1` / `2` / `3` | Log filter levels | Filter log messages |
| `r` | `respond` | Respond to blocker |
| `R` | `refresh` | Refresh display |
| `c` | `clear` | Clear file list |
| `g` | `show_git_diff` | Show git diff |
| `y` | `copy_session_id` | Copy session ID |
| `b` | `show_blocker` | Show blocker details |

---

## Target Layout (Option A)

```
+---------------------------------------------------------------------------------+
|  Orchestrator Auto - Watch Mode - project-name (branch)                         |
+------------------+--------------------------------------------------------------+
| > CURRENT FILE   |  AGENT OUTPUT                                    [<] [>]     |
| PLAN_fix_p2p...  +--------------------------------------------------------------+
| Milestone: 4/6   |                                                              |
| Phase: EXECUTION |  [PLANNER] or [EXECUTOR] content here                        |
|                  |                                                              |
| ---------------- |  Much wider - full code readability                          |
| STATS            |                                                              |
| Tokens: 85.0K    |  except ValidationError:  # RE-RAISES (critical fix)         |
| Cost:   $14.11   |      raise                                                   |
| Time:   03:33:13 |                                                              |
| API:    34 calls |  Propagates to view -> HTTP 403                              |
|                  |                                                              |
| ---------------- |  ...                                                         |
| QUEUE            |                                                              |
| v 5  x 0  || 1   |                                                              |
|                  |                                                              |
| > PLAN_fix_p2p.. |                                                              |
| v PLAN_fix_dis.. |                                                              |
| v PLAN_fix_dis.. |                                                              |
|                  |                                                              |
| ---------------- |                                                              |
| MILESTONES       |                                                              |
| v1 v2 v3 >4 o5 o6|                                                              |
+------------------+--------------------------------------------------------------+
| 21:43:44 > M4/6 | Executor implementing... | Press ? for help                   |
+---------------------------------------------------------------------------------+
```

**Key changes:**
- Single wide agent panel with `[` / `]` toggle (press `[` for planner, `]` for executor)
- Condensed left sidebar (~18 chars wide)
- Milestone progress as compact icons
- Single-line log/status bar at bottom

---

## Architecture: Verbose Mode Compatibility

```
                    DEFAULT (Compact)              --verbose (Expanded)
                    -----------------              ---------------------
Left Sidebar:       18 chars, condensed            25 chars, full details
Agent Panel:        Single view + toggle           Side-by-side (current)
Milestones:         Icon row (v > o)               Full list with names
Git Status:         Hidden                         Visible panel
Log Panel:          1-line status bar              8-line panel
```

---

## Phase 1: New Compact Widgets

### 1.1 Create `CompactSidebar` widget

**File:** `tui/widgets/compact_sidebar.py` (new)

Combines Watch + Status + Queue into a single 18-char panel:

```
+------------------+
| > PLAN_fix_p2p.. |  <- Current file (truncated)
| M4/6 . EXECUTION |  <- Milestone/Phase combined
|                  |
| --- STATS ------ |
| 85.0K . $14.11   |  <- Tokens + Cost
| 03:33 . 34 calls |  <- Time + API calls
|                  |
| --- QUEUE ------ |
| v5  x0  ||1      |  <- Compact counts
|                  |
| > PLAN_fix_p2p.. |  <- File list
| v PLAN_fix_dis.. |
| v PLAN_fix_dis.. |
|                  |
| - MILESTONES --- |
| v1 v2 v3 >4 o5 o6|  <- Compact icon row
+------------------+
```

**Key methods:**

```python
class CompactSidebar(Static):
    """Condensed sidebar combining watch, status, queue, and milestones."""

    def update_current_file(self, filename: str, milestone: int, total: int, phase: str) -> None:
        """Update current file and progress display."""

    def update_stats(self, tokens: int, cost: float, elapsed: str, api_calls: int) -> None:
        """Update statistics section."""

    def update_queue_counts(self, completed: int, failed: int, paused: int) -> None:
        """Update queue status counts."""

    def update_milestones(self, milestones: list, current: int) -> None:
        """Update milestone icon row."""

    def add_file(self, filename: str, status: str) -> None:
        """Add file to the file list."""

    def update_file(self, filename: str, status: str) -> None:
        """Update file status in the list."""
```

### 1.2 Create `CompactMilestoneRow` widget

**File:** `tui/widgets/compact_milestone_row.py` (new)

Single-row milestone display using icons:

```python
class CompactMilestoneRow(Static):
    """
    Single-row milestone display: v1 v2 v3 >4 o5 o6

    Compact representation of milestone progress using icons.
    Wraps to multiple rows if more than 6 milestones.
    """

    ICONS = {
        "completed": "v",   # checkmark
        "active": ">",      # arrow
        "pending": "o",     # circle
        "failed": "x",      # x mark
    }

    def set_milestones(self, milestones: list, current: int) -> None:
        """
        Update milestone display.

        Args:
            milestones: List of milestone dicts with 'id', 'title', 'status'
            current: Current milestone number (1-indexed)
        """

    def _format_row(self) -> str:
        """Format milestones as icon row: v1 v2 >3 o4"""
```

### 1.3 Create `AgentTogglePanel` widget

**File:** `tui/widgets/agent_toggle_panel.py` (new)

Single agent view with header showing toggle state:

```
+-------------------------------------------------------------+
| AGENT OUTPUT                                    [<] [>]     |  <- Toggle indicator
+-------------------------------------------------------------+
|                                                             |
|  except ValidationError: raise  # RE-RAISES                 |
|      v                                                      |
|  Propagates to view -> HTTP 403                             |
|                                                             |
+-------------------------------------------------------------+
```

**Key implementation:**

```python
class AgentTogglePanel(Vertical):
    """
    Single agent output panel with toggle between planner and executor.

    Buffers output from both agents but only displays the active one.
    Press '[' for planner, ']' for executor.
    """

    DEFAULT_CSS = """
    AgentTogglePanel {
        border: solid $secondary;
        height: 1fr;
    }

    AgentTogglePanel .toggle-header {
        dock: top;
        height: 1;
        background: $secondary;
    }

    AgentTogglePanel .toggle-indicator {
        dock: right;
        width: auto;
    }

    AgentTogglePanel.planner-active .toggle-planner {
        background: #00d7ff;
        color: black;
    }

    AgentTogglePanel.executor-active .toggle-executor {
        background: #00ff00;
        color: black;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._active_agent = "executor"  # Default to executor
        self._planner_buffer: list[str] = []
        self._executor_buffer: list[str] = []

    def toggle_agent(self) -> None:
        """Switch between planner and executor view."""

    def set_agent(self, agent: str) -> None:
        """Set specific agent view ('planner' or 'executor')."""

    def write_chunk(self, chunk: str, agent: str) -> None:
        """
        Buffer chunk and display if from active agent.

        Both agents' output is buffered so switching shows full history.
        """

    def get_active_agent(self) -> str:
        """Return currently active agent name."""

    def clear_buffers(self) -> None:
        """Clear both agent buffers (for new session)."""
```

### 1.4 Create `StatusBar` widget

**File:** `tui/widgets/status_bar.py` (new)

Single-line footer replacing LogPanel in compact mode:

```
| 21:43:44 > M4/6 | Executor implementing... | Press ? for help    |
```

**Key implementation:**

```python
class StatusBar(Static):
    """
    Single-line status bar showing current activity.

    Displays: timestamp | milestone | current activity | hint
    """

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $surface;
        color: $text-muted;
    }

    StatusBar .status-time {
        width: 10;
    }

    StatusBar .status-milestone {
        width: 8;
    }

    StatusBar .status-activity {
        width: 1fr;
    }

    StatusBar .status-hint {
        width: auto;
        dock: right;
    }
    """

    def set_milestone(self, current: int, total: int, name: str = "") -> None:
        """Update milestone display."""

    def set_activity(self, message: str) -> None:
        """Set current activity message (truncated if needed)."""

    def log(self, message: str, level: str = "info") -> None:
        """
        Log message to status bar.

        Shows most recent message. For verbose mode, use LogPanel instead.
        """
```

---

## Phase 2: Modify `WatchTUI` for Layout Modes

### 2.1 Add `verbose` parameter

**File:** `tui/watch_app.py`

```python
class WatchTUI(App):

    def __init__(
        self,
        plans_dir: str,
        verbose: bool = False,  # NEW PARAMETER
        db_path: Optional[str] = None,
        poll_interval: int = 2,
        auto_convert: bool = False,
        planner_model: Optional[str] = None,
        executor_model: Optional[str] = None,
        # ... rest of existing params ...
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.verbose = verbose
        # ... rest of init ...
```

### 2.2 Create two CSS layouts

```python
CSS_COMPACT = """
/* Compact layout (default) */
#main-row {
    width: 100%;
    height: 1fr;
}

#sidebar {
    width: 18;
    min-width: 18;
    max-width: 18;
    height: 100%;
    border: solid $secondary;
}

#agent-panel {
    width: 1fr;
    height: 100%;
}

#status-bar {
    dock: bottom;
    height: 1;
}

/* Hide verbose-only elements */
#left-col, #middle-col, #log-panel {
    display: none;
}
"""

CSS_VERBOSE = """
/* Verbose layout - existing CSS from current implementation */
#main-row {
    width: 100%;
    height: 1fr;
}

#left-col {
    width: 1fr;
    min-width: 20;
    max-width: 25;
    height: 100%;
}

/* ... rest of existing CSS ... */

/* Hide compact-only elements */
#sidebar, #agent-panel, #status-bar {
    display: none;
}
"""
```

### 2.3 Conditional `compose()` method

```python
def compose(self) -> ComposeResult:
    yield Header()

    if self.verbose:
        # Verbose layout (current behavior)
        with Horizontal(id="main-row"):
            with Vertical(id="left-col"):
                yield WatchPanel(id="watch-panel")
                yield MilestoneList(id="milestone-list")
            with Vertical(id="middle-col"):
                yield StatusPanel(id="status-panel")
                yield GitStatusPanel(id="git-panel")
            with Vertical(id="right-col"):
                with Horizontal(id="output-row"):
                    yield AgentOutput(
                        id="planner-output",
                        agent_filter="planner",
                        header_title="PLANNER"
                    )
                    yield AgentOutput(
                        id="executor-output",
                        agent_filter="executor",
                        header_title="EXECUTOR"
                    )
                yield LogPanel(id="log-panel")
    else:
        # Compact layout (Option A - new default)
        with Horizontal(id="main-row"):
            yield CompactSidebar(id="sidebar")
            yield AgentTogglePanel(id="agent-panel")
        yield StatusBar(id="status-bar")

    yield Footer()
```

### 2.4 Add keybindings for agent toggle

**File:** `tui/bindings.py`

**IMPORTANT:** Avoid conflicts with existing bindings. Use `[` and `]` for agent toggle.

```python
# Add to WATCH_BINDINGS (append, do not replace existing)
WATCH_BINDINGS = [
    # ... existing bindings (DO NOT MODIFY) ...
    Binding("r", "respond", "Respond"),
    Binding("R", "refresh", "Refresh"),
    Binding("c", "clear", "Clear"),
    Binding("g", "show_git_diff", "Git Diff"),
    Binding("y", "copy_session_id", "Copy ID"),
    Binding("b", "show_blocker", "Blocker"),
    Binding("tab", "focus_next", "Next Panel", show=False),
    Binding("shift+tab", "focus_prev", "Prev Panel", show=False),
    Binding("j", "scroll_down", "Scroll Down", show=False),
    Binding("k", "scroll_up", "Scroll Up", show=False),
    Binding("1", "filter_errors", "Errors", show=False),
    Binding("2", "filter_warnings", "Warnings", show=False),
    Binding("3", "filter_all", "All Logs", show=False),
    Binding("p", "toggle_pause", "Pause"),
    # NEW: Agent toggle bindings (compact mode only)
    Binding("[", "show_planner", "Planner", show=True),
    Binding("]", "show_executor", "Executor", show=True),
]
```

**File:** `tui/watch_app.py` (add action methods)

```python
def action_show_planner(self) -> None:
    """Show planner output (compact mode only)."""
    if not self.verbose:
        try:
            self.query_one("#agent-panel", AgentTogglePanel).set_agent("planner")
        except Exception:
            pass  # Verbose mode - no agent-panel

def action_show_executor(self) -> None:
    """Show executor output (compact mode only)."""
    if not self.verbose:
        try:
            self.query_one("#agent-panel", AgentTogglePanel).set_agent("executor")
        except Exception:
            pass  # Verbose mode - no agent-panel
```

### 2.5 Message handlers for both modes

```python
def on_chunk_received(self, message: messages.ChunkReceived) -> None:
    """Handle chunk received from agent."""
    try:
        if self.verbose:
            # Verbose mode - write to filtered panels (existing behavior)
            planner_output = self.query_one("#planner-output", AgentOutput)
            planner_output.write_chunk(message.chunk, message.agent)

            executor_output = self.query_one("#executor-output", AgentOutput)
            executor_output.write_chunk(message.chunk, message.agent)
        else:
            # Compact mode - write to toggle panel
            agent_panel = self.query_one("#agent-panel", AgentTogglePanel)
            agent_panel.write_chunk(message.chunk, message.agent)
    except Exception:
        pass

def on_state_changed(self, message: messages.StateChanged) -> None:
    """Handle state change."""
    state = message.state

    if self.verbose:
        # Existing verbose mode handling
        status_panel = self.query_one("#status-panel", StatusPanel)
        # ... existing code ...
    else:
        # Compact mode handling
        sidebar = self.query_one("#sidebar", CompactSidebar)
        status_bar = self.query_one("#status-bar", StatusBar)

        phase = getattr(state, 'phase', '-')
        current = getattr(state, 'current_milestone', 0)
        total = getattr(state, 'total_milestones', 0)

        sidebar.update_current_file(
            self._current_processing_file or "-",
            current, total, phase
        )
        status_bar.set_milestone(current, total)
```

---

## Phase 3: CLI Integration

**CORRECTED:** The watch entrypoint is `orchestrator watch PLANS_DIR`, not `orchestrator start --watch`.

### 3.1 Add `--verbose` flag to the `watch` command

**File:** `cli.py`

Locate the existing `watch` command and add the `--verbose` option:

```python
@cli.command()
@click.argument('plans_dir', type=click.Path(exists=True, file_okay=False))
@click.option('--poll-interval', default=2, type=int, help='Poll interval in seconds (default: 2)')
@click.option('--convert/--no-convert', 'auto_convert', default=False, help='Auto-convert invalid plans')
@click.option('--db-path', '-d', help='Custom database path')
@click.option('--planner-model', '-pm', help='Model for planner agent')
@click.option('--executor-model', '-em', help='Model for executor agent')
@click.option('--auto-commit', is_flag=True, help='Auto-commit changes after completion')
@click.option('--smart-commit/--no-smart-commit', default=None, help='Use AI-generated commit messages')
@click.option('--telegram/--no-telegram', default=None, help='Enable Telegram notifications')
@click.option('--mcp-config', type=click.Path(exists=True), help='Path to MCP configuration file')
@click.option('--headless', is_flag=True, default=False, help='Run Playwright MCP browser in headless mode')
@click.option('--tui/--no-tui', default=False, help='Launch Textual TUI dashboard')
@click.option('--verbose', '-v', is_flag=True, default=False,
              help='Use expanded TUI layout with both agent panels (default: compact)')  # NEW
def watch(
    plans_dir: str,
    poll_interval: int,
    auto_convert: bool,
    db_path: Optional[str],
    planner_model: Optional[str],
    executor_model: Optional[str],
    auto_commit: bool,
    smart_commit: Optional[bool],
    telegram: Optional[bool],
    mcp_config: Optional[str],
    headless: bool,
    tui: bool,
    verbose: bool,  # NEW PARAMETER
):
    """Watch a directory for plan files and process them."""
    # ... existing code ...

    if tui:
        _start_watch_tui(
            plans_dir=plans_dir,
            verbose=verbose,  # PASS TO TUI
            poll_interval=poll_interval,
            auto_convert=auto_convert,
            db_path=db_path,
            planner_model=planner_model,
            executor_model=executor_model,
            auto_commit=auto_commit,
            smart_commit=smart_commit,
            telegram=telegram,
            mcp_config=mcp_config,
            headless=headless,
        )
    else:
        # CLI mode (unchanged) - verbose flag ignored in non-TUI mode
        ...
```

### 3.2 Update `_start_watch_tui` function

**File:** `cli.py`

```python
def _start_watch_tui(
    plans_dir: str,
    verbose: bool = False,  # NEW PARAMETER
    poll_interval: int = 2,
    auto_convert: bool = False,
    db_path: Optional[str] = None,
    planner_model: Optional[str] = None,
    executor_model: Optional[str] = None,
    auto_commit: bool = False,
    smart_commit: Optional[bool] = None,
    telegram: Optional[bool] = None,
    mcp_config: Optional[str] = None,
    headless: bool = False,
) -> None:
    """Start watch mode with TUI dashboard."""
    try:
        from .tui import get_watch_app_class, check_textual_available
        check_textual_available()
    except ImportError as e:
        click.secho(f"TUI requires textual: {e}", fg="red")
        sys.exit(1)

    WatchTUI = get_watch_app_class()
    app = WatchTUI(
        plans_dir=plans_dir,
        verbose=verbose,  # PASS TO APP
        db_path=db_path,
        poll_interval=poll_interval,
        auto_convert=auto_convert,
        planner_model=planner_model,
        executor_model=executor_model,
        auto_commit=auto_commit,
        smart_commit=smart_commit,
        telegram=telegram,
        mcp_config=mcp_config,
        headless=headless,
    )
    app.run()
```

### 3.3 Usage Examples

```bash
# Default: compact layout (new)
orchestrator watch ./plans --tui

# Verbose: expanded layout (current behavior)
orchestrator watch ./plans --tui --verbose
orchestrator watch ./plans --tui -v

# Combine with other options
orchestrator watch ./plans --tui -v --telegram --auto-commit
```

---

## Phase 4: Testing

**CORRECTED:** Match existing test patterns (sync instantiation, no async integration tests).

### 4.1 Unit tests for new widgets

**File:** `tests/test_tui_compact_widgets.py` (new)

Follow existing patterns from `tests/test_tui.py`:

```python
"""Tests for compact TUI widgets.

These tests verify that compact TUI widgets can be instantiated
and their basic functionality works correctly.
"""

import pytest

# Skip all tests if textual is not installed
pytest.importorskip("textual")


class TestCompactWidgetImports:
    """Test that compact widgets can be imported."""

    def test_import_compact_sidebar(self):
        """Test importing CompactSidebar."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar
        assert CompactSidebar is not None

    def test_import_compact_milestone_row(self):
        """Test importing CompactMilestoneRow."""
        from orchestrator_auto.tui.widgets.compact_milestone_row import CompactMilestoneRow
        assert CompactMilestoneRow is not None

    def test_import_agent_toggle_panel(self):
        """Test importing AgentTogglePanel."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel
        assert AgentTogglePanel is not None

    def test_import_status_bar(self):
        """Test importing StatusBar."""
        from orchestrator_auto.tui.widgets.status_bar import StatusBar
        assert StatusBar is not None


class TestCompactMilestoneRow:
    """Tests for CompactMilestoneRow widget."""

    def test_initialization(self):
        """Test CompactMilestoneRow initializes correctly."""
        from orchestrator_auto.tui.widgets.compact_milestone_row import CompactMilestoneRow

        row = CompactMilestoneRow()
        assert row is not None

    def test_icons_defined(self):
        """Test milestone icons are defined."""
        from orchestrator_auto.tui.widgets.compact_milestone_row import CompactMilestoneRow

        assert "completed" in CompactMilestoneRow.ICONS
        assert "active" in CompactMilestoneRow.ICONS
        assert "pending" in CompactMilestoneRow.ICONS
        assert "failed" in CompactMilestoneRow.ICONS

    def test_set_milestones(self):
        """Test set_milestones stores data correctly."""
        from orchestrator_auto.tui.widgets.compact_milestone_row import CompactMilestoneRow

        row = CompactMilestoneRow()
        milestones = [
            {"id": 1, "title": "Setup", "status": "completed"},
            {"id": 2, "title": "Implement", "status": "active"},
            {"id": 3, "title": "Test", "status": "pending"},
        ]
        row.set_milestones(milestones, current=2)
        # Verify internal state (implementation-dependent)


class TestAgentTogglePanel:
    """Tests for AgentTogglePanel widget."""

    def test_initialization(self):
        """Test AgentTogglePanel initializes correctly."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        assert panel is not None

    def test_default_agent_is_executor(self):
        """Test that executor is the default active agent."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        assert panel.get_active_agent() == "executor"

    def test_toggle_switches_agent(self):
        """Test that toggle switches between agents."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        assert panel.get_active_agent() == "executor"
        panel.toggle_agent()
        assert panel.get_active_agent() == "planner"
        panel.toggle_agent()
        assert panel.get_active_agent() == "executor"

    def test_set_agent_explicit(self):
        """Test setting agent explicitly."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        panel.set_agent("planner")
        assert panel.get_active_agent() == "planner"
        panel.set_agent("executor")
        assert panel.get_active_agent() == "executor"

    def test_set_agent_invalid_ignored(self):
        """Test that invalid agent names are ignored."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        panel.set_agent("invalid")
        # Should remain at default
        assert panel.get_active_agent() == "executor"

    def test_buffers_initialized_empty(self):
        """Test that buffers start empty."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        assert len(panel._planner_buffer) == 0
        assert len(panel._executor_buffer) == 0

    def test_write_chunk_buffers_planner(self):
        """Test that planner chunks are buffered."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        panel.write_chunk("planner output", "planner")
        assert len(panel._planner_buffer) > 0

    def test_write_chunk_buffers_executor(self):
        """Test that executor chunks are buffered."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        panel.write_chunk("executor output", "executor")
        assert len(panel._executor_buffer) > 0

    def test_clear_buffers(self):
        """Test that clear_buffers empties both buffers."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        panel.write_chunk("planner output", "planner")
        panel.write_chunk("executor output", "executor")
        panel.clear_buffers()
        assert len(panel._planner_buffer) == 0
        assert len(panel._executor_buffer) == 0


class TestStatusBar:
    """Tests for StatusBar widget."""

    def test_initialization(self):
        """Test StatusBar initializes correctly."""
        from orchestrator_auto.tui.widgets.status_bar import StatusBar

        bar = StatusBar()
        assert bar is not None

    def test_set_milestone(self):
        """Test set_milestone updates internal state."""
        from orchestrator_auto.tui.widgets.status_bar import StatusBar

        bar = StatusBar()
        bar.set_milestone(3, 5, "Implement Feature")
        # Verify internal state (implementation-dependent)

    def test_set_activity(self):
        """Test set_activity updates internal state."""
        from orchestrator_auto.tui.widgets.status_bar import StatusBar

        bar = StatusBar()
        bar.set_activity("Processing...")
        # Verify internal state (implementation-dependent)

    def test_log_stores_message(self):
        """Test log method stores message."""
        from orchestrator_auto.tui.widgets.status_bar import StatusBar

        bar = StatusBar()
        bar.log("Test message", "info")
        # Verify internal state (implementation-dependent)


class TestCompactSidebar:
    """Tests for CompactSidebar widget."""

    def test_initialization(self):
        """Test CompactSidebar initializes correctly."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        assert sidebar is not None

    def test_update_current_file(self):
        """Test update_current_file updates internal state."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        sidebar.update_current_file("PLAN_test.md", 2, 5, "EXECUTION")
        # Verify internal state (implementation-dependent)

    def test_update_stats(self):
        """Test update_stats updates internal state."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        sidebar.update_stats(tokens=50000, cost=5.50, elapsed="01:23:45", api_calls=15)
        # Verify internal state (implementation-dependent)

    def test_update_queue_counts(self):
        """Test update_queue_counts updates internal state."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        sidebar.update_queue_counts(completed=5, failed=1, paused=2)
        # Verify internal state (implementation-dependent)


class TestWatchTUIVerboseParameter:
    """Test WatchTUI verbose parameter."""

    def test_watch_tui_accepts_verbose_false(self, tmp_path):
        """Test WatchTUI can be initialized with verbose=False."""
        from orchestrator_auto.tui.watch_app import WatchTUI

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        app = WatchTUI(plans_dir=str(plans_dir), verbose=False)
        assert app.verbose is False

    def test_watch_tui_accepts_verbose_true(self, tmp_path):
        """Test WatchTUI can be initialized with verbose=True."""
        from orchestrator_auto.tui.watch_app import WatchTUI

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        app = WatchTUI(plans_dir=str(plans_dir), verbose=True)
        assert app.verbose is True

    def test_watch_tui_default_verbose_is_false(self, tmp_path):
        """Test WatchTUI defaults to verbose=False (compact mode)."""
        from orchestrator_auto.tui.watch_app import WatchTUI

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        app = WatchTUI(plans_dir=str(plans_dir))
        assert app.verbose is False


class TestAgentToggleBindings:
    """Test agent toggle keybindings."""

    def test_watch_bindings_include_bracket_keys(self):
        """Test watch bindings include '[' and ']' for agent toggle."""
        from orchestrator_auto.tui.bindings import WATCH_BINDINGS

        keys = [b.key for b in WATCH_BINDINGS]
        assert "[" in keys
        assert "]" in keys

    def test_bracket_bindings_have_correct_actions(self):
        """Test '[' and ']' bindings have correct actions."""
        from orchestrator_auto.tui.bindings import WATCH_BINDINGS

        left_bracket = next((b for b in WATCH_BINDINGS if b.key == "["), None)
        right_bracket = next((b for b in WATCH_BINDINGS if b.key == "]"), None)

        assert left_bracket is not None
        assert left_bracket.action == "show_planner"

        assert right_bracket is not None
        assert right_bracket.action == "show_executor"

    def test_existing_bindings_unchanged(self):
        """Test that existing bindings are not modified."""
        from orchestrator_auto.tui.bindings import WATCH_BINDINGS

        # Verify critical existing bindings still work
        p_binding = next((b for b in WATCH_BINDINGS if b.key == "p"), None)
        assert p_binding is not None
        assert p_binding.action == "toggle_pause"  # NOT "show_planner"

        tab_binding = next((b for b in WATCH_BINDINGS if b.key == "tab"), None)
        assert tab_binding is not None
        assert tab_binding.action == "focus_next"  # NOT "toggle_agent"
```

---

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `tui/widgets/compact_sidebar.py` | **Create** | Combined sidebar widget (18 chars) |
| `tui/widgets/compact_milestone_row.py` | **Create** | Icon-based milestone row |
| `tui/widgets/agent_toggle_panel.py` | **Create** | Toggleable single agent panel |
| `tui/widgets/status_bar.py` | **Create** | Single-line status footer |
| `tui/widgets/__init__.py` | **Modify** | Export new widgets |
| `tui/watch_app.py` | **Modify** | Add verbose param, dual compose() |
| `tui/bindings.py` | **Modify** | Add `[` / `]` bindings (append only) |
| `cli.py` | **Modify** | Add `--verbose` flag to `watch` command |
| `tests/test_tui_compact_widgets.py` | **Create** | Widget unit tests (sync pattern) |

---

## Execution Order

1. **Phase 1.2**: `CompactMilestoneRow` (dependency-free)
2. **Phase 1.4**: `StatusBar` (dependency-free)
3. **Phase 1.3**: `AgentTogglePanel` (depends on `AgentOutput` patterns)
4. **Phase 1.1**: `CompactSidebar` (depends on `CompactMilestoneRow`)
5. **Phase 2**: `WatchTUI` modifications
6. **Phase 3**: CLI integration (`watch` command)
7. **Phase 4**: Testing

---

## Future Enhancements (Post-MVP)

- **Responsive breakpoints**: Auto-switch to verbose on wide terminals (>160 cols)
- **Config file support**: `verbose: true` in `.claude_orchestrator/config.yaml`
- **Per-panel verbose**: `--verbose-git`, `--verbose-log` flags
- **Keyboard shortcut**: `v` to toggle verbose mode live during execution
- **Mouse support**: Click on `[<]`/`[>]` indicator to toggle

---

## Acceptance Criteria

- [ ] Default layout uses compact sidebar (18 chars)
- [ ] Single agent panel fills remaining width
- [ ] Press `[` shows planner output
- [ ] Press `]` shows executor output
- [ ] Both agent outputs are buffered (switching shows full history)
- [ ] Milestone progress shows as icon row (v1 v2 >3 o4)
- [ ] Status bar shows timestamp, milestone, activity
- [ ] `--verbose` flag restores current (expanded) layout
- [ ] Existing keybindings (`p` = pause, `tab` = focus) unchanged
- [ ] All existing functionality works in both modes
- [ ] Tests pass for new widgets (sync instantiation pattern)
