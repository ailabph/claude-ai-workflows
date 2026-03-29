"""Tests for --debug traceback printing on all session-aware commands.

Verifies:
  - SDKError with --debug prints full traceback to stderr
  - SDKError without --debug prints one-line message only (no traceback)
  - CommandNotAllowedError with --debug prints traceback
  - review loop Exception with --debug prints traceback
  - complete phase-advance Exception with --debug prints traceback
  - Traceback is absent when --debug is not passed
"""

from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from planner_auto.cli import cli
from planner_auto.db import (
    add_plan_draft,
    create_session,
    init_schema,
    save_session_config,
    update_session_phase,
)
from planner_auto.errors import SDKError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path) -> str:
    """Create a fresh test DB and return its path."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    conn.close()
    return db_path


def _session_in_planning(tmp_path) -> tuple[str, str]:
    """Create a DB + session advanced to PLANNING phase for generate tests."""
    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    session_id = create_session(conn, "diag-test")
    save_session_config(conn, session_id, '{"project":"diag-test"}')
    # Advance to PLANNING so generate is allowed
    update_session_phase(conn, session_id, "PLANNING")
    conn.commit()
    conn.close()
    return db_path, session_id


# ---------------------------------------------------------------------------
# generate: SDKError
# ---------------------------------------------------------------------------

class TestGenerateSDKError:
    def test_sdk_error_without_debug_no_traceback(self, tmp_path):
        """Without --debug, SDKError prints one line but no traceback."""
        db_path, session_id = _session_in_planning(tmp_path)
        runner = CliRunner(mix_stderr=False)

        with patch(
            "planner_auto.agents.generate_plan",
            side_effect=SDKError("API key invalid"),
        ):
            result = runner.invoke(
                cli,
                ["--db-path", db_path, "generate", session_id],
                catch_exceptions=False,
            )

        # Error message present
        assert "API key invalid" in result.stderr or "API key invalid" in result.output
        # No traceback
        assert "Traceback" not in result.output
        assert "Traceback" not in result.stderr

    def test_sdk_error_with_debug_prints_traceback(self, tmp_path):
        """With --debug, SDKError prints traceback to stderr."""
        db_path, session_id = _session_in_planning(tmp_path)
        runner = CliRunner(mix_stderr=False)

        with patch(
            "planner_auto.agents.generate_plan",
            side_effect=SDKError("API key invalid"),
        ):
            result = runner.invoke(
                cli,
                ["--db-path", db_path, "generate", session_id, "--debug"],
                catch_exceptions=False,
            )

        # Error message present
        combined = result.output + result.stderr
        assert "API key invalid" in combined
        # Traceback present in stderr (traceback.print_exc() writes to stderr)
        assert "Traceback" in result.stderr or "SDKError" in result.stderr

    def test_sdk_error_debug_traceback_contains_sdk_error(self, tmp_path):
        """Traceback in --debug mode specifically mentions SDKError."""
        db_path, session_id = _session_in_planning(tmp_path)
        runner = CliRunner(mix_stderr=False)

        with patch(
            "planner_auto.agents.generate_plan",
            side_effect=SDKError("connection refused"),
        ):
            result = runner.invoke(
                cli,
                ["--db-path", db_path, "generate", session_id, "--debug"],
                catch_exceptions=False,
            )

        assert "SDKError" in result.stderr or "connection refused" in result.stderr


# ---------------------------------------------------------------------------
# discuss: SDKError via _discuss_single
# ---------------------------------------------------------------------------

class TestDiscussSDKError:
    def _setup_discuss_session(self, tmp_path):
        """Session in DISCUSSION phase for discuss command."""
        db_path = _make_db(tmp_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        init_schema(conn)
        session_id = create_session(conn, "discuss-test")
        save_session_config(conn, session_id, '{"project":"discuss-test"}')
        update_session_phase(conn, session_id, "DISCUSSION")
        conn.commit()
        conn.close()
        return db_path, session_id

    def test_discuss_sdk_error_no_debug_no_traceback(self, tmp_path):
        """Without --debug, SDKError in discuss shows error but no traceback."""
        db_path, session_id = self._setup_discuss_session(tmp_path)
        runner = CliRunner(mix_stderr=False)

        with patch(
            "planner_auto.agents.discuss",
            side_effect=SDKError("token limit exceeded"),
        ):
            result = runner.invoke(
                cli,
                ["--db-path", db_path, "discuss", session_id, "hello"],
                catch_exceptions=False,
            )

        combined = result.output + result.stderr
        assert "token limit exceeded" in combined
        assert "Traceback" not in result.output
        assert "Traceback" not in result.stderr

    def test_discuss_sdk_error_with_debug_prints_traceback(self, tmp_path):
        """With --debug, SDKError in discuss prints traceback."""
        db_path, session_id = self._setup_discuss_session(tmp_path)
        runner = CliRunner(mix_stderr=False)

        with patch(
            "planner_auto.agents.discuss",
            side_effect=SDKError("token limit exceeded"),
        ):
            result = runner.invoke(
                cli,
                ["--db-path", db_path, "discuss", session_id, "hello", "--debug"],
                catch_exceptions=False,
            )

        assert "Traceback" in result.stderr or "SDKError" in result.stderr


# ---------------------------------------------------------------------------
# add-context: CommandNotAllowedError
# ---------------------------------------------------------------------------

class TestAddContextCommandNotAllowed:
    def test_command_not_allowed_no_debug_no_traceback(self, tmp_path):
        """Without --debug, CommandNotAllowedError shows error but no traceback."""
        db_path = _make_db(tmp_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        init_schema(conn)
        session_id = create_session(conn, "blocked-test")
        # Advance to PLANNING — add-context is not allowed there
        update_session_phase(conn, session_id, "PLANNING")
        conn.commit()
        conn.close()

        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(
            cli,
            ["--db-path", db_path, "add-context", session_id, "--note", "test note"],
            catch_exceptions=False,
        )

        # Error message present
        combined = result.output + result.stderr
        assert "Error" in combined or "not allowed" in combined.lower()
        # No traceback
        assert "Traceback" not in result.output
        assert "Traceback" not in result.stderr

    def test_command_not_allowed_with_debug_prints_traceback(self, tmp_path):
        """With --debug, CommandNotAllowedError in add-context prints traceback."""
        db_path = _make_db(tmp_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        init_schema(conn)
        session_id = create_session(conn, "blocked-debug-test")
        update_session_phase(conn, session_id, "PLANNING")
        conn.commit()
        conn.close()

        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(
            cli,
            ["--db-path", db_path, "add-context", session_id,
             "--note", "test note", "--debug"],
            catch_exceptions=False,
        )

        # Traceback should be present since CommandNotAllowedError is raised
        assert "Traceback" in result.stderr or "CommandNotAllowedError" in result.stderr


# ---------------------------------------------------------------------------
# review: Exception in review loop
# ---------------------------------------------------------------------------

class TestReviewLoopException:
    def _setup_review_session(self, tmp_path):
        """Session + plan draft in REVIEW phase."""
        db_path = _make_db(tmp_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        init_schema(conn)
        session_id = create_session(conn, "review-test")
        save_session_config(conn, session_id, '{"project":"review-test"}')
        add_plan_draft(conn, session_id, "# Plan\n\n## Milestone 1\n\n### Tasks\n- [ ] task\n\n### Deliverables\n- [ ] done", "claude-test")
        update_session_phase(conn, session_id, "REVIEW")
        conn.commit()
        conn.close()
        return db_path, session_id

    def test_review_loop_error_no_debug_no_traceback(self, tmp_path):
        """Without --debug, review loop Exception shows error but no traceback."""
        db_path, session_id = self._setup_review_session(tmp_path)
        runner = CliRunner(mix_stderr=False)

        with patch("planner_auto.review_workflow.DirectAPIAdapter"), \
             patch("planner_auto.review_workflow.ReviewWorkflow.run",
                   side_effect=RuntimeError("reviewer API down")):
            result = runner.invoke(
                cli,
                ["--db-path", db_path, "review", session_id,
                 "--reviewer-model", "gpt-4o-mini"],
                catch_exceptions=False,
            )

        combined = result.output + result.stderr
        assert "reviewer API down" in combined
        assert "Traceback" not in result.output
        assert "Traceback" not in result.stderr

    def test_review_loop_error_with_debug_prints_traceback(self, tmp_path):
        """With --debug, review loop Exception prints traceback."""
        db_path, session_id = self._setup_review_session(tmp_path)
        runner = CliRunner(mix_stderr=False)

        with patch("planner_auto.review_workflow.DirectAPIAdapter"), \
             patch("planner_auto.review_workflow.ReviewWorkflow.run",
                   side_effect=RuntimeError("reviewer API down")):
            result = runner.invoke(
                cli,
                ["--db-path", db_path, "review", session_id,
                 "--reviewer-model", "gpt-4o-mini", "--debug"],
                catch_exceptions=False,
            )

        assert "Traceback" in result.stderr or "RuntimeError" in result.stderr
