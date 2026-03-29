"""Tests for TUI message classes.

Verify all 8 message types can be instantiated with correct fields and types.
"""

from __future__ import annotations

import pytest

from planner_auto.tui.messages import (
    FeedbackValidated,
    LoopError,
    LoopFinished,
    ReviewComplete,
    RevisionComplete,
    RevisionStarted,
    RevisionTimeout,
    RoundStarted,
)


class TestRoundStarted:
    def test_fields(self):
        msg = RoundStarted(round_num=3, max_rounds=6)
        assert msg.round_num == 3
        assert msg.max_rounds == 6

    def test_types(self):
        msg = RoundStarted(round_num=1, max_rounds=5)
        assert isinstance(msg.round_num, int)
        assert isinstance(msg.max_rounds, int)


class TestReviewComplete:
    def test_fields(self):
        msg = ReviewComplete(
            round_num=2,
            verdict="NO_GO",
            issue_count=3,
            latency_ms=1200,
            input_tokens=500,
            output_tokens=800,
            cost=0.05,
            keep_count=2,
            trim_count=1,
            issues=[{"severity": "critical", "description": "test"}],
        )
        assert msg.round_num == 2
        assert msg.verdict == "NO_GO"
        assert msg.issue_count == 3
        assert msg.latency_ms == 1200
        assert msg.input_tokens == 500
        assert msg.output_tokens == 800
        assert msg.cost == 0.05
        assert msg.keep_count == 2
        assert msg.trim_count == 1
        assert len(msg.issues) == 1

    def test_optional_none(self):
        msg = ReviewComplete(
            round_num=1, verdict="GO", issue_count=0, latency_ms=100,
            input_tokens=None, output_tokens=None, cost=None,
            keep_count=0, trim_count=0, issues=[],
        )
        assert msg.input_tokens is None
        assert msg.output_tokens is None
        assert msg.cost is None


class TestFeedbackValidated:
    def test_with_dispositions(self):
        disps = [{"description": "A", "disposition": "ACCEPT"}]
        msg = FeedbackValidated(round_num=1, dispositions=disps)
        assert msg.round_num == 1
        assert msg.dispositions == disps

    def test_none_dispositions(self):
        msg = FeedbackValidated(round_num=2, dispositions=None)
        assert msg.dispositions is None


class TestRevisionStarted:
    def test_fields(self):
        msg = RevisionStarted(
            round_num=1, accepted_count=3, deferred_count=1, rejected_count=0,
        )
        assert msg.round_num == 1
        assert msg.accepted_count == 3
        assert msg.deferred_count == 1
        assert msg.rejected_count == 0


class TestRevisionComplete:
    def test_fields(self):
        msg = RevisionComplete(
            round_num=1, prev_size=5000, new_size=5200,
            latency_ms=3000, history_context_size=1200,
        )
        assert msg.round_num == 1
        assert msg.prev_size == 5000
        assert msg.new_size == 5200
        assert msg.latency_ms == 3000
        assert msg.history_context_size == 1200


class TestLoopFinished:
    def test_converged(self):
        msg = LoopFinished(
            converged=True, stop_reason="go", rounds=3,
            total_cost=0.15, final_plan_path="/tmp/plan.md",
        )
        assert msg.converged is True
        assert msg.stop_reason == "go"
        assert msg.rounds == 3
        assert msg.total_cost == 0.15
        assert msg.final_plan_path == "/tmp/plan.md"

    def test_not_converged_no_path(self):
        msg = LoopFinished(
            converged=False, stop_reason="cap_with_criticals",
            rounds=6, total_cost=0.30,
        )
        assert msg.converged is False
        assert msg.final_plan_path is None


class TestRevisionTimeout:
    def test_fields(self):
        msg = RevisionTimeout(round_num=2, timeout_sec=120, retry_count=1)
        assert msg.round_num == 2
        assert msg.timeout_sec == 120
        assert msg.retry_count == 1


class TestLoopError:
    def test_with_round(self):
        msg = LoopError(error_message="API timeout", round_num=3)
        assert msg.error_message == "API timeout"
        assert msg.round_num == 3

    def test_without_round(self):
        msg = LoopError(error_message="Setup failed")
        assert msg.error_message == "Setup failed"
        assert msg.round_num is None
