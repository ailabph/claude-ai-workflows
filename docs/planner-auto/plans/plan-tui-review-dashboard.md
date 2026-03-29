# TUI Review Dashboard - Implementation Plan (v2)

## Overview

Add a Textual-based TUI to the `planner-auto review` command via a `--tui` flag. The dashboard shows live review loop progress: round-by-round metrics, convergence sparkline, GPT cost, plan growth, and disposition details. Read-only for v1 — displays state, does not modify it. Existing CLI behavior unchanged when `--tui` is not passed.

**Reference:** `docs/planner-auto/plans/proposal-tui.md` (v2)

**Key constraints:**
- Engine AND CLI stdout must be fully suppressed when TUI is active (new `"tui"` verbosity mode)
- CLI and TUI share the same review workflow core (refactored from current `cli.py:661-888`)
- Claude revision tokens and cost are `n/a` (only GPT metrics are available)
- Paused-state screen is read-only (shows blocker + CLI commands, no interactive actions)
- Quit during active review waits for current round to finish, then exits cleanly
- Textual is an optional dependency (`pip install planner-auto[tui]`)

## Review History

- **v1:** Reviewed NO_GO — 3 blockers: (1) TUI path skips review lifecycle setup/teardown, (2) stdout suppression only covers `_emit_progress` not `_emit_final` or CLI messages, (3) quit semantics undefined. 2 non-blocking: missing `on_revision_start` callback, log panel source unspecified.
- **v2:** All 5 issues addressed. Added M1 refactor task, full stdout inventory, quit contract, `RevisionStarted` message, log panel contract.

---

## Milestone 1: Review Workflow Refactor + Engine Callbacks

Extract the review orchestration logic from `cli.py` into a shared helper so both CLI and TUI use the same setup/run/finalize path. Add callback infrastructure to the engine with full stdout suppression in TUI mode.

### Tasks

**Review workflow refactor:**
- [ ] `review_workflow.py` (new file): Extract from `cli.py:692-888` into a `ReviewWorkflow` class with three phases:
  - `prepare(conn, session_id, opts) -> PreparedReview`: Validates session, advances PLANNING→REVIEW, loads draft, resolves complexity/cap, builds config snapshot, creates reviewer adapter, resolves planner model and backend. Returns a `PreparedReview` dataclass with all resolved values (engine, engine_config, current_plan, max_rounds, complexity, base_config, resolved_repo_root, fast). No stdout — all status communicated via return value.
  - `run(prepared) -> LoopResult`: Calls `asyncio.run(engine.run(...))`. No stdout — engine handles output via verbosity mode.
  - `finalize(conn, session_id, result, prepared) -> FinalizeResult`: On convergence: advances REVIEW→COMPLETE, exports artifacts, does .kafra handoff. On cap+criticals: creates blocker. Returns `FinalizeResult` dataclass with phase, export_paths, kafra_path, blocker_text. No stdout — caller decides how to present results.
- [ ] `review_workflow.py`: Define `ReviewOpts` dataclass for all review command options (fast, max_rounds, no_review_history, reviewer_model, reviewer_reasoning, complexity_override, repo_root, verbosity, debug)
- [ ] `review_workflow.py`: Define `PreparedReview` dataclass holding resolved engine, engine_config, current_plan, max_rounds, complexity, base_config, resolved_repo_root, fast, reviewer, planner_model
- [ ] `review_workflow.py`: Define `FinalizeResult` dataclass holding converged, phase, export_paths, kafra_path, blocker_text, total_cost, total_rounds, stop_reason
- [ ] `cli.py`: Refactor the `review` command to use `ReviewWorkflow`: call `prepare()`, emit CLI status messages (phase advance, "Starting review loop..."), call `run()`, emit CLI finalize messages (export count, .kafra path, session status), call `finalize()`. The CLI path uses the workflow but still owns its `click.echo()` calls. Existing behavior unchanged.
- [ ] `tests/test_review_workflow.py` (new file): Test `prepare()` returns correct config from mocked session. Test `finalize()` advances phase on convergence. Test `finalize()` creates blocker on cap_with_criticals. All with in-memory SQLite.

**Engine callback infrastructure:**
- [ ] `loop/engine.py`: Add `callbacks: dict | None = None` parameter to `ReviewLoopEngine.__init__()`, stored as `self._callbacks`
- [ ] `loop/engine.py`: Add `"tui"` verbosity mode to `_emit_progress()` — when `verbosity == "tui"`, skip ALL `print()` calls and dispatch to `self._callbacks` instead; file logging via `logger.*` continues unchanged
- [ ] `loop/engine.py`: Add `"tui"` verbosity mode to `_emit_final()` — when `verbosity == "tui"`, skip the `print()` call and dispatch to `self._callbacks["on_loop_finished"]` instead
- [ ] `loop/engine.py`: Add 7 callback dispatch points (each guarded with `if self._callbacks and "key" in self._callbacks`):
  1. Before GPT review call: `on_round_start(round_num, max_rounds)`
  2. After GPT review returns: `on_review_complete(metrics_dict)`
  3. After feedback validation: `on_feedback_validated(round_num, dispositions)`
  4. Before Claude revision call: `on_revision_start(round_num, accepted_count, deferred_count, rejected_count)`
  5. After Claude revision: `on_revision_complete(round_num, prev_size, new_size, latency_ms, history_context_size)`
  6. On loop exit: `on_loop_finished(result_dict)`
  7. On timeout/retry: `on_revision_timeout(round_num, timeout_sec, retry_count)`
- [ ] `pyproject.toml`: Add `tui = ["textual>=0.80.0"]` to `[project.optional-dependencies]`; add `"textual[dev]>=0.80.0"` to the `dev` dependency group

**Tests:**
- [ ] `tests/test_engine.py`: Add `test_tui_verbosity_skips_all_stdout` — run engine with `verbosity="tui"` and `callbacks=mock_dict`, mock `builtins.print`, assert zero print calls across both `_emit_progress` and `_emit_final`
- [ ] `tests/test_engine.py`: Add `test_callbacks_none_does_not_crash` — engine with `verbosity="tui"` and `callbacks=None`, assert no exception
- [ ] `tests/test_engine.py`: Add `test_callbacks_partial_dict` — provide dict with only 4 of 7 keys, assert missing keys skipped without error
- [ ] `tests/test_engine.py`: Add `test_on_revision_start_fires_before_revision` — verify `on_revision_start` callback is invoked between `on_feedback_validated` and `on_revision_complete`

### Deliverables
- [ ] `planner-auto review <id> --verbose` produces identical output to before (no regression)
- [ ] `ReviewWorkflow.prepare()` + `run()` + `finalize()` can reproduce the full CLI review path
- [ ] Engine with `verbosity="tui"` produces zero stdout output (both `_emit_progress` and `_emit_final` suppressed)
- [ ] Engine with `verbosity="tui"` and mock callbacks invokes all 7 callback types with correct arguments
- [ ] `on_revision_start` fires between feedback validation and revision completion
- [ ] All existing tests pass; new test files: `test_review_workflow.py` (3+ tests), `test_engine.py` additions (4 tests)
- [ ] `pip install -e ".[tui]"` installs textual

---

## Milestone 2: TUI Foundation + Static Shell

Create the Textual app, adapter, message types, and theme. The TUI uses `ReviewWorkflow` for setup/teardown. App renders a static layout populated from the DB on mount — no live updates yet. Validates that the TUI launches, renders correctly, and can be quit cleanly.

### Tasks
- [ ] `tui/__init__.py`: Create package with `get_review_app_class()` function that lazily imports and returns `ReviewTUI`
- [ ] `tui/messages.py`: Define 8 Textual message classes — each as a dataclass inheriting from `textual.message.Message` with typed fields matching the engine callback signatures:
  - `RoundStarted(round_num, max_rounds)`
  - `ReviewComplete(round_num, verdict, issue_count, latency_ms, input_tokens, output_tokens, cost, keep_count, trim_count, issues)`
  - `FeedbackValidated(round_num, dispositions)`
  - `RevisionStarted(round_num, accepted_count, deferred_count, rejected_count)` — triggers "Claude revising..." phase in CurrentRound
  - `RevisionComplete(round_num, prev_size, new_size, latency_ms, history_context_size)`
  - `LoopFinished(converged, stop_reason, rounds, total_cost, final_plan_path)`
  - `RevisionTimeout(round_num, timeout_sec, retry_count)`
  - `LoopError(error_message, round_num)`
- [ ] `tui/adapter.py`: Create `TUIAdapter` class with one method per callback (`on_round_start`, `on_review_complete`, `on_feedback_validated`, `on_revision_start`, `on_revision_complete`, `on_loop_finished`, `on_revision_timeout`, `on_error`); each calls `self.app.call_from_thread(self.app.post_message, MessageType(...))` for thread-safe dispatch; `as_dict()` returns the callbacks dict for engine consumption
- [ ] `tui/bindings.py`: Define `REVIEW_BINDINGS` list with keybinding tuples: `("d", "dispositions", "Dispositions")`, `("p", "plan", "Plan")`, `("l", "log_filter", "Log filter")`, `("q", "quit", "Quit")`, `("question_mark", "help", "Help")`
- [ ] `tui/styles/theme.tcss`: Port color palette from orchestrator-auto (`$primary: #00ff41`, `$accent: #00d9ff`, `$warning: #ffcc00`, `$error: #ff3333`, `$background: #0d0d0d`, `$surface: #1a1a1a`); define base widget styles for panels, headers, labels, log entries; add responsive grid rules for 3 breakpoints (<80, 80-119, 120+)
- [ ] `tui/review_app.py`: Create `ReviewTUI(App)` class:
  - `__init__` accepts `prepared: PreparedReview`, `conn`, `session_id`, `db_path`
  - `compose()` yields Header + 2-column grid (left sidebar container + main panel container) + log panel + Footer
  - `on_mount()` reads session from DB and populates sidebar labels (phase, status, project, backend, complexity, round cap)
  - Stores `self._review_active = False` flag for quit-guard logic
- [ ] `tui/widgets/session_panel.py`: Static widget showing session metadata in a Vertical container with Label pairs (field: value); `update_phase()` and `update_status()` methods for later use
- [ ] `tui/widgets/log_panel.py`: RichLog-based widget with `log(message, level)` method; color-codes by level (info=default, success=green, warning=yellow, error=red); max 500 lines. **Source contract:** log panel shows callback-derived timeline events (e.g., "R3: NO_GO — 2 issues"), NOT raw Python logger stream. The adapter translates engine callbacks into human-readable log lines.
- [ ] `cli.py`: Add `--tui` flag (is_flag=True) to the `review` command. When `--tui`:
  1. Attempt lazy import of `planner_auto.tui`; print actionable error if `textual` not installed and exit 1
  2. Call `ReviewWorkflow.prepare()` (shared setup — same as CLI path)
  3. Set `engine_config["verbosity"] = "tui"`
  4. Instantiate `ReviewTUI(prepared=prepared, conn=conn, ...)` and call `app.run()`
  5. After app exits, call `ReviewWorkflow.finalize()` (shared teardown — export, .kafra, phase transition)
- [ ] `tests/test_tui_messages.py`: Verify all 8 message classes can be instantiated with correct fields and have proper types
- [ ] `tests/test_tui_adapter.py`: Verify `TUIAdapter` methods create correct message types (mock the app); verify `as_dict()` returns all 7 callback keys
- [ ] `tests/test_review_cli.py`: Add `test_review_tui_flag_without_textual` — mock import failure, assert CLI prints install instructions and exits 1

### Deliverables
- [ ] `planner-auto review <id> --tui` calls `ReviewWorkflow.prepare()` then launches a Textual app with session metadata in the sidebar
- [ ] After TUI exits, `ReviewWorkflow.finalize()` handles export and .kafra handoff (same as CLI path)
- [ ] Pressing `q` on the static shell (no active review) exits cleanly — no hanging threads, no tracebacks
- [ ] Theme renders correctly in iTerm2 and Terminal.app (dark background, green accent)
- [ ] Responsive: resizing terminal below 80 cols switches to stacked layout
- [ ] All existing tests pass; 3 new test files pass

---

## Milestone 3: Live Review Dashboard

Wire the engine worker thread to the TUI via the adapter. Rounds appear in real-time. Convergence panel updates after each round. Current-round widget shows live progress with distinct GPT/Claude sub-phases. Log panel streams callback-derived timeline events. Quit during active review is handled gracefully.

### Tasks

**Worker thread + quit contract:**
- [ ] `tui/review_app.py`: Add `run_review_loop()` as a Textual worker (`@work(thread=True)`):
  1. Set `self._review_active = True`
  2. Call `ReviewWorkflow.run(prepared)` with engine callbacks pointing to `TUIAdapter(self).as_dict()`
  3. On completion, post `LoopFinished` message and set `self._review_active = False`
  4. On exception, post `LoopError` message and set `self._review_active = False`
- [ ] `tui/review_app.py`: Add `_quit_requested: bool = False` flag. Override `action_quit()`:
  - If `self._review_active is False`: exit immediately via `self.exit()`
  - If `self._review_active is True`: set `self._quit_requested = True`, log "Waiting for current round to finish before quitting..." in log panel, disable the `q` binding (change label to "quitting after round...")
  - In the `on_loop_finished` and `on_loop_error` handlers: if `self._quit_requested`, call `self.exit()` after finalize
- [ ] `tui/review_app.py`: On app exit (whether normal or quit-requested), ensure `ReviewWorkflow.finalize()` is called via the CLI wrapper (app returns result to CLI, CLI calls finalize)

**Message handlers:**
- [ ] `tui/review_app.py`: Add message handlers: `on_round_started()`, `on_review_complete()`, `on_feedback_validated()`, `on_revision_started()`, `on_revision_complete()`, `on_loop_finished()`, `on_revision_timeout()`, `on_loop_error()` — each updates the appropriate widgets and logs a timeline event to log_panel

**Widgets:**
- [ ] `tui/widgets/round_list.py`: ListView-based widget; `add_round(round_num, status)` appends a row with icon + round number; `update_round(round_num, verdict, issue_count, cost)` updates text and icon; icons: `▶` active, `✓` completed, `★` GO, `⚠` cap+criticals, `○` pending
- [ ] `tui/widgets/convergence_panel.py`: Shows issue trend as `3→1→2→_`, sparkline using Unicode block elements (`▁▂▃▄▅▆▇`), cumulative GPT cost, cumulative GPT tokens; `update(round_num, issue_count, cost, tokens)` appends to internal lists and re-renders
- [ ] `tui/widgets/plan_panel.py`: Shows current draft number, plan size in chars, growth percentage vs original, milestone count (parsed from `## Milestone` headers); `update(draft_num, size, original_size, plan_text)` recalculates and re-renders
- [ ] `tui/widgets/current_round.py`: Shows current sub-phase with distinct states:
  - On `RoundStarted` → show "GPT reviewing..." with elapsed timer and progress bar
  - On `FeedbackValidated` → briefly show disposition summary (X ACCEPT, Y DEFER, Z REJECT)
  - On `RevisionStarted` → show "Claude revising..." with elapsed timer and progress bar (progress estimated from average of prior revision latencies)
  - On `RevisionComplete` or `ReviewComplete(GO)` → clear to idle
  - `tick()` method called by 1s timer to update elapsed seconds
  - `clear()` method resets to idle state

**Sub-phase transitions** are driven by messages, not by a missing callback:
  - `RoundStarted` → GPT reviewing phase
  - `ReviewComplete` → brief pause (feedback incoming)
  - `FeedbackValidated` → disposition summary shown
  - `RevisionStarted` → Claude revising phase
  - `RevisionComplete` → idle (next round or finished)

**Finalize states:**
- [ ] `tui/review_app.py`: On `LoopFinished`, update session panel (phase=COMPLETE or PAUSED), show result summary in main panel (converged/cap/error, final plan path, total cost), stop the tick timer
- [ ] `tui/review_app.py`: On `RevisionTimeout`, update current-round widget to show retry status ("RETRY after 120s timeout"), log warning to log_panel
- [ ] `tui/review_app.py`: On `LoopError`, display error in main panel and log panel, update status to show failure
- [ ] Paused-state handling: when `LoopFinished` with `stop_reason="cap_with_criticals"`, show blocker text + critical issue description + CLI commands (`planner-auto resume`, `planner-auto review --max-rounds`, `planner-auto complete`) in main panel; no interactive actions

**Styles + tests:**
- [ ] `tui/styles/theme.tcss`: Add styles for round_list rows (status-based colors), convergence sparkline, current-round progress bar, paused/error states
- [ ] `tui/review_app.py`: Start 1-second `set_interval` timer on mount to call `current_round.tick()` for elapsed time updates
- [ ] `tests/test_tui_live.py`: Test that posting `RoundStarted` → `ReviewComplete` → `RevisionStarted` → `RevisionComplete` sequence updates round_list, convergence_panel, and plan_panel correctly
- [ ] `tests/test_tui_live.py`: Test that `LoopFinished(converged=True)` updates session_panel phase to COMPLETE
- [ ] `tests/test_tui_live.py`: Test that `LoopFinished(stop_reason="cap_with_criticals")` renders blocker text with CLI commands
- [ ] `tests/test_tui_live.py`: Test quit-during-review: post `RoundStarted`, simulate `q` keypress, assert "Waiting for current round..." appears in log_panel, then post `LoopFinished`, assert app exits

### Deliverables
- [ ] `planner-auto review <id> --tui` shows rounds appearing in real-time as the loop runs
- [ ] CurrentRound widget shows distinct "GPT reviewing..." and "Claude revising..." phases with elapsed timers
- [ ] `RevisionStarted` message triggers the "Claude revising..." sub-phase (not inferred from absence of events)
- [ ] Convergence panel sparkline and cost update after each round
- [ ] On convergence (GO), main panel shows result summary with final plan path
- [ ] On cap with criticals, main panel shows blocker + CLI commands (no interactive actions)
- [ ] On timeout, current-round shows retry status
- [ ] Log panel shows callback-derived timeline events (not raw logger output)
- [ ] Pressing `q` during active review shows "Waiting for current round..." and exits after the round completes (no mid-API-call termination, no orphaned threads)
- [ ] Pressing `q` when review is idle exits immediately
- [ ] All existing tests pass; 4 new TUI integration tests pass

---

## Milestone 4: Drill-Down Screens + Polish

Add round detail expansion, disposition screen, plan viewer, raw response viewer, help screen, and log filtering. Complete the keybinding system.

### Tasks
- [ ] `tui/widgets/round_detail.py`: Container widget shown when a round is selected; displays: verdict, GPT latency + tokens + cost, Claude latency (tokens/cost as `n/a` — clearly labeled "Claude revision metrics require plumbing work, see proposal"), keep items list (prefixed with `+`), trim items list (prefixed with `-`), issues with disposition badges (`[ACCEPT]`, `[DEFER]`, `[REJECT]`), draft size change with percentage, history context size
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
