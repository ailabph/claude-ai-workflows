"""Tests for ReviewHandlerMixin — decoupled review message handler logic."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from planner_auto.tui.review_handlers import ReviewHandlerMixin


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mixin():
    return ReviewHandlerMixin()


@pytest.fixture
def mock_widgets():
    """Return a dict of mock widgets matching handler signatures."""
    return {
        "round_list": MagicMock(),
        "current_round": MagicMock(),
        "log_panel": MagicMock(),
        "convergence_panel": MagicMock(),
        "plan_panel": MagicMock(),
        "session_panel": MagicMock(),
    }


def _make_msg(**kwargs):
    """Create a mock message with given attributes."""
    msg = MagicMock()
    for k, v in kwargs.items():
        setattr(msg, k, v)
    return msg


# ---------------------------------------------------------------------------
# Tests: handle_round_started
# ---------------------------------------------------------------------------

class TestHandleRoundStarted:
    def test_updates_latest_round(self, mixin, mock_widgets):
        msg = _make_msg(round_num=1, max_rounds=5)
        mixin.handle_round_started(
            msg, mock_widgets["round_list"], mock_widgets["current_round"], mock_widgets["log_panel"]
        )
        assert mixin.latest_round == 1

    def test_stores_round_data(self, mixin, mock_widgets):
        msg = _make_msg(round_num=2, max_rounds=5)
        mixin.handle_round_started(
            msg, mock_widgets["round_list"], mock_widgets["current_round"], mock_widgets["log_panel"]
        )
        assert 2 in mixin.round_data
        assert mixin.round_data[2]["max_rounds"] == 5

    def test_calls_round_list_add(self, mixin, mock_widgets):
        msg = _make_msg(round_num=1, max_rounds=3)
        mixin.handle_round_started(
            msg, mock_widgets["round_list"], mock_widgets["current_round"], mock_widgets["log_panel"]
        )
        mock_widgets["round_list"].add_round.assert_called_once_with(1)

    def test_calls_current_round_set_gpt(self, mixin, mock_widgets):
        msg = _make_msg(round_num=3, max_rounds=5)
        mixin.handle_round_started(
            msg, mock_widgets["round_list"], mock_widgets["current_round"], mock_widgets["log_panel"]
        )
        mock_widgets["current_round"].set_gpt_review.assert_called_once_with(3)

    def test_logs_message(self, mixin, mock_widgets):
        msg = _make_msg(round_num=1, max_rounds=4)
        mixin.handle_round_started(
            msg, mock_widgets["round_list"], mock_widgets["current_round"], mock_widgets["log_panel"]
        )
        mock_widgets["log_panel"].log_message.assert_called_once()
        call_args = mock_widgets["log_panel"].log_message.call_args
        assert "R1/4" in call_args[0][0]


# ---------------------------------------------------------------------------
# Tests: handle_review_complete
# ---------------------------------------------------------------------------

class TestHandleReviewComplete:
    def test_stores_round_data_fields(self, mixin, mock_widgets):
        msg = _make_msg(
            round_num=1, verdict="NO_GO", issue_count=3, cost=0.05,
            latency_ms=1200, input_tokens=100, output_tokens=50,
            keep_count=2, trim_count=1, issues=[{"desc": "a"}],
        )
        mixin.handle_review_complete(
            msg, mock_widgets["round_list"], mock_widgets["convergence_panel"],
            mock_widgets["current_round"], mock_widgets["log_panel"],
        )
        assert mixin.round_data[1]["verdict"] == "NO_GO"
        assert mixin.round_data[1]["issue_count"] == 3
        assert mixin.round_data[1]["cost"] == 0.05

    def test_calls_convergence_update(self, mixin, mock_widgets):
        msg = _make_msg(
            round_num=1, verdict="GO", issue_count=0, cost=0.01,
            latency_ms=500, input_tokens=80, output_tokens=20,
            keep_count=0, trim_count=0, issues=[],
        )
        mixin.handle_review_complete(
            msg, mock_widgets["round_list"], mock_widgets["convergence_panel"],
            mock_widgets["current_round"], mock_widgets["log_panel"],
        )
        mock_widgets["convergence_panel"].update.assert_called_once_with(1, 0, 0.01, 100)

    def test_go_verdict_clears_current_round(self, mixin, mock_widgets):
        msg = _make_msg(
            round_num=1, verdict="GO", issue_count=0, cost=0.01,
            latency_ms=500, input_tokens=80, output_tokens=20,
            keep_count=0, trim_count=0, issues=[],
        )
        mixin.handle_review_complete(
            msg, mock_widgets["round_list"], mock_widgets["convergence_panel"],
            mock_widgets["current_round"], mock_widgets["log_panel"],
        )
        mock_widgets["current_round"].clear.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: handle_feedback_validated
# ---------------------------------------------------------------------------

class TestHandleFeedbackValidated:
    def test_counts_dispositions(self, mixin, mock_widgets):
        dispositions = [
            {"disposition": "ACCEPT"},
            {"disposition": "ACCEPT"},
            {"disposition": "DEFER_NEXT"},
            {"disposition": "REJECT_OOB"},
        ]
        msg = _make_msg(round_num=1, dispositions=dispositions)
        mixin.handle_feedback_validated(
            msg, mock_widgets["current_round"], mock_widgets["log_panel"]
        )
        mock_widgets["current_round"].set_feedback.assert_called_once_with(2, 1, 1)

    def test_no_dispositions(self, mixin, mock_widgets):
        msg = _make_msg(round_num=1, dispositions=None)
        mixin.handle_feedback_validated(
            msg, mock_widgets["current_round"], mock_widgets["log_panel"]
        )
        mock_widgets["current_round"].set_feedback.assert_called_once_with(0, 0, 0)

    def test_empty_dispositions(self, mixin, mock_widgets):
        msg = _make_msg(round_num=1, dispositions=[])
        mixin.handle_feedback_validated(
            msg, mock_widgets["current_round"], mock_widgets["log_panel"]
        )
        mock_widgets["current_round"].set_feedback.assert_called_once_with(0, 0, 0)


# ---------------------------------------------------------------------------
# Tests: handle_revision_started
# ---------------------------------------------------------------------------

class TestHandleRevisionStarted:
    def test_calls_set_revision(self, mixin, mock_widgets):
        msg = _make_msg(round_num=2, accepted_count=3, deferred_count=1, rejected_count=0)
        mixin.handle_revision_started(
            msg, mock_widgets["current_round"], mock_widgets["log_panel"]
        )
        mock_widgets["current_round"].set_revision.assert_called_once_with(2)


# ---------------------------------------------------------------------------
# Tests: handle_revision_complete
# ---------------------------------------------------------------------------

class TestHandleRevisionComplete:
    def test_stores_revision_data(self, mixin, mock_widgets):
        mixin.original_plan_size = 1000
        msg = _make_msg(
            round_num=1, latency_ms=800, prev_size=1000, new_size=1200,
            history_context_size=500,
        )
        mixin.handle_revision_complete(
            msg, mock_widgets["plan_panel"], mock_widgets["current_round"],
            mock_widgets["log_panel"],
        )
        assert mixin.round_data[1]["new_size"] == 1200

    def test_clears_current_round(self, mixin, mock_widgets):
        mixin.original_plan_size = 1000
        msg = _make_msg(
            round_num=1, latency_ms=800, prev_size=1000, new_size=1050,
            history_context_size=500,
        )
        mixin.handle_revision_complete(
            msg, mock_widgets["plan_panel"], mock_widgets["current_round"],
            mock_widgets["log_panel"],
        )
        mock_widgets["current_round"].clear.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: handle_loop_finished
# ---------------------------------------------------------------------------

class TestHandleLoopFinished:
    def test_converged_logs_success(self, mixin, mock_widgets):
        msg = _make_msg(converged=True, stop_reason="go", rounds=3, total_cost=0.12)
        mixin.handle_loop_finished(
            msg, mock_widgets["session_panel"], mock_widgets["current_round"],
            mock_widgets["log_panel"],
        )
        mock_widgets["current_round"].clear.assert_called_once()
        call_args = mock_widgets["log_panel"].log_message.call_args
        assert "Converged" in call_args[0][0]
        assert call_args[1]["level"] == "success"

    def test_cap_reached_logs_warning(self, mixin, mock_widgets):
        msg = _make_msg(converged=False, stop_reason="cap", rounds=5, total_cost=0.50)
        mixin.handle_loop_finished(
            msg, mock_widgets["session_panel"], mock_widgets["current_round"],
            mock_widgets["log_panel"],
        )
        call_args = mock_widgets["log_panel"].log_message.call_args
        assert "Cap reached" in call_args[0][0]
        assert call_args[1]["level"] == "warning"


# ---------------------------------------------------------------------------
# Tests: handle_revision_timeout
# ---------------------------------------------------------------------------

class TestHandleRevisionTimeout:
    def test_calls_set_retry(self, mixin, mock_widgets):
        msg = _make_msg(round_num=2, timeout_sec=30, retry_count=1)
        mixin.handle_revision_timeout(
            msg, mock_widgets["current_round"], mock_widgets["log_panel"]
        )
        mock_widgets["current_round"].set_retry.assert_called_once_with(2, 30, 1)

    def test_logs_warning(self, mixin, mock_widgets):
        msg = _make_msg(round_num=3, timeout_sec=60, retry_count=2)
        mixin.handle_revision_timeout(
            msg, mock_widgets["current_round"], mock_widgets["log_panel"]
        )
        call_args = mock_widgets["log_panel"].log_message.call_args
        assert "Timeout" in call_args[0][0]
        assert call_args[1]["level"] == "warning"
