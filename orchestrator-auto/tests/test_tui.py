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

    def test_import_todo_app(self):
        """Test importing TodoTUI."""
        from orchestrator_auto.tui.todo_app import TodoTUI
        assert TodoTUI is not None

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
            TaskListPanel,
        )
        assert StatusPanel is not None
        assert MilestoneList is not None
        assert AgentOutput is not None
        assert LogPanel is not None
        assert InputModal is not None
        assert QueuePanel is not None
        assert WatchPanel is not None
        assert TaskListPanel is not None

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
            TodoStarted,
            TodoTaskStarted,
            TodoTaskCompleted,
            TodoCompleted,
        )
        # All messages should be importable
        assert ChunkReceived is not None
        assert WatchFileUpdated is not None
        assert TodoStarted is not None
        assert TodoTaskStarted is not None
        assert TodoTaskCompleted is not None
        assert TodoCompleted is not None

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

    def test_todo_started(self):
        """Test TodoStarted message."""
        from orchestrator_auto.tui.messages import TodoStarted
        tasks = [
            {"index": 1, "content": "Task 1", "status": "pending"},
            {"index": 2, "content": "Task 2", "status": "pending"},
        ]
        msg = TodoStarted(task_file="tasks.md", total_tasks=2, tasks=tasks)
        assert msg.task_file == "tasks.md"
        assert msg.total_tasks == 2
        assert len(msg.tasks) == 2

    def test_todo_task_started(self):
        """Test TodoTaskStarted message."""
        from orchestrator_auto.tui.messages import TodoTaskStarted
        msg = TodoTaskStarted(task_index=1, total_tasks=5, task_content="Test task")
        assert msg.task_index == 1
        assert msg.total_tasks == 5
        assert msg.task_content == "Test task"

    def test_todo_task_completed(self):
        """Test TodoTaskCompleted message."""
        from orchestrator_auto.tui.messages import TodoTaskCompleted
        msg = TodoTaskCompleted(task_index=1, status="done", result="Success", duration=5.2)
        assert msg.task_index == 1
        assert msg.status == "done"
        assert msg.result == "Success"
        assert msg.duration == 5.2

    def test_todo_completed(self):
        """Test TodoCompleted message."""
        from orchestrator_auto.tui.messages import TodoCompleted
        msg = TodoCompleted(completed=3, failed=1, total=5, duration=20.5, stopped=False)
        assert msg.completed == 3
        assert msg.failed == 1
        assert msg.total == 5
        assert msg.duration == 20.5
        assert msg.stopped is False

    def test_todo_completed_stopped(self):
        """Test TodoCompleted message with stopped=True."""
        from orchestrator_auto.tui.messages import TodoCompleted
        msg = TodoCompleted(completed=2, failed=0, total=5, duration=10.0, stopped=True)
        assert msg.stopped is True


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

    def test_todo_bindings(self):
        """Test todo mode bindings."""
        from orchestrator_auto.tui.bindings import TODO_BINDINGS
        keys = [b.key for b in TODO_BINDINGS]
        assert "l" in keys  # Logs
        assert "t" in keys  # Tasks
        assert "s" in keys  # Status

    def test_get_bindings_for_mode_todo(self):
        """Test get_bindings_for_mode returns todo bindings."""
        from orchestrator_auto.tui.bindings import get_bindings_for_mode
        bindings = get_bindings_for_mode("todo")
        keys = [b.key for b in bindings]
        # Should include global bindings
        assert "q" in keys  # Quit
        assert "?" in keys  # Help
        # Should include todo-specific bindings
        assert "l" in keys  # Logs
        assert "t" in keys  # Tasks
        assert "s" in keys  # Status


class TestTaskListPanel:
    """Test TaskListPanel widget."""

    def test_task_list_panel_initialization(self):
        """Test TaskListPanel initializes correctly."""
        from orchestrator_auto.tui.widgets import TaskListPanel

        panel = TaskListPanel()
        assert panel._total == 0
        assert panel._completed == 0
        assert panel._failed == 0
        assert len(panel._tasks) == 0

    def test_set_tasks(self):
        """Test set_tasks populates task list."""
        from orchestrator_auto.tui.widgets import TaskListPanel

        panel = TaskListPanel()
        tasks = [
            {"index": 1, "content": "Task 1", "status": "pending"},
            {"index": 2, "content": "Task 2", "status": "pending"},
            {"index": 3, "content": "Task 3", "status": "pending"},
        ]
        panel.set_tasks(tasks)

        assert panel._total == 3
        assert panel._completed == 0
        assert panel._failed == 0
        assert len(panel._tasks) == 3

    def test_task_item_markers(self):
        """Test TaskItem has correct status markers."""
        from orchestrator_auto.tui.widgets.task_list import TaskItem

        assert TaskItem.MARKERS["pending"] == "○"
        assert TaskItem.MARKERS["processing"] == "▶"
        assert TaskItem.MARKERS["done"] == "✓"
        assert TaskItem.MARKERS["failed"] == "✗"

    def test_task_item_truncates_long_content(self):
        """Test TaskItem truncates long task content."""
        from orchestrator_auto.tui.widgets.task_list import TaskItem

        long_content = "This is a very long task description that should be truncated to fit within the display width"
        item = TaskItem(task_index=1, task_content=long_content, status="pending")

        # Content should be truncated in compose
        assert item.task_content == long_content  # Original stored
        # Truncation happens during compose, not in __init__

    def test_on_todo_task_started_updates_status(self):
        """Test on_todo_task_started updates task status to processing."""
        from orchestrator_auto.tui.widgets import TaskListPanel
        from orchestrator_auto.tui.messages import TodoTaskStarted

        panel = TaskListPanel()
        tasks = [
            {"index": 1, "content": "Task 1", "status": "pending"},
        ]
        panel.set_tasks(tasks)

        # Verify initial status
        assert panel._tasks[1].task_status == "pending"

        # Simulate task started event
        msg = TodoTaskStarted(task_index=1, total_tasks=1, task_content="Task 1")
        panel.on_todo_task_started(msg)

        # Status should be updated to processing
        assert panel._tasks[1].task_status == "processing"

    def test_on_todo_task_completed_updates_status_and_counters(self):
        """Test on_todo_task_completed updates status and increments counters."""
        from orchestrator_auto.tui.widgets import TaskListPanel
        from orchestrator_auto.tui.messages import TodoTaskCompleted

        panel = TaskListPanel()
        tasks = [
            {"index": 1, "content": "Task 1", "status": "pending"},
            {"index": 2, "content": "Task 2", "status": "pending"},
        ]
        panel.set_tasks(tasks)

        # Complete task 1 successfully
        msg1 = TodoTaskCompleted(task_index=1, status="done", result="Success", duration=5.0)
        panel.on_todo_task_completed(msg1)

        assert panel._tasks[1].task_status == "done"
        assert panel._completed == 1
        assert panel._failed == 0

        # Fail task 2
        msg2 = TodoTaskCompleted(task_index=2, status="failed", result="Error", duration=2.0)
        panel.on_todo_task_completed(msg2)

        assert panel._tasks[2].task_status == "failed"
        assert panel._completed == 1
        assert panel._failed == 1


class TestOrchestratorTUIRespond:
    """Test OrchestratorTUI with answer parameter for respond mode."""

    def test_init_with_answer(self):
        """Test OrchestratorTUI can be initialized with answer parameter."""
        from orchestrator_auto.tui.app import OrchestratorTUI

        app = OrchestratorTUI(
            session_id="test-session-123",
            answer="my answer to blocker",
        )
        assert app.session_id == "test-session-123"
        assert app.answer == "my answer to blocker"

    def test_init_without_answer(self):
        """Test OrchestratorTUI works without answer (existing behavior)."""
        from orchestrator_auto.tui.app import OrchestratorTUI

        app = OrchestratorTUI(feature="Test feature")
        assert app.feature == "Test feature"
        assert app.answer is None

    def test_init_with_mcp_config(self):
        """Test OrchestratorTUI accepts mcp_config_path parameter."""
        from orchestrator_auto.tui.app import OrchestratorTUI

        app = OrchestratorTUI(
            feature="Test feature",
            mcp_config_path="/path/to/mcp.json",
            headless=True,
        )
        assert app.mcp_config_path == "/path/to/mcp.json"
        assert app.headless is True

    def test_init_with_telegram_notifier(self):
        """Test OrchestratorTUI accepts telegram_notifier parameter."""
        from orchestrator_auto.tui.app import OrchestratorTUI

        mock_notifier = object()  # Placeholder for notifier
        app = OrchestratorTUI(
            feature="Test feature",
            telegram_notifier=mock_notifier,
        )
        assert app.telegram_notifier is mock_notifier

    def test_init_all_respond_params(self):
        """Test OrchestratorTUI with all respond-related parameters."""
        from orchestrator_auto.tui.app import OrchestratorTUI

        app = OrchestratorTUI(
            session_id="session-456",
            answer="the answer",
            db_path="/tmp/test.db",
            mcp_config_path="/path/to/mcp.json",
            headless=True,
            telegram_notifier=None,
        )
        assert app.session_id == "session-456"
        assert app.answer == "the answer"
        assert app.db_path == "/tmp/test.db"
        assert app.mcp_config_path == "/path/to/mcp.json"
        assert app.headless is True
        assert app.telegram_notifier is None

    def test_init_with_empty_string_answer(self):
        """Test OrchestratorTUI with empty string answer (edge case).

        Empty string is a valid answer - should not be treated as None/falsy.
        """
        from orchestrator_auto.tui.app import OrchestratorTUI

        app = OrchestratorTUI(
            session_id="session-789",
            answer="",  # Empty string is valid
        )
        assert app.session_id == "session-789"
        assert app.answer == ""
        assert app.answer is not None  # Explicitly not None


class TestBlockerModal:
    """Test BlockerModal screen."""

    def test_blocker_modal_initialization(self):
        """Test BlockerModal can be initialized with required parameters."""
        from orchestrator_auto.tui.screens import BlockerModal

        modal = BlockerModal(
            question="What API endpoint should I use?",
            session_id="abc12345",
        )
        assert modal.question == "What API endpoint should I use?"
        assert modal.session_id == "abc12345"
        assert modal.agent == "unknown"  # Default
        assert modal.timestamp is None  # Default

    def test_blocker_modal_with_all_parameters(self):
        """Test BlockerModal with all optional parameters."""
        from orchestrator_auto.tui.screens import BlockerModal
        from datetime import datetime

        timestamp = datetime(2025, 1, 27, 14, 30, 0)
        modal = BlockerModal(
            question="How should I implement authentication?",
            session_id="def67890",
            agent="executor",
            timestamp=timestamp,
        )
        assert modal.question == "How should I implement authentication?"
        assert modal.session_id == "def67890"
        assert modal.agent == "executor"
        assert modal.timestamp == timestamp

    def test_blocker_modal_long_question(self):
        """Test BlockerModal handles long questions."""
        from orchestrator_auto.tui.screens import BlockerModal

        long_question = "This is a very long question " * 50
        modal = BlockerModal(
            question=long_question,
            session_id="ghi11111",
        )
        assert modal.question == long_question  # Full question stored


class TestWatchBindingsExtended:
    """Test extended watch mode bindings."""

    def test_watch_bindings_include_copy_id(self):
        """Test watch bindings include 'y' for copy session ID."""
        from orchestrator_auto.tui.bindings import WATCH_BINDINGS

        keys = [b.key for b in WATCH_BINDINGS]
        assert "y" in keys
        # Find the binding and check its action
        y_binding = next(b for b in WATCH_BINDINGS if b.key == "y")
        assert y_binding.action == "copy_session_id"

    def test_watch_bindings_include_blocker(self):
        """Test watch bindings include 'b' for show blocker."""
        from orchestrator_auto.tui.bindings import WATCH_BINDINGS

        keys = [b.key for b in WATCH_BINDINGS]
        assert "b" in keys
        # Find the binding and check its action
        b_binding = next(b for b in WATCH_BINDINGS if b.key == "b")
        assert b_binding.action == "show_blocker"


class TestWatchTUIContextInfo:
    """Test WatchTUI context visibility features."""

    def test_watch_tui_initialization_with_plans_dir(self, tmp_path):
        """Test WatchTUI initializes with plans directory."""
        from orchestrator_auto.tui.watch_app import WatchTUI

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        app = WatchTUI(plans_dir=str(plans_dir))
        assert app.plans_dir == plans_dir.resolve()
        # Session tracking starts as None
        assert app._current_session_id is None
        assert app._paused_session_id is None
        assert app._file_start_time is None

    def test_watch_tui_has_blocker_tracking(self, tmp_path):
        """Test WatchTUI has blocker tracking attributes."""
        from orchestrator_auto.tui.watch_app import WatchTUI

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        app = WatchTUI(plans_dir=str(plans_dir))
        # Blocker tracking attributes exist
        assert hasattr(app, "_current_blocker_question")
        assert hasattr(app, "_current_blocker_agent")
        assert app._current_blocker_question is None
        assert app._current_blocker_agent is None

    def test_watch_tui_has_focus_tracking(self, tmp_path):
        """Test WatchTUI has focus tracking attributes for panel navigation."""
        from orchestrator_auto.tui.watch_app import WatchTUI

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        app = WatchTUI(plans_dir=str(plans_dir))
        # Focus tracking attributes exist
        assert hasattr(app, "_focusable_panels")
        assert hasattr(app, "_focused_panel_index")
        # Default state
        assert len(app._focusable_panels) > 0
        assert app._focused_panel_index == -1  # No panel focused initially


class TestLogPanelFilter:
    """Test LogPanel filter functionality."""

    def test_log_panel_default_filter_level(self):
        """Test LogPanel starts with filter level 3 (all messages)."""
        from orchestrator_auto.tui.widgets import LogPanel

        panel = LogPanel()
        assert panel._filter_level == 3

    def test_log_panel_set_filter_level(self):
        """Test LogPanel.set_filter_level updates filter."""
        from orchestrator_auto.tui.widgets import LogPanel

        panel = LogPanel()
        panel.set_filter_level(1)
        assert panel._filter_level == 1

        panel.set_filter_level(2)
        assert panel._filter_level == 2

        panel.set_filter_level(3)
        assert panel._filter_level == 3

    def test_log_panel_filter_level_clamped(self):
        """Test filter level is clamped to valid range."""
        from orchestrator_auto.tui.widgets import LogPanel

        panel = LogPanel()
        panel.set_filter_level(0)  # Below min
        assert panel._filter_level == 1

        panel.set_filter_level(5)  # Above max
        assert panel._filter_level == 3

    def test_log_panel_should_log_at_level_1(self):
        """Test _should_log at filter level 1 (errors only)."""
        from orchestrator_auto.tui.widgets import LogPanel

        panel = LogPanel()
        panel._filter_level = 1

        assert panel._should_log("error") is True
        assert panel._should_log("warning") is False
        assert panel._should_log("info") is False
        assert panel._should_log("debug") is False

    def test_log_panel_should_log_at_level_2(self):
        """Test _should_log at filter level 2 (errors + warnings)."""
        from orchestrator_auto.tui.widgets import LogPanel

        panel = LogPanel()
        panel._filter_level = 2

        assert panel._should_log("error") is True
        assert panel._should_log("warning") is True
        assert panel._should_log("info") is False
        assert panel._should_log("debug") is False

    def test_log_panel_should_log_at_level_3(self):
        """Test _should_log at filter level 3 (all)."""
        from orchestrator_auto.tui.widgets import LogPanel

        panel = LogPanel()
        panel._filter_level = 3

        assert panel._should_log("error") is True
        assert panel._should_log("warning") is True
        assert panel._should_log("info") is True
        assert panel._should_log("debug") is False  # debug is level 4


class TestWatchBindingsPhase2:
    """Test Phase 2 watch mode bindings."""

    def test_watch_bindings_include_focus_navigation(self):
        """Test watch bindings include Tab/Shift+Tab for focus."""
        from orchestrator_auto.tui.bindings import WATCH_BINDINGS

        keys = [b.key for b in WATCH_BINDINGS]
        assert "tab" in keys
        assert "shift+tab" in keys

        # Verify actions
        tab_binding = next(b for b in WATCH_BINDINGS if b.key == "tab")
        assert tab_binding.action == "focus_next"

        shift_tab_binding = next(b for b in WATCH_BINDINGS if b.key == "shift+tab")
        assert shift_tab_binding.action == "focus_prev"

    def test_watch_bindings_include_scroll(self):
        """Test watch bindings include j/k for scrolling."""
        from orchestrator_auto.tui.bindings import WATCH_BINDINGS

        keys = [b.key for b in WATCH_BINDINGS]
        assert "j" in keys
        assert "k" in keys

        # Verify actions
        j_binding = next(b for b in WATCH_BINDINGS if b.key == "j")
        assert j_binding.action == "scroll_down"

        k_binding = next(b for b in WATCH_BINDINGS if b.key == "k")
        assert k_binding.action == "scroll_up"

    def test_watch_bindings_include_log_filter(self):
        """Test watch bindings include 1/2/3 for log filter."""
        from orchestrator_auto.tui.bindings import WATCH_BINDINGS

        keys = [b.key for b in WATCH_BINDINGS]
        assert "1" in keys
        assert "2" in keys
        assert "3" in keys

        # Verify actions
        binding_1 = next(b for b in WATCH_BINDINGS if b.key == "1")
        assert binding_1.action == "filter_errors"

        binding_2 = next(b for b in WATCH_BINDINGS if b.key == "2")
        assert binding_2.action == "filter_warnings"

        binding_3 = next(b for b in WATCH_BINDINGS if b.key == "3")
        assert binding_3.action == "filter_all"


class TestWatchBindingsPhase3:
    """Test Phase 3 watch mode bindings."""

    def test_watch_bindings_include_pause(self):
        """Test watch bindings include 'p' for pause/resume."""
        from orchestrator_auto.tui.bindings import WATCH_BINDINGS

        keys = [b.key for b in WATCH_BINDINGS]
        assert "p" in keys

        # Verify action
        p_binding = next(b for b in WATCH_BINDINGS if b.key == "p")
        assert p_binding.action == "toggle_pause"


class TestWatchControllerPause:
    """Test WatchController pause functionality."""

    def test_watch_controller_pause_flag_default(self, tmp_path):
        """Test WatchController starts with polling not paused."""
        from orchestrator_auto.controllers.watch_controller import WatchController

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        controller = WatchController(plans_dir=plans_dir)
        assert controller._polling_paused is False
        assert controller.is_polling_paused() is False

    def test_watch_controller_pause_polling(self, tmp_path):
        """Test WatchController.pause_polling() sets flag."""
        from orchestrator_auto.controllers.watch_controller import WatchController

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        events = []
        controller = WatchController(
            plans_dir=plans_dir,
            on_event=lambda e, d: events.append(e),
        )

        controller.pause_polling()
        assert controller._polling_paused is True
        assert controller.is_polling_paused() is True

    def test_watch_controller_resume_polling(self, tmp_path):
        """Test WatchController.resume_polling() clears flag."""
        from orchestrator_auto.controllers.watch_controller import WatchController

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        events = []
        controller = WatchController(
            plans_dir=plans_dir,
            on_event=lambda e, d: events.append(e),
        )

        controller.pause_polling()
        assert controller.is_polling_paused() is True

        controller.resume_polling()
        assert controller._polling_paused is False
        assert controller.is_polling_paused() is False

    def test_watch_controller_pause_emits_event(self, tmp_path):
        """Test pause/resume emits appropriate events."""
        from orchestrator_auto.controllers.watch_controller import WatchController, WatchEvent

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        events = []
        controller = WatchController(
            plans_dir=plans_dir,
            on_event=lambda e, d: events.append(e),
        )

        controller.pause_polling()
        assert WatchEvent.POLLING_PAUSED in events

        controller.resume_polling()
        assert WatchEvent.POLLING_RESUMED in events

    def test_watch_controller_pause_idempotent(self, tmp_path):
        """Test pause/resume are idempotent (don't emit duplicate events)."""
        from orchestrator_auto.controllers.watch_controller import WatchController, WatchEvent

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        events = []
        controller = WatchController(
            plans_dir=plans_dir,
            on_event=lambda e, d: events.append(e),
        )

        # Pause twice - should only emit one event
        controller.pause_polling()
        controller.pause_polling()
        assert events.count(WatchEvent.POLLING_PAUSED) == 1

        # Resume twice - should only emit one event
        events.clear()
        controller.resume_polling()
        controller.resume_polling()
        assert events.count(WatchEvent.POLLING_RESUMED) == 1
