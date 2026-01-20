"""
Unit tests for CLI interface.
"""

import pytest
from click.testing import CliRunner
from pathlib import Path
import sys
import tempfile
import os
import signal
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
        # New error format uses "Unexpected error" for non-OrchestratorError exceptions
        assert 'error' in result.output.lower()

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

    def test_respond_has_tui_option(self):
        """Test that respond command has --tui option."""
        from orchestrator_auto.cli import respond

        # Check that --tui is a valid option
        params = {p.name for p in respond.params}
        assert 'tui' in params

    def test_respond_tui_missing_textual(self, runner, temp_db, monkeypatch):
        """Test respond --tui shows helpful error when textual not installed."""
        # Create a paused session with blocker
        session_id = db.create_session("Test feature", db_path=temp_db)
        db.update_session(session_id, {"phase": "paused", "status": Status.PAUSED}, db_path=temp_db)
        db.create_blocker(session_id, "executor", "What color?", db_path=temp_db)

        # Mock check_textual_available in orchestrator_auto.tui (where it's defined)
        # _start_respond_tui imports from .tui, so patch at source
        def mock_check():
            raise ImportError("Textual is not installed")

        monkeypatch.setattr("orchestrator_auto.tui.check_textual_available", mock_check)

        result = runner.invoke(cli, [
            'respond', session_id, 'blue', '--tui', '--db-path', temp_db
        ])

        assert result.exit_code == 1
        assert "Textual is not installed" in result.output

    @patch('orchestrator_auto.cli.Orchestrator')
    def test_respond_without_tui_invokes_resume(self, mock_orch_class, runner, temp_db):
        """Test respond without --tui follows existing behavior and invokes resume."""
        # Create a paused session with blocker
        session_id = db.create_session("Test feature", db_path=temp_db)
        db.update_session(session_id, {"phase": "paused", "status": Status.PAUSED}, db_path=temp_db)
        db.create_blocker(session_id, "executor", "What color?", db_path=temp_db)

        # Setup mock orchestrator
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

        result = runner.invoke(cli, [
            'respond', session_id, 'blue', '--db-path', temp_db
        ])

        # Should show question/answer in output
        assert "What color?" in result.output
        assert "blue" in result.output
        # Should have invoked resume on the orchestrator (via ctx.invoke -> resume -> Orchestrator)
        assert mock_orch.resume.called


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


# =============================================================================
# Watch Mode Tests
# =============================================================================

from orchestrator_auto.cli import (
    _is_watch_candidate,
    _get_pending_plans,
    _find_available_converted_path,
    _strip_terminal_suffix,
    _rename_to_terminal,
    WatchResult,
)


class TestWatchCandidateSelection:
    """Tests for _is_watch_candidate helper."""

    def test_accepts_plain_md_file(self):
        """Plain .md files are candidates."""
        assert _is_watch_candidate(Path("feature.md")) is True

    def test_accepts_nested_path(self):
        """Files with parent directories are candidates."""
        assert _is_watch_candidate(Path("/some/path/feature.md")) is True

    def test_rejects_quarantined_file(self):
        """Files starting with _orchestrator-skip are rejected."""
        assert _is_watch_candidate(Path("_orchestrator-skip__feature.md")) is False
        assert _is_watch_candidate(Path("_orchestrator-skip_invalid.md")) is False

    def test_rejects_done_file(self):
        """Files ending with _done are rejected."""
        assert _is_watch_candidate(Path("feature_done.md")) is False

    def test_rejects_failed_file(self):
        """Files ending with _failed are rejected."""
        assert _is_watch_candidate(Path("feature_failed.md")) is False

    def test_rejects_paused_file(self):
        """Files ending with _paused are rejected."""
        assert _is_watch_candidate(Path("feature_paused.md")) is False

    def test_rejects_non_md_file(self):
        """Non-.md files are rejected."""
        assert _is_watch_candidate(Path("feature.txt")) is False
        assert _is_watch_candidate(Path("feature.py")) is False
        assert _is_watch_candidate(Path("feature")) is False

    def test_accepts_md_uppercase(self):
        """Case-insensitive extension matching."""
        assert _is_watch_candidate(Path("feature.MD")) is True
        assert _is_watch_candidate(Path("feature.Md")) is True

    def test_done_in_middle_is_valid(self):
        """'done' not at end of stem is valid."""
        assert _is_watch_candidate(Path("done-feature.md")) is True
        assert _is_watch_candidate(Path("feature-done-v2.md")) is True


class TestStripTerminalSuffix:
    """Tests for _strip_terminal_suffix helper."""

    def test_strips_done_suffix(self):
        """Strips _done suffix."""
        assert _strip_terminal_suffix("feature_done") == "feature"

    def test_strips_failed_suffix(self):
        """Strips _failed suffix."""
        assert _strip_terminal_suffix("feature_failed") == "feature"

    def test_strips_paused_suffix(self):
        """Strips _paused suffix."""
        assert _strip_terminal_suffix("feature_paused") == "feature"

    def test_leaves_plain_stem_unchanged(self):
        """Plain stems without terminal suffix are unchanged."""
        assert _strip_terminal_suffix("feature") == "feature"
        assert _strip_terminal_suffix("my-feature-plan") == "my-feature-plan"

    def test_only_strips_suffix_not_middle(self):
        """Only strips suffix, not if it appears in middle of name."""
        assert _strip_terminal_suffix("done-feature") == "done-feature"
        assert _strip_terminal_suffix("feature-done-v2") == "feature-done-v2"

    def test_handles_multiple_terminal_suffixes(self):
        """Only strips the outermost terminal suffix."""
        # If somehow feature_done_paused exists, strip _paused
        assert _strip_terminal_suffix("feature_done_paused") == "feature_done"


class TestGetPendingPlans:
    """Tests for _get_pending_plans helper."""

    def test_sorts_by_mtime_then_filename(self, tmp_path):
        """Files sorted by mtime ascending, then filename ascending."""
        import time

        # Create files with controlled timestamps
        file_c = tmp_path / "c_feature.md"
        file_c.write_text("# C")
        time.sleep(0.1)

        file_a = tmp_path / "a_feature.md"
        file_a.write_text("# A")
        time.sleep(0.1)

        file_b = tmp_path / "b_feature.md"
        file_b.write_text("# B")

        result = _get_pending_plans(tmp_path)

        # Should be sorted by mtime (oldest first)
        assert result[0].name == "c_feature.md"
        assert result[1].name == "a_feature.md"
        assert result[2].name == "b_feature.md"

    def test_excludes_terminal_files(self, tmp_path):
        """Terminal state files are excluded."""
        (tmp_path / "valid.md").write_text("# Valid")
        (tmp_path / "feature_done.md").write_text("# Done")
        (tmp_path / "feature_failed.md").write_text("# Failed")
        (tmp_path / "feature_paused.md").write_text("# Paused")
        (tmp_path / "_orchestrator-skip__old.md").write_text("# Skipped")

        result = _get_pending_plans(tmp_path)

        assert len(result) == 1
        assert result[0].name == "valid.md"

    def test_empty_directory(self, tmp_path):
        """Empty directory returns empty list."""
        result = _get_pending_plans(tmp_path)
        assert result == []

    def test_no_md_files(self, tmp_path):
        """Directory with no .md files returns empty list."""
        (tmp_path / "readme.txt").write_text("text")
        (tmp_path / "script.py").write_text("# py")

        result = _get_pending_plans(tmp_path)
        assert result == []


class TestFindAvailableConvertedPath:
    """Tests for _find_available_converted_path helper."""

    def test_first_path_available(self, tmp_path):
        """Returns <stem>_converted.md when available."""
        original = tmp_path / "feature.md"
        original.write_text("# Feature")

        result = _find_available_converted_path(original)

        assert result.name == "feature_converted.md"
        assert result.parent == tmp_path

    def test_collision_handling(self, tmp_path):
        """Returns _converted_2.md when _converted.md exists."""
        original = tmp_path / "feature.md"
        original.write_text("# Feature")
        (tmp_path / "feature_converted.md").write_text("# Existing")

        result = _find_available_converted_path(original)

        assert result.name == "feature_converted_2.md"

    def test_multiple_collisions(self, tmp_path):
        """Handles multiple collisions correctly."""
        original = tmp_path / "feature.md"
        original.write_text("# Feature")
        (tmp_path / "feature_converted.md").write_text("# 1")
        (tmp_path / "feature_converted_2.md").write_text("# 2")
        (tmp_path / "feature_converted_3.md").write_text("# 3")

        result = _find_available_converted_path(original)

        assert result.name == "feature_converted_4.md"

    def test_max_collisions_raises_error(self, tmp_path):
        """Raises error after 100 collision attempts."""
        original = tmp_path / "feature.md"
        original.write_text("# Feature")

        # Create all possible collision files
        (tmp_path / "feature_converted.md").write_text("# 1")
        for i in range(2, 101):
            (tmp_path / f"feature_converted_{i}.md").write_text(f"# {i}")

        with pytest.raises(RuntimeError, match="Too many converted files"):
            _find_available_converted_path(original)


class TestRenameToTerminal:
    """Tests for _rename_to_terminal helper."""

    def test_renames_to_done(self, tmp_path):
        """Successfully renames to _done suffix."""
        plan = tmp_path / "feature.md"
        plan.write_text("# Test")

        success, new_path = _rename_to_terminal(plan, '_done')

        assert success is True
        assert Path(new_path).name == "feature_done.md"
        assert not plan.exists()
        assert Path(new_path).exists()

    def test_renames_to_failed(self, tmp_path):
        """Successfully renames to _failed suffix."""
        plan = tmp_path / "feature.md"
        plan.write_text("# Test")

        success, new_path = _rename_to_terminal(plan, '_failed')

        assert success is True
        assert Path(new_path).name == "feature_failed.md"

    def test_renames_to_paused(self, tmp_path):
        """Successfully renames to _paused suffix."""
        plan = tmp_path / "feature.md"
        plan.write_text("# Test")

        success, new_path = _rename_to_terminal(plan, '_paused')

        assert success is True
        assert Path(new_path).name == "feature_paused.md"

    def test_updates_db_on_rename(self, tmp_path, temp_db):
        """Session plan_path is updated in database."""
        # Create a session
        session_id = db.create_session("Test feature", db_path=temp_db)

        plan = tmp_path / "feature.md"
        plan.write_text("# Test")

        success, new_path = _rename_to_terminal(plan, '_done', session_id, temp_db)

        assert success is True

        # Verify DB was updated
        session = db.get_session(session_id, temp_db)
        assert session['plan_path'] == new_path

    def test_handles_nonexistent_file(self, tmp_path):
        """Returns error for nonexistent file."""
        plan = tmp_path / "nonexistent.md"

        success, error = _rename_to_terminal(plan, '_done')

        assert success is False
        assert "No such file" in error or "cannot find" in error.lower() or "not found" in error.lower() or "FileNotFoundError" in error or "does not exist" in error.lower()


class TestWatchResult:
    """Tests for WatchResult dataclass."""

    def test_completed_result(self):
        """WatchResult for completed status."""
        result = WatchResult(
            status='completed',
            session_id='abc123',
            executed_path=Path('/tmp/feature.md'),
        )

        assert result.status == 'completed'
        assert result.session_id == 'abc123'
        assert result.executed_path == Path('/tmp/feature.md')
        assert result.error is None

    def test_failed_result_with_error(self):
        """WatchResult for failed status with error."""
        result = WatchResult(
            status='failed',
            session_id='abc123',
            error='Workflow failed',
        )

        assert result.status == 'failed'
        assert result.error == 'Workflow failed'

    def test_skipped_result(self):
        """WatchResult for skipped status."""
        result = WatchResult(
            status='skipped',
            error='Invalid plan format',
        )

        assert result.status == 'skipped'
        assert result.session_id is None
        assert result.executed_path is None


class TestWatchCommand:
    """Tests for the watch CLI command."""

    def test_help_shows_options(self, runner):
        """Help output shows all expected options."""
        result = runner.invoke(cli, ['watch', '--help'])

        assert result.exit_code == 0
        assert '--poll-interval' in result.output
        assert '--convert' in result.output
        assert '--no-convert' in result.output
        assert '--db-path' in result.output
        assert '--planner-model' in result.output
        assert '--executor-model' in result.output
        assert '--auto-commit' in result.output
        assert '--telegram' in result.output
        assert 'PLANS_DIR' in result.output

    def test_requires_directory(self, runner):
        """Watch command requires a directory argument."""
        result = runner.invoke(cli, ['watch'])

        assert result.exit_code != 0
        assert 'Missing argument' in result.output or 'PLANS_DIR' in result.output

    def test_validates_directory_exists(self, runner):
        """Watch command validates that directory exists."""
        result = runner.invoke(cli, ['watch', '/nonexistent/path'])

        assert result.exit_code != 0
        # Click validates that the path exists

    def test_accepts_valid_directory(self, runner, tmp_path):
        """Watch command accepts valid directory (immediate ctrl+c)."""
        # Note: This test uses a mock to avoid actually running the watch loop
        with patch('orchestrator_auto.cli.db.init_db'):
            with patch('orchestrator_auto.cli.signal.signal') as mock_signal:
                # Simulate immediate shutdown
                def call_handler(*args):
                    # When signal.signal is called with SIGINT, call the handler immediately
                    if len(args) >= 2 and args[0] == signal.SIGINT:
                        # Store the handler
                        call_handler.handler = args[1]
                    return signal.SIG_DFL

                mock_signal.side_effect = call_handler

                with patch('orchestrator_auto.cli._get_pending_plans', return_value=[]):
                    with patch('orchestrator_auto.cli.time.sleep', side_effect=KeyboardInterrupt):
                        result = runner.invoke(cli, ['watch', str(tmp_path)])

        # Command should handle the interrupt gracefully
        assert 'Watch mode stopped' in result.output or 'Watch Mode' in result.output


# Import the quarantine function for testing
from orchestrator_auto.cli import _quarantine_and_convert


class TestQuarantineAndConvert:
    """Tests for _quarantine_and_convert helper."""

    def test_quarantines_without_conversion_when_disabled(self, tmp_path):
        """When auto_convert=False, just quarantine the file."""
        plan = tmp_path / "invalid.md"
        plan.write_text("# No milestones here")

        result = _quarantine_and_convert(plan, auto_convert=False)

        assert result is None
        assert not plan.exists()
        quarantine = tmp_path / "_orchestrator-skip__invalid.md"
        assert quarantine.exists()

    def test_creates_converted_file_on_success(self, tmp_path):
        """On successful conversion, creates converted file and quarantines original."""
        plan = tmp_path / "feature.md"
        plan.write_text("# Feature\n\nStep 1: Do this\nStep 2: Do that")

        # Mock the convert_plan to return valid content
        with patch('orchestrator_auto.convert.convert_plan') as mock_convert:
            mock_convert.return_value = (
                "# Feature\n\n### Milestone 1: Setup\nDo this\n### Milestone 2: Build\nDo that",
                {"milestones": 2, "milestone_names": ["Setup", "Build"]},
            )

            result = _quarantine_and_convert(plan, auto_convert=True)

        assert result is not None
        assert result.name == "feature_converted.md"
        assert result.exists()
        # Original should be quarantined
        quarantine = tmp_path / "_orchestrator-skip__feature.md"
        assert quarantine.exists()
        assert not plan.exists()

    def test_handles_conversion_failure(self, tmp_path):
        """ConversionError results in quarantine only, no converted file."""
        from orchestrator_auto.convert import ConversionError

        plan = tmp_path / "invalid.md"
        plan.write_text("# Not convertible")

        with patch('orchestrator_auto.convert.convert_plan') as mock_convert:
            mock_convert.side_effect = ConversionError("Cannot convert")

            result = _quarantine_and_convert(plan, auto_convert=True)

        assert result is None
        assert not plan.exists()
        quarantine = tmp_path / "_orchestrator-skip__invalid.md"
        assert quarantine.exists()
        # No converted file should exist
        converted = tmp_path / "invalid_converted.md"
        assert not converted.exists()

    def test_handles_collision_on_converted_path(self, tmp_path):
        """When _converted.md exists, uses _converted_2.md."""
        plan = tmp_path / "feature.md"
        plan.write_text("# Feature\n\nTasks here")
        # Pre-create the collision file
        (tmp_path / "feature_converted.md").write_text("# Already exists")

        with patch('orchestrator_auto.convert.convert_plan') as mock_convert:
            mock_convert.return_value = (
                "# Feature\n\n### Milestone 1: Setup\nDo this",
                {"milestones": 1, "milestone_names": ["Setup"]},
            )

            result = _quarantine_and_convert(plan, auto_convert=True)

        assert result is not None
        assert result.name == "feature_converted_2.md"
        assert result.exists()


class TestPostResumeReconciliation:
    """Tests for post-resume reconciliation behavior in watch mode."""

    def test_renames_paused_to_done_after_completed_resume(self, tmp_path, temp_db):
        """When a paused session completes after resume, rename to _done."""
        # Create a session
        session_id = db.create_session("Test feature", db_path=temp_db)
        # Update to paused state
        db.update_session(session_id, {'phase': Phase.PAUSED, 'status': Status.PAUSED}, temp_db)

        # Create the paused plan file
        paused_plan = tmp_path / "feature_paused.md"
        paused_plan.write_text("# Test Plan\n### Milestone 1: Test")
        db.update_session(session_id, {'plan_path': str(paused_plan)}, temp_db)

        # Simulate resume completing
        db.update_session(
            session_id,
            {'phase': Phase.COMPLETED, 'status': Status.COMPLETED},
            temp_db
        )

        # Now rename to done (as watch mode would do)
        # Note: _paused suffix is REPLACED, not appended
        success, new_path = _rename_to_terminal(paused_plan, '_done', session_id, temp_db)

        assert success
        assert Path(new_path).name == "feature_done.md"  # Replaces _paused, not appends
        assert Path(new_path).exists()
        # Verify DB was updated
        session = db.get_session(session_id, temp_db)
        assert session['plan_path'] == new_path

    def test_renames_paused_to_failed_after_failed_resume(self, tmp_path, temp_db):
        """When a paused session fails after resume, rename to _failed."""
        # Create a session
        session_id = db.create_session("Test feature", db_path=temp_db)
        db.update_session(session_id, {'phase': Phase.PAUSED, 'status': Status.PAUSED}, temp_db)

        # Create the paused plan file
        paused_plan = tmp_path / "feature_paused.md"
        paused_plan.write_text("# Test Plan\n### Milestone 1: Test")
        db.update_session(session_id, {'plan_path': str(paused_plan)}, temp_db)

        # Simulate resume failing
        db.update_session(
            session_id,
            {'phase': Phase.COMPLETED, 'status': Status.FAILED},
            temp_db
        )

        # Rename to failed (replaces _paused suffix)
        success, new_path = _rename_to_terminal(paused_plan, '_failed', session_id, temp_db)

        assert success
        assert Path(new_path).name == "feature_failed.md"  # Replaces _paused, not appends
        assert Path(new_path).exists()

    def test_session_still_active_not_renamed(self, tmp_path, temp_db):
        """When session is still active (execution), don't rename yet."""
        # Create a session in execution phase
        session_id = db.create_session("Test feature", db_path=temp_db)
        db.update_session(
            session_id,
            {'phase': Phase.EXECUTION, 'status': Status.ACTIVE},
            temp_db
        )

        # Session is still running - verify it's not in a terminal state
        session = db.get_session(session_id, temp_db)
        assert session['phase'] == Phase.EXECUTION
        assert session['status'] == Status.ACTIVE

        # In watch mode, we would check:
        # if session.get('phase') != Phase.PAUSED:
        #     # then check for terminal state
        # This test verifies the state is as expected for the check


# =============================================================================
# MCP Cleanup Tests
# =============================================================================


class TestCleanupCommand:
    """Test orchestrator cleanup command."""

    def test_cleanup_no_processes(self, runner):
        """Test cleanup when no orphaned processes exist."""
        with patch('subprocess.run') as mock_run:
            # pgrep returns non-zero when no matches found
            mock_run.return_value = Mock(returncode=1, stdout='')
            result = runner.invoke(cli, ['cleanup'])
            assert result.exit_code == 0
            assert 'No matching MCP processes found' in result.output

    def test_cleanup_dry_run(self, runner):
        """Test cleanup dry run shows but doesn't kill."""
        with patch('subprocess.run') as mock_run:
            # First call is pgrep, returns process
            # Subsequent calls check process details
            mock_run.side_effect = [
                Mock(returncode=0, stdout='12345\n'),  # pgrep for first pattern
                Mock(returncode=1, stdout=''),         # pgrep for second pattern
                Mock(returncode=0, stdout='node mcp-server-playwright'),  # ps -p
            ]
            result = runner.invoke(cli, ['cleanup', '--dry-run'])
            assert result.exit_code == 0
            assert 'Dry run' in result.output
            assert 'PID 12345' in result.output
            # Verify kill was NOT called
            kill_calls = [c for c in mock_run.call_args_list if 'kill' in str(c)]
            assert len(kill_calls) == 0

    def test_cleanup_conservative_by_default(self, runner):
        """Test that cleanup uses conservative patterns by default."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1, stdout='')
            result = runner.invoke(cli, ['cleanup'])
            assert result.exit_code == 0
            assert 'conservative patterns' in result.output.lower()

    def test_cleanup_all_flag_warning(self, runner):
        """Test that --all flag shows warning."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout='12345\n'),  # pgrep pattern 1
                Mock(returncode=1, stdout=''),         # pgrep pattern 2
                Mock(returncode=1, stdout=''),         # pgrep pattern 3
                Mock(returncode=1, stdout=''),         # pgrep pattern 4
                Mock(returncode=0, stdout='node mcp'),  # ps -p
            ]
            result = runner.invoke(cli, ['cleanup', '--all', '--dry-run'])
            assert result.exit_code == 0
            assert 'WARNING' in result.output
            assert 'other applications' in result.output

    def test_cleanup_custom_pattern(self, runner):
        """Test cleanup with custom pattern."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout='99999\n'),  # pgrep custom pattern
                Mock(returncode=0, stdout='custom-mcp-server'),  # ps -p
            ]
            result = runner.invoke(cli, ['cleanup', '-p', 'my-custom-mcp', '--dry-run'])
            assert result.exit_code == 0
            assert 'PID 99999' in result.output

    def test_cleanup_force_skips_confirm(self, runner):
        """Test that --force skips confirmation prompt."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout='12345\n'),  # pgrep
                Mock(returncode=1, stdout=''),         # pgrep pattern 2
                Mock(returncode=0, stdout='node mcp'),  # ps -p
                Mock(returncode=0, stdout=''),         # kill
            ]
            result = runner.invoke(cli, ['cleanup', '--force'])
            assert result.exit_code == 0
            assert 'Killed PID 12345' in result.output

    def test_cleanup_abort_on_no_confirm(self, runner):
        """Test that cleanup aborts when user says no."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout='12345\n'),  # pgrep
                Mock(returncode=1, stdout=''),         # pgrep pattern 2
                Mock(returncode=0, stdout='node mcp'),  # ps -p
            ]
            # Simulate user typing 'n' to decline
            result = runner.invoke(cli, ['cleanup'], input='n\n')
            assert 'Aborted' in result.output


class TestDetectMcpProcesses:
    """Test the _detect_mcp_processes helper function."""

    def test_detect_no_processes(self):
        """Test detection returns empty when no processes."""
        from orchestrator_auto.cli import _detect_mcp_processes

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1, stdout='')
            processes, error = _detect_mcp_processes()
            assert processes == []
            assert error is None

    def test_detect_finds_processes(self):
        """Test detection finds MCP processes."""
        from orchestrator_auto.cli import _detect_mcp_processes

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout='12345\n67890\n'),  # First pattern
                Mock(returncode=1, stdout=''),                 # Second pattern
            ]
            processes, error = _detect_mcp_processes()
            assert error is None
            assert len(processes) == 2
            assert processes[0][2] == '12345'
            assert processes[1][2] == '67890'

    def test_detect_extended_patterns(self):
        """Test detection with extended patterns."""
        from orchestrator_auto.cli import _detect_mcp_processes

        with patch('subprocess.run') as mock_run:
            # 2 default patterns + 2 extended patterns
            mock_run.side_effect = [
                Mock(returncode=1, stdout=''),  # Default 1
                Mock(returncode=1, stdout=''),  # Default 2
                Mock(returncode=0, stdout='99999\n'),  # Extended 1
                Mock(returncode=1, stdout=''),  # Extended 2
            ]
            processes, error = _detect_mcp_processes(include_extended=True)
            assert error is None
            assert len(processes) == 1
            assert processes[0][2] == '99999'

    @patch('platform.system')
    def test_detect_windows_returns_error(self, mock_platform):
        """Test that Windows returns error status, not empty list."""
        from orchestrator_auto.cli import _detect_mcp_processes

        mock_platform.return_value = "Windows"
        processes, error = _detect_mcp_processes()
        assert processes == []
        assert error == "windows"

    def test_detect_pgrep_missing(self):
        """Test that missing pgrep returns error status."""
        from orchestrator_auto.cli import _detect_mcp_processes

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError("pgrep not found")
            processes, error = _detect_mcp_processes()
            assert processes == []
            assert error == "pgrep_missing"

    def test_detect_dedupes_pids(self):
        """Test that duplicate PIDs are deduped."""
        from orchestrator_auto.cli import _detect_mcp_processes

        with patch('subprocess.run') as mock_run:
            # Same PID matches both patterns
            mock_run.side_effect = [
                Mock(returncode=0, stdout='12345\n'),  # First pattern
                Mock(returncode=0, stdout='12345\n'),  # Second pattern (same PID)
            ]
            processes, error = _detect_mcp_processes()
            assert error is None
            assert len(processes) == 1  # Deduped!
            assert processes[0][2] == '12345'


class TestGracefulKill:
    """Test the _graceful_kill helper function."""

    def test_sigterm_success(self):
        """Test successful SIGTERM termination."""
        from orchestrator_auto.cli import _graceful_kill

        with patch('subprocess.run') as mock_run, \
             patch('orchestrator_auto.cli._is_process_running') as mock_running, \
             patch('time.sleep'):
            mock_run.return_value = Mock(returncode=0, stderr='')
            mock_running.return_value = False  # Process exits after SIGTERM

            success, method, error = _graceful_kill("12345")

            assert success is True
            assert method == "SIGTERM"
            assert error is None

    def test_sigkill_escalation(self):
        """Test escalation to SIGKILL when SIGTERM doesn't work."""
        from orchestrator_auto.cli import _graceful_kill

        with patch('subprocess.run') as mock_run, \
             patch('orchestrator_auto.cli._is_process_running') as mock_running, \
             patch('time.sleep'):
            mock_run.side_effect = [
                Mock(returncode=0, stderr=''),  # SIGTERM succeeds but...
                Mock(returncode=0, stderr=''),  # SIGKILL needed
            ]
            mock_running.return_value = True  # Process keeps running

            success, method, error = _graceful_kill("12345")

            assert success is True
            assert method == "SIGKILL"
            assert error is None

    def test_process_already_gone(self):
        """Test handling of already-terminated process."""
        from orchestrator_auto.cli import _graceful_kill

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1, stderr='No such process')

            success, method, error = _graceful_kill("12345")

            assert success is True
            assert method == "already_gone"
            assert error is None

    def test_permission_denied(self):
        """Test handling of permission denied error."""
        from orchestrator_auto.cli import _graceful_kill

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1, stderr='Operation not permitted')

            success, method, error = _graceful_kill("12345")

            assert success is False
            assert method is None
            assert "Operation not permitted" in error


class TestCheckMcpSection:
    """Test the MCP section of the check command."""

    def test_check_mcp_no_processes(self, runner, temp_db):
        """Test check command shows no MCP processes."""
        from orchestrator_auto.cli import _detect_mcp_processes

        with patch('orchestrator_auto.cli._detect_mcp_processes') as mock_detect, \
             patch('orchestrator_auto.cli.detect_auth') as mock_auth, \
             patch('subprocess.run'):  # For API connection test
            mock_detect.return_value = ([], None)
            mock_auth.return_value = Mock(
                is_configured=False,
                signals=[],
                has_multiple=False
            )

            result = runner.invoke(cli, ['check'])

            assert '5. MCP Processes' in result.output
            assert 'No MCP server processes detected' in result.output

    def test_check_mcp_processes_found(self, runner, temp_db):
        """Test check command shows detected MCP processes."""
        with patch('orchestrator_auto.cli._detect_mcp_processes') as mock_detect, \
             patch('orchestrator_auto.cli.detect_auth') as mock_auth:
            mock_detect.return_value = (
                [("Playwright MCP Server", "pattern", "12345")],
                None
            )
            mock_auth.return_value = Mock(
                is_configured=False,
                signals=[],
                has_multiple=False
            )

            result = runner.invoke(cli, ['check'])

            assert '5. MCP Processes' in result.output
            assert 'MCP processes detected: 1 running' in result.output
            assert 'PID: 12345' in result.output
            assert 'orchestrator cleanup --dry-run' in result.output

    def test_check_mcp_windows_not_supported(self, runner, temp_db):
        """Test check command shows Windows not supported message."""
        with patch('orchestrator_auto.cli._detect_mcp_processes') as mock_detect, \
             patch('orchestrator_auto.cli.detect_auth') as mock_auth:
            mock_detect.return_value = ([], "windows")
            mock_auth.return_value = Mock(
                is_configured=False,
                signals=[],
                has_multiple=False
            )

            result = runner.invoke(cli, ['check'])

            assert '5. MCP Processes' in result.output
            assert 'not supported on Windows' in result.output

    def test_check_mcp_pgrep_missing(self, runner, temp_db):
        """Test check command shows pgrep missing message."""
        with patch('orchestrator_auto.cli._detect_mcp_processes') as mock_detect, \
             patch('orchestrator_auto.cli.detect_auth') as mock_auth:
            mock_detect.return_value = ([], "pgrep_missing")
            mock_auth.return_value = Mock(
                is_configured=False,
                signals=[],
                has_multiple=False
            )

            result = runner.invoke(cli, ['check'])

            assert '5. MCP Processes' in result.output
            assert 'pgrep not found' in result.output
