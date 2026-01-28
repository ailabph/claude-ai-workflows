"""
Command-line interface for orchestrator-auto.

Provides commands for starting, resuming, and monitoring workflow sessions.
"""

import click
import sys
import signal
from pathlib import Path
from typing import Optional
from datetime import datetime

from . import db
from . import git
from . import __version__
from .engine import Orchestrator
from .state import Phase, Status
from .controllers import QueueController, QueueEvent, WatchController, WatchEvent
from .exceptions import OrchestratorError
from .parser import extract_feature_from_plan, parse_plan_file
from .auth import detect_auth, format_auth_display
from .config import (
    get_planner_model,
    get_executor_model,
    get_model_display_name,
    get_telegram_config,
    is_telegram_configured,
    get_stuck_sessions_config,
    get_project_identity,
    get_smart_commit_enabled,
)


# Global reference to orchestrator for signal handling
_current_orchestrator: Optional[Orchestrator] = None


def handle_interrupt(signum, frame):
    """
    Handle Ctrl+C by raising KeyboardInterrupt instead of exiting.

    This allows try/except KeyboardInterrupt blocks in _run_queue() and other
    code to handle queue item status updates and cleanup properly.
    """
    click.echo("\n")
    click.secho("⚠️  Interrupted (Ctrl+C)", fg="yellow")

    # Raise KeyboardInterrupt to let normal exception handling run
    # Do NOT call _cleanup() here - let the finally blocks handle it
    # Do NOT call sys.exit() - let the exception propagate
    signal.default_int_handler(signum, frame)


def format_phase(phase: str) -> str:
    """Format phase name with color."""
    colors = {
        Phase.DISCOVERY: "cyan",
        Phase.PLANNING: "blue",
        Phase.EXECUTION: "magenta",
        Phase.COMPLETED: "green",
        Phase.PAUSED: "yellow",
    }
    color = colors.get(phase, "white")
    return click.style(phase.upper(), fg=color, bold=True)


def format_status(status: str) -> str:
    """Format status with color."""
    colors = {
        Status.ACTIVE: "green",
        Status.PAUSED: "yellow",
        Status.COMPLETED: "blue",
        Status.FAILED: "red",
    }
    color = colors.get(status, "white")
    return click.style(status.upper(), fg=color, bold=True)


def _handle_queue_event(event: QueueEvent, data: dict) -> None:
    """Handle QueueController events with CLI output."""
    if event == QueueEvent.STARTED:
        click.echo()
        click.secho("Starting queue runner...", fg="cyan", bold=True)

    elif event == QueueEvent.ITEM_STARTED:
        position = data.get("position", 0)
        plan_path = data.get("plan_path", "")
        feature = data.get("feature_description", "")

        click.echo()
        click.secho("=" * 60, fg="cyan")
        click.secho(f"Queue Item {position}: {Path(plan_path).name}", fg="cyan", bold=True)
        click.secho(f"Feature: {feature}", fg="cyan")
        click.secho("=" * 60, fg="cyan")
        click.echo()

    elif event == QueueEvent.ITEM_COMPLETED:
        position = data.get("position", 0)
        click.secho(f"✓ Queue item {position} completed", fg="green", bold=True)

    elif event == QueueEvent.ITEM_FAILED:
        position = data.get("position", 0)
        error = data.get("error", "")
        click.secho(f"✗ Queue item {position} failed", fg="red", bold=True)
        if error:
            click.secho(f"  Error: {error}", fg="red")
        click.secho("  Continuing to next item (fail-forward)...", fg="yellow")

    elif event == QueueEvent.ITEM_PAUSED:
        position = data.get("position", 0)
        session_id = data.get("session_id", "")
        click.secho(f"⏸ Queue item {position} paused (blocker)", fg="yellow", bold=True)
        click.secho("Queue halted. Use 'orchestrator resume <session-id>' to continue.", fg="yellow")
        if session_id:
            click.echo(f"  Session: {session_id}")

    elif event == QueueEvent.COMPLETED:
        completed = data.get("completed", 0)
        failed = data.get("failed", 0)
        paused = data.get("paused", 0)

        click.echo()
        click.secho("=" * 60, fg="cyan")
        click.secho("Queue Complete", fg="cyan", bold=True)
        click.secho("=" * 60, fg="cyan")
        click.echo()
        click.echo(f"Completed: {click.style(str(completed), fg='green', bold=True)}")
        click.echo(f"Failed:    {click.style(str(failed), fg='red', bold=True)}")
        click.echo(f"Paused:    {click.style(str(paused), fg='yellow', bold=True)}")

    elif event == QueueEvent.HALTED:
        reason = data.get("reason", "")
        item = data.get("item", {})
        session_id = item.get("session_id", "") if item else ""

        if reason == "halt_paused":
            click.echo()
            click.secho(f"⏸ Queue halted: item {item.get('position', 0) + 1} is paused", fg="yellow", bold=True)
            if session_id:
                click.echo(f"  Resume with: orchestrator resume {session_id}")
        elif reason == "halt_active":
            click.echo()
            click.secho("⚠ Another queue runner appears to be active", fg="yellow", bold=True)
            if session_id:
                click.echo(f"  Session {session_id} has recent heartbeat")
            click.echo("  Exiting to avoid double-running.")
        elif reason == "halt_orphaned":
            position = item.get("position", 0) + 1 if item else 0
            click.echo()
            click.secho(f"⚠ Queue item {position} has orphaned session", fg="yellow", bold=True)
            if session_id:
                click.echo(f"  Session {session_id} has stale heartbeat")
                click.echo()
                click.echo("  To recover, run:")
                click.secho(f"    orchestrator reset {session_id}", fg="cyan")
                click.secho(f"    orchestrator resume {session_id} --force", fg="cyan")

    elif event == QueueEvent.RECONCILED:
        message = data.get("message", "")
        click.secho(f"✓ Reconciling: {message}", fg="green")

    elif event == QueueEvent.INFO:
        message = data.get("message", "")
        click.echo(message)

    elif event == QueueEvent.WARNING:
        message = data.get("message", "")
        click.secho(f"⚠ {message}", fg="yellow")


def _handle_watch_event(event: WatchEvent, data: dict, auto_commit: bool = False) -> None:
    """Handle WatchController events with CLI output."""
    if event == WatchEvent.STARTED:
        directory = data.get("directory", "")
        poll_interval = data.get("poll_interval", 2)
        auto_convert = data.get("auto_convert", True)

        click.echo()
        click.secho("👁️  Watch Mode", fg="cyan", bold=True)
        click.echo()
        click.echo(f"  Directory: {directory}")
        click.echo(f"  Poll interval: {poll_interval}s")
        click.echo(f"  Auto-convert: {'enabled' if auto_convert else 'disabled'}")
        if auto_commit:
            click.echo("  Auto-commit: enabled")
        click.echo()
        click.secho("Press Ctrl+C to stop", fg="yellow")
        click.echo()

    elif event == WatchEvent.FILE_FOUND:
        plan_path = data.get("plan_path", "")
        click.echo(f"📄 Found: {plan_path}")

    elif event == WatchEvent.FILE_COMPLETED:
        new_path = data.get("new_path", "")
        click.secho(f"✓ Completed: {new_path}", fg="green")

    elif event == WatchEvent.FILE_FAILED:
        new_path = data.get("new_path", "")
        error = data.get("error", "")
        click.secho(f"✗ Failed: {new_path}", fg="red")
        if error:
            click.echo(f"  Error: {error}")

    elif event == WatchEvent.FILE_PAUSED:
        session_id = data.get("session_id", "")
        click.echo()
        click.secho("⏸️  Session paused (blocker)", fg="yellow", bold=True)
        click.echo(f"  Resume with: orchestrator resume {session_id} --answer \"your response\"")
        click.echo()

    elif event == WatchEvent.FILE_SKIPPED:
        plan_path = data.get("plan_path", "")
        reason = data.get("reason", "")
        click.secho(f"⚠ Skipped: {plan_path}", fg="yellow")
        if reason:
            click.echo(f"  Reason: {reason}")

    elif event == WatchEvent.FILE_CONVERTED:
        original = data.get("original", "")
        converted = data.get("converted", "")
        click.secho(f"  ✓ Converted: {converted}", fg="green")

    elif event == WatchEvent.CONVERSION_FAILED:
        plan_path = data.get("plan_path", "")
        click.secho(f"⚠ Conversion failed (quarantined): {plan_path}", fg="yellow")

    elif event == WatchEvent.RESUMED_COMPLETED:
        new_path = data.get("new_path", "")
        click.secho(f"✓ Resumed session completed: {new_path}", fg="green")

    elif event == WatchEvent.RESUMED_FAILED:
        new_path = data.get("new_path", "")
        click.secho(f"✗ Resumed session failed: {new_path}", fg="red")

    elif event == WatchEvent.STOPPED:
        completed = data.get("completed", 0)
        failed = data.get("failed", 0)
        paused = data.get("paused", 0)
        click.echo()
        click.secho("✓ Watch mode stopped", fg="green")

    elif event == WatchEvent.INFO:
        message = data.get("message", "")
        click.echo(f"  {message}")

    elif event == WatchEvent.WARNING:
        message = data.get("message", "")
        click.secho(f"⚠ {message}", fg="yellow")


def _start_watch_tui(
    plans_dir: str,
    verbose: bool,
    poll_interval: int,
    auto_convert: bool,
    db_path: Optional[str],
    planner_model: Optional[str],
    executor_model: Optional[str],
    auto_commit: bool,
    smart_commit: Optional[bool],
    telegram: Optional[bool],
    show_activity: bool,
    mcp_config: Optional[str],
    headless: bool,
) -> None:
    """
    Start watch mode with TUI dashboard.

    Launches the Textual-based WatchTUI app for rich visual feedback.
    Uses the same WatchController as CLI mode for strict parity.

    Args:
        plans_dir: Directory to watch for plan files
        verbose: Use expanded layout with dual agent panels (default: compact)
        poll_interval: Seconds between directory polls
        auto_convert: Whether to auto-convert invalid plans
        db_path: Optional database path
        planner_model: Model for planner agent
        executor_model: Model for executor agent
        auto_commit: Whether to auto-commit on completion
        smart_commit: Whether to use AI-generated commit messages
        telegram: Whether to enable Telegram notifications
        show_activity: Whether to show streaming activity (ignored in TUI)
        mcp_config: Path to MCP configuration file
        headless: Whether to run Playwright browser headless
    """
    try:
        from .tui import get_watch_app_class, check_textual_available
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

    # Initialize database before TUI starts
    db.init_db(db_path)

    # Get the WatchTUI class and instantiate with all options
    WatchTUI = get_watch_app_class()
    app = WatchTUI(
        plans_dir=plans_dir,
        verbose=verbose,
        db_path=db_path,
        poll_interval=poll_interval,
        auto_convert=auto_convert,
        planner_model=planner_model,
        executor_model=executor_model,
        auto_commit=auto_commit,
        smart_commit=smart_commit,
        telegram=telegram,
        mcp_config=mcp_config,
        headless=headless,
    )

    # Run the TUI app (blocking)
    app.run()


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
        planner_model=resolved_planner,
        executor_model=resolved_executor,
        mcp_config_path=mcp_config,
        headless=headless,
        telegram_notifier=telegram_notifier,
    )

    # Run the TUI
    app.run()


def _handle_orchestrator_error(
    e: OrchestratorError,
    debug: bool = False,
    db_path: Optional[str] = None
) -> None:
    """
    Handle OrchestratorError with user-friendly output.

    Displays error message, log file path, and conditional retry guidance
    based on whether a plan_path exists for the session.
    """
    import traceback as tb

    click.echo()
    click.secho(f"Error: {e}", fg="red", bold=True)
    click.echo()

    if e.session_id:
        click.echo(f"Session: {e.session_id} (status: failed)")

    if e.log_path:
        click.echo(f"Log file: {e.log_path}")

    click.echo()

    # Conditional retry guidance based on plan_path
    if e.session_id:
        try:
            session = db.get_session(e.session_id, db_path)
            if session and session.get("plan_path"):
                click.echo("To retry with the same plan:")
                click.secho(f"  orchestrator start --plan {session['plan_path']}", fg="cyan")
            elif session and session.get("feature_description"):
                click.echo("To retry with the same feature:")
                # Escape quotes in feature description
                feature = session["feature_description"].replace('"', '\\"')
                click.secho(f'  orchestrator start -f "{feature}"', fg="cyan")
            else:
                click.echo("To start a new session:")
                click.secho('  orchestrator start -f "your feature"', fg="cyan")
        except Exception:
            # If we can't get session info, just show generic guidance
            click.echo("To start a new session:")
            click.secho('  orchestrator start -f "your feature"', fg="cyan")

    click.echo()
    click.echo("Use --debug flag for full stack trace.")

    if debug and e.__cause__:
        click.echo()
        click.secho("Stack trace:", fg="yellow")
        tb.print_exception(type(e.__cause__), e.__cause__, e.__cause__.__traceback__)


def _handle_unexpected_error(e: Exception, debug: bool = False) -> None:
    """
    Handle unexpected errors with user-friendly output.

    For errors that are not OrchestratorError (i.e., not handled at engine level).
    """
    import traceback as tb

    click.echo()
    click.secho(f"Unexpected error: {e}", fg="red", bold=True)
    click.echo()
    click.echo("This may be a bug. Please report at:")
    click.secho("  https://github.com/anthropics/claude-code/issues", fg="cyan")
    click.echo()
    click.echo("Use --debug flag for full stack trace.")

    if debug:
        click.echo()
        click.secho("Stack trace:", fg="yellow")
        tb.print_exception(type(e), e, e.__traceback__)


def display_auth_info() -> None:
    """Detect and display auth info with appropriate coloring."""
    auth_info = detect_auth()
    auth_display = format_auth_display(auth_info)

    # Use yellow for warnings (⚠ or Unknown)
    if "⚠" in auth_display or "Unknown" in auth_display:
        for line in auth_display.split("\n"):
            click.secho(line, fg="yellow")
    else:
        click.echo(auth_display)


def show_progress(orchestrator: Orchestrator) -> None:
    """Display current workflow progress."""
    status = orchestrator.get_status()

    click.echo()
    click.echo("=" * 60)
    click.echo(f"Session: {click.style(status['session_id'], fg='cyan', bold=True)}")
    click.echo(f"Phase: {format_phase(status['phase'])}")
    click.echo(f"Status: {format_status(status['status'])}")

    # Show models if set
    if status.get('planner_model') or status.get('executor_model'):
        planner_display = get_model_display_name(status['planner_model']) if status.get('planner_model') else "default"
        executor_display = get_model_display_name(status['executor_model']) if status.get('executor_model') else "default"
        click.echo(f"Models: P={click.style(planner_display, fg='blue')} | E={click.style(executor_display, fg='magenta')}")

    if status['phase'] == Phase.EXECUTION or status['current_milestone'] > 0:
        milestone_text = f"[{status['current_milestone']}/{status['total_milestones']}]"
        click.echo(f"Milestone: {click.style(milestone_text, fg='magenta', bold=True)}")

    click.echo("=" * 60)
    click.echo()


def output_callback(message: str) -> None:
    """Callback for orchestrator output."""
    click.echo(message)


def _do_smart_auto_commit(
    feature_description: str,
    milestones: list,
    path: Optional[str] = None,
    smart_commit_flag: Optional[bool] = None,
    executor_model: Optional[str] = None,
    auto_commit_model_flag: Optional[str] = None,
) -> tuple:
    """
    Perform auto-commit with smart commit support and CLI feedback.

    Args:
        feature_description: Feature being implemented
        milestones: List of milestone dicts
        path: Git repo path
        smart_commit_flag: CLI flag for smart commit (None = use config)
        executor_model: Resolved executor model for this session (fallback for commit model)
        auto_commit_model_flag: CLI flag for commit model (--auto-commit-model)

    Returns:
        (success, message) tuple
    """
    from .config import get_auto_commit_model

    # Determine if smart commit should be used
    use_smart = get_smart_commit_enabled(smart_commit_flag)

    # Determine which model to use for smart commit
    commit_model = get_auto_commit_model(auto_commit_model_flag, executor_model)

    # Status callback for CLI feedback
    def on_status(msg: str) -> None:
        if "Analyzing" in msg:
            click.secho(f"  {msg}", fg="cyan")
        elif "Secrets detected" in msg:
            click.secho(f"  ⚠ {msg}", fg="yellow")
        elif "Generating commit" in msg:
            click.secho(f"  {msg}", fg="cyan")
        elif "failed" in msg.lower() or "error" in msg.lower():
            click.secho(f"  ⚠ {msg}", fg="yellow")
        else:
            click.echo(f"  {msg}")

    # Call auto_commit with smart commit support
    success, msg, fallback_reason = git.auto_commit(
        feature_description=feature_description,
        milestones=milestones,
        path=path,
        use_smart_commit=use_smart,
        smart_commit_model=commit_model,
        on_status=on_status,
    )

    # Show fallback reason if applicable
    if success and fallback_reason:
        if fallback_reason == "secrets_detected":
            click.secho("  (Used static message due to potential secrets in diff)", fg="yellow")
        elif fallback_reason == "ai_generation_failed":
            click.secho("  (Used static message - AI generation unavailable)", fg="yellow")
        elif fallback_reason == "smart_commit_disabled":
            pass  # Don't mention if explicitly disabled
    elif success and not fallback_reason and use_smart:
        click.secho("  (AI-generated commit message)", fg="green")

    return success, msg


def _rename_plan_done(plan_path: str) -> tuple:
    """
    Rename completed plan file to *_done.md suffix.

    Args:
        plan_path: Path to the plan file

    Returns:
        Tuple of (success, message)
    """
    path = Path(plan_path)
    if not path.exists():
        return False, f"Plan file not found: {plan_path}"

    # Already has _done suffix
    if path.stem.endswith("_done"):
        return True, f"Already renamed: {plan_path}"

    # Build new name: my-feature.md -> my-feature_done.md
    new_name = f"{path.stem}_done{path.suffix}"
    new_path = path.parent / new_name

    # Don't overwrite existing
    if new_path.exists():
        return False, f"Target already exists: {new_path}"

    path.rename(new_path)
    return True, str(new_path)


def _create_telegram_notifier(cli_enabled: Optional[bool] = None):
    """
    Create Telegram notifier from config if available.

    Args:
        cli_enabled: Explicit enable/disable from CLI flag

    Returns:
        TelegramNotifier instance or None
    """
    try:
        from .telegram import create_notifier_from_config
        telegram_config = get_telegram_config()
        return create_notifier_from_config(telegram_config, cli_enabled)
    except ImportError:
        if cli_enabled:
            click.secho("⚠ Telegram requires httpx. Install with: pip install httpx", fg="yellow")
        return None
    except Exception as e:
        click.secho(f"⚠ Telegram setup error: {e}", fg="yellow")
        return None


def _check_stuck_sessions(telegram_notifier, db_path: Optional[str] = None) -> None:
    """
    Check for stuck sessions and notify via Telegram.

    Uses config for enabled/inactive_minutes settings.

    Args:
        telegram_notifier: TelegramNotifier instance (or None)
        db_path: Optional database path
    """
    if not telegram_notifier:
        return

    # Get stuck sessions config
    stuck_config = get_stuck_sessions_config()
    if not stuck_config.get("enabled", True):
        return

    inactive_minutes = stuck_config.get("inactive_minutes", 20)

    try:
        stuck_sessions = db.get_stuck_sessions(db_path, inactive_minutes)

        for session in stuck_sessions:
            # Use heartbeat_at if available, fall back to updated_at
            from datetime import datetime
            last_activity_str = session.get('heartbeat_at') or session.get('updated_at')

            if last_activity_str:
                try:
                    if 'T' in last_activity_str:
                        last_activity = datetime.fromisoformat(last_activity_str)
                    else:
                        last_activity = datetime.strptime(last_activity_str, "%Y-%m-%d %H:%M:%S")
                    last_updated_str = last_activity.strftime('%Y-%m-%d %H:%M')
                except (ValueError, TypeError):
                    last_updated_str = last_activity_str
            else:
                last_updated_str = "unknown"

            telegram_notifier.notify_stuck_session(
                session_id=session['id'][:8],
                feature=session['feature_description'],
                phase=session['phase'].upper(),
                last_updated=last_updated_str,
                inactive_minutes=inactive_minutes,
            )
            click.secho(f"⚠ Stuck session detected: {session['id'][:8]} ({session['feature_description']})", fg="yellow")

    except Exception as e:
        # Don't let stuck session check crash the workflow
        click.secho(f"⚠ Stuck session check failed: {e}", fg="yellow")


def _handle_queue_mode(
    queue_plans: tuple,
    queue_reset: bool,
    db_path: Optional[str],
    show_activity: bool,
    planner_model: Optional[str],
    executor_model: Optional[str],
    auto_commit: bool,
    telegram: Optional[bool],
    smart_commit: Optional[bool] = None,
    auto_commit_model: Optional[str] = None,
    no_rename: bool = False,
    mcp_config_path: Optional[str] = None,
    headless: bool = False,
) -> None:
    """
    Handle --queue mode: validate, create/resume queue, run queue.
    """
    from .config import get_project_identity

    # Get project identity
    project_id, project_remote = get_project_identity()

    # Load existing queue items
    existing_queue = db.list_queue_items(project_id, db_path, include_completed=False)

    # Case 1: Resume existing queue (no plans provided)
    if not queue_plans:
        if not existing_queue:
            raise click.UsageError(
                "No active queue found for this project. "
                "Provide plan paths to create a queue: orchestrator start --queue plan1.md plan2.md"
            )
        click.secho(f"Resuming existing queue ({len(existing_queue)} plans)...", fg="cyan", bold=True)
        _display_queue_status(existing_queue)

        # Run the queue
        _run_queue(
            project_id=project_id,
            db_path=db_path,
            show_activity=show_activity,
            planner_model=planner_model,
            executor_model=executor_model,
            auto_commit=auto_commit,
            telegram=telegram,
            smart_commit=smart_commit,
            auto_commit_model=auto_commit_model,
            no_rename=no_rename,
            mcp_config_path=mcp_config_path,
            headless=headless,
        )
        return

    # Case 2: Plans provided - validate and create/check queue
    queue_plans_list = list(queue_plans)

    # Normalize plan paths (absolute paths for comparison)
    normalized_provided = [str(Path(p).resolve()) for p in queue_plans_list]

    # Validate all plans upfront
    click.echo("Validating plan files...")
    validation_errors = []
    for plan_path in queue_plans_list:
        result = parse_plan_file(plan_path)
        if not result["valid"]:
            validation_errors.append(f"  ✗ {plan_path}: {result['error']}")
        else:
            click.echo(f"  ✓ {plan_path} ({result['milestones']} milestones)")

    if validation_errors:
        click.echo()
        click.secho("Validation failed:", fg="red", bold=True)
        for error in validation_errors:
            click.echo(error)
        sys.exit(1)

    # Check if active queue exists
    if existing_queue:
        # Extract normalized paths from existing queue
        normalized_existing = [str(Path(item["plan_path"]).resolve()) for item in existing_queue]

        # Check if they match
        if normalized_provided == normalized_existing:
            click.secho("Queue already exists with same plans (resuming)...", fg="cyan", bold=True)
            _display_queue_status(existing_queue)

            # Run the queue
            _run_queue(
                project_id=project_id,
                db_path=db_path,
                show_activity=show_activity,
                planner_model=planner_model,
                executor_model=executor_model,
                auto_commit=auto_commit,
                telegram=telegram,
                smart_commit=smart_commit,
                auto_commit_model=auto_commit_model,
                no_rename=no_rename,
                mcp_config_path=mcp_config_path,
                headless=headless,
            )
            return
        else:
            # Mismatch - require --queue-reset
            if not queue_reset:
                click.secho("Error: Active queue exists with different plans", fg="red", bold=True)
                click.echo()
                click.echo("Existing queue:")
                for i, item in enumerate(existing_queue, 1):
                    click.echo(f"  {i}. {item['plan_path']}")
                click.echo()
                click.echo("Provided plans:")
                for i, plan in enumerate(queue_plans_list, 1):
                    click.echo(f"  {i}. {plan}")
                click.echo()
                click.secho("Use --queue-reset to replace the existing queue", fg="yellow")
                sys.exit(1)

            # Clear and recreate
            click.secho("Clearing existing queue...", fg="yellow")
            count = db.clear_active_queue(project_id, db_path)
            click.echo(f"  Removed {count} items")

    # Create new queue
    click.echo()
    click.secho("Creating queue...", fg="cyan", bold=True)

    created_items = []
    for position, plan_path in enumerate(queue_plans_list):
        # Extract feature description from plan
        feature_desc = extract_feature_from_plan(plan_path)

        # Create queue item
        item_id = db.create_queue_item(
            project_id=project_id,
            plan_path=str(Path(plan_path).resolve()),
            feature_description=feature_desc,
            position=position,
            db_path=db_path,
        )

        created_items.append({
            "id": item_id,
            "position": position,
            "plan_path": str(Path(plan_path).resolve()),
            "feature_description": feature_desc,
            "status": "pending",
        })

        click.echo(f"  {position + 1}. {Path(plan_path).name} - \"{feature_desc}\"")

    click.echo()
    click.secho(f"✓ Queue created with {len(created_items)} plans", fg="green", bold=True)

    # Display queue status
    click.echo()
    _display_queue_status(created_items)

    # Run the queue
    click.echo()
    _run_queue(
        project_id=project_id,
        db_path=db_path,
        show_activity=show_activity,
        planner_model=planner_model,
        executor_model=executor_model,
        auto_commit=auto_commit,
        telegram=telegram,
        smart_commit=smart_commit,
        auto_commit_model=auto_commit_model,
        no_rename=no_rename,
        mcp_config_path=mcp_config_path,
        headless=headless,
    )


def _is_heartbeat_recent(session: dict, inactive_minutes: int = 20) -> bool:
    """
    Check if a session's heartbeat is recent (within inactive_minutes).

    Args:
        session: Session dict with heartbeat_at and updated_at fields
        inactive_minutes: Threshold for considering a session active

    Returns:
        True if heartbeat is recent, False if stale or missing
    """
    from datetime import timedelta

    last_activity_str = session.get('heartbeat_at') or session.get('updated_at')
    if not last_activity_str:
        return False

    try:
        if 'T' in last_activity_str:
            last_activity = datetime.fromisoformat(last_activity_str)
        else:
            last_activity = datetime.strptime(last_activity_str, "%Y-%m-%d %H:%M:%S")

        threshold = datetime.now() - timedelta(minutes=inactive_minutes)
        return last_activity >= threshold
    except (ValueError, TypeError):
        return False


def _reconcile_queue_head(
    project_id: str,
    db_path: Optional[str],
    auto_commit: bool,
    telegram_notifier,
    smart_commit: Optional[bool] = None,
    auto_commit_model: Optional[str] = None,
) -> tuple:
    """
    Reconcile the head active queue item before processing.

    Ensures sequential ordering by checking if any earlier item is running/paused
    before allowing pending items to start.

    Returns:
        Tuple of (action, head_item) where action is one of:
        - "ready": Safe to run the head pending item
        - "empty": No active items, queue is done
        - "halt_paused": Queue halted on paused item (user must resume)
        - "halt_active": Another runner is active (recent heartbeat)
        - "halt_orphaned": Session orphaned (stale heartbeat, needs reset)
    """
    from . import git

    stuck_config = get_stuck_sessions_config()
    inactive_minutes = stuck_config.get("inactive_minutes", 20)

    while True:
        # Get all active items (pending, running, paused) ordered by position
        items = db.list_queue_items(project_id, db_path, include_completed=False)

        if not items:
            return ("empty", None)

        head = items[0]  # Lowest position among active items
        status = head["status"]
        session_id = head.get("session_id")

        if status == "pending":
            # Safe to run this item
            return ("ready", head)

        if status == "paused":
            # Queue halted - user must resume this session
            click.echo()
            click.secho(f"⏸ Queue halted: item {head['position'] + 1} is paused", fg="yellow", bold=True)
            if session_id:
                click.echo(f"  Resume with: orchestrator resume {session_id}")
            return ("halt_paused", head)

        if status == "running":
            # Reconcile running item against session state
            if not session_id:
                # No session_id means crash before session was created - mark failed
                click.secho(f"⚠ Queue item {head['position'] + 1} has no session - marking failed", fg="yellow")
                db.update_queue_item(
                    head["id"],
                    db_path,
                    status="failed",
                    error_message="Queue item marked running but no session_id (crash before session created)",
                    completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                continue  # Re-check with next item

            session = db.get_session(session_id, db_path)
            if not session:
                # Session missing from DB - mark failed
                click.secho(f"⚠ Queue item {head['position'] + 1} session not found - marking failed", fg="yellow")
                db.update_queue_item(
                    head["id"],
                    db_path,
                    status="failed",
                    error_message=f"Queue item session not found: {session_id}",
                    completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                continue

            # Check session state
            session_phase = session.get("phase")
            session_status = session.get("status")

            if session_phase == Phase.COMPLETED or session_status == Status.COMPLETED:
                # Session completed but queue item not updated - reconcile
                click.secho(f"✓ Reconciling: queue item {head['position'] + 1} session already completed", fg="green")
                db.update_queue_item(
                    head["id"],
                    db_path,
                    status="completed",
                    completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )

                # Attempt auto-commit if enabled (idempotent)
                if auto_commit:
                    click.echo("  Attempting auto-commit for reconciled session...")
                    milestones = db.get_milestones(session_id, db_path)
                    # Use executor_model from session DB for crash recovery
                    success, msg = _do_smart_auto_commit(
                        head["feature_description"],
                        milestones,
                        smart_commit_flag=smart_commit,
                        executor_model=session.get("executor_model"),
                        auto_commit_model_flag=auto_commit_model,
                    )
                    if success:
                        click.secho("  ✓ Changes committed", fg="green")
                        click.echo(f"    {msg.split(chr(10))[0]}")
                    else:
                        click.secho(f"  ⚠ Auto-commit skipped: {msg}", fg="yellow")

                # Telegram notification
                if telegram_notifier:
                    telegram_notifier.notify_queue_item_completed(
                        head["position"] + 1,
                        head["feature_description"]
                    )

                # Rename plan file on completion
                plan_path = head.get("plan_path")
                if plan_path and not no_rename:
                    success, result = _rename_plan_done(plan_path)
                    if success:
                        click.secho(f"  ✓ Plan renamed: {result}", fg="green")
                    else:
                        click.secho(f"  ⚠ Could not rename plan: {result}", fg="yellow")

                continue  # Check next item

            if session_phase == Phase.PAUSED or session_status == Status.PAUSED:
                # Session paused - update queue item and halt
                click.secho(f"⏸ Reconciling: queue item {head['position'] + 1} session is paused", fg="yellow")
                db.update_queue_item(head["id"], db_path, status="paused")
                return ("halt_paused", head)

            # Session is still active - check heartbeat
            if _is_heartbeat_recent(session, inactive_minutes):
                # Another runner is active
                click.echo()
                click.secho("⚠ Another queue runner appears to be active", fg="yellow", bold=True)
                click.echo(f"  Session {session_id} has recent heartbeat")
                click.echo("  Exiting to avoid double-running.")
                return ("halt_active", head)
            else:
                # Orphaned session - stale heartbeat
                click.echo()
                click.secho(f"⚠ Queue item {head['position'] + 1} has orphaned session", fg="yellow", bold=True)
                click.echo(f"  Session {session_id} has stale heartbeat (>{inactive_minutes} min)")
                click.echo()
                click.echo("  To recover, run:")
                click.secho(f"    orchestrator reset {session_id}", fg="cyan")
                click.secho(f"    orchestrator resume {session_id} --force", fg="cyan")
                return ("halt_orphaned", head)

        # Unknown status - should not happen, but mark failed to avoid infinite loop
        click.secho(f"⚠ Queue item {head['position'] + 1} has unknown status '{status}' - marking failed", fg="yellow")
        db.update_queue_item(
            head["id"],
            db_path,
            status="failed",
            error_message=f"Unknown queue item status: {status}",
            completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        # Continue to re-check


def _run_queue(
    project_id: str,
    db_path: Optional[str],
    show_activity: bool,
    planner_model: Optional[str],
    executor_model: Optional[str],
    auto_commit: bool,
    telegram: Optional[bool],
    smart_commit: Optional[bool] = None,
    auto_commit_model: Optional[str] = None,
    no_rename: bool = False,
    mcp_config_path: Optional[str] = None,
    headless: bool = False,
) -> None:
    """
    Run queued plans sequentially with crash recovery and fail-forward behavior.

    Uses QueueController for the core logic with CLI-specific event handling.
    """
    # Setup Telegram notifier if configured
    telegram_notifier = None
    if telegram is not False:
        telegram_notifier = _create_telegram_notifier(telegram)

    # Check for stuck sessions
    _check_stuck_sessions(telegram_notifier, db_path)

    # Resolve model names for auto-commit
    resolved_executor = get_executor_model(executor_model)

    # State for CLI-specific post-processing
    _last_completed_session_id: Optional[str] = None
    _last_completed_plan_path: Optional[str] = None
    _last_completed_feature: Optional[str] = None

    def cli_event_handler(event: QueueEvent, data: dict) -> None:
        """Handle queue events with CLI output and auto-commit/rename."""
        nonlocal _last_completed_session_id, _last_completed_plan_path, _last_completed_feature

        # Handle base CLI output
        _handle_queue_event(event, data)

        # Handle CLI-specific post-processing for completed items
        if event == QueueEvent.ITEM_COMPLETED:
            session_id = data.get("session_id")
            feature = data.get("feature_description", "")

            # Auto-commit if enabled
            if auto_commit and session_id:
                click.echo()
                click.secho("Creating auto-commit...", fg="cyan")
                milestones = db.get_milestones(session_id, db_path)
                success, msg = _do_smart_auto_commit(
                    feature,
                    milestones,
                    smart_commit_flag=smart_commit,
                    executor_model=resolved_executor,
                    auto_commit_model_flag=auto_commit_model,
                )
                if success:
                    click.secho("✓ Changes committed", fg="green")
                    click.echo(f"  {msg.split(chr(10))[0]}")
                else:
                    click.secho(f"⚠ Auto-commit skipped: {msg}", fg="yellow")

            # Get plan path from queue item for renaming
            if not no_rename:
                items = db.list_queue_items(project_id, db_path, include_completed=True)
                for item in items:
                    if item.get("session_id") == session_id:
                        plan_path = item.get("plan_path")
                        if plan_path:
                            success, result = _rename_plan_done(plan_path)
                            if success:
                                click.secho(f"✓ Plan renamed: {result}", fg="green")
                            else:
                                click.secho(f"⚠ Could not rename plan: {result}", fg="yellow")
                        break

    # Create and run the controller
    # Note: on_output is always passed; show_activity controls the streaming indicator
    controller = QueueController(
        project_id=project_id,
        db_path=db_path,
        on_event=cli_event_handler,
        on_output=output_callback,
        planner_model=planner_model,
        executor_model=executor_model,
        auto_commit=False,  # Handled via event handler
        smart_commit=smart_commit,
        telegram_notifier=telegram_notifier,
        show_activity=show_activity,
        mcp_config_path=mcp_config_path,
        headless=headless,
        no_rename=True,  # Handled via event handler
    )

    # Run the queue
    controller.run()


def _display_queue_status(queue_items: list) -> None:
    """Display formatted queue status."""
    click.echo(f"Queue: {len(queue_items)} plans")
    for item in queue_items:
        position = item["position"] + 1
        status = item["status"].upper()
        plan_name = Path(item["plan_path"]).name
        feature = item["feature_description"]

        # Color status
        status_colors = {
            "PENDING": "white",
            "RUNNING": "cyan",
            "PAUSED": "yellow",
            "COMPLETED": "green",
            "FAILED": "red",
        }
        status_colored = click.style(f"[{status}]", fg=status_colors.get(status, "white"))

        click.echo(f"  {position}. {status_colored} {plan_name} - \"{feature}\"")


@click.group()
@click.version_option(version=__version__, prog_name="orchestrator")
def cli():
    """Orchestrator Auto - Automated two-agent workflow."""
    pass


@cli.command()
@click.option('--feature', '-f', required=False, help='Feature description (auto-extracted from --plan if not provided)')
@click.option('--db-path', '-d', help='Custom database path')
@click.option('--plan', '-p', type=click.Path(exists=True), help='Path to existing plan file (skips discovery/planning)')
@click.option('--queue', is_flag=True, help='Queue mode: run multiple plans sequentially')
@click.option('--queue-reset', is_flag=True, help='Reset existing queue for this project')
@click.argument('queue_plans', nargs=-1, type=click.Path(exists=True))
@click.option('--show-activity/--no-activity', default=True, help='Show streaming activity indicator (default: enabled)')
@click.option('--planner-model', '-pm', help='Model for planner agent. Aliases: opus, sonnet, haiku')
@click.option('--executor-model', '-em', help='Model for executor agent. Aliases: opus, sonnet, haiku')
@click.option('--auto-commit/--no-auto-commit', default=False, help='Auto-commit changes on workflow completion (default: disabled)')
@click.option('--smart-commit/--no-smart-commit', default=None, help='Use AI to generate commit messages (default: enabled when auto-commit is on)')
@click.option('--auto-commit-model', help='Model for smart commit messages (default: executor model). Aliases: opus, sonnet, haiku')
@click.option('--telegram/--no-telegram', default=None, help='Enable/disable Telegram notifications (default: auto from config)')
@click.option('--no-rename', is_flag=True, default=False, help='Do not rename plan file to *_done.md on completion')
@click.option('--mcp-config', type=click.Path(exists=True), help='Path to MCP configuration file (.mcp.json)')
@click.option('--headless', is_flag=True, default=False, help='Run Playwright MCP browser in headless mode')
@click.option('--no-rewind', is_flag=True, default=False, help='Disable automatic file rewind when milestone is rejected')
@click.option('--explore/--no-explore', default=None, help='Enable/disable exploration before milestones (default: from config)')
@click.option('--explore-query', multiple=True, help='Custom exploration query (can be used multiple times)')
@click.option('--validate/--no-validate', default=None, help='Enable/disable validation after milestones (default: from config)')
@click.option('--validators', help='Comma-separated list of validators to run (default: all enabled)')
@click.option('--debug', is_flag=True, help='Enable debug mode: print full stack trace on error')
@click.option('--tui', is_flag=True, help='Run in TUI (Text User Interface) mode')
def start(
    feature: Optional[str],
    db_path: Optional[str],
    plan: Optional[str],
    queue: bool,
    queue_reset: bool,
    queue_plans: tuple,
    show_activity: bool,
    planner_model: Optional[str],
    executor_model: Optional[str],
    auto_commit: bool,
    smart_commit: Optional[bool],
    auto_commit_model: Optional[str],
    telegram: Optional[bool],
    no_rename: bool,
    mcp_config: Optional[str],
    headless: bool,
    no_rewind: bool,
    explore: Optional[bool],
    explore_query: tuple,
    validate: Optional[bool],
    validators: Optional[str],
    debug: bool,
    tui: bool,
):
    """Start a new workflow session or queue."""
    global _current_orchestrator

    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, handle_interrupt)

    # Initialize database
    db.init_db(db_path)

    # Validate input combinations
    if queue and plan:
        raise click.UsageError("--queue and --plan are mutually exclusive. Use --queue for multiple plans or --plan for a single plan.")

    # In queue mode, feature is optional (each plan has its own feature)
    # In non-queue mode, feature is required unless --plan is provided
    feature_auto_extracted = False
    if plan and not feature:
        # Auto-extract feature from plan file
        feature = extract_feature_from_plan(plan)
        feature_auto_extracted = True
        if not feature:
            raise click.UsageError(f"Could not extract feature from plan: {plan}")

    if not queue and not plan and not feature:
        raise click.UsageError("--feature/-f is required unless --queue or --plan is provided.")

    # Handle TUI mode FIRST (before any click.echo() calls)
    # This prevents stray terminal output before Textual takes over
    if tui:
        # Validate incompatible flag combinations
        if queue or queue_plans:
            click.secho("Error: --tui is not supported with queue mode", fg="red")
            click.echo("Queue mode has its own TUI via 'orchestrator start --queue ...'")
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

    # Queue mode handling
    if queue:
        _handle_queue_mode(
            queue_plans=queue_plans,
            queue_reset=queue_reset,
            db_path=db_path,
            show_activity=show_activity,
            planner_model=planner_model,
            executor_model=executor_model,
            auto_commit=auto_commit,
            telegram=telegram,
            smart_commit=smart_commit,
            no_rename=no_rename,
            mcp_config_path=mcp_config,
            headless=headless,
        )
        return

    # Non-queue mode (original behavior)
    # Resolve model names (CLI > config > defaults)
    resolved_planner = get_planner_model(planner_model)
    resolved_executor = get_executor_model(executor_model)

    # Warn about flags that are accepted but not yet wired into execution flow
    if explore is not None or explore_query:
        click.secho(
            "Note: --explore flags are accepted but not yet wired into execution flow.",
            fg="yellow"
        )
    if validate is not None or validators:
        click.secho(
            "Note: --validate flags are accepted but not yet wired into execution flow.",
            fg="yellow"
        )

    # Setup Telegram notifier if configured
    telegram_notifier = None
    if telegram is not False:  # Not explicitly disabled
        telegram_notifier = _create_telegram_notifier(telegram)

    try:
        click.secho("Starting new workflow session...", fg="cyan", bold=True)
        if feature_auto_extracted:
            click.echo(f"Feature: {feature} (from plan)")
        else:
            click.echo(f"Feature: {feature}")
        click.echo(f"Models: Planner={get_model_display_name(resolved_planner)} | Executor={get_model_display_name(resolved_executor)}")
        display_auth_info()
        if telegram_notifier:
            click.echo("Telegram: enabled")
        if plan:
            click.echo(f"Plan: {plan}")
        click.echo()

        # Check for stuck sessions and notify via Telegram
        _check_stuck_sessions(telegram_notifier, db_path)

        # Create orchestrator
        orch = Orchestrator(
            feature_description=feature,
            db_path=db_path,
            plan_path=plan,
            on_output=output_callback,
            show_activity=show_activity,
            planner_model=resolved_planner,
            executor_model=resolved_executor,
            telegram_notifier=telegram_notifier,
            debug=debug,
            mcp_config_path=mcp_config,
            headless=headless,
            enable_rewind=not no_rewind,
        )
        _current_orchestrator = orch

        click.secho(f"✓ Session created: {orch.session_id}", fg="green")
        show_progress(orch)

        # Start workflow
        click.secho("Starting workflow...", fg="cyan")
        click.echo()
        orch.start()

        # Show final status
        click.echo()
        show_progress(orch)
        click.secho("✓ Workflow completed!", fg="green", bold=True)

        # Auto-commit if enabled and workflow completed successfully
        if auto_commit and orch.state.phase == Phase.COMPLETED:
            click.echo()
            click.secho("Creating auto-commit...", fg="cyan")
            milestones = db.get_milestones(orch.session_id, db_path)
            success, msg = _do_smart_auto_commit(
                feature,
                milestones,
                smart_commit_flag=smart_commit,
                executor_model=resolved_executor,
                auto_commit_model_flag=auto_commit_model,
            )
            if success:
                click.secho("✓ Changes committed", fg="green")
                click.echo(f"  {msg.split(chr(10))[0]}")  # First line of output
            else:
                click.secho(f"⚠ Auto-commit skipped: {msg}", fg="yellow")

        # Rename plan file on completion (if imported via --plan)
        if orch.state.phase == Phase.COMPLETED and plan and not no_rename:
            success, result = _rename_plan_done(plan)
            if success:
                click.secho(f"✓ Plan renamed: {result}", fg="green")
            else:
                click.secho(f"⚠ Could not rename plan: {result}", fg="yellow")

    except KeyboardInterrupt:
        # Handled by signal handler
        pass
    except OrchestratorError as e:
        _handle_orchestrator_error(e, debug=debug, db_path=db_path)
        sys.exit(1)
    except Exception as e:
        _handle_unexpected_error(e, debug=debug)
        sys.exit(1)
    finally:
        if _current_orchestrator:
            _current_orchestrator._cleanup()
            _current_orchestrator = None


@cli.command()
@click.argument('session_id')
@click.option('--answer', '-a', help='Answer to blocker question')
@click.option('--db-path', '-d', help='Custom database path')
@click.option('--show-activity/--no-activity', default=True, help='Show streaming activity indicator (default: enabled)')
@click.option('--telegram/--no-telegram', default=None, help='Enable/disable Telegram notifications (default: auto from config)')
@click.option('--force', '-f', is_flag=True, help='Force resume orphaned sessions (bypass pause check)')
@click.option('--auto-commit/--no-auto-commit', default=False, help='Auto-commit changes on workflow completion (default: disabled)')
@click.option('--smart-commit/--no-smart-commit', default=None, help='Use AI to generate commit messages (default: enabled when auto-commit is on)')
@click.option('--auto-commit-model', default=None, help='Model for AI commit messages (default: executor model)')
@click.option('--mcp-config', type=click.Path(exists=True), help='Path to MCP configuration file (session-only override, not persisted)')
@click.option('--headless', is_flag=True, default=False, help='Run Playwright MCP browser in headless mode')
@click.option('--debug', is_flag=True, help='Enable debug mode: print full stack trace on error')
def resume(session_id: str, answer: Optional[str], db_path: Optional[str], show_activity: bool, telegram: Optional[bool], force: bool, auto_commit: bool, smart_commit: Optional[bool], auto_commit_model: Optional[str], mcp_config: Optional[str], headless: bool, debug: bool):
    """Resume an existing session."""
    global _current_orchestrator

    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, handle_interrupt)

    # Setup Telegram notifier if configured
    telegram_notifier = None
    if telegram is not False:  # Not explicitly disabled
        telegram_notifier = _create_telegram_notifier(telegram)

    try:
        click.secho(f"Resuming session: {session_id}", fg="cyan", bold=True)
        display_auth_info()
        if telegram_notifier:
            click.echo("Telegram: enabled")
        if force:
            click.secho("Force mode: bypassing pause check", fg="yellow")
        click.echo()

        # Initialize database
        db.init_db(db_path)

        # Check if session exists
        session = db.get_session(session_id, db_path)
        if not session:
            click.secho(f"✗ Session '{session_id}' not found", fg="red")
            sys.exit(1)

        # Check if session is completed
        if session['phase'] == Phase.COMPLETED:
            click.secho(f"✗ Session is already completed", fg="red")
            sys.exit(1)

        # Handle --force semantics
        if force:
            # --force cannot bypass blockers in paused sessions
            if session['phase'] == Phase.PAUSED:
                blockers = db.get_unresolved_blockers(session_id, db_path)
                if blockers:
                    click.secho("✗ Cannot use --force on paused session with blocker", fg="red")
                    click.echo()
                    click.echo(f"Question: {blockers[0]['question']}")
                    click.echo()
                    click.echo("Use normal resume with --answer instead:")
                    click.secho(f"  orchestrator resume {session_id} --answer \"your response\"", fg="cyan")
                    sys.exit(1)

            # Warn about discovery phase (waiting on human input)
            if session['phase'] == Phase.DISCOVERY:
                click.secho("⚠ Session is in discovery phase (likely waiting on human input)", fg="yellow")
                click.echo("Discovery requires human interaction. Consider if this is truly stuck.")
                click.echo()

        # Create orchestrator
        orch = Orchestrator(
            session_id=session_id,
            db_path=db_path,
            on_output=output_callback,
            show_activity=show_activity,
            telegram_notifier=telegram_notifier,
            debug=debug,
            mcp_config_path=mcp_config,
            headless=headless,
        )
        _current_orchestrator = orch

        show_progress(orch)

        # If paused, check for answer (normal resume flow)
        if session['phase'] == Phase.PAUSED and not force:
            blockers = db.get_unresolved_blockers(session_id, db_path)
            if blockers and not answer:
                click.secho("⚠️  Session is paused with unresolved blocker:", fg="yellow")
                click.echo()
                click.echo(f"Question: {blockers[0]['question']}")
                click.echo()
                click.echo("Please provide an answer using: --answer \"your response\"")
                sys.exit(1)

        # Resume workflow
        click.secho("Resuming workflow...", fg="cyan")
        click.echo()

        if force:
            # Force resume: directly call start() to continue from current phase
            # Touch heartbeat to mark session as active again
            db.touch_session(session_id, db_path)
            orch.start()
        else:
            orch.resume(answer=answer)

        # Show final status
        click.echo()
        show_progress(orch)

        # Check if this session belongs to a queue
        queue_item = db.get_queue_item_by_session_id(session_id, db_path)

        if queue_item:
            # This session is part of a queue - handle queue advancement
            click.echo()
            click.secho("Session is part of a queue", fg="cyan")

            final_phase = orch.state.phase
            final_status = orch.state.status
            project_id = queue_item["project_id"]
            item_id = queue_item["id"]
            position = queue_item["position"] + 1

            if final_phase == Phase.COMPLETED:
                # Mark queue item completed and continue queue
                db.update_queue_item(
                    item_id,
                    db_path,
                    status="completed",
                    completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                click.secho(f"✓ Queue item {position} completed", fg="green", bold=True)

                # Telegram notification if configured
                if telegram_notifier:
                    telegram_notifier.notify_queue_item_completed(position, queue_item["feature_description"])

                # Continue the queue
                click.echo()
                click.secho("Continuing queue...", fg="cyan", bold=True)

                # Continue from where we left off - get project settings from the queue item's project
                from .config import get_project_identity, get_planner_model, get_executor_model

                # Use default models for continuation (could be enhanced to store models with queue)
                _run_queue(
                    project_id=project_id,
                    db_path=db_path,
                    show_activity=show_activity,
                    planner_model=None,  # Use defaults
                    executor_model=None,  # Use defaults
                    auto_commit=auto_commit,
                    telegram=telegram,
                    smart_commit=smart_commit,
                    auto_commit_model=auto_commit_model,
                    mcp_config_path=mcp_config,
                    headless=headless,
                )

            elif final_phase == Phase.PAUSED or final_status == Status.PAUSED:
                # Still paused - keep queue item paused
                click.secho(f"⏸ Queue item {position} still paused (new blocker)", fg="yellow", bold=True)
                click.secho("Queue remains halted. Resolve blocker and resume again.", fg="yellow")

            else:
                # Failed or other terminal state - fail forward
                error_msg = f"Resume ended in unexpected state: {final_phase}/{final_status}"
                db.update_queue_item(
                    item_id,
                    db_path,
                    status="failed",
                    error_message=error_msg,
                    completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                click.secho(f"✗ Queue item {position} failed", fg="red", bold=True)
                click.secho(f"  Error: {error_msg}", fg="red")

                # Telegram notification if configured
                if telegram_notifier:
                    telegram_notifier.notify_queue_item_failed(position, queue_item["feature_description"], error_msg)

                # Continue to next item (fail-forward)
                click.echo()
                click.secho("Continuing to next queue item (fail-forward)...", fg="yellow")

                _run_queue(
                    project_id=project_id,
                    db_path=db_path,
                    show_activity=show_activity,
                    planner_model=None,
                    executor_model=None,
                    auto_commit=auto_commit,
                    telegram=telegram,
                    smart_commit=smart_commit,
                    auto_commit_model=auto_commit_model,
                    mcp_config_path=mcp_config,
                    headless=headless,
                )
        else:
            # Not part of a queue - just complete normally
            click.secho("✓ Workflow completed!", fg="green", bold=True)

    except KeyboardInterrupt:
        # Handled by signal handler
        pass
    except OrchestratorError as e:
        # Check if this was a queue session that errored
        try:
            queue_item = db.get_queue_item_by_session_id(session_id, db_path)
            if queue_item:
                # Mark queue item as failed
                db.update_queue_item(
                    queue_item["id"],
                    db_path,
                    status="failed",
                    error_message=str(e),
                    completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                click.echo()
                click.secho("Queue item marked as failed", fg="red")

                # Attempt to continue queue (fail-forward)
                if telegram_notifier:
                    telegram_notifier.notify_queue_item_failed(
                        queue_item["position"] + 1,
                        queue_item["feature_description"],
                        str(e)
                    )

                click.echo()
                click.secho("Attempting to continue queue (fail-forward)...", fg="yellow")

                _run_queue(
                    project_id=queue_item["project_id"],
                    db_path=db_path,
                    show_activity=show_activity,
                    planner_model=None,
                    executor_model=None,
                    auto_commit=auto_commit,
                    telegram=telegram,
                    smart_commit=smart_commit,
                    auto_commit_model=auto_commit_model,
                    mcp_config_path=mcp_config,
                    headless=headless,
                )
        except Exception:
            # If we can't handle queue continuation, just show the original error
            pass

        _handle_orchestrator_error(e, debug=debug, db_path=db_path)
        sys.exit(1)
    except Exception as e:
        # Check if this was a queue session that errored
        try:
            queue_item = db.get_queue_item_by_session_id(session_id, db_path)
            if queue_item:
                # Mark queue item as failed
                db.update_queue_item(
                    queue_item["id"],
                    db_path,
                    status="failed",
                    error_message=str(e),
                    completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                click.echo()
                click.secho("Queue item marked as failed", fg="red")

                # Attempt to continue queue (fail-forward)
                if telegram_notifier:
                    telegram_notifier.notify_queue_item_failed(
                        queue_item["position"] + 1,
                        queue_item["feature_description"],
                        str(e)
                    )

                click.echo()
                click.secho("Attempting to continue queue (fail-forward)...", fg="yellow")

                _run_queue(
                    project_id=queue_item["project_id"],
                    db_path=db_path,
                    show_activity=show_activity,
                    planner_model=None,
                    executor_model=None,
                    auto_commit=auto_commit,
                    telegram=telegram,
                    smart_commit=smart_commit,
                    auto_commit_model=auto_commit_model,
                    mcp_config_path=mcp_config,
                    headless=headless,
                )
        except Exception:
            # If we can't handle queue continuation, just show the original error
            pass

        _handle_unexpected_error(e, debug=debug)
        sys.exit(1)
    finally:
        if _current_orchestrator:
            _current_orchestrator._cleanup()
            _current_orchestrator = None


@cli.command()
@click.argument('session_id')
@click.argument('answer')
@click.option('--db-path', '-d', help='Custom database path')
@click.option('--telegram/--no-telegram', default=None, help='Enable/disable Telegram notifications (default: auto from config)')
@click.option('--mcp-config', type=click.Path(exists=True), help='Path to MCP configuration file (session-only override, not persisted)')
@click.option('--headless', is_flag=True, default=False, help='Run Playwright MCP browser in headless mode')
@click.option('--tui', is_flag=True, help='Run in TUI (Text User Interface) mode')
def respond(session_id: str, answer: str, db_path: Optional[str], telegram: Optional[bool], mcp_config: Optional[str], headless: bool, tui: bool):
    """Respond to a blocker and continue workflow."""
    try:
        # Initialize database
        db.init_db(db_path)

        # Check if session exists and is paused
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

        # Resume with answer (will call resume command internally)
        ctx = click.get_current_context()
        ctx.invoke(resume, session_id=session_id, answer=answer, db_path=db_path, telegram=telegram, mcp_config=mcp_config, headless=headless)

    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red", bold=True)
        sys.exit(1)


@cli.command()
@click.argument('session_id')
@click.option('--db-path', '-d', help='Custom database path')
def reset(session_id: str, db_path: Optional[str]):
    """Reset an orphaned session to allow resumption.

    Use this when a session is stuck in ACTIVE status but no process is running.
    This refreshes the heartbeat and allows force resume.
    """
    try:
        # Initialize database
        db.init_db(db_path)

        # Check if session exists
        session = db.get_session(session_id, db_path)
        if not session:
            click.secho(f"✗ Session '{session_id}' not found", fg="red")
            sys.exit(1)

        # Show current state
        click.echo(f"Session: {session_id}")
        click.echo(f"Feature: {session['feature_description']}")
        click.echo(f"Phase: {session['phase']}")
        click.echo(f"Status: {session['status']}")

        # Show last activity
        last_activity = session.get('heartbeat_at') or session.get('updated_at')
        if last_activity:
            click.echo(f"Last activity: {last_activity}")
        click.echo()

        if session['phase'] == Phase.COMPLETED:
            click.secho("✗ Session is already completed, nothing to reset", fg="yellow")
            sys.exit(0)

        if session['phase'] == Phase.PAUSED:
            blockers = db.get_unresolved_blockers(session_id, db_path)
            if blockers:
                click.secho("Session is paused with unresolved blocker:", fg="yellow")
                click.echo(f"  Question: {blockers[0]['question']}")
                click.echo()
                click.echo("Use normal resume with --answer:")
                click.secho(f"  orchestrator resume {session_id} --answer \"your response\"", fg="cyan")
            else:
                click.secho("Session is paused, you can resume normally:", fg="yellow")
                click.secho(f"  orchestrator resume {session_id}", fg="cyan")
            sys.exit(0)

        # Reset: touch heartbeat and ensure status is active
        db.touch_session(session_id, db_path)
        db.update_session(session_id, {'status': Status.ACTIVE}, db_path)

        click.secho("✓ Session reset (heartbeat refreshed)", fg="green")
        click.echo()
        click.echo("Now run:")
        click.secho(f"  orchestrator resume {session_id} --force", fg="cyan")

    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red", bold=True)
        sys.exit(1)


@cli.command()
@click.argument('session_id')
@click.option('--db-path', '-d', help='Custom database path')
@click.option('--auto-commit', is_flag=True, help='Auto-commit changes after completion')
@click.option('--smart-commit/--no-smart-commit', default=None, help='Use AI-generated commit messages')
@click.option('--auto-commit-model', help='Model for AI commit messages')
def complete(session_id: str, db_path: Optional[str], auto_commit: bool, smart_commit: Optional[bool], auto_commit_model: Optional[str]):
    """Force-complete a stuck session.

    Use this when a session has finished all work but is stuck due to:
    - Incorrect milestone count in the system
    - Blocker that cannot be resolved normally
    - Other edge cases where manual completion is needed

    This command will:
    1. Mark the session as completed
    2. Resolve any unresolved blockers
    3. Optionally commit changes (with --auto-commit)

    Examples:
        orchestrator complete 7a6b014b
        orchestrator complete 7a6b014b --auto-commit
    """
    from .config import resolve_model, load_config
    from . import git

    try:
        # Initialize database
        db.init_db(db_path)

        # Check if session exists
        session = db.get_session(session_id, db_path)
        if not session:
            click.secho(f"✗ Session '{session_id}' not found", fg="red")
            sys.exit(1)

        # Show current state
        click.secho(f"Force completing session: {session_id}", fg="cyan", bold=True)
        click.echo(f"Feature: {session['feature_description']}")
        click.echo(f"Phase: {session['phase']}")
        click.echo(f"Progress: {session.get('current_milestone', 0)}/{session.get('total_milestones', 0)} milestones")
        click.echo()

        if session['phase'] == Phase.COMPLETED:
            click.secho("✓ Session is already completed", fg="green")
            sys.exit(0)

        # Resolve any unresolved blockers
        blockers = db.get_unresolved_blockers(session_id, db_path)
        if blockers:
            click.echo(f"Resolving {len(blockers)} unresolved blocker(s)...")
            for blocker in blockers:
                db.resolve_blocker(
                    blocker["id"],
                    "Force-completed by user via 'orchestrator complete' command",
                    db_path
                )
            click.secho(f"  ✓ Resolved {len(blockers)} blocker(s)", fg="green")

        # Mark session as completed
        # Note: sessions table uses updated_at (auto-updated), not completed_at
        db.update_session(
            session_id,
            {
                'phase': Phase.COMPLETED,
                'status': Status.COMPLETED,
            },
            db_path
        )
        click.secho("✓ Session marked as completed", fg="green")

        # Handle auto-commit if requested
        if auto_commit:
            click.echo()
            click.echo("Running auto-commit...")

            # Determine smart commit settings
            config = load_config()
            use_smart = smart_commit
            if use_smart is None:
                use_smart = config.get("auto_commit", {}).get("smart", True)

            # Determine commit model
            commit_model = auto_commit_model
            if commit_model is None:
                commit_model = config.get("auto_commit", {}).get("model")
            if commit_model:
                commit_model = resolve_model(commit_model)

            # Get milestone info for commit message
            milestones = []
            current = session.get('current_milestone', 0)
            for i in range(1, current + 1):
                milestones.append({"name": f"Milestone {i}", "status": "completed"})

            # Run auto-commit
            success, message, fallback_reason = git.auto_commit(
                feature_description=session['feature_description'],
                milestones=milestones,
                use_smart_commit=use_smart,
                smart_commit_model=commit_model,
                on_status=lambda msg: click.echo(f"  {msg}"),
            )

            if success:
                click.secho(f"  ✓ Committed: {message[:60]}...", fg="green")
                if fallback_reason:
                    click.echo(f"    (used fallback: {fallback_reason})")
            else:
                click.secho(f"  ⚠ Commit skipped: {message}", fg="yellow")

        click.echo()
        click.secho("✓ Session force-completed successfully", fg="green", bold=True)

    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red", bold=True)
        sys.exit(1)


@cli.command("list")
@click.option('--status', '-s', help='Filter by status (active, paused, completed, failed)')
@click.option('--db-path', '-d', help='Custom database path')
@click.option('--all-projects', '-a', is_flag=True, help='Show sessions from all projects (default: current project only)')
def list_sessions(status: Optional[str], db_path: Optional[str], all_projects: bool):
    """List sessions for the current project."""
    from .config import get_project_identity

    try:
        # Initialize database
        db.init_db(db_path)

        # Get project scoping
        project_id = None
        if not all_projects:
            project_id, _ = get_project_identity()

        # Get sessions
        sessions = db.list_sessions(db_path, status=status, project_id=project_id)

        if not sessions:
            if all_projects:
                click.echo("No sessions found.")
            else:
                click.echo("No sessions found for this project.")
                click.echo("Use --all-projects to see sessions from other projects.")
            return

        click.echo()
        scope_text = "all projects" if all_projects else "this project"
        click.secho(f"Found {len(sessions)} session(s) ({scope_text}):", fg="cyan", bold=True)
        click.echo()

        for session in sessions:
            # Format session info
            session_id = click.style(session['id'], fg='cyan', bold=True)
            phase = format_phase(session['phase'])
            status_str = format_status(session['status'])

            click.echo(f"  {session_id}")
            click.echo(f"    Feature: {session['feature_description']}")
            click.echo(f"    Phase: {phase}  Status: {status_str}")

            # Check if this session belongs to a queue
            queue_item = db.get_queue_item_by_session_id(session['id'], db_path)
            if queue_item:
                position = queue_item['position'] + 1  # 1-based for display
                queue_status = queue_item['status'].upper()

                # Color-code queue status
                queue_status_colors = {
                    "PENDING": "white",
                    "RUNNING": "cyan",
                    "PAUSED": "yellow",
                    "COMPLETED": "green",
                    "FAILED": "red",
                }
                queue_status_colored = click.style(
                    f"[{queue_status}]",
                    fg=queue_status_colors.get(queue_status, "white")
                )

                click.echo(f"    Queue: #{position} {queue_status_colored}")

            # Show models if set
            if session.get('planner_model') or session.get('executor_model'):
                planner_display = get_model_display_name(session['planner_model']) if session.get('planner_model') else "default"
                executor_display = get_model_display_name(session['executor_model']) if session.get('executor_model') else "default"
                click.echo(f"    Models: P={planner_display} | E={executor_display}")

            if session['phase'] == Phase.EXECUTION or session['current_milestone'] > 0:
                milestone = f"[{session['current_milestone']}/{session['total_milestones']}]"
                click.echo(f"    Milestone: {click.style(milestone, fg='magenta')}")

            # Format dates
            created = datetime.fromisoformat(session['created_at']).strftime('%Y-%m-%d %H:%M')
            updated = datetime.fromisoformat(session['updated_at']).strftime('%Y-%m-%d %H:%M')
            click.echo(f"    Created: {created}  Updated: {updated}")
            click.echo()

    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red", bold=True)
        sys.exit(1)


@cli.command()
@click.argument('session_id')
@click.option('--db-path', '-d', help='Custom database path')
def status(session_id: str, db_path: Optional[str]):
    """Show session status."""
    try:
        # Initialize database
        db.init_db(db_path)

        # Get session
        session = db.get_session(session_id, db_path)
        if not session:
            click.secho(f"✗ Session '{session_id}' not found", fg="red")
            sys.exit(1)

        click.echo()
        click.echo("=" * 60)
        click.secho("SESSION STATUS", fg="cyan", bold=True)
        click.echo("=" * 60)
        click.echo()

        # Basic info
        click.echo(f"Session ID: {click.style(session['id'], fg='cyan', bold=True)}")
        click.echo(f"Feature: {session['feature_description']}")
        click.echo(f"Phase: {format_phase(session['phase'])}")
        click.echo(f"Status: {format_status(session['status'])}")

        # Model info
        if session.get('planner_model') or session.get('executor_model'):
            planner_display = get_model_display_name(session['planner_model']) if session.get('planner_model') else "default"
            executor_display = get_model_display_name(session['executor_model']) if session.get('executor_model') else "default"
            click.echo(f"Models: Planner={click.style(planner_display, fg='blue')} | Executor={click.style(executor_display, fg='magenta')}")

        # Auth info (if available)
        if session.get('auth_source'):
            auth_source = session['auth_source']
            # Format auth source for display
            auth_display = {
                'api_key': 'API Key (ANTHROPIC_API_KEY)',
                'oauth_token': 'OAuth Token (CLAUDE_CODE_OAUTH_TOKEN)',
                'credentials_file': 'Credentials File (~/.claude/.credentials.json)',
                'bedrock': 'AWS Bedrock',
                'vertex': 'Google Vertex AI',
                'foundry': 'Azure Foundry',
                'multiple': 'Multiple Sources (see auth_signals)',
                'unknown': 'Unknown',
            }.get(auth_source, auth_source)
            click.echo(f"Auth: {auth_display}")
        click.echo()

        # Milestone progress
        if session['phase'] == Phase.EXECUTION or session['current_milestone'] > 0:
            milestone = f"{session['current_milestone']}/{session['total_milestones']}"
            progress_pct = (session['current_milestone'] / session['total_milestones'] * 100) if session['total_milestones'] > 0 else 0
            click.echo(f"Milestone Progress: {click.style(milestone, fg='magenta', bold=True)} ({progress_pct:.0f}%)")

            if session['plan_path']:
                click.echo(f"Plan: {session['plan_path']}")
            click.echo()

        # Dates
        created = datetime.fromisoformat(session['created_at']).strftime('%Y-%m-%d %H:%M:%S')
        updated = datetime.fromisoformat(session['updated_at']).strftime('%Y-%m-%d %H:%M:%S')
        click.echo(f"Created: {created}")
        click.echo(f"Updated: {updated}")
        click.echo()

        # Blockers
        blockers = db.get_unresolved_blockers(session_id, db_path)
        if blockers:
            click.secho("⚠️  UNRESOLVED BLOCKERS:", fg="yellow", bold=True)
            click.echo()
            for blocker in blockers:
                click.echo(f"  Agent: {blocker['agent']}")
                click.echo(f"  Question: {blocker['question']}")
                created = datetime.fromisoformat(blocker['created_at']).strftime('%Y-%m-%d %H:%M:%S')
                click.echo(f"  Created: {created}")
                click.echo()

        # Error details for failed sessions
        if session['status'] == Status.FAILED:
            latest_error = db.get_latest_session_error(session_id, db_path)
            if latest_error:
                click.secho("ERROR DETAILS:", fg="red", bold=True)
                click.echo()
                click.echo(f"  Type: {latest_error['error_type']}")
                click.echo(f"  Message: {latest_error['error_message']}")
                if latest_error.get('phase'):
                    click.echo(f"  Phase: {latest_error['phase']}")
                if latest_error.get('milestone_number'):
                    click.echo(f"  Milestone: {latest_error['milestone_number']}")
                if latest_error.get('log_file_path'):
                    click.echo(f"  Log file: {latest_error['log_file_path']}")
                error_created = datetime.fromisoformat(latest_error['created_at']).strftime('%Y-%m-%d %H:%M:%S')
                click.echo(f"  Time: {error_created}")
                click.echo()

                # Retry guidance
                if session.get("plan_path"):
                    click.echo("To retry with the same plan:")
                    click.secho(f"  orchestrator start --plan {session['plan_path']}", fg="cyan")
                elif session.get("feature_description"):
                    click.echo("To retry with the same feature:")
                    feature = session["feature_description"].replace('"', '\\"')
                    click.secho(f'  orchestrator start -f "{feature}"', fg="cyan")
                click.echo()

        # Message count
        messages = db.get_messages(session_id, db_path=db_path)
        click.echo(f"Total Messages: {len(messages)}")

        # Milestones
        milestones = db.get_milestones(session_id, db_path=db_path)
        if milestones:
            click.echo(f"Milestones: {len(milestones)}")
            click.echo()
            click.secho("MILESTONE HISTORY:", fg="cyan", bold=True)
            click.echo()
            for m in milestones:
                status_color = "green" if m['status'] == "completed" else "yellow"
                m_status = click.style(m['status'].upper(), fg=status_color)
                click.echo(f"  [{m['number']}] {m['name'] or 'Unnamed'} - {m_status}")

        click.echo()
        click.echo("=" * 60)

    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red", bold=True)
        sys.exit(1)


@cli.command()
@click.argument('session_id')
@click.option('--output', '-o', help='Output file path')
@click.option('--db-path', '-d', help='Custom database path')
@click.option('--tools', is_flag=True, help='Include tool invocation audit trail')
def export(session_id: str, output: Optional[str], db_path: Optional[str], tools: bool):
    """Export session history to a file."""
    try:
        # Initialize database
        db.init_db(db_path)

        # Get session
        session = db.get_session(session_id, db_path)
        if not session:
            click.secho(f"✗ Session '{session_id}' not found", fg="red")
            sys.exit(1)

        # Determine output path
        if not output:
            output = f"session_{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        output_path = Path(output)

        # Get all data
        messages = db.get_messages(session_id, db_path=db_path)
        milestones = db.get_milestones(session_id, db_path=db_path)
        blockers = db.get_all_blockers(session_id, db_path=db_path)

        # Generate markdown export
        content = []
        content.append(f"# Session Export: {session_id}\n")
        content.append(f"**Feature:** {session['feature_description']}\n")
        content.append(f"**Phase:** {session['phase']}\n")
        content.append(f"**Status:** {session['status']}\n")
        if session.get('planner_model') or session.get('executor_model'):
            planner_display = get_model_display_name(session['planner_model']) if session.get('planner_model') else "default"
            executor_display = get_model_display_name(session['executor_model']) if session.get('executor_model') else "default"
            content.append(f"**Models:** Planner={planner_display} | Executor={executor_display}\n")
        if session.get('auth_source'):
            auth_source = session['auth_source']
            # Format auth source for display
            auth_display = {
                'api_key': 'API Key (ANTHROPIC_API_KEY)',
                'oauth_token': 'OAuth Token (CLAUDE_CODE_OAUTH_TOKEN)',
                'credentials_file': 'Credentials File',
                'bedrock': 'AWS Bedrock',
                'vertex': 'Google Vertex AI',
                'foundry': 'Azure Foundry',
                'multiple': 'Multiple Sources',
                'unknown': 'Unknown',
            }.get(auth_source, auth_source)
            content.append(f"**Auth:** {auth_display}\n")
        content.append(f"**Created:** {session['created_at']}\n")
        content.append(f"**Updated:** {session['updated_at']}\n")
        content.append("\n---\n\n")

        # Milestones
        if milestones:
            content.append("## Milestones\n\n")
            for m in milestones:
                content.append(f"### [{m['number']}] {m['name'] or 'Unnamed'} - {m['status'].upper()}\n\n")
                if m['executor_report']:
                    content.append("**Executor Report:**\n")
                    content.append(f"```\n{m['executor_report']}\n```\n\n")
                if m['planner_feedback']:
                    content.append("**Planner Feedback:**\n")
                    content.append(f"```\n{m['planner_feedback']}\n```\n\n")
            content.append("\n---\n\n")

        # Blockers
        if blockers:
            content.append("## Blockers\n\n")
            for b in blockers:
                resolved = "✓ RESOLVED" if b['resolved_at'] else "⚠️  UNRESOLVED"
                content.append(f"### {resolved} - {b['agent']}\n\n")
                content.append(f"**Question:** {b['question']}\n\n")
                if b['response']:
                    content.append(f"**Response:** {b['response']}\n\n")
                content.append(f"**Created:** {b['created_at']}\n")
                if b['resolved_at']:
                    content.append(f"**Resolved:** {b['resolved_at']}\n")
                content.append("\n")
            content.append("\n---\n\n")

        # Tool Invocations (if requested)
        tool_invocations = []
        if tools:
            tool_invocations = db.get_tool_invocations(session_id, db_path=db_path)
            if tool_invocations:
                content.append("## Tool Invocations\n\n")
                content.append("| Agent | Milestone | Tool | Success | Time |\n")
                content.append("|-------|-----------|------|---------|------|\n")
                for inv in tool_invocations:
                    milestone = inv['milestone_number'] or '-'
                    success = '✓' if inv['success'] else '✗'
                    time = inv['created_at'].split('.')[0] if inv['created_at'] else '-'
                    content.append(f"| {inv['agent']} | {milestone} | {inv['tool_name']} | {success} | {time} |\n")
                content.append("\n")

                # Detailed invocations with input/output
                content.append("### Tool Details\n\n")
                for inv in tool_invocations:
                    content.append(f"#### {inv['tool_name']} ({inv['agent']})\n\n")
                    if inv['input_summary']:
                        content.append(f"**Input:** `{inv['input_summary'][:200]}{'...' if len(inv['input_summary'] or '') > 200 else ''}`\n\n")
                    if inv['output_summary']:
                        content.append(f"**Output:** `{inv['output_summary'][:200]}{'...' if len(inv['output_summary'] or '') > 200 else ''}`\n\n")
                content.append("\n---\n\n")

        # Messages
        content.append("## Message History\n\n")
        current_phase = None
        for msg in messages:
            if msg['phase'] != current_phase:
                current_phase = msg['phase']
                content.append(f"\n### Phase: {current_phase.upper()}\n\n")

            content.append(f"**{msg['agent']}** ({msg['role']}) - {msg['created_at']}\n")
            if msg['token_count']:
                content.append(f"*Tokens: {msg['token_count']}*\n\n")
            content.append(f"```\n{msg['content']}\n```\n\n")

        # Write to file
        output_path.write_text("".join(content))

        click.secho(f"✓ Session exported to: {output_path}", fg="green", bold=True)
        click.echo(f"  Messages: {len(messages)}")
        click.echo(f"  Milestones: {len(milestones)}")
        click.echo(f"  Blockers: {len(blockers)}")
        if tools:
            click.echo(f"  Tool Invocations: {len(tool_invocations)}")

    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red", bold=True)
        sys.exit(1)


# ============================================================================
# Telegram Commands
# ============================================================================

@cli.group()
def telegram():
    """Telegram integration commands."""
    pass


@telegram.command("test")
def telegram_test():
    """Test Telegram configuration by sending a test message."""
    try:
        from .telegram import TelegramNotifier, HTTPX_AVAILABLE

        if not HTTPX_AVAILABLE:
            click.secho("✗ httpx is required. Install with: pip install httpx", fg="red")
            sys.exit(1)

        telegram_config = get_telegram_config()

        if not telegram_config.get("bot_token") or not telegram_config.get("chat_id"):
            click.secho("✗ Telegram not configured", fg="red")
            click.echo()
            click.echo("Configure via ~/.claude_orchestrator/config.yaml:")
            click.echo()
            click.echo("  telegram:")
            click.echo("    enabled: true")
            click.echo("    bot_token: \"YOUR_BOT_TOKEN\"")
            click.echo("    chat_id: \"YOUR_CHAT_ID\"")
            click.echo()
            click.echo("Or via environment variables:")
            click.echo("  ORCHESTRATOR_TELEGRAM_BOT_TOKEN")
            click.echo("  ORCHESTRATOR_TELEGRAM_CHAT_ID")
            sys.exit(1)

        click.echo("Testing Telegram connection...")
        click.echo(f"  Bot token: ...{telegram_config['bot_token'][-4:]}")
        click.echo(f"  Chat ID: {telegram_config['chat_id']}")
        click.echo()

        notifier = TelegramNotifier(
            bot_token=telegram_config["bot_token"],
            chat_id=telegram_config["chat_id"],
        )

        success, message = notifier.send_test_message()
        notifier.close()

        if success:
            click.secho(f"✓ {message}", fg="green")
        else:
            click.secho(f"✗ {message}", fg="red")
            sys.exit(1)

    except ImportError as e:
        click.secho(f"✗ Import error: {e}", fg="red")
        click.echo("Install telegram dependencies: pip install httpx")
        sys.exit(1)
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red")
        sys.exit(1)


@telegram.command("ping")
@click.option("--timeout", default=60, help="Seconds to wait for reply (default: 60)")
@click.option("-v", "--verbose", is_flag=True, help="Show debug output")
def telegram_ping(timeout: int, verbose: bool):
    """Verify 2-way Telegram communication with ping-pong.

    Sends a ping message to your configured Telegram chat and waits for
    you to reply. This verifies that both outbound and inbound messaging
    work correctly before relying on blocker replies.

    Reply to the ping message (not a new message) to confirm 2-way communication.
    """
    try:
        from .telegram import TelegramNotifier, TelegramListener, HTTPX_AVAILABLE

        if not HTTPX_AVAILABLE:
            click.secho("✗ httpx is required. Install with: pip install httpx", fg="red")
            sys.exit(1)

        telegram_config = get_telegram_config()

        if not telegram_config.get("bot_token") or not telegram_config.get("chat_id"):
            click.secho("✗ Telegram not configured", fg="red")
            click.echo()
            click.echo("Configure via ~/.claude_orchestrator/config.yaml:")
            click.echo()
            click.echo("  telegram:")
            click.echo("    enabled: true")
            click.echo("    bot_token: \"YOUR_BOT_TOKEN\"")
            click.echo("    chat_id: \"YOUR_CHAT_ID\"")
            click.echo()
            click.echo("Or via environment variables:")
            click.echo("  ORCHESTRATOR_TELEGRAM_BOT_TOKEN")
            click.echo("  ORCHESTRATOR_TELEGRAM_CHAT_ID")
            sys.exit(1)

        click.echo("Sending ping message to Telegram...")

        notifier = TelegramNotifier(
            bot_token=telegram_config["bot_token"],
            chat_id=telegram_config["chat_id"],
        )

        message_id = notifier.send_ping()

        if not message_id:
            click.secho("✗ Failed to send ping message", fg="red")
            notifier.close()
            sys.exit(1)

        click.secho(f"✓ Ping sent (message_id: {message_id})", fg="green")
        click.echo()
        click.echo(f"Waiting for your reply in Telegram (timeout: {timeout}s)...")
        click.echo("Reply to the ping message with any text to confirm 2-way communication.")
        click.echo()

        listener = TelegramListener(
            bot_token=telegram_config["bot_token"],
            chat_id=telegram_config["chat_id"],
            verbose=verbose,
        )

        try:
            reply = listener.wait_for_pong(message_id, timeout=timeout)

            if reply:
                click.secho(f'✓ Pong received: "{reply}"', fg="green")
                click.secho("✓ 2-way communication verified!", fg="green", bold=True)
                # Send confirmation back
                notifier._send_message("✓ Pong received! 2-way communication verified.")
            else:
                click.secho(f"✗ Timeout: No reply received within {timeout}s.", fg="red")
                click.echo("Check that you replied to the ping message (not a new message).")
                sys.exit(1)
        finally:
            listener.close()
            notifier.close()

    except ImportError as e:
        click.secho(f"✗ Import error: {e}", fg="red")
        click.echo("Install telegram dependencies: pip install httpx")
        sys.exit(1)
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red")
        sys.exit(1)


@telegram.command("listen")
@click.option('--db-path', '-d', help='Custom database path')
@click.option('--poll-interval', default=3, help='Poll interval in seconds (default: 3)')
@click.option('--once', is_flag=True, help='Process one batch and exit')
@click.option('--verbose', '-v', is_flag=True, help='Show verbose debug output')
def telegram_listen(db_path: Optional[str], poll_interval: int, once: bool, verbose: bool):
    """Listen for Telegram replies to blocker notifications.

    Polls Telegram for reply messages and automatically resumes paused
    workflows when a blocker is answered.

    The listener only processes:
    - Direct messages (DM) from the configured chat_id
    - Replies to blocker notification messages
    - Messages from the current project (by default)

    Use --verbose to see ignored messages and mapping decisions.
    """
    from .telegram import TelegramListener, HTTPX_AVAILABLE
    from .config import get_project_identity

    if not HTTPX_AVAILABLE:
        click.secho("✗ httpx is required. Install with: pip install httpx", fg="red")
        sys.exit(1)

    telegram_config = get_telegram_config()

    if not telegram_config.get("bot_token") or not telegram_config.get("chat_id"):
        click.secho("✗ Telegram not configured", fg="red")
        click.echo()
        click.echo("See: orchestrator telegram test")
        sys.exit(1)

    # Initialize database
    db.init_db(db_path)

    # Get current project identity for scoping
    current_project_id, _ = get_project_identity()

    click.echo()
    click.secho("🎧 Telegram Listener (Phase 2)", fg="cyan", bold=True)
    click.echo()
    click.echo(f"  Bot token: ...{telegram_config['bot_token'][-4:]}")
    click.echo(f"  Chat ID: {telegram_config['chat_id']}")
    click.echo(f"  Project: {current_project_id}")
    click.echo(f"  Poll interval: {poll_interval}s")
    if verbose:
        click.echo("  Verbose: enabled")
    click.echo()
    click.secho("Press Ctrl+C to stop", fg="yellow")
    click.echo()

    # Create listener
    listener = TelegramListener(
        bot_token=telegram_config["bot_token"],
        chat_id=telegram_config["chat_id"],
        allowed_user_id=telegram_config.get("allowed_user_id"),
        poll_interval=poll_interval,
        verbose=verbose,
    )

    def handle_blocker_reply(telegram_message_id: int, answer: str, chat_id: str) -> Optional[str]:
        """
        Handle a reply to a blocker notification.

        Returns error message or None on success.
        """
        # Find blocker by telegram message ID
        blocker = db.get_blocker_by_telegram_message_id(telegram_message_id, db_path)

        if not blocker:
            if verbose:
                click.echo(f"  [verbose] No blocker found for message_id={telegram_message_id}")
            return "No blocker found for this message"

        # Check if blocker is already resolved
        if blocker.get("resolved_at"):
            return "This blocker has already been resolved"

        # Check project scoping
        blocker_project_id = blocker.get("project_id")
        if blocker_project_id and blocker_project_id != current_project_id:
            return f"Blocker belongs to different project: {blocker_project_id}"

        session_id = blocker["session_id"]
        blocker_id = blocker["id"]

        click.echo(f"  → Processing reply for session {session_id[:8]}")
        click.echo(f"    Question: {blocker['question'][:50]}...")
        click.echo(f"    Answer: {answer[:50]}...")

        # Resolve the blocker (but don't change session state - leave it paused
        # so `orchestrator resume` works correctly)
        try:
            db.resolve_blocker(blocker_id, answer, db_path)
            click.secho(f"  ✓ Blocker resolved", fg="green")
            return None  # Success

        except Exception as e:
            return f"Failed to resolve blocker: {e}"

    def get_last_update_id() -> int:
        return db.get_telegram_last_update_id(db_path)

    def set_last_update_id(update_id: int) -> None:
        db.set_telegram_last_update_id(update_id, db_path)

    def on_shutdown():
        click.echo()
        click.secho("✓ Listener stopped gracefully", fg="green")

    try:
        if once:
            # Single batch mode
            last_update_id = get_last_update_id()
            click.echo(f"Processing single batch (offset: {last_update_id})...")
            new_last_update_id = listener.poll_once(last_update_id, handle_blocker_reply)
            if new_last_update_id != last_update_id:
                set_last_update_id(new_last_update_id)
            click.secho("✓ Done", fg="green")
        else:
            # Continuous polling mode
            listener.run(
                on_blocker_reply=handle_blocker_reply,
                get_last_update_id=get_last_update_id,
                set_last_update_id=set_last_update_id,
                on_shutdown=on_shutdown,
            )

    except KeyboardInterrupt:
        click.echo()
        click.secho("✓ Interrupted", fg="yellow")
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red")
        sys.exit(1)
    finally:
        listener.close()


@cli.command()
@click.option('--model', '-m', default='sonnet',
              help='Model: opus, sonnet, haiku (default: sonnet)')
@click.option('--system-prompt', '-s', type=click.Path(exists=True),
              help='Path to custom system prompt file')
@click.option('--no-tools', is_flag=True,
              help='Disable file/bash tools (pure chat)')
@click.option('--show-activity/--no-activity', default=True,
              help='Show streaming activity indicator (default: enabled)')
def chat(model: str, system_prompt: Optional[str], no_tools: bool, show_activity: bool):
    """Start a direct chat session with Claude (no orchestration)."""
    from .chat import ChatSession

    # Display auth info at startup
    display_auth_info()

    # Load system prompt from file if provided
    prompt_content = None
    if system_prompt:
        prompt_content = Path(system_prompt).read_text()

    session = ChatSession(
        model=model,
        system_prompt=prompt_content,
        tools_enabled=not no_tools,
        show_activity=show_activity,
    )
    session.start()


@cli.command()
@click.option('--verbose', '-v', is_flag=True, help='Show detailed output')
@click.option('--mcp-config', type=click.Path(exists=True), help='Path to MCP configuration file to verify server connections')
def check(verbose: bool, mcp_config: Optional[str]):
    """Run health checks on dependencies, permissions, and authentication."""
    import importlib
    import tempfile
    import os

    click.echo()
    click.secho("=" * 60, bold=True)
    click.secho("  ORCHESTRATOR HEALTH CHECK", bold=True)
    click.secho("=" * 60, bold=True)
    click.echo()

    all_passed = True

    # -------------------------------------------------------------------------
    # 1. Dependencies Check
    # -------------------------------------------------------------------------
    click.secho("1. Dependencies", bold=True)

    required_deps = [
        ("claude_agent_sdk", "claude-agent-sdk", True),
        ("click", "click", True),
        ("prompt_toolkit", "prompt_toolkit", True),
        ("yaml", "pyyaml", True),
    ]
    optional_deps = [
        ("httpx", "httpx", False),  # For Telegram
    ]

    for module_name, package_name, required in required_deps + optional_deps:
        try:
            importlib.import_module(module_name)
            click.echo(f"   {click.style('✓', fg='green')} {package_name}")
        except ImportError:
            if required:
                click.echo(f"   {click.style('✗', fg='red')} {package_name} (MISSING - required)")
                all_passed = False
            else:
                click.echo(f"   {click.style('○', fg='yellow')} {package_name} (optional, not installed)")

    click.echo()

    # -------------------------------------------------------------------------
    # 2. Permissions Check
    # -------------------------------------------------------------------------
    click.secho("2. Permissions", bold=True)

    # Check database directory
    db_dir = db.DEFAULT_DB_DIR
    try:
        db_dir.mkdir(parents=True, exist_ok=True)
        # Test write permission
        test_file = db_dir / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        click.echo(f"   {click.style('✓', fg='green')} Database directory: {db_dir}")
        if verbose:
            click.echo(f"      Writable: Yes")
    except (PermissionError, OSError) as e:
        click.echo(f"   {click.style('✗', fg='red')} Database directory: {db_dir}")
        click.echo(f"      Error: {e}")
        all_passed = False

    # Check if database exists and is accessible
    db_path = db.DEFAULT_DB_PATH
    if db_path.exists():
        try:
            with db.get_connection() as conn:
                conn.execute("SELECT 1")
            click.echo(f"   {click.style('✓', fg='green')} Database file: {db_path}")
            if verbose:
                # Count sessions
                with db.get_connection() as conn:
                    cursor = conn.execute("SELECT COUNT(*) FROM sessions")
                    count = cursor.fetchone()[0]
                click.echo(f"      Sessions: {count}")
        except Exception as e:
            click.echo(f"   {click.style('✗', fg='red')} Database file: {db_path}")
            click.echo(f"      Error: {e}")
            all_passed = False
    else:
        click.echo(f"   {click.style('○', fg='yellow')} Database file: Not created yet (will be created on first use)")

    click.echo()

    # -------------------------------------------------------------------------
    # 3. Authentication Check
    # -------------------------------------------------------------------------
    click.secho("3. Authentication", bold=True)

    auth_info = detect_auth()

    if not auth_info.is_configured:
        click.echo(f"   {click.style('✗', fg='red')} No authentication detected")
        click.echo(f"      Set ANTHROPIC_API_KEY or run 'claude setup-token'")
        click.echo(f"      Note: macOS Keychain credentials cannot be detected")
        all_passed = False
    else:
        # Show detected sources
        for signal in auth_info.signals:
            source_name = signal.source.value.replace("_", " ").title()
            if signal.env_var:
                hint = f" ({signal.key_hint})" if signal.key_hint else ""
                click.echo(f"   {click.style('✓', fg='green')} {signal.env_var}{hint}")
            elif signal.file_path:
                click.echo(f"   {click.style('✓', fg='green')} Credentials file: {signal.file_path}")

        if auth_info.has_multiple:
            click.secho(f"   ⚠ Multiple sources detected - Claude Code will choose one", fg="yellow")

    click.echo()

    # -------------------------------------------------------------------------
    # 4. API Connection Test
    # -------------------------------------------------------------------------
    click.secho("4. API Connection", bold=True)

    if not auth_info.is_configured:
        click.echo(f"   {click.style('○', fg='yellow')} Skipped (no auth configured)")
    else:
        # Check if using OAuth token (requires Claude Agent SDK) vs API key (anthropic SDK)
        from .auth import AuthSource
        uses_oauth = any(
            s.source == AuthSource.OAUTH_TOKEN or s.source == AuthSource.CREDENTIALS_FILE
            for s in auth_info.signals
        )
        uses_api_key = any(s.source == AuthSource.API_KEY for s in auth_info.signals)

        if uses_oauth and not uses_api_key:
            # OAuth token - use Claude Agent SDK for testing
            click.echo(f"   Testing connection via Claude Agent SDK...")
            try:
                import asyncio
                from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

                async def test_oauth_connection():
                    options = ClaudeAgentOptions(
                        model="claude-3-5-haiku-20241022",
                    )
                    async with ClaudeSDKClient(options) as client:
                        await client.query("Say 'ok'")
                        async for message in client.receive_messages():
                            if hasattr(message, 'content'):
                                return message.content
                        return None

                result = asyncio.run(test_oauth_connection())
                if result:
                    click.echo(f"   {click.style('✓', fg='green')} Connection successful (OAuth)")
                    if verbose:
                        click.echo(f"      Auth: Claude Code OAuth token")
                else:
                    click.echo(f"   {click.style('✗', fg='red')} Connection failed: No response")
                    all_passed = False

            except Exception as e:
                error_msg = str(e)
                if "401" in error_msg or "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
                    click.echo(f"   {click.style('✗', fg='red')} Authentication failed")
                    click.echo(f"      Error: OAuth token invalid or expired")
                    click.echo(f"      Try: claude setup-token")
                else:
                    click.echo(f"   {click.style('✗', fg='red')} Connection test failed")
                    click.echo(f"      Error: {e}")
                if verbose:
                    click.echo(f"      Details: {e}")
                all_passed = False
        else:
            # API key - use anthropic SDK directly
            click.echo(f"   Testing connection via Anthropic SDK...")
            try:
                import anthropic

                # Create client and make a minimal request
                client = anthropic.Anthropic()
                response = client.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Say 'ok'"}],
                )

                # Check response
                if response.content and len(response.content) > 0:
                    click.echo(f"   {click.style('✓', fg='green')} Connection successful")
                    if verbose:
                        click.echo(f"      Model: claude-3-5-haiku-20241022")
                        click.echo(f"      Response: {response.content[0].text.strip()}")
                else:
                    click.echo(f"   {click.style('✗', fg='red')} Connection failed: Empty response")
                    all_passed = False

            except anthropic.AuthenticationError as e:
                click.echo(f"   {click.style('✗', fg='red')} Authentication failed")
                click.echo(f"      Error: Invalid API key or unauthorized")
                if verbose:
                    click.echo(f"      Details: {e}")
                all_passed = False
            except anthropic.APIConnectionError as e:
                click.echo(f"   {click.style('✗', fg='red')} Connection failed")
                click.echo(f"      Error: Could not reach Anthropic API")
                if verbose:
                    click.echo(f"      Details: {e}")
                all_passed = False
            except Exception as e:
                click.echo(f"   {click.style('✗', fg='red')} Connection test failed")
                click.echo(f"      Error: {e}")
                all_passed = False

    click.echo()

    # -------------------------------------------------------------------------
    # 5. MCP Process Detection
    # -------------------------------------------------------------------------
    click.secho("5. MCP Processes", bold=True)

    mcp_processes, mcp_error = _detect_mcp_processes()
    if mcp_error == "windows":
        click.echo(f"   {click.style('○', fg='yellow')} MCP process detection not supported on Windows")
    elif mcp_error == "pgrep_missing":
        click.echo(f"   {click.style('○', fg='yellow')} MCP process detection unavailable (pgrep not found)")
    elif mcp_processes:
        click.secho(f"   ⚠ MCP processes detected: {len(mcp_processes)} running", fg="yellow")
        for name, _, pid in mcp_processes[:3]:
            click.echo(f"      • {name} (PID: {pid})")
        if len(mcp_processes) > 3:
            click.echo(f"      ... and {len(mcp_processes) - 3} more")
        click.echo(f"      These may be orphaned. Run: orchestrator cleanup --dry-run")
        # Note: Don't fail check for this, just warn
    else:
        click.echo(f"   {click.style('✓', fg='green')} No MCP server processes detected")

    click.echo()

    # -------------------------------------------------------------------------
    # 6. MCP Server Status (SDK 0.1.23+)
    # -------------------------------------------------------------------------
    if mcp_config:
        click.secho("6. MCP Server Status", bold=True)

        try:
            import asyncio
            from claude_agent_sdk import ClaudeSDKClient
            from claude_agent_sdk.types import ClaudeAgentOptions
            from .config import load_mcp_config_raw

            # Load MCP config
            mcp_servers = load_mcp_config_raw(mcp_config)
            if not mcp_servers:
                click.echo(f"   {click.style('○', fg='yellow')} No MCP servers found in config")
            else:
                click.echo(f"   Found {len(mcp_servers)} MCP server(s) in config:")
                for server_name in mcp_servers:
                    click.echo(f"      • {server_name}")

                # Test server connections
                click.echo(f"   Testing connections...")

                async def check_mcp_status():
                    options = ClaudeAgentOptions(
                        model="claude-3-5-haiku-20241022",
                        mcp_servers=mcp_servers,
                    )
                    async with ClaudeSDKClient(options) as client:
                        return await client.get_mcp_status()

                try:
                    status = asyncio.run(check_mcp_status())
                    if status:
                        for server_name, info in status.items():
                            if info.get('connected', False):
                                click.echo(f"   {click.style('✓', fg='green')} {server_name}: connected")
                            else:
                                error = info.get('error', 'disconnected')
                                click.echo(f"   {click.style('✗', fg='red')} {server_name}: {error}")
                                all_passed = False
                    else:
                        click.echo(f"   {click.style('○', fg='yellow')} No status returned (servers may not be started)")
                except Exception as e:
                    click.echo(f"   {click.style('✗', fg='red')} Status check failed: {e}")
                    if verbose:
                        import traceback
                        traceback.print_exc()

        except ImportError as e:
            click.echo(f"   {click.style('✗', fg='red')} Missing dependency: {e}")
        except Exception as e:
            click.echo(f"   {click.style('✗', fg='red')} Config load failed: {e}")

        click.echo()

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    click.secho("=" * 60, bold=True)
    if all_passed:
        click.secho("  ✓ All checks passed", fg="green", bold=True)
    else:
        click.secho("  ✗ Some checks failed", fg="red", bold=True)
    click.secho("=" * 60, bold=True)
    click.echo()

    sys.exit(0 if all_passed else 1)


# =============================================================================
# MCP Process Detection & Cleanup
# =============================================================================

# Default patterns - intentionally conservative (MCP servers only)
DEFAULT_MCP_PATTERNS = [
    ("Playwright MCP Server", "mcp-server-playwright"),
    ("MCP NPX Process", "npx.*@playwright/mcp"),
]

# Extended patterns - more aggressive, higher risk of false positives
EXTENDED_MCP_PATTERNS = [
    ("Playwright Chrome", "ms-playwright/mcp-chrome"),
    ("Playwright Chromium", "ms-playwright/chromium"),
]


def _detect_mcp_processes(include_extended: bool = False):
    """
    Detect running MCP-related processes.

    Args:
        include_extended: Include browser processes (higher false positive risk)

    Returns:
        Tuple of (processes, error) where:
        - processes: List of (process_name, pattern, pid) tuples, deduped by PID
        - error: None if successful, or error string ("windows", "pgrep_missing")

    Note: May include processes from other applications using Playwright.
    """
    import subprocess
    import platform

    if platform.system() == "Windows":
        return ([], "windows")

    patterns = list(DEFAULT_MCP_PATTERNS)
    if include_extended:
        patterns.extend(EXTENDED_MCP_PATTERNS)

    found = []
    seen_pids = set()  # Dedupe by PID

    for name, pattern in patterns:
        try:
            result = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                for pid in result.stdout.strip().split('\n'):
                    if pid and pid not in seen_pids:
                        seen_pids.add(pid)
                        found.append((name, pattern, pid))
        except FileNotFoundError:
            return ([], "pgrep_missing")
        except Exception:
            pass  # Other errors (timeout, etc.) - continue with other patterns

    return (found, None)


def _is_process_running(pid: str) -> bool:
    """Check if a process is still running."""
    import subprocess
    try:
        result = subprocess.run(
            ["kill", "-0", pid],
            capture_output=True,
            timeout=2
        )
        return result.returncode == 0
    except Exception:
        return False


def _graceful_kill(pid: str, timeout: float = 2.0) -> tuple:
    """
    Kill a process gracefully: SIGTERM first, then SIGKILL if needed.

    Args:
        pid: Process ID to kill
        timeout: Seconds to wait after SIGTERM before escalating to SIGKILL

    Returns:
        Tuple of (success: bool, method: str, error: str or None)
        method is "SIGTERM", "SIGKILL", or None if failed
    """
    import subprocess
    import time

    # Try SIGTERM first (graceful)
    try:
        result = subprocess.run(
            ["kill", pid],  # Default is SIGTERM
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Wait briefly for process to exit
            time.sleep(0.5)
            if not _is_process_running(pid):
                return (True, "SIGTERM", None)

            # Process still running, wait a bit more
            time.sleep(timeout - 0.5)
            if not _is_process_running(pid):
                return (True, "SIGTERM", None)

            # Escalate to SIGKILL
            result = subprocess.run(
                ["kill", "-9", pid],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return (True, "SIGKILL", None)
            else:
                return (False, None, result.stderr.strip() or "kill -9 failed")
        else:
            # SIGTERM failed - maybe process already gone or permission denied
            error = result.stderr.strip()
            if "No such process" in error:
                return (True, "already_gone", None)
            return (False, None, error or "SIGTERM failed")
    except subprocess.TimeoutExpired:
        return (False, None, "timeout")
    except FileNotFoundError:
        return (False, None, "kill command not found")
    except Exception as e:
        return (False, None, str(e))


@cli.command()
@click.option('--dry-run', is_flag=True, help='Show what would be killed without actually killing')
@click.option('--force', '-f', is_flag=True, help='Skip confirmation prompt')
@click.option('--all', 'kill_all', is_flag=True, help='Include browser processes (may affect other Playwright users)')
@click.option('--pattern', '-p', multiple=True, help='Custom pattern(s) to match (can be specified multiple times)')
def cleanup(dry_run: bool, force: bool, kill_all: bool, pattern: tuple):
    """Kill orphaned MCP processes (Playwright MCP servers).

    By default, only kills MCP server processes. Use --all to also kill
    Playwright browser processes (WARNING: may affect other Playwright users).

    \b
    ⚠️  WARNING: Pattern matching may kill unrelated processes.
    Always use --dry-run first to preview what will be killed.

    Examples:

    \b
        orchestrator cleanup              # Kill MCP servers only (safe)
        orchestrator cleanup --dry-run    # Preview what would be killed
        orchestrator cleanup --all        # Also kill browser processes
        orchestrator cleanup -p "my-mcp"  # Custom pattern
    """
    import subprocess
    import platform

    if platform.system() == "Windows":
        click.secho("⚠ Windows cleanup not yet supported. Please use Task Manager.", fg="yellow")
        click.echo("Look for: node.exe (mcp-server), chrome.exe (playwright)")
        sys.exit(1)

    # Build pattern list
    if pattern:
        # User-specified patterns
        patterns = [("Custom", p) for p in pattern]
    else:
        patterns = list(DEFAULT_MCP_PATTERNS)
        if kill_all:
            patterns.extend(EXTENDED_MCP_PATTERNS)

    click.secho("🔍 Scanning for MCP processes...\n", fg="cyan")

    if not kill_all and not pattern:
        click.secho("ℹ  Using conservative patterns (MCP servers only).", fg="blue")
        click.secho("   Use --all to include browser processes (may affect other users).\n", fg="blue")

    # Scan for processes with deduplication
    found_processes = []
    seen_pids = set()
    pgrep_available = True

    for name, pat in patterns:
        try:
            result = subprocess.run(
                ["pgrep", "-f", pat],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid and pid not in seen_pids:
                        seen_pids.add(pid)
                        found_processes.append((name, pat, pid))
        except FileNotFoundError:
            click.secho("✗ Error: 'pgrep' command not found.", fg="red")
            click.echo("  Install procps (Linux) or use 'ps aux | grep' manually.")
            sys.exit(1)
        except Exception:
            pass

    if not found_processes:
        click.secho("✓ No matching MCP processes found.", fg="green")
        return

    # Display found processes (count reflects deduped list)
    click.secho(f"Found {len(found_processes)} process(es):\n", fg="yellow")
    for name, pat, pid in found_processes:
        # Try to get process command for clarity
        try:
            cmd_result = subprocess.run(
                ["ps", "-p", pid, "-o", "command="],
                capture_output=True,
                text=True,
                timeout=2
            )
            cmd = cmd_result.stdout.strip()[:60] + "..." if len(cmd_result.stdout.strip()) > 60 else cmd_result.stdout.strip()
        except Exception:
            cmd = f"(pattern: {pat})"
        click.echo(f"  • PID {pid}: {cmd}")
    click.echo()

    # Warning for --all mode
    if kill_all:
        click.secho("⚠  WARNING: --all mode may kill Playwright processes from other applications!", fg="yellow", bold=True)
        click.echo()

    if dry_run:
        click.secho("Dry run - no processes killed.", fg="cyan")
        return

    # Confirm unless forced
    if not force:
        if not click.confirm("Kill these processes?"):
            click.echo("Aborted.")
            return

    # Kill processes with graceful termination
    killed = 0
    for name, pat, pid in found_processes:
        success, method, error = _graceful_kill(pid)
        if success:
            if method == "already_gone":
                click.secho(f"  ○ PID {pid} already terminated", fg="yellow")
            elif method == "SIGKILL":
                click.secho(f"  ✓ Killed PID {pid} (force)", fg="green")
            else:
                click.secho(f"  ✓ Killed PID {pid}", fg="green")
            killed += 1
        else:
            click.secho(f"  ✗ Failed to kill PID {pid}: {error}", fg="red")

    click.echo()
    click.secho(f"Cleanup complete. Killed {killed}/{len(found_processes)} processes.",
                fg="green" if killed == len(found_processes) else "yellow")


@cli.command()
@click.argument('input_file', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), help='Output file path (default: stdout)')
@click.option('--in-place', '-i', is_flag=True, help='Modify input file in place (creates .bak backup)')
@click.option('--no-backup', is_flag=True, help='Skip backup creation when using --in-place')
@click.option('--model', '-m', default='sonnet', help='Model: opus, sonnet, haiku (default: sonnet)')
@click.option('--max-milestones', default=5, type=int, help='Maximum milestones to create (default: 5)')
@click.option('--validate-only', is_flag=True, help='Only check if file is orchestrator-compatible')
@click.option('--dry-run', is_flag=True, help='Preview conversion without writing')
def convert(
    input_file: str,
    output: Optional[str],
    in_place: bool,
    no_backup: bool,
    model: str,
    max_milestones: int,
    validate_only: bool,
    dry_run: bool,
):
    """Convert a markdown plan to orchestrator-compatible format.

    Uses AI to restructure regular markdown plans into the orchestrator format
    with properly formatted milestone headers (### Milestone N: Name).

    \b
    Examples:
      orchestrator convert plan.md                    # Output to stdout
      orchestrator convert plan.md -o converted.md   # Output to file
      orchestrator convert plan.md --in-place        # Modify in place (with backup)
      orchestrator convert plan.md --validate-only   # Check if already valid
      orchestrator convert plan.md --dry-run         # Preview without writing
    """
    from .convert import (
        convert_plan,
        validate_plan_content,
        ConversionError,
    )
    from .config import resolve_model

    input_path = Path(input_file)

    # Check mutually exclusive options
    if output and in_place:
        raise click.UsageError("Cannot use both --output and --in-place")

    # Read input file
    try:
        content = input_path.read_text()
    except Exception as e:
        click.secho(f"Error reading file: {e}", fg="red")
        sys.exit(1)

    # Pre-validate
    is_valid, details = validate_plan_content(content)

    if validate_only:
        # Validation-only mode
        if is_valid:
            click.secho(f"✓ Valid orchestrator plan", fg="green")
            click.echo(f"  Milestones: {details['milestones']}")
            for i, name in enumerate(details['milestone_names'], 1):
                click.echo(f"    {i}. {name}")
            sys.exit(0)
        else:
            click.secho(f"✗ Not a valid orchestrator plan", fg="red")
            click.echo(f"  Error: {details['error']}")
            sys.exit(1)

    # If already valid, inform user and skip conversion (unless output/in-place specified)
    if is_valid and not output and not in_place and not dry_run:
        click.secho(f"✓ File is already orchestrator-compatible", fg="green")
        click.echo(f"  Milestones: {details['milestones']}")
        click.echo(f"  Use --output or --in-place to force re-conversion")
        sys.exit(0)

    # Resolve model alias
    resolved_model = resolve_model(model)

    # Perform conversion
    click.echo(f"Converting plan using {click.style(model, fg='cyan')}...")

    try:
        converted, metadata = convert_plan(
            content=content,
            model=resolved_model,
            max_milestones=max_milestones,
        )
    except ConversionError as e:
        click.secho(f"✗ Conversion failed: {e}", fg="red")
        sys.exit(2)
    except Exception as e:
        click.secho(f"✗ Unexpected error: {e}", fg="red")
        sys.exit(1)

    # Show result info
    click.secho(f"✓ Converted to {metadata['milestones']} milestones", fg="green")
    if metadata.get('retry_used'):
        click.secho("  (required retry with enhanced prompt)", fg="yellow")
    if metadata.get('feature'):
        click.echo(f"  Feature: {metadata['feature']}")
    for i, name in enumerate(metadata['milestone_names'], 1):
        click.echo(f"    {i}. {name}")

    # Handle output
    if dry_run:
        click.echo()
        click.secho("--- DRY RUN (preview) ---", fg="yellow", bold=True)
        click.echo(converted)
        click.secho("--- END PREVIEW ---", fg="yellow", bold=True)
        sys.exit(0)

    if in_place:
        # Create backup unless disabled
        if not no_backup:
            backup_path = input_path.with_suffix(input_path.suffix + '.bak')
            backup_path.write_text(content)
            click.echo(f"  Backup: {backup_path}")

        # Write to original file
        input_path.write_text(converted)
        click.echo(f"  Updated: {input_path}")

    elif output:
        # Write to specified output file
        output_path = Path(output)
        output_path.write_text(converted)
        click.echo(f"  Saved to: {output_path}")

    else:
        # Output to stdout
        click.echo()
        click.echo(converted)

    sys.exit(0)


# =============================================================================
# Watch Mode - Directory monitoring for plan files
# =============================================================================

from dataclasses import dataclass
from typing import List
import time


@dataclass
class WatchResult:
    """Result of processing a plan file in watch mode."""
    status: str  # 'completed', 'failed', 'paused', 'skipped', 'conversion_failed'
    session_id: Optional[str] = None
    executed_path: Optional[Path] = None  # The file that was actually executed (may differ if converted)
    error: Optional[str] = None


def _is_watch_candidate(path: Path) -> bool:
    """
    Check if file should be considered for processing in watch mode.

    A file is a candidate if:
    - It has .md extension
    - It does not start with _orchestrator-skip (quarantined)
    - It does not end with _done (completed)
    - It does not end with _failed (failed execution)
    - It does not end with _paused (paused on blocker)

    Args:
        path: Path to check

    Returns:
        True if file should be processed, False otherwise
    """
    name = path.name
    stem = path.stem

    # Must be .md file
    if path.suffix.lower() != '.md':
        return False

    # Skip quarantined files
    if name.startswith('_orchestrator-skip'):
        return False

    # Skip terminal states
    if stem.endswith('_done') or stem.endswith('_failed') or stem.endswith('_paused'):
        return False

    return True


def _get_pending_plans(plans_dir: Path) -> List[Path]:
    """
    Get candidate plans sorted by mtime ascending, then filename ascending.

    .. deprecated::
        Use WatchController.get_pending_plans() instead.
        This function is kept for backwards compatibility.

    This provides deterministic oldest-first processing order.
    Handles race conditions where files may be deleted between glob() and stat().

    Args:
        plans_dir: Directory to scan for .md files

    Returns:
        List of Path objects sorted by (mtime, filename)
    """
    candidates = [p for p in plans_dir.glob('*.md') if _is_watch_candidate(p)]

    # Build list with mtime, handling race condition if file is deleted
    sortable = []
    for p in candidates:
        try:
            mtime = p.stat().st_mtime
            sortable.append((mtime, p.name, p))
        except FileNotFoundError:
            # File was deleted between glob() and stat() - skip it
            continue

    # Sort by (mtime, filename) and extract just the paths
    sortable.sort(key=lambda x: (x[0], x[1]))
    return [item[2] for item in sortable]


def _find_available_converted_path(original: Path) -> Path:
    """
    Find available path for converted file with collision handling.

    Tries <stem>_converted.md first, then <stem>_converted_2.md, etc.
    Raises RuntimeError if all 100 attempts fail.

    Args:
        original: Original plan file path

    Returns:
        Available path for converted file
    """
    base = original.parent / f"{original.stem}_converted.md"
    if not base.exists():
        return base

    for i in range(2, 101):
        candidate = original.parent / f"{original.stem}_converted_{i}.md"
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"Too many converted files for {original.name}")


def _strip_terminal_suffix(stem: str) -> str:
    """
    Strip terminal suffixes (_done, _failed, _paused) from a filename stem.

    This allows renaming feature_paused -> feature_done instead of
    feature_paused -> feature_paused_done.
    """
    for terminal in ('_done', '_failed', '_paused'):
        if stem.endswith(terminal):
            return stem[:-len(terminal)]
    return stem


def _rename_to_terminal(
    plan_path: Path,
    suffix: str,
    session_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> tuple:
    """
    Rename plan file to terminal state and update DB.

    .. deprecated::
        Use WatchController.rename_to_terminal() instead.
        This function is kept for backwards compatibility.

    If the file already has a terminal suffix (_done, _failed, _paused),
    it is replaced rather than appended. For example:
    - feature.md + _done -> feature_done.md
    - feature_paused.md + _done -> feature_done.md (replaces _paused)

    Args:
        plan_path: Path to the plan file
        suffix: Terminal suffix ('_done', '_failed', '_paused')
        session_id: Optional session ID to update in DB
        db_path: Optional database path

    Returns:
        Tuple of (success, new_path_or_error_message)
    """
    # Strip any existing terminal suffix before adding new one
    base_stem = _strip_terminal_suffix(plan_path.stem)
    new_name = f"{base_stem}{suffix}{plan_path.suffix}"
    new_path = plan_path.parent / new_name

    try:
        plan_path.rename(new_path)

        # Update DB so resume/export find the file
        if session_id:
            db.update_session(session_id, {'plan_path': str(new_path)}, db_path)

        return True, str(new_path)
    except OSError as e:
        return False, str(e)


@cli.command()
@click.argument('plans_dir', type=click.Path(exists=True, file_okay=False))
@click.option('--poll-interval', default=2, type=int, help='Poll interval in seconds (default: 2)')
@click.option('--convert/--no-convert', 'auto_convert', default=False, help='Auto-convert invalid plans (default: disabled)')
@click.option('--db-path', '-d', help='Custom database path')
@click.option('--planner-model', '-pm', help='Model for planner agent')
@click.option('--executor-model', '-em', help='Model for executor agent')
@click.option('--auto-commit/--no-auto-commit', default=False, help='Auto-commit on completion')
@click.option('--smart-commit/--no-smart-commit', default=None, help='Use AI commit messages')
@click.option('--telegram/--no-telegram', default=None, help='Enable Telegram notifications')
@click.option('--show-activity/--no-activity', default=True, help='Show streaming activity indicator')
@click.option('--mcp-config', type=click.Path(exists=True), help='Path to MCP configuration file for all watched sessions')
@click.option('--headless', is_flag=True, default=False, help='Run Playwright MCP browser in headless mode')
@click.option('--tui/--no-tui', default=False, help='Launch Textual TUI dashboard')
@click.option('--verbose', '-v', is_flag=True, default=False, help='TUI: use expanded layout with dual agent panels (default: compact)')
def watch(
    plans_dir: str,
    poll_interval: int,
    auto_convert: bool,
    db_path: Optional[str],
    planner_model: Optional[str],
    executor_model: Optional[str],
    auto_commit: bool,
    smart_commit: Optional[bool],
    telegram: Optional[bool],
    show_activity: bool,
    mcp_config: Optional[str],
    headless: bool,
    tui: bool,
    verbose: bool,
):
    """Watch a directory for new plan files and execute them.

    Monitors PLANS_DIR for new .md files, processes them oldest-first,
    auto-converts if needed, and renames to terminal state on completion.

    File naming conventions:
    - _orchestrator-skip__* : Quarantined (ignored)
    - *_done.md : Completed successfully
    - *_failed.md : Failed execution
    - *_paused.md : Paused on blocker (queue halted)

    Examples:
        orchestrator watch ./plans/
        orchestrator watch ./plans/ --poll-interval 5
        orchestrator watch ./plans/ --no-convert
        orchestrator watch ./plans/ --auto-commit
        orchestrator watch ./plans/ --tui
        orchestrator watch ./plans/ --tui --verbose
    """
    # Handle TUI mode
    if tui:
        _start_watch_tui(
            plans_dir=plans_dir,
            verbose=verbose,
            poll_interval=poll_interval,
            auto_convert=auto_convert,
            db_path=db_path,
            planner_model=planner_model,
            executor_model=executor_model,
            auto_commit=auto_commit,
            smart_commit=smart_commit,
            telegram=telegram,
            show_activity=show_activity,
            mcp_config=mcp_config,
            headless=headless,
        )
        return

    # Non-TUI mode: use WatchController for strict parity with TUI
    from .controllers.watch_controller import WatchController

    plans_path = Path(plans_dir).resolve()

    # Initialize database
    db.init_db(db_path)

    # Create telegram notifier if enabled
    telegram_notifier = None
    if telegram:
        telegram_notifier = _create_telegram_notifier(telegram)

    # Create event handler with auto_commit context
    def on_event(event: WatchEvent, data: dict) -> None:
        _handle_watch_event(event, data, auto_commit=auto_commit)

    # Create and run WatchController
    # Always pass output_callback for Click-based output routing
    # show_activity separately controls the streaming indicator (spinner/dots)
    controller = WatchController(
        plans_dir=plans_path,
        db_path=db_path,
        poll_interval=poll_interval,
        auto_convert=auto_convert,
        on_event=on_event,
        on_output=output_callback,
        planner_model=planner_model,
        executor_model=executor_model,
        auto_commit=auto_commit,
        smart_commit=smart_commit,
        telegram_notifier=telegram_notifier,
        show_activity=show_activity,
        mcp_config_path=mcp_config,
        headless=headless,
    )

    # Setup signal handlers for graceful shutdown
    def handle_shutdown(signum, frame):
        click.echo()
        click.secho("✓ Watch mode stopping...", fg="yellow")
        controller.stop()

    original_sigint = signal.signal(signal.SIGINT, handle_shutdown)
    original_sigterm = signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        controller.run()
    finally:
        # Restore signal handlers
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)


def _quarantine_and_convert(plan_path: Path, auto_convert: bool) -> Optional[Path]:
    """
    Quarantine invalid plan and create converted copy if enabled.

    .. deprecated::
        Use WatchController.quarantine_and_convert() instead.
        This function is kept for backwards compatibility.

    Args:
        plan_path: Path to the invalid plan
        auto_convert: Whether to attempt conversion

    Returns:
        Path to converted file, or None if conversion failed/disabled
    """
    from .convert import convert_plan, ConversionError

    content = plan_path.read_text()

    if not auto_convert:
        # Just quarantine, no conversion
        quarantine_path = plan_path.parent / f"_orchestrator-skip__{plan_path.name}"
        plan_path.rename(quarantine_path)
        return None

    try:
        converted_content, metadata = convert_plan(content)
    except ConversionError:
        # Conversion failed - quarantine original, no converted file
        quarantine_path = plan_path.parent / f"_orchestrator-skip__{plan_path.name}"
        plan_path.rename(quarantine_path)
        return None
    except Exception:
        # Unexpected error - quarantine original
        quarantine_path = plan_path.parent / f"_orchestrator-skip__{plan_path.name}"
        plan_path.rename(quarantine_path)
        return None

    # Find available converted path
    converted_path = _find_available_converted_path(plan_path)

    # Write converted content
    converted_path.write_text(converted_content)

    # Quarantine original
    quarantine_path = plan_path.parent / f"_orchestrator-skip__{plan_path.name}"
    plan_path.rename(quarantine_path)

    return converted_path


def _process_watch_file(
    plan_path: Path,
    auto_convert: bool,
    db_path: Optional[str],
    planner_model: Optional[str],
    executor_model: Optional[str],
    auto_commit: bool,
    smart_commit: Optional[bool],
    telegram: Optional[bool],
    show_activity: bool,
    mcp_config: Optional[str] = None,
    headless: bool = False,
) -> WatchResult:
    """
    Process a single plan file in watch mode.

    .. deprecated::
        Use WatchController._process_file() instead.
        This function is kept for backwards compatibility.

    Validates the plan, converts if needed, and runs the orchestrator.

    Args:
        plan_path: Path to the plan file
        auto_convert: Whether to auto-convert invalid plans
        db_path: Database path
        planner_model: Model for planner
        executor_model: Model for executor
        auto_commit: Auto-commit on completion
        smart_commit: Use AI commit messages
        telegram: Enable Telegram notifications
        mcp_config: Path to MCP configuration file
        headless: Whether to run browsers in headless mode
        show_activity: Show streaming activity

    Returns:
        WatchResult with status and details
    """
    from .convert import validate_plan_content
    from .parser import parse_plan_file

    # Validate the plan
    content = plan_path.read_text()
    is_valid, details = validate_plan_content(content)

    executed_path = plan_path

    if not is_valid:
        click.echo(f"  Plan needs conversion: {details.get('error', 'No milestones found')}")

        if auto_convert:
            converted_path = _quarantine_and_convert(plan_path, auto_convert)
            if converted_path:
                click.secho(f"  ✓ Converted: {converted_path.name}", fg="green")
                executed_path = converted_path
            else:
                return WatchResult(
                    status='conversion_failed',
                    error="Could not convert plan to valid format",
                )
        else:
            # Quarantine without conversion
            _quarantine_and_convert(plan_path, auto_convert=False)
            return WatchResult(
                status='skipped',
                error="Plan invalid and --no-convert specified",
            )

    # Parse plan for feature extraction
    parse_result = parse_plan_file(str(executed_path))
    if not parse_result.get('valid'):
        return WatchResult(
            status='skipped',
            error=f"Parse error: {parse_result.get('error')}",
        )

    feature = parse_result.get('feature') or executed_path.stem

    # Resolve models
    resolved_planner = get_planner_model(planner_model)
    resolved_executor = get_executor_model(executor_model)

    # Create Telegram notifier if enabled
    telegram_notifier = _create_telegram_notifier(telegram)

    # Create and run orchestrator
    try:
        orch = Orchestrator(
            feature_description=feature,
            db_path=db_path,
            on_output=output_callback if show_activity else None,
            show_activity=show_activity,
            planner_model=resolved_planner,
            executor_model=resolved_executor,
            plan_path=str(executed_path),
            telegram_notifier=telegram_notifier,
            mcp_config_path=mcp_config,
            headless=headless,
        )

        orch.start()

        # Check final state
        final_status = orch.get_status()
        final_phase = final_status.get('phase')
        final_state = final_status.get('status')

        if final_phase == Phase.COMPLETED and final_state == Status.COMPLETED:
            # Handle auto-commit
            if auto_commit:
                click.echo()
                click.secho("Creating commit...", fg="cyan")
                milestones = db.get_milestones(orch.session_id, db_path)
                success, msg = _do_smart_auto_commit(
                    feature_description=feature,
                    milestones=milestones,
                    smart_commit_flag=smart_commit,
                    executor_model=resolved_executor,
                )
                if success:
                    click.secho(f"✓ {msg}", fg="green")
                else:
                    click.secho(f"⚠ Commit: {msg}", fg="yellow")

            return WatchResult(
                status='completed',
                session_id=orch.session_id,
                executed_path=executed_path,
            )

        elif final_phase == Phase.PAUSED or final_state == Status.PAUSED:
            return WatchResult(
                status='paused',
                session_id=orch.session_id,
                executed_path=executed_path,
            )

        elif final_state == Status.FAILED:
            return WatchResult(
                status='failed',
                session_id=orch.session_id,
                executed_path=executed_path,
                error="Workflow failed",
            )

        else:
            # Unexpected state
            return WatchResult(
                status='failed',
                session_id=orch.session_id,
                executed_path=executed_path,
                error=f"Unexpected state: {final_phase}/{final_state}",
            )

    except Exception as e:
        return WatchResult(
            status='failed',
            executed_path=executed_path,
            error=str(e),
        )


@cli.command('test-playwright')
@click.argument('role', type=click.Choice(['planner', 'executor', 'both']))
@click.option('--test-url', required=True, help='URL to the test website (e.g., http://localhost:<PORT>/)')
@click.option('--mcp-config', type=click.Path(exists=True), help='Path to MCP configuration file')
@click.option('--out-dir', type=click.Path(), help='Directory to write artifacts')
@click.option('--timeout', default=120, type=int, help='Overall timeout in seconds (default: 120)')
@click.option('--model', help='Override model for test agent')
@click.option('--verbose', '-v', is_flag=True, help='Print full agent response')
def test_playwright(
    role: str,
    test_url: str,
    mcp_config: Optional[str],
    out_dir: Optional[str],
    timeout: int,
    model: Optional[str],
    verbose: bool,
):
    """Verify Playwright MCP tool integration for agents.

    Tests that the specified agent role(s) can access and use Playwright MCP tools.
    Validates success by checking for screenshot artifact creation.

    Prerequisites:
    - Playwright MCP server configured in .mcp.json
    - Test site running at --test-url
    - npx @anthropic/mcp-server-playwright available

    Examples:
        # Test planner agent
        orchestrator test-playwright planner --test-url http://localhost:<PORT>/

        # Test executor agent
        orchestrator test-playwright executor --test-url http://localhost:<PORT>/

        # Test both agents sequentially
        orchestrator test-playwright both --test-url http://localhost:<PORT>/

        # With custom MCP config
        orchestrator test-playwright planner --test-url http://localhost:<PORT>/ --mcp-config ./custom.mcp.json
    """
    from .playwright_test import (
        run_playwright_test,
        run_playwright_test_both,
    )

    out_path = Path(out_dir) if out_dir else None

    click.echo()
    click.secho("=" * 60, bold=True)
    click.secho("  MCP PLAYWRIGHT VERIFICATION", bold=True)
    click.secho("=" * 60, bold=True)
    click.echo()
    click.echo(f"  Role(s): {role}")
    click.echo(f"  Test URL: {test_url}")
    if mcp_config:
        click.echo(f"  MCP Config: {mcp_config}")
    else:
        click.echo(f"  MCP Config: auto-discover (.mcp.json)")
    if model:
        click.echo(f"  Model: {model}")
    click.echo()

    if role == 'both':
        all_passed, results, actual_out_dir = run_playwright_test_both(
            test_url=test_url,
            mcp_config_path=mcp_config,
            out_dir=out_path,
            timeout=timeout,
            model=model,
            verbose=verbose,
        )

        click.secho("-" * 60, dim=True)
        click.secho("Results:", bold=True)
        click.echo()

        for agent_role, (success, msg) in results.items():
            if success:
                click.echo(f"  {click.style('✓', fg='green')} {agent_role}: {msg}")
            else:
                click.echo(f"  {click.style('✗', fg='red')} {agent_role}: {msg}")

        click.echo()
        click.echo(f"  Artifacts: {actual_out_dir}")
        click.echo()

        if all_passed:
            click.secho("PASS", fg="green", bold=True)
            sys.exit(0)
        else:
            click.secho("FAIL", fg="red", bold=True)
            sys.exit(1)

    else:
        success, msg, actual_out_dir = run_playwright_test(
            role=role,
            test_url=test_url,
            mcp_config_path=mcp_config,
            out_dir=out_path,
            timeout=timeout,
            model=model,
            verbose=verbose,
        )

        click.secho("-" * 60, dim=True)
        click.secho("Result:", bold=True)
        click.echo()

        if success:
            click.echo(f"  {click.style('✓', fg='green')} {role}: {msg}")
        else:
            click.echo(f"  {click.style('✗', fg='red')} {role}: {msg}")

        click.echo()
        click.echo(f"  Artifacts: {actual_out_dir}")
        click.echo()

        if success:
            click.secho("PASS", fg="green", bold=True)
            sys.exit(0)
        else:
            click.secho("FAIL", fg="red", bold=True)
            sys.exit(1)


@cli.command()
@click.argument('file', type=click.Path(exists=True))
@click.option('--dry-run', is_flag=True, help='Preview tasks without executing')
@click.option('-m', '--model', default='sonnet', help='Model: opus, sonnet, haiku (default: sonnet)')
@click.option('--timeout', default=300, type=int, help='Per-task timeout in seconds (default: 300)')
@click.option('--retry-failed', is_flag=True, help='Retry tasks marked [!]')
@click.option('--results', type=click.Path(), help='Write detailed results to file')
@click.option('-v', '--verbose', is_flag=True, help='Show full agent responses')
@click.option('--mcp-config', type=click.Path(exists=True), help='MCP config file')
@click.option('--tui', is_flag=True, help='Run in TUI (Text User Interface) mode')
def todo(
    file: str,
    dry_run: bool,
    model: str,
    timeout: int,
    retry_failed: bool,
    results: Optional[str],
    verbose: bool,
    mcp_config: Optional[str],
    tui: bool,
):
    """Execute tasks from a markdown checkbox file.

    Each task runs with fresh agent context (no accumulated state).
    This is ideal for batch processing independent tasks without
    hitting token limits.

    \b
    Task File Format (only dash bullets supported):
        - [ ] Pending task to execute
        - [x] Already done (skipped)
        - [!] Previously failed (use --retry-failed)

    Note: Only '-' bullets are supported. '*', '+', and numbered lists
    are not recognized as tasks.

    \b
    Multi-line tasks (indent continuation lines):
        - [ ] Analyze this file
              Look for performance issues
              Check for memory leaks

    \b
    File context injection (use @path):
        - [ ] Review @src/auth.py for security issues

    Note: @path only supports relative paths within the task file's
    directory. Absolute paths and '../' escapes are rejected for security.
    Symlinks pointing outside the task directory are also rejected.

    \b
    Completion Tags:
        Agent MUST output [TASK_DONE] or [TASK_FAILED] tags.
        Tasks without completion tags are marked as failed.

    \b
    Examples:
        orchestrator todo tasks.md
        orchestrator todo tasks.md --dry-run
        orchestrator todo tasks.md --model haiku
        orchestrator todo tasks.md --retry-failed
        orchestrator todo tasks.md --results report.md
        orchestrator todo tasks.md --tui
    """
    from .todo_parser import parse_task_file, TaskStatus
    from .todo import TodoRunner
    from .config import load_mcp_config_raw, expand_env_vars

    file_path = Path(file)
    task_file = parse_task_file(file_path)

    # Handle TUI mode FIRST (before any click.echo() calls)
    if tui:
        from .tui.todo_app import TodoTUI

        # Load MCP config if provided
        mcp_servers = None
        if mcp_config:
            raw_config, _, _ = load_mcp_config_raw(mcp_config)
            if raw_config:
                mcp_servers = expand_env_vars(raw_config)

        # Create and run TUI app
        app = TodoTUI(
            task_file=task_file,
            model=model,
            timeout=timeout,
            retry_failed=retry_failed,
            results_file=results,
            verbose=verbose,
            mcp_config=mcp_servers,
            dry_run=dry_run,
        )
        app.run()
        return

    # Show summary
    total = len(task_file.tasks)
    pending = task_file.pending_count
    failed = task_file.failed_count
    done = task_file.done_count

    click.echo()
    click.secho("=" * 60, bold=True)
    click.secho("  ORCHESTRATOR TODO", bold=True)
    click.secho("=" * 60, bold=True)
    click.echo()
    click.echo(f"  File: {file}")
    click.echo(f"  Model: {model}")
    click.echo(f"  Timeout: {timeout}s per task")
    click.echo()
    click.echo(f"  Tasks: {total} total")
    click.echo(f"    [ ] Pending: {pending}")
    click.echo(f"    [x] Done: {done}")
    click.echo(f"    [!] Failed: {failed}")
    click.echo()

    # Check if there's work to do
    actionable = pending + (failed if retry_failed else 0)
    if actionable == 0:
        click.secho("No tasks to process.", fg="yellow")
        if failed > 0 and not retry_failed:
            click.echo(f"  Tip: Use --retry-failed to retry {failed} failed task(s)")
        return

    if dry_run:
        click.secho(f"[DRY RUN] Would process {actionable} task(s):", fg="cyan")
        click.echo()

        # List the tasks that would be processed
        from .todo_parser import get_actionable_tasks as get_tasks
        tasks_to_run = get_tasks(task_file, retry_failed=retry_failed)
        for i, task in enumerate(tasks_to_run, 1):
            status_marker = "[!]" if task.status == TaskStatus.FAILED else "[ ]"
            task_preview = task.first_line
            if len(task_preview) > 60:
                task_preview = task_preview[:57] + "..."
            click.echo(f"  {i}. {status_marker} {task_preview}")

        click.echo()
        return

    click.echo(f"Processing {actionable} task(s)...")
    click.echo()

    # Load MCP config if provided
    mcp_servers = None
    if mcp_config:
        raw_config, _, _ = load_mcp_config_raw(mcp_config)
        if raw_config:
            mcp_servers = expand_env_vars(raw_config)

    # Callbacks for progress display
    def on_task_start(index: int, total: int, task):
        # Truncate long task names
        task_name = task.first_line
        if len(task_name) > 55:
            task_name = task_name[:52] + "..."
        click.echo(f"[{index}/{total}] {task_name}")

    def on_task_complete(result):
        if result.status == TaskStatus.DONE:
            click.echo(f"      {click.style('✓', fg='green')} Done ({result.duration:.1f}s)")
            if result.result:
                # Truncate long results
                result_text = result.result
                if len(result_text) > 60:
                    result_text = result_text[:57] + "..."
                click.echo(f"      → {result_text}")
        else:
            click.echo(f"      {click.style('✗', fg='red')} Failed ({result.duration:.1f}s)")
            if result.error:
                click.echo(f"      → {result.error}")
            elif result.result:
                click.echo(f"      → {result.result}")
        click.echo()

    # Run tasks
    runner = TodoRunner(
        model=model,
        timeout=timeout,
        verbose=verbose,
        mcp_config=mcp_servers,
        on_task_start=on_task_start,
        on_task_complete=on_task_complete,
    )

    try:
        task_results = runner.run_all(
            task_file,
            retry_failed=retry_failed,
            dry_run=dry_run,
        )
    except KeyboardInterrupt:
        click.echo()
        click.secho("Interrupted. Progress has been saved.", fg="yellow")
        return

    # Summary
    completed = sum(1 for r in task_results if r.status == TaskStatus.DONE)
    failed_count = sum(1 for r in task_results if r.status == TaskStatus.FAILED)

    click.secho("-" * 60, dim=True)
    click.secho("Summary:", bold=True)
    click.echo(f"  {click.style('✓', fg='green')} Completed: {completed}")
    click.echo(f"  {click.style('✗', fg='red')} Failed: {failed_count}")
    if failed_count > 0:
        click.echo(f"    (marked [!] in file, use --retry-failed to retry)")
    click.echo()

    # Write results file if requested
    if results and task_results:
        results_path = Path(results)
        with results_path.open('w') as f:
            f.write(f"# Task Results\n\n")
            f.write(f"- Source: {file}\n")
            f.write(f"- Model: {model}\n")
            f.write(f"- Completed: {completed}\n")
            f.write(f"- Failed: {failed_count}\n\n")

            for r in task_results:
                status_emoji = "✓" if r.status == TaskStatus.DONE else "✗"
                f.write(f"## {status_emoji} {r.task.first_line}\n\n")
                f.write(f"- **Status:** {r.status.value}\n")
                f.write(f"- **Duration:** {r.duration:.1f}s\n")
                if r.result:
                    f.write(f"- **Result:** {r.result}\n")
                if r.error:
                    f.write(f"- **Error:** {r.error}\n")
                f.write("\n")

        click.echo(f"Results written to: {results}")


@cli.command('helper')
@click.argument('question', nargs=-1, required=True)
@click.option('-m', '--model', default='haiku', help='Model: opus, sonnet, haiku (default: haiku)')
@click.option('-v', '--verbose', is_flag=True, help='Show included documentation files')
def helper(question: tuple, model: str, verbose: bool):
    """Ask questions about orchestrator-auto (AI-powered).

    Examples:
        orchestrator helper "how do I use queue mode?"
        orchestrator helper how do I resume a session
        orchestrator helper "what models are available?" -m sonnet
    """
    from .resources import load_docs
    from .config import resolve_model
    from .agents import create_chat_agent
    from .auth import detect_auth

    # Check auth before running
    auth_info = detect_auth()
    if not auth_info.is_configured:
        click.secho("✗ No authentication detected", fg='red')
        click.echo("  Set ANTHROPIC_API_KEY or run 'claude setup-token'")
        click.echo("  Note: macOS Keychain credentials cannot be detected")
        return

    # Load bundled documentation
    docs_content, included_files = load_docs()

    if verbose:
        click.secho(f"Including: {', '.join(included_files)}", fg='blue')
        click.echo()

    # Join question parts for unquoted questions
    question_text = " ".join(question)

    # Resolve model alias to full model ID
    full_model = resolve_model(model)

    # Construct prompt with guardrails
    system_prompt = """You are a helpful assistant answering questions about orchestrator-auto.

Answer the user's question using ONLY the documentation provided below.
If the answer is not found in the documentation, say so clearly and suggest
where the user might look (e.g., --help, GitHub issues, or the docs/ folder).

<documentation>
{docs_content}
</documentation>""".format(docs_content=docs_content)

    # Create agent with no tools (docs-only safety)
    agent = create_chat_agent(
        model=full_model,
        system_prompt=system_prompt,
        allowed_tools=[],
    )

    # Send question and get response
    try:
        response = agent.send_message(question_text)
        click.echo(response)
    except Exception as e:
        click.secho(f"Error: {e}", fg='red')


if __name__ == '__main__':
    cli()
