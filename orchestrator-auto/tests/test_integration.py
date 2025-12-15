"""
End-to-end integration tests for orchestrator-auto.

Tests complete workflows with mocked agent responses.
"""

import pytest
from pathlib import Path
import sys
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock, call

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto.engine import Orchestrator
from orchestrator_auto import db
from orchestrator_auto.state import Phase, Status


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


class TestFullWorkflow:
    """Test complete workflow from start to finish."""

    @patch('orchestrator_auto.engine.create_planner_agent')
    def test_complete_workflow_planning(self, mock_create_planner, temp_db):
        """Test workflow through planning phase with PLAN_CONTENT."""
        from pathlib import Path as FilePath
        import re

        # Setup planner agent mock - returns string with PLAN_CONTENT
        mock_planner = Mock()

        def mock_send_message(prompt):
            match = re.search(r'docs/([^/]+)/DOC_', prompt)
            session_id = match.group(1) if match else "test"
            return f"""
[PLAN_READY]
Path: docs/{session_id}/DOC_{session_id}_plan.md
Milestones: 3 total

[PLAN_CONTENT]
# Test Plan

## Overview
Test feature implementation

## Milestones

### Milestone 1: Setup
### Milestone 2: Implementation
### Milestone 3: Testing
[/PLAN_CONTENT]

Summary: The plan is ready for execution.
"""

        mock_planner.send_message.side_effect = mock_send_message
        mock_create_planner.return_value = mock_planner

        # Create orchestrator
        orch = Orchestrator(
            feature_description="Test feature implementation",
            db_path=temp_db,
            on_output=lambda x: None
        )
        session_id = orch.session_id
        plan_path = FilePath(f"docs/{session_id}/DOC_{session_id}_plan.md")

        try:
            # Verify initial state
            assert orch.state.phase == Phase.DISCOVERY
            assert orch.state.status == Status.ACTIVE

            # Transition to planning
            success, state, error = orch.state_machine.transition(
                orch.session_id,
                "ready"
            )
            assert success
            orch.state = state

            # Run planning
            orch._run_planning()

            # Verify transitioned to execution
            assert orch.state.phase == Phase.EXECUTION
            assert orch.state.total_milestones == 3
            assert plan_path.exists()  # Engine should have created the file

            # Verify planner was called
            assert mock_planner.send_message.called

            # Verify messages logged to database
            messages = db.get_messages(orch.session_id, db_path=temp_db)
            assert len(messages) > 0

            # Cleanup
            orch._cleanup()
        finally:
            # Cleanup the test plan file created by engine
            if plan_path.exists():
                plan_path.unlink()
            if plan_path.parent.exists():
                plan_path.parent.rmdir()

    @patch('orchestrator_auto.engine.create_executor_agent')
    @patch('orchestrator_auto.engine.create_planner_agent')
    def test_workflow_milestone_execution(self, mock_create_planner, mock_create_executor, temp_db):
        """Test single milestone execution with planner review."""

        # Setup planner agent mock - returns string directly
        mock_planner = Mock()
        mock_planner.send_message.return_value = "[MILESTONE_APPROVED] Milestone 1 approved."
        mock_create_planner.return_value = mock_planner

        # Setup executor agent mock - returns string directly
        mock_executor = Mock()
        executor_report = """
            [PROGRESS_REPORT]
            ## Milestone 1: Setup - COMPLETED

            ### Files Created/Modified:
            - setup.py (created)

            ### Test Results:
            All tests passing

            ### Ready for Review: YES
            [/PROGRESS_REPORT]
            """
        mock_executor.send_message.return_value = executor_report
        mock_create_executor.return_value = mock_executor

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
                "phase": Phase.EXECUTION,
                "current_milestone": 1,
                "total_milestones": 1,
                "plan_path": "docs/test/plan.md"
            },
            temp_db
        )
        orch.state = orch.state_machine.get_state(orch.session_id)

        # Execute routing methods directly - now returns string
        report = mock_executor.send_message("Execute milestone")
        result = orch._route_to_planner(report)

        # Verify milestone approved
        assert result == "approved"

        # Verify both agents called
        assert mock_planner.send_message.called
        assert mock_executor.send_message.called

        # Cleanup
        orch._cleanup()


class TestBlockerHandling:
    """Test blocker and pause/resume functionality."""

    @patch('orchestrator_auto.engine.create_planner_agent')
    def test_blocker_in_planning(self, mock_create_planner, temp_db):
        """Test blocker during planning phase."""

        # Setup planner mock with blocker - returns string directly
        mock_planner = Mock()
        mock_planner.send_message.return_value = """
            [HUMAN_INPUT_NEEDED] Which database should we use - PostgreSQL or MySQL?

            Please clarify before I create the plan.
            """
        mock_create_planner.return_value = mock_planner

        # Create orchestrator
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )

        # Transition to planning
        orch.state_machine.transition(orch.session_id, "ready")
        orch.state = orch.state_machine.get_state(orch.session_id)

        # Run planning (should pause on blocker)
        orch._run_planning()

        # Verify paused
        assert orch.state.phase == Phase.PAUSED
        assert orch.state.status == Status.PAUSED
        assert orch.state.previous_phase == Phase.PLANNING

        # Verify blocker created
        blockers = db.get_unresolved_blockers(orch.session_id, temp_db)
        assert len(blockers) == 1
        assert "database" in blockers[0]['question'].lower()

        # Cleanup
        orch._cleanup()

    @patch('orchestrator_auto.engine.create_executor_agent')
    @patch('orchestrator_auto.engine.create_planner_agent')
    def test_resume_from_blocker(self, mock_create_planner, mock_create_executor, temp_db):
        """Test resuming workflow after blocker resolution."""
        from pathlib import Path as FilePath
        import re

        # Track which call we're on to return different responses
        call_count = [0]
        session_id_holder = [None]

        def mock_planner_send(prompt):
            call_count[0] += 1
            # Extract session_id from prompt
            match = re.search(r'docs/([^/]+)/DOC_', prompt)
            if match:
                session_id_holder[0] = match.group(1)

            if call_count[0] == 1:
                # First call - blocker
                return "[HUMAN_INPUT_NEEDED] Need clarification on X"
            elif call_count[0] == 2:
                # Second call - plan ready with PLAN_CONTENT
                sid = session_id_holder[0] or "test"
                return f"""
[PLAN_READY]
Path: docs/{sid}/DOC_{sid}_plan.md
Milestones: 1 total

[PLAN_CONTENT]
# Test Plan

## Overview
Using the clarification provided.

## Milestones

### Milestone 1: Done
**Deliverables:**
- Feature complete
[/PLAN_CONTENT]

Summary: Plan ready.
"""
            else:
                # Third call - milestone review
                return "[MILESTONE_APPROVED] Milestone 1 approved."

        mock_planner = Mock()
        mock_planner.send_message.side_effect = mock_planner_send
        mock_create_planner.return_value = mock_planner

        # Setup executor mock - returns string directly
        mock_executor = Mock()
        mock_executor.send_message.return_value = """
            [PROGRESS_REPORT]
            ## Milestone 1: Done - COMPLETED
            [/PROGRESS_REPORT]
            """
        mock_create_executor.return_value = mock_executor

        # Create orchestrator and trigger blocker
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )
        session_id = orch.session_id
        plan_path = FilePath(f"docs/{session_id}/DOC_{session_id}_plan.md")

        try:
            # Go to planning
            orch.state_machine.transition(orch.session_id, "ready")
            orch.state = orch.state_machine.get_state(orch.session_id)
            orch._run_planning()

            # Verify paused
            assert orch.state.phase == Phase.PAUSED

            # Cleanup first orchestrator
            orch._cleanup()

            # Resume with answer
            orch2 = Orchestrator(
                session_id=session_id,
                db_path=temp_db,
                on_output=lambda x: None
            )

            orch2.resume(answer="Use PostgreSQL")

            # Verify blocker resolved
            blockers = db.get_unresolved_blockers(session_id, temp_db)
            assert len(blockers) == 0

            # Verify workflow continued and completed
            assert orch2.state.phase == Phase.COMPLETED

            # Cleanup
            orch2._cleanup()
        finally:
            # Cleanup the test plan file created by engine
            if plan_path.exists():
                plan_path.unlink()
            if plan_path.parent.exists():
                plan_path.parent.rmdir()

    @patch('orchestrator_auto.engine.create_executor_agent')
    @patch('orchestrator_auto.engine.create_planner_agent')
    def test_blocker_in_execution(self, mock_create_planner, mock_create_executor, temp_db):
        """Test blocker during execution phase."""
        from pathlib import Path as FilePath
        import re

        # Setup planner mock - returns string with PLAN_CONTENT
        def mock_planner_send(prompt):
            match = re.search(r'docs/([^/]+)/DOC_', prompt)
            session_id = match.group(1) if match else "test"
            return f"""
[PLAN_READY]
Path: docs/{session_id}/DOC_{session_id}_plan.md
Milestones: 1 total

[PLAN_CONTENT]
# Test Plan

## Overview
Test implementation

## Milestones

### Milestone 1: Setup
**Deliverables:**
- Setup complete
[/PLAN_CONTENT]

Summary: Plan ready.
"""

        mock_planner = Mock()
        mock_planner.send_message.side_effect = mock_planner_send
        mock_create_planner.return_value = mock_planner

        # Setup executor mock with blocker - returns string directly
        mock_executor = Mock()
        mock_executor.send_message.return_value = """
            [BLOCKED] Cannot proceed: Missing API credentials

            I need the API key to continue.
            """
        mock_create_executor.return_value = mock_executor

        # Create orchestrator
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )
        session_id = orch.session_id
        plan_path = FilePath(f"docs/{session_id}/DOC_{session_id}_plan.md")

        try:
            # Go to execution
            orch.state_machine.transition(orch.session_id, "ready")
            orch.state = orch.state_machine.get_state(orch.session_id)
            orch._run_planning()

            assert orch.state.phase == Phase.EXECUTION

            # Start execution (should pause on blocker)
            orch._run_execution_loop()

            # Verify paused
            assert orch.state.phase == Phase.PAUSED
            assert orch.state.previous_phase == Phase.EXECUTION

            # Verify blocker created
            blockers = db.get_unresolved_blockers(orch.session_id, temp_db)
            assert len(blockers) == 1
            assert "API" in blockers[0]['question']

            # Cleanup
            orch._cleanup()
        finally:
            # Cleanup the test plan file created by engine
            if plan_path.exists():
                plan_path.unlink()
            if plan_path.parent.exists():
                plan_path.parent.rmdir()


class TestContextRecovery:
    """Test context recovery mechanisms."""

    @patch('orchestrator_auto.engine.create_planner_agent')
    def test_recovery_prompt_generation(self, mock_create_planner, temp_db):
        """Test that recovery prompts are generated correctly."""

        # Create orchestrator and add some messages
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )

        # Log some messages
        db.log_message(
            orch.session_id,
            Phase.DISCOVERY,
            "planner",
            "assistant",
            "Test message 1",
            100,
            temp_db
        )
        db.log_message(
            orch.session_id,
            Phase.DISCOVERY,
            "planner",
            "user",
            "Test message 2",
            50,
            temp_db
        )

        # Get recovery state
        from orchestrator_auto.recovery import get_recovery_state
        state = get_recovery_state(orch.session_id, temp_db)

        # Verify recovery state
        assert 'session' in state
        assert state['session']['phase'] == Phase.DISCOVERY
        assert state['session']['status'] == Status.ACTIVE
        assert len(state['recent_messages']) > 0

        # Generate recovery prompt
        from orchestrator_auto.recovery import generate_recovery_prompt
        prompt = generate_recovery_prompt(orch.session_id, "planner", temp_db)

        # Verify prompt contains context
        assert orch.session_id in prompt
        assert Phase.DISCOVERY in prompt
        assert "Test message" in prompt

        # Cleanup
        orch._cleanup()

    @patch('orchestrator_auto.engine.create_planner_agent')
    def test_precompact_hook_registration(self, mock_create_planner, temp_db):
        """Test that PreCompact hooks are registered correctly."""

        # Mock planner - no client attribute in new architecture
        mock_planner = Mock()
        mock_create_planner.return_value = mock_planner

        # Create orchestrator
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )

        # Initialize agents (would register hooks)
        # Note: In actual implementation, hooks are registered via agent initialization
        from orchestrator_auto.recovery import register_recovery_hook
        register_recovery_hook(mock_planner, orch.session_id, "planner", temp_db)

        # Verify hook registered (stored in _recovery_hook attribute in new architecture)
        assert hasattr(mock_planner, '_recovery_hook')
        assert hasattr(mock_planner, '_session_id')

        # Cleanup
        orch._cleanup()


class TestSessionPersistence:
    """Test session persistence and resumption."""

    @patch('orchestrator_auto.engine.create_planner_agent')
    def test_session_resumption(self, mock_create_planner, temp_db):
        """Test resuming a session from database."""

        # Create first orchestrator
        orch1 = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )
        session_id = orch1.session_id

        # Update state
        db.update_session(
            session_id,
            {
                'phase': Phase.PLANNING,
                'current_milestone': 2,
                'total_milestones': 5,
                'plan_path': 'docs/test/plan.md'
            },
            temp_db
        )

        # Cleanup first orchestrator
        orch1._cleanup()

        # Create new orchestrator with same session
        orch2 = Orchestrator(
            session_id=session_id,
            db_path=temp_db,
            on_output=lambda x: None
        )

        # Verify state restored
        assert orch2.state.phase == Phase.PLANNING
        assert orch2.state.current_milestone == 2
        assert orch2.state.total_milestones == 5
        assert orch2.state.plan_path == 'docs/test/plan.md'

        # Cleanup
        orch2._cleanup()

    def test_message_history_preserved(self, temp_db):
        """Test that message history is preserved across sessions."""

        # Create session and log messages
        session_id = db.create_session("Test feature", temp_db)

        db.log_message(session_id, Phase.DISCOVERY, "planner", "assistant", "Message 1", 50, temp_db)
        db.log_message(session_id, Phase.DISCOVERY, "planner", "user", "Message 2", 30, temp_db)
        db.log_message(session_id, Phase.PLANNING, "planner", "assistant", "Message 3", 100, temp_db)

        # Get messages
        messages = db.get_messages(session_id, db_path=temp_db)
        assert len(messages) == 3

        # Get messages by phase
        discovery_messages = db.get_messages(session_id, Phase.DISCOVERY, temp_db)
        assert len(discovery_messages) == 2

        planning_messages = db.get_messages(session_id, Phase.PLANNING, temp_db)
        assert len(planning_messages) == 1

    def test_milestone_tracking(self, temp_db):
        """Test milestone tracking across workflow."""

        # Create session and milestones
        session_id = db.create_session("Test feature", temp_db)

        m1 = db.create_milestone(session_id, 1, "Setup", temp_db)
        m2 = db.create_milestone(session_id, 2, "Implementation", temp_db)
        m3 = db.create_milestone(session_id, 3, "Testing", temp_db)

        # Update milestone statuses
        db.update_milestone(m1, {'status': 'completed', 'executor_report': 'Setup done'}, temp_db)
        db.update_milestone(m2, {'status': 'in_progress'}, temp_db)

        # Get milestones
        milestones = db.get_milestones(session_id, temp_db)
        assert len(milestones) == 3

        # Verify statuses
        assert milestones[0]['status'] == 'completed'
        assert milestones[1]['status'] == 'in_progress'
        assert milestones[2]['status'] == 'pending'


class TestErrorHandling:
    """Test error handling in various scenarios."""

    def test_invalid_session_id(self, temp_db):
        """Test handling of invalid session ID."""

        with pytest.raises(ValueError, match="not found"):
            Orchestrator(
                session_id="nonexistent",
                db_path=temp_db,
                on_output=lambda x: None
            )

    def test_missing_parameters(self, temp_db):
        """Test handling of missing required parameters."""

        with pytest.raises(ValueError, match="Must provide"):
            Orchestrator(
                db_path=temp_db,
                on_output=lambda x: None
            )

    @patch('orchestrator_auto.engine.create_planner_agent')
    def test_agent_error_handling(self, mock_create_planner, temp_db):
        """Test handling of agent errors."""

        # Setup planner to raise error
        mock_planner = Mock()
        mock_planner.send_message.side_effect = Exception("Agent error")
        mock_create_planner.return_value = mock_planner

        # Create orchestrator
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )

        # Transition to planning
        orch.state_machine.transition(orch.session_id, "ready")
        orch.state = orch.state_machine.get_state(orch.session_id)

        # Attempt planning (should raise)
        with pytest.raises(Exception, match="Agent error"):
            orch._run_planning()

        # Cleanup
        orch._cleanup()
