# TUI Proposal — Session Mode (Full Lifecycle)

## Problem

The current planner-auto workflow requires switching between multiple CLI commands across a terminal session:

```bash
planner-auto start --project my-api
planner-auto add-context abc123 --file src/app.py
planner-auto add-context abc123 --file src/models.py
planner-auto add-context abc123 --note "Uses PostgreSQL, deployed on AWS"
planner-auto discuss abc123 --interactive
# ... type messages, /done ...
planner-auto generate abc123
planner-auto review abc123 --tui    # <-- only this has a TUI
planner-auto complete abc123
```

The user must remember the session ID, re-type it for every command, mentally track which phase they're in, and switch between bare CLI output and the review TUI. There's no unified visual context across the session lifecycle.

## Goal

A single TUI that covers the full session lifecycle: start → add context → discuss → generate → review → complete. The user launches once and drives the entire workflow from a persistent dashboard, with phase-appropriate panels and interactions.

```bash
planner-auto session --project my-api --tui
# OR resume an existing session:
planner-auto session abc123 --tui
```

## Scope

**In scope:** Full session lifecycle TUI — one app from start to complete.

**Out of scope:**
- Multi-session management (one session per TUI instance)
- Replacing the CLI (TUI is opt-in, CLI commands continue to work)
- Inspector TUI (read-only post-hoc analysis — separate proposal)

## Design Principles

Same as the Review Dashboard TUI (v0.5.0):
1. Thread-safe message passing (worker thread + `call_from_thread`)
2. Progressive disclosure (at-a-glance → expand → deep dive)
3. Status-based color coding (green/cyan/yellow/red/gray)
4. Responsive layout (3 breakpoints: <80, 80-119, 120+)
5. Fail-safe widget updates (`is_mounted` checks, `--` for missing data)
6. Reuse existing widgets (SessionPanel, LogPanel, theme.tcss)

**Additional principle for session TUI:**
7. **Phase-driven layout** — the main panel changes based on the current phase. The sidebar stays constant (session info + phase progress). Navigation between phases follows the lifecycle rules.

---

## Modes (Phase-Driven Screens)

The TUI has one persistent layout with a phase-aware main panel. As the session progresses through phases, the main panel switches content:

| Phase | Main Panel | User Interactions |
|-------|-----------|-------------------|
| SETUP | Welcome + quick actions | Start session (auto) |
| CONTEXT | File/note list + add actions | Add file, add note, advance |
| DISCUSSION | Chat view + input | Type messages, /done |
| PLANNING | Generation progress → plan view | Generate, view plan |
| REVIEW | Review dashboard (existing) | Watch rounds, drill-down |
| COMPLETE | Result summary | Export, copy plan path |

---

## Layout Designs

### Persistent Shell (all phases)

The sidebar and footer are constant. The main panel content changes per phase.

```
+------------------------------------------------------------------------------+
|  planner-auto session -- my-api (abc123)                        DISCUSSION   |
+--------------------+---------------------------------------------------------+
|  SESSION           |                                                         |
|                    |  (Main panel content changes per phase)                 |
|  ID: abc123        |                                                         |
|  Project: my-api   |                                                         |
|  Backend: direct   |                                                         |
|  Status: ACTIVE    |                                                         |
|                    |                                                         |
|  PHASES            |                                                         |
|                    |                                                         |
|  ok SETUP          |                                                         |
|  ok CONTEXT (3)    |                                                         |
|  >> DISCUSSION (4) |                                                         |
|  oo PLANNING       |                                                         |
|  oo REVIEW         |                                                         |
|  oo COMPLETE       |                                                         |
|                    |                                                         |
|  CONTEXT           |                                                         |
|                    |                                                         |
|  3 files, 76KB     |                                                         |
|  1 note            |                                                         |
|                    |                                                         |
+--------------------+---------------------------------------------------------+
|  LOG                                                                         |
|  10:23:15 Context added: src/app.py (44K chars)                             |
|  10:23:18 Context added: src/models.py (24K chars)                          |
|  10:24:01 Phase advanced: CONTEXT -> DISCUSSION                             |
+------------------------------------------------------------------------------+
|  [a]dd context  [d]one  [p]lan  [e]xport  [q]uit           DISCUSSION >>   |
+------------------------------------------------------------------------------+
```

### Phase Icons

| Icon | Meaning |
|------|---------|
| `ok` | Completed phase (rendered as `✓` in Unicode) |
| `>>` | Current active phase (rendered as `▶`) |
| `oo` | Pending phase (rendered as `○`) |
| `!!` | Paused/blocked phase (rendered as `⚠`) |

---

### Mode 1: Context Manager (SETUP/CONTEXT phase)

```
+------------------------------------------------------------------------------+
|  planner-auto session -- my-api (abc123)                           CONTEXT   |
+--------------------+---------------------------------------------------------+
|  SESSION           |  CONTEXT FILES                                          |
|                    |                                                         |
|  (sidebar)         |  #  Type  Path / Content                   Size        |
|                    |  1  file  src/app.py                       44,102 ch   |
|  PHASES            |  2  file  src/models.py                    24,343 ch   |
|                    |  3  file  src/routes.py                     8,291 ch   |
|  ok SETUP          |  4  note  "Uses PostgreSQL, deployed..."      42 ch   |
|  >> CONTEXT (4)    |                                                         |
|  oo DISCUSSION     |  Total: 76,778 chars (3 files, 1 note)                 |
|  oo PLANNING       |                                                         |
|  oo REVIEW         |  ─────────────────────────────────────────────────────  |
|  oo COMPLETE       |  QUICK ACTIONS                                          |
|                    |                                                         |
|  CONTEXT           |  Press [f] to add a file                                |
|                    |  Press [n] to add a note                                |
|  4 entries, 76KB   |  Press [d] to start discussion                          |
|                    |                                                         |
+--------------------+---------------------------------------------------------+
|  LOG                                                                         |
|  10:23:15 Session created: abc123 (project: my-api, backend: direct)        |
|  10:23:15 Phase: SETUP -> CONTEXT                                           |
|  10:23:18 Context added: src/app.py (44,102 chars)                          |
+------------------------------------------------------------------------------+
|  [f]ile  [n]ote  [d]iscuss  [e]xport  [q]uit                  CONTEXT >>   |
+------------------------------------------------------------------------------+
```

#### Add File Modal

```
+----------------------------------------------+
|  Add Context File                            |
|                                              |
|  Path: src/services/auth.py                  |
|  [text input field]                          |
|                                              |
|  [Enter] Add  |  [Esc] Cancel                |
+----------------------------------------------+
```

#### Add Note Modal

```
+----------------------------------------------+
|  Add Context Note                            |
|                                              |
|  Note:                                       |
|  [multiline text area]                       |
|  Uses PostgreSQL 15 with pgvector            |
|  extension for embeddings. Deployed on       |
|  AWS ECS with RDS.                           |
|                                              |
|  [Enter] Add  |  [Esc] Cancel                |
+----------------------------------------------+
```

---

### Mode 2: Discussion (DISCUSSION phase)

```
+------------------------------------------------------------------------------+
|  planner-auto session -- my-api (abc123)                        DISCUSSION   |
+--------------------+---------------------------------------------------------+
|  SESSION           |  CONVERSATION                                           |
|                    |                                                         |
|  (sidebar)         |  You: Add user registration with email validation       |
|                    |       and password hashing. Should support OAuth         |
|  PHASES            |       providers as a future option.                     |
|                    |                                                         |
|  ok SETUP          |  Claude: I have a few questions before we plan:         |
|  ok CONTEXT (4)    |                                                         |
|  >> DISCUSSION (4) |  1. For email validation, do you want just format       |
|  oo PLANNING       |     checking or deliverability verification?            |
|  oo REVIEW         |                                                         |
|  oo COMPLETE       |  2. For password hashing, bcrypt or argon2id?           |
|                    |                                                         |
|  CONTEXT           |  3. Should the data model account for OAuth             |
|                    |     provider IDs now, or defer?                         |
|  4 entries, 76KB   |                                                         |
|                    |  You: Bcrypt is fine. Defer OAuth columns for now.      |
|  MESSAGES          |       Format-only email validation.                     |
|                    |                                                         |
|  4 messages        |  Claude: Got it. One more question...                   |
|  2 user, 2 asst    |                                                         |
|                    |---------------------------------------------------------|
|                    |  You: [text input]                                      |
|                    |                                                         |
+--------------------+---------------------------------------------------------+
|  LOG                                                                         |
|  10:25:01 Message sent (42 chars)                                           |
|  10:25:04 Claude responded (318 chars, 2.8s)                                |
+------------------------------------------------------------------------------+
|  Type message, Enter to send  |  [Ctrl+D] done -> planning  |  [q]uit      |
+------------------------------------------------------------------------------+
```

#### Claude Responding State

```
|                    |  You: Bcrypt is fine. Defer OAuth for now.              |
|                    |                                                         |
|                    |  Claude: [thinking... 2.3s]                             |
|                    |                                                         |
|                    |---------------------------------------------------------|
|                    |  (input disabled while Claude responds)                 |
```

---

### Mode 3: Planning (PLANNING phase)

#### Generating State

```
+------------------------------------------------------------------------------+
|  planner-auto session -- my-api (abc123)                          PLANNING   |
+--------------------+---------------------------------------------------------+
|  SESSION           |  PLAN GENERATION                                        |
|                    |                                                         |
|  (sidebar)         |  Step 1: Synthesizing context...  ========....  2.1s    |
|                    |    4 files + 1 note -> Haiku synthesis                  |
|  PHASES            |                                                         |
|                    |  Step 2: Generating plan...  (waiting for Step 1)       |
|  ok SETUP          |    Model: claude-sonnet-4-6                             |
|  ok CONTEXT (4)    |                                                         |
|  ok DISCUSSION (6) |                                                         |
|  >> PLANNING       |                                                         |
|  oo REVIEW         |                                                         |
|  oo COMPLETE       |                                                         |
|                    |                                                         |
+--------------------+---------------------------------------------------------+
```

#### Plan Ready State

```
+------------------------------------------------------------------------------+
|  planner-auto session -- my-api (abc123)                          PLANNING   |
+--------------------+---------------------------------------------------------+
|  SESSION           |  PLAN (Draft #1)                                        |
|                    |                                                         |
|  (sidebar)         |  ## Milestone 1: Database Schema + User Model           |
|                    |                                                         |
|  PHASES            |  ### Tasks                                               |
|                    |  - [ ] Create User model with email, password_hash     |
|  ok SETUP          |  - [ ] Add unique constraint on email                   |
|  ok CONTEXT (4)    |  - [ ] Create migration script                          |
|  ok DISCUSSION (6) |  - [ ] Write model unit tests                           |
|  >> PLANNING       |                                                         |
|  oo REVIEW         |  ### Deliverables                                        |
|  oo COMPLETE       |  - [ ] models.py updated                                |
|                    |  - [ ] migration created                                |
|                    |  - [ ] 5+ tests passing                                 |
|  PLAN              |                                                         |
|                    |  ## Milestone 2: Password Hashing + Registration        |
|  Draft: #1         |  ...                                                    |
|  Size: 2,847 ch    |                                                         |
|  Milestones: 4     |  Validation: OK                                         |
|  Model: sonnet     |                                                         |
|                    |                                                         |
+--------------------+---------------------------------------------------------+
|  LOG                                                                         |
|  10:26:01 Synthesis complete (1,247 chars, 1.8s)                            |
|  10:26:08 Plan generated: 4 milestones, 2,847 chars (6.2s)                  |
|  10:26:08 Plan format validation: OK                                        |
+------------------------------------------------------------------------------+
|  [r]eview  [g]enerate again  [p]lan fullscreen  [e]xport  [q]uit  PLANNING  |
+------------------------------------------------------------------------------+
```

---

### Mode 4: Review (REVIEW phase)

This delegates to the existing ReviewTUI widgets. The sidebar stays, but the main panel becomes the review dashboard.

```
+------------------------------------------------------------------------------+
|  planner-auto session -- my-api (abc123)                            REVIEW   |
+--------------------+---------------------------------------------------------+
|  SESSION           |  ROUND PROGRESS                                         |
|                    |                                                         |
|  (sidebar)         |  R1  ok NO_GO  3 issues  ------------------- $0.038    |
|                    |  R2  ok NO_GO  1 issue   ------------------- $0.055    |
|  PHASES            |  R3  >> reviewing...      ---------- 45s               |
|                    |                                                         |
|  ok SETUP          |---------------------------------------------------------|
|  ok CONTEXT (4)    |  CURRENT ROUND (3)                                      |
|  ok DISCUSSION (6) |                                                         |
|  ok PLANNING       |  Phase: GPT reviewing...  ============....  45s        |
|  >> REVIEW         |  Reviewer: gpt-5.4 (reasoning=high)                    |
|  oo COMPLETE       |  Plan size: 3,241 chars                                |
|                    |  History: 6,872 chars                                   |
|  CONVERGENCE       |                                                         |
|                    |                                                         |
|  Issues: 3>1>_     |                                                         |
|  Trend: ||.|       |                                                         |
|  GPT cost: $0.093  |                                                         |
|                    |                                                         |
+--------------------+---------------------------------------------------------+
|  LOG                                                                         |
|  10:27:12 [R2] NO_GO -- 1 issue (1 ACCEPT)                                 |
|  10:28:03 [R2] Revised: 3,102 -> 3,241 chars (+139)                        |
|  10:28:03 [R3] Starting review...                                           |
+------------------------------------------------------------------------------+
|  [d]ispos  [p]lan  [l]og filter  [q]uit                          R3/8 >>   |
+------------------------------------------------------------------------------+
```

---

### Mode 5: Complete (COMPLETE phase)

```
+------------------------------------------------------------------------------+
|  planner-auto session -- my-api (abc123)              [OK] COMPLETE  12:34   |
+--------------------+---------------------------------------------------------+
|  SESSION           |  SESSION COMPLETE                                        |
|                    |                                                         |
|  (sidebar)         |  [OK] Plan approved by GPT (GO at round 4)             |
|                    |  [OK] Final plan: Draft #5 (3,892 chars, 4 milestones) |
|  PHASES            |  [OK] Exported 9 artifacts                              |
|                    |  [OK] .kafra handoff: .kafra/a-01-plans/my-api.md      |
|  ok SETUP          |                                                         |
|  ok CONTEXT (4)    |  SESSION SUMMARY                                        |
|  ok DISCUSSION (6) |                                                         |
|  ok PLANNING       |  Phase       Duration    API Calls                      |
|  ok REVIEW (4 rds) |  Context     1m 12s      0                              |
|  ok COMPLETE       |  Discussion  3m 45s      4 (Claude)                     |
|                    |  Planning    8s          2 (Haiku + Sonnet)             |
|  TOTAL             |  Review      4m 22s      8 (GPT) + 3 (Claude)           |
|                    |  ──────────────────────────────────                     |
|  Duration: 9m 27s  |  Total       9m 27s      $0.34                          |
|  Cost: $0.34       |                                                         |
|  Messages: 6       |  ARTIFACTS                                              |
|  Review: 4 rounds  |                                                         |
|                    |  ~/.planner-auto/sessions/abc123/                       |
|                    |    chat.csv                                             |
|                    |    context-summary.md                                   |
|                    |    a-01-plan.md                                         |
|                    |    a-02-review.md                                       |
|                    |    ...                                                  |
|                    |    a-07-plan-final.md                                   |
|                    |                                                         |
+--------------------+---------------------------------------------------------+
|  [p]lan  [e]xport again  [c]opy plan path  [q]uit              [OK] DONE   |
+------------------------------------------------------------------------------+
```

---

### Mode 6: Paused State (any phase)

```
+------------------------------------------------------------------------------+
|  planner-auto session -- my-api (abc123)                    [!!] PAUSED      |
+--------------------+---------------------------------------------------------+
|  SESSION           |  SESSION PAUSED                                         |
|                    |                                                         |
|  (sidebar)         |  [!!] Blocker from: reviewer                           |
|                    |                                                         |
|  PHASES            |  Question:                                              |
|                    |    "Review cap reached. Critical issues remaining:      |
|  ok SETUP          |     - SQL injection risk in project name passed to     |
|  ok CONTEXT (4)    |       raw query in discover_repo_root"                 |
|  ok DISCUSSION (6) |                                                         |
|  ok PLANNING       |  ─────────────────────────────────────────────────────  |
|  !! REVIEW (R8/8)  |                                                         |
|  oo COMPLETE       |  Your answer:                                           |
|                    |  [text input area]                                      |
|  BLOCKER           |                                                         |
|                    |  [Enter] Submit answer and resume                       |
|  !! 1 open blocker |  [Esc] Keep paused and quit                            |
|                    |                                                         |
+--------------------+---------------------------------------------------------+
|  LOG                                                                         |
|  10:45:22 Review cap reached at round 8 with critical issues               |
|  10:45:22 Session paused. Blocker: SQL injection risk...                    |
+------------------------------------------------------------------------------+
|  Answer blocker to resume  |  [Esc] quit paused  |  [q]uit        !! R8/8   |
+------------------------------------------------------------------------------+
```

---

### Small Terminal (<80 columns) — Stacked Layout

```
+----------------------------------------------+
|  planner-auto -- abc123      DISCUSSION >>   |
+----------------------------------------------+
|  ok ok >> oo oo oo  4ctx  6msg  $0.00        |
+----------------------------------------------+
|  You: Add user registration with email       |
|       validation and password hashing.       |
|                                              |
|  Claude: I have a few questions:             |
|  1. Format-only or deliverability check?     |
|  2. Bcrypt or argon2id?                      |
|                                              |
|  You: Bcrypt. Format-only email.             |
|                                              |
|  Claude: Got it. One more...                 |
|                                              |
|----------------------------------------------|
|  You: [input]                                |
+----------------------------------------------+
|  10:25:04 Claude responded (2.8s)            |
+----------------------------------------------+
|  Enter=send  Ctrl+D=done  q=quit   DISC >>   |
+----------------------------------------------+
```

The compact phase bar `ok ok >> oo oo oo` replaces the full sidebar. Each phase is an icon: `✓ ✓ ▶ ○ ○ ○`.

---

## Architecture

### Component Hierarchy

```
planner_auto/tui/
+-- session_app.py           # SessionTUI — main app, phase-driven layout
+-- session_adapter.py       # SessionTUIAdapter — worker -> TUI bridge
+-- session_messages.py      # Session-specific message types
+-- session_bindings.py      # Phase-aware keybindings
+-- widgets/
|   +-- session_panel.py     # REUSE from review TUI
|   +-- log_panel.py         # REUSE from review TUI
|   +-- phase_list.py        # NEW — sidebar phase progress (ok/>>/ oo/!!)
|   +-- context_list.py      # NEW — file/note list with sizes
|   +-- chat_view.py         # NEW — scrollable message history with input
|   +-- plan_view.py         # NEW — plan text with milestone count + validation
|   +-- generation_progress.py  # NEW — synthesis + plan generation progress
|   +-- review_embed.py      # REUSE review widgets (RoundList, ConvergencePanel, etc.)
|   +-- result_summary.py    # NEW — completion summary with artifacts
|   +-- compact_phase_bar.py # NEW — inline phase icons for small terminals
+-- screens/
|   +-- file_input_screen.py    # NEW — modal for file path input
|   +-- note_input_screen.py    # NEW — modal for multiline note
|   +-- blocker_screen.py       # NEW — blocker question + answer input
|   +-- plan_screen.py          # REUSE from review TUI
|   +-- disposition_screen.py   # REUSE from review TUI
|   +-- help_screen.py          # REUSE from review TUI (extended bindings)
|   +-- raw_response_screen.py  # REUSE from review TUI
```

### Message Types

```python
# session_messages.py

# Phase lifecycle
class SessionStarted(Message):
    session_id: str
    project: str

class PhaseAdvanced(Message):
    from_phase: str
    to_phase: str

# Context
class ContextAdded(Message):
    entry_type: str       # "file" or "note"
    key: str              # path or note key
    size: int             # char count

# Discussion
class DiscussMessageSent(Message):
    content: str
    char_count: int

class DiscussResponseReceived(Message):
    content: str
    latency_ms: int

class DiscussThinking(Message):
    """Claude is generating a response."""
    pass

# Planning
class SynthesisStarted(Message):
    file_count: int
    note_count: int

class SynthesisComplete(Message):
    output_size: int
    latency_ms: int

class PlanGenerationStarted(Message):
    model: str

class PlanGenerated(Message):
    draft_number: int
    size: int
    milestone_count: int
    latency_ms: int
    validation_ok: bool
    warnings: list[str]

# Review — reuse existing messages from messages.py
# (RoundStarted, ReviewComplete, etc.)

# Completion
class SessionCompleted(Message):
    export_paths: list[str]
    kafra_path: str | None
    total_cost: float

# Errors
class SessionError(Message):
    error_message: str
    phase: str

# Blocker
class BlockerCreated(Message):
    source: str
    question: str

class BlockerResolved(Message):
    pass
```

### Worker Thread Model

The session TUI runs a single worker thread that drives the full lifecycle. Unlike the review TUI (one-shot engine call), the session worker manages multiple phases:

```python
@work(thread=True)
def run_session(self) -> None:
    worker_conn = sqlite3.connect(self._db_path)
    try:
        # Phase: CONTEXT (wait for user to add files + signal done)
        # User interactions happen via input events, not in the worker
        # Worker is idle during CONTEXT — user drives via keybindings

        # Phase: DISCUSSION (interactive loop)
        # Each message: worker calls discuss(), posts response
        # User triggers /done via Ctrl+D keybinding

        # Phase: PLANNING
        self._dispatch("on_synthesis_started", ...)
        synthesis = synthesize_context(session_id, worker_conn, ...)
        self._dispatch("on_synthesis_complete", ...)

        self._dispatch("on_plan_generation_started", ...)
        plan = generate_plan(session_id, worker_conn, ...)
        self._dispatch("on_plan_generated", ...)

        # Phase: REVIEW (delegates to ReviewLoopEngine)
        engine = ReviewLoopEngine(conn=worker_conn, callbacks=...)
        result = ReviewWorkflow.run(engine, plan, max_rounds)

        # Phase: COMPLETE
        finalize_result = ReviewWorkflow.finalize(worker_conn, ...)
        self._dispatch("on_session_completed", ...)
    except Exception as e:
        self._dispatch("on_error", str(e), current_phase)
    finally:
        worker_conn.close()
```

**Key difference from review TUI:** The worker has idle periods (context, discussion) where it waits for user input. During these phases, the worker thread is parked on a `threading.Event` and the TUI main thread handles user interactions. The worker wakes up when the user triggers a phase transition.

### Input Bridge (for Discussion)

```python
class SessionInputBridge:
    """Bridges TUI input to worker thread during discussion phase."""

    def __init__(self):
        self._event = threading.Event()
        self._message: str | None = None
        self._done: bool = False

    def send_message(self, content: str) -> None:
        """Called from TUI main thread when user presses Enter."""
        self._message = content
        self._event.set()

    def signal_done(self) -> None:
        """Called from TUI main thread when user presses Ctrl+D."""
        self._done = True
        self._event.set()

    def wait_for_input(self) -> tuple[str | None, bool]:
        """Called from worker thread. Blocks until input arrives."""
        self._event.wait()
        self._event.clear()
        return self._message, self._done
```

### Phase-Aware Keybindings

Keybindings change based on the current phase:

| Key | CONTEXT | DISCUSSION | PLANNING | REVIEW | COMPLETE |
|-----|---------|-----------|----------|--------|----------|
| `f` | Add file | -- | -- | -- | -- |
| `n` | Add note | -- | -- | -- | -- |
| `d` | Start discuss | -- | -- | Dispositions | -- |
| `Enter` | -- | Send message | -- | Round detail | -- |
| `Ctrl+D` | -- | Done -> planning | -- | -- | -- |
| `g` | -- | -- | Generate | -- | -- |
| `r` | -- | -- | Start review | Raw response | -- |
| `p` | -- | -- | Plan view | Plan view | Plan view |
| `e` | Export | Export | Export | Export | Export |
| `l` | Log filter | Log filter | Log filter | Log filter | Log filter |
| `c` | -- | -- | -- | -- | Copy plan path |
| `q` | Quit | Quit | Quit | Quit (deferred) | Quit |
| `?` | Help | Help | Help | Help | Help |

### DB Connection Model

Same as review TUI — 3 connections, 3 owners:
- **CLI thread:** `prepare()` and post-exit handoff (if needed)
- **Worker thread:** own connection for all writes (discuss, generate, review engine)
- **TUI main thread:** read-only connection for sidebar queries

### Quit Contract

- **CONTEXT/DISCUSSION/PLANNING/COMPLETE:** Quit immediately. Session stays in current phase, resumable later.
- **REVIEW (active):** Deferred quit — wait for current round to finish (same as review TUI).
- **PAUSED:** Quit immediately. Session stays paused.

---

## Integration with Existing Review TUI

The session TUI does NOT launch a separate `ReviewTUI`. Instead, it embeds the review widgets directly in its main panel during the REVIEW phase:

- `RoundList`, `ConvergencePanel`, `CurrentRound`, `PlanPanel` — mounted into the main panel container
- Same `TUIAdapter` callback pattern — engine posts messages, session app handles them
- Same `LoopFinished` single-source contract
- Same disposition/plan/raw-response screens (push via keybindings)

The existing `ReviewTUI` continues to work standalone via `planner-auto review <id> --tui`. The session TUI reuses its widgets, not its app class.

---

## CLI Entry Point

```bash
# New session
planner-auto session --project my-api --tui

# Resume existing session (picks up at current phase)
planner-auto session abc123 --tui

# With options
planner-auto session --project my-api --tui --claude-backend direct
```

The `session` command is new. It combines `start` + full lifecycle in one invocation. Without `--tui`, it could run a guided CLI flow (future scope — not in this proposal).

---

## Implementation Milestones (Estimated)

### M1: Session Shell + Phase Navigation
- `session_app.py` with persistent layout (sidebar + main + log + footer)
- `phase_list.py` widget with phase icons and counts
- `compact_phase_bar.py` for small terminals
- Phase-aware keybinding switching
- CLI `session` command with `--tui` flag
- Reuse `SessionPanel`, `LogPanel`, `theme.tcss`

### M2: Context Manager
- `context_list.py` widget (file/note list with sizes)
- `file_input_screen.py` modal (path input + validation + size display)
- `note_input_screen.py` modal (multiline text area)
- Worker thread: `add_context` calls on user input
- Phase advance: CONTEXT -> DISCUSSION on `d` key

### M3: Discussion View
- `chat_view.py` widget (scrollable message history, role-colored)
- `SessionInputBridge` for worker/TUI input synchronization
- Worker thread: `discuss()` calls, response posting
- "Thinking..." indicator during Claude response
- Phase advance: DISCUSSION -> PLANNING on `Ctrl+D`

### M4: Planning + Generation
- `generation_progress.py` widget (synthesis + plan generation steps)
- `plan_view.py` widget (scrollable plan with milestone count)
- Worker thread: `synthesize_context()` + `generate_plan()` calls
- Validation display (OK or warnings)
- Phase advance: PLANNING -> REVIEW on `r` key

### M5: Review Embed + Completion
- Embed review widgets (`RoundList`, `ConvergencePanel`, `CurrentRound`) in main panel
- Reuse `TUIAdapter` + existing review messages
- `result_summary.py` widget (completion stats, artifacts, .kafra path)
- `blocker_screen.py` modal (blocker question + answer input)
- Auto-advance REVIEW -> COMPLETE on convergence

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Phase transition bugs | Medium | High | Reuse existing `SessionManager` phase rules |
| Worker thread idle state management | Medium | Medium | `threading.Event` for input bridge, clear state machine |
| Keybinding conflicts across phases | Low | Medium | Phase-aware binding swap, test each phase |
| Review widget embedding conflicts | Medium | Medium | Mount/unmount review widgets on phase change |
| Discussion input race conditions | Medium | High | Input bridge with explicit event signaling |
| Large context files slow down context list | Low | Low | Show size only, lazy content loading |

---

## Success Criteria

| Criterion | Measurement |
|-----------|-------------|
| Full lifecycle in one TUI session | Start -> add context -> discuss -> generate -> review -> complete without exiting |
| Phase transitions visible | Phase list updates icons in real-time |
| Discussion interactive | Messages sent/received with "thinking" indicator |
| Review embedded | Same round-by-round experience as standalone review TUI |
| Blocker resolution | Paused state shows blocker, accepts answer, resumes |
| Small terminal usable | 60-column terminal shows compact phase bar + essential content |
| Resume works | `planner-auto session <id> --tui` picks up at correct phase |
| No regressions | Standalone `planner-auto review <id> --tui` still works |

---

## References

- Review TUI (implemented): `planner-auto/planner_auto/tui/` — widgets, adapter, messages, theme
- orchestrator-auto TUI: `orchestrator-auto/orchestrator_auto/tui/` — InputModal pattern, multi-phase app
- Session lifecycle: `planner-auto/planner_auto/cli.py` — all commands
- Phase rules: `planner-auto/planner_auto/state.py` — transitions, allowed commands
