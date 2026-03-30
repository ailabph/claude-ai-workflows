# AGENTS.md — planner-auto Developer Context

This file provides context for agents and developers working on the planner-auto codebase.

## What This Tool Does

planner-auto manages interactive planning sessions: user describes a feature → Claude generates a milestone plan → GPT reviews it → Claude revises → repeat until GPT approves → final plan exported for orchestrator-auto to implement.

Two phases: **Session Core** (Plan 1) handles the session lifecycle. **Reviewer Adapter** (Plan 2) handles the GPT review loop.

## Architecture

```
planner_auto/
├── cli.py              (1078 lines) # Click CLI — all commands
├── db.py               (772 lines)  # SQLite v2 schema, 8 tables, CRUD, migration
├── session.py          (192 lines)  # SessionManager — phase transitions, pause/resume
├── state.py            (50 lines)   # Phase/Status enums, transition rules
├── agents.py           (230 lines)  # discuss(), synthesize_context(), generate_plan()
├── sdk_wrapper.py      (248 lines)  # Claude SDK wrapper — retry, timeout, on_timeout callback
├── review_workflow.py  (349 lines)  # Shared review orchestration (prepare/run/finalize)
├── prompts.py          (57 lines)   # Planner system prompts + version hashing
├── export.py           (340 lines)  # Artifact export — plans, reviews, .kafra handoff
├── validation.py       (92 lines)   # Plan format validation
├── errors.py           (96 lines)   # Error hierarchy
├── git_utils.py        (50 lines)   # Repo root discovery
├── logging.py          (54 lines)   # Shared root logger + SessionFilter
├── inspect.py          (262 lines)  # DB inspection queries for debugging
├── reviewer/
│   ├── contract.py     (174 lines)  # ReviewerContract ABC, ReviewerResponse, ReviewIssue
│   ├── direct_api.py   (245 lines)  # GPT-5.4 adapter via OpenAI SDK
│   ├── parser.py       (384 lines)  # JSON/XML/free-form response parser
│   └── prompts.py      (171 lines)  # Reviewer system prompts (3 variants)
├── loop/
│   ├── engine.py       (738 lines)  # ReviewLoopEngine + 7 TUI callbacks
│   ├── feedback.py     (217 lines)  # ACCEPT/DEFER/REJECT per issue
│   ├── history.py      (201 lines)  # Cumulative review context builder
│   └── convergence.py  (126 lines)  # Complexity detection, caps, fast mode
└── tui/                              # TUI Review Dashboard (optional dep)
    ├── review_app.py   (671 lines)  # ReviewTUI — main Textual app + worker thread
    ├── adapter.py      (129 lines)  # Thread-safe engine → TUI bridge
    ├── messages.py     (135 lines)  # 8 Textual message types
    ├── bindings.py     (16 lines)   # Keybinding definitions
    ├── widgets/        (787 lines)  # 7 widgets: SessionPanel, ConvergencePanel, etc.
    ├── screens/        (410 lines)  # 4 screens: Dispositions, Plan, RawResponse, Help
    └── styles/theme.tcss (235 lines) # Dark theme, 3 responsive breakpoints
```

**Total:** ~8,500 source lines, ~8,800 test lines, 464 tests.

## Key Design Rules

### DB Access

- **All DB access through `db.py`** — never write raw SQL in other modules.
- **Callers manage commits** — CRUD functions do NOT auto-commit. Use `conn.commit()` for single ops, `transaction(conn)` context manager for atomic multi-ops.
- **Schema versioning** — `schema_version` table tracks version. Migrations run automatically in `init_schema()`.

```python
# Single operation
add_message(conn, session_id, "user", content)
conn.commit()

# Atomic multi-operation
with transaction(conn):
    add_message(conn, session_id, "user", user_input)
    add_message(conn, session_id, "assistant", response)
```

### Phase Transitions

- **All phase changes through `SessionManager`** — never update phase directly in DB.
- Allowed transitions defined in `state.py: VALID_PHASE_TRANSITIONS`.
- Command permissions defined in `state.py: PHASE_ALLOWED_COMMANDS`.
- `check_command()` enforces both phase and blocker rules.

```
SETUP → CONTEXT → DISCUSSION → PLANNING → REVIEW → COMPLETE
                                   │          │         ▲
                                   │          └─────────┘
                                   └────────────────────┘
```

### SDK Calls

- **All Claude calls through `sdk_wrapper.py: query_claude()`** — handles retry, timeout, error mapping.
- Two backends: `"direct"` (Anthropic API via `anthropic` package, default) and `"sdk"` (Claude CLI subprocess).
- Callers pass `backend=` (resolved from session config by CLI). Default `None` → auth-aware: `ANTHROPIC_API_KEY` → direct, OAuth only → sdk.
- Accepts `effort`, `thinking`, `max_turns`, `backend` params.
- `effort` maps to thinking budgets on direct backend: medium=10K, high=20K, max=50K tokens.
- `asyncio.wait_for()` enforces timeout on both backends.
- Rate limit: 3 retries with 2/4/8s backoff. Timeout: 1 retry after 2s.
- All anthropic exceptions mapped to existing `SDKError` hierarchy — callers don't know which backend ran.
- `.env` auto-loaded at CLI startup via `python-dotenv`.

### Reviewer Calls

- **All GPT calls through `reviewer/direct_api.py: DirectAPIAdapter`** — implements `ReviewerContract` ABC.
- When `reasoning_effort` is set, `temperature` must be omitted (OpenAI requirement).
- Response parsed through `reviewer/parser.py` — three-stage fallback: JSON → XML → free-form.
- Metadata (model, cost, tokens, raw_text) attached to `ReviewerResponse` by the adapter.

### Review Loop

- **Engine owns loop output** — CLI does not print duplicate summaries.
- Three output tiers: `quiet` (one line per round), `verbose` (full metrics), `debug` (raw content).
- Stop policy: GO → complete, cap+no-criticals → complete, cap+criticals → pause with blocker.
- Severity filtering happens AFTER feedback validation (dispositions reference original indices).
- Review history includes cumulative DEFER decisions from ALL prior rounds, not just the last.

### Logging

- **Shared root logger** `planner_auto` — all module loggers are children.
- `SessionFilter` injects `session_id` into every log record.
- File handler always at DEBUG (`~/.planner-auto/logs/<session-id>.log`).
- Stderr handler only when `--verbose` (INFO) or `--debug` (DEBUG).
- Every session-aware command calls `setup_session_logging()`.

### Testing

- **All tests use in-memory SQLite** (`:memory:`) with explicit commits.
- **All SDK/API calls are mocked** — no real API calls in tests.
- Use `conftest.py` `db_conn` fixture for DB setup.
- Use Click's `CliRunner` for CLI tests.
- Use `caplog` for structured logging tests.

```bash
pytest tests/ -v                              # All 368 tests
pytest tests/test_engine.py -v                # Single file
pytest tests/test_engine.py::TestRoundResume  # Single class
pytest -k "convergence" -v                    # Filter by name
```

## What NOT to Do

- **Don't commit from CRUD functions** — callers own transaction boundaries.
- **Don't bypass SessionManager** — use `advance_phase()` and `check_command()`.
- **Don't print from the engine in quiet mode** — only the one-liner and final line.
- **Don't store raw secrets in context_entries** — files are stored as UTF-8 text content.
- **Don't call OpenAI with `temperature` when `reasoning_effort` is set** — API rejects it.
- **Don't assume `round_number` starts at 1** — after resume, it continues from the next round.
- **Don't filter issues before `validate_feedback()`** — dispositions must reference original indices.
- **Don't persist history context strings** — they're reconstructed from DB state on demand.

## Common Development Tasks

### Adding a New CLI Command

1. Add the command in `cli.py` with Click decorators
2. Add `--verbose` and `--debug` flags, call `setup_session_logging()`
3. Use `SessionManager.check_command()` to enforce phase permissions
4. Add the command name to `PHASE_ALLOWED_COMMANDS` in `state.py`
5. Add tests in `tests/test_cli.py` using `CliRunner`

### Adding a New DB Table

1. Add CREATE TABLE to `init_schema()` in `db.py`
2. If modifying existing tables, add a migration (increment schema version, rebuild table)
3. Add CRUD functions (all take `conn` as first arg, no auto-commit)
4. Add tests in `tests/test_db.py` or `tests/test_db_v2.py`

### Modifying the Review Loop

1. Changes to loop logic go in `loop/engine.py`
2. Changes to feedback validation go in `loop/feedback.py`
3. Changes to history context go in `loop/history.py`
4. Changes to convergence/caps go in `loop/convergence.py`
5. All changes need tests in `tests/test_engine.py` (mocked reviewer + SDK)
6. Verify output tiers: quiet should only produce one line per round

### Adding a New Reviewer Adapter

1. Create a new class implementing `ReviewerContract` in `reviewer/`
2. Must implement `async review(plan_text, previous_context) -> ReviewerResponse`
3. Populate metadata fields on ReviewerResponse (reviewer_model, cost, tokens, raw_text)
4. Wire into `cli.py` review command (adapter selection based on flag)

## Config Snapshot

Every session stores its config in `session_config` for reproducibility:

```json
{
  "project": "my-api",
  "model_default": "claude-opus-4-6",
  "repo_root": "/path/to/repo",
  "reviewer_model": "gpt-5.4",
  "reasoning_effort": "high",
  "prompt_mode": "keep_trim",
  "review_history": true,
  "validate_feedback": true,
  "filter_severity": ["critical", "major"],
  "fast_mode": false,
  "complexity": "standard",
  "max_rounds": 8
}
```

## Known Issues

- **SDK backend (`--claude-backend sdk`)**: Shares rate-limit quota with active Claude Code sessions. Use default `direct` backend with `ANTHROPIC_API_KEY` whenever possible.
- **Direct backend thinking**: Extended thinking may require beta access. If unavailable, falls back to non-thinking mode with a warning.

## Related Documentation

| Document | Purpose |
|----------|---------|
| `planner-auto/README.md` | User-facing docs, CLI reference, known issues |
| `docs/planner-auto/progress.md` | Project history, experiment results |
| `docs/planner-auto/plans/` | Implementation plans and proposals |
| `docs/plans/planner-auto-proposal-v1.1.md` | Architecture proposal with convergence strategy |
| `scripts/poc/planner-auto/` | POC scripts and experiment data |
| `claude/agents/planner-auto-debugger.md` | Debugging agent with failure patterns |
