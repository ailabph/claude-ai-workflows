# TUI Proposal — Session Mode (Full Lifecycle) (v2)

## Revision History

- **v1:** Reviewed NO_GO — 3 blockers: (1) finalize ownership contradicts between worker and CLI, (2) single long-lived worker too complex for one plan, (3) paused/blocker inline resolution is new product behavior. 1 scope concern: too broad for a single implementation plan.
- **v2:** Finalize owned by worker thread (consistent). Worker model split per phase (no single long-lived worker). Blocker resolution deferred to v1d. Implementation split into 4 phased plans.

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

**In scope:** Full session lifecycle TUI — one app from start to complete. Delivered in 4 phased plans:

| Phase | Scope | Depends On |
|-------|-------|------------|
| **v1a** | Session shell + context manager | Review TUI (v0.5.0) |
| **v1b** | Discussion mode | v1a |
| **v1c** | Planning/generation + review embed + completion | v1b |
| **v1d** | Blocker resolution from TUI | v1c |

Each phase is independently shippable — the TUI works at each stage with graceful fallback for unimplemented phases (e.g., v1a shows "Use CLI for discussion" in the DISCUSSION panel).

**Out of scope:**
- Multi-session management (one session per TUI instance)
- Replacing the CLI (TUI is opt-in, CLI commands continue to work)
- Inspector TUI (read-only post-hoc analysis — separate proposal)

**Explicitly deferred to v1d:**
- Inline blocker resolution from TUI (current CLI `resume` command is the only way to resolve blockers until v1d)

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

#### v1a-v1c: Read-only (show blocker + CLI commands)

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
|  oo COMPLETE       |  To resolve from CLI:                                   |
|                    |    planner-auto resume abc123                           |
|  BLOCKER           |    planner-auto review abc123 --max-rounds 12          |
|                    |    planner-auto complete abc123                         |
|  !! 1 open blocker |                                                         |
|                    |                                                         |
+--------------------+---------------------------------------------------------+
|  LOG                                                                         |
|  10:45:22 Review cap reached at round 8 with critical issues               |
|  10:45:22 Session paused. Blocker: SQL injection risk...                    |
+------------------------------------------------------------------------------+
|  [p]lan  [l]og filter  [q]uit                                    !! R8/8   |
+------------------------------------------------------------------------------+
```

#### v1d: Interactive blocker resolution (future)

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

### Worker Thread Model — Per-Operation, Not Per-Session

Unlike v1 which proposed a single long-lived worker managing the full lifecycle, v2 uses **short-lived workers per operation**. This avoids the complexity of idle parking, cross-phase state sync, and long-lived thread management.

**Phase → Worker mapping:**

| Phase | Worker Pattern | Duration |
|-------|---------------|----------|
| CONTEXT | No worker — TUI main thread handles add-context directly (DB writes are fast, <10ms) | Instant |
| DISCUSSION | One worker per message — spawns on Enter, dies after Claude responds (~2-5s each) | Short |
| PLANNING | One-shot worker — synthesize + generate (~5-15s) | Medium |
| REVIEW | Long-running worker — ReviewLoopEngine (5-25 min, existing pattern) | Long |
| COMPLETE | One-shot worker — finalize + export (~1s) | Short |

```python
# CONTEXT: no worker needed
def action_add_file(self) -> None:
    """Runs on TUI main thread — DB write is fast."""
    self.push_screen(FileInputScreen(...))

def on_file_input_submitted(self, path: str) -> None:
    add_context(self._rw_conn, self._session_id, "file", path, content)
    self._rw_conn.commit()
    self.post_message(ContextAdded(...))

# DISCUSSION: worker per message
@work(thread=True)
def send_discuss_message(self, content: str) -> None:
    worker_conn = sqlite3.connect(self._db_path)
    try:
        response = discuss(self._session_id, worker_conn, content, backend=...)
        worker_conn.commit()
        self._dispatch("on_discuss_response", response)
    finally:
        worker_conn.close()

# PLANNING: one-shot worker
@work(thread=True)
def run_generate(self) -> None:
    worker_conn = sqlite3.connect(self._db_path)
    try:
        self._dispatch("on_synthesis_started", ...)
        # synthesize_context + generate_plan
        self._dispatch("on_plan_generated", ...)
    finally:
        worker_conn.close()

# REVIEW: long-running worker (same as ReviewTUI)
@work(thread=True)
def run_review_loop(self) -> None:
    worker_conn = sqlite3.connect(self._db_path)
    try:
        engine = ReviewLoopEngine(conn=worker_conn, callbacks=adapter)
        result = ReviewWorkflow.run(engine, plan, max_rounds)
        # Worker owns finalize — it has the write connection and LoopResult
        finalize_result = ReviewWorkflow.finalize(worker_conn, ...)
        self._dispatch("on_session_completed", finalize_result)
    finally:
        worker_conn.close()
```

**Why per-operation workers:**
- No idle parking complexity (no `threading.Event` bridges)
- Each worker is simple: open conn, do work, post result, close conn
- Context phase has no worker at all (DB writes are <10ms)
- Discussion messages are independent — no shared state between workers
- Familiar pattern — the review worker is identical to the existing ReviewTUI

### Discussion Input Flow (No Bridge Needed)

With per-message workers, there's no input bridge. The flow is:

```
User presses Enter with message text
  -> TUI main thread: disable input, show "thinking..."
  -> TUI spawns send_discuss_message(content) as @work(thread=True)
  -> Worker: opens conn, calls discuss(), posts DiscussResponseReceived
  -> TUI main thread: appends response to chat view, re-enables input
```

Each message is a fire-and-forget worker. The TUI main thread simply disables input while the worker runs and re-enables it when the response arrives.

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

Two persistent connections + per-worker connections:
- **TUI main thread:** Read-write connection for fast operations (add-context, phase queries). Also used for sidebar reads. Opened on mount, closed on exit.
- **Worker threads:** Each worker opens its own connection, closes in `finally`. Short-lived workers (discuss, generate) live <15s. The review worker lives longer but follows the same pattern.
- **CLI thread:** No post-exit handoff needed. The review worker owns finalize (it has the write connection and the `LoopResult`). CLI just calls `app.run()` and reads `app.exit_code` for shell return.

**Finalize ownership (resolved from v1):** The review worker calls `ReviewWorkflow.finalize(worker_conn, ...)` directly. The CLI does NOT call finalize after `app.run()` returns. This is different from the standalone ReviewTUI (where CLI owns finalize) but correct for the session TUI because the worker manages the full review→complete lifecycle.

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

## Implementation Phases

Each phase is a separate implementation plan, independently shippable. The TUI works at each stage — unimplemented phases show a "Use CLI for X" message in the main panel.

### Phase v1a: Session Shell + Context Manager

**Scope:** Persistent shell with sidebar + phase list + log panel. Context manager with file/note add modals. Resume existing sessions.

**What works after v1a:**
- `planner-auto session --project my-api --tui` creates session and shows context manager
- `planner-auto session abc123 --tui` resumes at current phase
- Add files and notes via `f`/`n` keybindings with modal input
- Context list shows entries with types and sizes
- Phase list shows progress icons
- Advance to DISCUSSION via `d` key (but discussion panel shows "Use CLI: planner-auto discuss abc123 --interactive")

**Key deliverables:**
- `session_app.py` with persistent layout
- `phase_list.py` widget
- `compact_phase_bar.py` for small terminals
- `context_list.py` widget
- `file_input_screen.py` + `note_input_screen.py` modals
- CLI `session` command with `--tui` flag
- Phase-aware keybinding switching
- No worker threads needed (context operations run on main thread)

### Phase v1b: Discussion Mode

**Scope:** Interactive chat view with message history, per-message worker threads, "thinking" indicator.

**What works after v1b:**
- Discussion phase is fully interactive in the TUI
- Messages appear in real-time with role coloring
- "Thinking..." indicator while Claude responds
- `Ctrl+D` advances to PLANNING (but planning panel shows "Use CLI: planner-auto generate abc123")

**Key deliverables:**
- `chat_view.py` widget (scrollable, role-colored, input at bottom)
- Per-message worker pattern (`send_discuss_message` as `@work(thread=True)`)
- `DiscussThinking` / `DiscussResponseReceived` messages
- Input disable/enable during Claude response

### Phase v1c: Planning + Review Embed + Completion

**Scope:** Generation progress display, plan view, embedded review dashboard (reuse existing widgets), completion summary with artifacts.

**What works after v1c:**
- Full lifecycle in one TUI: start → context → discuss → generate → review → complete
- Generation shows synthesis + plan progress
- Review phase embeds existing review widgets (RoundList, ConvergencePanel, CurrentRound)
- Completion shows summary, artifacts, .kafra path
- Paused state is read-only (shows blocker + CLI commands)

**Key deliverables:**
- `generation_progress.py` widget (synthesis + plan steps)
- `plan_view.py` widget (scrollable plan, milestone count, validation)
- Review widget embedding (mount/unmount on phase change)
- `result_summary.py` widget
- Review worker with finalize (worker owns finalize, not CLI)
- Paused state: read-only (show blocker + CLI resume commands)

### Phase v1d: Blocker Resolution (Future)

**Scope:** Inline blocker resolution from TUI. User answers blocker question directly instead of switching to CLI.

**What works after v1d:**
- Paused state shows blocker question + text input
- User submits answer → session resumes → review continues
- Matches existing `session.py:resolve_and_resume()` semantics

**Key deliverables:**
- `blocker_screen.py` modal (question display + answer input)
- Worker: resolve blocker, resume session, restart review loop
- Explicit contract: TUI calls same `resolve_and_resume()` as CLI `resume` command

**Why deferred:** This is new product behavior (inline resolution vs command-driven). The existing CLI `resume` command works. v1d adds convenience, not capability.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Phase transition bugs | Medium | High | Reuse existing `SessionManager` phase rules |
| Keybinding conflicts across phases | Low | Medium | Phase-aware binding swap, test each phase |
| Review widget embedding conflicts | Medium | Medium | Mount/unmount review widgets on phase change |
| Per-message worker spawning overhead | Low | Low | Workers are lightweight (~2-5s each, no idle state) |
| Large context files slow down context list | Low | Low | Show size only, lazy content loading |
| Finalize in worker vs CLI inconsistency | Low | High | Explicit contract: session TUI worker owns finalize, standalone ReviewTUI CLI owns finalize |

---

## Success Criteria

### v1a (Shell + Context)
| Criterion | Measurement |
|-----------|-------------|
| Session created from TUI | `planner-auto session --project X --tui` creates session |
| Context management works | Add files/notes via modals, see them in list |
| Resume works | `planner-auto session <id> --tui` picks up at correct phase |
| Small terminal usable | 60-column terminal shows compact phase bar |

### v1b (Discussion)
| Criterion | Measurement |
|-----------|-------------|
| Discussion interactive | Messages sent/received with "thinking" indicator |
| Per-message workers | No hangs, no race conditions across 10+ messages |
| Phase advance | Ctrl+D advances to PLANNING |

### v1c (Planning + Review + Complete)
| Criterion | Measurement |
|-----------|-------------|
| Full lifecycle | Start → context → discuss → generate → review → complete without exiting |
| Review embedded | Same round-by-round experience as standalone review TUI |
| Finalize in worker | Worker calls finalize, CLI does not |
| Paused state read-only | Shows blocker + CLI commands, no interactive resolution |
| No regressions | Standalone `planner-auto review <id> --tui` still works |

### v1d (Blocker Resolution)
| Criterion | Measurement |
|-----------|-------------|
| Blocker resolution | Paused state accepts answer, resumes session |
| Same semantics as CLI | Uses `resolve_and_resume()` from `session.py` |

---

## References

- Review TUI (implemented): `planner-auto/planner_auto/tui/` — widgets, adapter, messages, theme
- orchestrator-auto TUI: `orchestrator-auto/orchestrator_auto/tui/` — InputModal pattern, multi-phase app
- Session lifecycle: `planner-auto/planner_auto/cli.py` — all commands
- Phase rules: `planner-auto/planner_auto/state.py` — transitions, allowed commands
