# Implementation Plan: Watch TUI Layout B (Sub-Agent Aware)

**Status:** DRAFT (v2 - updated after review)
**Version:** 1.3.0+
**Author:** Claude
**Date:** 2026-01-28

---

## Review Notes (v2)

This plan was updated to address feedback from code review:

| Feedback | Status | Resolution |
|----------|--------|------------|
| "Explore sub-agent infrastructure absent" | **Invalid** | `orchestrator_auto/explore.py` exists with full `ExploreSubAgent` implementation |
| "Validation pipeline not wired to WatchController" | **Valid** | Added prerequisite Milestone 0 to wire integration |
| "Log filter handlers not implemented" | **Invalid** | `LogPanel.set_filter_level()` exists at `log_panel.py:54`, actions at `watch_app.py:1375-1400` |
| "CSS theme divergence" | **Valid** | Updated CSS approach to extend existing `theme.tcss` |

---

## Overview

Implement a new verbose layout for `orchestrator watch <dir> --tui --verbose` that surfaces exploration and validation sub-agent activity alongside the main workflow.

### Target Layout

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Watch: ./plans (2s)                                    main +3 │ 14:32:15       │
├─────────────────────────────────────────────────────────────────────────────────┤
│ ▶ auth.md                                                                       │
│ ═══════════════════════════════════════░░░░░░░░░░░░░░░░░░░░░░░░░ M2/5 (40%)    │
├──────────────────┬──────────────────┬───────────────────────────────────────────┤
│ MILESTONES       │ SUB-AGENTS       │ EXECUTOR OUTPUT                           │
│ ──────────────────│ ──────────────────│                                           │
│ ✓ 1. Schema      │ ┌─ EXPLORE ─────┐│ ## Milestone 2: API Endpoints             │
│   └ 3 files      │ │ ✓ auth patterns││                                           │
│                  │ │ ✓ route conv. ││ Found existing auth patterns:             │
│ ▶ 2. API         │ │ ○ test fixtures││ - JWT middleware in middleware/auth.py   │
│   └ 2/4 tasks    │ └────────────────┘│ - User model in models/user.py           │
│                  │                  │                                           │
│ ○ 3. Validation  │ ┌─ VALIDATE ────┐│ Creating routes/users.py...               │
│ ○ 4. Tests       │ │ ⏳ pending    ││                                           │
│ ○ 5. Docs        │ │               ││ ```python                                 │
│                  │ │ Security   ○  ││ @router.post("/users")                    │
│ ──────────────────│ │ Performance○  ││ async def create_user(...):               │
│ QUEUE     ✓8 ✗1  │ │ API        ○  ││     ...                                   │
│ ──────────────────│ └────────────────┘│ ```                                       │
│ ○ feat1.md       │                  │                                           │
│ ○ feat2.md       │ STATS            │                                           │
│ ⏸ blocked.md     │ ──────────────────│                                           │
│                  │ 45K tok · $0.34 │                                           │
│                  │ 12 calls · 12:45│                                           │
├──────────────────┴──────────────────┴───────────────────────────────────────────┤
│ LOG ────────────────────────────────────────────────────────────────── [1][2][3]│
│ [14:32:10] Exploring: Find existing auth patterns...                            │
│ [14:32:08] Milestone 2 started                                                  │
│ [14:31:55] Milestone 1 approved ✓                                               │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Current State Analysis

### Existing Sub-Agent Infrastructure (v1.3.0)

The following sub-agent infrastructure is **already implemented**:

| Module | Status | Notes |
|--------|--------|-------|
| `orchestrator_auto/explore.py` | **Complete** | `ExploreSubAgent`, `ExplorationResult`, `_ExplorationAccumulator` |
| `orchestrator_auto/validation/pipeline.py` | **Complete** | `ValidationPipeline` with async execution |
| `orchestrator_auto/validation/security.py` | **Complete** | `SecurityValidator` for secrets/credentials |
| `orchestrator_auto/validation/performance.py` | **Complete** | `PerformanceValidator` for anti-patterns |
| `orchestrator_auto/validation/api.py` | **Complete** | `APIValidator` for endpoint consistency |

**Missing integration:** `WatchController` does not currently call `ExploreSubAgent` or `ValidationPipeline`. This is addressed in Milestone 0 (Prerequisite).

### Existing TUI Files

| File | Purpose | Changes Needed |
|------|---------|----------------|
| `tui/watch_app.py` | Main WatchTUI app | Add Layout B compose path, extend CSS |
| `tui/widgets/milestone_list.py` | Milestone display | Add task count support |
| `tui/widgets/log_panel.py` | Log output | Filter buttons already exist via `set_filter_level()` |
| `tui/widgets/status_panel.py` | Status display | Extract stats section |
| `controllers/watch_controller.py` | Watch orchestration | Wire sub-agent calls, emit events |
| `tui/styles/theme.tcss` | CSS theme | Extend with new component styles |

### New Files Required

| File | Purpose |
|------|---------|
| `tui/widgets/progress_bar.py` | Full-width milestone progress bar |
| `tui/widgets/subagent_panel.py` | Explore + Validate status panel |
| `tui/widgets/stats_panel.py` | Compact stats display (tokens, cost, time) |
| `tui/widgets/header_bar.py` | Single-line header with git + time |

---

## Component Specifications

### 1. HeaderBar Widget

**Purpose:** Compact single-line header replacing verbose header + git panel.

```
Watch: ./plans (2s)                                    main +3 │ 14:32:15
```

**Structure:**
```python
class HeaderBar(Static):
    """Single-line header with watch info, git status, and time."""

    def __init__(
        self,
        watch_dir: str,
        poll_interval: int = 2,
    ):
        ...

    def update_git(self, branch: str, changes: int) -> None:
        """Update git status display."""

    def update_time(self) -> None:
        """Update clock (called every second)."""
```

**CSS:**
```css
HeaderBar {
    height: 1;
    background: $surface;
    color: $text;
}
HeaderBar .watch-info { /* left-aligned */ }
HeaderBar .git-status { /* right-aligned, before time */ }
HeaderBar .clock { /* right-aligned, fixed width */ }
```

### 2. ProgressBar Widget

**Purpose:** Full-width progress bar with milestone chip indicators.

```
▶ auth.md
═══════════════════════════════════════░░░░░░░░░░░░░░░░░░░░░░░░░ M2/5 (40%)
✓Schema  ▶API  ○Valid  ○Test  ○Docs
```

**Structure:**
```python
class MilestoneProgressBar(Static):
    """Full-width progress bar with milestone chips."""

    def __init__(self):
        ...

    def update_progress(
        self,
        current_file: str,
        current_milestone: int,
        total_milestones: int,
        milestone_names: List[str],
        milestone_statuses: List[str],  # "completed", "active", "pending", "failed"
    ) -> None:
        """Update progress display."""
```

**Visual States:**
- `═` = completed portion (green)
- `░` = remaining portion (dim)
- Milestone chips: `✓` completed, `▶` active, `○` pending, `✗` failed

**CSS:**
```css
MilestoneProgressBar {
    height: 3;
    padding: 0 1;
}
MilestoneProgressBar .filename { color: $accent; }
MilestoneProgressBar .progress-text { color: $text-muted; }
MilestoneProgressBar .chip-completed { color: $success; }
MilestoneProgressBar .chip-active { color: $warning; }
MilestoneProgressBar .chip-pending { color: $text-muted; }
MilestoneProgressBar .chip-failed { color: $error; }
```

### 3. MilestoneList Widget (Enhanced)

**Purpose:** Milestone list with task counts per milestone.

```
MILESTONES
──────────────────
✓ 1. Schema
  └ 3 files

▶ 2. API
  └ 2/4 tasks

○ 3. Validation
○ 4. Tests
○ 5. Docs
```

**Changes to Existing:**
```python
@dataclass
class MilestoneInfo:
    number: int
    title: str
    status: str  # "completed", "active", "pending", "failed"
    task_count: Optional[int] = None      # NEW: total tasks
    tasks_completed: Optional[int] = None  # NEW: completed tasks
    files_changed: Optional[int] = None    # NEW: files modified
```

**New Methods:**
```python
def update_milestone_tasks(
    self,
    milestone_num: int,
    tasks_completed: int,
    tasks_total: int,
) -> None:
    """Update task progress for a milestone."""

def update_milestone_files(
    self,
    milestone_num: int,
    files_count: int,
) -> None:
    """Update files changed count for a milestone."""
```

### 4. SubAgentPanel Widget

**Purpose:** Display exploration and validation sub-agent status.

```
SUB-AGENTS
──────────────────
┌─ EXPLORE ─────┐
│ ✓ auth patterns│
│ ✓ route conv. │
│ ○ test fixtures│
└────────────────┘

┌─ VALIDATE ────┐
│ ⏳ pending    │
│               │
│ Security   ○  │
│ Performance○  │
│ API        ○  │
└────────────────┘
```

**Structure:**
```python
@dataclass
class ExplorationQuery:
    query: str
    status: str  # "pending", "running", "completed", "failed"

@dataclass
class ValidatorStatus:
    name: str
    status: str  # "pending", "running", "passed", "issues", "failed"
    issue_count: int = 0
    severity: Optional[str] = None  # "high", "medium", "low"

class SubAgentPanel(Static):
    """Panel showing exploration and validation sub-agent status."""

    def __init__(self):
        self.explore_queries: List[ExplorationQuery] = []
        self.validators: List[ValidatorStatus] = []
        self.explore_status: str = "idle"  # "idle", "running", "completed"
        self.validate_status: str = "idle"

    def set_explore_queries(self, queries: List[ExplorationQuery]) -> None:
        """Set exploration queries to display."""

    def update_explore_query(self, index: int, status: str) -> None:
        """Update status of a specific query."""

    def set_validators(self, validators: List[ValidatorStatus]) -> None:
        """Set validators to display."""

    def update_validator(self, name: str, status: str, issues: int = 0) -> None:
        """Update status of a specific validator."""

    def set_explore_status(self, status: str) -> None:
        """Set overall exploration status."""

    def set_validate_status(self, status: str) -> None:
        """Set overall validation status."""
```

**Visual States:**

Exploration:
- `○` pending query
- `◐` running query (animated)
- `✓` completed query
- `✗` failed query

Validation:
- `⏳ pending` = waiting for milestone completion
- `◐ running` = validation in progress
- `✓ passed` = no issues found
- `⚠ issues` = issues found (yellow)
- `✗ failed` = validation error

Validator line states:
- `Security   ○` = pending
- `Security   ◐` = running
- `Security   ✓` = passed (0 issues)
- `Security   2` = 2 issues found (colored by max severity)
- `Security   ✗` = error

**CSS:**
```css
SubAgentPanel {
    width: 100%;
    height: 100%;
}
SubAgentPanel .section-box {
    border: round $primary;
    margin-bottom: 1;
}
SubAgentPanel .section-title {
    background: $primary;
    color: $text;
}
SubAgentPanel .query-completed { color: $success; }
SubAgentPanel .query-running { color: $warning; }
SubAgentPanel .query-pending { color: $text-muted; }
SubAgentPanel .validator-passed { color: $success; }
SubAgentPanel .validator-issues { color: $warning; }
SubAgentPanel .validator-failed { color: $error; }
```

### 5. StatsPanel Widget

**Purpose:** Compact stats display.

```
STATS
──────────────────
45K tok · $0.34
12 calls · 12:45
```

**Structure:**
```python
class StatsPanel(Static):
    """Compact statistics display."""

    def update_stats(
        self,
        tokens: int,
        cost: float,
        api_calls: int,
        elapsed: str,  # "MM:SS" or "HH:MM:SS"
    ) -> None:
        """Update all stats."""
```

### 6. LogPanel Widget (Already Implemented)

**Purpose:** Log output with filter buttons.

```
LOG ────────────────────────────────────────────────────────────────── [1][2][3]
[14:32:10] Exploring: Find existing auth patterns...
[14:32:08] Milestone 2 started
[14:31:55] Milestone 1 approved ✓
```

**Already Implemented:**

The following filter functionality already exists in `log_panel.py`:
- `set_filter_level(level: int)` - Set filter level (1=errors, 2=warnings+, 3=info+)
- Filter indicator in border title

**Key Bindings (already wired in `watch_app.py:1375-1400`):**
- `1` = Filter to errors only (`action_filter_errors`)
- `2` = Filter to errors + warnings (`action_filter_warnings`)
- `3` = Filter to all (`action_filter_all`)

**Visual Enhancement Only:**
- Add `[1][2][3]` button indicators to title bar to show available keys

---

## Layout Structure

### Grid Definition

```python
def compose(self) -> ComposeResult:
    """Compose Layout B (Sub-Agent Aware)."""
    yield HeaderBar(
        watch_dir=self.watch_dir,
        poll_interval=self.poll_interval,
    )
    yield MilestoneProgressBar()

    with Horizontal(id="main-content"):
        # Left column: Milestones + Queue (width: 1fr, min 18)
        with Vertical(id="left-column"):
            yield MilestoneList(id="milestones")
            yield Horizontal(
                Static("QUEUE", classes="section-title"),
                Static("", id="queue-counts"),
                id="queue-header",
            )
            yield FileList(id="queue-files", max_items=6)

        # Middle column: Sub-Agents + Stats (width: 1fr, min 18)
        with Vertical(id="middle-column"):
            yield SubAgentPanel(id="subagents")
            yield StatsPanel(id="stats")

        # Right column: Executor Output (width: 3fr, min 40)
        yield AgentOutput(id="executor-output", title="EXECUTOR OUTPUT")

    yield LogPanel(id="log", show_filter_buttons=True)
```

### CSS Grid

```css
#main-content {
    height: 1fr;
}

#left-column {
    width: 1fr;
    min-width: 18;
    max-width: 25;
}

#middle-column {
    width: 1fr;
    min-width: 18;
    max-width: 25;
}

#executor-output {
    width: 3fr;
    min-width: 40;
}

LogPanel {
    height: 6;
    min-height: 4;
    max-height: 10;
}
```

---

## Data Flow

### Event Flow

```
WatchController
    │
    ├─► FILE_DETECTED ──────► Update queue files
    ├─► FILE_PROCESSING ────► Update progress bar, set active file
    ├─► FILE_COMPLETED ─────► Update queue counts, move to completed
    ├─► FILE_FAILED ────────► Update queue counts, show error
    │
    ├─► MILESTONE_STARTED ──► Update milestone list, progress bar
    ├─► MILESTONE_COMPLETED ► Update milestone list, progress bar
    │
    ├─► EXPLORE_STARTED ────► SubAgentPanel.set_explore_status("running")
    ├─► EXPLORE_QUERY ──────► SubAgentPanel.set_explore_queries(...)
    ├─► EXPLORE_QUERY_DONE ─► SubAgentPanel.update_explore_query(i, "completed")
    ├─► EXPLORE_COMPLETED ──► SubAgentPanel.set_explore_status("completed")
    │
    ├─► VALIDATE_STARTED ───► SubAgentPanel.set_validate_status("running")
    ├─► VALIDATOR_STARTED ──► SubAgentPanel.update_validator(name, "running")
    ├─► VALIDATOR_DONE ─────► SubAgentPanel.update_validator(name, status, issues)
    ├─► VALIDATE_COMPLETED ─► SubAgentPanel.set_validate_status("completed")
    │
    ├─► STATS_UPDATE ───────► StatsPanel.update_stats(...)
    ├─► GIT_UPDATE ─────────► HeaderBar.update_git(...)
    │
    └─► LOG_MESSAGE ────────► LogPanel.log(...)
```

### New WatchController Events

```python
class WatchEvent(Enum):
    # ... existing events ...

    # New sub-agent events
    EXPLORE_STARTED = "explore_started"
    EXPLORE_QUERY = "explore_query"
    EXPLORE_QUERY_DONE = "explore_query_done"
    EXPLORE_COMPLETED = "explore_completed"

    VALIDATE_STARTED = "validate_started"
    VALIDATOR_STARTED = "validator_started"
    VALIDATOR_DONE = "validator_done"
    VALIDATE_COMPLETED = "validate_completed"
```

### Event Payloads

```python
@dataclass
class ExploreQueryEvent:
    index: int
    query: str
    status: str  # "pending", "running", "completed", "failed"

@dataclass
class ValidatorEvent:
    name: str
    status: str  # "pending", "running", "passed", "issues", "failed"
    issue_count: int = 0
    high_count: int = 0
    medium_count: int = 0
```

---

## Integration with Sub-Agent Infrastructure

### Exploration Integration

When a milestone starts, if `--explore` is enabled:

1. `WatchController` calls `ExploreSubAgent.explore_multiple_async(queries)`
2. Emits `EXPLORE_STARTED` event
3. For each query:
   - Emits `EXPLORE_QUERY` with status="running"
   - On completion, emits `EXPLORE_QUERY_DONE`
4. Emits `EXPLORE_COMPLETED`

```python
# In WatchController._process_file()
if self.explore_enabled:
    queries = generate_exploration_queries(milestone_text)
    self._emit(WatchEvent.EXPLORE_STARTED)

    for i, query in enumerate(queries):
        self._emit(WatchEvent.EXPLORE_QUERY, ExploreQueryEvent(i, query, "pending"))

    results = await self.explore_agent.explore_multiple_async(queries)

    for i, result in enumerate(results):
        status = "completed" if result.is_success() else "failed"
        self._emit(WatchEvent.EXPLORE_QUERY_DONE, ExploreQueryEvent(i, queries[i], status))

    self._emit(WatchEvent.EXPLORE_COMPLETED)
```

### Validation Integration

When a milestone completes, if `--validate` is enabled:

1. `WatchController` calls `ValidationPipeline.run(changed_files, diff)`
2. Emits `VALIDATE_STARTED` event
3. For each validator:
   - Emits `VALIDATOR_STARTED` with name
   - On completion, emits `VALIDATOR_DONE` with results
4. Emits `VALIDATE_COMPLETED`

```python
# In WatchController._on_milestone_complete()
if self.validate_enabled:
    self._emit(WatchEvent.VALIDATE_STARTED)

    for validator in self.pipeline.validators:
        self._emit(WatchEvent.VALIDATOR_STARTED, ValidatorEvent(validator.name, "running"))

    report = await self.pipeline.run(changed_files, diff)

    for result in report.results:
        status = "passed" if result.high_count == 0 else "issues"
        if result.error:
            status = "failed"
        self._emit(WatchEvent.VALIDATOR_DONE, ValidatorEvent(
            result.validator_name,
            status,
            len(result.issues),
            result.high_count,
            result.medium_count,
        ))

    self._emit(WatchEvent.VALIDATE_COMPLETED)
```

---

## Implementation Milestones

### Milestone Dependency Graph

```
M0 (Prerequisite: WatchController Integration)
 │
 ├─► M1 (Core Widgets) ───► M4 (Layout B Integration)
 │                                    │
 ├─► M2 (SubAgentPanel) ──────────────┤
 │                                    │
 └─► M3 (Enhanced MilestoneList) ─────┤
                                      │
                                      ▼
                               M5 (Event Handlers)
                                      │
                                      ▼
                               M6 (Polish & Testing)
```

**Note:** M1, M2, M3 can be developed in parallel after M0 is complete.

---

### Milestone 0: WatchController Sub-Agent Integration (Prerequisite)

**Purpose:** Wire existing `ExploreSubAgent` and `ValidationPipeline` into `WatchController` before building UI widgets that depend on their events.

**Tasks:**
1. Add `--explore` and `--validate` CLI flags to `orchestrator watch`
2. Import `ExploreSubAgent` and `ValidationPipeline` in `WatchController`
3. Implement milestone boundary detection (see below)
4. Call `ExploreSubAgent.explore_multiple_async()` at milestone start (when `--explore` enabled)
5. Call `ValidationPipeline.run()` at milestone completion (when `--validate` enabled)
6. Add new `WatchEvent` enum values for sub-agent lifecycle
7. Emit events during exploration and validation phases

#### Milestone Boundary Detection

The `on_state_change` callback receives the full `WorkflowState` object on every state transition. To detect milestone boundaries:

```python
# In WatchController.__init__():
self._last_milestone = 0

# Create wrapper callback that intercepts milestone changes:
def _on_state_change_wrapper(state: WorkflowState) -> None:
    current = state.current_milestone

    # Detect milestone START (current increased)
    if current > self._last_milestone:
        # Trigger exploration BEFORE executor runs
        if self.explore_enabled:
            self._run_exploration(state)

    # Detect milestone COMPLETION (check phase == EXECUTION and status indicates approval)
    # Note: MILESTONE_APPROVED transitions keep phase=EXECUTION but increment milestone
    if current > self._last_milestone and self._last_milestone > 0:
        # Previous milestone just completed - run validation
        if self.validate_enabled:
            self._run_validation(self._last_milestone)

    self._last_milestone = current

    # Forward to original callback
    if self.on_state_change:
        self.on_state_change(state)
```

**Alternative approach:** Add explicit `on_milestone_start` and `on_milestone_complete` callbacks to `Orchestrator` class. This is cleaner but requires modifying `engine.py`.

#### Validation Inputs Acquisition

Use existing functions from `git.py`:

```python
from ..git import get_changed_files, get_full_diff
from pathlib import Path

def _run_validation(self, milestone_num: int) -> None:
    """Run validation pipeline after milestone completion."""
    # Get changed files as Path objects
    changed_file_strings = get_changed_files(str(self.plans_dir))
    changed_files = [Path(f) for f in changed_file_strings]

    # Get unified diff (staged + unstaged changes)
    diff = get_full_diff(str(self.plans_dir))

    # Build milestone context
    context = f"Milestone {milestone_num}"

    # Run pipeline
    self._emit(WatchEvent.VALIDATE_STARTED)
    report = await self.pipeline.run(changed_files, diff, context)
    # ... emit per-validator events ...
    self._emit(WatchEvent.VALIDATE_COMPLETED)
```

**Note on staged vs unstaged:** `get_full_diff()` returns `git diff HEAD` which includes both staged and unstaged changes. This captures all work done during the milestone. If validation should only cover staged changes, use `get_staged_diff()` instead.

#### Exploration Query Generation

Use existing `generate_exploration_queries()` from `explore.py`:

```python
from ..explore import ExploreSubAgent, generate_exploration_queries

def _run_exploration(self, state: WorkflowState) -> None:
    """Run exploration before milestone execution."""
    # Get milestone text from plan
    milestone_text = self._get_milestone_text(state.current_milestone)

    # Generate queries from milestone description
    queries = generate_exploration_queries(milestone_text)

    self._emit(WatchEvent.EXPLORE_STARTED)
    for i, query in enumerate(queries):
        self._emit(WatchEvent.EXPLORE_QUERY, {"index": i, "query": query, "status": "pending"})

    results = await self.explore_agent.explore_multiple_async(queries)
    # ... emit per-query completion events ...
    self._emit(WatchEvent.EXPLORE_COMPLETED)
```

**Acceptance Criteria:**
- `orchestrator watch ./plans --explore --validate` runs without error
- Exploration queries generated from milestone text via `generate_exploration_queries()`
- Validation runs on changed files via `git.get_changed_files()` + `git.get_full_diff()`
- Milestone boundaries detected via `on_state_change` callback wrapper
- Events emitted (verifiable via log panel)

**Files:**
- `cli.py` (add `--explore`, `--validate` flags)
- `controllers/watch_controller.py` (import sub-agents, add wrapper callback, implement `_run_exploration` and `_run_validation`)

**Why This is Prerequisite:**
The `SubAgentPanel` widget depends on receiving `EXPLORE_*` and `VALIDATE_*` events from `WatchController`. Without this wiring, the panel would remain empty.

---

### Milestone 1: Core Widgets (Foundation)

**Depends on:** Milestone 0

**Tasks:**
1. Create `HeaderBar` widget with watch info + git + clock
2. Create `MilestoneProgressBar` widget with chips
3. Create `StatsPanel` widget
4. Add visual `[1][2][3]` indicators to `LogPanel` title (filter logic already exists)

**Acceptance Criteria:**
- HeaderBar shows directory, poll interval, git status, time
- ProgressBar renders progress with milestone chips
- StatsPanel displays tokens, cost, calls, elapsed
- LogPanel shows filter key hints in title

**Files:**
- `tui/widgets/header_bar.py` (new)
- `tui/widgets/progress_bar.py` (new)
- `tui/widgets/stats_panel.py` (new)
- `tui/widgets/log_panel.py` (minor: add key hints to title)

### Milestone 2: SubAgentPanel Widget

**Depends on:** Milestone 0 (for event types)

**Tasks:**
1. Create `SubAgentPanel` widget structure
2. Implement exploration query display with status icons
3. Implement validator status display with issue counts
4. Add section box styling (rounded borders)

**Acceptance Criteria:**
- Explore section shows queries with ○/◐/✓/✗ status
- Validate section shows validators with status
- Issue counts displayed with severity coloring
- Sections have rounded borders with titles

**Files:**
- `tui/widgets/subagent_panel.py` (new)

### Milestone 3: Enhanced MilestoneList

**Depends on:** None (can be developed in parallel with M1, M2)

**Tasks:**
1. Add task count fields to `MilestoneInfo`
2. Implement task progress display (2/4 tasks)
3. Implement files changed display (3 files)
4. Update rendering to show sub-info

**Acceptance Criteria:**
- Milestones show task progress when available
- Completed milestones show files changed count
- Sub-info rendered with tree-style indent (└)

**Files:**
- `tui/widgets/milestone_list.py` (modify)

### Milestone 4: Layout B Integration

**Depends on:** Milestones 1, 2, 3

**Tasks:**
1. Add Layout B compose method to `WatchTUI`
2. Create CSS for 3-column layout
3. Wire up event handlers for new widgets
4. Add `--layout` flag or auto-detect based on `--verbose`

**Acceptance Criteria:**
- `--verbose` activates Layout B
- All panels receive and display data
- Responsive behavior (min-width constraints)
- Focus navigation works across panels

**Files:**
- `tui/watch_app.py` (modify)

### Milestone 5: Event Handlers and TUI Wiring

**Depends on:** Milestones 0-4

**Tasks:**
1. Add `WatchTUI` message handlers for `EXPLORE_*` and `VALIDATE_*` events
2. Wire `SubAgentPanel` updates to event callbacks
3. Add progress callbacks for real-time query status
4. Test full event flow from controller to UI

**Acceptance Criteria:**
- `SubAgentPanel` updates when explore queries start/complete
- `SubAgentPanel` updates when validators run
- Real-time status icons (○ → ◐ → ✓)
- Events include timing information

**Files:**
- `tui/watch_app.py` (add event handlers)
- `tui/messages.py` (add new message types)

### Milestone 6: Polish and Testing

**Depends on:** Milestones 4, 5

**Tasks:**
1. Add unit tests for new widgets
2. Add integration tests for Layout B
3. Performance optimization (debounce updates)
4. Documentation update

**Acceptance Criteria:**
- All new widgets have unit tests
- Layout B tested with mock data
- No flicker on rapid updates
- README updated with Layout B screenshots

**Files:**
- `tests/tui/test_header_bar.py` (new)
- `tests/tui/test_progress_bar.py` (new)
- `tests/tui/test_subagent_panel.py` (new)
- `tests/tui/test_stats_panel.py` (new)
- `README.md` (modify)

---

## CSS Theme

**Approach:** Extend existing `tui/styles/theme.tcss` rather than adding conflicting inline CSS in `watch_app.py`. The current codebase uses `CSS_PATH = "styles/theme.tcss"` with supplementary `CSS_VERBOSE` and `CSS_COMPACT` inline strings.

### Integration Strategy

1. Add new component styles to `theme.tcss` (not inline)
2. Use existing color variables from theme where possible
3. Layout-specific grid rules can remain inline (as `CSS_LAYOUT_B`)

### Color Variables (from existing theme)

```css
$primary: #7c3aed;      /* Purple - accent */
$success: #22c55e;      /* Green - completed/passed */
$warning: #eab308;      /* Yellow - active/running */
$error: #ef4444;        /* Red - failed/error */
$text: #f8fafc;         /* White - primary text */
$text-muted: #64748b;   /* Gray - secondary text */
$surface: #1e293b;      /* Dark - backgrounds */
$border: #334155;       /* Slate - borders */
```

### Component Styles

```css
/* Section titles */
.section-title {
    text-style: bold;
    color: $text;
    border-bottom: solid $border;
    padding-bottom: 1;
    margin-bottom: 1;
}

/* Status icons */
.status-completed { color: $success; }
.status-active { color: $warning; }
.status-pending { color: $text-muted; }
.status-failed { color: $error; }
.status-running { color: $warning; text-style: bold; }

/* Progress bar */
.progress-filled { color: $success; }
.progress-empty { color: $text-muted; }

/* Milestone chips */
.chip {
    padding: 0 1;
}
.chip-completed { background: $success 20%; color: $success; }
.chip-active { background: $warning 20%; color: $warning; }
.chip-pending { background: $text-muted 20%; color: $text-muted; }

/* Sub-agent boxes */
.subagent-box {
    border: round $border;
    padding: 0 1;
    margin-bottom: 1;
}
.subagent-box-title {
    background: $primary;
    color: $text;
    text-align: center;
}
```

---

## Key Bindings

| Key | Action | Scope |
|-----|--------|-------|
| `1` | Filter log: errors only | Global |
| `2` | Filter log: errors + warnings | Global |
| `3` | Filter log: all | Global |
| `p` | Pause/resume polling | Global |
| `Tab` | Focus next panel | Global |
| `Shift+Tab` | Focus previous panel | Global |
| `j` / `Down` | Scroll down | Focused panel |
| `k` / `Up` | Scroll up | Focused panel |
| `?` | Show help | Global |
| `q` | Quit | Global |
| `y` | Copy session ID | Global |

---

## Testing Strategy

### Unit Tests

```python
# test_header_bar.py
def test_header_bar_displays_watch_info():
    """HeaderBar shows directory and poll interval."""

def test_header_bar_updates_git_status():
    """HeaderBar updates git branch and change count."""

def test_header_bar_updates_clock():
    """HeaderBar clock updates every second."""

# test_progress_bar.py
def test_progress_bar_calculates_percentage():
    """ProgressBar shows correct percentage."""

def test_progress_bar_renders_milestone_chips():
    """ProgressBar shows chips with correct status icons."""

# test_subagent_panel.py
def test_subagent_panel_shows_explore_queries():
    """SubAgentPanel displays exploration queries."""

def test_subagent_panel_shows_validators():
    """SubAgentPanel displays validator status."""

def test_subagent_panel_updates_on_completion():
    """SubAgentPanel updates icons on query/validator completion."""
```

### Integration Tests

```python
# test_watch_layout_b.py
async def test_layout_b_renders_all_panels():
    """Layout B shows all expected panels."""

async def test_layout_b_receives_subagent_events():
    """Layout B updates SubAgentPanel on events."""

async def test_layout_b_progress_updates():
    """Layout B progress bar updates on milestone changes."""
```

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Milestone 0 delayed | UI work blocked | UI widgets can be developed with mock events; integration tested later |
| Sub-agent events not emitted | SubAgentPanel stays empty | Add fallback "Not enabled" state when flags not set |
| Terminal too narrow | Layout breaks | Min-width constraints, graceful degradation |
| Too many log updates | Performance issues | Debounce updates, virtualize log |
| Milestone data incomplete | Task counts missing | Show "—" for unknown counts |
| CSS conflicts with existing theme | Visual inconsistency | Extend `theme.tcss` instead of inline CSS |

---

## Dependencies

### External
- `textual>=0.80.0` (existing in `pyproject.toml`)

### Internal (already implemented in v1.3.0)
- `orchestrator_auto.explore` - `ExploreSubAgent`, `ExplorationResult`, `generate_exploration_queries()`
- `orchestrator_auto.validation.pipeline` - `ValidationPipeline`, `ValidationReport`
- `orchestrator_auto.validation.security` - `SecurityValidator`
- `orchestrator_auto.validation.performance` - `PerformanceValidator`
- `orchestrator_auto.validation.api` - `APIValidator`

### Not Yet Implemented (addressed in Milestone 0)
- `WatchController` integration with `ExploreSubAgent`
- `WatchController` integration with `ValidationPipeline`
- CLI flags `--explore` and `--validate` for `orchestrator watch`

---

## Open Questions

1. **Should Layout B replace verbose mode entirely or be a separate `--layout=subagent` flag?**
   - Recommendation: Replace verbose mode (simpler UX)

2. **Should we show planner output alongside executor, or toggle?**
   - Recommendation: Executor only in main panel, planner in log (keeps focus)

3. **How to handle sub-agents when `--explore`/`--validate` not enabled?**
   - Recommendation: Show SubAgentPanel with "Not enabled" message, or hide panel entirely

4. **Should progress bar be collapsible to save space?**
   - Recommendation: No, it's the primary progress indicator

5. **Should Milestone 0 be a separate PR before the UI work?**
   - Recommendation: Yes, keep backend integration separate from UI changes for easier review

---

## Approval

- [ ] Layout design approved
- [ ] Component specifications approved
- [ ] Implementation milestones approved
- [ ] CSS theme approved

**Approved by:** _______________
**Date:** _______________
