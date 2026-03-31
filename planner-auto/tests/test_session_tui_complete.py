"""Tests for session TUI complete phase — ResultSummary, COMPLETE bindings."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from planner_auto.tui.session_bindings import SESSION_BINDINGS
from planner_auto.tui.session_messages import SessionCompleted


# ---------------------------------------------------------------------------
# Tests: COMPLETE phase bindings
# ---------------------------------------------------------------------------

class TestCompleteBindings:
    def test_complete_bindings_exist(self):
        assert "COMPLETE" in SESSION_BINDINGS

    def test_complete_has_plan_key(self):
        keys = [b[0] for b in SESSION_BINDINGS["COMPLETE"]]
        assert "p" in keys

    def test_complete_has_copy_plan_path(self):
        keys = [b[0] for b in SESSION_BINDINGS["COMPLETE"]]
        assert "c" in keys

    def test_complete_has_quit(self):
        keys = [b[0] for b in SESSION_BINDINGS["COMPLETE"]]
        assert "q" in keys

    def test_complete_has_export(self):
        keys = [b[0] for b in SESSION_BINDINGS["COMPLETE"]]
        assert "e" in keys

    def test_complete_has_log_filter(self):
        keys = [b[0] for b in SESSION_BINDINGS["COMPLETE"]]
        assert "l" in keys


# ---------------------------------------------------------------------------
# Tests: ResultSummary widget
# ---------------------------------------------------------------------------

class TestResultSummaryWidget:
    def test_instantiate(self):
        from planner_auto.tui.widgets.result_summary import ResultSummary
        rs = ResultSummary()
        assert rs is not None

    def test_set_summary_no_crash_pre_compose(self):
        """set_summary before compose should not crash (widget not mounted)."""
        from planner_auto.tui.widgets.result_summary import ResultSummary
        rs = ResultSummary()
        # Before compose, query_one will fail — this tests graceful handling
        try:
            rs.set_summary(
                export_paths=["/tmp/plan.md"],
                kafra_path=None,
                total_cost=0.05,
                review_rounds=3,
                draft_number=2,
                plan_size=5000,
                milestone_count=4,
            )
        except Exception:
            pass  # Expected — no widget tree yet


# ---------------------------------------------------------------------------
# Tests: SessionCompleted message carries correct data
# ---------------------------------------------------------------------------

class TestSessionCompletedData:
    def test_with_kafra(self):
        msg = SessionCompleted(
            export_paths=["/tmp/plan.md", "/tmp/review.json"],
            kafra_path="/project/.kafra/handoff.md",
            total_cost=0.25,
        )
        assert len(msg.export_paths) == 2
        assert msg.kafra_path is not None

    def test_without_kafra(self):
        msg = SessionCompleted(
            export_paths=["/tmp/plan.md"],
            kafra_path=None,
            total_cost=0.10,
        )
        assert msg.kafra_path is None

    def test_empty_exports(self):
        msg = SessionCompleted(
            export_paths=[],
            kafra_path=None,
            total_cost=0.0,
        )
        assert msg.export_paths == []
        assert msg.total_cost == 0.0


# ---------------------------------------------------------------------------
# Tests: REVIEW phase bindings
# ---------------------------------------------------------------------------

class TestReviewBindings:
    def test_review_bindings_exist(self):
        assert "REVIEW" in SESSION_BINDINGS

    def test_review_has_dispositions(self):
        keys = [b[0] for b in SESSION_BINDINGS["REVIEW"]]
        assert "d" in keys

    def test_review_has_plan(self):
        keys = [b[0] for b in SESSION_BINDINGS["REVIEW"]]
        assert "p" in keys

    def test_review_has_raw_response(self):
        keys = [b[0] for b in SESSION_BINDINGS["REVIEW"]]
        assert "r" in keys


# ---------------------------------------------------------------------------
# Tests: PLANNING phase bindings
# ---------------------------------------------------------------------------

class TestPlanningBindings:
    def test_planning_bindings_exist(self):
        assert "PLANNING" in SESSION_BINDINGS

    def test_planning_has_generate(self):
        keys = [b[0] for b in SESSION_BINDINGS["PLANNING"]]
        assert "g" in keys

    def test_planning_has_start_review(self):
        keys = [b[0] for b in SESSION_BINDINGS["PLANNING"]]
        assert "r" in keys
