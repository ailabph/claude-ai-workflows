# Implementation Plan: Add --tui Flag to `respond` Command

## Overview

Add TUI support to the `orchestrator respond` command so users can respond to blockers with a rich text user interface instead of CLI-only mode.

**Command signature:**
```bash
orchestrator respond <session_id> "my reply" --tui
```

## Current State Analysis

### Current `respond` Command (cli.py:1596-1638)
```python
@cli.command()
@click.argument('session_id')
@click.argument('answer')
@click.option('--db-path', '-d')
@click.option('--telegram/--no-telegram', default=None)
@click.option('--mcp-config', type=click.Path(exists=True))
@click.option('--headless', is_flag=True, default=False)
def respond(session_id, answer, db_path, telegram, mcp_config, headless):
    # Validates session exists and is paused
    # Validates unresolved blocker exists
    # Invokes resume command with answer
    ctx.invoke(resume, session_id=session_id, answer=answer, ...)
```

### Current TUI Architecture
- `OrchestratorTUI` (tui/app.py) supports:
  - `feature` - for new workflows
  - `session_id` - for resuming sessions
  - Does NOT support `answer` parameter for blocker resolution
- `_run_orchestrator()` calls `orchestrator.start()` only
- For paused sessions with blockers, `orchestrator.resume(answer)` must be called first

### Key Insight
When a session is in `paused` phase, `orchestrator.start()` does nothing because none of the phase conditions match (discovery/planning/execution/completed).

**Critical**: `resume(answer)` already calls `start()` internally (engine.py:514), and `start()` always runs `_cleanup()` in its finally block (engine.py:458-460). Therefore:
- Call `resume(answer)` ONLY - it handles everything
- Do NOT call both `resume()` and `start()` - that would execute `start()` twice and double-cleanup

---

## Implementation Plan

### Milestone 1: Extend OrchestratorTUI to Support Answer Parameter

**Files to modify:**
- `orchestrator_auto/tui/app.py`

**Changes:**

1. Add `answer` parameter to `OrchestratorTUI.__init__`:
```python
def __init__(
    self,
    feature: str = "",
    db_path: Optional[str] = None,
    plan_path: Optional[str] = None,
    planner_model: Optional[str] = None,
    executor_model: Optional[str] = None,
    session_id: Optional[str] = None,
    answer: Optional[str] = None,  # NEW
    mcp_config_path: Optional[str] = None,  # NEW (for parity)
    headless: bool = False,  # NEW (for parity)
    telegram_notifier = None,  # NEW (for parity)
    **kwargs,
) -> None:
    # ...
    self.answer = answer
    self.mcp_config_path = mcp_config_path
    self.headless = headless
    self.telegram_notifier = telegram_notifier
```

2. Modify `_run_orchestrator()` to handle answer:

**IMPORTANT**: `resume(answer)` already calls `start()` internally (engine.py:514), and `start()` always calls `_cleanup()` in its finally block (engine.py:458-460). Therefore we must NOT call both `resume()` and `start()` - that would call `start()` twice.

```python
def _run_orchestrator(self) -> None:
    from ..engine import Orchestrator

    try:
        self._orchestrator = Orchestrator(
            feature_description=self.feature,
            db_path=self.db_path,
            plan_path=self.plan_path,
            session_id=self.session_id,
            on_chunk=self._adapter.on_chunk,
            on_state_change=self._adapter.on_state_change,
            on_output=self._adapter.on_output,
            input_provider=self._input_provider,
            planner_model=self.planner_model,
            executor_model=self.executor_model,
            mcp_config_path=self.mcp_config_path,  # NEW
            headless=self.headless,  # NEW
            telegram_notifier=self.telegram_notifier,  # NEW
            show_activity=False,
        )

        # Notify TUI with model info
        self._adapter.notify_models_set(...)

        # Notify TUI
        self._adapter.notify_workflow_started(...)

        # Branch: resume with answer OR start fresh
        # NOTE: resume() internally calls start(), so we must not call both
        if self.session_id and self.answer:
            self._orchestrator.resume(self.answer)
        else:
            self._orchestrator.start()

        # Notify completion
        self._adapter.notify_workflow_completed(...)

    except Exception as e:
        self._adapter.notify_workflow_error(str(e))
```

**Deliverables:**
- [x] `answer` parameter added to TUI constructor
- [x] `mcp_config_path`, `headless`, `telegram_notifier` parameters added for feature parity
- [x] `_run_orchestrator` branches: `resume(answer)` OR `start()`

---

### Milestone 2: Add --tui Flag to respond Command

**Files to modify:**
- `orchestrator_auto/cli.py`

**Changes:**

1. Add `--tui` option to respond command:
```python
@cli.command()
@click.argument('session_id')
@click.argument('answer')
@click.option('--db-path', '-d', help='Custom database path')
@click.option('--telegram/--no-telegram', default=None, help='Enable/disable Telegram notifications')
@click.option('--mcp-config', type=click.Path(exists=True), help='Path to MCP configuration file')
@click.option('--headless', is_flag=True, default=False, help='Run Playwright MCP browser in headless mode')
@click.option('--tui', is_flag=True, help='Run in TUI (Text User Interface) mode')  # NEW
def respond(session_id: str, answer: str, db_path: Optional[str], telegram: Optional[bool], mcp_config: Optional[str], headless: bool, tui: bool):
```

2. Add TUI handling at start of respond function:

**IMPORTANT**: Handle TUI mode FIRST before any `click.echo()` calls (following pattern from `todo` command, cli.py:3816). This prevents stray terminal output before Textual takes over the screen.

```python
def respond(session_id, answer, db_path, telegram, mcp_config, headless, tui):
    """Respond to a blocker and continue workflow."""
    try:
        # Initialize database
        db.init_db(db_path)

        # Validate session exists and is paused
        session = db.get_session(session_id, db_path)
        if not session:
            click.secho(f"✗ Session '{session_id}' not found", fg="red")
            sys.exit(1)

        if session['status'] != Status.PAUSED:
            click.secho(f"✗ Session is not paused (status: {session['status']})", fg="red")
            sys.exit(1)

        # Get unresolved blockers
        blockers = db.get_unresolved_blockers(session_id, db_path)
        if not blockers:
            click.secho("✗ No unresolved blockers found", fg="red")
            sys.exit(1)

        # Handle TUI mode FIRST (before any click.echo() calls)
        # This prevents stray terminal output before Textual takes over
        if tui:
            _start_respond_tui(
                session_id=session_id,
                answer=answer,
                db_path=db_path,
                telegram=telegram,
                mcp_config=mcp_config,
                headless=headless,
            )
            return

        # Non-TUI mode: existing behavior (click.echo() is safe here)
        click.secho(f"Responding to session: {session_id}", fg="cyan", bold=True)
        click.echo()
        click.echo(f"Question: {blockers[0]['question']}")
        click.echo(f"Answer: {answer}")
        click.echo()

        ctx = click.get_current_context()
        ctx.invoke(resume, session_id=session_id, answer=answer, db_path=db_path, telegram=telegram, mcp_config=mcp_config, headless=headless)

    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red", bold=True)
        sys.exit(1)
```

3. Add `_start_respond_tui` helper function (near other `_start_*_tui` functions):

**IMPORTANT**: Follow Telegram tri-state behavior from `resume` command (cli.py:1312-1315):
- `--telegram` explicitly enables
- `--no-telegram` explicitly disables
- Omitted → enabled if configured (check `if telegram is not False`)

```python
def _start_respond_tui(
    session_id: str,
    answer: str,
    db_path: Optional[str],
    telegram: Optional[bool],
    mcp_config: Optional[str],
    headless: bool,
) -> None:
    """
    Start respond mode with TUI dashboard.

    Launches the Textual-based OrchestratorTUI app for rich visual feedback
    when responding to a blocker.

    Args:
        session_id: Session ID to respond to
        answer: Answer to the blocker question
        db_path: Optional database path
        telegram: Telegram tri-state (True=enabled, False=disabled, None=auto from config)
        mcp_config: Path to MCP configuration file
        headless: Whether to run Playwright browser headless
    """
    try:
        from .tui import get_app_class, check_textual_available
        check_textual_available()
    except ImportError:
        click.secho("Error: Textual is not installed.", fg="red", bold=True)
        click.echo()
        click.echo("Install TUI support with:")
        click.secho('  pip install -e ".[tui]"', fg="cyan")
        click.echo()
        click.echo("Or install textual directly:")
        click.secho("  pip install textual", fg="cyan")
        sys.exit(1)

    # Setup Telegram notifier if configured (tri-state: not explicitly disabled)
    # Matches resume command behavior (cli.py:1312-1315)
    telegram_notifier = None
    if telegram is not False:  # Not explicitly disabled
        telegram_notifier = _create_telegram_notifier(telegram)

    # Get the OrchestratorTUI class and instantiate
    OrchestratorTUI = get_app_class()
    app = OrchestratorTUI(
        session_id=session_id,
        answer=answer,
        db_path=db_path,
        mcp_config_path=mcp_config,
        headless=headless,
        telegram_notifier=telegram_notifier,
    )

    # Run the TUI
    app.run()
```

**Deliverables:**
- [x] `--tui` flag added to respond command
- [x] TUI handling branch added to respond function
- [x] `_start_respond_tui` helper function created

---

### Milestone 3: Update tui/__init__.py Exports (Optional)

**Files to modify:**
- `orchestrator_auto/tui/__init__.py`

No changes needed - `get_app_class()` already returns `OrchestratorTUI` which we're extending.

---

### Milestone 4: Add Tests

**Files to create/modify:**
- `orchestrator_auto/tests/test_tui.py`
- `orchestrator_auto/tests/test_cli.py`

**New tests in test_tui.py:**

**IMPORTANT**: Follow existing pattern - use `pytest.importorskip("textual")` at module level (test_tui.py:11) to skip all TUI tests when Textual is not installed. Do NOT import Textual unconditionally.

```python
# At top of file (already exists in test_tui.py:11)
pytest.importorskip("textual")


class TestOrchestratorTUIRespond:
    """Test OrchestratorTUI with answer parameter for respond mode."""

    def test_init_with_answer(self):
        """Test OrchestratorTUI can be initialized with answer parameter."""
        from orchestrator_auto.tui.app import OrchestratorTUI

        app = OrchestratorTUI(
            session_id="test-session-123",
            answer="my answer to blocker",
        )
        assert app.session_id == "test-session-123"
        assert app.answer == "my answer to blocker"

    def test_init_without_answer(self):
        """Test OrchestratorTUI works without answer (existing behavior)."""
        from orchestrator_auto.tui.app import OrchestratorTUI

        app = OrchestratorTUI(feature="Test feature")
        assert app.feature == "Test feature"
        assert app.answer is None

    def test_init_with_mcp_config(self):
        """Test OrchestratorTUI accepts mcp_config_path parameter."""
        from orchestrator_auto.tui.app import OrchestratorTUI

        app = OrchestratorTUI(
            feature="Test feature",
            mcp_config_path="/path/to/mcp.json",
            headless=True,
        )
        assert app.mcp_config_path == "/path/to/mcp.json"
        assert app.headless is True
```

**New tests in test_cli.py:**

```python
from unittest.mock import patch


class TestRespondTUIFlag:
    """Test respond command --tui flag."""

    def test_respond_has_tui_option(self):
        """Test that respond command has --tui option."""
        from orchestrator_auto.cli import respond

        # Check that --tui is a valid option
        params = {p.name for p in respond.params}
        assert 'tui' in params

    def test_respond_tui_missing_textual(self, tmp_path, monkeypatch):
        """Test respond --tui shows helpful error when textual not installed."""
        from click.testing import CliRunner
        from orchestrator_auto.cli import cli
        from orchestrator_auto import db
        from orchestrator_auto.state import Status

        # Create a paused session with blocker
        db_path = str(tmp_path / "test.db")
        db.init_db(db_path)
        session_id = db.create_session("Test feature", db_path=db_path)
        db.update_session(session_id, {"phase": "paused", "status": Status.PAUSED}, db_path=db_path)
        db.create_blocker(session_id, "executor", "What color?", db_path=db_path)

        # Mock check_textual_available in orchestrator_auto.tui (where it's defined)
        # _start_respond_tui imports from .tui, so patch at source
        def mock_check():
            raise ImportError("Textual is not installed")

        monkeypatch.setattr("orchestrator_auto.tui.check_textual_available", mock_check)

        runner = CliRunner()
        result = runner.invoke(cli, [
            'respond', session_id, 'blue', '--tui', '--db-path', db_path
        ])

        assert result.exit_code == 1
        assert "Textual is not installed" in result.output

    @patch('orchestrator_auto.cli.resume')
    def test_respond_without_tui_works(self, mock_resume, tmp_path):
        """Test respond without --tui follows existing behavior."""
        from click.testing import CliRunner
        from orchestrator_auto.cli import cli
        from orchestrator_auto import db
        from orchestrator_auto.state import Status

        # Create a paused session with blocker
        db_path = str(tmp_path / "test.db")
        db.init_db(db_path)
        session_id = db.create_session("Test feature", db_path=db_path)
        db.update_session(session_id, {"phase": "paused", "status": Status.PAUSED}, db_path=db_path)
        db.create_blocker(session_id, "executor", "What color?", db_path=db_path)

        runner = CliRunner()
        result = runner.invoke(cli, [
            'respond', session_id, 'blue', '--db-path', db_path
        ])

        # Should show question/answer and invoke resume
        assert "What color?" in result.output
        assert "blue" in result.output
```

**Deliverables:**
- [x] Unit tests for OrchestratorTUI with answer parameter
- [x] CLI tests for --tui flag on respond command
- [x] Error handling test for missing Textual

---

### Milestone 5: Update Documentation

**Files to modify:**
- `orchestrator_auto/docs/CONFIGURATION.md`
- `orchestrator_auto/resources/CONFIGURATION.md`
- `CLAUDE.md` (if CLI usage section needs update)

**Documentation updates:**

Add to CLI reference section:
```markdown
### respond

Respond to a blocker and continue workflow.

```bash
orchestrator respond <session_id> "answer" [OPTIONS]
```

**Options:**
| Option | Description |
|--------|-------------|
| `--db-path`, `-d` | Custom database path |
| `--telegram/--no-telegram` | Enable/disable Telegram notifications |
| `--mcp-config` | Path to MCP configuration file |
| `--headless` | Run Playwright MCP browser in headless mode |
| `--tui` | Run in TUI (Text User Interface) mode |

**Examples:**
```bash
# CLI mode (default)
orchestrator respond abc123 "Use JWT tokens"

# TUI mode with rich visual feedback
orchestrator respond abc123 "Use JWT tokens" --tui
```
```

**Deliverables:**
- [x] CONFIGURATION.md updated with --tui flag
- [x] resources/CONFIGURATION.md synced

---

## File Change Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `orchestrator_auto/tui/app.py` | Modify | Add `answer`, `mcp_config_path`, `headless`, `telegram_notifier` params; update `_run_orchestrator()` |
| `orchestrator_auto/cli.py` | Modify | Add `--tui` flag to respond; add `_start_respond_tui()` helper |
| `tests/test_tui.py` | Modify | Add tests for answer parameter |
| `tests/test_cli.py` | Modify | Add tests for respond --tui flag |
| `docs/CONFIGURATION.md` | Modify | Document --tui flag |
| `orchestrator_auto/resources/CONFIGURATION.md` | Modify | Sync with docs |

---

## Testing Strategy

1. **Unit tests**: Verify TUI class accepts new parameters
2. **CLI tests**: Verify --tui flag exists and works
3. **Integration tests** (optional): Test full flow with mocked orchestrator
4. **Manual testing**:
   ```bash
   # Create a session that will hit a blocker
   orchestrator start -f "Test feature"
   # When blocked, test respond with TUI
   orchestrator respond <session-id> "my answer" --tui
   ```

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| TUI threading issues with answer injection | Answer is passed before orchestrator starts, no race condition |
| Breaking existing respond behavior | TUI is opt-in flag, default behavior unchanged |
| Missing Textual dependency | Same error handling pattern as watch/todo commands |

---

## Dependencies

- Textual library (optional, for TUI mode)
- No new dependencies required

---

## Estimated Complexity

- **Milestone 1**: Low - Adding parameters and simple conditional
- **Milestone 2**: Low - Following existing pattern from watch command
- **Milestone 3**: N/A - No changes needed
- **Milestone 4**: Medium - Writing comprehensive tests
- **Milestone 5**: Low - Documentation updates

**Total: Low-Medium complexity**

---

## Review Notes (v2)

Corrections applied based on code review:

1. **`resume()` calls `start()` internally** (engine.py:514)
   - Original plan: call `resume(answer)` then `start()`
   - Fixed: call `resume(answer)` ONLY when responding with answer
   - Rationale: `start()` has cleanup in finally block (engine.py:458-460), calling twice causes issues

2. **TUI branch must come FIRST** (before any `click.echo()`)
   - Follows pattern from `todo` command (cli.py:3816)
   - Prevents stray terminal output before Textual takes over screen

3. **Telegram tri-state behavior** (cli.py:1312-1315)
   - `--telegram` → explicitly enabled
   - `--no-telegram` → explicitly disabled
   - Omitted → enabled if configured (`if telegram is not False`)
   - `_start_respond_tui` must follow same pattern as `resume` command

4. **TUI tests must use `pytest.importorskip("textual")`** (test_tui.py:11)
   - Do NOT import Textual unconditionally
   - Tests will be skipped when Textual is not installed

## Review Notes (v3)

Additional corrections:

5. **Deliverable wording fix** (line 128)
   - Was: "handles answer by calling resume() before start()"
   - Fixed: "branches: resume(answer) OR start()"

6. **CLI test mock path** (tui/__init__.py:20)
   - `check_textual_available` lives in `orchestrator_auto.tui`, not `orchestrator_auto.cli`
   - Fixed: `monkeypatch.setattr("orchestrator_auto.tui.check_textual_available", ...)`

7. **No pytest-mock in repo** (pyproject.toml)
   - `mocker` fixture not available (pytest-mock not in dev deps)
   - Fixed: use `unittest.mock.patch` decorator (matches existing test_cli.py pattern)

8. **db.create_session signature** (db.py:277-286)
   - `db_path` is keyword-only, not positional
   - Fixed: `db.create_session("Test feature", db_path=db_path)` (matches test_cli.py:295 pattern)
