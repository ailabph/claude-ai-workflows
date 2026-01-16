# Feature: Watch TUI Layout Redesign v2

Redesign the Watch TUI layout to maximize information density with separate agent outputs, git status tracking, and accurate token counting.

## Current Layout

```
┌─────────────┬─────────────┬─────────────────────────────────┐
│ WATCH       │ STATUS      │ AGENT OUTPUT                    │
│             ├─────────────┤ (combined planner + executor)   │
│             │ MILESTONES  │                                 │
├─────────────┴─────────────┴─────────────────────────────────┤
│ LOG                                                         │
└─────────────────────────────────────────────────────────────┘
```

**Problems:**
- Planner and executor output mixed together (hard to follow)
- No git/VCS status visibility
- MILESTONES panel too small
- Token count inaccurate (estimates from chunk length, not actual API usage)

## Proposed Layout

```
┌─────────────┬─────────────┬────────────────┬────────────────┐
│ WATCH       │ STATUS      │ PLANNER        │ EXECUTOR       │
│             │             │                │                │
│ Directory:  │ Phase:  EXE │ > planner:     │ > executor:    │
│ ...c-revol  │ Status: ACT │ Reviewing the  │ Implementing   │
│ Interval:2s │ Session:8ad │ progress repo- │ Milestone 2... │
│ Convert: No │ Feature:SHA │ rt for M1...   │                │
│ Pending:  3 │ Milestone:  │                │ ```python      │
│             │        2/8  │ The code looks │ def create():  │
│ ✓ 2 ✗ 0 ⏸ 0│ Models:     │ good. Tests    │   return {}    │
│             │  opus/sonn  │ pass. Approved │ ```            │
│ Recent:     │ Calls:   12 │                │                │
│ ▶ 04-SHARE  │ Tokens: 45K │ [MILESTONE_    │ Now adding     │
│ ○ 05-AUTH   │ Cost: $0.89 │  APPROVED]     │ validation...  │
│ ○ 06-API    │ Time: 12:34 │            ▼   │            ▼   │
├─────────────┼─────────────┼────────────────┴────────────────┤
│ MILESTONES  │ GIT STATUS  │ LOG                             │
│             │             │                                 │
│ ✓ 1: Setup  │ Branch:main │ 12:34:01 ✓ M1 approved          │
│ ▶ 2: API    │ Staged: 3   │ 12:34:02 → Sending M2...        │
│ ○ 3: Tests  │ Changed: 5  │ 12:35:15 [executor] Writing...  │
│ ○ 4: Docs   │ +284 -47    │ 12:36:22 [executor] Tests pass  │
│             │             │                                 │
│             │ src/api.py  │                                 │
│             │ src/model.  │                                 │
│             │ tests/test_ │                             ▼   │
└─────────────┴─────────────┴─────────────────────────────────┘
  q Quit  ? Help  r Refresh  c Clear  g Git diff    ^p palette
```

## Milestone 1: Create GitStatusPanel Widget

**Goal:** New widget showing real-time git status with file changes and diff stats.

**Tasks:**
1. Create `orchestrator_auto/tui/widgets/git_panel.py`
2. Implement `GitStatusPanel` widget with:
   - Branch name display
   - Staged/unstaged file counts
   - Total lines added/removed (+N -M)
   - List of modified files (truncated names)
3. Add `refresh_git_status()` method that runs `git status --porcelain` and `git diff --stat`
4. Add periodic refresh (every 5 seconds or on-demand)
5. Handle non-git directories gracefully

**Widget Layout:**
```
GIT STATUS
Branch: main
Staged:   3 files
Changed:  5 files
+284 -47 lines

Modified:
 src/api.py
 src/models.py
 tests/test_api.py
```

**Files:**
- `orchestrator_auto/tui/widgets/git_panel.py` (NEW)
- `orchestrator_auto/tui/widgets/__init__.py` (export)

**Acceptance:**
- [ ] Shows current branch name
- [ ] Shows staged and unstaged file counts
- [ ] Shows +lines -lines summary
- [ ] Lists modified files (max 5-6, scrollable or truncated)
- [ ] Updates periodically or on file change events
- [ ] Gracefully handles non-git directories

## Milestone 2: Split Agent Output into Planner and Executor Panels

**Goal:** Separate output streams so developers can follow each agent's work independently.

**Tasks:**
1. Create `PlannerOutput` widget (copy of `AgentOutput` with different styling)
2. Create `ExecutorOutput` widget (or reuse `AgentOutput` with agent filter)
3. Modify `AgentOutput` to accept `agent_filter` parameter
4. Update `watch_app.py` layout to use two output panels side-by-side
5. Route chunks to correct panel based on `message.agent` ("planner" vs "executor")
6. Different header colors: planner=cyan, executor=green

**Files:**
- `orchestrator_auto/tui/widgets/agent_output.py` (modify)
- `orchestrator_auto/tui/watch_app.py` (layout change)

**Acceptance:**
- [ ] Two separate output panels in the layout
- [ ] Planner output only shows planner messages
- [ ] Executor output only shows executor messages
- [ ] Both panels scroll independently
- [ ] Visual distinction between panels (color/header)

## Milestone 3: Fix Token Counting Accuracy

**Goal:** Replace chunk-length estimation with actual API token counts.

**Current Problem:**
```python
# Current (inaccurate):
estimated_tokens = max(1, len(message.chunk) // 4)  # ~4 chars per token guess
```

**Tasks:**
1. Investigate where actual token counts are available:
   - Claude SDK response metadata
   - `ResultMessage` or streaming events
   - Agent SDK callbacks
2. Add token tracking to `BaseAgent` or adapter layer
3. Create new message type `TokensUsed(input_tokens, output_tokens, model)`
4. Emit `TokensUsed` after each agent turn completes
5. Update `StatusPanel` to track input vs output tokens separately
6. Fix cost calculation using actual token counts

**Token Sources (investigate):**
- `claude-agent-sdk` response objects
- Streaming event metadata
- Turn completion callbacks

**Files:**
- `orchestrator_auto/agents.py` (add token extraction)
- `orchestrator_auto/tui/messages.py` (add TokensUsed message)
- `orchestrator_auto/tui/watch_app.py` (wire up handler)
- `orchestrator_auto/tui/widgets/status_panel.py` (input/output tracking)

**Acceptance:**
- [ ] Token counts match actual API usage (within 5%)
- [ ] Input and output tokens tracked separately
- [ ] Cost calculation uses real token counts
- [ ] Works for both planner and executor agents

## Milestone 4: Update Watch TUI Layout Grid

**Goal:** Implement the new 4-column layout with all panels.

**New Grid Structure:**
```
Row 0: WATCH | STATUS | PLANNER_OUTPUT | EXECUTOR_OUTPUT
Row 1: MILESTONES | GIT_STATUS | LOG (spanning 2 cols)
```

**Tasks:**
1. Update `watch_app.py` `compose()` method with new grid
2. Use Textual `Grid` or nested `Horizontal`/`Vertical` containers
3. Set appropriate size hints/constraints:
   - Left panels: fixed width (~15-20 chars)
   - Middle panels: fixed width (~15-20 chars)
   - Right panels: flexible (fill remaining)
4. Ensure responsive behavior for different terminal widths
5. Update CSS in `theme.tcss` for new panel IDs

**Container Structure:**
```python
def compose(self) -> ComposeResult:
    yield Header()
    with Horizontal(id="main-row"):
        with Vertical(id="left-col"):
            yield WatchPanel(id="watch-panel")
            yield MilestoneList(id="milestone-list")
        with Vertical(id="middle-col"):
            yield StatusPanel(id="status-panel")
            yield GitStatusPanel(id="git-panel")
        with Vertical(id="right-col"):
            with Horizontal(id="output-row"):
                yield AgentOutput(id="planner-output", agent_filter="planner")
                yield AgentOutput(id="executor-output", agent_filter="executor")
            yield LogPanel(id="log-panel")
    yield Footer()
```

**Files:**
- `orchestrator_auto/tui/watch_app.py` (layout rewrite)
- `orchestrator_auto/tui/styles/theme.tcss` (new panel styles)

**Acceptance:**
- [ ] All 6 panels visible in layout
- [ ] Panels resize appropriately with terminal
- [ ] No overlapping or clipping issues
- [ ] Keyboard navigation works between panels

## Milestone 5: Add Git Diff Keyboard Shortcut

**Goal:** Press `g` to show full git diff in a modal/overlay.

**Tasks:**
1. Add `g` keybinding to `WATCH_BINDINGS`
2. Create `GitDiffScreen` modal screen
3. Run `git diff` and display in scrollable view
4. Support `git diff --staged` toggle with `s` key in modal
5. Syntax highlighting for diff output (optional)
6. `Esc` or `q` to close modal

**Files:**
- `orchestrator_auto/tui/bindings.py` (add keybinding)
- `orchestrator_auto/tui/screens/git_diff_screen.py` (NEW)
- `orchestrator_auto/tui/watch_app.py` (handle keypress)

**Acceptance:**
- [ ] `g` opens git diff modal
- [ ] Diff is scrollable
- [ ] `s` toggles staged/unstaged view
- [ ] `Esc` closes modal
- [ ] Works when there are no changes (shows "No changes")

## Summary

| Milestone | Effort | Impact | Dependencies |
|-----------|--------|--------|--------------|
| M1: GitStatusPanel | Medium | High | None |
| M2: Split Agent Output | Medium | High | None |
| M3: Fix Token Counting | High | High | Agent SDK research |
| M4: Layout Grid | Medium | High | M1, M2 |
| M5: Git Diff Modal | Low | Medium | M1 |

## Technical Notes

### Git Commands Used
```bash
# Branch name
git rev-parse --abbrev-ref HEAD

# Status (porcelain for parsing)
git status --porcelain

# Diff stats
git diff --stat --stat-width=40

# Staged diff stats
git diff --cached --stat --stat-width=40

# Full diff for modal
git diff
git diff --cached
```

### Token Counting Research
The Claude Agent SDK may expose token counts via:
- Response metadata in `ResultMessage`
- Streaming event callbacks
- Usage tracking in the SDK client

Need to investigate `claude-agent-sdk` source or docs to find exact location.

### Responsive Breakpoints
- **Small** (<100 cols): Stack panels vertically, hide git panel
- **Medium** (100-140 cols): 2-column layout
- **Large** (>140 cols): Full 4-column layout

### Color Scheme
```
Planner header: cyan (#00d7ff)
Executor header: green (#00ff00)
Git additions: green
Git deletions: red
Git branch: yellow
```

## Testing

```bash
# Test with watch mode
orchestrator watch .plans --tui --headless

# Test in non-git directory
cd /tmp && orchestrator watch ./test-plans --tui

# Test responsive layouts
# Resize terminal to various widths
```
