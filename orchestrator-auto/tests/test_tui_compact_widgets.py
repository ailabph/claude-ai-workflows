"""Tests for compact TUI widgets.

These tests verify that compact TUI widgets can be instantiated
and their basic functionality works correctly.
"""

import pytest

# Skip all tests if textual is not installed
pytest.importorskip("textual")


class TestCompactWidgetImports:
    """Test that compact widgets can be imported."""

    def test_import_compact_sidebar(self):
        """Test importing CompactSidebar."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar
        assert CompactSidebar is not None

    def test_import_compact_milestone_row(self):
        """Test importing CompactMilestoneRow."""
        from orchestrator_auto.tui.widgets.compact_milestone_row import CompactMilestoneRow
        assert CompactMilestoneRow is not None

    def test_import_agent_toggle_panel(self):
        """Test importing AgentTogglePanel."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel
        assert AgentTogglePanel is not None

    def test_import_status_bar(self):
        """Test importing StatusBar."""
        from orchestrator_auto.tui.widgets.status_bar import StatusBar
        assert StatusBar is not None

    def test_widgets_exported_from_init(self):
        """Test that all compact widgets are exported from widgets __init__."""
        from orchestrator_auto.tui.widgets import (
            CompactSidebar,
            CompactMilestoneRow,
            AgentTogglePanel,
            StatusBar,
        )
        assert CompactSidebar is not None
        assert CompactMilestoneRow is not None
        assert AgentTogglePanel is not None
        assert StatusBar is not None


class TestCompactMilestoneRow:
    """Tests for CompactMilestoneRow widget."""

    def test_initialization(self):
        """Test CompactMilestoneRow initializes correctly."""
        from orchestrator_auto.tui.widgets.compact_milestone_row import CompactMilestoneRow

        row = CompactMilestoneRow()
        assert row is not None

    def test_icons_defined(self):
        """Test milestone icons are defined."""
        from orchestrator_auto.tui.widgets.compact_milestone_row import CompactMilestoneRow

        assert "completed" in CompactMilestoneRow.ICONS
        assert "active" in CompactMilestoneRow.ICONS
        assert "pending" in CompactMilestoneRow.ICONS
        assert "failed" in CompactMilestoneRow.ICONS

    def test_styles_defined(self):
        """Test milestone styles are defined."""
        from orchestrator_auto.tui.widgets.compact_milestone_row import CompactMilestoneRow

        assert "completed" in CompactMilestoneRow.STYLES
        assert "active" in CompactMilestoneRow.STYLES
        assert "pending" in CompactMilestoneRow.STYLES
        assert "failed" in CompactMilestoneRow.STYLES

    def test_set_milestones(self):
        """Test set_milestones stores data correctly."""
        from orchestrator_auto.tui.widgets.compact_milestone_row import CompactMilestoneRow

        row = CompactMilestoneRow()
        milestones = [
            {"id": 1, "title": "Setup", "status": "completed"},
            {"id": 2, "title": "Implement", "status": "active"},
            {"id": 3, "title": "Test", "status": "pending"},
        ]
        row.set_milestones(milestones, current=2)
        assert row.milestones == milestones
        assert row.current == 2

    def test_set_current(self):
        """Test set_current updates milestone statuses."""
        from orchestrator_auto.tui.widgets.compact_milestone_row import CompactMilestoneRow

        row = CompactMilestoneRow()
        milestones = [
            {"id": 1, "title": "M1", "status": "pending"},
            {"id": 2, "title": "M2", "status": "pending"},
            {"id": 3, "title": "M3", "status": "pending"},
        ]
        row.set_milestones(milestones, current=1)
        row.set_current(2)

        # M1 should be completed, M2 active, M3 pending
        assert row._milestones[0]["status"] == "completed"
        assert row._milestones[1]["status"] == "active"
        assert row._milestones[2]["status"] == "pending"

    def test_format_row_empty(self):
        """Test _format_row with no milestones."""
        from orchestrator_auto.tui.widgets.compact_milestone_row import CompactMilestoneRow

        row = CompactMilestoneRow()
        result = row._format_row()
        assert "No milestones" in result

    def test_format_row_with_milestones(self):
        """Test _format_row with milestones."""
        from orchestrator_auto.tui.widgets.compact_milestone_row import CompactMilestoneRow

        row = CompactMilestoneRow()
        milestones = [
            {"id": 1, "title": "M1", "status": "completed"},
            {"id": 2, "title": "M2", "status": "active"},
        ]
        row.set_milestones(milestones, current=2)
        result = row._format_row()
        # Should contain milestone numbers
        assert "1" in result
        assert "2" in result


class TestAgentTogglePanel:
    """Tests for AgentTogglePanel widget."""

    def test_initialization(self):
        """Test AgentTogglePanel initializes correctly."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        assert panel is not None

    def test_default_agent_is_executor(self):
        """Test that executor is the default active agent."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        assert panel.get_active_agent() == "executor"

    def test_toggle_switches_agent(self):
        """Test that toggle switches between agents."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        assert panel.get_active_agent() == "executor"
        panel.toggle_agent()
        assert panel.get_active_agent() == "planner"
        panel.toggle_agent()
        assert panel.get_active_agent() == "executor"

    def test_set_agent_explicit(self):
        """Test setting agent explicitly."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        panel.set_agent("planner")
        assert panel.get_active_agent() == "planner"
        panel.set_agent("executor")
        assert panel.get_active_agent() == "executor"

    def test_set_agent_invalid_ignored(self):
        """Test that invalid agent names are ignored."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        panel.set_agent("invalid")
        # Should remain at default
        assert panel.get_active_agent() == "executor"

    def test_set_agent_same_noop(self):
        """Test that setting same agent is a no-op."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        panel.set_agent("executor")  # Already executor
        assert panel.get_active_agent() == "executor"

    def test_buffers_initialized_empty(self):
        """Test that buffers start empty."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        assert len(panel._planner_buffer) == 0
        assert len(panel._executor_buffer) == 0

    def test_write_chunk_buffers_planner(self):
        """Test that planner chunks are buffered."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        panel.write_chunk("planner output", "planner")
        assert len(panel._planner_buffer) == 1
        assert panel._planner_buffer[0] == "planner output"

    def test_write_chunk_buffers_executor(self):
        """Test that executor chunks are buffered."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        panel.write_chunk("executor output", "executor")
        assert len(panel._executor_buffer) == 1
        assert panel._executor_buffer[0] == "executor output"

    def test_write_chunk_unknown_agent_ignored(self):
        """Test that unknown agent chunks are ignored."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        panel.write_chunk("unknown output", "unknown")
        assert len(panel._planner_buffer) == 0
        assert len(panel._executor_buffer) == 0

    def test_clear_buffers(self):
        """Test that clear_buffers empties both buffers."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        panel.write_chunk("planner output", "planner")
        panel.write_chunk("executor output", "executor")
        panel.clear_buffers()
        assert len(panel._planner_buffer) == 0
        assert len(panel._executor_buffer) == 0

    def test_get_title_planner(self):
        """Test _get_title returns PLANNER when planner active."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        panel.set_agent("planner")
        assert panel._get_title() == "PLANNER"

    def test_get_title_executor(self):
        """Test _get_title returns EXECUTOR when executor active."""
        from orchestrator_auto.tui.widgets.agent_toggle_panel import AgentTogglePanel

        panel = AgentTogglePanel()
        assert panel._get_title() == "EXECUTOR"


class TestStatusBar:
    """Tests for StatusBar widget."""

    def test_initialization(self):
        """Test StatusBar initializes correctly."""
        from orchestrator_auto.tui.widgets.status_bar import StatusBar

        bar = StatusBar()
        assert bar is not None

    def test_set_milestone(self):
        """Test set_milestone updates internal state."""
        from orchestrator_auto.tui.widgets.status_bar import StatusBar

        bar = StatusBar()
        bar.set_milestone(3, 5, "Implement Feature")
        assert bar._milestone_current == 3
        assert bar._milestone_total == 5
        assert bar._milestone_name == "Implement Feature"

    def test_set_activity(self):
        """Test set_activity updates internal state."""
        from orchestrator_auto.tui.widgets.status_bar import StatusBar

        bar = StatusBar()
        bar.set_activity("Processing...")
        assert bar._activity == "Processing..."

    def test_log_stores_message(self):
        """Test log method stores message."""
        from orchestrator_auto.tui.widgets.status_bar import StatusBar

        bar = StatusBar()
        bar.log("Test message", "info")
        assert bar._last_message == "Test message"

    def test_set_hint(self):
        """Test set_hint updates hint."""
        from orchestrator_auto.tui.widgets.status_bar import StatusBar

        bar = StatusBar()
        bar.set_hint("Press q to quit")
        assert bar._hint == "Press q to quit"

    def test_format_time(self):
        """Test _format_time returns HH:MM:SS format."""
        from orchestrator_auto.tui.widgets.status_bar import StatusBar

        bar = StatusBar()
        time_str = bar._format_time()
        # Should match HH:MM:SS pattern
        assert len(time_str) == 8
        assert time_str[2] == ":"
        assert time_str[5] == ":"

    def test_format_milestone_with_data(self):
        """Test _format_milestone with milestone data."""
        from orchestrator_auto.tui.widgets.status_bar import StatusBar

        bar = StatusBar()
        bar.set_milestone(2, 5)
        result = bar._format_milestone()
        assert result == "M2/5"

    def test_format_milestone_no_data(self):
        """Test _format_milestone with no milestone data."""
        from orchestrator_auto.tui.widgets.status_bar import StatusBar

        bar = StatusBar()
        result = bar._format_milestone()
        assert result == "M-/-"


class TestCompactSidebar:
    """Tests for CompactSidebar widget."""

    def test_initialization(self):
        """Test CompactSidebar initializes correctly."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        assert sidebar is not None

    def test_initial_state(self):
        """Test CompactSidebar has correct initial state."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        assert sidebar._current_file == "—"
        assert sidebar._milestone_current == 0
        assert sidebar._milestone_total == 0
        assert sidebar._tokens == 0
        assert sidebar._cost == 0.0
        assert sidebar._completed == 0
        assert sidebar._failed == 0
        assert sidebar._paused == 0

    def test_update_current_file(self):
        """Test update_current_file updates internal state."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        sidebar.update_current_file("PLAN_test.md", 2, 5, "EXECUTION")
        assert sidebar._current_file == "PLAN_test.md"
        assert sidebar._milestone_current == 2
        assert sidebar._milestone_total == 5
        assert sidebar._phase == "EXECUTION"

    def test_update_stats(self):
        """Test update_stats updates internal state."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        sidebar.update_stats(tokens=50000, cost=5.50, elapsed="01:23:45", api_calls=15)
        assert sidebar._tokens == 50000
        assert sidebar._cost == 5.50
        assert sidebar._elapsed == "01:23:45"
        assert sidebar._api_calls == 15

    def test_update_queue_counts(self):
        """Test update_queue_counts updates internal state."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        sidebar.update_queue_counts(completed=5, failed=1, paused=2)
        assert sidebar._completed == 5
        assert sidebar._failed == 1
        assert sidebar._paused == 2

    def test_set_polling_paused(self):
        """Test set_polling_paused updates state."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        sidebar.set_polling_paused(True)
        assert sidebar._is_polling_paused is True
        sidebar.set_polling_paused(False)
        assert sidebar._is_polling_paused is False

    def test_truncate_short_text(self):
        """Test _truncate with short text."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        result = sidebar._truncate("short", 10)
        assert result == "short"

    def test_truncate_long_text(self):
        """Test _truncate with long text."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        result = sidebar._truncate("this is a very long text", 10)
        assert len(result) == 10
        assert result.endswith("..")

    def test_format_tokens_small(self):
        """Test _format_tokens with small number."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        assert sidebar._format_tokens(500) == "500"

    def test_format_tokens_thousands(self):
        """Test _format_tokens with thousands."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        result = sidebar._format_tokens(50000)
        assert "K" in result

    def test_format_tokens_millions(self):
        """Test _format_tokens with millions."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        result = sidebar._format_tokens(1500000)
        assert "M" in result

    def test_format_progress_no_milestones(self):
        """Test _format_progress with no milestones."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        result = sidebar._format_progress()
        assert "M-/-" in result

    def test_format_progress_with_milestones(self):
        """Test _format_progress with milestones."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        sidebar._milestone_current = 2
        sidebar._milestone_total = 5
        sidebar._phase = "EXEC"
        result = sidebar._format_progress()
        assert "M2/5" in result
        assert "EXEC" in result

    def test_format_progress_paused(self):
        """Test _format_progress when paused."""
        from orchestrator_auto.tui.widgets.compact_sidebar import CompactSidebar

        sidebar = CompactSidebar()
        sidebar._is_polling_paused = True
        result = sidebar._format_progress()
        assert "PAUSED" in result


class TestWatchTUIVerboseParameter:
    """Test WatchTUI verbose parameter."""

    def test_watch_tui_accepts_verbose_false(self, tmp_path):
        """Test WatchTUI can be initialized with verbose=False."""
        from orchestrator_auto.tui.watch_app import WatchTUI

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        app = WatchTUI(plans_dir=str(plans_dir), verbose=False)
        assert app.verbose is False

    def test_watch_tui_accepts_verbose_true(self, tmp_path):
        """Test WatchTUI can be initialized with verbose=True."""
        from orchestrator_auto.tui.watch_app import WatchTUI

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        app = WatchTUI(plans_dir=str(plans_dir), verbose=True)
        assert app.verbose is True

    def test_watch_tui_default_verbose_is_false(self, tmp_path):
        """Test WatchTUI defaults to verbose=False (compact mode)."""
        from orchestrator_auto.tui.watch_app import WatchTUI

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        app = WatchTUI(plans_dir=str(plans_dir))
        assert app.verbose is False

    def test_focusable_panels_compact_mode(self, tmp_path):
        """Test focusable panels in compact mode."""
        from orchestrator_auto.tui.watch_app import WatchTUI

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        app = WatchTUI(plans_dir=str(plans_dir), verbose=False)
        assert "#agent-panel" in app._focusable_panels
        assert "#planner-output" not in app._focusable_panels

    def test_focusable_panels_verbose_mode(self, tmp_path):
        """Test focusable panels in verbose mode."""
        from orchestrator_auto.tui.watch_app import WatchTUI

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        app = WatchTUI(plans_dir=str(plans_dir), verbose=True)
        assert "#planner-output" in app._focusable_panels
        assert "#executor-output" in app._focusable_panels
        assert "#log-panel" in app._focusable_panels


class TestAgentToggleBindings:
    """Test agent toggle keybindings."""

    def test_watch_bindings_include_bracket_keys(self):
        """Test watch bindings include '[' and ']' for agent toggle."""
        from orchestrator_auto.tui.bindings import WATCH_BINDINGS

        keys = [b.key for b in WATCH_BINDINGS]
        assert "[" in keys
        assert "]" in keys

    def test_bracket_bindings_have_correct_actions(self):
        """Test '[' and ']' bindings have correct actions."""
        from orchestrator_auto.tui.bindings import WATCH_BINDINGS

        left_bracket = next((b for b in WATCH_BINDINGS if b.key == "["), None)
        right_bracket = next((b for b in WATCH_BINDINGS if b.key == "]"), None)

        assert left_bracket is not None
        assert left_bracket.action == "show_planner"

        assert right_bracket is not None
        assert right_bracket.action == "show_executor"

    def test_existing_bindings_unchanged(self):
        """Test that existing bindings are not modified."""
        from orchestrator_auto.tui.bindings import WATCH_BINDINGS

        # Verify critical existing bindings still work
        p_binding = next((b for b in WATCH_BINDINGS if b.key == "p"), None)
        assert p_binding is not None
        assert p_binding.action == "toggle_pause"  # NOT "show_planner"

        tab_binding = next((b for b in WATCH_BINDINGS if b.key == "tab"), None)
        assert tab_binding is not None
        assert tab_binding.action == "focus_next"  # NOT "toggle_agent"
