"""Tests for TUIAdapter — verifies callback→message translation.

The app is mocked; we verify correct message types are posted.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from planner_auto.tui.adapter import TUIAdapter
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


@pytest.fixture
def mock_app():
    """Mock Textual App with call_from_thread and post_message."""
    app = MagicMock()
    # call_from_thread should call the function immediately for testing.
    app.call_from_thread = MagicMock(side_effect=lambda fn, *args: fn(*args))
    app.post_message = MagicMock()
    return app


@pytest.fixture
def adapter(mock_app):
    return TUIAdapter(mock_app)


class TestAdapterMethods:
    def test_on_round_start_posts_round_started(self, adapter, mock_app):
        adapter.on_round_start(3, 6)
        mock_app.post_message.assert_called_once()
        msg = mock_app.post_message.call_args[0][0]
        assert isinstance(msg, RoundStarted)
        assert msg.round_num == 3
        assert msg.max_rounds == 6

    def test_on_review_complete_posts_review_complete(self, adapter, mock_app):
        metrics = {
            "round_num": 1,
            "verdict": "NO_GO",
            "issue_count": 2,
            "latency_ms": 1500,
            "input_tokens": 400,
            "output_tokens": 600,
            "cost": 0.03,
            "keep_count": 1,
            "trim_count": 0,
            "issues": [{"severity": "critical"}],
        }
        adapter.on_review_complete(metrics)
        msg = mock_app.post_message.call_args[0][0]
        assert isinstance(msg, ReviewComplete)
        assert msg.verdict == "NO_GO"
        assert msg.issue_count == 2

    def test_on_feedback_validated_posts_feedback_validated(self, adapter, mock_app):
        disps = [{"description": "A", "disposition": "ACCEPT"}]
        adapter.on_feedback_validated(2, disps)
        msg = mock_app.post_message.call_args[0][0]
        assert isinstance(msg, FeedbackValidated)
        assert msg.round_num == 2

    def test_on_revision_start_posts_revision_started(self, adapter, mock_app):
        adapter.on_revision_start(1, 3, 1, 0)
        msg = mock_app.post_message.call_args[0][0]
        assert isinstance(msg, RevisionStarted)
        assert msg.accepted_count == 3

    def test_on_revision_complete_posts_revision_complete(self, adapter, mock_app):
        adapter.on_revision_complete(1, 5000, 5200, 2000, 800)
        msg = mock_app.post_message.call_args[0][0]
        assert isinstance(msg, RevisionComplete)
        assert msg.prev_size == 5000
        assert msg.new_size == 5200

    def test_on_loop_finished_posts_loop_finished(self, adapter, mock_app):
        result_dict = {
            "converged": True,
            "stop_reason": "go",
            "total_rounds": 3,
            "total_cost": 0.12,
        }
        adapter.on_loop_finished(result_dict)
        msg = mock_app.post_message.call_args[0][0]
        assert isinstance(msg, LoopFinished)
        assert msg.converged is True
        assert msg.stop_reason == "go"

    def test_on_revision_timeout_posts_revision_timeout(self, adapter, mock_app):
        adapter.on_revision_timeout(2, 120, 1)
        msg = mock_app.post_message.call_args[0][0]
        assert isinstance(msg, RevisionTimeout)
        assert msg.timeout_sec == 120

    def test_on_error_posts_loop_error(self, adapter, mock_app):
        adapter.on_error("Something broke", round_num=4)
        msg = mock_app.post_message.call_args[0][0]
        assert isinstance(msg, LoopError)
        assert msg.error_message == "Something broke"
        assert msg.round_num == 4


class TestAsDict:
    def test_returns_all_7_callback_keys(self, adapter):
        d = adapter.as_dict()
        expected_keys = {
            "on_round_start",
            "on_review_complete",
            "on_feedback_validated",
            "on_revision_start",
            "on_revision_complete",
            "on_loop_finished",
            "on_revision_timeout",
        }
        assert set(d.keys()) == expected_keys

    def test_values_are_callable(self, adapter):
        d = adapter.as_dict()
        for key, value in d.items():
            assert callable(value), f"{key} is not callable"

    def test_does_not_include_on_error(self, adapter):
        """on_error is not an engine callback — it's used by the worker thread."""
        d = adapter.as_dict()
        assert "on_error" not in d
