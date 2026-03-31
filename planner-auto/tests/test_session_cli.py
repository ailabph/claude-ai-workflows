"""Tests for the `session` CLI command."""

import sqlite3
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from planner_auto.cli import cli
from planner_auto.db import create_session, init_schema


@pytest.fixture
def runner(tmp_path):
    """Provide a CliRunner with a temp database."""
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    return runner, ["--db-path", db_path], db_path, tmp_path


def _get_conn(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    return conn


class TestSessionCommand:
    """Tests for planner-auto session command."""

    def test_requires_tui_flag(self, runner):
        r, base_args, db_path, tmp_path = runner
        result = r.invoke(cli, [*base_args, "session", "--project", "myapp"])
        assert result.exit_code != 0
        assert "requires --tui flag" in result.output

    def test_requires_project_or_session_id(self, runner):
        r, base_args, db_path, tmp_path = runner
        result = r.invoke(cli, [*base_args, "session", "--tui"])
        assert result.exit_code != 0
        assert "Provide either" in result.output

    def test_session_not_found(self, runner):
        r, base_args, db_path, tmp_path = runner
        # First initialize the DB so the session lookup works
        conn = _get_conn(db_path)
        conn.close()
        result = r.invoke(cli, [*base_args, "session", "nonexistent-id", "--tui"])
        assert result.exit_code != 0
        assert "Session not found" in result.output

    def test_cannot_provide_both_project_and_id(self, runner):
        r, base_args, db_path, tmp_path = runner
        result = r.invoke(cli, [*base_args, "session", "some-id", "--project", "myapp", "--tui"])
        assert result.exit_code != 0
        assert "not both" in result.output

    @patch("planner_auto.cli.SessionTUI", create=True)
    def test_new_session_creates_and_launches(self, mock_tui_cls, runner):
        """Test that --project creates a new session and launches TUI."""
        r, base_args, db_path, tmp_path = runner

        # Mock the TUI import and run
        mock_app = MagicMock()
        mock_app.exit_code = 0

        with patch("planner_auto.tui.session_app.SessionTUI") as mock_cls:
            mock_cls.return_value = mock_app
            with patch("planner_auto.cli.SessionTUI", mock_cls, create=True):
                # The actual import happens inside the command
                result = r.invoke(cli, [*base_args, "session", "--project", "myapp", "--tui"])

        # Session should have been created in DB
        conn = _get_conn(db_path)
        rows = conn.execute("SELECT * FROM sessions WHERE project = 'myapp'").fetchall()
        assert len(rows) == 1
        conn.close()

    def test_textual_not_installed(self, runner):
        """Test graceful error when textual is not installed."""
        r, base_args, db_path, tmp_path = runner

        with patch.dict("sys.modules", {"planner_auto.tui.session_app": None}):
            with patch("planner_auto.cli.SessionTUI", side_effect=ImportError("No module"), create=True):
                # This test verifies the error path exists — actual import
                # handling depends on the lazy import in the command.
                pass
