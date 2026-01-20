# Add --tui Flag to `orchestrator start` - Implementation Plan

## Overview

Add a `--tui` flag to the `orchestrator start` command to enable running new workflows in the Textual-based Text User Interface. This provides a rich visual experience with real-time streaming output, milestone tracking, and status panels.

**Scope**: CLI integration with proper model resolution and clear flag compatibility rules.

**Key Constraints Identified**:
1. Model aliases must be resolved before passing to TUI (TUI doesn't resolve aliases)
2. `--auto-commit` and `--smart-commit` not currently supported by `OrchestratorTUI` - must error
3. `--no-rename` has no effect in TUI mode (plan renaming is CLI-layer logic)

---

## Milestone 1: Add `--tui` Flag with Model Resolution

### Tasks
- [ ] Add `@click.option('--tui', is_flag=True, help='Run in TUI (Text User Interface) mode')` to `start` command
- [ ] Add `tui: bool` parameter to `start()` function signature
- [ ] Create `_start_session_tui()` helper function with **model resolution**
- [ ] Call `_start_session_tui()` early in `start()` when `--tui` flag is set

### Deliverables
- [ ] `orchestrator_auto/cli.py` updated with `--tui` flag on `start` command
- [ ] `_start_session_tui()` resolves model aliases via `get_planner_model()` / `get_executor_model()`
- [ ] TUI launches correctly for `orchestrator start -f "Test" --tui -pm sonnet -em haiku`

### Implementation Details

**Location**: `orchestrator_auto/cli.py`

**New helper function** (add after `_start_respond_tui()` around line 377):

```python
def _start_session_tui(
    feature: str,
    db_path: Optional[str],
    plan_path: Optional[str],
    planner_model: Optional[str],
    executor_model: Optional[str],
    telegram: Optional[bool],
    mcp_config: Optional[str],
    headless: bool,
) -> None:
    """
    Start a new workflow session with TUI dashboard.

    Launches the Textual-based OrchestratorTUI app for rich visual feedback
    when starting a new workflow.

    Args:
        feature: Feature description for the workflow
        db_path: Optional database path
        plan_path: Optional path to existing plan file
        planner_model: Model for planner agent (alias or full ID)
        executor_model: Model for executor agent (alias or full ID)
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

    # CRITICAL: Resolve model aliases to full IDs
    # OrchestratorTUI -> Orchestrator -> agents.py passes model directly to SDK
    # SDK does not understand aliases like "sonnet" or "haiku"
    resolved_planner = get_planner_model(planner_model)
    resolved_executor = get_executor_model(executor_model)

    # Setup Telegram notifier if configured (tri-state: not explicitly disabled)
    telegram_notifier = None
    if telegram is not False:
        telegram_notifier = _create_telegram_notifier(telegram)

    # Get the OrchestratorTUI class and instantiate
    OrchestratorTUI = get_app_class()
    app = OrchestratorTUI(
        feature=feature,
        db_path=db_path,
        plan_path=plan_path,
        planner_model=resolved_planner,   # Pass resolved full model ID
        executor_model=resolved_executor,  # Pass resolved full model ID
        mcp_config_path=mcp_config,
        headless=headless,
        telegram_notifier=telegram_notifier,
    )

    # Run the TUI
    app.run()
```

**Modify `start` command** (around line 1170):

1. Add option after `--debug`:
```python
@click.option('--tui', is_flag=True, help='Run in TUI (Text User Interface) mode')
```

2. Add `tui: bool` to function signature

3. Add TUI branch early in function (around line 1210, before queue handling):
```python
# Handle TUI mode FIRST (before any click.echo() calls)
if tui:
    # Validate incompatible flag combinations
    if queue or queue_plans:
        click.secho("Error: --tui is not supported with queue mode", fg="red")
        click.echo("Queue mode has its own TUI. Use: orchestrator start --queue ... (without --tui)")
        sys.exit(1)

    if auto_commit:
        click.secho("Error: --auto-commit is not yet supported with --tui", fg="red")
        click.echo("The TUI does not currently perform auto-commit on completion.")
        click.echo("Run without --tui to use auto-commit, or commit manually after TUI exits.")
        sys.exit(1)

    if smart_commit is True:  # Explicitly enabled
        click.secho("Error: --smart-commit is not yet supported with --tui", fg="red")
        sys.exit(1)

    _start_session_tui(
        feature=feature,
        db_path=db_path,
        plan_path=plan,
        planner_model=planner_model,
        executor_model=executor_model,
        telegram=telegram,
        mcp_config=mcp_config,
        headless=headless,
    )
    return
```

---

## Milestone 2: Add Unit Tests

### Tasks
- [ ] Add test for `--tui` flag registration on `start` command
- [ ] Add test for `_start_session_tui()` with mocked TUI
- [ ] Add test for `--tui` + `--queue` incompatibility error
- [ ] Add test for `--tui` + `--auto-commit` incompatibility error
- [ ] Add test that model aliases are resolved before TUI launch

### Deliverables
- [ ] `tests/test_cli.py` updated with TUI flag tests
- [ ] All existing tests still pass
- [ ] New tests pass with `pytest tests/test_cli.py -k "tui" -v`

### Test Cases

```python
class TestStartTUIFlag:
    """Tests for --tui flag on start command."""

    def test_tui_flag_exists(self, cli_runner):
        """Test that --tui flag is recognized."""
        result = cli_runner.invoke(cli, ['start', '--help'])
        assert '--tui' in result.output
        assert 'TUI' in result.output or 'Text User Interface' in result.output

    def test_tui_with_queue_error(self, cli_runner, temp_db):
        """Test that --tui with --queue shows error."""
        result = cli_runner.invoke(cli, [
            'start', '-f', 'Test', '--tui', '--queue',
            '-d', temp_db
        ])
        assert result.exit_code != 0
        assert 'not supported with queue mode' in result.output

    def test_tui_with_auto_commit_error(self, cli_runner, temp_db):
        """Test that --tui with --auto-commit shows error."""
        result = cli_runner.invoke(cli, [
            'start', '-f', 'Test', '--tui', '--auto-commit',
            '-d', temp_db
        ])
        assert result.exit_code != 0
        assert 'not yet supported with --tui' in result.output

    def test_tui_with_smart_commit_error(self, cli_runner, temp_db):
        """Test that --tui with --smart-commit shows error."""
        result = cli_runner.invoke(cli, [
            'start', '-f', 'Test', '--tui', '--smart-commit',
            '-d', temp_db
        ])
        assert result.exit_code != 0
        assert 'not yet supported with --tui' in result.output

    @patch('orchestrator_auto.cli._start_session_tui')
    def test_tui_calls_helper(self, mock_tui, cli_runner, temp_db):
        """Test that --tui flag calls _start_session_tui."""
        cli_runner.invoke(cli, [
            'start', '-f', 'Test feature', '--tui',
            '-d', temp_db
        ])
        mock_tui.assert_called_once()
        call_kwargs = mock_tui.call_args[1]
        assert call_kwargs['feature'] == 'Test feature'

    @patch('orchestrator_auto.cli.get_app_class')
    @patch('orchestrator_auto.cli.check_textual_available')
    def test_model_aliases_resolved(self, mock_check, mock_get_app, temp_db):
        """Test that model aliases are resolved to full IDs before TUI launch."""
        mock_app = Mock()
        mock_get_app.return_value = Mock(return_value=mock_app)

        from orchestrator_auto.cli import _start_session_tui

        _start_session_tui(
            feature='Test feature',
            db_path=temp_db,
            plan_path=None,
            planner_model='sonnet',  # Alias
            executor_model='haiku',   # Alias
            telegram=None,
            mcp_config=None,
            headless=False,
        )

        # Verify full model IDs were passed, not aliases
        call_kwargs = mock_get_app.return_value.call_args[1]
        assert 'sonnet' not in call_kwargs.get('planner_model', '')
        assert 'haiku' not in call_kwargs.get('executor_model', '')
        # Should contain full model IDs
        assert 'claude-' in call_kwargs.get('planner_model', '')
        assert 'claude-' in call_kwargs.get('executor_model', '')
```

---

## Milestone 3: Update Documentation

### Tasks
- [ ] Update `orchestrator start --help` output verification
- [ ] Update `docs/CLI_REFERENCE.md` with `--tui` flag and compatibility notes
- [ ] Update `orchestrator-auto/README.md` with TUI example
- [ ] Document flag incompatibilities clearly

### Deliverables
- [ ] `docs/CLI_REFERENCE.md` includes `--tui` for start command with notes
- [ ] `orchestrator-auto/README.md` mentions TUI mode
- [ ] Help text is clear and consistent with other commands

### Documentation Updates

**CLI_REFERENCE.md** - Add to start command options:
```markdown
| `--tui` | Run in TUI (Text User Interface) mode |

**Note**: `--tui` is not compatible with:
- `--queue` (queue mode has its own TUI)
- `--auto-commit` / `--smart-commit` (not yet implemented in TUI)
- `--no-rename` (has no effect in TUI mode)
```

**README.md** - Add example:
```bash
# Start with TUI dashboard
orchestrator start -f "Add user authentication" --tui

# With custom models
orchestrator start -f "Add feature" --tui -pm sonnet -em haiku
```

---

## Milestone 4: Manual Testing & Edge Cases

### Tasks
- [ ] Test `orchestrator start -f "Feature" --tui` launches TUI correctly
- [ ] Test `orchestrator start --plan plan.md --tui` works with existing plan
- [ ] Test `orchestrator start -f "Feature" --tui -pm sonnet -em haiku` resolves models correctly
- [ ] Test `orchestrator start -f "Feature" --tui --telegram` works
- [ ] Test TUI handles Ctrl+C gracefully
- [ ] Test TUI displays milestone progress correctly
- [ ] Verify error messages for incompatible flags are clear

### Deliverables
- [ ] All manual test scenarios pass
- [ ] No regressions in non-TUI mode
- [ ] TUI properly cleans up on exit

### Test Scenarios

| Scenario | Command | Expected |
|----------|---------|----------|
| Basic TUI start | `orchestrator start -f "Test" --tui` | TUI launches, shows discovery phase |
| With plan | `orchestrator start --plan plan.md --tui` | TUI launches in execution phase |
| Model aliases | `orchestrator start -f "Test" --tui -pm sonnet -em haiku` | Models resolved, shown in status panel |
| With Telegram | `orchestrator start -f "Test" --tui --telegram` | Notifications sent + TUI |
| Queue conflict | `orchestrator start --queue plan.md --tui` | Error: "not supported with queue mode" |
| Auto-commit conflict | `orchestrator start -f "Test" --tui --auto-commit` | Error: "not yet supported" |
| Smart-commit conflict | `orchestrator start -f "Test" --tui --smart-commit` | Error: "not yet supported" |
| Interrupt | Ctrl+C during workflow | Clean exit, session paused |

---

## Technical Notes

### Feedback Addressed

1. **Model resolution (CRITICAL)**: `_start_session_tui()` now calls `get_planner_model()` and `get_executor_model()` to resolve aliases like `sonnet`/`haiku` to full model IDs before passing to `OrchestratorTUI`. This prevents SDK errors.

2. **Auto-commit parity**: Rather than silently ignoring `--auto-commit` and `--smart-commit`, we explicitly error with a helpful message. This is the safest approach until `OrchestratorTUI` gains auto-commit support (a separate feature).

3. **Plan renaming**: `--no-rename` has no effect in TUI mode since plan renaming is CLI-layer logic. This is documented but not errored (low impact).

### Future Enhancement: TUI Auto-Commit Support

To add auto-commit to `OrchestratorTUI` (not in this scope):
1. Add `auto_commit`, `smart_commit` parameters to `OrchestratorTUI.__init__()`
2. Handle completion in `on_workflow_completed()` to trigger commit
3. Add `GitDiffScreen` for review before commit
4. Follow pattern from `WatchTUI` which already has auto-commit support

### Why Error Instead of Silent Ignore

- **User expectation**: If user passes `--auto-commit`, they expect it to work
- **Debugging**: Silent ignore leads to confusion ("why didn't it commit?")
- **Clear contract**: Error message tells user exactly what's supported
- **Safe default**: No unexpected behavior

---

## Summary

| Milestone | Effort | Files Changed |
|-----------|--------|---------------|
| M1: Add flag + helper with model resolution | ~1 hour | `cli.py` |
| M2: Unit tests | ~45 min | `tests/test_cli.py` |
| M3: Documentation | ~20 min | `CLI_REFERENCE.md`, `README.md` |
| M4: Manual testing | ~30 min | None (verification) |

**Total estimated effort**: ~2.5 hours

### Key Differences from Original Plan

1. **Added model resolution** in `_start_session_tui()` (lines with `get_planner_model()` / `get_executor_model()`)
2. **Added incompatibility checks** for `--auto-commit`, `--smart-commit`, `--queue`
3. **Added tests** for model resolution and incompatible flag combinations
4. **Documented limitations** clearly in CLI reference
