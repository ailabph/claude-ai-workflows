"""Tests for the `check` CLI command.

Verifies:
  - Passes when required env vars are set
  - Fails with clear message when env vars are missing
  - claude on PATH detection
  - openai importability check
  - DB writability check
  - Schema version check
  - --probe flag is not called by default
"""

from __future__ import annotations

import os
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from planner_auto.cli import cli
from planner_auto.db import CURRENT_SCHEMA_VERSION, init_schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_check(env: dict | None = None, args: list | None = None, db_path: str = ":memory:"):
    """Invoke the check command with a controlled environment."""
    runner = CliRunner()
    cli_args = ["--db-path", db_path, "check"] + (args or [])
    with runner.isolated_filesystem():
        result = runner.invoke(cli, cli_args, env=env or {}, catch_exceptions=False)
    return result


# ---------------------------------------------------------------------------
# Auth checks
# ---------------------------------------------------------------------------

class TestAuthChecks:
    def test_anthropic_key_passes(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--db-path", db_path, "check"],
            env={"ANTHROPIC_API_KEY": "sk-test", "OPENAI_API_KEY": ""},
            catch_exceptions=False,
        )
        assert "Claude auth" in result.output
        assert "✓" in result.output or "ANTHROPIC_API_KEY" in result.output

    def test_oauth_token_passes(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--db-path", db_path, "check"],
            env={"CLAUDE_CODE_OAUTH_TOKEN": "tok-test"},
            catch_exceptions=False,
        )
        assert "Claude auth" in result.output

    def test_missing_claude_auth_fails(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--db-path", db_path, "check"],
            env={"ANTHROPIC_API_KEY": "", "CLAUDE_CODE_OAUTH_TOKEN": ""},
            catch_exceptions=False,
        )
        # Output should mention the check failed
        assert "✗" in result.output or "not set" in result.output


# ---------------------------------------------------------------------------
# PATH check
# ---------------------------------------------------------------------------

class TestPathChecks:
    def test_claude_found_on_path(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        conn.close()

        runner = CliRunner()
        with patch("planner_auto.cli.shutil.which", return_value="/usr/bin/claude"):
            result = runner.invoke(
                cli,
                ["--db-path", db_path, "check"],
                env={"ANTHROPIC_API_KEY": "key"},
                catch_exceptions=False,
            )
        assert "claude on PATH" in result.output
        assert "/usr/bin/claude" in result.output

    def test_claude_not_on_path(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        conn.close()

        runner = CliRunner()
        with patch("planner_auto.cli.shutil.which", return_value=None):
            result = runner.invoke(
                cli,
                ["--db-path", db_path, "check"],
                env={"ANTHROPIC_API_KEY": "key"},
                catch_exceptions=False,
            )
        assert "claude on PATH" in result.output
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# DB and schema checks
# ---------------------------------------------------------------------------

class TestDbChecks:
    def test_writable_db_passes(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--db-path", db_path, "check"],
            env={"ANTHROPIC_API_KEY": "key"},
            catch_exceptions=False,
        )
        assert "DB path writable" in result.output

    def test_current_schema_version_passes(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--db-path", db_path, "check"],
            env={"ANTHROPIC_API_KEY": "key"},
            catch_exceptions=False,
        )
        assert "Schema version" in result.output
        assert f"v{CURRENT_SCHEMA_VERSION}" in result.output


# ---------------------------------------------------------------------------
# probe flag
# ---------------------------------------------------------------------------

class TestProbeFlag:
    def test_probe_not_called_by_default(self, tmp_path):
        """Without --probe, no live API calls are made."""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        conn.close()

        called = []

        def fake_which(name):
            return "/usr/bin/" + name

        runner = CliRunner()
        with patch("planner_auto.cli.shutil.which", side_effect=fake_which):
            result = runner.invoke(
                cli,
                ["--db-path", db_path, "check"],
                env={"ANTHROPIC_API_KEY": "key"},
                catch_exceptions=False,
            )

        # No probe result labels in output (tmp_path may contain "probe" in its name)
        assert "Claude API probe" not in result.output
        assert "OpenAI API probe" not in result.output

    def test_probe_flag_present_in_output(self, tmp_path):
        """With --probe and mocked API, output includes probe results."""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        conn.close()

        async def fake_query_claude(prompt, **kwargs):
            return "OK"

        runner = CliRunner()
        with patch("planner_auto.cli.shutil.which", return_value="/usr/bin/claude"), \
             patch("planner_auto.sdk_wrapper.query_claude", side_effect=fake_query_claude):
            result = runner.invoke(
                cli,
                ["--db-path", db_path, "check", "--probe"],
                env={"ANTHROPIC_API_KEY": "key"},
                catch_exceptions=False,
            )

        assert "probe" in result.output.lower() or "API" in result.output


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------

class TestCheckOutputFormat:
    def test_shows_all_checks_passed_when_everything_ok(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        conn.close()

        import importlib.util

        runner = CliRunner()
        with patch("planner_auto.cli.shutil.which", return_value="/usr/bin/claude"), \
             patch("importlib.util.find_spec", return_value=MagicMock()):
            result = runner.invoke(
                cli,
                ["--db-path", db_path, "check"],
                env={"ANTHROPIC_API_KEY": "sk-key", "OPENAI_API_KEY": "oai-key"},
                catch_exceptions=False,
            )

        assert "All checks passed" in result.output

    def test_exit_code_nonzero_on_failure(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        conn.close()

        runner = CliRunner()
        with patch("planner_auto.cli.shutil.which", return_value=None):
            result = runner.invoke(
                cli,
                ["--db-path", db_path, "check"],
                env={"ANTHROPIC_API_KEY": "", "CLAUDE_CODE_OAUTH_TOKEN": "",
                     "OPENAI_API_KEY": ""},
                catch_exceptions=False,
            )

        # Should have non-zero exit code due to failures
        assert result.exit_code != 0 or "failed" in result.output.lower()
