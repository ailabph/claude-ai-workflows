"""
Tests for TUI components.

These tests verify that TUI widgets and screens can be instantiated
and their basic functionality works correctly.
"""

import pytest

# Skip all TUI tests if textual is not installed
pytest.importorskip("textual")


class TestTUIImports:
    """Test that TUI components can be imported."""

    def test_import_main_app(self):
        """Test importing OrchestratorTUI."""
        from orchestrator_auto.tui.app import OrchestratorTUI
        assert OrchestratorTUI is not None

    def test_import_queue_app(self):
        """Test importing QueueTUI."""
        from orchestrator_auto.tui.queue_app import QueueTUI
        assert QueueTUI is not None

    def test_import_watch_app(self):
        """Test importing WatchTUI."""
        from orchestrator_auto.tui.watch_app import WatchTUI
        assert WatchTUI is not None

    def test_import_widgets(self):
        """Test importing TUI widgets."""
        from orchestrator_auto.tui.widgets import (
            StatusPanel,
            MilestoneList,
            AgentOutput,
            LogPanel,
            InputModal,
            QueuePanel,
            WatchPanel,
        )
        assert StatusPanel is not None
        assert MilestoneList is not None
        assert AgentOutput is not None
        assert LogPanel is not None
        assert InputModal is not None
        assert QueuePanel is not None
        assert WatchPanel is not None

    def test_import_screens(self):
        """Test importing TUI screens."""
        from orchestrator_auto.tui.screens import HelpScreen, SessionPickerScreen
        assert HelpScreen is not None
        assert SessionPickerScreen is not None

    def test_import_messages(self):
        """Test importing TUI messages."""
        from orchestrator_auto.tui.messages import (
            ChunkReceived,
            StateChanged,
            OutputReceived,
            InputRequested,
            WorkflowStarted,
            WorkflowCompleted,
            WorkflowError,
            MilestoneUpdated,
            QueueStarted,
            QueueCompleted,
            QueueHalted,
            WatchStarted,
            WatchStopped,
            WatchPaused,
            WatchFileUpdated,
        )
        # All messages should be importable
        assert ChunkReceived is not None
        assert WatchFileUpdated is not None

    def test_import_adapter(self):
        """Test importing TUI adapters."""
        from orchestrator_auto.tui.adapter import TUIOutputAdapter, TUIInputProvider
        assert TUIOutputAdapter is not None
        assert TUIInputProvider is not None


class TestMessages:
    """Test TUI message classes."""

    def test_chunk_received(self):
        """Test ChunkReceived message."""
        from orchestrator_auto.tui.messages import ChunkReceived
        msg = ChunkReceived(chunk="test chunk", agent="executor")
        assert msg.chunk == "test chunk"
        assert msg.agent == "executor"

    def test_state_changed(self):
        """Test StateChanged message."""
        from orchestrator_auto.tui.messages import StateChanged

        class MockState:
            phase = "DISCOVERY"
            status = "ACTIVE"

        msg = StateChanged(state=MockState(), previous_phase="INIT")
        assert msg.state.phase == "DISCOVERY"
        assert msg.previous_phase == "INIT"

    def test_workflow_started(self):
        """Test WorkflowStarted message."""
        from orchestrator_auto.tui.messages import WorkflowStarted
        msg = WorkflowStarted(session_id="abc123", feature="Test feature")
        assert msg.session_id == "abc123"
        assert msg.feature == "Test feature"

    def test_queue_started(self):
        """Test QueueStarted message."""
        from orchestrator_auto.tui.messages import QueueStarted
        items = [{"position": 1, "feature": "F1", "status": "pending"}]
        msg = QueueStarted(total_items=1, items=items)
        assert msg.total_items == 1
        assert len(msg.items) == 1

    def test_watch_file_updated_with_rename(self):
        """Test WatchFileUpdated message with rename."""
        from orchestrator_auto.tui.messages import WatchFileUpdated
        msg = WatchFileUpdated(
            filename="plan_done.md",
            status="completed",
            original_filename="plan.md",
        )
        assert msg.filename == "plan_done.md"
        assert msg.status == "completed"
        assert msg.original_filename == "plan.md"


class TestHelpScreen:
    """Test HelpScreen."""

    def test_help_screen_modes(self):
        """Test HelpScreen can be created for different modes."""
        from orchestrator_auto.tui.screens import HelpScreen

        for mode in ["session", "queue", "watch"]:
            screen = HelpScreen(mode=mode)
            assert screen.mode == mode


class TestSessionPicker:
    """Test SessionPickerScreen."""

    def test_session_picker_empty(self):
        """Test SessionPickerScreen with no sessions."""
        from orchestrator_auto.tui.screens import SessionPickerScreen
        screen = SessionPickerScreen(sessions=[])
        assert len(screen.sessions) == 0

    def test_session_picker_with_sessions(self):
        """Test SessionPickerScreen with sessions."""
        from orchestrator_auto.tui.screens import SessionPickerScreen
        sessions = [
            {"id": "abc123", "feature_description": "Test", "phase": "PAUSED", "status": "paused"},
            {"id": "def456", "feature_description": "Test2", "phase": "EXECUTION", "status": "active"},
        ]
        screen = SessionPickerScreen(sessions=sessions)
        assert len(screen.sessions) == 2


class TestAgentOutput:
    """Test AgentOutput widget handles orchestrator tags safely."""

    def test_write_chunk_with_progress_report_tag(self):
        """Test that write_chunk handles [PROGRESS_REPORT] tags without crashing."""
        from orchestrator_auto.tui.widgets import AgentOutput

        widget = AgentOutput()
        # This would crash with markup=True due to unmatched [/PROGRESS_REPORT]
        chunk = "Perfect!\n\n[PROGRESS_REPORT]\n## Milestone 1\n[/PROGRESS_REPORT]\n"
        # Should not raise MarkupError
        widget.write_chunk(chunk, agent="executor")

    def test_write_chunk_with_plan_ready_tag(self):
        """Test that write_chunk handles [PLAN_READY] tags without crashing."""
        from orchestrator_auto.tui.widgets import AgentOutput

        widget = AgentOutput()
        chunk = "[PLAN_READY]\n## Plan Overview\n"
        widget.write_chunk(chunk, agent="planner")

    def test_write_chunk_with_blocked_tag(self):
        """Test that write_chunk handles [BLOCKED] tags without crashing."""
        from orchestrator_auto.tui.widgets import AgentOutput

        widget = AgentOutput()
        chunk = "[BLOCKED]\nNeed user input\n[/BLOCKED]"
        widget.write_chunk(chunk, agent="executor")

    def test_write_chunk_with_mixed_tags(self):
        """Test that write_chunk handles various orchestrator tags."""
        from orchestrator_auto.tui.widgets import AgentOutput

        widget = AgentOutput()
        # Mix of various orchestrator tags that could be misinterpreted as Rich markup
        chunks = [
            "[MILESTONE_APPROVED]",
            "[CHANGES_REQUESTED]",
            "[HUMAN_INPUT_NEEDED]",
            "[CLARIFICATION_NEEDED]",
            "[bold]not actual markup[/bold]",
            "[red]some text[/red]",
        ]
        for chunk in chunks:
            widget.write_chunk(chunk, agent="test")

    def test_write_message_with_style(self):
        """Test that write_message with style works correctly."""
        from orchestrator_auto.tui.widgets import AgentOutput

        widget = AgentOutput()
        widget.write_message("Test message", style="bold green")

    def test_write_message_plain(self):
        """Test that write_message without style works correctly."""
        from orchestrator_auto.tui.widgets import AgentOutput

        widget = AgentOutput()
        widget.write_message("Plain message")

    def test_write_separator(self):
        """Test that write_separator works correctly."""
        from orchestrator_auto.tui.widgets import AgentOutput

        widget = AgentOutput()
        widget.write_separator()

    def test_agent_filter_initialization(self):
        """Test that agent filter is set correctly."""
        from orchestrator_auto.tui.widgets import AgentOutput

        # Test with filter
        widget = AgentOutput(agent_filter="planner")
        assert widget._agent_filter == "planner"
        # Agent tracking starts empty (only updates when mounted)
        assert widget._current_agent == ""

        # Test without filter
        widget2 = AgentOutput()
        assert widget2._agent_filter is None
        assert widget2._current_agent == ""

    def test_clear_output_resets_state(self):
        """Test that clear_output resets agent tracking."""
        from orchestrator_auto.tui.widgets import AgentOutput

        widget = AgentOutput()
        # State starts empty
        assert widget._current_agent == ""
        # After clear, still empty (widget not mounted, so clear does nothing harmful)
        widget.clear_output()
        assert widget._current_agent == ""

    def test_widget_initialization(self):
        """Test that AgentOutput initializes with correct defaults."""
        from orchestrator_auto.tui.widgets import AgentOutput

        widget = AgentOutput()
        # Check widget attributes
        assert widget._agent_filter is None
        assert widget._current_agent == ""
        assert widget._header_title == "AGENT OUTPUT"

        # With custom header
        widget2 = AgentOutput(header_title="CUSTOM")
        assert widget2._header_title == "CUSTOM"


class TestBindings:
    """Test TUI bindings."""

    def test_global_bindings(self):
        """Test global bindings are defined."""
        from orchestrator_auto.tui.bindings import GLOBAL_BINDINGS
        keys = [b.key for b in GLOBAL_BINDINGS]
        assert "q" in keys  # Quit
        assert "?" in keys  # Help

    def test_session_bindings(self):
        """Test session mode bindings."""
        from orchestrator_auto.tui.bindings import SESSION_BINDINGS
        keys = [b.key for b in SESSION_BINDINGS]
        assert "l" in keys  # Toggle logs
        assert "m" in keys  # Toggle milestones

    def test_queue_bindings(self):
        """Test queue mode bindings."""
        from orchestrator_auto.tui.bindings import QUEUE_BINDINGS
        keys = [b.key for b in QUEUE_BINDINGS]
        assert "c" in keys  # Clear queue
        assert "r" in keys  # Refresh

    def test_watch_bindings(self):
        """Test watch mode bindings."""
        from orchestrator_auto.tui.bindings import WATCH_BINDINGS
        keys = [b.key for b in WATCH_BINDINGS]
        assert "c" in keys  # Clear
        assert "r" in keys  # Respond
        assert "R" in keys  # Refresh
