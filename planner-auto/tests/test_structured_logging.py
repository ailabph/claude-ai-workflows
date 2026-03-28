"""Tests for structured logging across planner_auto modules.

Verifies that key decision-point log messages are emitted at the correct
levels.  Uses pytest's ``caplog`` fixture — no real API calls are made.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from planner_auto.db import create_session, init_schema
from planner_auto.loop.convergence import detect_complexity, get_max_rounds
from planner_auto.loop.history import build_review_context
from planner_auto.reviewer.parser import parse_reviewer_response
from planner_auto.session import SessionManager
from planner_auto.state import Phase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# session.py — phase transition log
# ---------------------------------------------------------------------------

class TestSessionLogging:
    def test_phase_transition_logged_at_info(self, caplog):
        """advance_phase logs 'Phase X → Y' at INFO level."""
        conn = _make_conn()
        session_id = create_session(conn, "test-project")
        sm = SessionManager(conn)

        with caplog.at_level(logging.INFO, logger="planner_auto"):
            sm.advance_phase(session_id, Phase.CONTEXT.value)

        assert any(
            "Phase" in r.message and "SETUP" in r.message and "CONTEXT" in r.message
            for r in caplog.records
        )

    def test_command_blocked_logged_at_warning(self, caplog):
        """check_command logs a WARNING when a command is blocked."""
        conn = _make_conn()
        session_id = create_session(conn, "test-project")
        sm = SessionManager(conn)

        # In SETUP phase, 'discuss' is not allowed.
        from planner_auto.errors import CommandNotAllowedError
        with caplog.at_level(logging.WARNING, logger="planner_auto"):
            with pytest.raises(CommandNotAllowedError):
                sm.check_command(session_id, "discuss")

        assert any(
            r.levelno == logging.WARNING and "discuss" in r.message
            for r in caplog.records
        )

    def test_pause_with_blocker_logged_at_info(self, caplog):
        """pause_with_blocker logs 'Session paused, blocker: {source}' at INFO."""
        conn = _make_conn()
        session_id = create_session(conn, "test-project")
        sm = SessionManager(conn)
        # Advance to a phase where pausing is meaningful
        sm.advance_phase(session_id, Phase.CONTEXT.value)
        sm.advance_phase(session_id, Phase.DISCUSSION.value)
        sm.advance_phase(session_id, Phase.PLANNING.value)
        sm.advance_phase(session_id, Phase.REVIEW.value)

        with caplog.at_level(logging.INFO, logger="planner_auto"):
            sm.pause_with_blocker(session_id, "reviewer", "Needs clarification")

        assert any(
            "Session paused" in r.message and "reviewer" in r.message
            for r in caplog.records
        )


# ---------------------------------------------------------------------------
# reviewer/parser.py — parse stage log
# ---------------------------------------------------------------------------

class TestParserLogging:
    def test_json_parse_logged_as_json(self, caplog):
        """parse_reviewer_response logs 'Parsed as JSON' when JSON matches."""
        valid_json = '{"verdict": "GO", "issues": [], "summary": "ok"}'
        with caplog.at_level(logging.DEBUG, logger="planner_auto"):
            parse_reviewer_response(valid_json)

        assert any(
            "JSON" in r.message for r in caplog.records
        )

    def test_xml_parse_logs_json_failed_then_xml(self, caplog):
        """When JSON fails, 'JSON parse failed, trying XML' is logged."""
        xml_text = (
            "<verdict>NO_GO</verdict>"
            "<summary>needs work</summary>"
            "<issues></issues>"
        )
        with caplog.at_level(logging.DEBUG, logger="planner_auto"):
            parse_reviewer_response(xml_text)

        messages = [r.message for r in caplog.records]
        assert any("JSON parse failed" in m for m in messages)
        assert any("XML" in m for m in messages)

    def test_freeform_parse_path(self, caplog):
        """When JSON and XML both fail, free-form parse is attempted."""
        freeform = "The plan looks good. I recommend proceeding."
        with caplog.at_level(logging.DEBUG, logger="planner_auto"):
            parse_reviewer_response(freeform)

        messages = [r.message for r in caplog.records]
        assert any("JSON parse failed" in m for m in messages)

    def test_parse_failure_logged(self, caplog):
        """Fully unparseable input logs a failure message."""
        with caplog.at_level(logging.DEBUG, logger="planner_auto"):
            parse_reviewer_response("{invalid json {{{{")

        assert any("failure" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# loop/convergence.py — complexity log
# ---------------------------------------------------------------------------

class TestConvergenceLogging:
    def test_complexity_logged_with_cap(self, caplog):
        """detect_complexity logs level, keywords, and cap at INFO."""
        conn = _make_conn()
        session_id = create_session(conn, "test-project")

        with caplog.at_level(logging.INFO, logger="planner_auto"):
            level = detect_complexity(conn, session_id)

        assert any(
            "Complexity" in r.message and "cap" in r.message
            for r in caplog.records
        )
        assert level in ("standard", "complex")


# ---------------------------------------------------------------------------
# loop/history.py — context size log
# ---------------------------------------------------------------------------

class TestHistoryLogging:
    def test_context_size_logged_at_debug(self, caplog, db_conn):
        """build_review_context logs 'History context: N chars, M defers' at DEBUG."""
        session_id = create_session(db_conn, "history-test")

        # Build_review_context returns None for round 1 — test round 2.
        # We need a review row for round 1.
        from planner_auto.db import add_plan_draft, add_review_v2
        add_plan_draft(db_conn, session_id, "plan content", "model")
        add_review_v2(
            db_conn,
            session_id=session_id,
            round_number=1,
            verdict="NO_GO",
            issues_json='[{"severity":"major","description":"foo","rationale":"bar"}]',
            summary="summary",
            raw_response=None,
            reviewer_model=None,
            cost=None,
            input_tokens=None,
            output_tokens=None,
        )
        db_conn.commit()

        with caplog.at_level(logging.DEBUG, logger="planner_auto"):
            result = build_review_context(db_conn, session_id, current_round=2)

        # Result is a string (not None) because round 2 > 1 and review 1 exists.
        assert result is not None
        assert any(
            "History context" in r.message and "chars" in r.message
            for r in caplog.records
        )


# ---------------------------------------------------------------------------
# export.py — file export log
# ---------------------------------------------------------------------------

class TestExportLogging:
    def test_export_files_logged_at_info(self, tmp_path, caplog):
        """export_session logs 'Exported {filename}, {size} bytes' at INFO."""
        from planner_auto.export import export_session

        conn = _make_conn()
        session_id = create_session(conn, "export-test")

        with caplog.at_level(logging.INFO, logger="planner_auto"):
            export_session(session_id, conn, output_dir=str(tmp_path))

        assert any(
            "Exported" in r.message and "bytes" in r.message
            for r in caplog.records
        )

    def test_kafra_skipped_logs_warning(self, tmp_path, caplog):
        """.kafra handoff logs a WARNING when no repo root is found."""
        from planner_auto.export import kafra_handoff

        conn = _make_conn()
        session_id = create_session(conn, "kafra-test")

        with patch("planner_auto.export.discover_repo_root", return_value=None):
            with caplog.at_level(logging.WARNING, logger="planner_auto"):
                result = kafra_handoff(session_id, conn, "plan text", "my-project")

        assert result is None
        assert any(
            ".kafra skipped" in r.message or "no repo root" in r.message
            for r in caplog.records
        )

    def test_kafra_success_logs_info(self, tmp_path, caplog):
        """Successful .kafra handoff logs 'Copied to {path}' at INFO."""
        from planner_auto.export import kafra_handoff

        conn = _make_conn()
        session_id = create_session(conn, "kafra-success")

        with caplog.at_level(logging.INFO, logger="planner_auto"):
            result = kafra_handoff(
                session_id, conn, "plan text", "my-project",
                repo_root=str(tmp_path),
            )

        assert result is not None
        assert any(
            "Copied to" in r.message for r in caplog.records
        )
