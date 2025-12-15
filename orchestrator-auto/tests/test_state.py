"""
Unit tests for state machine and workflow state management.
"""

import pytest
import tempfile
import os
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto.state import (
    WorkflowState,
    StateMachine,
    Phase,
    Status,
    TransitionEvent,
)
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


@pytest.fixture
def session_id(temp_db):
    """Create a test session."""
    session_id = db.create_session(
        feature_description="Test feature",
        db_path=temp_db
    )
    return session_id


class TestWorkflowState:
    """Test WorkflowState dataclass."""

    def test_workflow_state_creation(self):
        """Test creating a WorkflowState."""
        state = WorkflowState(
            session_id="test-123",
            phase="discovery",
            status="active",
            current_milestone=0,
            total_milestones=5,
        )

        assert state.session_id == "test-123"
        assert state.phase == "discovery"
        assert state.status == "active"
        assert state.current_milestone == 0
        assert state.total_milestones == 5

    def test_from_db(self):
        """Test creating WorkflowState from database data."""
        db_data = {
            "id": "test-456",
            "phase": "execution",
            "status": "active",
            "current_milestone": 2,
            "total_milestones": 5,
            "plan_path": "docs/test/plan.md",
            "feature_description": "Test feature",
        }

        state = WorkflowState.from_db(db_data)

        assert state.session_id == "test-456"
        assert state.phase == "execution"
        assert state.current_milestone == 2
        assert state.plan_path == "docs/test/plan.md"

    def test_to_db_update(self):
        """Test converting WorkflowState to database update dict."""
        state = WorkflowState(
            session_id="test-789",
            phase="planning",
            status="active",
            plan_path="docs/feature/plan.md",
            total_milestones=4,
        )

        update = state.to_db_update()

        assert "phase" in update
        assert "status" in update
        assert "plan_path" in update
        assert update["phase"] == "planning"
        assert update["total_milestones"] == 4


class TestStateMachine:
    """Test StateMachine transitions."""

    def test_get_state(self, temp_db, session_id):
        """Test loading state from database."""
        sm = StateMachine(db_path=temp_db)
        state = sm.get_state(session_id)

        assert state is not None
        assert state.session_id == session_id
        assert state.phase == "discovery"
        assert state.status == "active"

    def test_get_state_nonexistent(self, temp_db):
        """Test loading non-existent session."""
        sm = StateMachine(db_path=temp_db)
        state = sm.get_state("nonexistent")

        assert state is None

    def test_can_transition_valid(self, temp_db):
        """Test checking valid transitions."""
        sm = StateMachine(db_path=temp_db)

        # Valid transitions
        assert sm.can_transition("discovery", "ready")
        assert sm.can_transition("planning", "plan_approved")
        assert sm.can_transition("execution", "milestone_approved")
        assert sm.can_transition("execution", "all_milestones_done")
        assert sm.can_transition("discovery", "human_input_needed")

    def test_can_transition_invalid(self, temp_db):
        """Test checking invalid transitions."""
        sm = StateMachine(db_path=temp_db)

        # Invalid transitions
        assert not sm.can_transition("discovery", "plan_approved")
        assert not sm.can_transition("planning", "milestone_approved")
        assert not sm.can_transition("completed", "ready")

    def test_transition_discovery_to_planning(self, temp_db, session_id):
        """Test transition from discovery to planning."""
        sm = StateMachine(db_path=temp_db)

        success, state, error = sm.transition(session_id, "ready")

        assert success
        assert error is None
        assert state.phase == "planning"
        assert state.status == "active"

    def test_transition_planning_to_execution(self, temp_db, session_id):
        """Test transition from planning to execution."""
        sm = StateMachine(db_path=temp_db)

        # First transition to planning
        sm.transition(session_id, "ready")

        # Then to execution
        success, state, error = sm.transition(
            session_id,
            "plan_approved",
            plan_path="docs/test/plan.md",
            total_milestones=5
        )

        assert success
        assert error is None
        assert state.phase == "execution"
        assert state.plan_path == "docs/test/plan.md"
        assert state.total_milestones == 5

    def test_transition_milestone_approved(self, temp_db, session_id):
        """Test milestone approval transition."""
        sm = StateMachine(db_path=temp_db)

        # Setup: get to execution phase
        sm.transition(session_id, "ready")
        sm.transition(session_id, "plan_approved", total_milestones=5)

        # Approve milestone
        success, state, error = sm.transition(
            session_id,
            "milestone_approved",
            current_milestone=1
        )

        assert success
        assert error is None
        assert state.phase == "execution"
        assert state.current_milestone == 2  # Incremented

    def test_transition_all_milestones_done(self, temp_db, session_id):
        """Test completing all milestones."""
        sm = StateMachine(db_path=temp_db)

        # Setup: get to execution phase
        sm.transition(session_id, "ready")
        sm.transition(session_id, "plan_approved", total_milestones=3)

        # Complete all milestones
        success, state, error = sm.transition(
            session_id,
            "all_milestones_done"
        )

        assert success
        assert error is None
        assert state.phase == "completed"
        assert state.status == "completed"

    def test_transition_to_paused(self, temp_db, session_id):
        """Test pausing the workflow."""
        sm = StateMachine(db_path=temp_db)

        # Pause from discovery
        success, state, error = sm.transition(
            session_id,
            "human_input_needed"
        )

        assert success
        assert error is None
        assert state.phase == "paused"
        assert state.status == "paused"
        assert state.previous_phase == "discovery"

    def test_transition_resume_from_paused(self, temp_db, session_id):
        """Test resuming from paused state."""
        sm = StateMachine(db_path=temp_db)

        # First pause
        sm.transition(session_id, "human_input_needed")

        # Then resume
        success, state, error = sm.transition(
            session_id,
            "human_responded"
        )

        assert success
        assert error is None
        assert state.phase == "discovery"  # Back to previous phase
        assert state.status == "active"
        assert state.previous_phase is None

    def test_transition_invalid(self, temp_db, session_id):
        """Test invalid transition."""
        sm = StateMachine(db_path=temp_db)

        # Try invalid transition
        success, state, error = sm.transition(
            session_id,
            "plan_approved"  # Can't approve plan from discovery
        )

        assert not success
        assert error is not None
        assert "Invalid transition" in error
        assert state.phase == "discovery"  # Phase unchanged

    def test_transition_failed(self, temp_db, session_id):
        """Test marking workflow as failed."""
        sm = StateMachine(db_path=temp_db)

        success, state, error = sm.transition(
            session_id,
            "failed"
        )

        assert success
        assert error is None
        assert state.phase == "completed"
        assert state.status == "failed"

    def test_reset_to_phase(self, temp_db, session_id):
        """Test resetting workflow to a specific phase."""
        sm = StateMachine(db_path=temp_db)

        # Transition to planning
        sm.transition(session_id, "ready")

        # Reset back to discovery
        success, state, error = sm.reset_to_phase(session_id, "discovery")

        assert success
        assert error is None
        assert state.phase == "discovery"
        assert state.status == "active"

    def test_reset_to_invalid_phase(self, temp_db, session_id):
        """Test resetting to invalid phase."""
        sm = StateMachine(db_path=temp_db)

        success, state, error = sm.reset_to_phase(session_id, "invalid_phase")

        assert not success
        assert error is not None
        assert "Invalid phase" in error

    def test_complex_workflow(self, temp_db, session_id):
        """Test a complete workflow sequence."""
        sm = StateMachine(db_path=temp_db)

        # Discovery → Planning
        success, state, _ = sm.transition(session_id, "ready")
        assert success and state.phase == "planning"

        # Planning → Execution
        success, state, _ = sm.transition(
            session_id,
            "plan_approved",
            total_milestones=3
        )
        assert success and state.phase == "execution"

        # Milestone 1 approved
        success, state, _ = sm.transition(
            session_id,
            "milestone_approved",
            current_milestone=1
        )
        assert success and state.current_milestone == 2

        # Pause for human input
        success, state, _ = sm.transition(session_id, "human_input_needed")
        assert success and state.phase == "paused"

        # Resume
        success, state, _ = sm.transition(session_id, "human_responded")
        assert success and state.phase == "execution"

        # Milestone 2 approved
        success, state, _ = sm.transition(
            session_id,
            "milestone_approved",
            current_milestone=2
        )
        assert success and state.current_milestone == 3

        # All milestones done
        success, state, _ = sm.transition(session_id, "all_milestones_done")
        assert success and state.phase == "completed"
        assert state.status == "completed"
