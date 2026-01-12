# Plan: Graceful Error Handling with Stack Trace Logging

## Problem Statement

When the orchestrator crashes (e.g., Claude Agent SDK errors, subprocess failures), the error output is unhelpful:

```
Fatal error in message reader: Command failed with exit code 1 (exit code: 1)
Error output: Check stderr for details
```

**Issues:**
- No stack trace visible to diagnose root cause
- Session state may be inconsistent after crash
- No persistent log for post-mortem debugging
- User has no actionable path forward

## Goals

1. **Capture full stack traces** when exceptions occur
2. **Log to persistent file** for post-mortem analysis
3. **Display user-friendly error** with log file path
4. **Mark session as failed** with error context preserved
5. **Optional verbose mode** for immediate stack trace output

## Design Decisions

### Failed Sessions Are Terminal (Not Resumable)

The current state machine sets `phase=COMPLETED` on `FAILED` event (`state.py:234-236`), and `resume` blocks completed sessions (`cli.py:1151-1154`). Rather than modifying the state machine, we keep failures terminal and guide users to re-run with the plan file.

**Rationale:**
- Simpler implementation (no state machine changes)
- Failed sessions may have corrupted conversation context
- Re-running with the plan is cleaner than resuming mid-failure
- Matches existing pattern where completed sessions are immutable

### Per-Session Loggers (Not Root Logger)

Queue mode and watch mode run multiple sessions in one process (`cli.py:655-734`). Configuring the root logger once would either:
- Funnel all sessions into one file, or
- Accumulate handlers across sessions

**Solution:** Create per-session logger instances with dedicated file handlers, torn down after each session completes.

### Session Errors Table (Not Columns)

A dedicated `session_errors` table is more flexible than adding columns to `sessions`:
- Preserves error history (multiple failures per session if retried)
- Supports debugging patterns (query all errors across sessions)
- Cleaner schema separation

## Implementation Plan

### Milestone 1: Logging Infrastructure

**Files:** `orchestrator_auto/logging_config.py` (new)

1. Create logging module with per-session logger factory:
   ```python
   def create_session_logger(session_id: str, debug: bool = False) -> tuple[logging.Logger, str]:
       """
       Create a logger for a specific session.

       Returns:
           tuple of (logger instance, log file path)
       """
   ```

2. Logger configuration:
   - Log directory: `~/.claude_orchestrator/logs/`
   - Log file naming: `error_<session_id>_<timestamp>.log`
   - Format: `%(asctime)s | %(levelname)s | %(name)s | %(message)s`
   - File handler per session (not rotating - one file per crash)
   - Console handler only when `debug=True`

3. Teardown function for queue/watch compatibility:
   ```python
   def teardown_session_logger(logger: logging.Logger) -> None:
       """Remove and close all handlers from session logger."""
   ```

**Deliverables:**
- [ ] `logging_config.py` with `create_session_logger()` and `teardown_session_logger()`
- [ ] Log directory auto-creation (`~/.claude_orchestrator/logs/`)
- [ ] Per-session file handler (isolated from other sessions)

### Milestone 2: Custom Exception Hierarchy

**Files:** `orchestrator_auto/exceptions.py` (new)

1. Create exception classes:
   ```python
   class OrchestratorError(Exception):
       """Base exception for orchestrator errors."""
       def __init__(self, message: str, session_id: str = None, log_path: str = None):
           self.session_id = session_id
           self.log_path = log_path
           super().__init__(message)

   class AgentError(OrchestratorError):
       """Claude Agent SDK communication failure."""
       pass

   class SessionStateError(OrchestratorError):
       """Invalid state transition or corrupted session."""
       pass

   class PlanParseError(OrchestratorError):
       """Malformed plan file."""
       pass
   ```

**Deliverables:**
- [ ] `exceptions.py` with `OrchestratorError`, `AgentError`, `SessionStateError`, `PlanParseError`
- [ ] All exceptions carry `session_id` and `log_path` for error reporting

### Milestone 3: Exception Handlers in Engine

**Files:** `orchestrator_auto/engine.py`

1. Add logger initialization in `Orchestrator.__init__()`:
   ```python
   # After session_id is created/loaded
   self._logger, self._log_path = create_session_logger(self.session_id, debug=self._debug)
   ```

2. Wrap agent calls in try/except blocks:
   - `_run_discovery_loop()` - planner agent calls
   - `_run_planning()` - planner agent calls
   - `_run_execution_loop()` - executor + planner calls
   - `_route_to_planner()` / `_route_to_executor()`

3. On exception in `start()` method (top-level catch around phase routing):
   ```python
   def start(self) -> str:
       """Main orchestration entry point."""
       try:
           # Phase routing logic
           if self._state.phase == Phase.DISCOVERY:
               self._run_discovery_loop()
           elif self._state.phase == Phase.PLANNING:
               self._run_planning()
           elif self._state.phase == Phase.EXECUTION:
               self._run_execution_loop()
           # ... etc
       except KeyboardInterrupt:
           # User cancelled - don't mark as failed
           raise
       except Exception as e:
           self._handle_fatal_error(e)
           raise  # Re-raise typed OrchestratorError
       finally:
           if self._logger:
               teardown_session_logger(self._logger)
   ```

4. Add `_handle_fatal_error()` helper (critical for session state consistency):
   ```python
   def _handle_fatal_error(self, error: Exception) -> None:
       """
       Handle fatal error: mark session failed, log to DB and file.

       This ensures session row is marked failed even if queue mode
       only catches at CLI level (cli.py:878).
       """
       import traceback

       # Log full stack trace to file
       self._logger.exception("Orchestration failed")

       # Get current state for context
       session = db.get_session(self.session_id, self._db_path)
       current_phase = session.get("phase") if session else "unknown"
       current_milestone = session.get("current_milestone") if session else None

       # Transition to FAILED state (sets phase=completed, status=failed)
       self._state_machine.transition(
           TransitionEvent.FAILED,
           self.session_id,
           self._db_path
       )

       # Persist error details to session_errors table
       stack_trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
       db.log_session_error(
           session_id=self.session_id,
           error_type=type(error).__name__,
           error_message=str(error),
           stack_trace=stack_trace,
           phase=current_phase,
           milestone_number=current_milestone,
           log_file_path=self._log_path,
           db_path=self._db_path
       )

       # Wrap and re-raise as typed exception for CLI boundary
       raise AgentError(
           str(error),
           session_id=self.session_id,
           log_path=self._log_path
       ) from error
   ```

   **Why this matters:** Queue mode (`cli.py:878`) catches exceptions and marks the *queue item* failed, but without engine-level handling the *session row* remains "active". This causes:
   - `orchestrator list` shows session as active (misleading)
   - Stuck session detection may flag it incorrectly
   - No error context preserved in session_errors table

**Deliverables:**
- [ ] Logger initialized after session_id exists
- [ ] Top-level try/except in `start()` around phase routing
- [ ] `_handle_fatal_error()` helper that:
  - Transitions session via `TransitionEvent.FAILED`
  - Persists error to `session_errors` table with log_file_path
  - Re-raises as `AgentError` with session context
- [ ] `KeyboardInterrupt` excluded from failure handling (user cancel)
- [ ] Logger teardown in finally block (queue/watch safe)

### Milestone 4: CLI Error Boundary

**Files:** `orchestrator_auto/cli.py`

1. Add `--debug` flag to `start`, `resume`, `chat` commands:
   ```python
   @click.option("--debug", is_flag=True, help="Print full stack trace on error")
   ```

2. Add error boundary in CLI commands:
   ```python
   try:
       orch.start()
   except OrchestratorError as e:
       _handle_orchestrator_error(e, debug=debug)
       sys.exit(1)
   except Exception as e:
       _handle_unexpected_error(e, debug=debug)
       sys.exit(1)
   ```

3. User-friendly error output (conditional on plan_path):
   ```python
   def _handle_orchestrator_error(e: OrchestratorError, debug: bool) -> None:
       click.secho(f"Error: {e}", fg="red", bold=True)
       click.echo()
       click.echo(f"Session: {e.session_id} (status: failed)")
       if e.log_path:
           click.echo(f"Log file: {e.log_path}")
       click.echo()

       # Conditional retry guidance based on plan_path
       session = db.get_session(e.session_id)
       if session and session.get("plan_path"):
           click.echo("To retry with the same plan:")
           click.secho(f"  orchestrator start --plan {session['plan_path']}", fg="cyan")
       elif session and session.get("feature_description"):
           click.echo("To retry with the same feature:")
           click.secho(f'  orchestrator start -f "{session["feature_description"]}"', fg="cyan")
       else:
           click.echo("To start a new session:")
           click.secho('  orchestrator start -f "your feature"', fg="cyan")

       click.echo()
       click.echo("Use --debug flag for full stack trace.")

       if debug:
           import traceback
           click.echo()
           click.secho("Stack trace:", fg="yellow")
           traceback.print_exception(type(e.__cause__), e.__cause__, e.__cause__.__traceback__)
   ```

4. Pass `debug` flag to `Orchestrator` constructor for logger config.

**Deliverables:**
- [ ] `--debug` flag on `start`, `resume`, `chat` commands
- [ ] Error boundary with `_handle_orchestrator_error()` helper
- [ ] Conditional retry guidance:
  - If `plan_path` exists: `orchestrator start --plan <path>`
  - Else if `feature_description` exists: `orchestrator start -f "<feature>"`
  - Else: generic "start a new session" guidance
- [ ] Stack trace printed to stderr when `--debug` is set

### Milestone 5: Database Schema for Error Tracking

**Files:** `orchestrator_auto/db.py`

1. Add `session_errors` table in `init_db()`:
   ```sql
   CREATE TABLE IF NOT EXISTS session_errors (
       id INTEGER PRIMARY KEY,
       session_id TEXT NOT NULL,
       error_type TEXT NOT NULL,
       error_message TEXT NOT NULL,
       stack_trace TEXT,
       phase TEXT,
       milestone_number INTEGER,
       log_file_path TEXT,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       FOREIGN KEY (session_id) REFERENCES sessions(id)
   );
   CREATE INDEX IF NOT EXISTS idx_session_errors_session_id ON session_errors(session_id);
   ```

2. Add functions:
   ```python
   def log_session_error(
       session_id: str,
       error_type: str,
       error_message: str,
       stack_trace: str,
       phase: str,
       milestone_number: int,
       log_file_path: str,
       db_path: str = None
   ) -> int:
       """Log error to session_errors table. Returns error id."""

   def get_session_errors(session_id: str, db_path: str = None) -> list[dict]:
       """Get all errors for a session, ordered by created_at desc."""
   ```

3. Update `status` command to show error details for failed sessions:
   ```
   Session: abc123
   Status: failed
   Phase: execution (milestone 2/4)

   Last Error: AgentError - Command failed with exit code 1
   Log: ~/.claude_orchestrator/logs/error_abc123_20260112_143022.log

   To retry: orchestrator start --plan docs/abc123/DOC_abc123_plan.md
   ```

   If no plan_path exists (crashed during discovery/planning):
   ```
   Session: def456
   Status: failed
   Phase: discovery

   Last Error: AgentError - Connection timeout
   Log: ~/.claude_orchestrator/logs/error_def456_20260112_150000.log

   To retry: orchestrator start -f "Add user authentication"
   ```

**Deliverables:**
- [ ] `session_errors` table with index
- [ ] `log_session_error()` function
- [ ] `get_session_errors()` function
- [ ] `status` command shows error details for failed sessions
- [ ] `status` command shows conditional retry guidance (plan_path vs feature)

### Milestone 6: Testing & Documentation

**Files:** `tests/test_error_handling.py` (new), `README.md`

1. Unit tests:
   - `test_create_session_logger()` - creates logger with file handler
   - `test_teardown_session_logger()` - removes handlers cleanly
   - `test_exception_classes()` - verify exception attributes
   - `test_session_marked_failed()` - mock agent failure, check status=failed via TransitionEvent.FAILED
   - `test_error_persisted_to_db()` - verify session_errors row created with log_file_path
   - `test_multiple_sessions_isolated_logs()` - queue mode simulation
   - `test_retry_guidance_with_plan()` - verify `--plan` guidance when plan_path exists
   - `test_retry_guidance_without_plan()` - verify `-f` guidance when only feature exists
   - `test_keyboard_interrupt_not_failed()` - verify Ctrl+C doesn't mark session failed

2. Integration tests:
   - Simulate agent failure, verify log file created with stack trace
   - Verify session status is `failed` after error
   - Verify `status` command shows error details

3. Update README with troubleshooting section:
   - Document `--debug` flag
   - Document log file location
   - Document error recovery workflow (re-run with plan)

**Deliverables:**
- [ ] `tests/test_error_handling.py` with unit tests
- [ ] Integration tests for error flow
- [ ] README troubleshooting section

## File Changes Summary

| File | Change Type |
|------|-------------|
| `orchestrator_auto/logging_config.py` | New |
| `orchestrator_auto/exceptions.py` | New |
| `orchestrator_auto/engine.py` | Modify |
| `orchestrator_auto/cli.py` | Modify |
| `orchestrator_auto/db.py` | Modify |
| `tests/test_error_handling.py` | New |
| `README.md` | Modify |

## Configuration

Add to `config.yaml` schema:
```yaml
logging:
  level: INFO  # DEBUG, INFO, WARNING, ERROR
  log_dir: ~/.claude_orchestrator/logs  # override default
```

## Success Criteria

1. Any crash produces a log file with full stack trace
2. User sees clear error message with log file path
3. Failed session shows error details in `orchestrator status`
4. `--debug` flag prints stack trace immediately to stderr
5. Queue/watch mode: each session gets isolated log file
6. Session row marked `failed` (not stuck as `active`) via `TransitionEvent.FAILED`
7. Conditional retry guidance:
   - With plan: `orchestrator start --plan <path>`
   - Without plan: `orchestrator start -f "<feature>"`
8. `KeyboardInterrupt` does not mark session as failed

## Out of Scope

- Resumable failed sessions (kept terminal for simplicity)
- Remote error reporting/telemetry
- Automatic crash recovery
- Error alerting via Telegram (could be added later)
- Log rotation (one file per crash is sufficient)
