"""Click CLI interface for planner-auto."""

import asyncio
import json
import os
import sqlite3

import click

from planner_auto.db import (
    add_context_entry,
    create_session,
    get_all_plan_drafts,
    get_context_entries,
    get_latest_plan_draft,
    get_messages,
    get_open_blockers,
    get_review_by_round,
    get_session,
    get_session_config,
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
from planner_auto.export import export_review_artifacts, kafra_handoff
from planner_auto.git_utils import discover_repo_root
from planner_auto.logging import setup_session_logger
from planner_auto.loop.convergence import detect_complexity, get_max_rounds
from planner_auto.loop.engine import ReviewLoopEngine
from planner_auto.reviewer.direct_api import DirectAPIAdapter
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
@click.option(
    "--repo-root",
    default=None,
    help="Override repository root path (auto-detected from cwd if not provided).",
)
@click.pass_context
def start(ctx, project, verbose, debug, repo_root):
    """Start a new planning session."""
    conn = _get_conn(ctx)

    session_id = create_session(conn, project)

    # Resolve repo root: explicit flag takes precedence, then auto-detect.
    if repo_root is not None:
        resolved_repo_root = os.path.abspath(repo_root)
    else:
        resolved_repo_root = discover_repo_root()

    # Save initial config snapshot (includes repo_root for .kafra handoff)
    config = {
        "project": project,
        "model_default": "claude-sonnet-4-6",
        "repo_root": resolved_repo_root,
    }
    save_session_config(conn, session_id, json.dumps(config))
    conn.commit()

    # Set up session logger (creates log file)
    setup_session_logger(session_id, verbose=verbose, debug=debug)

    click.echo(f"Session created: {session_id}")
    click.echo(f"Project: {project}")
    click.echo(f"Phase: SETUP")
    click.echo(f"Status: ACTIVE")
    if resolved_repo_root:
        click.echo(f"Repo root: {resolved_repo_root}")


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
            conn.commit()
            click.echo("  Resolved.")

    # Set status back to ACTIVE
    if current_status == "PAUSED":
        update_session_status(conn, session_id, "ACTIVE")
        conn.commit()

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
    """Validate and store a file as context.

    Resolves the path to an absolute path so context entries are
    unambiguous regardless of the working directory at query time.
    """
    # Resolve to absolute path at add-context time.
    abs_path = os.path.abspath(file_path)

    if not os.path.exists(abs_path):
        click.echo(f"Error: File not found: {file_path}", err=True)
        ctx.exit(1)
        return

    file_size = os.path.getsize(abs_path)
    if file_size > MAX_FILE_SIZE:
        click.echo(
            f"Error: File too large ({file_size} bytes). Maximum is {MAX_FILE_SIZE} bytes (500KB).",
            err=True,
        )
        ctx.exit(1)
        return

    # Read and validate UTF-8
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        click.echo("Error: File is not valid UTF-8 (binary files are not supported).", err=True)
        ctx.exit(1)
        return

    # Use the absolute path as the key so it's unambiguous.
    key = abs_path
    add_context_entry(conn, session_id, key, "file", content)
    conn.commit()
    click.echo(f"Context added: file '{abs_path}' ({len(content)} chars)")


def _add_note_context(conn, session_id, note):
    """Store a note as context with auto-generated key."""
    from datetime import datetime

    key = f"note-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    add_context_entry(conn, session_id, key, "note", note)
    conn.commit()
    click.echo(f"Context added: note '{key}'")


@cli.command()
@click.argument("session_id")
@click.argument("message", required=False, default=None)
@click.option("--interactive", is_flag=True, default=False, help="Enter interactive discussion mode.")
@click.option("--done", is_flag=True, default=False, help="Advance to PLANNING after this message.")
@click.pass_context
def discuss(ctx, session_id, message, interactive, done):
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
        success = _discuss_single(ctx, conn, session_id, message, discuss_fn)
        if done and success:
            try:
                sm.advance_phase(session_id, Phase.PLANNING.value)
                click.echo("Phase advanced to PLANNING.")
            except Exception as e:
                click.echo(f"Error advancing phase: {e}", err=True)
        elif done and not success:
            click.echo("Warning: --done ignored because the discussion call failed.", err=True)
    else:
        click.echo("Error: Provide a message or use --interactive.", err=True)
        ctx.exit(1)


def _discuss_single(ctx, conn, session_id, message, discuss_fn):
    """Send a single discussion message. Returns True on success, False on failure."""
    try:
        response = asyncio.run(discuss_fn(session_id, message, conn))
        click.echo(f"\nAssistant: {response}")
        return True
    except SDKError as e:
        click.echo(f"Error: {e}", err=True)
        return False
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

    # Check command is allowed in current phase/status (catches PAUSED)
    sm = SessionManager(conn)
    try:
        sm.check_command(session_id, "complete")
    except CommandNotAllowedError as e:
        click.echo(f"Error: {e}", err=True)
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
    try:
        sm.advance_phase(session_id, Phase.COMPLETE.value)
    except Exception as e:
        click.echo(f"Error advancing phase: {e}", err=True)
        ctx.exit(1)
        return

    # Set status to COMPLETE
    update_session_status(conn, session_id, "COMPLETE")
    conn.commit()

    # Auto-export
    paths = export_session(session_id, conn)
    click.echo(f"Session {session_id} completed.")
    click.echo(f"Exported {len(paths)} file(s):")
    for p in paths:
        click.echo(f"  {p}")


@cli.command()
@click.argument("session_id")
@click.option("--fast", is_flag=True, default=False, help="Fast mode: 4 rounds, no history, basic prompt.")
@click.option("--max-rounds", default=None, type=int, help="Override maximum review rounds.")
@click.option("--no-review-history", is_flag=True, default=False, help="Disable review history context.")
@click.option("--reviewer-model", default="gpt-5.4", show_default=True, help="GPT model for review.")
@click.option("--reviewer-reasoning", default="high", show_default=True, help="Reasoning effort level.")
@click.option(
    "--complexity",
    "complexity_override",
    default=None,
    type=click.Choice(["standard", "complex"]),
    help="Override complexity detection.",
)
@click.option("--repo-root", default=None, help="Override repository root for .kafra handoff.")
@click.pass_context
def review(
    ctx,
    session_id,
    fast,
    max_rounds,
    no_review_history,
    reviewer_model,
    reviewer_reasoning,
    complexity_override,
    repo_root,
):
    """Run the GPT review loop for a planning session."""
    conn = _get_conn(ctx)

    session = get_session(conn, session_id)
    if session is None:
        click.echo(f"Error: Session not found: {session_id}", err=True)
        ctx.exit(1)
        return

    sm = SessionManager(conn)
    try:
        sm.check_command(session_id, "review")
    except CommandNotAllowedError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
        return

    # Advance PLANNING → REVIEW if needed.
    if session["phase"] == Phase.PLANNING.value:
        sm.advance_phase(session_id, Phase.REVIEW.value)
        click.echo("Phase advanced to REVIEW.")

    # Require a plan draft.
    draft = get_latest_plan_draft(conn, session_id)
    if draft is None:
        click.echo("Error: No plan draft found. Run 'generate' first.", err=True)
        ctx.exit(1)
        return
    current_plan = draft["content"]

    # Determine complexity and max rounds.
    complexity = complexity_override or detect_complexity(conn, session_id)
    if max_rounds is None:
        max_rounds = get_max_rounds(complexity, fast=fast)

    # Prompt mode: fast uses "basic", normal uses "keep_trim" (POC-proven default).
    prompt_mode = "basic" if fast else "keep_trim"
    review_history_enabled = not no_review_history
    validate_fb = True

    if fast:
        review_history_enabled = False
        validate_fb = False

    # Load existing config for project name and model default.
    base_config: dict = {}
    existing_config_row = get_session_config(conn, session_id)
    if existing_config_row:
        try:
            base_config = json.loads(existing_config_row["config_json"])
        except (json.JSONDecodeError, TypeError):
            pass

    # Resolve repo_root override (absolute path if provided).
    resolved_repo_root = os.path.abspath(repo_root) if repo_root is not None else base_config.get("repo_root")

    # Save extended config snapshot capturing all reviewer settings.
    review_config = {
        **base_config,
        "reviewer_model": reviewer_model,
        "reasoning_effort": reviewer_reasoning,
        "prompt_mode": prompt_mode,
        "review_history": review_history_enabled,
        "validate_feedback": validate_fb,
        "filter_severity": ["critical", "major"],
        "keep_trim": not fast,
        "fast_mode": fast,
        "complexity": complexity,
        "max_rounds": max_rounds,
        "mode": "fast" if fast else "standard",
        "repo_root": resolved_repo_root,
    }
    save_session_config(conn, session_id, json.dumps(review_config))
    conn.commit()

    # Build reviewer adapter.
    reviewer = DirectAPIAdapter(
        model=reviewer_model,
        reasoning_effort=reviewer_reasoning,
        prompt_mode=prompt_mode,
    )

    # agents.py stores the key as "model"; start command stores as "model_default".
    # Try both, preferring "model" (from generate_plan config).
    planner_model = base_config.get("model") or base_config.get("model_default", "claude-sonnet-4-6")

    engine_config: dict = {
        "validate_feedback": validate_fb,
        "filter_severity": ["critical", "major"],
        "review_history": review_history_enabled,
        "effort": "medium",       # POC-proven default for planner revision calls
        "thinking": True,         # POC-proven default for planner revision calls
        "max_turns": 0,           # unlimited for thinking mode
    }

    engine = ReviewLoopEngine(
        conn=conn,
        session_id=session_id,
        reviewer=reviewer,
        planner_model=planner_model,
        config=engine_config,
    )

    click.echo(
        f"Starting review loop (max_rounds={max_rounds}, complexity={complexity}, fast={fast})..."
    )

    try:
        result = asyncio.run(engine.run(current_plan, max_rounds=max_rounds))
    except Exception as exc:
        click.echo(f"Error during review loop: {exc}", err=True)
        ctx.exit(1)
        return

    click.echo(f"Loop complete. Stop reason: {result.stop_reason} (rounds={result.rounds})")

    if result.converged:
        # Advance REVIEW → COMPLETE.
        try:
            sm.advance_phase(session_id, Phase.COMPLETE.value)
        except Exception as exc:
            click.echo(f"Error advancing phase: {exc}", err=True)

        update_session_status(conn, session_id, "COMPLETE")
        conn.commit()

        # Export review artifacts.
        export_paths = export_review_artifacts(session_id, conn, fast_mode=fast)
        click.echo(f"Exported {len(export_paths)} artifact(s).")

        # .kafra handoff.
        project = base_config.get("project", session_id)
        kafra_path = kafra_handoff(
            session_id,
            conn,
            result.final_plan,
            project,
            repo_root=resolved_repo_root,
        )
        if kafra_path:
            click.echo(f".kafra handoff: {kafra_path}")

        click.echo(f"Session {session_id} completed.")

    else:
        # cap_with_criticals: pause with a blocker listing remaining criticals.
        blocker_q = "Review cap reached with critical issues remaining."
        final_review = get_review_by_round(conn, session_id, result.rounds)
        if final_review and final_review["issues_json"]:
            try:
                issues = json.loads(final_review["issues_json"])
                criticals = [
                    i.get("description", "")
                    for i in issues
                    if i.get("severity") == "critical"
                ]
                if criticals:
                    blocker_q = (
                        "Review cap reached. Critical issues remaining:\n"
                        + "\n".join(f"- {c}" for c in criticals)
                    )
            except (json.JSONDecodeError, TypeError):
                pass

        sm.pause_with_blocker(session_id, "reviewer", blocker_q)
        click.echo(f"Session paused. Blocker: {blocker_q[:120]}")
