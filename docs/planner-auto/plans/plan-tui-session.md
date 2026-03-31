# TUI Session Mode - Implementation Plan (v2)

## Overview

Add a full-lifecycle Session TUI to planner-auto via `planner-auto session --project my-api --tui`. One persistent dashboard from start to complete: context management, interactive discussion, plan generation, embedded review, and completion summary. Phase-driven layout — sidebar stays constant, main panel switches per phase.

**Reference:** `docs/planner-auto/plans/proposal-tui-session.md` (v2)

**Review History:**
- **v1:** Reviewed NO_GO — 3 blockers: (1) no reusable context-write API (`add-context` is a Click command, not a library function), (2) `session` command not in `PHASE_ALLOWED_COMMANDS`, (3) review handler reuse overstated (handlers coupled to ReviewTUI widget tree). 1 non-blocking: M4 sneaks in new product behavior beyond `resolve_and_resume`.
- **v2:** All 4 issues addressed. Added context service extraction task. Defined session as a launcher that bypasses phase permissions. Added explicit review handler refactor task. Removed M4 post-resolve product decision.
- **v3:** 2 blockers + 2 medium fixes. ResultSummary reduced to available data (no phase durations or API call counts). SETUP→CONTEXT UI transition explicitly wired. Session logging added. LoopFinished vs SessionCompleted ownership clarified.
- **v4:** 2 blockers + 1 medium fix. Worker always calls finalize() (both convergence and cap+criticals). BlockerCreated includes blocker_id. Test wording corrected to match event ownership.

**Key constraints:**
- Per-operation workers, not a single long-lived worker (context: no worker, discuss: per-message, generate: one-shot, review: long-running)
- Worker thread owns finalize during review (different from standalone ReviewTUI where CLI owns finalize)
- Paused/blocker state is read-only until Milestone 4 (shows blocker + CLI commands)
- Reuses existing review widgets (RoundList, ConvergencePanel, CurrentRound) — requires a refactor step to extract shared handler logic from ReviewTUI
- Each milestone is independently shippable — unimplemented phases show "Use CLI for X" fallback

---

## Milestone 1: Session Shell + Context Manager

Persistent TUI shell with sidebar (session info + phase progress), context manager (file/note add modals), CLI `session` command, and phase-aware keybinding foundation. No worker threads — all context operations run on the TUI main thread.

### Tasks

**Context service extraction (prerequisite for TUI context management):**
- [ ] `context_service.py` (new file): Extract context-write logic from `cli.py:292-336` into a reusable function `add_context_entry(conn, session_id, entry_type, path_or_content, *, sm=None) -> dict`. This function: (1) validates file exists, is readable, is UTF-8, is <500KB (for type="file"), (2) resolves to absolute path, (3) reads file content, (4) calls `db.add_context_entry()`, (5) advances phase SETUP→CONTEXT if needed (via `SessionManager`), (6) commits, (7) returns `{"entry_type": ..., "key": ..., "size": ...}`. No `click.echo()` — returns data, caller decides presentation. For type="note": auto-generates key, stores content directly.
- [ ] `cli.py`: Refactor `add-context` command to call `context_service.add_context_entry()` and wrap result with `click.echo()`. Existing CLI behavior unchanged.
- [ ] `tests/test_context_service.py` (new file): Test `add_context_entry()` with file type (valid path, missing path, >500KB, non-UTF-8). Test with note type. Test phase advance SETUP→CONTEXT. All with in-memory SQLite.

**Session command permission model:**
- [ ] `cli.py`: Add `session` command. The `session` command is a **launcher**, not a phase-gated operation. It does NOT appear in `PHASE_ALLOWED_COMMANDS` and does NOT call `SessionManager.check_command()`. Instead, it reads the session's current phase from the DB and renders the TUI at that phase. Any phase is valid for resume — the TUI's phase-driven layout handles the rest.
- [ ] `cli.py`: Two invocation patterns: `planner-auto session --project <name> --tui` (create new) and `planner-auto session <session-id> --tui` (resume existing). When `--tui` is not passed, print "Session TUI requires --tui flag" and exit. Lazy import of `planner_auto.tui.session_app`; print install instructions if textual not installed.
- [ ] `cli.py`: In the `session` command's `--tui` path: if creating new, call `create_session()` + `save_session_config()` (same logic as `start` command). If resuming, load session from DB and validate it exists. Call `setup_session_logging(session_id)` before launching TUI — preserves observability conventions (session-scoped log file at `~/.planner-auto/logs/<session-id>.log`). Pass `session_id` + `db_path` to `SessionTUI`. After `app.run()` returns, read `app.exit_code` for shell return (0=normal, 1=error).

**TUI app + widgets:**
- [ ] `tui/session_app.py` (new file): Create `SessionTUI(App)` class:
  - `__init__` accepts `session_id: str`, `db_path: str`
  - `TITLE`, `CSS_PATH` (reuse `theme.tcss`), `BINDINGS` (phase-aware)
  - `compose()` yields: Header + 2-column grid (left sidebar container with SessionPanel + PhaseList + context summary + right main panel container) + LogPanel + Footer
  - `on_mount()`: open read-write connection (`self._rw_conn`), read session from DB, populate SessionPanel fields, populate PhaseList with current phase, populate context list from `context_entries` table, set initial main panel content based on current phase
  - `self._current_phase: str` tracks active phase for keybinding switching
  - `self.exit_code: int = 0` for CLI handoff
  - `action_quit()`: quit immediately (no deferred quit in context/discussion phases)
- [ ] `tui/session_app.py`: Implement phase-aware main panel switching — when phase changes, unmount current main panel content and mount the new phase's widget. For unimplemented phases (DISCUSSION, PLANNING, REVIEW in M1), mount a Static widget showing "Use CLI: planner-auto <command> <session-id>"
- [ ] `tui/session_app.py`: On `ContextAdded` message: (1) update context summary in sidebar (file count, note count, total size), (2) append entry to context_list widget, (3) **check if phase changed** — compare `self._current_phase` against the session's phase in DB (re-read via `_rw_conn`). If phase advanced (e.g., SETUP→CONTEXT on first add), post `PhaseAdvanced` message so the UI stays in sync with the DB.
- [ ] `tui/session_app.py`: On `PhaseAdvanced` message, update PhaseList icons, update `self._current_phase`, swap keybindings for new phase, and switch main panel content
- [ ] `tui/widgets/phase_list.py` (new file): Vertical widget showing 6 phases with status icons (`✓` completed, `▶` active, `○` pending, `⚠` paused). Each phase row shows: icon + phase name + optional count (e.g., "CONTEXT (4)"). Method `update_phase(phase, icon)` updates a single row. Method `set_active(phase)` highlights the current phase.
- [ ] `tui/widgets/compact_phase_bar.py` (new file): Single-line widget for small terminals (<80 cols). Renders as `✓ ✓ ▶ ○ ○ ○  4ctx  6msg  $0.00`. Shows phase icons inline + key metrics. Method `update(phases, context_count, message_count, cost)`.
- [ ] `tui/widgets/context_list.py` (new file): Scrollable list showing context entries. Each row: `#  Type  Path/Content  Size`. Types: `file` (shows path), `note` (shows first 40 chars), `synthesis` (shows "auto-generated"). Method `add_entry(entry_type, key, size)`. Method `get_total_size() -> int`.
- [ ] `tui/screens/file_input_screen.py` (new file): Modal screen with single-line text input for file path. On submit: calls `context_service.add_context_entry(conn, session_id, "file", path)` on the main thread. On success: posts `ContextAdded` message, dismisses modal. On validation error (missing file, >500KB, non-UTF-8): shows error inline from the raised exception, keeps modal open.
- [ ] `tui/screens/note_input_screen.py` (new file): Modal screen with multiline TextArea for note content. On submit: calls `context_service.add_context_entry(conn, session_id, "note", content)` on the main thread. Posts `ContextAdded` message, dismisses modal. Dismiss without saving on Esc.
- [ ] `tui/session_app.py`: Wire keybindings for CONTEXT phase: `f` → push `FileInputScreen`, `n` → push `NoteInputScreen`, `d` → advance to DISCUSSION phase (calls `SessionManager.advance_phase()`), `e` → export, `l` → cycle log filter, `q` → quit, `?` → help. Disable phase-inappropriate keys (e.g., `f`/`n` only active in CONTEXT/SETUP phase).
- [ ] `tui/session_bindings.py` (new file): Define `SESSION_BINDINGS` dict keyed by phase. Each phase maps to a list of `(key, action, label)` tuples. The app swaps bindings when phase changes via `self._bindings = [Binding(*b) for b in SESSION_BINDINGS[phase]]`.
- [ ] `tui/session_messages.py` (new file): Define message types for M1: `SessionStarted(session_id, project)`, `ContextAdded(entry_type, key, size)`, `PhaseAdvanced(from_phase, to_phase)`, `SessionError(error_message, phase)`
- [ ] `tui/session_app.py`: On `on_resize`, toggle CSS classes for responsive layout: `layout-stacked` below 80 cols (hide sidebar, show compact_phase_bar), default 2-column at 80+, `layout-wide` at 120+
- [ ] `tui/styles/theme.tcss`: Add styles for new session widgets — phase_list rows (phase-colored icons), context_list table, compact_phase_bar, file/note modal screens
- [ ] `tests/test_session_tui_shell.py` (new file): Test SessionTUI mounts with correct sidebar fields from mock session. Test PhaseList shows correct icons for each phase. Test ContextAdded message updates context_list and sidebar summary.
- [ ] `tests/test_session_tui_context.py` (new file): Test FileInputScreen validates existing file and rejects missing file. Test NoteInputScreen submits note content. Test `f` key pushes FileInputScreen, `Esc` dismisses. Test `d` key advances phase from CONTEXT to DISCUSSION.
- [ ] `tests/test_session_cli.py` (new file): Test `session --project X --tui` without textual prints install instructions. Test `session <bad-id> --tui` prints "Session not found".

### Deliverables
- [ ] `planner-auto session --project my-api --tui` creates a session and launches TUI with context manager
- [ ] `planner-auto session <id> --tui` resumes at the correct phase with existing context displayed
- [ ] `f` key opens file modal, validates path, adds to context list on success
- [ ] `n` key opens note modal, adds to context list on submit
- [ ] `d` key advances to DISCUSSION (main panel shows "Use CLI" fallback until M2)
- [ ] Phase list shows correct icons (`✓`/`▶`/`○`) and updates on phase change
- [ ] Small terminal (<80 cols) shows compact phase bar instead of sidebar
- [ ] `q` exits cleanly, session stays in current phase (resumable)
- [ ] `context_service.add_context_entry()` works as a standalone library function (no Click dependency)
- [ ] Existing `planner-auto add-context` CLI command still works (uses context_service internally)
- [ ] `session` command bypasses `PHASE_ALLOWED_COMMANDS` — works at any phase
- [ ] All existing 464 tests pass; 4 new test files pass (including `test_context_service.py`)

---

## Milestone 2: Discussion Mode

Interactive chat view in the TUI with per-message worker threads. Messages appear in real-time with role coloring and "thinking" indicator. Ctrl+D advances to PLANNING.

### Tasks
- [ ] `tui/widgets/chat_view.py` (new file): Scrollable widget showing message history. Each message: role label ("You:" in `$primary` green, "Claude:" in `$accent` cyan) + content text. Auto-scrolls to bottom on new message. Method `add_message(role, content)`. Method `show_thinking()` — appends animated "Claude: [thinking... Ns]" row with elapsed timer. Method `clear_thinking()` — removes the thinking row. Input area at bottom: single-line TextInput that captures Enter key.
- [ ] `tui/widgets/chat_view.py`: On mount, populate from existing messages in DB (read via `_rw_conn` on main thread — messages table query)
- [ ] `tui/session_app.py`: Wire DISCUSSION phase — when phase is DISCUSSION, mount `ChatView` as main panel content. On `Enter` in chat input: read input text, clear input, call `add_message("user", text)`, call `show_thinking()`, disable input, spawn `send_discuss_message(text)` worker
- [ ] `tui/session_app.py`: Add `send_discuss_message(content)` as `@work(thread=True)`: opens own `sqlite3.connect(db_path)`, calls `agents.discuss(session_id, conn, content, backend=...)`, commits both messages (user + assistant), posts `DiscussResponseReceived(response, latency_ms)`, closes conn in `finally`. On exception: posts `SessionError`.
- [ ] `tui/session_app.py`: On `DiscussResponseReceived` message: call `clear_thinking()`, call `add_message("assistant", response)`, re-enable input, log event to LogPanel ("Claude responded (N chars, N.Ns)")
- [ ] `tui/session_app.py`: On `SessionError` during discussion: call `clear_thinking()`, re-enable input, show error in LogPanel, do NOT crash — user can retry
- [ ] `tui/session_app.py`: Wire `Ctrl+D` keybinding in DISCUSSION phase: advance phase DISCUSSION → PLANNING via `SessionManager.advance_phase()`, post `PhaseAdvanced` message. If PLANNING is not yet implemented (this milestone), main panel shows "Use CLI" fallback.
- [ ] `tui/session_messages.py`: Add message types: `DiscussMessageSent(content, char_count)`, `DiscussResponseReceived(content, latency_ms)`, `DiscussThinking()`
- [ ] `tui/session_bindings.py`: Add DISCUSSION phase bindings: `Enter` → send message (handled by ChatView), `Ctrl+D` → done/advance, `e` → export, `l` → log filter, `q` → quit, `?` → help
- [ ] `tui/session_app.py`: Quit during DISCUSSION while worker is active: since per-message workers are short-lived (~2-5s), `q` can wait for the current worker to finish (same deferred pattern as review TUI but resolves much faster). If no worker active, quit immediately.
- [ ] `tui/styles/theme.tcss`: Add styles for chat_view — user messages green-tinted, assistant messages cyan-tinted, thinking indicator with muted animation, input area at bottom with border
- [ ] `tests/test_session_tui_discuss.py` (new file): Test ChatView renders existing messages from mock DB. Test sending a message posts DiscussResponseReceived (mock `agents.discuss`). Test thinking indicator appears and disappears. Test Ctrl+D advances phase. Test error during discuss re-enables input without crash. Test quit during active worker defers until worker completes.

### Deliverables
- [ ] Discussion phase shows scrollable message history with role coloring
- [ ] Typing a message and pressing Enter sends it, shows "thinking...", then shows Claude's response
- [ ] Input is disabled while Claude responds, re-enabled after
- [ ] Errors during discuss show in log panel but don't crash — user can retry
- [ ] Ctrl+D advances to PLANNING
- [ ] Existing messages load from DB on mount (resume scenario)
- [ ] `q` during active discussion worker waits for response before exiting
- [ ] All existing tests pass; 1 new test file passes

---

## Milestone 3: Planning + Review Embed + Completion

Generation progress display, plan view, embedded review dashboard using existing widgets, completion summary with artifacts. Worker owns finalize. Paused state is read-only.

### Tasks

**Planning/Generation:**
- [ ] `tui/widgets/generation_progress.py` (new file): Widget showing 2-step progress — "Step 1: Synthesizing context... ========.... Ns" and "Step 2: Generating plan... ========.... Ns". Each step shows model name, elapsed timer. Method `start_synthesis(file_count, note_count)`, `complete_synthesis(output_size, latency_ms)`, `start_generation(model)`, `complete_generation(draft_number, size, milestone_count, latency_ms)`.
- [ ] `tui/widgets/plan_view.py` (new file): Scrollable widget showing plan text with header info (Draft #N, size, milestone count, model, validation status). Method `set_plan(draft_number, content, model, validation_ok, warnings)`. Warnings shown in `$warning` yellow if any.
- [ ] `tui/session_app.py`: Wire PLANNING phase — on phase entry, mount `GenerationProgress`. On `g` key (or auto-generate on first entry): spawn `run_generate()` worker.
- [ ] `tui/session_app.py`: Add `run_generate()` as `@work(thread=True)`: opens own conn, calls `synthesize_context()` (posts `SynthesisStarted` → `SynthesisComplete`), calls `generate_plan()` (posts `PlanGenerationStarted` → `PlanGenerated`), closes conn in finally. On exception: posts `SessionError`.
- [ ] `tui/session_app.py`: On `PlanGenerated` message: replace GenerationProgress with PlanView showing the generated plan. Update sidebar PlanPanel (draft#, size, milestones). Log event. Show `r` key hint to start review.
- [ ] `tui/session_app.py`: On `g` key (regenerate): confirm via log message, re-mount GenerationProgress, spawn new `run_generate()` worker
- [ ] `tui/session_messages.py`: Add message types: `SynthesisStarted(file_count, note_count)`, `SynthesisComplete(output_size, latency_ms)`, `PlanGenerationStarted(model)`, `PlanGenerated(draft_number, size, milestone_count, latency_ms, validation_ok, warnings)`

**Review handler refactor (prerequisite for embedding):**
- [ ] `tui/review_handlers.py` (new file): Extract the review message handler logic from `tui/review_app.py` into a standalone mixin or helper class `ReviewHandlerMixin`. This class provides methods: `handle_round_started(msg, round_list, current_round, log_panel)`, `handle_review_complete(msg, round_list, convergence_panel, log_panel)`, `handle_feedback_validated(msg, current_round, log_panel)`, `handle_revision_started(msg, current_round)`, `handle_revision_complete(msg, plan_panel, current_round, log_panel)`, `handle_loop_finished(msg, session_panel, log_panel)`, `handle_revision_timeout(msg, current_round, log_panel)`. Each method takes the message + the target widgets as parameters — no `self.query_one()` calls, no coupling to a specific app's widget tree.
- [ ] `tui/review_app.py`: Refactor existing ReviewTUI message handlers to delegate to `ReviewHandlerMixin`. Each `on_X` handler calls `self._review_handlers.handle_X(msg, self.query_one(...), ...)`. Existing ReviewTUI behavior unchanged.
- [ ] `tests/test_review_handlers.py` (new file): Test each handler method with mock widgets. Verify ReviewTUI still works after refactor (run existing review TUI tests).

**Review embed:**
- [ ] `tui/session_app.py`: On `r` key in PLANNING phase: advance phase PLANNING → REVIEW, mount review widgets (RoundList, ConvergencePanel, CurrentRound, PlanPanel from existing `tui/widgets/`) into main panel. Instantiate `ReviewHandlerMixin` and wire message handlers to delegate to it with the mounted widgets.
- [ ] `tui/session_app.py`: Add `run_review_loop()` as `@work(thread=True)`: opens own conn, runs `ReviewWorkflow.prepare()`, creates `ReviewLoopEngine(conn=worker_conn, callbacks=adapter, verbosity="tui")`, calls `ReviewWorkflow.run(engine, plan, max_rounds)`. Then **always** calls `ReviewWorkflow.finalize(worker_conn, session_id, result, prepared)` — finalize handles both outcomes: on convergence it advances phase + exports + .kafra handoff; on cap+criticals it creates the blocker + pauses the session. Worker reads `FinalizeResult` and posts either `SessionCompleted(export_paths, kafra_path, total_cost)` if `finalize_result.converged` or `BlockerCreated(source, question, blocker_id)` if not. Closes conn in finally.
- [ ] `tui/session_app.py`: Reuse existing `TUIAdapter` from `tui/adapter.py` for review callbacks — same `RoundStarted`, `ReviewComplete`, `FeedbackValidated`, `RevisionStarted`, `RevisionComplete`, `LoopFinished`, `RevisionTimeout` messages
- [ ] **Final-event ownership contract:** `LoopFinished` (from engine callback) updates review widgets only (round list, convergence panel, log panel) via `ReviewHandlerMixin`. The worker then calls `finalize()` and posts `SessionCompleted` or `BlockerCreated`. Phase transitions (REVIEW→COMPLETE or REVIEW→PAUSED) are triggered by `SessionCompleted`/`BlockerCreated`, NOT by `LoopFinished`. This keeps review widget updates and session phase transitions as two separate responsibilities.
- [ ] `tui/session_app.py`: Review quit contract — same deferred quit as standalone ReviewTUI (`_quit_requested` flag, wait for current round to finish)

**Completion + paused:**
- [ ] `tui/widgets/result_summary.py` (new file): Widget showing completion summary using **only data currently available** — no phase durations or API call counts (these are not persisted). Shows: checkmarks for each step (plan approved, exported, .kafra handoff), review rounds count (queried from `reviews` table), total GPT review cost (from `SessionCompleted.total_cost`), final plan draft info (draft number, size, milestone count from `plan_drafts` table), artifact list with paths (from `SessionCompleted.export_paths`), .kafra handoff path. All DB queries use the main thread's read-only connection.
- [ ] `tui/session_app.py`: On `SessionCompleted` message: advance phase to COMPLETE, mount ResultSummary, update PhaseList, update sidebar. Log completion.
- [ ] `tui/session_app.py`: On `BlockerCreated` message: set phase to PAUSED (with `⚠` icon), mount read-only blocker display showing: blocker source, question text, CLI commands (`planner-auto resume <id>`, `planner-auto review <id> --max-rounds N`, `planner-auto complete <id>`). No interactive input — user must use CLI to resolve.
- [ ] `tui/session_messages.py`: Add message types: `SessionCompleted(export_paths, kafra_path, total_cost)`, `BlockerCreated(source, question, blocker_id)` — `blocker_id` is read from the blocker row created by `ReviewWorkflow.finalize()` (query `get_open_blockers()` after finalize returns, take the latest)
- [ ] `tui/session_bindings.py`: Add REVIEW phase bindings (reuse from review TUI: `d` dispositions, `p` plan, `l` log filter, Enter round detail, Escape back, `n`/`p` navigate, `r` raw response). Add COMPLETE phase bindings: `p` plan, `e` export, `c` copy plan path, `l` log filter, `q` quit.
- [ ] `tui/styles/theme.tcss`: Add styles for generation_progress steps, plan_view header, result_summary table/checkmarks, paused-state blocker display
- [ ] `tests/test_session_tui_planning.py` (new file): Test GenerationProgress shows synthesis + plan steps. Test PlanGenerated message mounts PlanView. Test `g` key triggers regeneration.
- [ ] `tests/test_session_tui_review.py` (new file): Test review widgets mount on REVIEW phase entry. Test LoopFinished updates review widgets only (via ReviewHandlerMixin), does NOT trigger phase transition. Test SessionCompleted mounts ResultSummary and advances phase to COMPLETE. Test BlockerCreated shows read-only blocker with CLI commands and stores blocker_id. Test quit during review uses deferred pattern.
- [ ] `tests/test_session_tui_complete.py` (new file): Test ResultSummary renders export paths and cost. Test COMPLETE phase bindings (p, e, c, q).

### Deliverables
- [ ] Full lifecycle in one TUI: start → context → discuss → generate → review → complete without exiting
- [ ] Generation shows 2-step progress (synthesis + plan) with elapsed timers
- [ ] Plan view shows draft text, milestone count, validation status
- [ ] `g` key regenerates plan; `r` key starts review
- [ ] `ReviewHandlerMixin` extracted — review handlers decoupled from ReviewTUI widget tree
- [ ] Standalone `planner-auto review <id> --tui` still works after handler refactor (no regressions)
- [ ] Review phase embeds existing review widgets via `ReviewHandlerMixin` — same experience as standalone
- [ ] On convergence: worker calls finalize, session completes, ResultSummary shows artifacts + cost
- [ ] On cap+criticals: paused state shows blocker + CLI commands (read-only, no interactive resolution)
- [ ] Quit during review defers until current round completes
- [ ] All existing tests pass; 4 new test files pass (including `test_review_handlers.py`)

---

## Milestone 4: Blocker Resolution from TUI

Inline blocker resolution — user answers the blocker question directly in the TUI instead of switching to CLI. Uses existing `session.py:resolve_and_resume()` semantics.

### Tasks
- [ ] `tui/screens/blocker_screen.py` (new file): Modal screen showing blocker details and answer input. Displays: blocker source (e.g., "reviewer"), question text (full, scrollable if long), TextArea for answer input. On Enter: submit answer. On Esc: dismiss without resolving (session stays paused).
- [ ] `tui/session_app.py`: On `BlockerCreated` message (updated from M3): instead of showing read-only blocker display, push `BlockerScreen` modal. User can answer or dismiss.
- [ ] `tui/session_app.py`: Store `self._blocker_id` from `BlockerCreated.blocker_id` when entering paused state. On blocker answer submitted: spawn `resolve_blocker()` as `@work(thread=True)`. Worker opens conn, calls `SessionManager.resolve_and_resume(session_id, self._blocker_id, answer)` (same function CLI `resume` uses), commits. If session status returns to ACTIVE: posts `BlockerResolved`. Closes conn in finally.
- [ ] `tui/session_app.py`: On `BlockerResolved` message: dismiss BlockerScreen, update PhaseList (remove `⚠` icon, restore previous phase as active), update sidebar status to ACTIVE, log "Blocker resolved. Session resumed." Session returns to the phase it was in before pausing. User can then take the next action from the TUI (e.g., `r` to start a new review run, `q` to quit). No automatic re-entry into review — user decides.
- [ ] `tui/session_messages.py`: Add `BlockerResolved` message type
- [ ] `tui/session_bindings.py`: Update PAUSED bindings — replace read-only bindings with `Enter` → open blocker screen, `q` → quit paused
- [ ] `tests/test_session_tui_blocker.py` (new file): Test BlockerScreen renders question and accepts answer. Test submitting answer calls `resolve_and_resume()`. Test dismissing with Esc keeps session paused. Test BlockerResolved updates phase icons and status.

### Deliverables
- [ ] Paused state shows blocker question with answer input (not just CLI commands)
- [ ] Submitting an answer resolves the blocker and resumes the session
- [ ] Dismissing the modal keeps the session paused (safe exit)
- [ ] Resolved blocker updates phase icons and session status in real-time
- [ ] Uses same `resolve_and_resume()` as CLI `resume` command — no new product semantics
- [ ] All existing tests pass; 1 new test file passes
