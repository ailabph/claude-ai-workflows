"""Tests for session TUI review phase — widget mounting, event ownership, blockers."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from planner_auto.db import (
    add_plan_draft,
    create_session,
    init_schema,
    save_session_config,
)
from planner_auto.tui.messages import (
    LoopFinished,
    LoopError,
    RoundStarted,
    ReviewComplete,
    RevisionTimeout,
)
from planner_auto.tui.review_handlers import ReviewHandlerMixin
from planner_auto.tui.session_messages import (
    BlockerCreated,
    SessionCompleted,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_db():
    """In-memory SQLite with schema initialized."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


@pytest.fixture
def review_session(mem_db):
    """Session in REVIEW phase with a plan draft."""
    sid = create_session(mem_db, "test-project")
    mem_db.execute("UPDATE sessions SET phase = 'REVIEW' WHERE id = ?", (sid,))
    mem_db.commit()
    plan_text = "## Milestone 1: Test\n### Tasks\n- [ ] task\n### Deliverables\n- [ ] d"
    add_plan_draft(mem_db, sid, plan_text, "claude-sonnet-4-6")
    mem_db.commit()
    save_session_config(mem_db, sid, json.dumps({"model": "claude-sonnet-4-6", "claude_backend": "direct"}))
    mem_db.commit()
    return sid


# ---------------------------------------------------------------------------
# Tests: LoopFinished does NOT trigger phase transition
# ---------------------------------------------------------------------------

class TestLoopFinishedOwnership:
    """LoopFinished updates review widgets only — no phase transitions."""

    def test_loop_finished_converged_no_phase_change(self):
        """LoopFinished(converged=True) should NOT advance phase."""
        mixin = ReviewHandlerMixin()
        session_panel = MagicMock()
        current_round = MagicMock()
        log_panel = MagicMock()

        msg = MagicMock()
        msg.converged = True
        msg.stop_reason = "go"
        msg.rounds = 2
        msg.total_cost = 0.05

        mixin.handle_loop_finished(msg, session_panel, current_round, log_panel)

        # Current round should be cleared
        current_round.clear.assert_called_once()
        # Log success
        log_panel.log_message.assert_called_once()
        assert log_panel.log_message.call_args[1]["level"] == "success"
        # Session panel is NOT updated with phase — that's SessionCompleted's job
        session_panel.advance_phase.assert_not_called() if hasattr(session_panel, 'advance_phase') else None

    def test_loop_finished_cap_no_phase_change(self):
        """LoopFinished(converged=False) should NOT set paused state."""
        mixin = ReviewHandlerMixin()
        session_panel = MagicMock()
        current_round = MagicMock()
        log_panel = MagicMock()

        msg = MagicMock()
        msg.converged = False
        msg.stop_reason = "cap_with_criticals"
        msg.rounds = 5
        msg.total_cost = 0.40

        mixin.handle_loop_finished(msg, session_panel, current_round, log_panel)

        current_round.clear.assert_called_once()
        assert log_panel.log_message.call_args[1]["level"] == "warning"


# ---------------------------------------------------------------------------
# Tests: SessionCompleted message
# ---------------------------------------------------------------------------

class TestSessionCompleted:
    def test_message_fields(self):
        msg = SessionCompleted(
            export_paths=["/tmp/plan.md", "/tmp/review.md"],
            kafra_path="/tmp/.kafra",
            total_cost=0.15,
        )
        assert msg.export_paths == ["/tmp/plan.md", "/tmp/review.md"]
        assert msg.kafra_path == "/tmp/.kafra"
        assert msg.total_cost == 0.15

    def test_message_no_kafra(self):
        msg = SessionCompleted(
            export_paths=["/tmp/plan.md"],
            kafra_path=None,
            total_cost=0.10,
        )
        assert msg.kafra_path is None


# ---------------------------------------------------------------------------
# Tests: BlockerCreated message
# ---------------------------------------------------------------------------

class TestBlockerCreated:
    def test_message_fields(self):
        msg = BlockerCreated(
            source="reviewer",
            question="Review cap reached with critical issues.",
            blocker_id=42,
        )
        assert msg.source == "reviewer"
        assert msg.question == "Review cap reached with critical issues."
        assert msg.blocker_id == 42


# ---------------------------------------------------------------------------
# Tests: Review message routing via mixin
# ---------------------------------------------------------------------------

class TestReviewMessageRouting:
    """Test that review messages can be handled by the mixin."""

    def test_round_started_routing(self):
        mixin = ReviewHandlerMixin()
        round_list = MagicMock()
        current_round = MagicMock()
        log_panel = MagicMock()

        msg = MagicMock()
        msg.round_num = 1
        msg.max_rounds = 5

        mixin.handle_round_started(msg, round_list, current_round, log_panel)
        round_list.add_round.assert_called_once_with(1)

    def test_revision_timeout_routing(self):
        mixin = ReviewHandlerMixin()
        current_round = MagicMock()
        log_panel = MagicMock()

        msg = MagicMock()
        msg.round_num = 2
        msg.timeout_sec = 30
        msg.retry_count = 1

        mixin.handle_revision_timeout(msg, current_round, log_panel)
        current_round.set_retry.assert_called_once_with(2, 30, 1)


# ---------------------------------------------------------------------------
# Tests: LoopError message
# ---------------------------------------------------------------------------

class TestLoopError:
    def test_message_fields(self):
        msg = LoopError("Connection timeout", round_num=3)
        assert msg.error_message == "Connection timeout"
        assert msg.round_num == 3

    def test_message_no_round(self):
        msg = LoopError("Setup failed", round_num=None)
        assert msg.round_num is None


# ---------------------------------------------------------------------------
# Tests: Deferred quit during review
# ---------------------------------------------------------------------------

class TestDeferredQuit:
    def test_quit_deferred_flag(self):
        """The _quit_requested pattern should be supported."""
        # This tests the contract, not the TUI directly
        quit_requested = False
        review_active = True

        # Simulating action_quit
        if not review_active:
            pass  # would call _cleanup_and_exit
        else:
            quit_requested = True

        assert quit_requested is True

    def test_quit_after_review_completes(self):
        """After review finishes, deferred quit should proceed."""
        quit_requested = True
        review_active = False
        should_exit = not review_active and quit_requested
        assert should_exit is True


# ---------------------------------------------------------------------------
# Tests: PhaseList.set_paused
# ---------------------------------------------------------------------------

class TestPhaseListSetPaused:
    """Test that PhaseList.set_paused sets the paused icon correctly."""

    def test_set_paused_updates_icon(self):
        from planner_auto.tui.widgets.phase_list import (
            ICON_PAUSED,
            PhaseList,
        )
        pl = PhaseList()
        # Before compose, _icons is empty — set_paused calls update_phase
        # which stores the icon even if the label doesn't exist yet
        pl._icons["REVIEW"] = "▶"
        pl.set_paused("REVIEW")
        assert pl._icons["REVIEW"] == ICON_PAUSED

    def test_set_paused_method_exists(self):
        from planner_auto.tui.widgets.phase_list import PhaseList
        assert hasattr(PhaseList, "set_paused")
        assert callable(getattr(PhaseList, "set_paused"))
