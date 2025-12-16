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
from .engine import Orchestrator
from .state import Phase, Status
from .config import (
    get_planner_model,
    get_executor_model,
    get_model_display_name,
    get_telegram_config,
    is_telegram_configured,
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


@click.group()
def cli():
    """Orchestrator Auto - Automated two-agent workflow."""
    pass


@cli.command()
@click.option('--feature', '-f', required=True, help='Feature description')
@click.option('--db-path', '-d', help='Custom database path')
@click.option('--plan', '-p', type=click.Path(exists=True), help='Path to existing plan file (skips discovery/planning)')
@click.option('--show-activity/--no-activity', default=True, help='Show streaming activity indicator (default: enabled)')
@click.option('--planner-model', '-pm', help='Model for planner agent. Aliases: opus, sonnet, haiku')
@click.option('--executor-model', '-em', help='Model for executor agent. Aliases: opus, sonnet, haiku')
@click.option('--auto-commit/--no-auto-commit', default=False, help='Auto-commit changes on workflow completion (default: disabled)')
@click.option('--telegram/--no-telegram', default=None, help='Enable/disable Telegram notifications (default: auto from config)')
def start(
    feature: str,
    db_path: Optional[str],
    plan: Optional[str],
    show_activity: bool,
    planner_model: Optional[str],
    executor_model: Optional[str],
    auto_commit: bool,
    telegram: Optional[bool],
):
    """Start a new workflow session."""
    global _current_orchestrator

    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, handle_interrupt)

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

        # Initialize database
        db.init_db(db_path)

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
def resume(session_id: str, answer: Optional[str], db_path: Optional[str], show_activity: bool, telegram: Optional[bool]):
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
        click.echo()

        # Initialize database
        db.init_db(db_path)

        # Check if session exists
        session = db.get_session(session_id, db_path)
        if not session:
            click.secho(f"✗ Session '{session_id}' not found", fg="red")
            sys.exit(1)

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

        # If paused, check for answer
        if session['status'] == Status.PAUSED:
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
        orch.resume(answer=answer)

        # Show final status
        click.echo()
        show_progress(orch)
        click.secho("✓ Workflow completed!", fg="green", bold=True)

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


@cli.command("list")
@click.option('--status', '-s', help='Filter by status (active, paused, completed, failed)')
@click.option('--db-path', '-d', help='Custom database path')
def list_sessions(status: Optional[str], db_path: Optional[str]):
    """List all sessions."""
    try:
        # Initialize database
        db.init_db(db_path)

        # Get sessions
        sessions = db.list_sessions(db_path, status=status)

        if not sessions:
            click.echo("No sessions found.")
            return

        click.echo()
        click.secho(f"Found {len(sessions)} session(s):", fg="cyan", bold=True)
        click.echo()

        for session in sessions:
            # Format session info
            session_id = click.style(session['id'], fg='cyan', bold=True)
            phase = format_phase(session['phase'])
            status_str = format_status(session['status'])

            click.echo(f"  {session_id}")
            click.echo(f"    Feature: {session['feature_description']}")
            click.echo(f"    Phase: {phase}  Status: {status_str}")

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


if __name__ == '__main__':
    cli()
