"""Tests for ReviewWorkflow: prepare(), run(), and finalize().

All external calls are mocked — no API keys needed.
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from planner_auto.db import (
    add_plan_draft,
    create_session,
    get_open_blockers,
    get_session,
    init_schema,
    update_session_phase,
)
from planner_auto.loop.engine import LoopResult
from planner_auto.review_workflow import (
    FinalizeResult,
    PreparedReview,
    ReviewOpts,
    ReviewWorkflow,
)
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


def _make_planning_session(conn) -> str:
    """Create a session in PLANNING phase with one plan draft."""
    sid = create_session(conn, "test-project")
    update_session_phase(conn, sid, "CONTEXT")
    update_session_phase(conn, sid, "DISCUSSION")
    update_session_phase(conn, sid, "PLANNING")
    add_plan_draft(conn, sid, "# Test Plan\n\nThis is the initial plan.", "claude-sonnet")
    conn.commit()
    return sid


# ---------------------------------------------------------------------------
# 1. prepare() returns correct config from mocked session
# ---------------------------------------------------------------------------

@patch("planner_auto.review_workflow.DirectAPIAdapter")
class TestPrepare:
    def test_prepare_returns_prepared_review(self, mock_adapter_cls):
        conn = _make_conn()
        sid = _make_planning_session(conn)

        opts = ReviewOpts(fast=False, max_rounds=3)
        prepared = ReviewWorkflow.prepare(conn, sid, opts)

        assert isinstance(prepared, PreparedReview)
        assert prepared.current_plan.startswith("# Test Plan")
        assert prepared.max_rounds == 3
        assert prepared.fast is False
        assert prepared.planner_model is not None
        assert prepared.session_id == sid

    def test_prepare_advances_planning_to_review(self, mock_adapter_cls):
        conn = _make_conn()
        sid = _make_planning_session(conn)

        opts = ReviewOpts()
        ReviewWorkflow.prepare(conn, sid, opts)

        session = get_session(conn, sid)
        assert session["phase"] == Phase.REVIEW.value

    def test_prepare_fast_mode_sets_config(self, mock_adapter_cls):
        conn = _make_conn()
        sid = _make_planning_session(conn)

        opts = ReviewOpts(fast=True)
        prepared = ReviewWorkflow.prepare(conn, sid, opts)

        assert prepared.fast is True
        assert prepared.engine_config["validate_feedback"] is False
        assert prepared.engine_config["review_history"] is False

    def test_prepare_no_draft_raises_value_error(self, mock_adapter_cls):
        conn = _make_conn()
        sid = create_session(conn, "test-project")
        update_session_phase(conn, sid, "CONTEXT")
        update_session_phase(conn, sid, "DISCUSSION")
        update_session_phase(conn, sid, "PLANNING")
        conn.commit()

        opts = ReviewOpts()
        with pytest.raises(ValueError, match="No plan draft"):
            ReviewWorkflow.prepare(conn, sid, opts)


# ---------------------------------------------------------------------------
# 2. finalize() advances phase on convergence
# ---------------------------------------------------------------------------

class TestFinalizeConverged:
    @patch("planner_auto.review_workflow.DirectAPIAdapter")
    def test_finalize_converged_advances_to_complete(self, mock_adapter_cls):
        conn = _make_conn()
        sid = _make_planning_session(conn)

        # Prepare first to advance to REVIEW.
        opts = ReviewOpts(max_rounds=2)
        prepared = ReviewWorkflow.prepare(conn, sid, opts)

        result = LoopResult(
            converged=True,
            rounds=2,
            final_plan="final plan text",
            final_draft_number=2,
            total_cost=0.05,
            stop_reason="go",
            final_round_number=2,
        )

        with patch("planner_auto.review_workflow.export_review_artifacts", return_value=[]):
            with patch("planner_auto.review_workflow.kafra_handoff", return_value=None):
                fin = ReviewWorkflow.finalize(conn, sid, result, prepared)

        assert fin.converged is True
        assert fin.phase == Phase.COMPLETE.value

        session = get_session(conn, sid)
        assert session["phase"] == Phase.COMPLETE.value
        assert session["status"] == "COMPLETE"


# ---------------------------------------------------------------------------
# 3. finalize() creates blocker on cap_with_criticals
# ---------------------------------------------------------------------------

class TestFinalizeCapWithCriticals:
    @patch("planner_auto.review_workflow.DirectAPIAdapter")
    def test_finalize_cap_creates_blocker(self, mock_adapter_cls):
        conn = _make_conn()
        sid = _make_planning_session(conn)

        opts = ReviewOpts(max_rounds=2)
        prepared = ReviewWorkflow.prepare(conn, sid, opts)

        result = LoopResult(
            converged=False,
            rounds=2,
            final_plan="final plan text",
            final_draft_number=2,
            total_cost=0.10,
            stop_reason="cap_with_criticals",
            final_round_number=2,
        )

        fin = ReviewWorkflow.finalize(conn, sid, result, prepared)

        assert fin.converged is False
        assert fin.blocker_text is not None
        assert "cap reached" in fin.blocker_text.lower()

        # Session should be paused with a blocker.
        blockers = get_open_blockers(conn, sid)
        assert len(blockers) >= 1
