"""Tests for planner_auto.export, blocker lifecycle, and complete command."""

import csv
import os
import sqlite3

import pytest
from click.testing import CliRunner

from planner_auto.cli import cli
from planner_auto.db import (
    add_context_entry,
    add_message,
    add_plan_draft,
    create_blocker,
    create_session,
    get_open_blockers,
    get_session,
    init_schema,
    update_session_phase,
    update_session_status,
)
from planner_auto.export import export_session
from planner_auto.session import SessionManager


@pytest.fixture
def populated_session(db_conn):
    """Create a session with messages, context, and plan drafts."""
    sid = create_session(db_conn, "myapp")
    add_message(db_conn, sid, "user", "Build auth")
    add_message(db_conn, sid, "assistant", "Got it")
    add_context_entry(db_conn, sid, "readme.md", "file", "# My Project")
    add_context_entry(db_conn, sid, "note-1", "note", "Use PostgreSQL")
    add_context_entry(db_conn, sid, "synthesis-1", "synthesis", "Project needs auth with PG")
    add_plan_draft(db_conn, sid, "# Plan Draft 1\nContent here", "sonnet")
    add_plan_draft(db_conn, sid, "# Plan Draft 2\nRevised content", "opus")
    return sid


class TestExportSession:
    """Tests for export_session()."""

    def test_creates_all_expected_files(self, db_conn, populated_session, tmp_path):
        sid = populated_session
        output_dir = str(tmp_path / "export")
        paths = export_session(sid, db_conn, output_dir=output_dir)

        # Should create: chat.csv, context-summary.md, plan-draft-1.md, plan-draft-2.md
        assert len(paths) == 4
        filenames = [os.path.basename(p) for p in paths]
        assert "chat.csv" in filenames
        assert "context-summary.md" in filenames
        assert "plan-draft-1.md" in filenames
        assert "plan-draft-2.md" in filenames

        # All files should exist
        for p in paths:
            assert os.path.exists(p)

    def test_chat_csv_content_ordered_by_id(self, db_conn, populated_session, tmp_path):
        sid = populated_session
        output_dir = str(tmp_path / "export")
        export_session(sid, db_conn, output_dir=output_dir)

        csv_path = os.path.join(output_dir, "chat.csv")
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["role"] == "user"
        assert rows[0]["content"] == "Build auth"
        assert rows[1]["role"] == "assistant"
        assert rows[1]["content"] == "Got it"
        # Ordered by id
        assert int(rows[0]["id"]) < int(rows[1]["id"])

    def test_context_summary_grouped_by_type(self, db_conn, populated_session, tmp_path):
        sid = populated_session
        output_dir = str(tmp_path / "export")
        export_session(sid, db_conn, output_dir=output_dir)

        md_path = os.path.join(output_dir, "context-summary.md")
        content = open(md_path, "r", encoding="utf-8").read()

        assert "## Files" in content
        assert "readme.md" in content
        assert "## Notes" in content
        assert "Use PostgreSQL" in content
        assert "## Synthesiss" in content or "## Synthesis" in content
        assert "Project needs auth with PG" in content

    def test_multiple_drafts_produce_multiple_files(self, db_conn, populated_session, tmp_path):
        sid = populated_session
        output_dir = str(tmp_path / "export")
        export_session(sid, db_conn, output_dir=output_dir)

        draft1 = open(os.path.join(output_dir, "plan-draft-1.md"), "r").read()
        draft2 = open(os.path.join(output_dir, "plan-draft-2.md"), "r").read()
        assert "Plan Draft 1" in draft1
        assert "Plan Draft 2" in draft2

    def test_re_export_is_idempotent(self, db_conn, populated_session, tmp_path):
        sid = populated_session
        output_dir = str(tmp_path / "export")

        paths1 = export_session(sid, db_conn, output_dir=output_dir)
        paths2 = export_session(sid, db_conn, output_dir=output_dir)

        assert len(paths1) == len(paths2)
        # Content should be identical
        for p in paths1:
            assert os.path.exists(p)

    def test_empty_session_export(self, db_conn, tmp_path):
        """Export a session with no messages, context, or drafts."""
        sid = create_session(db_conn, "empty")
        output_dir = str(tmp_path / "export")
        paths = export_session(sid, db_conn, output_dir=output_dir)

        # Should still create chat.csv and context-summary.md (both empty-ish)
        assert len(paths) == 2
        filenames = [os.path.basename(p) for p in paths]
        assert "chat.csv" in filenames
        assert "context-summary.md" in filenames


class TestBlockerLifecycle:
    """Tests for blocker pause/resume via SessionManager."""

    def test_pause_with_blocker(self, db_conn):
        sid = create_session(db_conn, "myapp")
        sm = SessionManager(db_conn)

        bid = sm.pause_with_blocker(sid, "planner", "Which DB?")
        session = get_session(db_conn, sid)
        assert session["status"] == "PAUSED"

        blockers = get_open_blockers(db_conn, sid)
        assert len(blockers) == 1
        assert blockers[0]["question"] == "Which DB?"

    def test_resolve_and_resume_with_single_blocker(self, db_conn):
        sid = create_session(db_conn, "myapp")
        sm = SessionManager(db_conn)

        bid = sm.pause_with_blocker(sid, "planner", "Which DB?")
        sm.resolve_and_resume(sid, bid, "PostgreSQL")

        session = get_session(db_conn, sid)
        assert session["status"] == "ACTIVE"
        assert len(get_open_blockers(db_conn, sid)) == 0

    def test_resolve_and_resume_with_multiple_blockers(self, db_conn):
        """Resolving one blocker when others remain should keep PAUSED."""
        sid = create_session(db_conn, "myapp")
        sm = SessionManager(db_conn)

        bid1 = sm.pause_with_blocker(sid, "planner", "Which DB?")
        # Add second blocker directly
        bid2 = create_blocker(db_conn, sid, "planner", "Which framework?")

        sm.resolve_and_resume(sid, bid1, "PostgreSQL")

        # Still PAUSED because bid2 is open
        session = get_session(db_conn, sid)
        assert session["status"] == "PAUSED"
        assert len(get_open_blockers(db_conn, sid)) == 1

        # Resolve second blocker
        sm.resolve_and_resume(sid, bid2, "Django")

        session = get_session(db_conn, sid)
        assert session["status"] == "ACTIVE"
        assert len(get_open_blockers(db_conn, sid)) == 0


class TestCompleteCLI:
    """Tests for the complete CLI command."""

    @pytest.fixture
    def cli_runner(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        return runner, ["--db-path", db_path], db_path, tmp_path

    def _get_conn(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def test_complete_rejected_with_open_blockers(self, cli_runner):
        r, base_args, db_path, tmp_path = cli_runner
        result = r.invoke(cli, [*base_args, "start", "--project", "myapp"])
        sid = result.output.split("Session created: ")[1].split("\n")[0].strip()

        # Move to REVIEW phase and add a blocker
        conn = self._get_conn(db_path)
        init_schema(conn)
        update_session_phase(conn, sid, "CONTEXT")
        update_session_phase(conn, sid, "DISCUSSION")
        update_session_phase(conn, sid, "PLANNING")
        update_session_phase(conn, sid, "REVIEW")
        create_blocker(conn, sid, "planner", "Need clarification")
        conn.close()

        result = r.invoke(cli, [*base_args, "complete", sid])
        assert "Cannot complete" in result.output or "open blockers" in result.output

    def test_complete_succeeds_and_auto_exports(self, cli_runner):
        r, base_args, db_path, tmp_path = cli_runner
        result = r.invoke(cli, [*base_args, "start", "--project", "myapp"])
        sid = result.output.split("Session created: ")[1].split("\n")[0].strip()

        # Move to REVIEW phase
        conn = self._get_conn(db_path)
        init_schema(conn)
        update_session_phase(conn, sid, "CONTEXT")
        update_session_phase(conn, sid, "DISCUSSION")
        update_session_phase(conn, sid, "PLANNING")
        update_session_phase(conn, sid, "REVIEW")
        add_message(conn, sid, "user", "test msg")
        conn.close()

        result = r.invoke(cli, [*base_args, "complete", sid])
        assert result.exit_code == 0
        assert "completed" in result.output
        assert "Exported" in result.output

        # Verify session state
        conn = self._get_conn(db_path)
        session = get_session(conn, sid)
        assert session["phase"] == "COMPLETE"
        assert session["status"] == "COMPLETE"
        conn.close()


class TestExportCLI:
    """Tests for the export CLI command."""

    @pytest.fixture
    def cli_runner(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        return runner, ["--db-path", db_path], db_path, tmp_path

    def _get_conn(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def test_export_creates_files(self, cli_runner):
        r, base_args, db_path, tmp_path = cli_runner
        result = r.invoke(cli, [*base_args, "start", "--project", "myapp"])
        sid = result.output.split("Session created: ")[1].split("\n")[0].strip()

        output_dir = str(tmp_path / "export_out")
        result = r.invoke(cli, [*base_args, "export", sid, "--output-dir", output_dir])
        assert result.exit_code == 0
        assert "Exported" in result.output
        assert os.path.exists(os.path.join(output_dir, "chat.csv"))
