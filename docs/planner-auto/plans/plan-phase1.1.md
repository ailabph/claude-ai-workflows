# Planner-Auto Session Core (Plan 1) - Implementation Plan

## Overview
Build a Python CLI tool (`planner-auto`) that manages interactive planning sessions with SQLite persistence and artifact export. The tool guides users through a structured lifecycle (setup → context → discussion → planning → review → complete), stores all state in SQLite, invokes Claude via `claude-agent-sdk` for context synthesis and plan generation, and exports session artifacts to disk. Reviewer integration is explicitly out of scope (Plan 2).

## Milestone 1: Package Scaffold, DB Schema, and CRUD Layer

Set up the Python package structure, define all 7 SQLite tables, implement the CRUD layer with a consistent connection-based DB access contract, and provide complete test coverage.

### Tasks
- [ ] Create package directory `planner-auto/planner_auto/` with `__init__.py` (version = "0.1.0") and `planner-auto/pyproject.toml`. Runtime deps: `click`, `claude-agent-sdk`, `prompt_toolkit`. Dev deps in `[project.optional-dependencies] dev`: `pytest`, `pytest-asyncio`. Entry point: `planner-auto = "planner_auto.cli:cli"`. Do NOT list `sqlite3` (stdlib).
- [ ] Create `planner_auto/db.py` with `open_db(db_path) -> sqlite3.Connection` that creates `~/.planner-auto/` via `os.makedirs(exist_ok=True)`, opens the connection, and applies `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON` on every opened connection. Add `init_schema(conn: sqlite3.Connection)` that creates all 7 tables (DDL below). Every subsequent CRUD/query function in this file accepts `conn: sqlite3.Connection` as its first parameter.
- [ ] DDL for `sessions` (id TEXT PK, project TEXT NOT NULL, phase TEXT NOT NULL DEFAULT 'SETUP', status TEXT NOT NULL DEFAULT 'ACTIVE', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP), `messages` (id INTEGER PK AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id), role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP) with INDEX on (session_id, id), `context_entries` (id INTEGER PK AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id), entry_key TEXT NOT NULL, entry_type TEXT NOT NULL CHECK(entry_type IN ('file','note','synthesis')), content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(session_id, entry_key, entry_type)), `plan_drafts` (id INTEGER PK AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id), draft_number INTEGER NOT NULL, content TEXT NOT NULL, model TEXT NOT NULL, config_snapshot_id INTEGER REFERENCES session_config(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(session_id, draft_number)), `reviews` (id INTEGER PK AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id), draft_id INTEGER NOT NULL REFERENCES plan_drafts(id), verdict TEXT, content TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP), `blockers` (id INTEGER PK AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id), source TEXT NOT NULL, question TEXT NOT NULL, answer TEXT, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved')), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, resolved_at TEXT), `session_config` (id INTEGER PK AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id), config_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP).
- [ ] Implement CRUD functions (all taking `conn` as first arg): `create_session(conn, project)`, `update_session_phase(conn, id, phase)`, `update_session_status(conn, id, status)`, `add_message(conn, session_id, role, content)`, `add_context_entry(conn, session_id, key, type, content)` (UPSERT on unique constraint), `add_plan_draft(conn, session_id, content, model, config_snapshot_id)` (auto-increments draft_number per session via `SELECT COALESCE(MAX(draft_number),0)+1`), `add_review(conn, session_id, draft_id, verdict, content)`, `create_blocker(conn, session_id, source, question)`, `resolve_blocker(conn, blocker_id, answer)` (sets resolved_at), `save_session_config(conn, session_id, config_json)`.
- [ ] Implement query helpers (all taking `conn` as first arg): `get_session(conn, id)`, `get_messages(conn, session_id)` (ordered by `id ASC` — autoincrement guarantees insertion order regardless of timestamp granularity), `get_context_entries(conn, session_id, entry_type=None)`, `get_latest_plan_draft(conn, session_id)`, `get_all_plan_drafts(conn, session_id)`, `get_open_blockers(conn, session_id)`, `get_session_config(conn, session_id)`.
- [ ] Define enums and lifecycle rules in `planner_auto/state.py`: `Phase` enum (SETUP, CONTEXT, DISCUSSION, PLANNING, REVIEW, COMPLETE), `Status` enum (ACTIVE, PAUSED, COMPLETE, FAILED). Define `VALID_PHASE_TRANSITIONS` dict and `PHASE_ALLOWED_COMMANDS` dict. Rules: (1) `export` allowed in any phase/status, (2) `complete` requires zero open blockers, (3) PAUSED status only allows `resume`, `status`, `export`, (4) `add-context` allowed in SETUP and CONTEXT, (5) `generate` callable repeatedly in PLANNING.
- [ ] Create `planner-auto/tests/conftest.py` with a `db_conn` fixture that opens an in-memory connection, applies PRAGMAs, and calls `init_schema()`. Create `planner-auto/tests/test_db.py` testing all CRUD functions: create/read/update for each table, duplicate context entry UPSERT, draft_number auto-increment, blocker create/resolve lifecycle, session_config round-trip, foreign key enforcement, and a test inserting two messages with the same `created_at` timestamp proving `get_messages` returns them in insertion order (by `id`).

### Deliverables
- [ ] `planner-auto/planner_auto/db.py` exists with `open_db()`, `init_schema()`, all CRUD/query functions accepting `conn` as first arg
- [ ] `planner-auto/planner_auto/state.py` exists with phase/status enums, transition map, and phase-command permissions
- [ ] `pytest planner-auto/tests/test_db.py` passes with ≥16 tests covering all tables plus deterministic ordering
- [ ] `pip install -e "planner-auto/[dev]"` succeeds without errors

## Milestone 2: CLI Entry Point, Session Lifecycle, and Logging

Implement the Click CLI with `start`, `status`, `list`, and `resume` commands, the `SessionManager` that enforces phase transitions and command permissions, and session-scoped logging.

### Tasks
- [ ] Create `planner_auto/cli.py` with Click group `cli` and subcommand `start` that: calls `open_db()` to get connection (PRAGMAs applied automatically), creates a session via `create_session(conn, project)`, saves initial config snapshot containing only start-time fields (`config_json` = `{"project": name, "model_default": "claude-sonnet-4-6"}`), creates log file at `~/.planner-auto/logs/<session-id>.log`, prints session ID. Accept `--project` (required), `--verbose`, `--debug` flags.
- [ ] Implement `list` command showing all sessions (id, project, phase, status, created_at) in a formatted table, with `--status` filter option.
- [ ] Implement `status <session-id>` command showing full session details: phase, status, message count, context entry count, plan draft count, open blockers count and their questions.
- [ ] Create `planner_auto/session.py` with `SessionManager` class initialized with `conn: sqlite3.Connection`. `advance_phase(session_id, target_phase)` checks `VALID_PHASE_TRANSITIONS`; raises `InvalidTransitionError`. `check_command(session_id, command_name)` checks `PHASE_ALLOWED_COMMANDS` and current status; raises `CommandNotAllowedError` with explanation. Both error classes defined in `planner_auto/errors.py`.
- [ ] Create `planner_auto/logging.py` with `setup_session_logger(session_id, verbose=False, debug=False)` configuring a file handler to `~/.planner-auto/logs/<session-id>.log` and optionally stderr at DEBUG or INFO level.
- [ ] Implement `resume <session-id>` command: validates status is ACTIVE or PAUSED, lists open blockers, prompts user for answers to each via `click.prompt()`, resolves them in DB, sets status back to ACTIVE, prints current phase.
- [ ] Create `planner-auto/tests/test_cli.py` using Click's `CliRunner`: test `start` creates session in DB, `list` shows it, `status` returns correct counts, `resume` on invalid ID returns error, `resume` on COMPLETE session returns error. Create `planner-auto/tests/test_session.py` testing `advance_phase` valid/invalid transitions, `check_command` for each phase, PAUSED status restrictions, and `complete` blocked by open blockers.

### Deliverables
- [ ] `planner-auto start --project myapp` creates a session, config snapshot (project + model_default only), log file, and prints ID
- [ ] `planner-auto list` and `planner-auto status <id>` display correct session data
- [ ] `SessionManager.advance_phase()` and `check_command()` enforce full lifecycle rules (tested)
- [ ] `pytest planner-auto/tests/test_cli.py planner-auto/tests/test_session.py` passes with ≥12 tests total

## Milestone 3: Context Loading, Prompts, and SDK Wrapper with Robust Error Handling

Implement context loading with file validation, define prompt constants, and build the SDK wrapper with commit-on-success persistence semantics.

### Tasks
- [ ] Create `planner_auto/prompts.py` containing `PLANNER_SYSTEM_PROMPT` and `SYNTHESIS_SYSTEM_PROMPT` as string constants extracted from POC files. Include `prompt_version_hash(prompt: str) -> str` using `hashlib.sha256`.
- [ ] Create `planner_auto/sdk_wrapper.py` with `async query_claude(messages, system_prompt, model, timeout_sec=120)` that wraps `claude_agent_sdk.query()`. Error handling: `AuthenticationError` → `SDKAuthError("Invalid API key — set ANTHROPIC_API_KEY")`; `RateLimitError` → retry up to 3 times with exponential backoff (2s, 4s, 8s), then raise `SDKRateLimitError`; timeout/`ConnectionError` → retry once after 2s, then raise `SDKTimeoutError`; empty/malformed response → raise `SDKResponseError`. All custom errors in `errors.py`. Every call logs model, token count, and latency.
- [ ] Add `add-context` subcommand: `planner-auto add-context <session-id> --file <path>`. Validate: file exists, is ≤500KB, is valid UTF-8 (reject binary with clear error). Store in `context_entries` with filename as key, entry_type="file". UPSERT on duplicate. Also support `--note "text"` variant (entry_type="note", key=auto-generated timestamp). Check command permission via `SessionManager.check_command()`. Advance phase to CONTEXT if in SETUP.
- [ ] Create `planner-auto/tests/test_sdk_wrapper.py` testing: auth error mapping, rate-limit with retry exhaustion, timeout with single retry, empty response error, successful call. All mocked. Create `planner-auto/tests/test_context.py` testing: `add-context --file` rejects >500KB, rejects binary, stores UTF-8, UPSERT replaces content, `--note` stores with auto-key. ≥10 tests total.

### Deliverables
- [ ] `planner_auto/prompts.py` exists with both prompt constants and `prompt_version_hash()`
- [ ] `sdk_wrapper.py` handles auth, rate-limit (exponential backoff), timeout, and malformed response errors
- [ ] `add-context --file` rejects invalid files, replaces on duplicate, stores UTF-8 content
- [ ] `pytest planner-auto/tests/test_sdk_wrapper.py planner-auto/tests/test_context.py` passes with ≥10 tests

## Milestone 4: Discussion, Context Synthesis, and Plan Generation

Implement the discussion phase, context synthesis via Haiku, plan generation via Sonnet/Opus with commit-on-success persistence, and plan format validation.

### Tasks
- [ ] Create `planner_auto/agents.py` with `async discuss(session_id, user_input, conn)`: checks command permission, loads message history via `get_messages(conn, session_id)`, calls `query_claude()` with discussion system prompt. **Persistence contract: both user and assistant messages are committed together in a single transaction only on successful SDK response.** On SDK failure, nothing is committed; the user message is re-sent on retry. Uses `claude-sonnet-4-6`.
- [ ] Add `discuss` subcommand: `planner-auto discuss <session-id> "<message>"` — advances to DISCUSSION if in CONTEXT, calls `discuss()`, prints response. CLI catches all `SDK*Error` subclasses and prints user-friendly messages with suggested fixes.
- [ ] Implement interactive mode: `planner-auto discuss <session-id> --interactive` enters a `prompt_toolkit` input loop. Each line sent through `discuss()`. User types `/done` to advance phase to PLANNING. SDK errors print inline and allow retry.
- [ ] Add `async synthesize_context(session_id, conn)` in `agents.py`: queries all `context_entries` (excluding prior syntheses) and `messages`, builds synthesis prompt, calls `query_claude()` with Haiku (`claude-haiku-4-5-20251001`). **Commits synthesis entry only on success.** Stores as context_entry with entry_type="synthesis", key="synthesis-<timestamp>" (no UPSERT — syntheses accumulate).
- [ ] Add `async generate_plan(session_id, conn, model)` in `agents.py`: calls `synthesize_context()`, calls `query_claude()` with `PLANNER_SYSTEM_PROMPT`. **Persistence contract: config snapshot and plan draft are committed together in a single transaction only after successful SDK response.** Config snapshot `config_json` contains `{"model": model, "prompt_hashes": {"planner": hash, "synthesis": hash}, "feature_description": <first user message>}`. Stores result in `plan_drafts` with auto-incremented draft_number linked to the config snapshot ID.
- [ ] Add `generate` subcommand: `planner-auto generate <session-id>` — checks command permission, calls `generate_plan()`, prints the plan. Accept `--model` flag defaulting to `claude-sonnet-4-6`. Can be called multiple times in PLANNING phase.
- [ ] Create `planner_auto/validation.py` with `validate_plan_format(content)` checking: has `## Milestone N:` headers, 3-5 milestones, sequential numbering from 1, each has `### Tasks` and `### Deliverables` sections with `- [ ]` items. Returns list of error strings (empty = valid). Run automatically after generation; print warnings but don't block storage.
- [ ] Create `planner-auto/tests/test_agents.py`: test `discuss()` commits both messages on success, commits nothing on SDK failure, phase advancement on `/done`. Test `synthesize_context()` stores synthesis only on success. Test `generate_plan()` stores draft + config atomically on success, stores nothing on failure, draft_number increments correctly. Create `planner-auto/tests/test_validation.py`: test valid plan, missing milestones, wrong numbering, missing sections. ≥14 tests total.

### Deliverables
- [ ] `discuss` returns Claude response; on SDK failure, no messages are persisted (clean retry)
- [ ] `generate` produces a plan with atomically-linked config snapshot; repeated calls increment draft_number
- [ ] `validate_plan_format()` identifies valid and malformed plans correctly
- [ ] `pytest planner-auto/tests/test_agents.py planner-auto/tests/test_validation.py` passes with ≥14 tests

## Milestone 5: Artifact Export, Blocker Lifecycle, and Session Completion

Implement artifact file export with multi-draft support, blocker pause/resume wired into SessionManager, and the `complete` command.

### Tasks
- [ ] Create `planner_auto/export.py` with `export_session(session_id, conn, output_dir)` that creates `output_dir` via `os.makedirs(exist_ok=True)` (default `~/.planner-auto/sessions/<session-id>/`) and writes: `chat.csv` (columns: id, timestamp, role, content — from `get_messages` ordered by `id`), `context-summary.md` (context_entries grouped by type with headers), and one plan file per draft named `plan-draft-<N>.md`. Overwrites on re-export (idempotent).
- [ ] Add `export` subcommand: `planner-auto export <session-id>` calls `export_session()`, prints paths. Accept `--output-dir` override. Allowed in any phase/status.
- [ ] Implement blocker lifecycle in `SessionManager`: `pause_with_blocker(session_id, source, question)` sets status=PAUSED and inserts blocker in one transaction. `resolve_and_resume(session_id, blocker_id, answer)` resolves blocker; if no open blockers remain, sets status=ACTIVE. Wire into the `resume` command from Milestone 2.
- [ ] Add `complete` subcommand: `planner-auto complete <session-id>` — checks for open blockers (rejects with error listing them), advances phase to COMPLETE, sets status=COMPLETE, runs `export_session()` automatically, prints export paths.
- [ ] Create `planner-auto/tests/test_export.py`: test `export_session()` creates all expected files with correct content, re-export is idempotent, multiple drafts produce multiple plan files, `chat.csv` rows ordered by id. Test blocker pause/resume lifecycle through `SessionManager`. Test `complete` rejected with open blockers. ≥8 tests. Run full suite `pytest planner-auto/tests/` to confirm all tests pass.

### Deliverables
- [ ] `planner-auto export <id>` creates `chat.csv` (ordered by id), `context-summary.md`, and `plan-draft-<N>.md` files
- [ ] `planner-auto complete <id>` rejects with open blockers, succeeds otherwise and auto-exports
- [ ] Blocker pause/resume lifecycle works end-to-end via `resume` command
- [ ] `pytest planner-auto/tests/test_export.py` passes with ≥8 tests
- [ ] Full suite `pytest planner-auto/tests/` passes with all tests green