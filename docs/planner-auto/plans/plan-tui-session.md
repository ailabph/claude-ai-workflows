# TUI Session Mode - Implementation Plan

## Overview

Add a full-lifecycle Session TUI to planner-auto via `planner-auto session --project my-api --tui`. One persistent dashboard from start to complete: context management, interactive discussion, plan generation, embedded review, and completion summary. Phase-driven layout — sidebar stays constant, main panel switches per phase.

**Reference:** `docs/planner-auto/plans/proposal-tui-session.md` (v2)

**Key constraints:**
- Per-operation workers, not a single long-lived worker (context: no worker, discuss: per-message, generate: one-shot, review: long-running)
- Worker thread owns finalize during review (different from standalone ReviewTUI where CLI owns finalize)
- Paused/blocker state is read-only until Milestone 4 (shows blocker + CLI commands)
- Reuses existing review widgets (RoundList, ConvergencePanel, CurrentRound) — does not launch a separate ReviewTUI
- Each milestone is independently shippable — unimplemented phases show "Use CLI for X" fallback

---

## Milestone 1: Session Shell + Context Manager

Persistent TUI shell with sidebar (session info + phase progress), context manager (file/note add modals), CLI `session` command, and phase-aware keybinding foundation. No worker threads — all context operations run on the TUI main thread.

### Tasks
- [ ] `cli.py`: Add `session` command with two invocation patterns: `planner-auto session --project <name> --tui` (create new) and `planner-auto session <session-id> --tui` (resume existing). When `--tui` is not passed, print "Session TUI requires --tui flag" and exit (no CLI-only session mode yet). Lazy import of `planner_auto.tui.session_app`; print install instructions if textual not installed.
- [ ] `cli.py`: In the `session` command's `--tui` path: if creating new, call `create_session()` + `save_session_config()` (same logic as `start` command). If resuming, load session from DB and validate it exists. Pass `session_id` + `db_path` to `SessionTUI`. After `app.run()` returns, read `app.exit_code` for shell return (0=normal, 1=error).
- [ ] `tui/session_app.py` (new file): Create `SessionTUI(App)` class:
  - `__init__` accepts `session_id: str`, `db_path: str`
  - `TITLE`, `CSS_PATH` (reuse `theme.tcss`), `BINDINGS` (phase-aware)
  - `compose()` yields: Header + 2-column grid (left sidebar container with SessionPanel + PhaseList + context summary + right main panel container) + LogPanel + Footer
  - `on_mount()`: open read-write connection (`self._rw_conn`), read session from DB, populate SessionPanel fields, populate PhaseList with current phase, populate context list from `context_entries` table, set initial main panel content based on current phase
  - `self._current_phase: str` tracks active phase for keybinding switching
  - `self.exit_code: int = 0` for CLI handoff
  - `action_quit()`: quit immediately (no deferred quit in context/discussion phases)
- [ ] `tui/session_app.py`: Implement phase-aware main panel switching — when phase changes, unmount current main panel content and mount the new phase's widget. For unimplemented phases (DISCUSSION, PLANNING, REVIEW in M1), mount a Static widget showing "Use CLI: planner-auto <command> <session-id>"
- [ ] `tui/session_app.py`: On `ContextAdded` message, update context summary in sidebar (file count, note count, total size) and append entry to context_list widget
- [ ] `tui/session_app.py`: On `PhaseAdvanced` message, update PhaseList icons and switch main panel content
- [ ] `tui/widgets/phase_list.py` (new file): Vertical widget showing 6 phases with status icons (`✓` completed, `▶` active, `○` pending, `⚠` paused). Each phase row shows: icon + phase name + optional count (e.g., "CONTEXT (4)"). Method `update_phase(phase, icon)` updates a single row. Method `set_active(phase)` highlights the current phase.
- [ ] `tui/widgets/compact_phase_bar.py` (new file): Single-line widget for small terminals (<80 cols). Renders as `✓ ✓ ▶ ○ ○ ○  4ctx  6msg  $0.00`. Shows phase icons inline + key metrics. Method `update(phases, context_count, message_count, cost)`.
- [ ] `tui/widgets/context_list.py` (new file): Scrollable list showing context entries. Each row: `#  Type  Path/Content  Size`. Types: `file` (shows path), `note` (shows first 40 chars), `synthesis` (shows "auto-generated"). Method `add_entry(entry_type, key, size)`. Method `get_total_size() -> int`.
- [ ] `tui/screens/file_input_screen.py` (new file): Modal screen with single-line text input for file path. On submit: validates file exists, is readable, is <500KB, is UTF-8. On validation pass: reads content, calls `add_context()` on the main thread's `_rw_conn`, posts `ContextAdded` message, dismisses modal. On validation fail: shows error inline, keeps modal open.
- [ ] `tui/screens/note_input_screen.py` (new file): Modal screen with multiline TextArea for note content. On submit: posts `ContextAdded` message after writing to DB via `_rw_conn`. Dismiss on submit or Esc.
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
- [ ] All existing 464 tests pass; 3 new test files pass

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

**Review embed:**
- [ ] `tui/session_app.py`: On `r` key in PLANNING phase: advance phase PLANNING → REVIEW, mount review widgets (RoundList, ConvergencePanel, CurrentRound, PlanPanel from existing `tui/widgets/`) into main panel. Spawn `run_review_loop()` worker.
- [ ] `tui/session_app.py`: Add `run_review_loop()` as `@work(thread=True)`: opens own conn, runs `ReviewWorkflow.prepare()` to resolve complexity/cap/reviewer/config, creates `ReviewLoopEngine(conn=worker_conn, callbacks=adapter, verbosity="tui")`, calls `ReviewWorkflow.run(engine, plan, max_rounds)`. On convergence: calls `ReviewWorkflow.finalize(worker_conn, session_id, result, prepared)` — **worker owns finalize**. Posts `SessionCompleted(export_paths, kafra_path, total_cost)`. On cap+criticals: posts `BlockerCreated(source, question)`. Closes conn in finally.
- [ ] `tui/session_app.py`: Reuse existing `TUIAdapter` from `tui/adapter.py` for review callbacks — same `RoundStarted`, `ReviewComplete`, `FeedbackValidated`, `RevisionStarted`, `RevisionComplete`, `LoopFinished`, `RevisionTimeout` messages
- [ ] `tui/session_app.py`: Reuse existing review message handlers from ReviewTUI — `on_round_started`, `on_review_complete`, etc. These update RoundList, ConvergencePanel, CurrentRound, PlanPanel. Same handlers, mounted into the session app's main panel instead of ReviewTUI's main panel.
- [ ] `tui/session_app.py`: Review quit contract — same deferred quit as standalone ReviewTUI (`_quit_requested` flag, wait for current round to finish)

**Completion + paused:**
- [ ] `tui/widgets/result_summary.py` (new file): Widget showing completion summary — checkmarks for each step (plan approved, exported, .kafra handoff), session summary table (phase durations, API call counts, total cost), artifact list with paths. Populated from `SessionCompleted` message fields.
- [ ] `tui/session_app.py`: On `SessionCompleted` message: advance phase to COMPLETE, mount ResultSummary, update PhaseList, update sidebar. Log completion.
- [ ] `tui/session_app.py`: On `BlockerCreated` message: set phase to PAUSED (with `⚠` icon), mount read-only blocker display showing: blocker source, question text, CLI commands (`planner-auto resume <id>`, `planner-auto review <id> --max-rounds N`, `planner-auto complete <id>`). No interactive input — user must use CLI to resolve.
- [ ] `tui/session_messages.py`: Add message types: `SessionCompleted(export_paths, kafra_path, total_cost)`, `BlockerCreated(source, question)`
- [ ] `tui/session_bindings.py`: Add REVIEW phase bindings (reuse from review TUI: `d` dispositions, `p` plan, `l` log filter, Enter round detail, Escape back, `n`/`p` navigate, `r` raw response). Add COMPLETE phase bindings: `p` plan, `e` export, `c` copy plan path, `l` log filter, `q` quit.
- [ ] `tui/styles/theme.tcss`: Add styles for generation_progress steps, plan_view header, result_summary table/checkmarks, paused-state blocker display
- [ ] `tests/test_session_tui_planning.py` (new file): Test GenerationProgress shows synthesis + plan steps. Test PlanGenerated message mounts PlanView. Test `g` key triggers regeneration.
- [ ] `tests/test_session_tui_review.py` (new file): Test review widgets mount on REVIEW phase entry. Test LoopFinished(converged=True) posts SessionCompleted and mounts ResultSummary. Test LoopFinished(cap_with_criticals) shows read-only blocker with CLI commands. Test quit during review uses deferred pattern.
- [ ] `tests/test_session_tui_complete.py` (new file): Test ResultSummary renders export paths and cost. Test COMPLETE phase bindings (p, e, c, q).

### Deliverables
- [ ] Full lifecycle in one TUI: start → context → discuss → generate → review → complete without exiting
- [ ] Generation shows 2-step progress (synthesis + plan) with elapsed timers
- [ ] Plan view shows draft text, milestone count, validation status
- [ ] `g` key regenerates plan; `r` key starts review
- [ ] Review phase embeds existing review widgets — same experience as standalone `planner-auto review <id> --tui`
- [ ] On convergence: worker calls finalize, session completes, ResultSummary shows artifacts + cost
- [ ] On cap+criticals: paused state shows blocker + CLI commands (read-only, no interactive resolution)
- [ ] Quit during review defers until current round completes
- [ ] Standalone `planner-auto review <id> --tui` still works (no regressions)
- [ ] All existing tests pass; 3 new test files pass

---

## Milestone 4: Blocker Resolution from TUI

Inline blocker resolution — user answers the blocker question directly in the TUI instead of switching to CLI. Uses existing `session.py:resolve_and_resume()` semantics.

### Tasks
- [ ] `tui/screens/blocker_screen.py` (new file): Modal screen showing blocker details and answer input. Displays: blocker source (e.g., "reviewer"), question text (full, scrollable if long), TextArea for answer input. On Enter: submit answer. On Esc: dismiss without resolving (session stays paused).
- [ ] `tui/session_app.py`: On `BlockerCreated` message (updated from M3): instead of showing read-only blocker display, push `BlockerScreen` modal. User can answer or dismiss.
- [ ] `tui/session_app.py`: On blocker answer submitted: spawn `resolve_blocker()` as `@work(thread=True)`. Worker opens conn, calls `SessionManager.resolve_and_resume(session_id, blocker_id, answer)` (same function CLI `resume` uses), commits. If session status returns to ACTIVE: posts `BlockerResolved`. Closes conn in finally.
- [ ] `tui/session_app.py`: On `BlockerResolved` message: dismiss BlockerScreen, update PhaseList (remove `⚠` icon), update sidebar status to ACTIVE, log "Blocker resolved. Session resumed." If the blocker was from the review cap: prompt user whether to continue review (spawn new review worker with extended rounds) or complete the session.
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
