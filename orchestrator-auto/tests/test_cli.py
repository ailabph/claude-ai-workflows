"""
Unit tests for CLI interface.
"""

import pytest
from click.testing import CliRunner
from pathlib import Path
import sys
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto.cli import cli, format_phase, format_status, show_progress
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


@pytest.fixture
def runner():
    """Create a Click CLI runner."""
    return CliRunner()


class TestFormatHelpers:
    """Test formatting helper functions."""

    def test_format_phase(self):
        """Test phase formatting with colors."""
        result = format_phase(Phase.DISCOVERY)
        assert "DISCOVERY" in result

        result = format_phase(Phase.PLANNING)
        assert "PLANNING" in result

        result = format_phase(Phase.EXECUTION)
        assert "EXECUTION" in result

        result = format_phase(Phase.COMPLETED)
        assert "COMPLETED" in result

        result = format_phase(Phase.PAUSED)
        assert "PAUSED" in result

    def test_format_status(self):
        """Test status formatting with colors."""
        result = format_status(Status.ACTIVE)
        assert "ACTIVE" in result

        result = format_status(Status.PAUSED)
        assert "PAUSED" in result

        result = format_status(Status.COMPLETED)
        assert "COMPLETED" in result

        result = format_status(Status.FAILED)
        assert "FAILED" in result

    @patch('orchestrator_auto.cli.click.echo')
    def test_show_progress(self, mock_echo):
        """Test progress display."""
        mock_orch = Mock()
        mock_orch.get_status.return_value = {
            'session_id': 'test123',
            'phase': Phase.DISCOVERY,
            'status': Status.ACTIVE,
            'current_milestone': 0,
            'total_milestones': 0,
        }

        show_progress(mock_orch)

        # Verify echo was called multiple times
        assert mock_echo.called


class TestStartCommand:
    """Test the start command."""

    @patch('orchestrator_auto.cli.Orchestrator')
    def test_start_basic(self, mock_orch_class, runner, temp_db):
        """Test starting a new workflow."""
        # Setup mock
        mock_orch = Mock()
        mock_orch.session_id = "test123"
        mock_orch.get_status.return_value = {
            'session_id': 'test123',
            'phase': Phase.COMPLETED,
            'status': Status.COMPLETED,
            'current_milestone': 0,
            'total_milestones': 0,
        }
        mock_orch_class.return_value = mock_orch

        # Run command
        result = runner.invoke(cli, ['start', '-f', 'Test feature', '-d', temp_db])

        # Verify
        assert result.exit_code == 0
        assert 'test123' in result.output
        assert mock_orch.start.called

    def test_start_missing_feature(self, runner):
        """Test start command without feature description."""
        result = runner.invoke(cli, ['start'])

        assert result.exit_code != 0
        assert 'Missing option' in result.output or 'required' in result.output.lower()

    @patch('orchestrator_auto.cli.Orchestrator')
    def test_start_with_error(self, mock_orch_class, runner, temp_db):
        """Test start command with orchestrator error."""
        # Setup mock to raise error
        mock_orch_class.side_effect = Exception("Test error")

        # Run command
        result = runner.invoke(cli, ['start', '-f', 'Test feature', '-d', temp_db])

        # Verify error handling
        assert result.exit_code != 0
        assert 'Error' in result.output

    @patch('orchestrator_auto.cli.Orchestrator')
    def test_start_with_plan(self, mock_orch_class, runner, temp_db, tmp_path):
        """Test starting with existing plan file."""
        # Create a valid plan file
        plan_content = """# Test Plan

### Milestone 1: Setup
**Deliverables:**
- Setup complete

### Milestone 2: Implementation
**Deliverables:**
- Feature done
"""
        plan_file = tmp_path / "test_plan.md"
        plan_file.write_text(plan_content)

        # Setup mock
        mock_orch = Mock()
        mock_orch.session_id = "test123"
        mock_orch.get_status.return_value = {
            'session_id': 'test123',
            'phase': Phase.EXECUTION,
            'status': Status.ACTIVE,
            'current_milestone': 1,
            'total_milestones': 2,
        }
        mock_orch_class.return_value = mock_orch

        # Run command with --plan
        result = runner.invoke(cli, [
            'start', '-f', 'Test feature', '-d', temp_db, '--plan', str(plan_file)
        ])

        # Verify
        assert result.exit_code == 0
        assert 'test123' in result.output
        mock_orch_class.assert_called_once()
        # Verify plan_path was passed
        call_kwargs = mock_orch_class.call_args.kwargs
        assert call_kwargs['plan_path'] == str(plan_file)

    def test_start_with_nonexistent_plan(self, runner, temp_db):
        """Test starting with non-existent plan file."""
        result = runner.invoke(cli, [
            'start', '-f', 'Test feature', '-d', temp_db, '--plan', '/nonexistent/plan.md'
        ])

        # Click should fail because file doesn't exist
        assert result.exit_code != 0


class TestResumeCommand:
    """Test the resume command."""

    @patch('orchestrator_auto.cli.Orchestrator')
    def test_resume_active_session(self, mock_orch_class, runner, temp_db):
        """Test resuming an active session."""
        # Create a session
        session_id = db.create_session("Test feature", db_path=temp_db)

        # Setup mock
        mock_orch = Mock()
        mock_orch.session_id = session_id
        mock_orch.get_status.return_value = {
            'session_id': session_id,
            'phase': Phase.COMPLETED,
            'status': Status.COMPLETED,
            'current_milestone': 0,
            'total_milestones': 0,
        }
        mock_orch_class.return_value = mock_orch

        # Run command
        result = runner.invoke(cli, ['resume', session_id, '-d', temp_db])

        # Verify
        assert result.exit_code == 0
        assert mock_orch.resume.called

    def test_resume_nonexistent_session(self, runner, temp_db):
        """Test resuming a session that doesn't exist."""
        result = runner.invoke(cli, ['resume', 'nonexistent', '-d', temp_db])

        assert result.exit_code != 0
        assert 'not found' in result.output

    @patch('orchestrator_auto.cli.Orchestrator')
    def test_resume_paused_without_answer(self, mock_orch_class, runner, temp_db):
        """Test resuming paused session without answer."""
        # Create a session and pause it (set both phase and status as state machine does)
        session_id = db.create_session("Test feature", db_path=temp_db)
        db.update_session(session_id, {'phase': Phase.PAUSED, 'status': Status.PAUSED}, temp_db)

        # Create a blocker
        db.create_blocker(session_id, "planner", "Test question?", temp_db)

        # Setup mock (needed for show_progress call)
        mock_orch = Mock()
        mock_orch.session_id = session_id
        mock_orch.get_status.return_value = {
            'session_id': session_id,
            'phase': Phase.PAUSED,
            'status': Status.PAUSED,
            'current_milestone': 0,
            'total_milestones': 0,
        }
        mock_orch_class.return_value = mock_orch

        # Run command without answer
        result = runner.invoke(cli, ['resume', session_id, '-d', temp_db])

        # Should exit with error asking for answer
        assert result.exit_code != 0
        assert 'blocker' in result.output.lower() or 'answer' in result.output.lower()

    @patch('orchestrator_auto.cli.Orchestrator')
    def test_resume_paused_with_answer(self, mock_orch_class, runner, temp_db):
        """Test resuming paused session with answer."""
        # Create a session and pause it
        session_id = db.create_session("Test feature", db_path=temp_db)
        db.update_session(session_id, {'status': Status.PAUSED}, temp_db)

        # Create a blocker
        db.create_blocker(session_id, "planner", "Test question?", temp_db)

        # Setup mock
        mock_orch = Mock()
        mock_orch.session_id = session_id
        mock_orch.get_status.return_value = {
            'session_id': session_id,
            'phase': Phase.COMPLETED,
            'status': Status.COMPLETED,
            'current_milestone': 0,
            'total_milestones': 0,
        }
        mock_orch_class.return_value = mock_orch

        # Run command with answer
        result = runner.invoke(cli, ['resume', session_id, '-a', 'Test answer', '-d', temp_db])

        # Verify
        assert result.exit_code == 0
        assert mock_orch.resume.called


class TestRespondCommand:
    """Test the respond command."""

    @patch('orchestrator_auto.cli.Orchestrator')
    def test_respond_to_blocker(self, mock_orch_class, runner, temp_db):
        """Test responding to a blocker."""
        # Create a paused session with blocker
        session_id = db.create_session("Test feature", db_path=temp_db)
        db.update_session(session_id, {'status': Status.PAUSED}, temp_db)
        db.create_blocker(session_id, "planner", "Test question?", temp_db)

        # Setup mock
        mock_orch = Mock()
        mock_orch.session_id = session_id
        mock_orch.get_status.return_value = {
            'session_id': session_id,
            'phase': Phase.COMPLETED,
            'status': Status.COMPLETED,
            'current_milestone': 0,
            'total_milestones': 0,
        }
        mock_orch_class.return_value = mock_orch

        # Run command
        result = runner.invoke(cli, ['respond', session_id, 'Test answer', '-d', temp_db])

        # Verify
        assert result.exit_code == 0

    def test_respond_to_nonexistent_session(self, runner, temp_db):
        """Test respond to nonexistent session."""
        result = runner.invoke(cli, ['respond', 'nonexistent', 'answer', '-d', temp_db])

        assert result.exit_code != 0
        assert 'not found' in result.output

    def test_respond_to_active_session(self, runner, temp_db):
        """Test respond to session that's not paused."""
        # Create an active session
        session_id = db.create_session("Test feature", db_path=temp_db)

        # Run command
        result = runner.invoke(cli, ['respond', session_id, 'answer', '-d', temp_db])

        # Should fail because session is not paused
        assert result.exit_code != 0
        assert 'not paused' in result.output.lower()

    def test_respond_without_blocker(self, runner, temp_db):
        """Test respond to paused session without blocker."""
        # Create a paused session without blocker
        session_id = db.create_session("Test feature", db_path=temp_db)
        db.update_session(session_id, {'status': Status.PAUSED}, temp_db)

        # Run command
        result = runner.invoke(cli, ['respond', session_id, 'answer', '-d', temp_db])

        # Should fail because no blocker
        assert result.exit_code != 0
        assert 'blocker' in result.output.lower()


class TestListCommand:
    """Test the list command."""

    def test_list_empty(self, runner, temp_db):
        """Test listing when no sessions exist."""
        result = runner.invoke(cli, ['list', '-d', temp_db])

        assert result.exit_code == 0
        assert 'No sessions found' in result.output

    def test_list_with_sessions(self, runner, temp_db):
        """Test listing sessions with --all-projects flag."""
        # Create multiple sessions (no project_id, so need --all-projects)
        session1 = db.create_session("Feature 1", db_path=temp_db)
        session2 = db.create_session("Feature 2", db_path=temp_db)
        db.update_session(session2, {'status': Status.COMPLETED}, temp_db)

        # Run command with --all-projects since sessions have no project_id
        result = runner.invoke(cli, ['list', '-d', temp_db, '--all-projects'])

        # Verify
        assert result.exit_code == 0
        assert session1 in result.output
        assert session2 in result.output
        assert 'Feature 1' in result.output
        assert 'Feature 2' in result.output

    def test_list_filter_by_status(self, runner, temp_db):
        """Test filtering sessions by status with --all-projects flag."""
        # Create sessions with different statuses (no project_id, so need --all-projects)
        session1 = db.create_session("Active feature", db_path=temp_db)
        session2 = db.create_session("Completed feature", db_path=temp_db)
        db.update_session(session2, {'status': Status.COMPLETED}, temp_db)

        # Run command with filter (pass string value, not enum)
        result = runner.invoke(cli, ['list', '-s', 'completed', '-d', temp_db, '--all-projects'])

        # Verify only completed session shown
        assert result.exit_code == 0
        assert session2 in result.output
        assert session1 not in result.output


class TestStatusCommand:
    """Test the status command."""

    def test_status_basic(self, runner, temp_db):
        """Test showing status for a session."""
        # Create a session
        session_id = db.create_session("Test feature", db_path=temp_db)

        # Run command
        result = runner.invoke(cli, ['status', session_id, '-d', temp_db])

        # Verify
        assert result.exit_code == 0
        assert session_id in result.output
        assert 'Test feature' in result.output
        assert 'SESSION STATUS' in result.output

    def test_status_nonexistent(self, runner, temp_db):
        """Test status for nonexistent session."""
        result = runner.invoke(cli, ['status', 'nonexistent', '-d', temp_db])

        assert result.exit_code != 0
        assert 'not found' in result.output

    def test_status_with_milestones(self, runner, temp_db):
        """Test status with milestone information."""
        # Create a session in execution
        session_id = db.create_session("Test feature", db_path=temp_db)
        db.update_session(
            session_id,
            {
                'phase': Phase.EXECUTION,
                'current_milestone': 2,
                'total_milestones': 5,
                'plan_path': 'docs/test/plan.md'
            },
            temp_db
        )

        # Create milestones
        db.create_milestone(session_id, 1, "Setup", temp_db)
        db.create_milestone(session_id, 2, "Implementation", temp_db)

        # Run command
        result = runner.invoke(cli, ['status', session_id, '-d', temp_db])

        # Verify
        assert result.exit_code == 0
        assert '2/5' in result.output
        assert 'docs/test/plan.md' in result.output

    def test_status_with_blocker(self, runner, temp_db):
        """Test status with unresolved blocker."""
        # Create a paused session with blocker
        session_id = db.create_session("Test feature", db_path=temp_db)
        db.update_session(session_id, {'status': Status.PAUSED}, temp_db)
        db.create_blocker(session_id, "planner", "Test question?", temp_db)

        # Run command
        result = runner.invoke(cli, ['status', session_id, '-d', temp_db])

        # Verify
        assert result.exit_code == 0
        assert 'BLOCKER' in result.output
        assert 'Test question?' in result.output


class TestExportCommand:
    """Test the export command."""

    def test_export_basic(self, runner, temp_db):
        """Test exporting a session."""
        # Create a session with some data
        session_id = db.create_session("Test feature", db_path=temp_db)
        db.log_message(session_id, Phase.DISCOVERY, "planner", "assistant", "Test message", 50, temp_db)

        with runner.isolated_filesystem():
            # Run command
            result = runner.invoke(cli, ['export', session_id, '-o', 'test_export.md', '-d', temp_db])

            # Verify
            assert result.exit_code == 0
            assert 'exported' in result.output.lower()

            # Check file was created
            assert Path('test_export.md').exists()

            # Check content
            content = Path('test_export.md').read_text()
            assert session_id in content
            assert 'Test feature' in content
            assert 'Test message' in content

    def test_export_nonexistent(self, runner, temp_db):
        """Test exporting nonexistent session."""
        result = runner.invoke(cli, ['export', 'nonexistent', '-d', temp_db])

        assert result.exit_code != 0
        assert 'not found' in result.output

    def test_export_with_default_filename(self, runner, temp_db):
        """Test export with auto-generated filename."""
        # Create a session
        session_id = db.create_session("Test feature", db_path=temp_db)

        with runner.isolated_filesystem():
            # Run command without output option
            result = runner.invoke(cli, ['export', session_id, '-d', temp_db])

            # Verify
            assert result.exit_code == 0
            assert 'exported' in result.output.lower()

            # Check a file was created with the session id in name
            md_files = list(Path('.').glob(f'session_{session_id}_*.md'))
            assert len(md_files) == 1

    def test_export_with_all_data(self, runner, temp_db):
        """Test export includes all session data."""
        # Create a session with comprehensive data
        session_id = db.create_session("Test feature", db_path=temp_db)

        # Add messages
        db.log_message(session_id, Phase.DISCOVERY, "planner", "assistant", "Discovery message", 50, temp_db)
        db.log_message(session_id, Phase.PLANNING, "planner", "assistant", "Planning message", 100, temp_db)

        # Add milestone
        milestone_id = db.create_milestone(session_id, 1, "Setup", temp_db)
        db.update_milestone(
            milestone_id,
            {'status': 'completed', 'executor_report': 'Report content'},
            temp_db
        )

        # Add blocker
        blocker_id = db.create_blocker(session_id, "planner", "Test question?", temp_db)
        db.resolve_blocker(blocker_id, "Test answer", temp_db)

        with runner.isolated_filesystem():
            # Run command
            result = runner.invoke(cli, ['export', session_id, '-o', 'full_export.md', '-d', temp_db])

            # Verify
            assert result.exit_code == 0

            # Check content includes all data
            content = Path('full_export.md').read_text()
            assert 'Discovery message' in content
            assert 'Planning message' in content
            assert 'Setup' in content
            assert 'Report content' in content
            assert 'Test question?' in content
            assert 'Test answer' in content
            assert 'RESOLVED' in content


class TestErrorHandling:
    """Test error handling across commands."""

    @patch('orchestrator_auto.cli.db.get_session')
    def test_database_error(self, mock_get_session, runner):
        """Test handling database errors."""
        # Make db operation raise error
        mock_get_session.side_effect = Exception("Database error")

        # Run command
        result = runner.invoke(cli, ['status', 'test123'])

        # Should handle error gracefully
        assert result.exit_code != 0
        assert 'Error' in result.output


class TestCompleteCommand:
    """Test the complete command for force-completing stuck sessions."""

    def test_complete_paused_session(self, runner, temp_db):
        """Test force-completing a paused session with blocker."""
        # Create a session in execution phase
        session_id = db.create_session(
            feature_description="Test feature",
            planner_model="opus",
            executor_model="sonnet",
            db_path=temp_db
        )

        # Update to execution phase with progress
        db.update_session(
            session_id,
            {
                'phase': Phase.PAUSED,
                'status': Status.PAUSED,
                'current_milestone': 5,
                'total_milestones': 7,
                'previous_phase': Phase.EXECUTION,
            },
            temp_db
        )

        # Create an unresolved blocker
        blocker_id = db.create_blocker(session_id, "executor", "Stuck on milestone", temp_db)

        # Run complete command
        result = runner.invoke(cli, ['complete', session_id, '-d', temp_db])

        # Verify success
        assert result.exit_code == 0
        assert 'Force completing session' in result.output
        assert 'Session marked as completed' in result.output
        assert 'Resolved 1 blocker' in result.output

        # Verify session is now completed
        session = db.get_session(session_id, temp_db)
        assert session['phase'] == Phase.COMPLETED
        assert session['status'] == Status.COMPLETED

        # Verify blocker is resolved
        blockers = db.get_unresolved_blockers(session_id, temp_db)
        assert len(blockers) == 0

    def test_complete_execution_session(self, runner, temp_db):
        """Test force-completing an active execution session."""
        # Create a session in execution phase
        session_id = db.create_session(
            feature_description="Test feature",
            planner_model="opus",
            executor_model="sonnet",
            db_path=temp_db
        )

        db.update_session(
            session_id,
            {
                'phase': Phase.EXECUTION,
                'status': Status.ACTIVE,
                'current_milestone': 3,
                'total_milestones': 5,
            },
            temp_db
        )

        # Run complete command
        result = runner.invoke(cli, ['complete', session_id, '-d', temp_db])

        # Verify success
        assert result.exit_code == 0
        assert 'Session marked as completed' in result.output

        # Verify session is completed
        session = db.get_session(session_id, temp_db)
        assert session['phase'] == Phase.COMPLETED

    def test_complete_already_completed(self, runner, temp_db):
        """Test completing an already completed session."""
        # Create a completed session
        session_id = db.create_session(
            feature_description="Test feature",
            planner_model="opus",
            executor_model="sonnet",
            db_path=temp_db
        )

        db.update_session(
            session_id,
            {'phase': Phase.COMPLETED, 'status': Status.COMPLETED},
            temp_db
        )

        # Run complete command
        result = runner.invoke(cli, ['complete', session_id, '-d', temp_db])

        # Should exit gracefully
        assert result.exit_code == 0
        assert 'already completed' in result.output

    def test_complete_nonexistent_session(self, runner, temp_db):
        """Test completing a nonexistent session."""
        result = runner.invoke(cli, ['complete', 'nonexistent123', '-d', temp_db])

        assert result.exit_code != 0
        assert 'not found' in result.output

    def test_complete_multiple_blockers(self, runner, temp_db):
        """Test force-completing a session with multiple blockers."""
        # Create a session
        session_id = db.create_session(
            feature_description="Test feature",
            planner_model="opus",
            executor_model="sonnet",
            db_path=temp_db
        )

        db.update_session(
            session_id,
            {'phase': Phase.PAUSED, 'status': Status.PAUSED},
            temp_db
        )

        # Create multiple unresolved blockers
        db.create_blocker(session_id, "executor", "Blocker 1", temp_db)
        db.create_blocker(session_id, "planner", "Blocker 2", temp_db)
        db.create_blocker(session_id, "executor", "Blocker 3", temp_db)

        # Run complete command
        result = runner.invoke(cli, ['complete', session_id, '-d', temp_db])

        # Verify all blockers resolved
        assert result.exit_code == 0
        assert 'Resolved 3 blocker' in result.output

        # Verify no unresolved blockers remain
        blockers = db.get_unresolved_blockers(session_id, temp_db)
        assert len(blockers) == 0


class TestStartWithPlanAutoFeature:
    """Test auto-extraction of feature from plan file."""

    def test_start_plan_without_feature_extracts_from_h1(self, runner, temp_db, tmp_path):
        """Feature auto-extracted from plan H1 header."""
        plan_file = tmp_path / "test_plan.md"
        plan_file.write_text("""# My Awesome Feature

### Milestone 1: Setup
Tasks here
""")

        with patch('orchestrator_auto.cli.Orchestrator') as mock_orch:
            mock_instance = MagicMock()
            mock_orch.return_value = mock_instance
            mock_instance.session_id = "test123"
            mock_instance.start.return_value = None
            mock_instance.get_status.return_value = {
                'session_id': 'test123',
                'phase': Phase.COMPLETED,
                'status': Status.COMPLETED,
                'current_milestone': 0,
                'total_milestones': 0,
            }

            result = runner.invoke(cli, [
                'start',
                '--plan', str(plan_file),
                '-d', temp_db,
            ])

        # Should succeed without -f flag
        assert result.exit_code == 0
        assert 'My Awesome Feature' in result.output
        assert '(from plan)' in result.output

    def test_start_plan_without_feature_extracts_from_yaml(self, runner, temp_db, tmp_path):
        """Feature auto-extracted from YAML frontmatter."""
        plan_file = tmp_path / "test_plan.md"
        plan_file.write_text("""---
feature: YAML Extracted Feature
---

# Implementation Plan

### Milestone 1: Setup
Tasks here
""")

        with patch('orchestrator_auto.cli.Orchestrator') as mock_orch:
            mock_instance = MagicMock()
            mock_orch.return_value = mock_instance
            mock_instance.session_id = "test123"
            mock_instance.start.return_value = None
            mock_instance.get_status.return_value = {
                'session_id': 'test123',
                'phase': Phase.COMPLETED,
                'status': Status.COMPLETED,
                'current_milestone': 0,
                'total_milestones': 0,
            }

            result = runner.invoke(cli, [
                'start',
                '--plan', str(plan_file),
                '-d', temp_db,
            ])

        assert result.exit_code == 0
        assert 'YAML Extracted Feature' in result.output
        assert '(from plan)' in result.output

    def test_start_plan_without_feature_falls_back_to_filename(self, runner, temp_db, tmp_path):
        """Feature falls back to filename when no headers present."""
        plan_file = tmp_path / "user-authentication-flow.md"
        plan_file.write_text("""### Milestone 1: Setup
Tasks here
""")

        with patch('orchestrator_auto.cli.Orchestrator') as mock_orch:
            mock_instance = MagicMock()
            mock_orch.return_value = mock_instance
            mock_instance.session_id = "test123"
            mock_instance.start.return_value = None
            mock_instance.get_status.return_value = {
                'session_id': 'test123',
                'phase': Phase.COMPLETED,
                'status': Status.COMPLETED,
                'current_milestone': 0,
                'total_milestones': 0,
            }

            result = runner.invoke(cli, [
                'start',
                '--plan', str(plan_file),
                '-d', temp_db,
            ])

        assert result.exit_code == 0
        # Filename converted: user-authentication-flow -> user authentication flow
        assert 'user authentication flow' in result.output
        assert '(from plan)' in result.output

    def test_start_plan_with_explicit_feature_overrides(self, runner, temp_db, tmp_path):
        """Explicit -f takes priority over extraction."""
        plan_file = tmp_path / "test_plan.md"
        plan_file.write_text("""# Feature From Plan

### Milestone 1: Setup
Tasks here
""")

        with patch('orchestrator_auto.cli.Orchestrator') as mock_orch:
            mock_instance = MagicMock()
            mock_orch.return_value = mock_instance
            mock_instance.session_id = "test123"
            mock_instance.start.return_value = None
            mock_instance.get_status.return_value = {
                'session_id': 'test123',
                'phase': Phase.COMPLETED,
                'status': Status.COMPLETED,
                'current_milestone': 0,
                'total_milestones': 0,
            }

            result = runner.invoke(cli, [
                'start',
                '--plan', str(plan_file),
                '-f', 'Explicit Override Feature',
                '-d', temp_db,
            ])

        assert result.exit_code == 0
        assert 'Explicit Override Feature' in result.output
        # Should NOT show "(from plan)" since it was explicit
        assert '(from plan)' not in result.output

    def test_start_plan_shows_from_plan_indicator(self, runner, temp_db, tmp_path):
        """Output shows '(from plan)' when auto-extracted."""
        plan_file = tmp_path / "test_plan.md"
        plan_file.write_text("""# Implementation Plan: Auto Test Feature

### Milestone 1: Setup
Tasks here
""")

        with patch('orchestrator_auto.cli.Orchestrator') as mock_orch:
            mock_instance = MagicMock()
            mock_orch.return_value = mock_instance
            mock_instance.session_id = "test123"
            mock_instance.start.return_value = None
            mock_instance.get_status.return_value = {
                'session_id': 'test123',
                'phase': Phase.COMPLETED,
                'status': Status.COMPLETED,
                'current_milestone': 0,
                'total_milestones': 0,
            }

            result = runner.invoke(cli, [
                'start',
                '--plan', str(plan_file),
                '-d', temp_db,
            ])

        assert result.exit_code == 0
        assert 'Auto Test Feature' in result.output
        assert '(from plan)' in result.output


class TestRenamePlanDone:
    """Test _rename_plan_done helper function."""

    def test_renames_plan_file(self, tmp_path):
        """Plan file renamed to _done.md suffix."""
        from orchestrator_auto.cli import _rename_plan_done

        plan_file = tmp_path / "my-feature.md"
        plan_file.write_text("# Test plan")

        success, result = _rename_plan_done(str(plan_file))

        assert success is True
        assert result == str(tmp_path / "my-feature_done.md")
        assert not plan_file.exists()
        assert (tmp_path / "my-feature_done.md").exists()

    def test_skips_already_done_suffix(self, tmp_path):
        """Files already ending in _done are skipped."""
        from orchestrator_auto.cli import _rename_plan_done

        plan_file = tmp_path / "my-feature_done.md"
        plan_file.write_text("# Test plan")

        success, result = _rename_plan_done(str(plan_file))

        assert success is True
        assert "Already renamed" in result
        assert plan_file.exists()

    def test_skips_if_target_exists(self, tmp_path):
        """Does not overwrite existing _done.md file."""
        from orchestrator_auto.cli import _rename_plan_done

        plan_file = tmp_path / "my-feature.md"
        plan_file.write_text("# Test plan")
        done_file = tmp_path / "my-feature_done.md"
        done_file.write_text("# Existing done file")

        success, result = _rename_plan_done(str(plan_file))

        assert success is False
        assert "Target already exists" in result
        assert plan_file.exists()  # Original still exists
        assert done_file.read_text() == "# Existing done file"  # Not overwritten

    def test_handles_missing_plan_file(self, tmp_path):
        """Gracefully handles nonexistent plan file."""
        from orchestrator_auto.cli import _rename_plan_done

        plan_file = tmp_path / "nonexistent.md"

        success, result = _rename_plan_done(str(plan_file))

        assert success is False
        assert "Plan file not found" in result


class TestPlanCompletionRename:
    """Test plan rename on workflow completion."""

    def test_renames_plan_on_completion(self, runner, temp_db, tmp_path):
        """Plan file renamed to _done.md on successful completion."""
        plan_file = tmp_path / "test-plan.md"
        plan_file.write_text("""# Test Feature

### Milestone 1: Setup
Tasks here
""")

        with patch('orchestrator_auto.cli.Orchestrator') as mock_orch:
            mock_instance = MagicMock()
            mock_orch.return_value = mock_instance
            mock_instance.session_id = "test123"
            mock_instance.start.return_value = None
            mock_instance.state.phase = Phase.COMPLETED
            mock_instance.get_status.return_value = {
                'session_id': 'test123',
                'phase': Phase.COMPLETED,
                'status': Status.COMPLETED,
                'current_milestone': 0,
                'total_milestones': 0,
            }

            result = runner.invoke(cli, [
                'start',
                '--plan', str(plan_file),
                '-d', temp_db,
            ])

        assert result.exit_code == 0
        assert 'Plan renamed' in result.output
        assert not plan_file.exists()
        assert (tmp_path / "test-plan_done.md").exists()

    def test_no_rename_flag_skips_rename(self, runner, temp_db, tmp_path):
        """--no-rename flag prevents renaming."""
        plan_file = tmp_path / "test-plan.md"
        plan_file.write_text("""# Test Feature

### Milestone 1: Setup
Tasks here
""")

        with patch('orchestrator_auto.cli.Orchestrator') as mock_orch:
            mock_instance = MagicMock()
            mock_orch.return_value = mock_instance
            mock_instance.session_id = "test123"
            mock_instance.start.return_value = None
            mock_instance.state.phase = Phase.COMPLETED
            mock_instance.get_status.return_value = {
                'session_id': 'test123',
                'phase': Phase.COMPLETED,
                'status': Status.COMPLETED,
                'current_milestone': 0,
                'total_milestones': 0,
            }

            result = runner.invoke(cli, [
                'start',
                '--plan', str(plan_file),
                '--no-rename',
                '-d', temp_db,
            ])

        assert result.exit_code == 0
        assert 'Plan renamed' not in result.output
        assert plan_file.exists()  # Original still exists
        assert not (tmp_path / "test-plan_done.md").exists()

    def test_no_rename_without_plan_flag(self, runner, temp_db):
        """No rename attempted when started without --plan."""
        with patch('orchestrator_auto.cli.Orchestrator') as mock_orch:
            mock_instance = MagicMock()
            mock_orch.return_value = mock_instance
            mock_instance.session_id = "test123"
            mock_instance.start.return_value = None
            mock_instance.state.phase = Phase.COMPLETED
            mock_instance.get_status.return_value = {
                'session_id': 'test123',
                'phase': Phase.COMPLETED,
                'status': Status.COMPLETED,
                'current_milestone': 0,
                'total_milestones': 0,
            }

            result = runner.invoke(cli, [
                'start',
                '-f', 'Test feature',
                '-d', temp_db,
            ])

        assert result.exit_code == 0
        assert 'Plan renamed' not in result.output
