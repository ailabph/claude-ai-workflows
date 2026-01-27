# Proposal: Watch TUI Quality of Life Improvements

## Problem Statement

The `orchestrator watch --tui` provides a rich dashboard for monitoring plan execution, but several usability gaps make it difficult to:

1. **Know context** - What repo/branch am I in? What plan is being executed?
2. **Navigate content** - Can't scroll agent outputs or focus specific panels
3. **Control execution** - Can't pause polling while editing plans
4. **Access information** - Blocker questions truncated, session IDs require manual typing

## Current State

The Watch TUI (`tui/watch_app.py`) has:
- Watch panel (directory, counts)
- Status panel (phase, milestones, tokens)
- Git panel (basic status)
- Agent output panels (planner/executor)
- Log panel

**Missing:**
- Repo/branch prominently displayed
- Current plan filename visible
- Panel navigation/focus
- Scrollable outputs
- Pause/resume control

## Proposed Improvements

### Priority 1: Context Visibility

#### 1A. Repo & Branch Header
Add repo name and current branch to the header/subtitle area.

```
┌─────────────────────────────────────────────────────────────────┐
│ Orchestrator Auto - Watch Mode                                  │
│ 📁 my-project (main) | Watching: ./plans/                       │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation:**
- Detect repo name from `.git` or directory name
- Get current branch via `git rev-parse --abbrev-ref HEAD`
- Update `SUB_TITLE` dynamically or add a dedicated header widget

#### 1B. Current Plan Display
Show the currently processing plan filename prominently in the status panel.

```
┌─ STATUS ─────────────────────┐
│ Plan: feature-auth.md        │  ← NEW
│ Session: abc123...           │
│ Phase: EXECUTION (ACTIVE)    │
│ Milestone: 2/5               │
└──────────────────────────────┘
```

**Implementation:**
- Add `update_current_plan(filename)` to `StatusPanel`
- Call on `WatchEvent.FILE_FOUND`
- Clear on completion/failure/pause

### Priority 2: Panel Navigation

#### 2A. Focus Cycling (`Tab`)
Allow cycling focus between panels with visual border highlight.

```
Panels (in order): Watch → Status → Planner Output → Executor Output → Log
```

**Implementation:**
- Track `_focused_panel_index`
- `action_focus_next()` bound to `Tab`
- `action_focus_prev()` bound to `Shift+Tab`
- Focused panel gets `border: solid $accent;` style

#### 2B. Scroll Focused Panel (`j/k` or `↑/↓`)
Enable vertical scrolling in the focused panel.

**Implementation:**
- `AgentOutput` and `LogPanel` already use `RichLog` which supports scrolling
- Need to forward key events to focused widget
- Add `action_scroll_up()` / `action_scroll_down()`

#### 2C. Maximize Panel (`f`)
Toggle fullscreen mode for focused panel.

**Implementation:**
- Store original layout in `_layout_backup`
- Hide other panels, expand focused to `width: 100%; height: 100%;`
- `f` again restores layout
- Show `[f] Exit fullscreen` in footer when maximized

### Priority 3: Execution Control

#### 3A. Pause/Resume Polling (`p`)
Pause directory watching without quitting.

```
┌─ WATCH ──────────────────────┐
│ 📁 ./plans/                  │
│ ⏸ PAUSED (press p to resume) │  ← When paused
│ ✓ 3  ✗ 1  ⏸ 0               │
└──────────────────────────────┘
```

**Semantics (confirmed):** Pause **polling only** - stop detecting new files, but let any in-flight orchestrator execution complete. This is the low-complexity option that doesn't require `Orchestrator.pause()`.

**Implementation:**
- Add `_should_pause` flag to `WatchController` (pattern already exists with `_should_stop`)
- Add `pause()` / `resume()` methods
- `WatchPanel.set_polling_paused(True/False)`
- Useful when editing plan files mid-watch

#### 3B. Skip Current File (`s`) - DEFERRED

> **Status:** NO-GO for this proposal. Requires `Orchestrator.abort()` which doesn't exist.

Abort current processing and move to next file.

**Why deferred:**
- `Orchestrator` has no `abort()`, `cancel()`, or cancellation token pattern
- Would require cross-cutting changes: controller, orchestrator, lifecycle events
- File rename semantics (`*_skipped.md`) need careful state handling
- Partial outputs, DB state, and logs need cleanup logic

**Future work:** Design `Orchestrator.abort()` as a separate proposal, then revisit skip.

### Priority 4: Information Access

#### 4A. Copy Session ID (`y`)
Copy current/paused session ID to clipboard.

**Implementation:**
- Use Textual's built-in `App.copy_to_clipboard()` (available in v0.80.0+, we have `>=0.80.0`)
- Uses OSC 52 escape sequence - works in most terminals except macOS Terminal.app
- Flash confirmation in log panel: "Copied: abc12345"
- Works for both active and paused sessions

```python
def action_copy_session_id(self) -> None:
    session_id = self._current_session_id or self._paused_session_id
    if session_id:
        self.copy_to_clipboard(session_id)
        self._log_info(f"Copied: {session_id[:8]}...")
```

**Note:** No new dependency needed. If macOS Terminal.app support is required later, can add optional `pyperclip` fallback.

#### 4B. View Full Blocker (`b`)
Show complete blocker question in modal (currently truncated to 100 chars).

**Implementation:**
- New `BlockerModal` screen with full question text
- Scrollable if question is long
- "Respond" button that opens `InputModal`
- Shows: agent (planner/executor), timestamp, full question

#### 4C. Log Level Filter (`1/2/3`)
Filter log panel by severity.

```
1 = Errors only
2 = Errors + Warnings
3 = All (default)
```

**Implementation:**
- Add `set_filter_level(level)` to `LogPanel`
- Store `_min_level` and filter in `log()` method
- Show current filter in panel header: `LOG (errors only)`

### Priority 5: Timing Information

#### 5A. Per-File Elapsed Time
Show how long the current file has been processing.

```
┌─ STATUS ─────────────────────┐
│ Plan: feature-auth.md (2m34s)│  ← Per-file time
│ Session: abc123...           │
│ Total: 15m22s                │  ← Existing total time
└──────────────────────────────┘
```

**Implementation:**
- Track `_file_start_time` on `FILE_FOUND`
- Update display in `_update_elapsed()` timer
- Reset on file completion/failure

## New Keybindings

```python
WATCH_BINDINGS = [
    # Existing
    Binding("r", "respond", "Respond"),
    Binding("R", "refresh", "Refresh"),
    Binding("c", "clear", "Clear"),
    Binding("g", "show_git_diff", "Git Diff"),
    # New (Phase 1-3)
    Binding("p", "toggle_pause", "Pause"),
    Binding("tab", "focus_next", "Next Panel", show=False),
    Binding("shift+tab", "focus_prev", "Prev Panel", show=False),
    Binding("j", "scroll_down", "Scroll Down", show=False),
    Binding("k", "scroll_up", "Scroll Up", show=False),
    Binding("f", "toggle_fullscreen", "Fullscreen"),  # Conditional
    Binding("y", "copy_session_id", "Copy ID"),
    Binding("b", "show_blocker", "Blocker"),
    Binding("1", "filter_errors", "Errors", show=False),
    Binding("2", "filter_warnings", "Warnings", show=False),
    Binding("3", "filter_all", "All Logs", show=False),
    # Deferred: Binding("s", "skip_file", "Skip") - needs Orchestrator.abort()
]
```

## Implementation Order

| Phase | Features | Status | Effort |
|-------|----------|--------|--------|
| **Phase 1** | 1A (repo/branch), 1B (current plan), 4A (copy ID), 4B (full blocker) | **GO** | 1-2 days |
| **Phase 2** | 2A (focus cycling), 2B (scroll), 4C (log filter) | **GO** | 1-2 days |
| **Phase 3** | 3A (pause polling), 5A (per-file time) | **GO** | 1 day |
| **Phase 4** | 2C (maximize panel) | **Conditional GO** | 1 day |
| ~~Phase 5~~ | ~~3B (skip file)~~ | **DEFERRED** | N/A |

**Risk Assessment:**
- **Phase 1-3:** Low risk, localized TUI/controller changes
- **Phase 4 (2C):** Medium risk - layout edge cases, may need iteration
- **3B Skip:** High risk - requires `Orchestrator.abort()` design first

## UI Mockup

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Orchestrator Auto - Watch Mode          📁 my-project (feature/auth-v2)    │
├────────────────┬────────────────┬────────────────────────────────────────────┤
│ WATCH          │ STATUS         │ PLANNER                 │ EXECUTOR        │
│ ./plans/       │                │                         │                 │
│ ▶ Running      │ Plan: auth.md  │ Looking at milestone 2  │ I'll implement  │
│                │ (1m23s)        │ requirements...         │ the login API..│
│ ✓ 2 ✗ 0 ⏸ 0   │                │                         │                 │
│                │ Session: a1b2  │ The deliverables look   │ ```python       │
│ Pending:       │ Phase: EXEC    │ complete. Let me verify │ def login():    │
│  • api-fix.md  │ M: 2/4         │ the tests pass...       │   ...           │
│  • refactor.md │                │                         │ ```             │
│                │ Tokens: 45.2k  │                         │                 │
├────────────────┤ Cost: $0.12    │                         │                 │
│ MILESTONES     ├────────────────┤                         │                 │
│ ✓ 1. Setup     │ GIT            │                         │                 │
│ ▶ 2. Auth API  │ M 3 files      │                         │                 │
│ ○ 3. Tests     │ + 2 untracked  │                         │                 │
│ ○ 4. Docs      │                │                         │                 │
├────────────────┴────────────────┴─────────────────────────┴─────────────────┤
│ LOG (all)                                                          [1/2/3]  │
│ 14:32:01 [INFO] Found: feature-auth.md                                      │
│ 14:32:05 [INFO] Session started: a1b2c3d4                                   │
│ 14:33:28 [SUCCESS] Milestone 1 approved                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ q Quit  ? Help  r Respond  p Pause  f Full  g Git  y Copy  b Blocker  1/2/3 │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Testing Strategy

1. **Unit tests** for new `StatusPanel` methods (`update_current_plan`, `update_repo_info`)
2. **Unit tests** for `WatchController.pause()` / `resume()`
3. **Unit tests** for `LogPanel.set_filter_level()`
4. **Manual testing** of keyboard navigation and focus states
5. **Integration test** for full watch cycle with pause/resume

## Open Questions (Resolved)

| Question | Decision | Rationale |
|----------|----------|-----------|
| Should pause also pause orchestrator execution? | **No** - polling only | Low complexity, doesn't require `Orchestrator.pause()` |
| Should skip require confirmation? | **Deferred** | Skip feature deferred pending `Orchestrator.abort()` |
| Should repo/branch auto-refresh? | **Yes** - every 30s | Catches branch switches without manual refresh |

## Review Status

### Review Round 1 (2025-01-27)
- **Verdict:** GO for Phases 1-3, Conditional GO for Phase 4, NO-GO for 3B
- **Key decisions:**
  - Clipboard: Use built-in `App.copy_to_clipboard()` (no new deps)
  - Pause semantics: Polling only (not orchestrator execution)
  - Skip file: Deferred - requires `Orchestrator.abort()` design
- **Risk notes:**
  - 2A/2B (focus/scroll): Medium risk due to keyboard event routing
  - 2C (maximize): Medium risk due to layout edge cases
  - 3B (skip): High risk - cross-cutting orchestrator changes needed
