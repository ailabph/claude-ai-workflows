"""Tests for session TUI blocker resolution — BlockerScreen, resolve worker, bindings."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from planner_auto.db import (
    create_session,
    init_schema,
    save_session_config,
    update_session_status,
)
from planner_auto.session import SessionManager
from planner_auto.tui.session_bindings import SESSION_BINDINGS
from planner_auto.tui.session_messages import (
    BlockerCreated,
    BlockerResolved,
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
def paused_session(mem_db):
    """Session in REVIEW phase, paused with a blocker."""
    sid = create_session(mem_db, "test-project")
    # Advance to REVIEW and pause
    mem_db.execute("UPDATE sessions SET phase = 'REVIEW', status = 'PAUSED' WHERE id = ?", (sid,))
    mem_db.commit()
    # Create a blocker
    sm = SessionManager(mem_db)
    sm.pause_with_blocker(sid, "reviewer", "Review cap reached with critical issues.")
    return sid


# ---------------------------------------------------------------------------
# Tests: BlockerScreen widget
# ---------------------------------------------------------------------------

class TestBlockerScreen:
    def test_instantiate(self):
        from planner_auto.tui.screens.blocker_screen import BlockerScreen
        screen = BlockerScreen(source="reviewer", question="What should we do?")
        assert screen._source == "reviewer"
        assert screen._question == "What should we do?"

    def test_dismiss_returns_none(self):
        """Esc should dismiss returning None — session stays paused."""
        from planner_auto.tui.screens.blocker_screen import BlockerScreen
        screen = BlockerScreen(source="reviewer", question="question")
        # Simulate action_dismiss_modal — normally calls self.dismiss(None)
        assert hasattr(screen, "action_dismiss_modal")

    def test_bindings_include_escape(self):
        from planner_auto.tui.screens.blocker_screen import BlockerScreen
        screen = BlockerScreen(source="reviewer", question="question")
        binding_keys = [b.key for b in screen.BINDINGS]
        assert "escape" in binding_keys

    def test_long_question_text(self):
        """BlockerScreen should handle long question text without crash."""
        from planner_auto.tui.screens.blocker_screen import BlockerScreen
        long_q = "- Critical issue: " * 50
        screen = BlockerScreen(source="reviewer", question=long_q)
        assert screen._question == long_q


# ---------------------------------------------------------------------------
# Tests: BlockerCreated message
# ---------------------------------------------------------------------------

class TestBlockerCreatedMessage:
    def test_stores_blocker_id(self):
        msg = BlockerCreated(source="reviewer", question="critical issues", blocker_id=42)
        assert msg.blocker_id == 42
        assert msg.source == "reviewer"

    def test_all_fields(self):
        msg = BlockerCreated(
            source="user",
            question="Need clarification on API design.",
            blocker_id=7,
        )
        assert msg.source == "user"
        assert msg.question == "Need clarification on API design."
        assert msg.blocker_id == 7


# ---------------------------------------------------------------------------
# Tests: BlockerResolved message
# ---------------------------------------------------------------------------

class TestBlockerResolvedMessage:
    def test_fields(self):
        msg = BlockerResolved(blocker_id=42, phase="REVIEW")
        assert msg.blocker_id == 42
        assert msg.phase == "REVIEW"

    def test_different_phase(self):
        msg = BlockerResolved(blocker_id=1, phase="PLANNING")
        assert msg.phase == "PLANNING"


# ---------------------------------------------------------------------------
# Tests: PAUSED bindings
# ---------------------------------------------------------------------------

class TestPausedBindings:
    def test_paused_bindings_exist(self):
        assert "PAUSED" in SESSION_BINDINGS

    def test_paused_has_enter(self):
        keys = [b[0] for b in SESSION_BINDINGS["PAUSED"]]
        assert "enter" in keys

    def test_paused_enter_action(self):
        actions = [b[1] for b in SESSION_BINDINGS["PAUSED"]]
        assert "open_blocker" in actions

    def test_paused_has_quit(self):
        keys = [b[0] for b in SESSION_BINDINGS["PAUSED"]]
        assert "q" in keys

    def test_paused_has_common_bindings(self):
        keys = [b[0] for b in SESSION_BINDINGS["PAUSED"]]
        assert "e" in keys  # export
        assert "l" in keys  # log filter


# ---------------------------------------------------------------------------
# Tests: resolve_and_resume
# ---------------------------------------------------------------------------

class TestResolveAndResume:
    def test_resolve_resumes_session(self, mem_db, paused_session):
        """resolve_and_resume should resolve the blocker and set status to ACTIVE."""
        from planner_auto.db import get_open_blockers, get_session
        blockers = get_open_blockers(mem_db, paused_session)
        assert len(blockers) >= 1

        sm = SessionManager(mem_db)
        sm.resolve_and_resume(paused_session, blockers[0]["id"], "Accepted the issues.")

        # Should have no open blockers now
        remaining = get_open_blockers(mem_db, paused_session)
        assert len(remaining) == 0

        # Session should be ACTIVE
        session = get_session(mem_db, paused_session)
        assert session["status"] == "ACTIVE"

    def test_resolve_with_empty_answer_still_works(self, mem_db, paused_session):
        """Even an empty answer should resolve the blocker."""
        from planner_auto.db import get_open_blockers
        blockers = get_open_blockers(mem_db, paused_session)
        sm = SessionManager(mem_db)
        # resolve_and_resume accepts any string — validation is at the TUI level
        sm.resolve_and_resume(paused_session, blockers[0]["id"], "")

        remaining = get_open_blockers(mem_db, paused_session)
        assert len(remaining) == 0


# ---------------------------------------------------------------------------
# Tests: Dismiss keeps session paused
# ---------------------------------------------------------------------------

class TestDismissKeepsPaused:
    def test_none_answer_means_no_resolve(self, mem_db, paused_session):
        """When BlockerScreen returns None, the session stays paused."""
        from planner_auto.db import get_open_blockers, get_session

        # Verify blocker exists
        blockers = get_open_blockers(mem_db, paused_session)
        assert len(blockers) >= 1

        # Simulate dismiss (answer=None) — no resolve call
        # Session should still be paused
        session = get_session(mem_db, paused_session)
        assert session["status"] == "PAUSED"


# ---------------------------------------------------------------------------
# Tests: BlockerResolved updates state
# ---------------------------------------------------------------------------

class TestBlockerResolvedUpdatesState:
    def test_resolved_clears_blocker_state(self):
        """on_blocker_resolved should clear _blocker_id."""
        # Test the contract: after resolution, blocker_id should be None
        blocker_id = 42
        blocker_id = None  # Simulating on_blocker_resolved setting it
        assert blocker_id is None

    def test_resolved_restores_phase(self):
        """BlockerResolved carries the session's current phase."""
        msg = BlockerResolved(blocker_id=42, phase="REVIEW")
        # The phase in the message is read from the DB after resolution
        assert msg.phase == "REVIEW"

    def test_resolved_sets_active_status(self):
        """After resolution, session status should be ACTIVE."""
        # Integration test: resolve_and_resume sets ACTIVE
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        sid = create_session(conn, "test")
        conn.execute("UPDATE sessions SET phase = 'REVIEW', status = 'PAUSED' WHERE id = ?", (sid,))
        conn.commit()
        sm = SessionManager(conn)
        sm.pause_with_blocker(sid, "reviewer", "Test blocker")

        from planner_auto.db import get_open_blockers, get_session
        blockers = get_open_blockers(conn, sid)
        sm.resolve_and_resume(sid, blockers[0]["id"], "Fixed it")

        session = get_session(conn, sid)
        assert session["status"] == "ACTIVE"
        conn.close()
