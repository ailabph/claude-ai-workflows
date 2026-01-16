# Feature: Enhanced Watch TUI Statistics

Add useful developer statistics to the Watch TUI to fill blank space and provide better visibility into workflow progress.

## Current State

The Watch TUI has underutilized space in:
- STATUS panel (7 stats, room for more)
- MILESTONES panel (shows "No milestones yet" even when milestones exist - BUG)
- WATCH panel (has counts but missing pending/queue info)

## Milestone 1: Fix Milestones Panel Loading

**Problem:** MILESTONES panel shows "No milestones yet" even when executing milestone 2/8.

**Tasks:**
1. Investigate why `MilestonesLoaded` message isn't being sent in watch mode
2. Trace the flow: `parse_plan_file()` → orchestrator → adapter → TUI
3. Ensure `on_milestones_loaded` handler is called when session starts
4. Add milestone loading to `SESSION_STARTED` event or emit separate event from watch controller

**Files:**
- `orchestrator_auto/controllers/watch_controller.py`
- `orchestrator_auto/tui/watch_app.py`
- `orchestrator_auto/tui/messages.py` (if new message needed)

**Acceptance:**
- [ ] Milestones panel shows all milestones from plan file
- [ ] Current milestone is highlighted
- [ ] Completed milestones show checkmark

## Milestone 2: Add Milestone Progress to STATUS Panel

**Goal:** Show current milestone progress prominently (e.g., "Milestone: 2/8")

**Tasks:**
1. Add `milestone_progress` field to `StatusPanel` widget
2. Add `update_milestone_progress(current, total)` method
3. Update layout in `StatusPanel.compose()` to include milestone row
4. Wire up updates from `StateChanged` events (already has `current_milestone`, `total_milestones`)
5. Also update from `SESSION_STARTED` event

**Files:**
- `orchestrator_auto/tui/widgets/status_panel.py`
- `orchestrator_auto/tui/watch_app.py` (wire up handlers)

**Acceptance:**
- [ ] STATUS panel shows "Milestone: 2/8" format
- [ ] Updates in real-time as milestones complete

## Milestone 3: Add Feature Name to STATUS Panel

**Goal:** Show what feature/plan is being executed (truncated to fit)

**Tasks:**
1. Add `feature` field to `StatusPanel` widget
2. Add `update_feature(name)` method with truncation (max ~25 chars)
3. Update layout to include feature row after Session
4. Pass feature name in `SESSION_STARTED` event from watch controller
5. Update `WatchSessionStarted` message to include feature
6. Wire up handler to call `status_panel.update_feature()`

**Files:**
- `orchestrator_auto/tui/widgets/status_panel.py`
- `orchestrator_auto/controllers/watch_controller.py`
- `orchestrator_auto/tui/messages.py`
- `orchestrator_auto/tui/watch_app.py`

**Acceptance:**
- [ ] STATUS panel shows "Feature: Add user auth..." (truncated)
- [ ] Clears/updates when new file starts processing

## Milestone 4: Add Pending Files Count to WATCH Panel

**Goal:** Show how many files are waiting to be processed

**Tasks:**
1. Add `pending_count` field to `WatchPanel` widget
2. Add `update_pending_count(count)` method
3. Update layout to show "Pending: N files" in watch info section
4. Update `sync_pending_files()` to also update the count display
5. Alternatively, derive from `len(pending_files)` in the sync method

**Files:**
- `orchestrator_auto/tui/widgets/watch_panel.py`

**Acceptance:**
- [ ] WATCH panel shows "Pending: 3 files" (or "Pending: 0" when empty)
- [ ] Updates in real-time as files are added/processed

## Milestone 5: Add Estimated Cost to STATUS Panel

**Goal:** Show running cost estimate based on tokens and model pricing

**Tasks:**
1. Define pricing constants (per 1M tokens):
   - Opus input: $15, output: $75
   - Sonnet input: $3, output: $15
   - Haiku input: $0.25, output: $1.25
2. Add `estimated_cost` field to `StatusPanel`
3. Add `update_cost(input_tokens, output_tokens, model)` method
4. Track input vs output tokens separately (currently only total)
5. Update `add_tokens()` to estimate input/output split or add separate tracking
6. Display as "Est. Cost: $0.12" format

**Files:**
- `orchestrator_auto/tui/widgets/status_panel.py`
- `orchestrator_auto/tui/watch_app.py` (if token tracking needs changes)

**Acceptance:**
- [ ] STATUS panel shows "Est. Cost: $X.XX"
- [ ] Cost accumulates as tokens are processed
- [ ] Resets when new session starts

## Summary

| Milestone | Effort | Impact |
|-----------|--------|--------|
| M1: Fix Milestones Panel | Medium | High - Currently broken |
| M2: Milestone Progress | Low | High - Key visibility |
| M3: Feature Name | Low | Medium - Context |
| M4: Pending Count | Low | Medium - Queue visibility |
| M5: Est. Cost | Medium | Medium - Cost awareness |

## Technical Notes

- All changes are additive to existing widgets
- No breaking changes to existing functionality
- Follow existing patterns in `status_panel.py` and `watch_panel.py`
- Use `try/except` guards like existing update methods for resilience
- Test with `orchestrator watch .plans --tui --headless`
