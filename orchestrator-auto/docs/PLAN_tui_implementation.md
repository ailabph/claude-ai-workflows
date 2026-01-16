# TUI Implementation Plan for orchestrator-auto

**Version:** 1.0
**Date:** 2026-01-16
**Status:** Planning

## Executive Summary

This document outlines the implementation plan for an elegant Text User Interface (TUI) for orchestrator-auto. The TUI will provide a professional, hacker-aesthetic dashboard for monitoring and controlling AI agent workflows with real-time streaming output, milestone tracking, logs, and system statistics.

---

## 1. Library Research and Recommendation

### 1.1 Library Comparison

| Library | Stars | Last Updated | Async Support | Rich Widgets | Learning Curve | Active Maintenance |
|---------|-------|--------------|---------------|--------------|----------------|-------------------|
| **Textual** | 24k+ | Weekly | Native async | Extensive | Medium | Excellent (Textualize team) |
| **Rich** | 48k+ | Weekly | Limited | Display only | Low | Excellent (same team) |
| **urwid** | 2.7k+ | Monthly | Via asyncio | Basic | High | Moderate |
| **blessed** | 1.2k+ | Bi-monthly | Manual | Minimal | Medium | Moderate |
| **Prompt Toolkit** | 9k+ | Monthly | Native async | Input-focused | Medium | Good |

### 1.2 Recommendation: Textual

**Primary Choice: Textual v0.80+**

Reasons:
1. **Native async/await** - Perfect for streaming agent responses
2. **CSS-like styling** - Easy to achieve the hacker aesthetic with dark themes and neon accents
3. **Rich widget library** - DataTable, Tree, Log, TextArea, ProgressBar, Footer, Header
4. **Same ecosystem as Rich** - Seamless integration with Rich formatting (already battle-tested)
5. **Active development** - Backed by Textualize, weekly releases, excellent documentation
6. **Terminal size handling** - Built-in responsive layout system with CSS grid/flexbox
7. **Modern Python** - Type hints, async-first design, Python 3.8+

**Secondary Integration: Rich**

Use Rich for:
- Console output formatting outside TUI (fallback mode)
- Markdown/syntax highlighting within Textual widgets
- Export functionality

### 1.3 Why Not Others

- **urwid**: Steeper learning curve, callback-based rather than async, dated API
- **blessed**: Too low-level, requires building everything from scratch
- **Prompt Toolkit**: Already in use for input, but not designed for full dashboards
- **Rich alone**: No interactive widgets, display-only

---

## 2. Current Codebase Analysis

### 2.1 Key Integration Points

```
orchestrator-auto/
  orchestrator_auto/
    cli.py           # Entry point, Click commands - TUI launch point
    engine.py        # Orchestrator class - main workflow loop
    output.py        # StreamingIndicator - replace with TUI widgets
    state.py         # StateMachine, WorkflowState - data source for TUI
    agents.py        # BaseAgent.send_message() - streaming callback integration
    db.py            # Session data - populate TUI panels
    todo.py          # Task execution - progress tracking
    input_handler.py # PasteAwareInput - integrate with TUI input
```

### 2.2 Current Output Flow

```
engine.py::Orchestrator
    |
    +---> on_output callback (print by default)
    |
    +---> StreamingIndicator.on_chunk() for activity
    |
    +---> db.log_message() for persistence
```

### 2.3 Key Data Structures

```python
# state.py - Primary state source
@dataclass
class WorkflowState:
    session_id: str
    phase: str           # discovery, planning, execution, completed, paused
    status: str          # active, paused, completed, failed
    current_milestone: int
    total_milestones: int
    plan_path: Optional[str]
    feature_description: Optional[str]

# db.py - Session data
{
    "id": str,
    "feature_description": str,
    "phase": str,
    "status": str,
    "current_milestone": int,
    "total_milestones": int,
    "planner_model": str,
    "executor_model": str,
    "created_at": str,
    "updated_at": str,
    "heartbeat_at": str,
}
```

---

## 3. TUI Design

### 3.1 Visual Layout (80x24 Minimum)

```
+==============================================================================+
|  ORCHESTRATOR-AUTO v0.13.0                    [Session: a1b2c3d4] [14:32:05] |
+==============================================================================+
|                                                                              |
| +-- STATUS ----------------+  +-- MILESTONES --------------------------+    |
| | Phase: EXECUTION         |  | [x] M1: Database schema setup          |    |
| | Status: ACTIVE           |  | [x] M2: API endpoints implementation   |    |
| | Feature: User auth       |  | [>] M3: Authentication middleware      |    |
| | Models: opus/sonnet      |  | [ ] M4: Testing and validation         |    |
| +---- STATS ---------------+  +----------------------------------------+    |
| | API Calls: 47            |                                               |
| | Tokens: 12,847           |                                               |
| | Elapsed: 00:08:23        |                                               |
| +--------------------------+                                               |
|                                                                              |
| +-- AGENT OUTPUT ---------------------------------------------------------+ |
| | > Executor implementing M3...                                           | |
| | > Writing auth middleware to src/middleware/auth.py                     | |
| | > Added JWT validation logic                                            | |
| | > Running tests: pytest tests/test_auth.py                              | |
| |   [streaming] ...checking token expiration...                           | |
| +-------------------------------------------------------------------------+ |
|                                                                              |
| +-- LOGS (tail) ----------------------------------------------------------+ |
| | [14:31:42] Planner approved M2                                          | |
| | [14:31:45] Starting M3: Authentication middleware                       | |
| | [14:32:01] Executor: Reading existing auth patterns                     | |
| +-------------------------------------------------------------------------+ |
|                                                                              |
+==============================================================================+
| [Q]uit  [P]ause  [R]esume  [L]ogs  [S]tatus  [?]Help        Status: RUNNING |
+==============================================================================+
```

### 3.2 Responsive Layouts

**Large Terminal (120+ cols)**
```
+============================================================================+
| Header                                                                      |
+============================================================================+
| Status Panel  | Milestones Panel | Agent Output (streaming)                |
| (20 cols)     | (30 cols)        | (remaining space)                       |
|               |                  |                                         |
|               |                  |                                         |
+---------------+------------------+-----------------------------------------+
| Logs Panel (full width, 6 lines)                                           |
+============================================================================+
| Footer                                                                      |
+============================================================================+
```

**Medium Terminal (80-119 cols)**
```
+====================================+
| Header                             |
+====================================+
| Status/Stats  | Agent Output       |
| (25 cols)     | (remaining)        |
+---------------+--------------------+
| Milestones (full width, collapsible)|
+------------------------------------+
| Logs (3-4 lines)                   |
+====================================+
| Footer                             |
+====================================+
```

**Small Terminal (80 cols, 24 lines)**
```
+================================+
| Header (compact)               |
+================================+
| Agent Output                   |
| (full width, scrolling)        |
|                                |
+--------------------------------+
| Status bar: M3/4 | 12k tokens  |
+================================+
| [Q]uit [P]ause [?]Help         |
+================================+
```

### 3.3 Color Scheme (Hacker Aesthetic)

```css
/* TUI CSS Theme - Matrix/Cyberpunk Style */

Screen {
    background: #0a0a0a;  /* Near black */
}

.header {
    background: #1a1a2e;  /* Dark blue-black */
    color: #00ff41;       /* Matrix green */
    text-style: bold;
}

.status-panel {
    border: tall #00ff41; /* Green border */
    background: #0d0d0d;
}

.phase-active {
    color: #00ff41;       /* Green - active */
}

.phase-paused {
    color: #ffcc00;       /* Amber - paused */
}

.phase-error {
    color: #ff0040;       /* Neon red - error */
}

.milestone-done {
    color: #00ff41;       /* Green checkmark */
}

.milestone-current {
    color: #00d4ff;       /* Cyan - in progress */
    text-style: bold;
}

.milestone-pending {
    color: #666666;       /* Gray - pending */
}

.agent-output {
    background: #0a0a0a;
    color: #e0e0e0;       /* Light gray text */
    border: round #00d4ff; /* Cyan border */
}

.streaming-text {
    color: #00d4ff;       /* Cyan for streaming */
}

.log-panel {
    background: #050505;
    color: #888888;       /* Muted gray */
    border: round #333333;
}

.log-timestamp {
    color: #666666;
}

.log-info {
    color: #00d4ff;
}

.log-warning {
    color: #ffcc00;
}

.log-error {
    color: #ff0040;
}

.footer {
    background: #1a1a2e;
    color: #00ff41;
}

.stats-value {
    color: #ff00ff;       /* Magenta for numbers */
}

.keybinding {
    color: #00ff41;
    text-style: bold;
}
```

---

## 4. Component Architecture

### 4.1 Module Structure

```
orchestrator_auto/
  tui/
    __init__.py           # TUI entry point, TUIApp class
    app.py                # Main Textual Application
    screens/
      __init__.py
      dashboard.py        # Main dashboard screen
      logs.py             # Full-screen logs viewer
      help.py             # Help/keybindings screen
      session_picker.py   # Session selection screen
    widgets/
      __init__.py
      status_panel.py     # Status/stats display
      milestone_list.py   # Milestone progress list
      agent_output.py     # Streaming agent output panel
      log_panel.py        # Log tail display
      progress_bar.py     # Custom progress indicators
      streaming_text.py   # Text with streaming animation
    styles/
      __init__.py
      theme.tcss          # Main theme CSS
      colors.py           # Color constants
    bindings.py           # Keyboard bindings
    events.py             # Custom event types
    state.py              # TUI state management (reactive)
```

### 4.2 Class Hierarchy

```
TextualApp (Textual base)
    |
    +-- OrchestratorTUI
            |
            +-- DashboardScreen (main)
            |       |
            |       +-- StatusPanel (Static widget)
            |       +-- MilestoneList (ListView)
            |       +-- AgentOutput (RichLog)
            |       +-- LogPanel (Log)
            |       +-- Footer (Static)
            |
            +-- LogsScreen (full logs)
            +-- HelpScreen (keybindings)
            +-- SessionPickerScreen (for resume)
```

### 4.3 Key Widget Specifications

#### StatusPanel
```python
class StatusPanel(Static):
    """Displays session status, phase, and statistics."""

    # Reactive attributes (auto-update on change)
    phase: reactive[str] = reactive("discovery")
    status: reactive[str] = reactive("active")
    feature: reactive[str] = reactive("")
    api_calls: reactive[int] = reactive(0)
    token_count: reactive[int] = reactive(0)
    elapsed: reactive[float] = reactive(0.0)

    def compose(self) -> ComposeResult:
        yield Static("Phase: ", classes="label")
        yield Static(self.phase, classes="phase-value")
        # ...
```

#### AgentOutput (Streaming)
```python
class AgentOutput(RichLog):
    """Real-time streaming agent output with auto-scroll."""

    def on_chunk(self, chunk: str) -> None:
        """Handle streaming chunk from agent."""
        # Update last line with streaming animation
        self.write(chunk, scroll_end=True)

    def on_message_complete(self) -> None:
        """Called when agent message is complete."""
        self.write("\n")
```

#### MilestoneList
```python
class MilestoneList(ListView):
    """Displays milestone progress with visual indicators."""

    milestones: reactive[list] = reactive([])
    current_milestone: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        for i, milestone in enumerate(self.milestones):
            status_icon = self._get_status_icon(i)
            yield ListItem(
                Static(f"{status_icon} M{i+1}: {milestone['name']}"),
                classes=self._get_classes(i)
            )
```

---

## 5. Integration Strategy

### 5.1 Engine Integration

The TUI will integrate with the engine through a new output adapter:

```python
# orchestrator_auto/tui/adapter.py

class TUIOutputAdapter:
    """Bridges Orchestrator output to TUI widgets."""

    def __init__(self, app: OrchestratorTUI):
        self.app = app
        self._token_count = 0
        self._api_calls = 0

    def on_output(self, message: str) -> None:
        """Handle orchestrator output messages."""
        self.app.post_message(AgentOutputMessage(message))

    def on_chunk(self, chunk: str) -> None:
        """Handle streaming chunks."""
        self._token_count += len(chunk.split())
        self.app.post_message(StreamingChunkMessage(chunk))
        self.app.update_stats(tokens=self._token_count)

    def on_state_change(self, state: WorkflowState) -> None:
        """Handle state transitions."""
        self.app.post_message(StateChangeMessage(state))
```

### 5.2 Modified Engine Initialization

```python
# In cli.py - TUI mode start

def start_with_tui(feature: str, **kwargs):
    """Start orchestrator with TUI dashboard."""
    from .tui import OrchestratorTUI, TUIOutputAdapter

    app = OrchestratorTUI()
    adapter = TUIOutputAdapter(app)

    # Create orchestrator with TUI callbacks
    orchestrator = Orchestrator(
        feature_description=feature,
        on_output=adapter.on_output,
        show_activity=False,  # TUI handles this
        **kwargs
    )

    # Run TUI with orchestrator in background worker
    app.set_orchestrator(orchestrator)
    app.run()
```

### 5.3 Async Integration Pattern

```python
# TUI runs in main thread, orchestrator in worker

class OrchestratorTUI(App):

    def on_mount(self) -> None:
        """Called when app is mounted."""
        if self.orchestrator:
            self.run_worker(self._run_orchestrator())

    async def _run_orchestrator(self) -> None:
        """Run orchestrator in background worker."""
        try:
            # This runs in a worker thread
            await asyncio.to_thread(self.orchestrator.start)
        except Exception as e:
            self.post_message(ErrorMessage(str(e)))
```

### 5.4 CLI Flag Integration

```python
# Add to cli.py

@cli.command()
@click.option('--tui/--no-tui', default=False, help='Launch TUI dashboard')
@click.option('--tui-mode', type=click.Choice(['full', 'compact', 'minimal']),
              default='full', help='TUI layout mode')
def start(feature, tui, tui_mode, **kwargs):
    if tui:
        start_with_tui(feature, mode=tui_mode, **kwargs)
    else:
        # Existing CLI behavior
        ...
```

---

## 6. Implementation Phases

### Phase 1: Foundation (Week 1)

**Milestone 1.1: Project Setup**
- Add Textual to dependencies in `pyproject.toml`
- Create `tui/` package structure
- Set up basic App class with dark theme
- Create initial CSS theme file

**Milestone 1.2: Static Dashboard**
- Implement Header widget with session info
- Implement Footer with keybindings display
- Create StatusPanel (static, no data binding yet)
- Create placeholder panels for Agent Output and Logs

**Deliverables:**
- TUI launches with `--tui` flag
- Static dark-themed dashboard displays
- Basic keyboard navigation (Q to quit)

### Phase 2: Data Integration (Week 2)

**Milestone 2.1: State Binding**
- Implement reactive state management
- Create TUIOutputAdapter class
- Bind StatusPanel to WorkflowState
- Implement MilestoneList widget

**Milestone 2.2: Engine Connection**
- Modify Orchestrator to accept TUI callbacks
- Implement worker pattern for background execution
- Wire up state change events
- Handle phase transitions visually

**Deliverables:**
- TUI updates in real-time as workflow progresses
- Milestone list shows current progress
- Phase/status display reflects actual state

### Phase 3: Streaming Output (Week 3)

**Milestone 3.1: Agent Output Panel**
- Implement AgentOutput widget with RichLog
- Create streaming text animation
- Handle agent message boundaries
- Implement auto-scroll with scroll-lock toggle

**Milestone 3.2: Log Panel**
- Implement LogPanel with timestamp formatting
- Add log level coloring
- Create log filtering options
- Link to full LogsScreen

**Deliverables:**
- Real-time streaming agent output visible
- Log panel shows recent activity
- Smooth scrolling and updates

### Phase 4: Interactivity (Week 4)

**Milestone 4.1: Keyboard Controls**
- Implement Pause/Resume functionality
- Add Help screen with keybindings
- Create session picker for resume mode
- Add input handling for user responses

**Milestone 4.2: User Input Integration**
- Handle discovery phase input in TUI
- Integrate paste support
- Handle blocker responses
- Implement command palette

**Deliverables:**
- Full keyboard control of workflow
- User can respond to blockers within TUI
- Help documentation accessible

### Phase 5: Polish and Responsive Design (Week 5)

**Milestone 5.1: Responsive Layouts**
- Implement layout breakpoints
- Create compact mode for small terminals
- Handle terminal resize events
- Optimize for 80x24 minimum

**Milestone 5.2: Visual Polish**
- Add subtle animations (pulse for streaming)
- Implement progress bar animations
- Add status transition effects
- Final theme adjustments

**Deliverables:**
- TUI works at any terminal size
- Professional visual appearance
- Smooth animations and transitions

### Phase 6: Advanced Features (Week 6)

**Milestone 6.1: Session Management**
- Session picker with filtering
- Session status overview
- Multi-session switching (future)

**Milestone 6.2: Export and Utilities**
- Export current view to file
- Screenshot capability (save to file)
- Integration with todo command

**Deliverables:**
- Complete TUI feature set
- Documentation and examples
- Performance optimization

---

## 7. Code Examples

### 7.1 Main Application

```python
# orchestrator_auto/tui/app.py

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer
from textual.containers import Container, Horizontal, Vertical

from .screens import DashboardScreen, LogsScreen, HelpScreen
from .widgets import StatusPanel, MilestoneList, AgentOutput, LogPanel
from .styles import THEME_CSS


class OrchestratorTUI(App):
    """Main TUI application for orchestrator-auto."""

    CSS = THEME_CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("p", "pause", "Pause"),
        Binding("r", "resume", "Resume"),
        Binding("l", "logs", "Full Logs"),
        Binding("?", "help", "Help"),
        Binding("s", "scroll_toggle", "Scroll Lock"),
    ]

    def __init__(self, orchestrator=None):
        super().__init__()
        self.orchestrator = orchestrator
        self._adapter = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Horizontal(
                Vertical(
                    StatusPanel(id="status"),
                    id="left-panel",
                ),
                Vertical(
                    MilestoneList(id="milestones"),
                    id="center-panel",
                ),
                Vertical(
                    AgentOutput(id="agent-output"),
                    id="right-panel",
                ),
                id="main-content",
            ),
            LogPanel(id="logs"),
            id="dashboard",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize and start orchestrator when mounted."""
        self.title = "ORCHESTRATOR-AUTO"
        self.sub_title = f"v{__version__}"

        if self.orchestrator:
            self._start_orchestrator()

    def _start_orchestrator(self) -> None:
        """Start orchestrator in background worker."""
        from .adapter import TUIOutputAdapter

        self._adapter = TUIOutputAdapter(self)
        self.orchestrator.on_output = self._adapter.on_output

        # Run in worker thread
        self.run_worker(self._run_orchestrator_async())

    async def _run_orchestrator_async(self) -> None:
        """Async wrapper for orchestrator execution."""
        import asyncio
        try:
            await asyncio.to_thread(self.orchestrator.start)
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_pause(self) -> None:
        """Pause the workflow."""
        # Implementation
        pass

    def action_resume(self) -> None:
        """Resume the workflow."""
        # Implementation
        pass

    def action_logs(self) -> None:
        """Switch to full logs screen."""
        self.push_screen(LogsScreen())

    def action_help(self) -> None:
        """Show help screen."""
        self.push_screen(HelpScreen())
```

### 7.2 Status Panel Widget

```python
# orchestrator_auto/tui/widgets/status_panel.py

from textual.widgets import Static
from textual.reactive import reactive
from textual.app import ComposeResult
from rich.text import Text
from rich.table import Table


class StatusPanel(Static):
    """Displays session status, phase, and statistics."""

    # Reactive properties - UI updates automatically when these change
    session_id: reactive[str] = reactive("")
    phase: reactive[str] = reactive("discovery")
    status: reactive[str] = reactive("active")
    feature: reactive[str] = reactive("")
    planner_model: reactive[str] = reactive("opus")
    executor_model: reactive[str] = reactive("sonnet")
    api_calls: reactive[int] = reactive(0)
    token_count: reactive[int] = reactive(0)
    elapsed_seconds: reactive[float] = reactive(0.0)

    def render(self) -> Table:
        """Render the status panel as a Rich Table."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Label", style="dim")
        table.add_column("Value")

        # Phase with color
        phase_style = self._get_phase_style()
        table.add_row("Phase:", Text(self.phase.upper(), style=phase_style))

        # Status with color
        status_style = self._get_status_style()
        table.add_row("Status:", Text(self.status.upper(), style=status_style))

        # Feature (truncated)
        feature_display = self.feature[:30] + "..." if len(self.feature) > 30 else self.feature
        table.add_row("Feature:", feature_display)

        # Models
        table.add_row("Models:", f"{self.planner_model}/{self.executor_model}")

        # Statistics section
        table.add_row("", "")  # Spacer
        table.add_row("API Calls:", Text(str(self.api_calls), style="magenta"))
        table.add_row("Tokens:", Text(f"{self.token_count:,}", style="magenta"))
        table.add_row("Elapsed:", self._format_elapsed())

        return table

    def _get_phase_style(self) -> str:
        """Get style for phase based on value."""
        styles = {
            "discovery": "cyan",
            "planning": "blue",
            "execution": "green bold",
            "completed": "green",
            "paused": "yellow",
        }
        return styles.get(self.phase, "white")

    def _get_status_style(self) -> str:
        """Get style for status based on value."""
        styles = {
            "active": "green bold",
            "paused": "yellow",
            "completed": "blue",
            "failed": "red bold",
        }
        return styles.get(self.status, "white")

    def _format_elapsed(self) -> str:
        """Format elapsed time as HH:MM:SS."""
        hours, remainder = divmod(int(self.elapsed_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
```

### 7.3 Agent Output Widget

```python
# orchestrator_auto/tui/widgets/agent_output.py

from textual.widgets import RichLog
from textual.reactive import reactive
from rich.text import Text


class AgentOutput(RichLog):
    """
    Real-time streaming agent output display.

    Features:
    - Auto-scroll to bottom (toggleable)
    - Streaming text with visual indicator
    - Agent message boundaries
    - Syntax highlighting for code blocks
    """

    auto_scroll: reactive[bool] = reactive(True)
    is_streaming: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    AgentOutput {
        background: #0a0a0a;
        border: round #00d4ff;
        padding: 0 1;
    }

    AgentOutput:focus {
        border: round #00ff41;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(highlight=True, markup=True, **kwargs)
        self._current_line = ""

    def write_chunk(self, chunk: str) -> None:
        """
        Write a streaming chunk from agent response.

        Chunks are accumulated until a newline, then written as a line.
        Shows streaming indicator while receiving chunks.
        """
        self.is_streaming = True
        self._current_line += chunk

        # Check for complete lines
        if "\n" in self._current_line:
            lines = self._current_line.split("\n")
            # Write all complete lines
            for line in lines[:-1]:
                self._write_line(line)
            # Keep the incomplete part
            self._current_line = lines[-1]

        # Update streaming indicator
        self._update_streaming_indicator()

    def finish_message(self) -> None:
        """Called when agent message is complete."""
        self.is_streaming = False

        # Write any remaining content
        if self._current_line:
            self._write_line(self._current_line)
            self._current_line = ""

        # Add visual separator
        self.write(Text("─" * 40, style="dim"))

    def _write_line(self, line: str) -> None:
        """Write a line with appropriate styling."""
        # Detect agent prefixes
        if line.startswith(">"):
            text = Text(line, style="green")
        elif line.startswith("!"):
            text = Text(line, style="yellow")
        elif line.startswith("ERROR"):
            text = Text(line, style="red bold")
        else:
            text = Text(line)

        self.write(text, scroll_end=self.auto_scroll)

    def _update_streaming_indicator(self) -> None:
        """Update visual streaming indicator."""
        if self.is_streaming:
            # Could add pulsing animation here
            pass

    def toggle_scroll(self) -> None:
        """Toggle auto-scroll behavior."""
        self.auto_scroll = not self.auto_scroll
        status = "ON" if self.auto_scroll else "OFF"
        self.notify(f"Auto-scroll: {status}")
```

### 7.4 Theme CSS

```css
/* orchestrator_auto/tui/styles/theme.tcss */

/* ============================================
   ORCHESTRATOR-AUTO TUI THEME
   Hacker/Cyberpunk Aesthetic
   ============================================ */

/* Base screen */
Screen {
    background: #0a0a0a;
}

/* Header */
Header {
    background: #1a1a2e;
    color: #00ff41;
    text-style: bold;
    dock: top;
    height: 1;
}

Header > .header--highlight {
    background: #1a1a2e;
    color: #00d4ff;
}

/* Footer */
Footer {
    background: #1a1a2e;
    color: #00ff41;
}

Footer > .footer--key {
    color: #00ff41;
    text-style: bold;
    background: #2a2a4e;
}

Footer > .footer--description {
    color: #888888;
}

/* Main container layout */
#dashboard {
    layout: grid;
    grid-size: 1;
    grid-rows: 1fr auto;
}

#main-content {
    layout: horizontal;
    height: 100%;
}

#left-panel {
    width: 25;
    min-width: 20;
    max-width: 30;
}

#center-panel {
    width: 35;
    min-width: 25;
}

#right-panel {
    width: 1fr;
    min-width: 40;
}

/* Status Panel */
#status {
    background: #0d0d0d;
    border: tall #00ff41;
    padding: 1;
    margin: 1;
}

/* Milestone List */
#milestones {
    background: #0d0d0d;
    border: tall #00d4ff;
    padding: 1;
    margin: 1;
}

.milestone-done {
    color: #00ff41;
}

.milestone-current {
    color: #00d4ff;
    text-style: bold;
}

.milestone-pending {
    color: #666666;
}

/* Agent Output */
#agent-output {
    background: #0a0a0a;
    border: round #00d4ff;
    padding: 0 1;
    margin: 1;
}

#agent-output:focus {
    border: round #00ff41;
}

/* Log Panel */
#logs {
    background: #050505;
    border: round #333333;
    height: 8;
    padding: 0 1;
    margin: 0 1 1 1;
}

.log-timestamp {
    color: #666666;
}

.log-info {
    color: #00d4ff;
}

.log-warning {
    color: #ffcc00;
}

.log-error {
    color: #ff0040;
    text-style: bold;
}

/* Statistics values */
.stat-value {
    color: #ff00ff;
    text-style: bold;
}

/* Scrollbars */
Scrollbar {
    background: #1a1a1a;
}

ScrollBar > .scrollbar--bar {
    background: #00ff41 30%;
}

ScrollBar > .scrollbar--bar-hover {
    background: #00ff41 50%;
}

/* Input styling */
Input {
    background: #0d0d0d;
    border: tall #00ff41;
    color: #e0e0e0;
}

Input:focus {
    border: tall #00d4ff;
}

/* Notifications */
Toast {
    background: #1a1a2e;
    border: round #00ff41;
    color: #e0e0e0;
}

/* Loading/Progress indicators */
LoadingIndicator {
    color: #00d4ff;
}

ProgressBar > .bar--bar {
    color: #00ff41;
}

ProgressBar > .bar--complete {
    color: #00ff41;
}
```

### 7.5 CLI Integration

```python
# Add to orchestrator_auto/cli.py

@cli.command()
@click.option('-f', '--feature', required=True, help='Feature description')
@click.option('--tui', is_flag=True, default=False, help='Launch TUI dashboard')
@click.option('--tui-mode', type=click.Choice(['full', 'compact', 'minimal']),
              default='full', help='TUI layout mode')
@click.option('--plan', 'plan_path', type=click.Path(exists=True),
              help='Path to existing plan file')
@click.option('-pm', '--planner-model', help='Planner model (opus, sonnet, haiku)')
@click.option('-em', '--executor-model', help='Executor model')
@click.option('--auto-commit', is_flag=True, help='Auto-commit on completion')
@click.option('--debug', is_flag=True, help='Enable debug logging')
@click.pass_context
def start(ctx, feature, tui, tui_mode, plan_path, planner_model,
          executor_model, auto_commit, debug):
    """Start a new orchestration workflow."""

    if tui:
        # Launch TUI mode
        _start_with_tui(
            feature=feature,
            plan_path=plan_path,
            planner_model=planner_model,
            executor_model=executor_model,
            auto_commit=auto_commit,
            debug=debug,
            mode=tui_mode,
        )
    else:
        # Existing CLI mode
        _start_cli_mode(ctx, feature, plan_path, planner_model,
                       executor_model, auto_commit, debug)


def _start_with_tui(feature: str, mode: str = 'full', **kwargs) -> None:
    """Start orchestrator with TUI dashboard."""
    try:
        from .tui import OrchestratorTUI
    except ImportError:
        click.secho("TUI requires textual. Install with: pip install textual", fg="red")
        sys.exit(1)

    # Resolve models
    planner_model = get_planner_model(kwargs.get('planner_model'))
    executor_model = get_executor_model(kwargs.get('executor_model'))

    # Create orchestrator (don't start yet - TUI will handle that)
    orchestrator = Orchestrator(
        feature_description=feature,
        plan_path=kwargs.get('plan_path'),
        planner_model=planner_model,
        executor_model=executor_model,
        show_activity=False,  # TUI handles activity display
        debug=kwargs.get('debug', False),
    )

    # Create and run TUI
    app = OrchestratorTUI(
        orchestrator=orchestrator,
        mode=mode,
    )
    app.run()
```

---

## 8. Testing Strategy

### 8.1 Unit Tests

```python
# tests/test_tui_widgets.py

import pytest
from orchestrator_auto.tui.widgets import StatusPanel, MilestoneList

class TestStatusPanel:
    def test_phase_style_mapping(self):
        panel = StatusPanel()
        panel.phase = "execution"
        assert panel._get_phase_style() == "green bold"

    def test_elapsed_format(self):
        panel = StatusPanel()
        panel.elapsed_seconds = 3661  # 1h 1m 1s
        assert panel._format_elapsed() == "01:01:01"

class TestMilestoneList:
    def test_milestone_status_icons(self):
        # Test done, current, pending icons
        pass
```

### 8.2 Integration Tests

```python
# tests/test_tui_integration.py

import pytest
from textual.pilot import Pilot
from orchestrator_auto.tui import OrchestratorTUI

@pytest.mark.asyncio
async def test_tui_startup():
    """Test TUI starts without errors."""
    app = OrchestratorTUI()
    async with app.run_test() as pilot:
        assert app.title == "ORCHESTRATOR-AUTO"

@pytest.mark.asyncio
async def test_quit_binding():
    """Test Q key quits the app."""
    app = OrchestratorTUI()
    async with app.run_test() as pilot:
        await pilot.press("q")
        assert app._exit
```

### 8.3 Visual Tests

Use Textual's snapshot testing for visual regression:

```python
# tests/test_tui_snapshots.py

from textual.testing import snapshot_test

@snapshot_test
async def test_dashboard_snapshot(app):
    """Snapshot test for dashboard layout."""
    async with app.run_test(size=(80, 24)) as pilot:
        # Snapshot captures the terminal state
        pass
```

---

## 9. Dependencies

### 9.1 New Dependencies

```toml
# Add to pyproject.toml

[project.optional-dependencies]
tui = [
    "textual>=0.80.0",
]
```

### 9.2 Updated Environment

```yaml
# Add to environment.yml
dependencies:
  - pip:
    - textual>=0.80.0
```

---

## 10. Future Enhancements

### 10.1 Phase 2 Features (Post-MVP)

- **Multi-session Dashboard**: Show multiple sessions in tabs
- **Watch Mode Integration**: TUI for `orchestrator watch` command
- **Todo Integration**: Task execution progress in TUI
- **Telegram Bridge**: Show Telegram notifications in TUI
- **Performance Graphs**: Token usage over time charts
- **Session Diff View**: Compare sessions side-by-side

### 10.2 Accessibility Considerations

- High contrast theme option
- Screen reader compatibility
- Reduced motion mode
- Keyboard-only navigation (no mouse required)

---

## 11. Success Metrics

1. **Performance**: TUI responds within 100ms to user input
2. **Memory**: <100MB additional memory usage
3. **Terminal Compatibility**: Works in iTerm2, Terminal.app, VS Code terminal, SSH
4. **Minimum Size**: Fully functional at 80x24
5. **User Satisfaction**: Professional appearance, intuitive controls

---

## 12. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Textual API changes | Medium | Pin version, test on updates |
| Performance with large logs | Medium | Implement log rotation/truncation |
| Terminal compatibility issues | Low | Test across major terminals |
| Async complexity | Medium | Clear patterns, comprehensive tests |
| Learning curve for users | Low | Excellent help system, fallback to CLI |

---

## Appendix A: File Structure After Implementation

```
orchestrator_auto/
    __init__.py
    cli.py                    # Modified: add --tui flag
    engine.py                 # Modified: callback hooks
    output.py                 # Unchanged (fallback)
    state.py                  # Unchanged
    agents.py                 # Minor: streaming callbacks
    db.py                     # Unchanged
    tui/
        __init__.py           # Package exports
        app.py                # Main OrchestratorTUI class
        adapter.py            # TUIOutputAdapter
        bindings.py           # Keyboard bindings
        events.py             # Custom message types
        screens/
            __init__.py
            dashboard.py      # Main dashboard
            logs.py           # Full logs screen
            help.py           # Help screen
            session_picker.py # Session selection
        widgets/
            __init__.py
            status_panel.py   # Status display
            milestone_list.py # Milestone progress
            agent_output.py   # Streaming output
            log_panel.py      # Log tail
            streaming_text.py # Animated text
        styles/
            __init__.py
            theme.tcss        # Main theme CSS
            colors.py         # Color constants
tests/
    test_tui_widgets.py
    test_tui_integration.py
    test_tui_snapshots.py
```

---

## Appendix B: Quick Start Example

```bash
# Install with TUI support
pip install -e ".[tui]"

# Start workflow with TUI
orchestrator start -f "Add user authentication" --tui

# Resume with TUI
orchestrator resume abc123 --tui

# TUI with custom layout
orchestrator start -f "Build API endpoints" --tui --tui-mode compact
```

---

**Document Author:** Claude (Backend Architect)
**Review Status:** Draft - Pending Human Review
