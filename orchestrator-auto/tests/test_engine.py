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
        """Test planning phase with successful plan creation via PLAN_CONTENT."""
        # Setup mocks - agents now return strings with PLAN_CONTENT
        mock_planner = Mock()

        # Use a lambda to generate dynamic path based on session_id from prompt
        def mock_send_message(prompt, **kwargs):
            import re
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
**Deliverables:**
- Setup complete

### Milestone 2: Implementation
**Deliverables:**
- Feature implemented

### Milestone 3: Testing
**Deliverables:**
- Tests passing
[/PLAN_CONTENT]

Summary: Plan is ready for execution.
"""

        mock_planner.send_message.side_effect = mock_send_message
        mock_create_planner.return_value = mock_planner

        # Create orchestrator in planning phase
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            on_output=lambda x: None
        )
        session_id = orch.session_id
        plan_path = Path(f"docs/{session_id}/DOC_{session_id}_plan.md")

        try:
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
            assert plan_path.exists()  # Engine should have created the file
        finally:
            # Cleanup the test plan file created by engine
            if plan_path.exists():
                plan_path.unlink()
            if plan_path.parent.exists():
                plan_path.parent.rmdir()

    @patch("orchestrator_auto.engine.create_planner_agent")
    def test_planning_with_blocker(self, mock_create_planner, temp_db):
        """Test planning phase with blocker."""
        # Setup mocks - agents now return strings directly
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
        # Setup executor mock - returns string directly
        mock_executor = Mock()
        mock_executor.send_message.return_value = """
        [PROGRESS_REPORT]
        ## Milestone 1: Setup - COMPLETED

        ### Files Created/Modified:
        - setup.py (created)

        ### Test Results:
        All tests passing

        ### Ready for Review: YES
        [/PROGRESS_REPORT]
        """
        mock_create_executor.return_value = mock_executor

        # Setup planner mock - returns string directly
        mock_planner = Mock()
        mock_planner.send_message.return_value = "[MILESTONE_APPROVED] Milestone 1 approved. Proceed to Milestone 2."
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
        # Setup executor mock - returns string directly
        mock_executor = Mock()
        mock_executor.send_message.return_value = "I'll fix those issues."
        mock_create_executor.return_value = mock_executor

        # Setup planner mock - returns string directly
        mock_planner = Mock()
        mock_planner.send_message.return_value = """
        [CHANGES_REQUESTED] Milestone 1 needs changes:
        - Fix test coverage
        - Add docstrings
        """
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
        # FIX: _route_to_planner now returns tuple (validation, executor_response)
        result, executor_response = orch._route_to_planner("Test report")
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
        # Setup mock - returns string directly
        mock_planner = Mock()
        mock_planner.send_message.return_value = "[MILESTONE_APPROVED] Milestone 1 approved."
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
        # FIX: _route_to_planner now returns tuple (validation, executor_response)
        result, executor_response = orch._route_to_planner("Test report")

        assert result == "approved"
        assert mock_planner.send_message.called

    @patch("orchestrator_auto.engine.create_executor_agent")
    def test_route_to_executor(self, mock_create_executor, temp_db):
        """Test routing feedback to executor."""
        # Setup mock - returns string directly
        mock_executor = Mock()
        mock_executor.send_message.return_value = "Understood, fixing now."
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


class TestOrchestratorStartWithPlan:
    """Test starting with existing plan file."""

    def test_start_with_valid_plan(self, temp_db, tmp_path):
        """Test starting session with valid plan file."""
        # Create a valid plan file
        plan_content = """# Implementation Plan: Test Feature

## Overview
Test feature implementation.

## Milestones

### Milestone 1: Setup
**Deliverables:**
- Setup complete

### Milestone 2: Implementation
**Deliverables:**
- Feature implemented

### Milestone 3: Testing
**Deliverables:**
- Tests passing
"""
        plan_file = tmp_path / "test_plan.md"
        plan_file.write_text(plan_content)

        # Create orchestrator with plan
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            plan_path=str(plan_file),
            on_output=lambda x: None
        )

        # Verify session was created in execution phase
        assert orch.session_id is not None
        assert orch.state.phase == "execution"
        assert orch.state.current_milestone == 1
        assert orch.state.total_milestones == 3
        assert orch.state.plan_path == str(plan_file)

    def test_start_with_invalid_plan_no_milestones(self, temp_db, tmp_path):
        """Test starting with plan that has no milestones."""
        # Create invalid plan file (no milestones)
        plan_content = """# Implementation Plan

## Overview
No milestones here.
"""
        plan_file = tmp_path / "invalid_plan.md"
        plan_file.write_text(plan_content)

        # Should raise ValueError
        with pytest.raises(ValueError, match="No milestones found"):
            Orchestrator(
                feature_description="Test feature",
                db_path=temp_db,
                plan_path=str(plan_file),
                on_output=lambda x: None
            )

    def test_start_with_nonexistent_plan(self, temp_db):
        """Test starting with non-existent plan file."""
        with pytest.raises(ValueError, match="not found"):
            Orchestrator(
                feature_description="Test feature",
                db_path=temp_db,
                plan_path="/nonexistent/plan.md",
                on_output=lambda x: None
            )

    def test_start_with_plan_single_milestone(self, temp_db, tmp_path):
        """Test starting with plan that has single milestone."""
        plan_content = """# Quick Fix Plan

### Milestone 1: Fix Bug
**Deliverables:**
- Bug fix
"""
        plan_file = tmp_path / "quick_plan.md"
        plan_file.write_text(plan_content)

        orch = Orchestrator(
            feature_description="Quick fix",
            db_path=temp_db,
            plan_path=str(plan_file),
            on_output=lambda x: None
        )

        assert orch.state.phase == "execution"
        assert orch.state.total_milestones == 1


class TestTruncatedResponseContinuation:
    """Test auto-continue behavior for truncated responses."""

    @patch("orchestrator_auto.engine.create_executor_agent")
    def test_executor_truncated_response_triggers_continuation(self, mock_create_executor, temp_db, tmp_path):
        """Test that truncated executor response triggers auto-continuation."""
        # Setup plan file
        plan_content = """# Test Plan
### Milestone 1: Setup
**Deliverables:**
- Complete setup
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        # Mock executor: first call returns truncated, second returns valid
        mock_executor = Mock()
        call_count = [0]

        def executor_side_effect(prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: truncated response (no valid tag, ends incomplete)
                return "Let me start working on the setup. I'll create the configuration"
            else:
                # Second call (continuation): valid progress report
                return """
[PROGRESS_REPORT]
## Milestone 1: Setup - COMPLETED
All setup tasks completed.
[/PROGRESS_REPORT]
"""

        mock_executor.send_message.side_effect = executor_side_effect
        mock_create_executor.return_value = mock_executor

        # Create orchestrator with plan (starts in execution phase)
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            plan_path=str(plan_file),
            on_output=lambda x: None
        )

        # Run executor routing with milestone prompt
        result = orch._route_to_executor("Execute Milestone 1: Setup")

        # Should have called executor twice (original + continuation)
        assert mock_executor.send_message.call_count == 2

        # Result should contain the valid progress report
        assert "[PROGRESS_REPORT]" in result

    @patch("orchestrator_auto.engine.create_planner_agent")
    def test_planner_truncated_response_triggers_continuation(self, mock_create_planner, temp_db, tmp_path):
        """Test that truncated planner response triggers auto-continuation."""
        # Setup plan file
        plan_content = """# Test Plan
### Milestone 1: Setup
**Deliverables:**
- Complete setup
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        # Mock planner: first call returns truncated, second returns valid
        mock_planner = Mock()
        call_count = [0]

        def planner_side_effect(prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: truncated response (no valid tag, ends incomplete)
                return "Looking at the milestone report, I can see that"
            else:
                # Second call (continuation): valid approval
                return "[MILESTONE_APPROVED] Milestone 1 approved. Good work!"

        mock_planner.send_message.side_effect = planner_side_effect
        mock_create_planner.return_value = mock_planner

        # Create orchestrator with plan (starts in execution phase)
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            plan_path=str(plan_file),
            on_output=lambda x: None
        )

        # Set current milestone for context
        orch.state.current_milestone = 1

        # Prepare a mock progress report
        mock_report = """
[PROGRESS_REPORT]
## Milestone 1 - COMPLETED
Setup tasks done.
[/PROGRESS_REPORT]
"""

        # Run planner routing with progress report
        result_type, result_data = orch._route_to_planner(mock_report)

        # Should have called planner twice (original + continuation)
        assert mock_planner.send_message.call_count == 2

        # Result should be approved
        assert result_type == "approved"

    @patch("orchestrator_auto.engine.create_executor_agent")
    def test_executor_valid_response_no_continuation(self, mock_create_executor, temp_db, tmp_path):
        """Test that valid executor response does not trigger continuation."""
        # Setup plan file
        plan_content = """# Test Plan
### Milestone 1: Setup
**Deliverables:**
- Complete setup
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        # Mock executor: returns valid response immediately
        mock_executor = Mock()
        mock_executor.send_message.return_value = """
[PROGRESS_REPORT]
## Milestone 1: Setup - COMPLETED
All setup tasks completed.
[/PROGRESS_REPORT]
"""
        mock_create_executor.return_value = mock_executor

        # Create orchestrator with plan
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            plan_path=str(plan_file),
            on_output=lambda x: None
        )

        # Run executor routing
        result = orch._route_to_executor("Execute Milestone 1: Setup")

        # Should have called executor only once (no continuation needed)
        assert mock_executor.send_message.call_count == 1
        assert "[PROGRESS_REPORT]" in result

    @patch("orchestrator_auto.engine.create_executor_agent")
    def test_executor_blocked_response_no_continuation(self, mock_create_executor, temp_db, tmp_path):
        """Test that BLOCKED response does not trigger continuation."""
        # Setup plan file
        plan_content = """# Test Plan
### Milestone 1: Setup
**Deliverables:**
- Complete setup
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        # Mock executor: returns BLOCKED response
        mock_executor = Mock()
        mock_executor.send_message.return_value = "[BLOCKED] Cannot proceed: missing credentials"
        mock_create_executor.return_value = mock_executor

        # Create orchestrator with plan
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            plan_path=str(plan_file),
            on_output=lambda x: None
        )

        # Run executor routing
        result = orch._route_to_executor("Execute Milestone 1: Setup")

        # Should have called executor only once (BLOCKED is valid tag)
        assert mock_executor.send_message.call_count == 1
        assert "[BLOCKED]" in result


class TestEmptyResponseRetry:
    """Test auto-retry behavior for empty planner responses."""

    @patch("orchestrator_auto.engine.time.sleep")
    @patch("orchestrator_auto.engine.create_planner_agent")
    def test_planner_empty_response_retry_succeeds(self, mock_create_planner, mock_sleep, temp_db, tmp_path):
        """Test that empty response triggers retry and succeeds on second attempt."""
        # Setup plan file
        plan_content = """# Test Plan
### Milestone 1: Setup
**Deliverables:**
- Complete setup
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        # Mock planner: first call returns empty, second returns valid approval
        mock_planner = Mock()
        call_count = [0]

        def planner_side_effect(prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ""  # Empty response
            else:
                return "[MILESTONE_APPROVED] Milestone 1 approved."

        mock_planner.send_message.side_effect = planner_side_effect
        mock_create_planner.return_value = mock_planner

        # Create orchestrator with plan
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            plan_path=str(plan_file),
            on_output=lambda x: None
        )
        orch.state.current_milestone = 1

        # Run planner routing
        mock_report = "[PROGRESS_REPORT]\nMilestone 1 done.\n[/PROGRESS_REPORT]"
        result_type, result_data = orch._route_to_planner(mock_report)

        # Should have called planner twice (original + retry)
        assert mock_planner.send_message.call_count == 2
        # Should have slept once (backoff)
        assert mock_sleep.call_count == 1
        # Result should be approved
        assert result_type == "approved"

    @patch("orchestrator_auto.engine.time.sleep")
    @patch("orchestrator_auto.engine.create_planner_agent")
    def test_planner_none_response_retry_succeeds(self, mock_create_planner, mock_sleep, temp_db, tmp_path):
        """Test that None response triggers retry and succeeds on second attempt."""
        plan_content = """# Test Plan
### Milestone 1: Setup
**Deliverables:**
- Complete setup
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        # Mock planner: first call returns None, second returns valid approval
        mock_planner = Mock()
        call_count = [0]

        def planner_side_effect(prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # None response (SDK edge case)
            else:
                return "[MILESTONE_APPROVED] Milestone 1 approved."

        mock_planner.send_message.side_effect = planner_side_effect
        mock_create_planner.return_value = mock_planner

        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            plan_path=str(plan_file),
            on_output=lambda x: None
        )
        orch.state.current_milestone = 1

        mock_report = "[PROGRESS_REPORT]\nMilestone 1 done.\n[/PROGRESS_REPORT]"
        result_type, result_data = orch._route_to_planner(mock_report)

        # Should succeed without crashing
        assert mock_planner.send_message.call_count == 2
        assert result_type == "approved"

    @patch("orchestrator_auto.engine.time.sleep")
    @patch("orchestrator_auto.engine.create_planner_agent")
    def test_planner_empty_response_all_retries_fail(self, mock_create_planner, mock_sleep, temp_db, tmp_path):
        """Test that all empty retries creates a blocker."""
        plan_content = """# Test Plan
### Milestone 1: Setup
**Deliverables:**
- Complete setup
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        # Mock planner: always returns empty
        mock_planner = Mock()
        mock_planner.send_message.return_value = ""
        mock_create_planner.return_value = mock_planner

        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            plan_path=str(plan_file),
            on_output=lambda x: None
        )
        orch.state.current_milestone = 1

        mock_report = "[PROGRESS_REPORT]\nMilestone 1 done.\n[/PROGRESS_REPORT]"
        result_type, result_data = orch._route_to_planner(mock_report)

        # Should have called planner 3 times (original + 2 retries)
        assert mock_planner.send_message.call_count == 3
        # Should have slept twice (backoff for each retry)
        assert mock_sleep.call_count == 2
        # Result should be blocked
        assert result_type == "blocked"

    @patch("orchestrator_auto.engine.time.sleep")
    @patch("orchestrator_auto.engine.create_planner_agent")
    @patch("orchestrator_auto.engine.create_executor_agent")
    def test_planner_empty_then_changes_requested(self, mock_create_executor, mock_create_planner, mock_sleep, temp_db, tmp_path):
        """Test that empty response followed by CHANGES_REQUESTED works correctly."""
        plan_content = """# Test Plan
### Milestone 1: Setup
**Deliverables:**
- Complete setup
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        # Mock planner: first call returns empty, second returns changes requested
        mock_planner = Mock()
        call_count = [0]

        def planner_side_effect(prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ""
            else:
                return "[CHANGES_REQUESTED]\n- Fix the tests\n- Add error handling"

        mock_planner.send_message.side_effect = planner_side_effect
        mock_create_planner.return_value = mock_planner

        # Mock executor for the feedback routing
        mock_executor = Mock()
        mock_executor.send_message.return_value = "[PROGRESS_REPORT]\nFixed issues.\n[/PROGRESS_REPORT]"
        mock_create_executor.return_value = mock_executor

        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            plan_path=str(plan_file),
            on_output=lambda x: None
        )
        orch.state.current_milestone = 1

        mock_report = "[PROGRESS_REPORT]\nMilestone 1 done.\n[/PROGRESS_REPORT]"
        result_type, result_data = orch._route_to_planner(mock_report)

        # Should have called planner twice
        assert mock_planner.send_message.call_count == 2
        # Result should be changes_requested
        assert result_type == "changes_requested"
        # Should have routed to executor
        assert mock_executor.send_message.call_count == 1

    @patch("orchestrator_auto.engine.time.sleep")
    @patch("orchestrator_auto.engine.create_planner_agent")
    def test_planner_empty_then_unparseable_falls_through(self, mock_create_planner, mock_sleep, temp_db, tmp_path):
        """Test that empty then unparseable response falls through to truncation check."""
        plan_content = """# Test Plan
### Milestone 1: Setup
**Deliverables:**
- Complete setup
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        # Mock planner: first call returns empty, second returns unparseable (no tag)
        mock_planner = Mock()
        call_count = [0]

        def planner_side_effect(prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ""
            elif call_count[0] == 2:
                # Retry returns unparseable - no valid tag
                return "I think the milestone looks good overall."
            else:
                # Continuation attempt (from truncation check) also fails
                return "The code appears to work correctly."

        mock_planner.send_message.side_effect = planner_side_effect
        mock_create_planner.return_value = mock_planner

        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
            plan_path=str(plan_file),
            on_output=lambda x: None
        )
        orch.state.current_milestone = 1

        mock_report = "[PROGRESS_REPORT]\nMilestone 1 done.\n[/PROGRESS_REPORT]"
        result_type, result_data = orch._route_to_planner(mock_report)

        # Should have called planner at least twice (original + retry that got non-empty)
        assert mock_planner.send_message.call_count >= 2
        # Result should be blocked (unparseable falls through to blocker)
        assert result_type == "blocked"
