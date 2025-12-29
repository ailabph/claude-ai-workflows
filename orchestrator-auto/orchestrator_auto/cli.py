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
from .parser import extract_feature_from_plan, parse_plan_file
from .config import (
    get_planner_model,
    get_executor_model,
    get_model_display_name,
    get_telegram_config,
    is_telegram_configured,
    get_stuck_sessions_config,
    get_project_identity,
)


# Global reference to orchestrator for signal handling
_current_orchestrator: Optional[Orchestrator] = None


def handle_interrupt(signum, frame):
    """Handle Ctrl+C gracefully."""
    click.echo("\n")
    click.secho("⚠️  Workflow interrupted by user", fg="yellow")

    if _current_orchestrator:
        click.echo("Saving current state...")
        try:
            _current_orchestrator._cleanup()
            click.secho("✓ State saved successfully", fg="green")
        except Exception as e:
            click.secho(f"✗ Error saving state: {e}", fg="red")

    click.echo("Exiting...")
    sys.exit(0)


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
    )


def _run_queue(
    project_id: str,
    db_path: Optional[str],
    show_activity: bool,
    planner_model: Optional[str],
    executor_model: Optional[str],
    auto_commit: bool,
    telegram: Optional[bool],
) -> None:
    """
    Run queued plans sequentially with crash recovery and fail-forward behavior.
    """
    global _current_orchestrator

    # Resolve model names
    resolved_planner = get_planner_model(planner_model)
    resolved_executor = get_executor_model(executor_model)

    # Setup Telegram notifier if configured
    telegram_notifier = None
    if telegram is not False:
        telegram_notifier = _create_telegram_notifier(telegram)

    # Check for stuck sessions
    _check_stuck_sessions(telegram_notifier, db_path)

    click.echo()
    click.secho("Starting queue runner...", fg="cyan", bold=True)

    # Telegram: Queue started notification
    if telegram_notifier:
        all_items = db.list_queue_items(project_id, db_path, include_completed=False)
        telegram_notifier.notify_queue_started(len(all_items))

    completed_count = 0
    failed_count = 0
    paused_count = 0

    while True:
        # Get next pending item
        next_item = db.get_next_queue_item(project_id, db_path)

        if not next_item:
            # No more pending items
            break

        item_id = next_item["id"]
        plan_path = next_item["plan_path"]
        feature_desc = next_item["feature_description"]
        position = next_item["position"] + 1

        click.echo()
        click.secho(f"=" * 60, fg="cyan")
        click.secho(f"Queue Item {position}: {Path(plan_path).name}", fg="cyan", bold=True)
        click.secho(f"Feature: {feature_desc}", fg="cyan")
        click.secho(f"=" * 60, fg="cyan")
        click.echo()

        # Telegram: Item start notification
        if telegram_notifier:
            telegram_notifier.notify_queue_item_started(position, feature_desc)

        try:
            # Mark as running
            db.update_queue_item(
                item_id,
                db_path,
                status="running",
                started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

            # Create orchestrator for this plan
            orch = Orchestrator(
                feature_description=feature_desc,
                db_path=db_path,
                plan_path=plan_path,
                on_output=output_callback,
                show_activity=show_activity,
                planner_model=resolved_planner,
                executor_model=resolved_executor,
                telegram_notifier=telegram_notifier,
            )
            _current_orchestrator = orch

            # Store session_id on queue item
            db.update_queue_item(item_id, db_path, session_id=orch.session_id)

            click.secho(f"✓ Session created: {orch.session_id}", fg="green")
            click.echo()

            # Run the workflow
            orch.start()

            # Check final status
            final_phase = orch.state.phase
            final_status = orch.state.status

            click.echo()
            click.secho(f"Workflow ended: phase={final_phase}, status={final_status}", fg="yellow")

            if final_phase == Phase.COMPLETED:
                # Mark queue item as completed
                db.update_queue_item(
                    item_id,
                    db_path,
                    status="completed",
                    completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                completed_count += 1

                click.secho(f"✓ Queue item {position} completed", fg="green", bold=True)

                # Telegram: Item completed
                if telegram_notifier:
                    telegram_notifier.notify_queue_item_completed(position, feature_desc)

                # Auto-commit if enabled
                if auto_commit:
                    click.echo()
                    click.secho("Creating auto-commit...", fg="cyan")
                    milestones = db.get_milestones(orch.session_id, db_path)
                    success, msg = git.auto_commit(feature_desc, milestones)
                    if success:
                        click.secho("✓ Changes committed", fg="green")
                        click.echo(f"  {msg.split(chr(10))[0]}")
                    else:
                        click.secho(f"⚠ Auto-commit skipped: {msg}", fg="yellow")

            elif final_phase == Phase.PAUSED or final_status == Status.PAUSED:
                # Mark queue item as paused - queue halts
                db.update_queue_item(item_id, db_path, status="paused")
                paused_count += 1

                click.secho(f"⏸ Queue item {position} paused (blocker)", fg="yellow", bold=True)
                click.secho("Queue halted. Use 'orchestrator resume <session-id>' to continue.", fg="yellow")

                # Telegram: Item paused
                if telegram_notifier:
                    telegram_notifier.notify_queue_item_paused(position, feature_desc, orch.session_id)

                # Stop queue runner
                break

            else:
                # Failed or other terminal state - fail forward
                error_msg = f"Workflow ended in unexpected state: {final_phase}/{final_status}"
                db.update_queue_item(
                    item_id,
                    db_path,
                    status="failed",
                    error_message=error_msg,
                    completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                failed_count += 1

                click.secho(f"✗ Queue item {position} failed", fg="red", bold=True)
                click.secho(f"  Error: {error_msg}", fg="red")
                click.secho("  Continuing to next item (fail-forward)...", fg="yellow")

                # Telegram: Item failed
                if telegram_notifier:
                    telegram_notifier.notify_queue_item_failed(position, feature_desc, error_msg)

        except KeyboardInterrupt:
            # User interrupted - mark as paused
            click.echo()
            click.secho("⚠ Queue interrupted by user", fg="yellow")
            db.update_queue_item(item_id, db_path, status="paused")
            paused_count += 1

            # Telegram: Queue interrupted
            if telegram_notifier:
                telegram_notifier.notify_queue_interrupted(position, feature_desc)

            # Stop queue runner
            raise

        except Exception as e:
            # Workflow error - fail forward
            error_msg = str(e)
            db.update_queue_item(
                item_id,
                db_path,
                status="failed",
                error_message=error_msg,
                completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            failed_count += 1

            click.secho(f"✗ Queue item {position} failed with exception", fg="red", bold=True)
            click.secho(f"  Error: {error_msg}", fg="red")
            click.secho("  Continuing to next item (fail-forward)...", fg="yellow")

            # Telegram: Item failed
            if telegram_notifier:
                telegram_notifier.notify_queue_item_failed(position, feature_desc, error_msg)

        finally:
            if _current_orchestrator:
                _current_orchestrator._cleanup()
                _current_orchestrator = None

    # Queue complete - show summary
    click.echo()
    click.secho("=" * 60, fg="cyan")
    click.secho("Queue Complete", fg="cyan", bold=True)
    click.secho("=" * 60, fg="cyan")
    click.echo()
    click.echo(f"Completed: {click.style(str(completed_count), fg='green', bold=True)}")
    click.echo(f"Failed:    {click.style(str(failed_count), fg='red', bold=True)}")
    click.echo(f"Paused:    {click.style(str(paused_count), fg='yellow', bold=True)}")

    # Telegram: Queue complete summary
    if telegram_notifier:
        telegram_notifier.notify_queue_completed(completed_count, failed_count, paused_count)


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
@click.option('--feature', '-f', required=False, help='Feature description (required unless --queue or --plan is provided)')
@click.option('--db-path', '-d', help='Custom database path')
@click.option('--plan', '-p', type=click.Path(exists=True), help='Path to existing plan file (skips discovery/planning)')
@click.option('--queue', is_flag=True, help='Queue mode: run multiple plans sequentially')
@click.option('--queue-reset', is_flag=True, help='Reset existing queue for this project')
@click.argument('queue_plans', nargs=-1, type=click.Path(exists=True))
@click.option('--show-activity/--no-activity', default=True, help='Show streaming activity indicator (default: enabled)')
@click.option('--planner-model', '-pm', help='Model for planner agent. Aliases: opus, sonnet, haiku')
@click.option('--executor-model', '-em', help='Model for executor agent. Aliases: opus, sonnet, haiku')
@click.option('--auto-commit/--no-auto-commit', default=False, help='Auto-commit changes on workflow completion (default: disabled)')
@click.option('--telegram/--no-telegram', default=None, help='Enable/disable Telegram notifications (default: auto from config)')
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
    telegram: Optional[bool],
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
    if not queue and not plan and not feature:
        raise click.UsageError("--feature/-f is required unless --queue or --plan is provided.")

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
        )
        return

    # Non-queue mode (original behavior)
    # Resolve model names (CLI > config > defaults)
    resolved_planner = get_planner_model(planner_model)
    resolved_executor = get_executor_model(executor_model)

    # Setup Telegram notifier if configured
    telegram_notifier = None
    if telegram is not False:  # Not explicitly disabled
        telegram_notifier = _create_telegram_notifier(telegram)

    try:
        click.secho("Starting new workflow session...", fg="cyan", bold=True)
        click.echo(f"Feature: {feature}")
        click.echo(f"Models: Planner={get_model_display_name(resolved_planner)} | Executor={get_model_display_name(resolved_executor)}")
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
            success, msg = git.auto_commit(feature, milestones)
            if success:
                click.secho("✓ Changes committed", fg="green")
                click.echo(f"  {msg.split(chr(10))[0]}")  # First line of output
            else:
                click.secho(f"⚠ Auto-commit skipped: {msg}", fg="yellow")

    except KeyboardInterrupt:
        # Handled by signal handler
        pass
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red", bold=True)
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
def resume(session_id: str, answer: Optional[str], db_path: Optional[str], show_activity: bool, telegram: Optional[bool], force: bool):
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
                    auto_commit=False,  # Don't auto-commit on resume continuation
                    telegram=telegram,
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
                    auto_commit=False,
                    telegram=telegram,
                )
        else:
            # Not part of a queue - just complete normally
            click.secho("✓ Workflow completed!", fg="green", bold=True)

    except KeyboardInterrupt:
        # Handled by signal handler
        pass
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
                    auto_commit=False,
                    telegram=telegram,
                )
        except Exception:
            # If we can't handle queue continuation, just show the original error
            pass

        click.secho(f"✗ Error: {e}", fg="red", bold=True)
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
def respond(session_id: str, answer: str, db_path: Optional[str], telegram: Optional[bool]):
    """Respond to a blocker and continue workflow."""
    try:
        click.secho(f"Responding to session: {session_id}", fg="cyan", bold=True)
        click.echo()

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

        click.echo(f"Question: {blockers[0]['question']}")
        click.echo(f"Answer: {answer}")
        click.echo()

        # Resume with answer (will call resume command internally)
        ctx = click.get_current_context()
        ctx.invoke(resume, session_id=session_id, answer=answer, db_path=db_path, telegram=telegram)

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
def export(session_id: str, output: Optional[str], db_path: Optional[str]):
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


if __name__ == '__main__':
    cli()
