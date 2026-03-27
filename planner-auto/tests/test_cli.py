"""Tests for planner_auto.cli using Click's CliRunner."""

import json
import sqlite3

import pytest
from click.testing import CliRunner

from planner_auto.cli import cli
from planner_auto.db import (
    create_blocker,
    create_session,
    get_session,
    get_session_config,
    init_schema,
    update_session_status,
    add_message,
    add_context_entry,
    add_plan_draft,
)


@pytest.fixture
def runner(tmp_path):
    """Provide a CliRunner with a temp database."""
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    return runner, ["--db-path", db_path], db_path


def _get_conn(db_path):
    """Open a test connection to the same DB."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


class TestStartCommand:
    """Tests for the 'start' command."""

    def test_start_creates_session(self, runner):
        r, base_args, db_path = runner
        result = r.invoke(cli, [*base_args, "start", "--project", "myapp"])
        assert result.exit_code == 0
        assert "Session created:" in result.output
        assert "myapp" in result.output

        # Verify in DB
        conn = _get_conn(db_path)
        init_schema(conn)
        rows = conn.execute("SELECT * FROM sessions").fetchall()
        assert len(rows) == 1
        assert rows[0]["project"] == "myapp"
        assert rows[0]["phase"] == "SETUP"
        assert rows[0]["status"] == "ACTIVE"
        conn.close()

    def test_start_creates_config_snapshot(self, runner):
        r, base_args, db_path = runner
        result = r.invoke(cli, [*base_args, "start", "--project", "myapp"])
        assert result.exit_code == 0

        conn = _get_conn(db_path)
        init_schema(conn)
        # Extract session ID from output
        sid = result.output.split("Session created: ")[1].split("\n")[0].strip()
        cfg = get_session_config(conn, sid)
        assert cfg is not None
        data = json.loads(cfg["config_json"])
        assert data["project"] == "myapp"
        assert data["model_default"] == "claude-sonnet-4-6"
        conn.close()


class TestListCommand:
    """Tests for the 'list' command."""

    def test_list_shows_session(self, runner):
        r, base_args, db_path = runner
        r.invoke(cli, [*base_args, "start", "--project", "myapp"])
        result = r.invoke(cli, [*base_args, "list"])
        assert result.exit_code == 0
        assert "myapp" in result.output
        assert "SETUP" in result.output

    def test_list_empty(self, runner):
        r, base_args, db_path = runner
        result = r.invoke(cli, [*base_args, "list"])
        assert result.exit_code == 0
        assert "No sessions found" in result.output

    def test_list_with_status_filter(self, runner):
        r, base_args, db_path = runner
        r.invoke(cli, [*base_args, "start", "--project", "app1"])
        r.invoke(cli, [*base_args, "start", "--project", "app2"])

        # Mark one as COMPLETE via direct DB
        conn = _get_conn(db_path)
        init_schema(conn)
        rows = conn.execute("SELECT id FROM sessions").fetchall()
        conn.execute(
            "UPDATE sessions SET status = 'COMPLETE' WHERE id = ?",
            (rows[0]["id"],),
        )
        conn.commit()
        conn.close()

        result = r.invoke(cli, [*base_args, "list", "--status", "ACTIVE"])
        assert result.exit_code == 0
        # Only one session should remain ACTIVE
        lines = [l for l in result.output.strip().split("\n") if l and not l.startswith("ID") and not l.startswith("-")]
        assert len(lines) == 1


class TestStatusCommand:
    """Tests for the 'status' command."""

    def test_status_returns_correct_counts(self, runner):
        r, base_args, db_path = runner
        # Create session
        result = r.invoke(cli, [*base_args, "start", "--project", "myapp"])
        sid = result.output.split("Session created: ")[1].split("\n")[0].strip()

        # Add some data
        conn = _get_conn(db_path)
        init_schema(conn)
        add_message(conn, sid, "user", "Hello")
        add_message(conn, sid, "assistant", "Hi")
        add_context_entry(conn, sid, "readme", "file", "content")
        add_plan_draft(conn, sid, "Draft 1", "sonnet")
        create_blocker(conn, sid, "planner", "Which DB?")
        conn.close()

        result = r.invoke(cli, [*base_args, "status", sid])
        assert result.exit_code == 0
        assert "Messages:        2" in result.output
        assert "Context entries: 1" in result.output
        assert "Plan drafts:     1" in result.output
        assert "Open blockers:   1" in result.output
        assert "Which DB?" in result.output

    def test_status_not_found(self, runner):
        r, base_args, db_path = runner
        # Need to init the DB first
        r.invoke(cli, [*base_args, "list"])  # triggers init
        result = r.invoke(cli, [*base_args, "status", "nonexistent"])
        assert "Session not found" in result.output


class TestResumeCommand:
    """Tests for the 'resume' command."""

    def test_resume_invalid_id(self, runner):
        r, base_args, db_path = runner
        r.invoke(cli, [*base_args, "list"])  # init DB
        result = r.invoke(cli, [*base_args, "resume", "nonexistent"])
        assert "Session not found" in result.output

    def test_resume_complete_session_fails(self, runner):
        r, base_args, db_path = runner
        result = r.invoke(cli, [*base_args, "start", "--project", "myapp"])
        sid = result.output.split("Session created: ")[1].split("\n")[0].strip()

        conn = _get_conn(db_path)
        init_schema(conn)
        conn.execute("UPDATE sessions SET status = 'COMPLETE' WHERE id = ?", (sid,))
        conn.commit()
        conn.close()

        result = r.invoke(cli, [*base_args, "resume", sid])
        assert "Cannot resume" in result.output
        assert "COMPLETE" in result.output

    def test_resume_resolves_blockers(self, runner):
        r, base_args, db_path = runner
        result = r.invoke(cli, [*base_args, "start", "--project", "myapp"])
        sid = result.output.split("Session created: ")[1].split("\n")[0].strip()

        conn = _get_conn(db_path)
        init_schema(conn)
        update_session_status(conn, sid, "PAUSED")
        create_blocker(conn, sid, "planner", "Which DB?")
        conn.close()

        # Simulate user input for blocker answer
        result = r.invoke(cli, [*base_args, "resume", sid], input="PostgreSQL\n")
        assert result.exit_code == 0
        assert "Resolved" in result.output
        assert "resumed" in result.output

        # Verify blocker resolved and status is ACTIVE
        conn = _get_conn(db_path)
        session = get_session(conn, sid)
        assert session["status"] == "ACTIVE"
        blockers = conn.execute(
            "SELECT * FROM blockers WHERE session_id = ? AND status = 'open'",
            (sid,),
        ).fetchall()
        assert len(blockers) == 0
        conn.close()
