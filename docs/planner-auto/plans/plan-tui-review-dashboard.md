# TUI Review Dashboard - Implementation Plan

## Overview

Add a Textual-based TUI to the `planner-auto review` command via a `--tui` flag. The dashboard shows live review loop progress: round-by-round metrics, convergence sparkline, GPT cost, plan growth, and disposition details. Read-only for v1 — displays state, does not modify it. Existing CLI behavior unchanged when `--tui` is not passed.

**Reference:** `docs/planner-auto/plans/proposal-tui.md` (v2)

**Key constraints:**
- Engine stdout must be fully suppressed when TUI is active (new `"tui"` verbosity mode)
- Claude revision tokens and cost are `n/a` (only GPT metrics are available)
- Paused-state screen is read-only (shows blocker + CLI commands, no interactive actions)
- Textual is an optional dependency (`pip install planner-auto[tui]`)

---

## Milestone 1: Engine Callbacks + CLI Wiring

Add callback infrastructure to `ReviewLoopEngine` and wire `--tui` flag in CLI. No TUI code yet — this milestone makes the engine TUI-ready without breaking existing behavior.

### Tasks
- [ ] `loop/engine.py`: Add `callbacks: dict | None = None` parameter to `ReviewLoopEngine.__init__()`, stored as `self._callbacks`
- [ ] `loop/engine.py`: Add `"tui"` to the verbosity mode handling in `_emit_progress()` — when `verbosity == "tui"`, skip all `print()` calls and dispatch to `self._callbacks` instead; file logging via `logger.*` continues unchanged
- [ ] `loop/engine.py`: Add 6 callback dispatch points at: (1) before GPT review call (`on_round_start`), (2) after GPT review returns (`on_review_complete`), (3) after feedback validation (`on_feedback_validated`), (4) after Claude revision (`on_revision_complete`), (5) on loop exit (`on_loop_finished`), (6) on timeout/retry (`on_revision_timeout`)
- [ ] `loop/engine.py`: Ensure each callback dispatch is guarded with `if self._callbacks and "on_X" in self._callbacks`
- [ ] `cli.py`: Add `--tui` flag (is_flag=True) to the `review` command
- [ ] `cli.py`: When `--tui` is passed, set `engine_config["verbosity"] = "tui"` and attempt lazy import of `planner_auto.tui`; print actionable error if `textual` not installed and exit
- [ ] `pyproject.toml`: Add `tui = ["textual>=0.80.0"]` to `[project.optional-dependencies]`; add `"textual[dev]>=0.80.0"` to the `dev` dependency group
- [ ] `tests/test_engine.py`: Add `test_tui_verbosity_skips_stdout` — run engine with `verbosity="tui"` and `callbacks=mock_dict`, assert no `print()` calls (mock builtins.print), assert callbacks were invoked
- [ ] `tests/test_engine.py`: Add `test_callbacks_none_does_not_crash` — run engine with `verbosity="tui"` and `callbacks=None`, assert no exception
- [ ] `tests/test_engine.py`: Add `test_callbacks_partial_dict` — provide callbacks dict with only 3 of 6 keys, assert missing keys are skipped without error
- [ ] `tests/test_review_cli.py`: Add `test_review_tui_flag_without_textual` — mock import failure for `planner_auto.tui`, assert CLI prints install instructions and exits 1

### Deliverables
- [ ] `planner-auto review <id> --verbose` produces identical output to before (no regression)
- [ ] `planner-auto review <id> --tui` with textual not installed prints `"TUI requires 'textual'. Install: pip install planner-auto[tui]"` and exits 1
- [ ] Engine with `verbosity="tui"` and mock callbacks invokes all 6 callback types with correct arguments
- [ ] Engine with `verbosity="tui"` produces zero stdout output
- [ ] All existing tests pass; 4 new tests pass
- [ ] `pip install -e ".[tui]"` installs textual

---

## Milestone 2: TUI Foundation + Static Shell

Create the Textual app, adapter, message types, and theme. App renders a static layout populated from the DB on mount — no live updates yet. Validates that the TUI launches, renders correctly, and can be quit cleanly.

### Tasks
- [ ] `tui/__init__.py`: Create package with `get_review_app_class()` function that lazily imports and returns `ReviewTUI`
- [ ] `tui/messages.py`: Define 7 Textual message classes: `RoundStarted`, `ReviewComplete`, `FeedbackValidated`, `RevisionComplete`, `LoopFinished`, `RevisionTimeout`, `LoopError` — each as a dataclass inheriting from `textual.message.Message` with typed fields matching the engine callback signatures
- [ ] `tui/adapter.py`: Create `TUIAdapter` class with one method per callback (`on_round_start`, `on_review_complete`, `on_feedback_validated`, `on_revision_complete`, `on_loop_finished`, `on_revision_timeout`, `on_error`) — each calls `self.app.call_from_thread(self.app.post_message, MessageType(...))` for thread-safe dispatch
- [ ] `tui/bindings.py`: Define `REVIEW_BINDINGS` list with keybinding tuples: `("d", "dispositions", "Dispositions")`, `("p", "plan", "Plan")`, `("l", "log_filter", "Log filter")`, `("q", "quit", "Quit")`, `("question_mark", "help", "Help")`
- [ ] `tui/styles/theme.tcss`: Port color palette from orchestrator-auto (`$primary: #00ff41`, `$accent: #00d9ff`, `$warning: #ffcc00`, `$error: #ff3333`, `$background: #0d0d0d`, `$surface: #1a1a1a`); define base widget styles for panels, headers, labels, log entries; add responsive grid rules for 3 breakpoints (<80, 80-119, 120+)
- [ ] `tui/review_app.py`: Create `ReviewTUI(App)` class with: `TITLE`, `CSS_PATH`, `BINDINGS`; `__init__` accepts `session_id`, `db_path`, `engine_config`; `compose()` yields Header + 2-column grid (left sidebar container + main panel container) + log panel + Footer; `on_mount()` reads session from DB and populates sidebar labels (phase, status, project, backend, complexity, round cap)
- [ ] `tui/widgets/session_panel.py`: Static widget showing session metadata in a Vertical container with Label pairs (field: value); `update_phase()` and `update_status()` methods for later use
- [ ] `tui/widgets/log_panel.py`: RichLog-based widget with `log(message, level)` method; color-codes by level (info=default, success=green, warning=yellow, error=red); max 500 lines
- [ ] `cli.py`: Complete the `--tui` path — when textual is available, instantiate `ReviewTUI` with session data and call `app.run()`
- [ ] `tests/test_tui_messages.py`: Verify all 7 message classes can be instantiated with correct fields and have proper types
- [ ] `tests/test_tui_adapter.py`: Verify `TUIAdapter` methods create correct message types (mock the app)

### Deliverables
- [ ] `planner-auto review <id> --tui` launches a Textual app that renders the 2-column layout with session metadata in the sidebar
- [ ] Pressing `q` exits the TUI cleanly (no hanging threads, no tracebacks)
- [ ] Theme renders correctly in iTerm2 and Terminal.app (dark background, green accent)
- [ ] Responsive: resizing terminal below 80 cols switches to stacked layout
- [ ] All existing tests pass; 2 new test files pass

---

## Milestone 3: Live Review Dashboard

Wire the engine worker thread to the TUI via the adapter. Rounds appear in real-time. Convergence panel updates after each round. Current-round widget shows live progress. Log panel streams events.

### Tasks
- [ ] `tui/review_app.py`: Add `run_review_loop()` as a Textual worker (`@work(thread=True)`); instantiate `ReviewLoopEngine` with `verbosity="tui"` and `callbacks=TUIAdapter(self).as_dict()`; catch exceptions and post `LoopError` message
- [ ] `tui/review_app.py`: Add message handlers: `on_round_started()`, `on_review_complete()`, `on_feedback_validated()`, `on_revision_complete()`, `on_loop_finished()`, `on_revision_timeout()`, `on_loop_error()` — each updates the appropriate widgets
- [ ] `tui/widgets/round_list.py`: ListView-based widget; `add_round(round_num, status)` appends a row with icon + round number; `update_round(round_num, verdict, issue_count, cost)` updates text and icon; icons: `▶` active, `✓` completed, `★` GO, `⚠` cap+criticals, `○` pending
- [ ] `tui/widgets/convergence_panel.py`: Shows issue trend as `3→1→2→_`, sparkline using Unicode block elements (`▁▂▃▄▅▆▇`), cumulative GPT cost, cumulative GPT tokens; `update(round_num, issue_count, cost, tokens)` appends to internal lists and re-renders
- [ ] `tui/widgets/plan_panel.py`: Shows current draft number, plan size in chars, growth percentage vs original, milestone count (parsed from `## Milestone` headers); `update(draft_num, size, original_size, plan_text)` recalculates and re-renders
- [ ] `tui/widgets/current_round.py`: Shows current sub-phase ("GPT reviewing..." or "Claude revising..."), elapsed seconds with progress bar (estimated from average of prior round latencies), reviewer/revision model, plan size and history context size; `set_phase(phase_name)`, `tick()` (called by 1s timer), `clear()` methods
- [ ] `tui/review_app.py`: Start 1-second `set_interval` timer on mount to call `current_round.tick()` for elapsed time updates
- [ ] `tui/review_app.py`: On `LoopFinished`, update session panel (phase=COMPLETE or PAUSED), show result summary in main panel (converged/cap/error, final plan path, total cost), stop the tick timer
- [ ] `tui/review_app.py`: On `RevisionTimeout`, update current-round widget to show retry status ("RETRY after 120s timeout"), log warning
- [ ] `tui/review_app.py`: On `LoopError`, display error in main panel and log panel, update status to show failure
- [ ] Paused-state handling: when `LoopFinished` with `stop_reason="cap_with_criticals"`, show blocker text + critical issue description + CLI commands (`planner-auto resume`, `planner-auto review --max-rounds`, `planner-auto complete`) in main panel; no interactive actions
- [ ] `tui/styles/theme.tcss`: Add styles for round_list rows (status-based colors), convergence sparkline, current-round progress bar, paused/error states
- [ ] `tests/test_tui_live.py`: Test that posting `RoundStarted` → `ReviewComplete` → `RevisionComplete` sequence to a mounted ReviewTUI updates round_list count, convergence_panel issue trend, and plan_panel size (use Textual's `async with app.run_test()` pattern)
- [ ] `tests/test_tui_live.py`: Test that `LoopFinished(converged=True)` updates session_panel phase to COMPLETE
- [ ] `tests/test_tui_live.py`: Test that `LoopFinished(stop_reason="cap_with_criticals")` renders blocker text with CLI commands

### Deliverables
- [ ] `planner-auto review <id> --tui` shows rounds appearing in real-time as the loop runs
- [ ] Convergence panel sparkline and cost update after each round
- [ ] Current-round widget shows elapsed time ticking during GPT review and Claude revision
- [ ] On convergence (GO), main panel shows result summary with final plan path
- [ ] On cap with criticals, main panel shows blocker + CLI commands (no interactive actions)
- [ ] On timeout, current-round shows retry status
- [ ] Log panel shows all round events with timestamps
- [ ] All existing tests pass; 3 new TUI integration tests pass

---

## Milestone 4: Drill-Down Screens + Polish

Add round detail expansion, disposition screen, plan viewer, raw response viewer, help screen, and log filtering. Complete the keybinding system.

### Tasks
- [ ] `tui/widgets/round_detail.py`: Container widget shown when a round is selected; displays: verdict, GPT latency + tokens + cost, Claude latency (tokens/cost as `n/a`), keep items list (prefixed with `+`), trim items list (prefixed with `-`), issues with disposition badges (`[ACCEPT]`, `[DEFER]`, `[REJECT]`), draft size change with percentage, history context size
- [ ] `tui/review_app.py`: On `Enter` key in round_list, replace main panel content with `round_detail` for the selected round; `Escape` returns to the round list + current-round view; `n`/`p` navigate between rounds in detail view
- [ ] `tui/screens/disposition_screen.py`: Modal screen (pushed via `app.push_screen`) showing all dispositions across all rounds in a DataTable: columns = Round, Issue, Disposition, Rationale (truncated); scrollable; data sourced from `review_dispositions` DB table
- [ ] `tui/screens/plan_screen.py`: Modal screen with scrollable TextArea (read-only) showing the latest plan draft; title shows draft number and char count
- [ ] `tui/screens/raw_response_screen.py`: Modal screen showing raw GPT response for the selected round; prefixed with security warning ("This contains the raw API response. Do not share publicly."); data sourced from `reviews.raw_response` DB column; only accessible from round detail view via `r` key
- [ ] `tui/screens/help_screen.py`: Modal screen listing all keybindings with descriptions; auto-generated from `REVIEW_BINDINGS`
- [ ] `tui/widgets/log_panel.py`: Add `cycle_filter()` method that rotates through 3 levels: all, warn+, error only; `l` key calls this; display current filter level in panel title
- [ ] `tui/review_app.py`: Wire all keybindings: `d` → disposition_screen, `p` → plan_screen, `l` → log_panel.cycle_filter(), `?` → help_screen, `Enter` → round_detail, `Escape` → back, `n`/`p` → navigate rounds, `r` → raw_response_screen (only in round detail)
- [ ] `tui/review_app.py`: Add `on_resize` handler that switches CSS classes for responsive layout (stacked below 80 cols, 2-column at 80+, wider main at 120+)
- [ ] `tui/styles/theme.tcss`: Add styles for modal screens (centered, bordered, semi-transparent background), round detail layout, disposition table, help screen
- [ ] `tests/test_tui_screens.py`: Test disposition screen renders with mock DB data (verify row count matches)
- [ ] `tests/test_tui_screens.py`: Test plan screen shows correct draft content
- [ ] `tests/test_tui_screens.py`: Test help screen lists all keybindings
- [ ] `tests/test_tui_keybindings.py`: Test `d` key pushes disposition screen, `Escape` pops it
- [ ] `tests/test_tui_keybindings.py`: Test `Enter` on round_list shows round_detail, `Escape` returns to round_list

### Deliverables
- [ ] Pressing `Enter` on any round in the list shows full round detail (GPT metrics, keep/trim, issues with dispositions)
- [ ] Claude revision row shows latency but tokens and cost as `n/a` (clearly labeled)
- [ ] `d` key shows cross-round disposition table; `Escape` returns to dashboard
- [ ] `p` key shows full plan text in scrollable viewer
- [ ] `r` key in round detail shows raw GPT response with security warning
- [ ] `?` key shows help screen with all keybindings
- [ ] `l` key cycles log filter (all → warn+ → error)
- [ ] Layout responds to terminal resize (stacked <80, 2-col 80+)
- [ ] All existing 401 tests pass; 4 new TUI test files pass
- [ ] Running `planner-auto review <id> --tui` on a completed session shows all rounds, final state, and allows full drill-down navigation
