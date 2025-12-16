"""
Unit tests for database operations.
"""

import pytest
import tempfile
import os
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto import db


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)

    # Initialize the database
    db.init_db(path)

    yield path

    # Cleanup
    os.unlink(path)


class TestDatabaseInitialization:
    """Test database initialization."""

    def test_init_db_creates_tables(self, temp_db):
        """Test that init_db creates all required tables."""
        with db.get_connection(temp_db) as conn:
            cursor = conn.cursor()

            # Check that all tables exist
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table'
            """)
            tables = {row[0] for row in cursor.fetchall()}

            assert "sessions" in tables
            assert "messages" in tables
            assert "milestones" in tables
            assert "blockers" in tables

    def test_init_db_creates_indexes(self, temp_db):
        """Test that init_db creates indexes."""
        with db.get_connection(temp_db) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='index'
            """)
            indexes = {row[0] for row in cursor.fetchall()}

            assert "idx_messages_session" in indexes
            assert "idx_milestones_session" in indexes

    def test_init_db_idempotent(self, temp_db):
        """Test that init_db can be called multiple times safely."""
        # Should not raise any errors
        db.init_db(temp_db)
        db.init_db(temp_db)


class TestSessionCRUD:
    """Test session CRUD operations."""

    def test_create_session(self, temp_db):
        """Test creating a new session."""
        session_id = db.create_session(
            feature_description="Test feature",
            db_path=temp_db
        )

        assert session_id is not None
        assert len(session_id) == 8  # Short UUID

    def test_get_session(self, temp_db):
        """Test retrieving a session."""
        session_id = db.create_session(
            feature_description="Test feature",
            db_path=temp_db
        )

        session = db.get_session(session_id, temp_db)

        assert session is not None
        assert session["id"] == session_id
        assert session["feature_description"] == "Test feature"
        assert session["phase"] == "discovery"
        assert session["status"] == "active"

    def test_get_nonexistent_session(self, temp_db):
        """Test retrieving a session that doesn't exist."""
        session = db.get_session("nonexistent", temp_db)
        assert session is None

    def test_update_session(self, temp_db):
        """Test updating session fields."""
        session_id = db.create_session(
            feature_description="Test feature",
            db_path=temp_db
        )

        db.update_session(
            session_id,
            {
                "phase": "planning",
                "plan_path": "docs/test/plan.md",
                "total_milestones": 5
            },
            temp_db
        )

        session = db.get_session(session_id, temp_db)
        assert session["phase"] == "planning"
        assert session["plan_path"] == "docs/test/plan.md"
        assert session["total_milestones"] == 5

    def test_list_sessions(self, temp_db):
        """Test listing all sessions."""
        # Create multiple sessions
        id1 = db.create_session("Feature 1", db_path=temp_db)
        id2 = db.create_session("Feature 2", db_path=temp_db)

        sessions = db.list_sessions(temp_db)

        assert len(sessions) == 2
        assert sessions[0]["id"] in [id1, id2]
        assert sessions[1]["id"] in [id1, id2]

    def test_list_sessions_by_status(self, temp_db):
        """Test listing sessions filtered by status."""
        id1 = db.create_session("Feature 1", db_path=temp_db)
        id2 = db.create_session("Feature 2", db_path=temp_db)

        # Update one session to completed
        db.update_session(id1, {"status": "completed"}, temp_db)

        active_sessions = db.list_sessions(temp_db, status="active")
        completed_sessions = db.list_sessions(temp_db, status="completed")

        assert len(active_sessions) == 1
        assert len(completed_sessions) == 1
        assert active_sessions[0]["id"] == id2
        assert completed_sessions[0]["id"] == id1

    def test_create_session_with_models(self, temp_db):
        """Test creating a session with model parameters."""
        session_id = db.create_session(
            feature_description="Test feature",
            planner_model="claude-opus-4-5-20251101",
            executor_model="claude-sonnet-4-5-20250929",
            db_path=temp_db
        )

        session = db.get_session(session_id, temp_db)

        assert session is not None
        assert session["planner_model"] == "claude-opus-4-5-20251101"
        assert session["executor_model"] == "claude-sonnet-4-5-20250929"

    def test_create_session_without_models(self, temp_db):
        """Test creating a session without model parameters."""
        session_id = db.create_session(
            feature_description="Test feature",
            db_path=temp_db
        )

        session = db.get_session(session_id, temp_db)

        assert session is not None
        # Models should be None when not specified
        assert session["planner_model"] is None
        assert session["executor_model"] is None


class TestMessageLogging:
    """Test message logging operations."""

    def test_log_message(self, temp_db):
        """Test logging a message."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        message_id = db.log_message(
            session_id=session_id,
            phase="discovery",
            agent="planner",
            role="user",
            content="Test message",
            token_count=10,
            db_path=temp_db
        )

        assert message_id is not None

    def test_get_messages(self, temp_db):
        """Test retrieving messages."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        db.log_message(session_id, "discovery", "planner", "user", "Message 1", db_path=temp_db)
        db.log_message(session_id, "planning", "planner", "assistant", "Message 2", db_path=temp_db)

        messages = db.get_messages(session_id, db_path=temp_db)

        assert len(messages) == 2
        assert messages[0]["content"] == "Message 1"
        assert messages[1]["content"] == "Message 2"

    def test_get_messages_by_phase(self, temp_db):
        """Test retrieving messages filtered by phase."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        db.log_message(session_id, "discovery", "planner", "user", "Message 1", db_path=temp_db)
        db.log_message(session_id, "planning", "planner", "assistant", "Message 2", db_path=temp_db)

        discovery_messages = db.get_messages(session_id, phase="discovery", db_path=temp_db)

        assert len(discovery_messages) == 1
        assert discovery_messages[0]["content"] == "Message 1"


class TestMilestoneTracking:
    """Test milestone tracking operations."""

    def test_create_milestone(self, temp_db):
        """Test creating a milestone."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        milestone_id = db.create_milestone(
            session_id=session_id,
            number=1,
            name="Setup",
            db_path=temp_db
        )

        assert milestone_id is not None

    def test_get_milestone(self, temp_db):
        """Test retrieving a milestone."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        db.create_milestone(session_id, 1, "Setup", temp_db)

        milestone = db.get_milestone(session_id, 1, temp_db)

        assert milestone is not None
        assert milestone["number"] == 1
        assert milestone["name"] == "Setup"
        assert milestone["status"] == "pending"

    def test_update_milestone(self, temp_db):
        """Test updating a milestone."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        milestone_id = db.create_milestone(session_id, 1, "Setup", temp_db)

        db.update_milestone(
            milestone_id,
            {
                "status": "completed",
                "executor_report": "All done",
                "planner_feedback": "Approved"
            },
            temp_db
        )

        milestone = db.get_milestone(session_id, 1, temp_db)

        assert milestone["status"] == "completed"
        assert milestone["executor_report"] == "All done"
        assert milestone["planner_feedback"] == "Approved"

    def test_get_milestones(self, temp_db):
        """Test retrieving all milestones for a session."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        db.create_milestone(session_id, 1, "Setup", temp_db)
        db.create_milestone(session_id, 2, "Implementation", temp_db)

        milestones = db.get_milestones(session_id, temp_db)

        assert len(milestones) == 2
        assert milestones[0]["number"] == 1
        assert milestones[1]["number"] == 2


class TestBlockerManagement:
    """Test blocker management operations."""

    def test_create_blocker(self, temp_db):
        """Test creating a blocker."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        blocker_id = db.create_blocker(
            session_id=session_id,
            agent="planner",
            question="Need clarification",
            db_path=temp_db
        )

        assert blocker_id is not None

    def test_resolve_blocker(self, temp_db):
        """Test resolving a blocker."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        blocker_id = db.create_blocker(session_id, "planner", "Question?", temp_db)

        db.resolve_blocker(blocker_id, "Here's the answer", temp_db)

        blockers = db.get_all_blockers(session_id, temp_db)

        assert len(blockers) == 1
        assert blockers[0]["response"] == "Here's the answer"
        assert blockers[0]["resolved_at"] is not None

    def test_get_unresolved_blockers(self, temp_db):
        """Test retrieving unresolved blockers."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        blocker1_id = db.create_blocker(session_id, "planner", "Question 1?", temp_db)
        blocker2_id = db.create_blocker(session_id, "executor", "Question 2?", temp_db)

        # Resolve one blocker
        db.resolve_blocker(blocker1_id, "Answer 1", temp_db)

        unresolved = db.get_unresolved_blockers(session_id, temp_db)

        assert len(unresolved) == 1
        assert unresolved[0]["id"] == blocker2_id

    def test_get_all_blockers(self, temp_db):
        """Test retrieving all blockers."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        blocker1_id = db.create_blocker(session_id, "planner", "Question 1?", temp_db)
        blocker2_id = db.create_blocker(session_id, "executor", "Question 2?", temp_db)

        db.resolve_blocker(blocker1_id, "Answer 1", temp_db)

        all_blockers = db.get_all_blockers(session_id, temp_db)

        assert len(all_blockers) == 2
