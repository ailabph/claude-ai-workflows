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
from .engine import Orchestrator
from .state import Phase, Status


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

    if status['phase'] == Phase.EXECUTION or status['current_milestone'] > 0:
        milestone_text = f"[{status['current_milestone']}/{status['total_milestones']}]"
        click.echo(f"Milestone: {click.style(milestone_text, fg='magenta', bold=True)}")

    click.echo("=" * 60)
    click.echo()


def output_callback(message: str) -> None:
    """Callback for orchestrator output."""
    click.echo(message)


@click.group()
def cli():
    """Orchestrator Auto - Automated two-agent workflow."""
    pass


@cli.command()
@click.option('--feature', '-f', required=True, help='Feature description')
@click.option('--db-path', '-d', help='Custom database path')
@click.option('--plan', '-p', type=click.Path(exists=True), help='Path to existing plan file (skips discovery/planning)')
def start(feature: str, db_path: Optional[str], plan: Optional[str]):
    """Start a new workflow session."""
    global _current_orchestrator

    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, handle_interrupt)

    try:
        click.secho("Starting new workflow session...", fg="cyan", bold=True)
        click.echo(f"Feature: {feature}")
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
            on_output=output_callback
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
def resume(session_id: str, answer: Optional[str], db_path: Optional[str]):
    """Resume an existing session."""
    global _current_orchestrator

    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, handle_interrupt)

    try:
        click.secho(f"Resuming session: {session_id}", fg="cyan", bold=True)
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
            on_output=output_callback
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
def respond(session_id: str, answer: str, db_path: Optional[str]):
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
        ctx.invoke(resume, session_id=session_id, answer=answer, db_path=db_path)

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


if __name__ == '__main__':
    cli()
