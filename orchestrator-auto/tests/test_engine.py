"""
Unit tests for orchestrator engine.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path
import sys
import tempfile
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto.engine import Orchestrator
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


class TestOrchestratorInitialization:
    """Test orchestrator initialization."""

    def test_create_new_session(self, temp_db):
        """Test creating a new orchestrator session."""
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None  # Suppress output
        )

        assert orch.session_id is not None
        assert orch.state is not None
        assert orch.state.phase == "discovery"

    def test_resume_existing_session(self, temp_db):
        """Test resuming an existing session."""
        # Create a session first
        orch1 = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )
        session_id = orch1.session_id

        # Resume it
        orch2 = Orchestrator(
            session_id=session_id,
            db_path=temp_db,
            on_output=lambda x: None
        )

        assert orch2.session_id == session_id
        assert orch2.state.phase == "discovery"

    def test_resume_nonexistent_session(self, temp_db):
        """Test resuming a session that doesn't exist."""
        with pytest.raises(ValueError, match="not found"):
            Orchestrator(
                session_id="nonexistent",
                db_path=temp_db,
                on_output=lambda x: None
            )

    def test_init_without_params(self, temp_db):
        """Test initialization without required params."""
        with pytest.raises(ValueError, match="Must provide"):
            Orchestrator(db_path=temp_db, on_output=lambda x: None)


class TestOrchestratorPlanning:
    """Test planning phase."""

    @patch("orchestrator_auto.engine.create_planner_agent")
    def test_planning_with_plan_ready(self, mock_create_planner, temp_db):
        """Test planning phase with successful plan creation."""
        # Setup mocks
        mock_planner = Mock()
        mock_result = Mock()
        mock_result.content = """
        [PLAN_READY] Implementation plan created at: docs/test/DOC_test_plan.md
        Milestones: 3 total

        Plan is ready for execution.
        """
        mock_result.usage = {"total_tokens": 100}
        mock_planner.send_message.return_value = mock_result
        mock_create_planner.return_value = mock_planner

        # Create orchestrator in planning phase
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )

        # Transition to planning
        db.update_session(
            orch.session_id,
            {"phase": "planning"},
            temp_db
        )
        orch.state = orch.state_machine.get_state(orch.session_id)

        # Run planning
        orch._run_planning()

        # Verify state transition
        assert orch.state.phase == "execution"
        assert orch.state.total_milestones == 3
        assert "docs/test/DOC_test_plan.md" in orch.state.plan_path

    @patch("orchestrator_auto.engine.create_planner_agent")
    def test_planning_with_blocker(self, mock_create_planner, temp_db):
        """Test planning phase with blocker."""
        # Setup mocks
        mock_planner = Mock()
        mock_result = Mock()
        mock_result.content = """
        [HUMAN_INPUT_NEEDED] Which database should we use - PostgreSQL or MySQL?

        Please clarify before I create the plan.
        """
        mock_result.usage = {"total_tokens": 50}
        mock_planner.send_message.return_value = mock_result
        mock_create_planner.return_value = mock_planner

        # Create orchestrator
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )

        # Transition to planning
        db.update_session(orch.session_id, {"phase": "planning"}, temp_db)
        orch.state = orch.state_machine.get_state(orch.session_id)

        # Run planning
        orch._run_planning()

        # Verify paused
        assert orch.state.phase == "paused"

        # Verify blocker created
        blockers = db.get_unresolved_blockers(orch.session_id, temp_db)
        assert len(blockers) > 0


class TestOrchestratorExecution:
    """Test execution phase."""

    @patch("orchestrator_auto.engine.create_executor_agent")
    @patch("orchestrator_auto.engine.create_planner_agent")
    def test_execution_milestone_approved(self, mock_create_planner, mock_create_executor, temp_db):
        """Test execution with milestone approval."""
        # Setup executor mock
        mock_executor = Mock()
        mock_executor_result = Mock()
        mock_executor_result.content = """
        [PROGRESS_REPORT]
        ## Milestone 1: Setup - COMPLETED

        ### Files Created/Modified:
        - setup.py (created)

        ### Test Results:
        All tests passing

        ### Ready for Review: YES
        [/PROGRESS_REPORT]
        """
        mock_executor_result.usage = {"total_tokens": 150}
        mock_executor.send_message.return_value = mock_executor_result
        mock_create_executor.return_value = mock_executor

        # Setup planner mock
        mock_planner = Mock()
        mock_planner_result = Mock()
        mock_planner_result.content = "[MILESTONE_APPROVED] Milestone 1 approved. Proceed to Milestone 2."
        mock_planner_result.usage = {"total_tokens": 30}
        mock_planner.send_message.return_value = mock_planner_result
        mock_create_planner.return_value = mock_planner

        # Create orchestrator in execution phase
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )

        # Setup execution state
        db.update_session(
            orch.session_id,
            {
                "phase": "execution",
                "plan_path": "docs/test/plan.md",
                "current_milestone": 1,
                "total_milestones": 1
            },
            temp_db
        )
        orch.state = orch.state_machine.get_state(orch.session_id)

        # Run execution
        orch._run_execution_loop()

        # Verify completion
        assert orch.state.phase == "completed"
        assert orch.state.current_milestone == 2  # Incremented after approval

    @patch("orchestrator_auto.engine.create_executor_agent")
    @patch("orchestrator_auto.engine.create_planner_agent")
    def test_execution_changes_requested(self, mock_create_planner, mock_create_executor, temp_db):
        """Test execution with changes requested."""
        # Setup executor mock
        mock_executor = Mock()
        mock_executor_result = Mock()
        mock_executor_result.content = "I'll fix those issues."
        mock_executor_result.usage = {"total_tokens": 20}
        mock_executor.send_message.return_value = mock_executor_result
        mock_create_executor.return_value = mock_executor

        # Setup planner mock
        mock_planner = Mock()
        mock_planner_result = Mock()
        mock_planner_result.content = """
        [CHANGES_REQUESTED] Milestone 1 needs changes:
        - Fix test coverage
        - Add docstrings
        """
        mock_planner_result.usage = {"total_tokens": 40}
        mock_planner.send_message.return_value = mock_planner_result
        mock_create_planner.return_value = mock_planner

        # Create orchestrator
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )

        # Setup execution state
        db.update_session(
            orch.session_id,
            {
                "phase": "execution",
                "current_milestone": 1,
                "total_milestones": 2
            },
            temp_db
        )
        orch.state = orch.state_machine.get_state(orch.session_id)

        # Test route_to_planner with changes requested
        result = orch._route_to_planner("Test report")
        assert result == "changes_requested"

        # Verify planner was called
        assert mock_planner.send_message.called

        # Verify feedback was sent to executor (route_to_executor was called)
        assert mock_executor.send_message.called


class TestOrchestratorBlockers:
    """Test blocker handling."""

    def test_handle_blocker(self, temp_db):
        """Test handling a blocker."""
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )

        # Handle blocker
        orch._handle_blocker("planner", "Need clarification on X")

        # Verify paused
        assert orch.state.phase == "paused"

        # Verify blocker created
        blockers = db.get_unresolved_blockers(orch.session_id, temp_db)
        assert len(blockers) == 1
        assert blockers[0]["question"] == "Need clarification on X"

    @patch("orchestrator_auto.engine.create_planner_agent")
    def test_resume_from_blocker(self, mock_create_planner, temp_db):
        """Test resuming after blocker."""
        # Create orchestrator and pause it
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )

        # Create a blocker
        blocker_id = db.create_blocker(
            session_id=orch.session_id,
            agent="planner",
            question="Test question",
            db_path=temp_db
        )

        # Pause workflow
        db.update_session(
            orch.session_id,
            {"phase": "paused", "previous_phase": "discovery"},
            temp_db
        )
        orch.state = orch.state_machine.get_state(orch.session_id)

        # Mock planner for resume
        mock_planner = Mock()
        mock_create_planner.return_value = mock_planner

        # Resume with answer
        try:
            orch.resume(answer="Use PostgreSQL")
        except:
            # May fail trying to continue workflow, but that's ok for this test
            pass

        # Verify blocker resolved
        blocker = db.get_all_blockers(orch.session_id, temp_db)[0]
        assert blocker["response"] == "Use PostgreSQL"
        assert blocker["resolved_at"] is not None


class TestOrchestratorMessageRouting:
    """Test message routing between agents."""

    @patch("orchestrator_auto.engine.create_planner_agent")
    def test_route_to_planner_approved(self, mock_create_planner, temp_db):
        """Test routing report to planner with approval."""
        # Setup mock
        mock_planner = Mock()
        mock_result = Mock()
        mock_result.content = "[MILESTONE_APPROVED] Milestone 1 approved."
        mock_result.usage = {"total_tokens": 20}
        mock_planner.send_message.return_value = mock_result
        mock_create_planner.return_value = mock_planner

        # Create orchestrator
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )

        db.update_session(orch.session_id, {"current_milestone": 1}, temp_db)
        orch.state = orch.state_machine.get_state(orch.session_id)

        # Route report
        result = orch._route_to_planner("Test report")

        assert result == "approved"
        assert mock_planner.send_message.called

    @patch("orchestrator_auto.engine.create_executor_agent")
    def test_route_to_executor(self, mock_create_executor, temp_db):
        """Test routing feedback to executor."""
        # Setup mock
        mock_executor = Mock()
        mock_result = Mock()
        mock_result.content = "Understood, fixing now."
        mock_result.usage = {"total_tokens": 10}
        mock_executor.send_message.return_value = mock_result
        mock_create_executor.return_value = mock_executor

        # Create orchestrator
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )

        # Route feedback
        orch._route_to_executor("Fix issue X")

        assert mock_executor.send_message.called


class TestOrchestratorState:
    """Test orchestrator state management."""

    def test_get_status(self, temp_db):
        """Test getting workflow status."""
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )

        status = orch.get_status()

        assert status["session_id"] == orch.session_id
        assert status["phase"] == "discovery"
        assert status["status"] == "active"
        assert status["current_milestone"] == 0
        assert status["total_milestones"] == 0

    def test_cleanup(self, temp_db):
        """Test cleanup of resources."""
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )

        # Create agents
        orch.planner = Mock()
        orch.executor = Mock()

        # Cleanup
        orch._cleanup()

        # Verify close was called
        assert orch.planner.close.called
        assert orch.executor.close.called


class TestOrchestratorMessageLogging:
    """Test message logging."""

    def test_log_message(self, temp_db):
        """Test logging messages to database."""
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )

        # Log a message
        orch._log_message("planner", "assistant", "Test message", token_count=50)

        # Verify logged
        messages = db.get_messages(orch.session_id, db_path=temp_db)
        assert len(messages) == 1
        assert messages[0]["agent"] == "planner"
        assert messages[0]["content"] == "Test message"
        assert messages[0]["token_count"] == 50
