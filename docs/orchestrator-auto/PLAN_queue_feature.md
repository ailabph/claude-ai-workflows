# Plan: Plan Queue Feature (GO-Ready)

Queue multiple plan files for sequential execution with automatic advancement on completion.

## Feature Description

Add a `--queue` mode to `orchestrator start` to enqueue multiple plan files for sequential execution, automatically starting the next workflow when the current one completes.

Queue state is persisted in SQLite for crash recovery and for resuming mid-queue.

### Proposed CLI UX

```bash
# Create a new queue and run sequentially
orchestrator start --queue plan1.md plan2.md plan3.md

# Resume an existing queue for this project
orchestrator start --queue

# Reset (overwrite) existing active queue, then run
orchestrator start --queue --queue-reset plan1.md plan2.md

# Queue plans with explicit DB path
orchestrator start --queue --queue-reset plan1.md plan2.md -d /tmp/db.sqlite

# Queue plans, enabling telegram notifications
orchestrator start --queue --queue-reset plan1.md plan2.md --telegram
```

### CLI Semantics (Important)

- `orchestrator start` currently requires `--feature`.
- In **queue mode**, `--feature` becomes **optional** because each queued plan provides its own feature label.
- Queue mode is **mutually exclusive** with `--plan` (single-workflow plan import).
- If `--feature` is provided in queue mode, it is ignored (or used only as an overall label in output; do not store it into `sessions.feature_description`).
- Backwards compatibility:
  - `orchestrator start -f "Feature"` continues to work unchanged.
  - `orchestrator start --plan some.md -f "Feature"` continues to work unchanged.

Queue mode will use `extract_feature_from_plan(plan_path)` to set each session’s `feature_description`. If extraction fails, fall back to filename stem.

### Queue Recovery Semantics (Decide Upfront)

This feature supports **one active queue per project** (`project_id`). Multiple named queues / parallel queues are explicitly out of scope.

To satisfy “crash recovery” without introducing a new `orchestrator queue ...` command group, `orchestrator start --queue` must support **resume** as well as **reset**:

- **Resume existing queue (default):**
  - If an active queue exists for `project_id` (items with status `pending|running|paused`), `orchestrator start --queue` resumes it.
  - Recommended UX: allow `orchestrator start --queue` with **no plan args** to mean “resume existing queue”.
  - If plan args are provided while an active queue exists, require that the provided list matches the persisted queue (same count and same normalized paths in order). If it does not match, error with a message instructing to use `--queue-reset`.

- **Reset queue (explicit):**
  - Add `--queue-reset` to clear any active queue items for `project_id` and replace them with the provided plan list.

- **History retention:** Completed/failed queue items may remain for auditability; “active queue” is defined only as `pending|running|paused`.

**Queue item status values:** `pending`, `running`, `paused`, `completed`, `failed`.

### Telegram Notifier Ownership (Critical)

The current `Orchestrator._cleanup()` closes `self.telegram_notifier`. In queue mode we may run multiple orchestrators sequentially.

To avoid losing notifications after the first run:
- Treat the Telegram notifier as **owned by the CLI runner**, not by individual orchestrator instances.
- Either:
  - introduce a `close_telegram_notifier` flag on `Orchestrator`, defaulting to today’s behavior, **or**
  - pass a notifier factory / create a new notifier per queued run.

This decision is required before implementing queue advancement.

---

## Milestones

### M1: Database Schema & CRUD (Queue Persistence)

Add queue persistence layer with project scoping.

**Tasks:**
- [ ] Add `queue_items` table to `db.py` schema in `init_db()`
  ```sql
  CREATE TABLE IF NOT EXISTS queue_items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id TEXT,
      plan_path TEXT NOT NULL,
      feature_description TEXT,
      position INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      session_id TEXT,
      error_message TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      started_at TIMESTAMP,
      completed_at TIMESTAMP
  )
  ```
- [ ] Add indexes to support lookups:
  - `idx_queue_items_project_status` on `(project_id, status)`
  - optional: `idx_queue_items_session_id` on `(session_id)`
- [ ] Add CRUD functions to `db.py` (names can vary; behavior matters):
  - `create_queue_item(project_id, plan_path, feature_description, position, db_path) -> int`
  - `list_queue_items(project_id, db_path, include_completed=True) -> List[Dict]`
  - `get_next_queue_item(project_id, db_path) -> Optional[Dict]` (next `pending` by `position`)
  - `get_queue_item_by_session_id(session_id, db_path) -> Optional[Dict]` (for `resume` integration)
  - `update_queue_item(item_id, *, status=None, session_id=None, error_message=None, started_at=None, completed_at=None, db_path) -> bool`
  - `clear_active_queue(project_id, db_path) -> int` (clears `pending|running|paused` items for project)
- [ ] Add tests in `tests/test_db.py` for queue persistence:
  - create/list ordering
  - get_next behavior
  - update status/session_id
  - clear_active_queue scoping by `project_id`

**Deliverables:**
- Queue table created on `init_db()`
- CRUD functions with docstrings
- Unit tests passing

⛔ STOP - Generate progress report, wait for approval

---

### M2: Feature Extraction from Plan Files

Extract a human-friendly feature label from plan files for display/telemetry and to populate `sessions.feature_description`.

**Tasks:**
- [ ] Add `extract_feature_from_plan(plan_path: str) -> str` to `parser.py`:
  - Parse YAML frontmatter `feature: <description>` if present
  - Parse `# Feature: <description>` if present in first ~20 lines
  - Parse the first H1 title as fallback (common pattern):
    - `# Implementation Plan: <description>` → `<description>`
    - `# <description>` → `<description>`
  - Final fallback: filename stem (`auth-flow.md` → `"auth-flow"`)
  - Handle missing/unreadable files gracefully (fallback to filename)
- [ ] Add tests in `tests/test_parser.py`:
  - YAML frontmatter
  - `# Feature:` header
  - `# Implementation Plan:` header
  - plain `# Title` header
  - no headers (filename fallback)
  - missing file (filename fallback)

**Deliverables:**
- `extract_feature_from_plan()` implemented
- Unit tests passing

⛔ STOP - Generate progress report, wait for approval

---

### M3: CLI: `start --queue` (Input Validation + Queue Creation)

Add `--queue` mode to the `start` command.

**Tasks:**
- [ ] Update `orchestrator start` signature in `cli.py`:
  - Make `--feature/-f` conditionally required:
    - required if neither `--plan` nor `--queue` is provided
    - optional when `--queue` is provided
  - Add `--queue` (mode flag) and `--queue-reset` (overwrite existing queue) options.
  - Accept plan paths for queue creation (recommended approach):
    - use a variadic click argument (allows `--queue` with zero args for resume):
      - `@click.argument('queue_plans', nargs=-1, type=click.Path(exists=True))`
    - enforce the following behavior:
      - `--queue` with **no** `queue_plans` → resume existing queue for this project (error if none exists)
      - `--queue` with `queue_plans` and **no active queue exists** → create a new queue from provided plans
      - `--queue` with `queue_plans` and an **active queue exists** →
        - if `queue_plans` exactly matches the persisted queue (same normalized paths + order): treat as resume
        - otherwise require `--queue-reset` (overwrite)
- [ ] Determine current project identity (`project_id`) using existing config logic.
- [ ] Load any existing active queue items for `project_id`.
- [ ] If `queue_plans` is empty:
  - error if no active queue exists
  - otherwise proceed to runner (M4)
- [ ] If `queue_plans` is provided:
  - validate all plan files upfront using `parse_plan_file()`
  - if no active queue exists: create queue items
  - if an active queue exists:
    - if `queue_plans` matches existing queue: resume
    - if mismatch and `--queue-reset` is not set: error and instruct `--queue-reset`
    - if mismatch and `--queue-reset` is set: clear active items and create new queue items
- [ ] Create queue items in DB with extracted feature descriptions (only on reset/new queue creation).
- [ ] Display queue status on creation:
  ```
  Queue: 3 plans
    1. [PENDING] auth-flow.md - "Add user authentication"
    2. [PENDING] api-refactor.md - "Refactor API endpoints"
    3. [PENDING] tests.md - "Add integration tests"
  ```

**Deliverables:**
- `orchestrator start --queue ...` accepted
- Backwards compatible non-queue start behavior
- Upfront validation + persisted queue items
- Queue creation UX output

⛔ STOP - Generate progress report, wait for approval

---

### M4: Queue Runner (Advancement on Completion)

Run queued plans sequentially.

**Design Choice (to keep this a GO):**
Implement advancement in the CLI runner loop instead of adding an engine callback. `Orchestrator.start()` is already synchronous and returns when the workflow reaches a terminal condition (completed/paused/failed).

**Crash-recovery behavior:** When resuming an existing queue, the runner must reconcile `queue_items.status` with the linked `sessions.status/phase` (if `session_id` exists). For example:
- queue item is `running` but session is `completed` → mark item `completed` and advance
- queue item is `running` but session is `paused` → mark item `paused` and halt
- queue item is `running` but session is missing → mark item `failed` with `error_message` and advance
- queue item is `running` but session is `active`:
  - if heartbeat is recent: assume another runner is active; **exit without changes** to avoid double-running
  - if heartbeat is stale: treat as orphaned; instruct user to `orchestrator reset <session-id>` and then `orchestrator resume <session-id> --force` (queue should not auto-force)

**Tasks:**
- [ ] In `cli.py start` queue path, implement a loop:
  - fetch next pending queue item
  - mark it `running` + `started_at`
  - create an `Orchestrator(feature_description=<extracted>, plan_path=<plan_path>, ...)`
  - store `session_id` on the queue item once created
  - run `orch.start()`
  - inspect final `orch.state.phase/status`:
    - if completed: mark item `completed` + `completed_at`
    - if paused: mark item `paused` (queue halts; do not advance)
    - if error/exception: mark item `failed` with `error_message` and continue to next (fail-forward)
- [ ] Add Telegram queue notifications (if enabled):
  - notify queue started (count)
  - notify each item start/finish (optional)
  - notify queue complete summary
- [ ] Ensure Telegram notifier lifecycle works across multiple queued orchestrators (see “Telegram Notifier Ownership”).

**Deliverables:**
- Sequential queue execution
- Fail-forward behavior on plan failure
- Queue halts on blockers (`paused`)
- Queue completion summary

⛔ STOP - Generate progress report, wait for approval

---

### M5: Resume Integration (Blockers + Continue Queue)

Ensure `orchestrator resume <session-id>` continues queue advancement when the resumed session completes.

**Tasks:**
- [ ] Add `get_queue_item_by_session_id()` DB lookup usage in CLI `resume`:
  - after `orch.resume(...)` completes, check if this session belongs to a queue item
  - if the session ends in `completed`, mark the queue item completed and continue the queue runner loop
  - if the session ends in `paused`, keep queue item paused (no advancement)
  - if resume run errors, mark queue item failed and continue to next (fail-forward)
- [ ] Add queue visibility in `orchestrator list` output:
  - display `queue_item_id` and/or queue position if `session_id` is present in `queue_items`
  - implement via DB lookup/join (no sessions schema change required)
- [ ] Test scenario: queue of 3, blocker on #2, resume, verify #3 starts.

**Deliverables:**
- Blockers pause queue correctly
- Resume continues queue when appropriate
- Queue membership visible in list output

⛔ STOP - Generate progress report, wait for approval

---

### M6: Documentation + Integration Tests

Finalize feature with docs and end-to-end tests.

**Tasks:**
- [ ] Update `orchestrator-auto/README.md`:
  - Add `--queue` to Quick Reference
  - Add Queue section explaining usage + semantics (resume by default; overwrite with `--queue-reset`)
  - Update TODO (mark Plan Queue complete)
- [ ] Add/Update integration tests in `tests/test_integration.py` using mocked agents:
  - Queue of 2 plan files completes sequentially
  - Queue pauses on blocker and does not advance
  - Resume completes blocker session and advances to next queued item
- [ ] Decide and document auto-commit behavior in queue mode:
  - recommended default: apply `--auto-commit` per completed session (per plan)
  - document if different

**Deliverables:**
- README updated
- Integration tests passing
- Manual verification notes complete

⛔ STOP - Generate progress report, wait for approval

---

## Success Criteria

1. `orchestrator start --queue plan1.md plan2.md plan3.md` executes plans sequentially
2. Queue survives process interruption (queue items persisted in SQLite) and can be resumed via `orchestrator start --queue`
3. Blockers pause the queue; `orchestrator resume <session-id>` continues and then advances
4. Failed plans are recorded (`failed + error_message`) but do not stop the queue (fail-forward)
5. Telegram notifications work across multi-session queue runs (no notifier lifetime bugs)
6. All existing tests continue to pass

## Out of Scope (Future)

- `orchestrator queue` subcommand group (add/remove/list/clear)
- `--queue-append` / multiple named queues per project
- Parallel queues
- Glob pattern support (`--queue plans/*.md`)
- Queue priority/reordering
- `--skip-on-blocker` (auto-advance on paused)
