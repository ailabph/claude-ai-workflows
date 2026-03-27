"""Click CLI interface for planner-auto."""

import asyncio
import json
import os
import sqlite3

import click

from planner_auto.db import (
    add_context_entry,
    create_session,
    get_context_entries,
    get_messages,
    get_open_blockers,
    get_all_plan_drafts,
    get_session,
    init_schema,
    open_db,
    resolve_blocker,
    save_session_config,
    update_session_status,
)
from planner_auto.errors import (
    CommandNotAllowedError,
    SDKError,
    SessionNotFoundError,
)
from planner_auto.logging import setup_session_logger
from planner_auto.session import SessionManager
from planner_auto.state import Phase


def _get_conn(ctx: click.Context) -> sqlite3.Connection:
    """Get or create a database connection from Click context."""
    if "conn" not in ctx.obj:
        conn = open_db(ctx.obj.get("db_path"))
        init_schema(conn)
        ctx.obj["conn"] = conn
    return ctx.obj["conn"]


@click.group()
@click.option("--db-path", default=None, envvar="PLANNER_AUTO_DB", help="Custom DB path.")
@click.pass_context
def cli(ctx, db_path):
    """Planner-auto: Interactive planning session manager."""
    ctx.ensure_object(dict)
    if db_path:
        ctx.obj["db_path"] = db_path


@cli.command()
@click.option("--project", required=True, help="Project name.")
@click.option("--verbose", is_flag=True, default=False, help="Verbose logging to stderr.")
@click.option("--debug", is_flag=True, default=False, help="Debug logging to stderr.")
@click.pass_context
def start(ctx, project, verbose, debug):
    """Start a new planning session."""
    conn = _get_conn(ctx)

    session_id = create_session(conn, project)

    # Save initial config snapshot
    config = {"project": project, "model_default": "claude-sonnet-4-6"}
    save_session_config(conn, session_id, json.dumps(config))

    # Set up session logger (creates log file)
    setup_session_logger(session_id, verbose=verbose, debug=debug)

    click.echo(f"Session created: {session_id}")
    click.echo(f"Project: {project}")
    click.echo(f"Phase: SETUP")
    click.echo(f"Status: ACTIVE")


@cli.command("list")
@click.option("--status", "status_filter", default=None, help="Filter by status (ACTIVE, PAUSED, COMPLETE, FAILED).")
@click.pass_context
def list_sessions(ctx, status_filter):
    """List all sessions."""
    conn = _get_conn(ctx)

    if status_filter:
        rows = conn.execute(
            "SELECT id, project, phase, status, created_at FROM sessions WHERE status = ? ORDER BY created_at DESC",
            (status_filter.upper(),),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, project, phase, status, created_at FROM sessions ORDER BY created_at DESC"
        ).fetchall()

    if not rows:
        click.echo("No sessions found.")
        return

    # Formatted table output
    click.echo(f"{'ID':<12} {'PROJECT':<20} {'PHASE':<14} {'STATUS':<10} {'CREATED'}")
    click.echo("-" * 78)
    for row in rows:
        click.echo(
            f"{row['id']:<12} {row['project']:<20} {row['phase']:<14} "
            f"{row['status']:<10} {row['created_at']}"
        )


@cli.command()
@click.argument("session_id")
@click.pass_context
def status(ctx, session_id):
    """Show detailed session status."""
    conn = _get_conn(ctx)

    session = get_session(conn, session_id)
    if session is None:
        click.echo(f"Error: Session not found: {session_id}", err=True)
        ctx.exit(1)
        return

    messages = get_messages(conn, session_id)
    context_entries = get_context_entries(conn, session_id)
    drafts = get_all_plan_drafts(conn, session_id)
    blockers = get_open_blockers(conn, session_id)

    click.echo("=" * 60)
    click.echo("SESSION STATUS")
    click.echo("=" * 60)
    click.echo(f"Session ID:      {session['id']}")
    click.echo(f"Project:         {session['project']}")
    click.echo(f"Phase:           {session['phase']}")
    click.echo(f"Status:          {session['status']}")
    click.echo(f"Created:         {session['created_at']}")
    click.echo(f"Updated:         {session['updated_at']}")
    click.echo(f"Messages:        {len(messages)}")
    click.echo(f"Context entries: {len(context_entries)}")
    click.echo(f"Plan drafts:     {len(drafts)}")
    click.echo(f"Open blockers:   {len(blockers)}")

    if blockers:
        click.echo("")
        click.echo("OPEN BLOCKERS:")
        for b in blockers:
            click.echo(f"  [{b['id']}] ({b['source']}) {b['question']}")


@cli.command()
@click.argument("session_id")
@click.pass_context
def resume(ctx, session_id):
    """Resume a paused or active session, resolving open blockers."""
    conn = _get_conn(ctx)

    session = get_session(conn, session_id)
    if session is None:
        click.echo(f"Error: Session not found: {session_id}", err=True)
        ctx.exit(1)
        return

    current_status = session["status"]
    if current_status not in ("ACTIVE", "PAUSED"):
        click.echo(
            f"Error: Cannot resume session with status '{current_status}'. "
            f"Only ACTIVE or PAUSED sessions can be resumed.",
            err=True,
        )
        ctx.exit(1)
        return

    blockers = get_open_blockers(conn, session_id)
    if blockers:
        click.echo(f"Resolving {len(blockers)} open blocker(s):")
        for b in blockers:
            click.echo(f"\n  Blocker [{b['id']}] ({b['source']}): {b['question']}")
            answer = click.prompt("  Your answer")
            resolve_blocker(conn, b["id"], answer)
            click.echo("  Resolved.")

    # Set status back to ACTIVE
    if current_status == "PAUSED":
        update_session_status(conn, session_id, "ACTIVE")

    session = get_session(conn, session_id)
    click.echo(f"\nSession {session_id} resumed.")
    click.echo(f"Phase: {session['phase']}")
    click.echo(f"Status: {session['status']}")


MAX_FILE_SIZE = 500 * 1024  # 500 KB


@cli.command("add-context")
@click.argument("session_id")
@click.option("--file", "file_path", type=click.Path(), default=None, help="Path to a file to add as context.")
@click.option("--note", default=None, help="Text note to add as context.")
@click.pass_context
def add_context(ctx, session_id, file_path, note):
    """Add a context entry (file or note) to a session."""
    conn = _get_conn(ctx)

    session = get_session(conn, session_id)
    if session is None:
        click.echo(f"Error: Session not found: {session_id}", err=True)
        ctx.exit(1)
        return

    # Check command permission
    sm = SessionManager(conn)
    try:
        sm.check_command(session_id, "add-context")
    except CommandNotAllowedError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
        return

    if file_path is None and note is None:
        click.echo("Error: Provide either --file or --note.", err=True)
        ctx.exit(1)
        return

    if file_path is not None and note is not None:
        click.echo("Error: Provide either --file or --note, not both.", err=True)
        ctx.exit(1)
        return

    if file_path is not None:
        _add_file_context(ctx, conn, session_id, file_path)
    else:
        _add_note_context(conn, session_id, note)

    # Advance phase to CONTEXT if currently in SETUP
    if session["phase"] == Phase.SETUP.value:
        sm.advance_phase(session_id, Phase.CONTEXT.value)
        click.echo("Phase advanced to CONTEXT.")


def _add_file_context(ctx, conn, session_id, file_path):
    """Validate and store a file as context."""
    import os

    if not os.path.exists(file_path):
        click.echo(f"Error: File not found: {file_path}", err=True)
        ctx.exit(1)
        return

    file_size = os.path.getsize(file_path)
    if file_size > MAX_FILE_SIZE:
        click.echo(
            f"Error: File too large ({file_size} bytes). Maximum is {MAX_FILE_SIZE} bytes (500KB).",
            err=True,
        )
        ctx.exit(1)
        return

    # Read and validate UTF-8
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        click.echo("Error: File is not valid UTF-8 (binary files are not supported).", err=True)
        ctx.exit(1)
        return

    key = os.path.basename(file_path)
    add_context_entry(conn, session_id, key, "file", content)
    click.echo(f"Context added: file '{key}' ({len(content)} chars)")


def _add_note_context(conn, session_id, note):
    """Store a note as context with auto-generated key."""
    from datetime import datetime

    key = f"note-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    add_context_entry(conn, session_id, key, "note", note)
    click.echo(f"Context added: note '{key}'")


@cli.command()
@click.argument("session_id")
@click.argument("message", required=False, default=None)
@click.option("--interactive", is_flag=True, default=False, help="Enter interactive discussion mode.")
@click.pass_context
def discuss(ctx, session_id, message, interactive):
    """Send a discussion message or enter interactive mode."""
    from planner_auto.agents import discuss as discuss_fn

    conn = _get_conn(ctx)

    session = get_session(conn, session_id)
    if session is None:
        click.echo(f"Error: Session not found: {session_id}", err=True)
        ctx.exit(1)
        return

    sm = SessionManager(conn)

    # Advance to DISCUSSION if in CONTEXT
    if session["phase"] == Phase.CONTEXT.value:
        sm.advance_phase(session_id, Phase.DISCUSSION.value)
        click.echo("Phase advanced to DISCUSSION.")

    if interactive:
        _discuss_interactive(ctx, conn, sm, session_id)
    elif message:
        _discuss_single(ctx, conn, session_id, message, discuss_fn)
    else:
        click.echo("Error: Provide a message or use --interactive.", err=True)
        ctx.exit(1)


def _discuss_single(ctx, conn, session_id, message, discuss_fn):
    """Send a single discussion message."""
    try:
        response = asyncio.run(discuss_fn(session_id, message, conn))
        click.echo(f"\nAssistant: {response}")
    except SDKError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo("Hint: Check your API key and network connection.", err=True)
    except CommandNotAllowedError as e:
        click.echo(f"Error: {e}", err=True)


def _discuss_interactive(ctx, conn, sm, session_id):
    """Enter interactive discussion mode with prompt_toolkit."""
    from planner_auto.agents import discuss as discuss_fn

    try:
        from prompt_toolkit import prompt as pt_prompt
    except ImportError:
        click.echo("Error: prompt_toolkit is required for interactive mode.", err=True)
        ctx.exit(1)
        return

    click.echo("Interactive discussion mode. Type '/done' to finish.\n")

    while True:
        try:
            user_input = pt_prompt("You: ")
        except (EOFError, KeyboardInterrupt):
            click.echo("\nExiting discussion.")
            break

        if user_input.strip() == "/done":
            # Advance to PLANNING
            try:
                sm.advance_phase(session_id, Phase.PLANNING.value)
                click.echo("Phase advanced to PLANNING.")
            except Exception as e:
                click.echo(f"Error advancing phase: {e}", err=True)
            break

        if not user_input.strip():
            continue

        try:
            response = asyncio.run(discuss_fn(session_id, user_input, conn))
            click.echo(f"\nAssistant: {response}\n")
        except SDKError as e:
            click.echo(f"SDK Error: {e}", err=True)
            click.echo("You can retry or type '/done' to exit.\n", err=True)
        except CommandNotAllowedError as e:
            click.echo(f"Error: {e}", err=True)


@cli.command()
@click.argument("session_id")
@click.option("--model", default="claude-sonnet-4-6", help="Model for plan generation.")
@click.pass_context
def generate(ctx, session_id, model):
    """Generate an implementation plan."""
    from planner_auto.agents import generate_plan
    from planner_auto.validation import validate_plan_format

    conn = _get_conn(ctx)

    session = get_session(conn, session_id)
    if session is None:
        click.echo(f"Error: Session not found: {session_id}", err=True)
        ctx.exit(1)
        return

    sm = SessionManager(conn)
    try:
        sm.check_command(session_id, "generate")
    except CommandNotAllowedError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
        return

    try:
        plan = asyncio.run(generate_plan(session_id, conn, model=model))
        click.echo("\n" + plan)

        # Validate format and print warnings
        warnings = validate_plan_format(plan)
        if warnings:
            click.echo("\nPlan format warnings:")
            for w in warnings:
                click.echo(f"  - {w}")
        else:
            click.echo("\nPlan format validation: OK")

    except SDKError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo("Hint: Check your API key and network connection.", err=True)


@cli.command("export")
@click.argument("session_id")
@click.option("--output-dir", default=None, help="Override output directory.")
@click.pass_context
def export_cmd(ctx, session_id, output_dir):
    """Export session artifacts to disk."""
    from planner_auto.export import export_session

    conn = _get_conn(ctx)

    session = get_session(conn, session_id)
    if session is None:
        click.echo(f"Error: Session not found: {session_id}", err=True)
        ctx.exit(1)
        return

    paths = export_session(session_id, conn, output_dir=output_dir)
    click.echo(f"Exported {len(paths)} file(s):")
    for p in paths:
        click.echo(f"  {p}")


@cli.command()
@click.argument("session_id")
@click.pass_context
def complete(ctx, session_id):
    """Complete a session — checks blockers, advances phase, auto-exports."""
    from planner_auto.export import export_session

    conn = _get_conn(ctx)

    session = get_session(conn, session_id)
    if session is None:
        click.echo(f"Error: Session not found: {session_id}", err=True)
        ctx.exit(1)
        return

    # Check for open blockers
    blockers = get_open_blockers(conn, session_id)
    if blockers:
        click.echo("Error: Cannot complete session with open blockers:", err=True)
        for b in blockers:
            click.echo(f"  [{b['id']}] ({b['source']}) {b['question']}", err=True)
        ctx.exit(1)
        return

    # Advance phase to COMPLETE
    sm = SessionManager(conn)
    try:
        sm.advance_phase(session_id, Phase.COMPLETE.value)
    except Exception as e:
        click.echo(f"Error advancing phase: {e}", err=True)
        ctx.exit(1)
        return

    # Set status to COMPLETE
    update_session_status(conn, session_id, "COMPLETE")

    # Auto-export
    paths = export_session(session_id, conn)
    click.echo(f"Session {session_id} completed.")
    click.echo(f"Exported {len(paths)} file(s):")
    for p in paths:
        click.echo(f"  {p}")
