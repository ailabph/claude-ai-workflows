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
            planner_model="claude-opus-4-6",
            executor_model="claude-sonnet-4-6",
            db_path=temp_db
        )

        session = db.get_session(session_id, temp_db)

        assert session is not None
        assert session["planner_model"] == "claude-opus-4-6"
        assert session["executor_model"] == "claude-sonnet-4-6"

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


class TestHeartbeatAndStuckSessions:
    """Test heartbeat functionality and stuck session detection."""

    def test_touch_session_updates_heartbeat(self, temp_db):
        """Test that touch_session updates heartbeat_at."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        # Get initial heartbeat
        session = db.get_session(session_id, temp_db)
        initial_heartbeat = session.get('heartbeat_at')
        assert initial_heartbeat is not None

        # Touch session
        import time
        time.sleep(0.1)  # Small delay to ensure different timestamp
        db.touch_session(session_id, temp_db)

        # Verify heartbeat was updated
        session = db.get_session(session_id, temp_db)
        new_heartbeat = session.get('heartbeat_at')
        assert new_heartbeat is not None
        assert new_heartbeat >= initial_heartbeat

    def test_create_session_sets_heartbeat(self, temp_db):
        """Test that create_session sets initial heartbeat_at."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        session = db.get_session(session_id, temp_db)
        assert session.get('heartbeat_at') is not None

    def test_stuck_detection_returns_old_heartbeat_sessions(self, temp_db):
        """Test stuck detection returns sessions with old heartbeat."""
        from datetime import datetime, timedelta

        # Create a session with old heartbeat
        session_id = db.create_session("Test feature", db_path=temp_db)

        # Manually set old heartbeat (30 minutes ago)
        old_time = (datetime.now() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        db.update_session(session_id, {
            'phase': 'execution',
            'status': 'active',
            'heartbeat_at': old_time
        }, temp_db)

        # Check stuck sessions with 20 minute threshold
        stuck = db.get_stuck_sessions(temp_db, inactive_minutes=20)

        assert len(stuck) == 1
        assert stuck[0]['id'] == session_id

    def test_stuck_detection_excludes_recent_heartbeat(self, temp_db):
        """Test that sessions with recent heartbeat are not flagged as stuck."""
        # Create a session
        session_id = db.create_session("Test feature", db_path=temp_db)

        # Update to execution phase (keeps recent heartbeat)
        db.update_session(session_id, {
            'phase': 'execution',
            'status': 'active'
        }, temp_db)
        db.touch_session(session_id, temp_db)

        # Check stuck sessions - should not include this session
        stuck = db.get_stuck_sessions(temp_db, inactive_minutes=20)

        assert len(stuck) == 0

    def test_stuck_detection_excludes_discovery_phase(self, temp_db):
        """Test that discovery phase sessions are not flagged as stuck."""
        from datetime import datetime, timedelta

        # Create a session in discovery phase with old heartbeat
        session_id = db.create_session("Test feature", db_path=temp_db)

        old_time = (datetime.now() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        db.update_session(session_id, {
            'phase': 'discovery',  # Discovery is excluded
            'status': 'active',
            'heartbeat_at': old_time
        }, temp_db)

        stuck = db.get_stuck_sessions(temp_db, inactive_minutes=20)

        assert len(stuck) == 0

    def test_stuck_detection_excludes_paused_phase(self, temp_db):
        """Test that paused sessions are not flagged as stuck."""
        from datetime import datetime, timedelta

        session_id = db.create_session("Test feature", db_path=temp_db)

        old_time = (datetime.now() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        db.update_session(session_id, {
            'phase': 'paused',
            'status': 'paused',
            'heartbeat_at': old_time
        }, temp_db)

        stuck = db.get_stuck_sessions(temp_db, inactive_minutes=20)

        assert len(stuck) == 0

    def test_stuck_detection_falls_back_to_updated_at(self, temp_db):
        """Test that stuck detection uses updated_at when heartbeat_at is NULL."""
        from datetime import datetime, timedelta

        session_id = db.create_session("Test feature", db_path=temp_db)

        # Set old updated_at and NULL heartbeat
        old_time = (datetime.now() - timedelta(minutes=30)).isoformat()
        with db.get_connection(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sessions
                SET phase = 'execution', status = 'active',
                    heartbeat_at = NULL, updated_at = ?
                WHERE id = ?
            """, (old_time, session_id))

        stuck = db.get_stuck_sessions(temp_db, inactive_minutes=20)

        assert len(stuck) == 1

    def test_stuck_detection_configurable_threshold(self, temp_db):
        """Test that stuck detection respects inactive_minutes parameter."""
        from datetime import datetime, timedelta

        session_id = db.create_session("Test feature", db_path=temp_db)

        # Set heartbeat to 15 minutes ago
        old_time = (datetime.now() - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        db.update_session(session_id, {
            'phase': 'execution',
            'status': 'active',
            'heartbeat_at': old_time
        }, temp_db)

        # With 20 min threshold - not stuck
        stuck_20 = db.get_stuck_sessions(temp_db, inactive_minutes=20)
        assert len(stuck_20) == 0

        # With 10 min threshold - stuck
        stuck_10 = db.get_stuck_sessions(temp_db, inactive_minutes=10)
        assert len(stuck_10) == 1


# ============================================================================
# Phase 2: Telegram State and Project Scoping Tests
# ============================================================================


class TestTelegramState:
    """Test telegram state management for polling cursor."""

    def test_get_telegram_last_update_id_initial(self, temp_db):
        """Test that initial last_update_id is 0."""
        result = db.get_telegram_last_update_id(temp_db)
        assert result == 0

    def test_set_and_get_telegram_last_update_id(self, temp_db):
        """Test setting and getting telegram update ID."""
        db.set_telegram_last_update_id(12345, temp_db)

        result = db.get_telegram_last_update_id(temp_db)
        assert result == 12345

    def test_set_telegram_last_update_id_overwrite(self, temp_db):
        """Test that setting update ID overwrites previous value."""
        db.set_telegram_last_update_id(100, temp_db)
        db.set_telegram_last_update_id(200, temp_db)

        result = db.get_telegram_last_update_id(temp_db)
        assert result == 200


class TestBlockerTelegramMessageId:
    """Test telegram message ID tracking for blockers."""

    def test_set_blocker_telegram_message_id(self, temp_db):
        """Test storing telegram message ID for a blocker."""
        session_id = db.create_session("Test feature", db_path=temp_db)
        blocker_id = db.create_blocker(session_id, "planner", "Question?", temp_db)

        db.set_blocker_telegram_message_id(blocker_id, 98765, temp_db)

        # Verify by looking up
        blocker = db.get_blocker_by_telegram_message_id(98765, temp_db)
        assert blocker is not None
        assert blocker["id"] == blocker_id

    def test_get_blocker_by_telegram_message_id_not_found(self, temp_db):
        """Test lookup returns None for unknown message ID."""
        result = db.get_blocker_by_telegram_message_id(99999, temp_db)
        assert result is None

    def test_get_blocker_by_telegram_message_id_includes_project_id(self, temp_db):
        """Test that blocker lookup includes session's project_id."""
        session_id = db.create_session(
            "Test feature",
            project_id="/path/to/project",
            db_path=temp_db
        )
        blocker_id = db.create_blocker(session_id, "planner", "Question?", temp_db)
        db.set_blocker_telegram_message_id(blocker_id, 11111, temp_db)

        blocker = db.get_blocker_by_telegram_message_id(11111, temp_db)

        assert blocker is not None
        assert blocker["project_id"] == "/path/to/project"


class TestProjectScoping:
    """Test project-based session scoping."""

    def test_create_session_with_project_id(self, temp_db):
        """Test creating session with project identity."""
        session_id = db.create_session(
            "Test feature",
            project_id="/path/to/repo",
            project_remote="git@github.com:user/repo.git",
            db_path=temp_db
        )

        session = db.get_session(session_id, temp_db)
        assert session["project_id"] == "/path/to/repo"
        assert session["project_remote"] == "git@github.com:user/repo.git"

    def test_list_sessions_filters_by_project_id(self, temp_db):
        """Test that list_sessions can filter by project_id."""
        # Create sessions for different projects
        session1 = db.create_session(
            "Feature for project A",
            project_id="/project/a",
            db_path=temp_db
        )
        session2 = db.create_session(
            "Feature for project B",
            project_id="/project/b",
            db_path=temp_db
        )
        session3 = db.create_session(
            "Another feature for project A",
            project_id="/project/a",
            db_path=temp_db
        )

        # List only project A sessions
        project_a_sessions = db.list_sessions(temp_db, project_id="/project/a")
        assert len(project_a_sessions) == 2

        # List only project B sessions
        project_b_sessions = db.list_sessions(temp_db, project_id="/project/b")
        assert len(project_b_sessions) == 1

        # List all sessions (no filter)
        all_sessions = db.list_sessions(temp_db)
        assert len(all_sessions) == 3

    def test_list_sessions_combined_filters(self, temp_db):
        """Test list_sessions with both status and project_id filters."""
        from orchestrator_auto.state import Status

        # Create sessions
        session1 = db.create_session(
            "Active in A",
            project_id="/project/a",
            db_path=temp_db
        )
        session2 = db.create_session(
            "Completed in A",
            project_id="/project/a",
            db_path=temp_db
        )
        db.update_session(session2, {"status": Status.COMPLETED}, temp_db)

        session3 = db.create_session(
            "Active in B",
            project_id="/project/b",
            db_path=temp_db
        )

        # Filter: project A + active status
        active_a = db.list_sessions(temp_db, status="active", project_id="/project/a")
        assert len(active_a) == 1
        assert active_a[0]["id"] == session1

        # Filter: project A + completed status
        completed_a = db.list_sessions(temp_db, status="completed", project_id="/project/a")
        assert len(completed_a) == 1
        assert completed_a[0]["id"] == session2


# ============================================================================
# Phase 3: Queue Items Tests (Plan Queue Feature)
# ============================================================================


class TestQueueItemsTableCreation:
    """Test that queue_items table is created properly."""

    def test_queue_items_table_exists(self, temp_db):
        """Test that init_db creates queue_items table."""
        with db.get_connection(temp_db) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='queue_items'
            """)
            result = cursor.fetchone()

            assert result is not None

    def test_queue_items_indexes_exist(self, temp_db):
        """Test that queue_items indexes are created."""
        with db.get_connection(temp_db) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='index'
            """)
            indexes = {row[0] for row in cursor.fetchall()}

            assert "idx_queue_items_project_status" in indexes
            assert "idx_queue_items_session_id" in indexes


class TestQueueItemCRUD:
    """Test queue item CRUD operations."""

    def test_create_queue_item(self, temp_db):
        """Test creating a queue item."""
        item_id = db.create_queue_item(
            project_id="/project/a",
            plan_path="docs/plan1.md",
            feature_description="Feature 1",
            position=0,
            db_path=temp_db
        )

        assert item_id is not None
        assert isinstance(item_id, int)

    def test_create_multiple_queue_items(self, temp_db):
        """Test creating multiple queue items with positions."""
        id1 = db.create_queue_item(
            project_id="/project/a",
            plan_path="docs/plan1.md",
            feature_description="Feature 1",
            position=0,
            db_path=temp_db
        )
        id2 = db.create_queue_item(
            project_id="/project/a",
            plan_path="docs/plan2.md",
            feature_description="Feature 2",
            position=1,
            db_path=temp_db
        )
        id3 = db.create_queue_item(
            project_id="/project/a",
            plan_path="docs/plan3.md",
            feature_description="Feature 3",
            position=2,
            db_path=temp_db
        )

        assert id1 is not None
        assert id2 is not None
        assert id3 is not None

    def test_list_queue_items_returns_in_order(self, temp_db):
        """Test that list_queue_items returns items in position order."""
        # Create items out of order
        db.create_queue_item("/project/a", "docs/plan2.md", "Feature 2", 2, temp_db)
        db.create_queue_item("/project/a", "docs/plan0.md", "Feature 0", 0, temp_db)
        db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 1, temp_db)

        items = db.list_queue_items("/project/a", temp_db)

        assert len(items) == 3
        assert items[0]["position"] == 0
        assert items[1]["position"] == 1
        assert items[2]["position"] == 2
        assert items[0]["plan_path"] == "docs/plan0.md"
        assert items[1]["plan_path"] == "docs/plan1.md"
        assert items[2]["plan_path"] == "docs/plan2.md"

    def test_list_queue_items_filters_by_project(self, temp_db):
        """Test that list_queue_items filters by project_id."""
        # Create items for different projects
        db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)
        db.create_queue_item("/project/b", "docs/plan2.md", "Feature 2", 0, temp_db)
        db.create_queue_item("/project/a", "docs/plan3.md", "Feature 3", 1, temp_db)

        items_a = db.list_queue_items("/project/a", temp_db)
        items_b = db.list_queue_items("/project/b", temp_db)

        assert len(items_a) == 2
        assert len(items_b) == 1
        assert items_a[0]["project_id"] == "/project/a"
        assert items_b[0]["project_id"] == "/project/b"

    def test_list_queue_items_include_completed_false(self, temp_db):
        """Test that include_completed=False excludes completed/failed items."""
        id1 = db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)
        id2 = db.create_queue_item("/project/a", "docs/plan2.md", "Feature 2", 1, temp_db)
        id3 = db.create_queue_item("/project/a", "docs/plan3.md", "Feature 3", 2, temp_db)

        # Mark some as completed/failed
        db.update_queue_item(id1, temp_db, status="completed")
        db.update_queue_item(id3, temp_db, status="failed")

        # With include_completed=True (default)
        all_items = db.list_queue_items("/project/a", temp_db, include_completed=True)
        assert len(all_items) == 3

        # With include_completed=False
        active_items = db.list_queue_items("/project/a", temp_db, include_completed=False)
        assert len(active_items) == 1
        assert active_items[0]["id"] == id2
        assert active_items[0]["status"] == "pending"

    def test_get_next_queue_item_returns_first_pending(self, temp_db):
        """Test that get_next_queue_item returns first pending by position."""
        id1 = db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)
        id2 = db.create_queue_item("/project/a", "docs/plan2.md", "Feature 2", 1, temp_db)
        id3 = db.create_queue_item("/project/a", "docs/plan3.md", "Feature 3", 2, temp_db)

        next_item = db.get_next_queue_item("/project/a", temp_db)

        assert next_item is not None
        assert next_item["id"] == id1
        assert next_item["position"] == 0
        assert next_item["status"] == "pending"

    def test_get_next_queue_item_skips_non_pending(self, temp_db):
        """Test that get_next_queue_item skips running/completed items."""
        id1 = db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)
        id2 = db.create_queue_item("/project/a", "docs/plan2.md", "Feature 2", 1, temp_db)
        id3 = db.create_queue_item("/project/a", "docs/plan3.md", "Feature 3", 2, temp_db)

        # Mark first two as non-pending
        db.update_queue_item(id1, temp_db, status="completed")
        db.update_queue_item(id2, temp_db, status="running")

        next_item = db.get_next_queue_item("/project/a", temp_db)

        assert next_item is not None
        assert next_item["id"] == id3
        assert next_item["position"] == 2

    def test_get_next_queue_item_returns_none_when_empty(self, temp_db):
        """Test that get_next_queue_item returns None when no pending items."""
        next_item = db.get_next_queue_item("/project/a", temp_db)
        assert next_item is None

    def test_get_next_queue_item_returns_none_when_all_completed(self, temp_db):
        """Test that get_next_queue_item returns None when all items completed."""
        id1 = db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)
        db.update_queue_item(id1, temp_db, status="completed")

        next_item = db.get_next_queue_item("/project/a", temp_db)
        assert next_item is None

    def test_update_queue_item_status(self, temp_db):
        """Test updating queue item status."""
        item_id = db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)

        result = db.update_queue_item(item_id, temp_db, status="running")

        assert result is True

        items = db.list_queue_items("/project/a", temp_db)
        assert items[0]["status"] == "running"

    def test_update_queue_item_session_id(self, temp_db):
        """Test updating queue item with session_id."""
        item_id = db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)

        result = db.update_queue_item(item_id, temp_db, session_id="abc123")

        assert result is True

        items = db.list_queue_items("/project/a", temp_db)
        assert items[0]["session_id"] == "abc123"

    def test_update_queue_item_multiple_fields(self, temp_db):
        """Test updating multiple queue item fields at once."""
        item_id = db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)

        result = db.update_queue_item(
            item_id,
            temp_db,
            status="running",
            session_id="abc123",
            started_at="2025-01-01 10:00:00"
        )

        assert result is True

        items = db.list_queue_items("/project/a", temp_db)
        assert items[0]["status"] == "running"
        assert items[0]["session_id"] == "abc123"
        assert items[0]["started_at"] == "2025-01-01 10:00:00"

    def test_update_queue_item_error_message(self, temp_db):
        """Test updating queue item with error message."""
        item_id = db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)

        result = db.update_queue_item(
            item_id,
            temp_db,
            status="failed",
            error_message="Plan parsing failed"
        )

        assert result is True

        items = db.list_queue_items("/project/a", temp_db)
        assert items[0]["status"] == "failed"
        assert items[0]["error_message"] == "Plan parsing failed"

    def test_update_queue_item_completed_at(self, temp_db):
        """Test updating queue item with completed_at timestamp."""
        item_id = db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)

        result = db.update_queue_item(
            item_id,
            temp_db,
            status="completed",
            completed_at="2025-01-01 12:00:00"
        )

        assert result is True

        items = db.list_queue_items("/project/a", temp_db)
        assert items[0]["status"] == "completed"
        assert items[0]["completed_at"] == "2025-01-01 12:00:00"

    def test_update_queue_item_no_updates_returns_false(self, temp_db):
        """Test that update_queue_item returns False when no updates provided."""
        item_id = db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)

        result = db.update_queue_item(item_id, temp_db)

        assert result is False

    def test_get_queue_item_by_session_id(self, temp_db):
        """Test retrieving queue item by session_id."""
        item_id = db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)
        db.update_queue_item(item_id, temp_db, session_id="abc123")

        item = db.get_queue_item_by_session_id("abc123", temp_db)

        assert item is not None
        assert item["id"] == item_id
        assert item["session_id"] == "abc123"
        assert item["plan_path"] == "docs/plan1.md"

    def test_get_queue_item_by_session_id_not_found(self, temp_db):
        """Test that get_queue_item_by_session_id returns None when not found."""
        item = db.get_queue_item_by_session_id("nonexistent", temp_db)
        assert item is None

    def test_clear_active_queue_removes_pending_running_paused(self, temp_db):
        """Test that clear_active_queue removes pending/running/paused items."""
        id1 = db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)
        id2 = db.create_queue_item("/project/a", "docs/plan2.md", "Feature 2", 1, temp_db)
        id3 = db.create_queue_item("/project/a", "docs/plan3.md", "Feature 3", 2, temp_db)
        id4 = db.create_queue_item("/project/a", "docs/plan4.md", "Feature 4", 3, temp_db)

        # Set various statuses
        db.update_queue_item(id1, temp_db, status="pending")
        db.update_queue_item(id2, temp_db, status="running")
        db.update_queue_item(id3, temp_db, status="paused")
        db.update_queue_item(id4, temp_db, status="completed")

        # Clear active queue
        count = db.clear_active_queue("/project/a", temp_db)

        assert count == 3  # Should remove pending, running, paused

        # Only completed should remain
        items = db.list_queue_items("/project/a", temp_db)
        assert len(items) == 1
        assert items[0]["id"] == id4
        assert items[0]["status"] == "completed"

    def test_clear_active_queue_retains_completed_and_failed(self, temp_db):
        """Test that clear_active_queue retains completed/failed items."""
        id1 = db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)
        id2 = db.create_queue_item("/project/a", "docs/plan2.md", "Feature 2", 1, temp_db)
        id3 = db.create_queue_item("/project/a", "docs/plan3.md", "Feature 3", 2, temp_db)

        db.update_queue_item(id1, temp_db, status="completed")
        db.update_queue_item(id2, temp_db, status="failed", error_message="Error")
        db.update_queue_item(id3, temp_db, status="pending")

        count = db.clear_active_queue("/project/a", temp_db)

        assert count == 1  # Only pending removed

        items = db.list_queue_items("/project/a", temp_db)
        assert len(items) == 2
        assert items[0]["status"] == "completed"
        assert items[1]["status"] == "failed"

    def test_clear_active_queue_scoped_by_project(self, temp_db):
        """Test that clear_active_queue only affects specified project."""
        # Create items for two projects
        db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)
        db.create_queue_item("/project/b", "docs/plan2.md", "Feature 2", 0, temp_db)

        # Clear project A
        count = db.clear_active_queue("/project/a", temp_db)

        assert count == 1

        # Project A should be empty
        items_a = db.list_queue_items("/project/a", temp_db)
        assert len(items_a) == 0

        # Project B should be unaffected
        items_b = db.list_queue_items("/project/b", temp_db)
        assert len(items_b) == 1

    def test_clear_active_queue_returns_zero_when_empty(self, temp_db):
        """Test that clear_active_queue returns 0 when no items to clear."""
        count = db.clear_active_queue("/project/a", temp_db)
        assert count == 0


# ============================================================================
# MCP Configuration Persistence Tests
# ============================================================================


class TestMcpConfigPersistence:
    """Test MCP configuration persistence in sessions."""

    def test_create_session_without_mcp_config(self, temp_db):
        """Test creating session without MCP config stores NULL."""
        session_id = db.create_session(
            feature_description="Test feature",
            db_path=temp_db
        )

        mcp_config = db.get_session_mcp_config(session_id, temp_db)
        assert mcp_config is None

    def test_create_session_with_mcp_config(self, temp_db):
        """Test creating session with MCP config stores JSON.

        Note: Engine persists config as {"servers": ..., "planner": ..., "executor": ...}
        which is the transformed format, not the raw .mcp.json format.
        """
        # Use the format engine.py actually persists (see engine.py:291-295)
        mcp_config = {
            "servers": {
                "playwright": {
                    "command": "npx",
                    "args": ["@anthropic/mcp-server-playwright"]
                }
            },
            "planner": {},
            "executor": {},
        }

        session_id = db.create_session(
            feature_description="Test feature",
            mcp_config=mcp_config,
            db_path=temp_db
        )

        retrieved = db.get_session_mcp_config(session_id, temp_db)

        assert retrieved is not None
        assert "servers" in retrieved
        assert "playwright" in retrieved["servers"]
        assert retrieved["servers"]["playwright"]["command"] == "npx"

    def test_create_session_with_complex_mcp_config(self, temp_db):
        """Test creating session with multiple MCP servers and per-agent config.

        Note: Engine persists config as {"servers": ..., "planner": ..., "executor": ...}
        which is the transformed format from load_mcp_config_raw().
        """
        # Use the format engine.py actually persists (see engine.py:291-295)
        mcp_config = {
            "servers": {
                "playwright": {
                    "command": "npx",
                    "args": ["@anthropic/mcp-server-playwright"],
                    "env": {
                        "PLAYWRIGHT_HEADLESS": "true"
                    }
                },
                "figma": {
                    "command": "figma-mcp",
                    "args": [],
                    "env": {
                        "FIGMA_ACCESS_TOKEN": "${FIGMA_TOKEN}"
                    }
                }
            },
            "planner": {
                "mcpServers": ["figma"]
            },
            "executor": {
                "mcpServers": ["playwright"]
            },
        }

        session_id = db.create_session(
            feature_description="Test feature",
            mcp_config=mcp_config,
            db_path=temp_db
        )

        retrieved = db.get_session_mcp_config(session_id, temp_db)

        assert retrieved is not None
        assert len(retrieved["servers"]) == 2
        assert "playwright" in retrieved["servers"]
        assert "figma" in retrieved["servers"]
        assert retrieved["planner"]["mcpServers"] == ["figma"]
        assert retrieved["executor"]["mcpServers"] == ["playwright"]
        # Verify env vars are stored raw (not expanded)
        assert retrieved["servers"]["figma"]["env"]["FIGMA_ACCESS_TOKEN"] == "${FIGMA_TOKEN}"

    def test_get_session_mcp_config_nonexistent_session(self, temp_db):
        """Test get_session_mcp_config returns None for nonexistent session."""
        mcp_config = db.get_session_mcp_config("nonexistent", temp_db)
        assert mcp_config is None

    def test_mcp_config_column_exists(self, temp_db):
        """Test that mcp_config_json column exists in sessions table."""
        with db.get_connection(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(sessions)")
            columns = {row[1] for row in cursor.fetchall()}

        assert "mcp_config_json" in columns

    def test_create_session_with_empty_mcp_config(self, temp_db):
        """Test creating session with empty MCP config dict."""
        # Engine format with empty servers
        mcp_config = {"servers": {}, "planner": None, "executor": None}

        session_id = db.create_session(
            feature_description="Test feature",
            mcp_config=mcp_config,
            db_path=temp_db
        )

        retrieved = db.get_session_mcp_config(session_id, temp_db)

        assert retrieved is not None
        assert retrieved["servers"] == {}

    def test_mcp_config_persists_across_reconnection(self, temp_db):
        """Test that MCP config persists after closing and reopening connection."""
        # Engine format
        mcp_config = {
            "servers": {
                "test-server": {"command": "test-cmd"}
            },
            "planner": {},
            "executor": {},
        }

        session_id = db.create_session(
            feature_description="Test feature",
            mcp_config=mcp_config,
            db_path=temp_db
        )

        # Close connection explicitly (context manager handles it)
        # Then retrieve again - simulating a resume scenario
        retrieved = db.get_session_mcp_config(session_id, temp_db)

        assert retrieved is not None
        assert retrieved["servers"]["test-server"]["command"] == "test-cmd"


# ============================================================================
# Tool Invocations Tests (SDK 0.1.22+)
# ============================================================================


class TestToolInvocationsTable:
    """Test tool_invocations table creation."""

    def test_tool_invocations_table_exists(self, temp_db):
        """Test that init_db creates tool_invocations table."""
        with db.get_connection(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='tool_invocations'
            """)
            result = cursor.fetchone()
            assert result is not None

    def test_tool_invocations_index_exists(self, temp_db):
        """Test that tool_invocations index is created."""
        with db.get_connection(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='index' AND name='idx_tool_invocations_session_id'
            """)
            result = cursor.fetchone()
            assert result is not None


class TestToolInvocationsCRUD:
    """Test tool invocations CRUD operations."""

    def test_save_tool_invocation(self, temp_db):
        """Test saving a single tool invocation."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        inv_id = db.save_tool_invocation(
            session_id=session_id,
            agent="executor",
            tool_name="Read",
            milestone_number=1,
            input_summary="/path/to/file.py",
            output_summary="File contents...",
            success=True,
            db_path=temp_db
        )

        assert inv_id is not None
        assert isinstance(inv_id, int)

    def test_get_tool_invocations(self, temp_db):
        """Test retrieving tool invocations."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        db.save_tool_invocation(
            session_id=session_id,
            agent="executor",
            tool_name="Read",
            milestone_number=1,
            db_path=temp_db
        )
        db.save_tool_invocation(
            session_id=session_id,
            agent="executor",
            tool_name="Write",
            milestone_number=1,
            db_path=temp_db
        )

        invocations = db.get_tool_invocations(session_id, db_path=temp_db)

        assert len(invocations) == 2
        assert invocations[0]["tool_name"] == "Read"
        assert invocations[1]["tool_name"] == "Write"

    def test_get_tool_invocations_filter_by_agent(self, temp_db):
        """Test filtering tool invocations by agent."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        db.save_tool_invocation(session_id, "planner", "Read", db_path=temp_db)
        db.save_tool_invocation(session_id, "executor", "Write", db_path=temp_db)
        db.save_tool_invocation(session_id, "executor", "Edit", db_path=temp_db)

        executor_invs = db.get_tool_invocations(session_id, agent="executor", db_path=temp_db)
        planner_invs = db.get_tool_invocations(session_id, agent="planner", db_path=temp_db)

        assert len(executor_invs) == 2
        assert len(planner_invs) == 1

    def test_get_tool_invocations_filter_by_milestone(self, temp_db):
        """Test filtering tool invocations by milestone."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        db.save_tool_invocation(session_id, "executor", "Read", milestone_number=1, db_path=temp_db)
        db.save_tool_invocation(session_id, "executor", "Write", milestone_number=1, db_path=temp_db)
        db.save_tool_invocation(session_id, "executor", "Edit", milestone_number=2, db_path=temp_db)

        m1_invs = db.get_tool_invocations(session_id, milestone_number=1, db_path=temp_db)
        m2_invs = db.get_tool_invocations(session_id, milestone_number=2, db_path=temp_db)

        assert len(m1_invs) == 2
        assert len(m2_invs) == 1

    def test_save_tool_invocations_batch(self, temp_db):
        """Test saving multiple tool invocations in batch."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        invocations = [
            {"tool_name": "Read", "input": "/file1.py", "output": "content1", "success": True},
            {"tool_name": "Write", "input": "/file2.py", "output": "ok", "success": True},
            {"tool_name": "Bash", "input": "ls", "output": "files", "success": False},
        ]

        count = db.save_tool_invocations_batch(
            session_id=session_id,
            agent="executor",
            invocations=invocations,
            milestone_number=1,
            db_path=temp_db
        )

        assert count == 3

        retrieved = db.get_tool_invocations(session_id, db_path=temp_db)
        assert len(retrieved) == 3
        assert retrieved[2]["success"] == 0  # False stored as 0

    def test_save_tool_invocations_batch_empty(self, temp_db):
        """Test batch save with empty list returns 0."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        count = db.save_tool_invocations_batch(
            session_id=session_id,
            agent="executor",
            invocations=[],
            db_path=temp_db
        )

        assert count == 0

    def test_tool_invocation_truncates_long_strings(self, temp_db):
        """Test that long input/output strings are truncated."""
        session_id = db.create_session("Test feature", db_path=temp_db)

        long_input = "x" * 1000
        long_output = "y" * 2000

        invocations = [
            {"tool_name": "Read", "input": long_input, "output": long_output, "success": True},
        ]

        db.save_tool_invocations_batch(
            session_id=session_id,
            agent="executor",
            invocations=invocations,
            db_path=temp_db
        )

        retrieved = db.get_tool_invocations(session_id, db_path=temp_db)

        # Input truncated to 500 chars
        assert len(retrieved[0]["input_summary"]) == 500
        assert retrieved[0]["input_summary"].endswith("...")

        # Output truncated to 1000 chars
        assert len(retrieved[0]["output_summary"]) == 1000
        assert retrieved[0]["output_summary"].endswith("...")
