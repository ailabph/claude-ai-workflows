"""Tests for planner_auto.git_utils.discover_repo_root() and the
--repo-root CLI flag on the start command."""

import json
import os
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from planner_auto.cli import cli
from planner_auto.db import get_session_config, init_schema, open_db
from planner_auto.git_utils import discover_repo_root


# ---------------------------------------------------------------------------
# discover_repo_root() unit tests
# ---------------------------------------------------------------------------

class TestDiscoverRepoRoot:
    def test_returns_repo_root_inside_git_repo(self, tmp_path):
        """discover_repo_root must return the repo root when cwd is a git repo."""
        # Initialise a real git repo in a temp directory.
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        result = discover_repo_root(cwd=str(tmp_path))
        # On macOS, /var is a symlink to /private/var; resolve for comparison.
        assert result is not None
        assert os.path.isabs(result)

    def test_returns_none_outside_git_repo(self, tmp_path):
        """discover_repo_root must return None when cwd is not in a git repo.

        We use a truly isolated temp directory that cannot be inside any repo.
        """
        # Create a subdirectory isolated from any parent git repo by using
        # a mock so we don't depend on the test runner's environment.
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="not a git repo")
            result = discover_repo_root(cwd=str(tmp_path))
        assert result is None

    def test_returns_none_when_git_not_installed(self, tmp_path):
        """discover_repo_root must return None if git is not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            result = discover_repo_root(cwd=str(tmp_path))
        assert result is None

    def test_returns_none_on_timeout(self, tmp_path):
        """discover_repo_root must return None on subprocess timeout."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5)):
            result = discover_repo_root(cwd=str(tmp_path))
        assert result is None

    def test_uses_cwd_none_by_default(self):
        """Calling discover_repo_root() without args passes cwd=None to subprocess."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="/some/repo\n")
            result = discover_repo_root()
        assert result == "/some/repo"
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] is None


# ---------------------------------------------------------------------------
# --repo-root CLI flag on the start command
# ---------------------------------------------------------------------------

class TestStartCommandRepoRoot:
    def _make_runner_and_db(self, tmp_path):
        runner = CliRunner()
        db_path = str(tmp_path / "test.db")
        return runner, db_path

    def test_repo_root_flag_stored_in_config(self, tmp_path):
        """--repo-root must be stored as repo_root in the session config JSON."""
        runner, db_path = self._make_runner_and_db(tmp_path)
        fake_root = str(tmp_path / "myrepo")

        result = runner.invoke(
            cli,
            ["--db-path", db_path, "start", "--project", "test-proj",
             "--repo-root", fake_root],
        )
        assert result.exit_code == 0, result.output

        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        # Find the session that was created.
        session = conn.execute(
            "SELECT id FROM sessions ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        config_row = get_session_config(conn, session["id"])
        config = json.loads(config_row["config_json"])
        conn.close()

        # The flag value should be stored as an absolute path.
        assert "repo_root" in config
        assert os.path.isabs(config["repo_root"])
        # The stored path must match the provided value (resolved to abs).
        assert config["repo_root"] == os.path.abspath(fake_root)

    def test_repo_root_auto_detected_when_flag_absent(self, tmp_path):
        """When --repo-root is not provided, auto-detection is attempted."""
        runner, db_path = self._make_runner_and_db(tmp_path)
        fake_root = "/detected/repo"

        with patch("planner_auto.cli.discover_repo_root", return_value=fake_root):
            result = runner.invoke(
                cli,
                ["--db-path", db_path, "start", "--project", "auto-proj"],
            )

        assert result.exit_code == 0, result.output

        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        session = conn.execute(
            "SELECT id FROM sessions ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        config_row = get_session_config(conn, session["id"])
        config = json.loads(config_row["config_json"])
        conn.close()

        assert config.get("repo_root") == fake_root

    def test_repo_root_null_when_not_in_git_repo(self, tmp_path):
        """When git discovery returns None, repo_root must be None in config."""
        runner, db_path = self._make_runner_and_db(tmp_path)

        with patch("planner_auto.cli.discover_repo_root", return_value=None):
            result = runner.invoke(
                cli,
                ["--db-path", db_path, "start", "--project", "no-git-proj"],
            )

        assert result.exit_code == 0, result.output

        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        session = conn.execute(
            "SELECT id FROM sessions ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        config_row = get_session_config(conn, session["id"])
        config = json.loads(config_row["config_json"])
        conn.close()

        assert config.get("repo_root") is None
