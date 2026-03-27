"""Tests for planner_auto.session.SessionManager."""

import pytest

from planner_auto.db import (
    create_blocker,
    create_session,
    get_session,
    update_session_phase,
    update_session_status,
)
from planner_auto.errors import (
    CommandNotAllowedError,
    InvalidTransitionError,
    SessionNotFoundError,
)
from planner_auto.session import SessionManager
from planner_auto.state import Phase, Status


@pytest.fixture
def sm(db_conn):
    """Provide a SessionManager with an in-memory DB."""
    return SessionManager(db_conn)


class TestAdvancePhase:
    """Tests for SessionManager.advance_phase()."""

    def test_valid_setup_to_context(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        sm.advance_phase(sid, Phase.CONTEXT.value)
        session = get_session(db_conn, sid)
        assert session["phase"] == "CONTEXT"

    def test_valid_context_to_discussion(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        update_session_phase(db_conn, sid, Phase.CONTEXT.value)
        sm.advance_phase(sid, Phase.DISCUSSION.value)
        session = get_session(db_conn, sid)
        assert session["phase"] == "DISCUSSION"

    def test_valid_discussion_to_planning(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        update_session_phase(db_conn, sid, Phase.DISCUSSION.value)
        sm.advance_phase(sid, Phase.PLANNING.value)
        assert get_session(db_conn, sid)["phase"] == "PLANNING"

    def test_valid_planning_to_review(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        update_session_phase(db_conn, sid, Phase.PLANNING.value)
        sm.advance_phase(sid, Phase.REVIEW.value)
        assert get_session(db_conn, sid)["phase"] == "REVIEW"

    def test_valid_review_to_complete(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        update_session_phase(db_conn, sid, Phase.REVIEW.value)
        sm.advance_phase(sid, Phase.COMPLETE.value)
        assert get_session(db_conn, sid)["phase"] == "COMPLETE"

    def test_valid_review_to_planning(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        update_session_phase(db_conn, sid, Phase.REVIEW.value)
        sm.advance_phase(sid, Phase.PLANNING.value)
        assert get_session(db_conn, sid)["phase"] == "PLANNING"

    def test_invalid_setup_to_planning(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        with pytest.raises(InvalidTransitionError) as exc_info:
            sm.advance_phase(sid, Phase.PLANNING.value)
        assert "SETUP" in str(exc_info.value)
        assert "PLANNING" in str(exc_info.value)

    def test_invalid_complete_to_anything(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        update_session_phase(db_conn, sid, Phase.COMPLETE.value)
        with pytest.raises(InvalidTransitionError):
            sm.advance_phase(sid, Phase.SETUP.value)

    def test_nonexistent_session(self, sm):
        with pytest.raises(SessionNotFoundError):
            sm.advance_phase("nonexistent", Phase.CONTEXT.value)


class TestCheckCommand:
    """Tests for SessionManager.check_command()."""

    def test_export_always_allowed(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        # export allowed in SETUP
        sm.check_command(sid, "export")
        # export allowed when PAUSED
        update_session_status(db_conn, sid, Status.PAUSED.value)
        sm.check_command(sid, "export")

    def test_add_context_allowed_in_setup(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        sm.check_command(sid, "add-context")  # should not raise

    def test_add_context_allowed_in_context_phase(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        update_session_phase(db_conn, sid, Phase.CONTEXT.value)
        sm.check_command(sid, "add-context")  # should not raise

    def test_add_context_blocked_in_discussion(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        update_session_phase(db_conn, sid, Phase.DISCUSSION.value)
        with pytest.raises(CommandNotAllowedError):
            sm.check_command(sid, "add-context")

    def test_discuss_allowed_in_discussion(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        update_session_phase(db_conn, sid, Phase.DISCUSSION.value)
        sm.check_command(sid, "discuss")  # should not raise

    def test_discuss_blocked_in_setup(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        with pytest.raises(CommandNotAllowedError):
            sm.check_command(sid, "discuss")

    def test_generate_allowed_in_planning(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        update_session_phase(db_conn, sid, Phase.PLANNING.value)
        sm.check_command(sid, "generate")  # should not raise

    def test_generate_blocked_in_discussion(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        update_session_phase(db_conn, sid, Phase.DISCUSSION.value)
        with pytest.raises(CommandNotAllowedError):
            sm.check_command(sid, "generate")

    def test_paused_only_allows_resume_status_export(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        update_session_status(db_conn, sid, Status.PAUSED.value)
        # Allowed
        sm.check_command(sid, "resume")
        sm.check_command(sid, "status")
        sm.check_command(sid, "export")
        # Blocked
        with pytest.raises(CommandNotAllowedError) as exc_info:
            sm.check_command(sid, "add-context")
        assert "PAUSED" in str(exc_info.value)

    def test_complete_blocked_by_open_blockers(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        create_blocker(db_conn, sid, "planner", "Which DB?")
        with pytest.raises(CommandNotAllowedError) as exc_info:
            sm.check_command(sid, "complete")
        assert "open blocker" in str(exc_info.value)

    def test_complete_allowed_with_no_blockers(self, sm, db_conn):
        sid = create_session(db_conn, "myapp")
        sm.check_command(sid, "complete")  # should not raise

    def test_nonexistent_session(self, sm):
        with pytest.raises(SessionNotFoundError):
            sm.check_command("nonexistent", "status")
