# Planner-Auto Observability & Debug - Implementation Plan

## Overview
Add comprehensive logging, DB inspection, and debug tooling to planner-auto. Shared root logger with session-id context injection captures all module logs into session-scoped files. New `inspect` CLI commands expose review state, dispositions, and reconstructed history. Three-tier output (headless/verbose/debug) preserves quiet default while enabling deep diagnostics. `check` command validates environment without live API calls by default.

## Milestone 1: Logger Architecture and Per-Command Wiring

Rewrite the logging module to use a shared root logger with session-id context injection, and wire --verbose/--debug into every session-aware command.

### Tasks
- [ ] Rewrite `planner_auto/logging.py`: replace `setup_session_logger()` with `setup_session_logging(session_id, verbose, debug)` that attaches handlers to the `planner_auto` root logger (not a per-session named logger). Add `SessionFilter(logging.Filter)` that injects `session_id` into all log records. File handler always at DEBUG to `~/.planner-auto/logs/<session-id>.log`. Stderr handler only when verbose (INFO) or debug (DEBUG). Clear existing handlers before attaching to prevent duplicates on re-attach.
- [ ] Update log format to include session_id: `"%(asctime)s [%(levelname)s] %(name)s (%(session_id)s): %(message)s"`.
- [ ] Add `--verbose` and `--debug` flags to all session-aware commands: `discuss`, `generate`, `review`, `export`, `complete`, `resume`. Each command calls `setup_session_logging(session_id, verbose, debug)` after resolving session_id. Keep existing flags on `start` (backward compatible).
- [ ] Ensure all modules use `logging.getLogger("planner_auto.<module>")` naming convention so they are children of the root `planner_auto` logger: verify `agents.py`, `session.py`, `sdk_wrapper.py`, `db.py`, `export.py`, `reviewer/direct_api.py`, `reviewer/parser.py`, `loop/engine.py`, `loop/feedback.py`, `loop/history.py`, `loop/convergence.py`, `git_utils.py`. Add `logger = logging.getLogger(__name__)` to any module missing it.
- [ ] Create `tests/test_logging.py`: SessionFilter injects session_id, setup_session_logging creates file handler, verbose adds stderr handler, debug sets DEBUG level, re-attach clears old handlers, module loggers flow to root. 8+ tests.

### Deliverables
- [ ] `planner_auto/logging.py` rewritten with shared root logger + SessionFilter
- [ ] All session-aware commands accept --verbose/--debug
- [ ] All modules use `logging.getLogger(__name__)` naming
- [ ] `pytest tests/test_logging.py` passes with 8+ tests

## Milestone 2: Structured Logging Across All Modules

Add log calls at key decision points in every module. Not every line — just the decisions that affect session state or would help diagnose issues.

### Tasks
- [ ] `cli.py`: log command invoked with session_id and flags at INFO on every command entry.
- [ ] `session.py`: log phase transitions (`INFO: Phase {old} → {new}`), pause/resume (`INFO: Session paused, blocker: {source}`), command permission checks that fail (`WARNING: Command {cmd} blocked in phase {phase}`).
- [ ] `agents.py`: log SDK call start (`INFO: Calling Claude for {purpose}, model={model}`), call end (`INFO: Claude responded, {len} chars, {duration}ms`), synthesis result size (`INFO: Context synthesized, {words} words`).
- [ ] `sdk_wrapper.py`: log config applied (`DEBUG: effort={effort}, thinking={thinking}, max_turns={max_turns}`), retry attempts (`WARNING: Rate limited, retry {n}/{max} in {delay}s`), timeout (`WARNING: Timeout after {sec}s, retrying`).
- [ ] `db.py`: log schema migration (`WARNING: Migrating schema v{old} → v{new}`), schema version check (`DEBUG: Schema version: {v}`).
- [ ] `reviewer/parser.py`: log parse stage used (`DEBUG: Parsed as {stage}: JSON/XML/free-form/failure`), fallback triggered (`DEBUG: JSON parse failed, trying XML`).
- [ ] `loop/engine.py`: log round start (`INFO: Round {n} starting`), verdict (`INFO: Round {n}: {verdict}, {count} issues`), stop reason (`INFO: Loop stopped: {reason}`), total cost (`INFO: Loop complete: {rounds} rounds, ${cost}`).
- [ ] `loop/feedback.py`: log per-issue disposition (`INFO: Issue {i}: {disposition} — {description[:60]}`).
- [ ] `loop/history.py`: log context size (`DEBUG: History context: {len} chars, {defer_count} cumulative defers`).
- [ ] `loop/convergence.py`: log complexity detected (`INFO: Complexity: {level}, keywords: {matches}, cap: {rounds}`).
- [ ] `export.py`: log files written (`INFO: Exported {filename}, {size} bytes`), .kafra handoff (`INFO: Copied to {path}` or `WARNING: .kafra skipped, no repo root`).
- [ ] Create `tests/test_structured_logging.py`: verify key log messages are emitted at correct levels for phase transition, SDK call, review round, disposition, and export. Use `caplog` fixture. 10+ tests.

### Deliverables
- [ ] Every module emits structured logs at documented decision points
- [ ] Log levels follow convention: INFO for state changes, WARNING for retries/skips, DEBUG for internal details
- [ ] `pytest tests/test_structured_logging.py` passes with 10+ tests

## Milestone 3: Review Loop Output Tiers

Implement the three-tier stdout output for the review loop: headless default, verbose, and debug.

### Tasks
- [ ] Add `_emit_progress(round_num, verdict, issue_count, ...)` method to `ReviewLoopEngine` that formats output based on the configured verbosity level (read from `self.config`).
- [ ] **Default (headless):** one line per round: `"Round {n}: {verdict} ({count} issues) → revising..."`. Final line: `"Converged in {n} rounds. ${cost} total."` or `"Cap reached after {n} rounds. ${cost} total."`. Suitable for piping and .kafra pipeline.
- [ ] **Verbose (--verbose):** full round block with separator, GPT model/latency/tokens/cost, keep/trim counts, per-issue disposition with description, revision model/latency/cost, draft size change, history context size.
- [ ] **Debug (--debug):** all of verbose plus raw GPT response text, full history context string sent to GPT, full revision prompt text sent to Claude. Prepend each with `"⚠ DEBUG OUTPUT — may contain sensitive content"` warning.
- [ ] Wire verbosity into engine config: `self.config["verbosity"]` = "quiet" (default), "verbose", or "debug". Set from CLI flags.
- [ ] Create `tests/test_loop_output.py`: verify headless output is one line per round (no excess), verbose includes model/tokens/dispositions, debug includes raw response warning. Use `capsys` or `capfd`. 6+ tests.

### Deliverables
- [ ] Default review loop output is one line per round (headless-safe)
- [ ] --verbose shows full round details with metrics and dispositions
- [ ] --debug shows raw API content with security warning
- [ ] `pytest tests/test_loop_output.py` passes with 6+ tests

## Milestone 4: DB Inspection Commands and Check Command

Add the `inspect` CLI subgroup for session debugging and the `check` command for environment validation.

### Tasks
- [ ] Create `planner_auto/inspect.py` with query functions: `format_reviews_table(conn, session_id)`, `format_dispositions(conn, session_id, round_num)`, `format_config(conn, session_id)`, `reconstruct_history(conn, session_id, round_num)` (calls `build_review_context()` from history.py), `format_raw_response(conn, session_id, round_num)`, `dump_session_json(conn, session_id)`.
- [ ] Wire `inspect` as a Click subgroup in `cli.py` with commands: `reviews`, `dispositions`, `config`, `history`, `raw-response`, `dump`. Each accepts `session-id` and relevant options (--round, --output).
- [ ] `inspect history` documents output as "reconstructed from DB state, not stored" in the help text.
- [ ] `inspect raw-response` and `inspect dump` print a security warning: `"⚠ Output may contain repository content and API responses. Do not share without redaction."`.
- [ ] Create `check` command in `cli.py`. Default (safe): check `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` set, check `OPENAI_API_KEY` set, check `claude` on PATH via `shutil.which`, check `openai` importable, check DB path writable, check schema version current. Print pass/fail per check. With `--probe`: send trivial prompt to Claude SDK and OpenAI API, report latency.
- [ ] Create `tests/test_inspect.py`: reviews formatting, dispositions for specific round, config display, history reconstruction matches `build_review_context()` output, dump contains all tables, raw-response includes security warning. Create `tests/test_check.py`: env var detection, path checks, schema version, --probe skipped by default. 12+ tests total.

### Deliverables
- [ ] `planner-auto inspect reviews/dispositions/config/history/raw-response/dump` all working
- [ ] `planner-auto check` validates environment safely; `--probe` for live API checks
- [ ] `pytest tests/test_inspect.py tests/test_check.py` passes with 12+ tests

## Milestone 5: Error Diagnostics and Integration

Add --debug traceback printing to all commands, verify all logging flows end-to-end, and run the full test suite.

### Tasks
- [ ] Add traceback printing on --debug to all commands that catch exceptions. Pattern: `if ctx.obj.get("debug"): import traceback; traceback.print_exc()`. Apply to: `start`, `discuss`, `generate`, `review`, `export`, `complete`, `resume`, `add-context`.
- [ ] Verify end-to-end logging flow: run `planner-auto start --debug --project test`, `add-context`, `discuss`, `generate` and confirm all module logs appear in `~/.planner-auto/logs/<session-id>.log` with session_id in each line.
- [ ] Verify review loop logging: mock a 2-round review and confirm engine, feedback, history, convergence, and adapter logs all appear in the session log file.
- [ ] Create `tests/test_error_diagnostics.py`: SDK error with --debug prints traceback, SDK error without --debug prints one-line message only, reviewer error includes traceback on --debug, session error (invalid transition) includes traceback on --debug. 6+ tests.
- [ ] Run full test suite `pytest tests/` confirming all existing Plan 1 + Plan 2 tests still pass alongside new observability tests.

### Deliverables
- [ ] --debug prints full tracebacks on all commands
- [ ] Session log file captures all module activity for a full session lifecycle
- [ ] `pytest tests/test_error_diagnostics.py` passes with 6+ tests
- [ ] `pytest tests/` passes with all tests green
