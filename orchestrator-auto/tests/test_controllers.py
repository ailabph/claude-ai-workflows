"""
Tests for controller abstractions.

Tests the QueueController and WatchController interfaces.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from orchestrator_auto.controllers import (
    QueueController,
    QueueEvent,
    QueueItem,
    QueueState,
    WatchController,
    WatchEvent,
    WatchResult,
    WatchState,
)


class TestQueueControllerInit:
    """Tests for QueueController initialization."""

    def test_init_with_defaults(self):
        """Controller initializes with default values."""
        controller = QueueController(project_id="test-project")

        assert controller.project_id == "test-project"
        assert controller.db_path is None
        assert controller.auto_commit is False
        assert controller.show_activity is True
        assert controller._should_stop is False

    def test_init_with_callbacks(self):
        """Controller accepts callbacks."""
        on_event = Mock()
        on_chunk = Mock()
        on_output = Mock()

        controller = QueueController(
            project_id="test-project",
            on_event=on_event,
            on_chunk=on_chunk,
            on_output=on_output,
        )

        assert controller.on_event is on_event
        assert controller.on_chunk is on_chunk
        assert controller.on_output is on_output


class TestQueueControllerHeartbeat:
    """Tests for heartbeat checking."""

    def test_heartbeat_recent_with_iso_format(self):
        """Recent heartbeat returns True (ISO format)."""
        controller = QueueController(project_id="test")

        recent_time = (datetime.now() - timedelta(minutes=5)).isoformat()
        session = {"heartbeat_at": recent_time}

        assert controller.is_heartbeat_recent(session, inactive_minutes=20) is True

    def test_heartbeat_old_returns_false(self):
        """Old heartbeat returns False."""
        controller = QueueController(project_id="test")

        old_time = (datetime.now() - timedelta(minutes=30)).isoformat()
        session = {"heartbeat_at": old_time}

        assert controller.is_heartbeat_recent(session, inactive_minutes=20) is False

    def test_heartbeat_missing_returns_false(self):
        """Missing heartbeat returns False."""
        controller = QueueController(project_id="test")
        session = {}

        assert controller.is_heartbeat_recent(session) is False


class TestQueueControllerState:
    """Tests for queue state management."""

    def test_stop_sets_flag(self):
        """Stop method sets _should_stop flag."""
        controller = QueueController(project_id="test")

        assert controller._should_stop is False
        controller.stop()
        assert controller._should_stop is True


class TestQueueEvent:
    """Tests for QueueEvent enum."""

    def test_event_values(self):
        """All expected events are defined."""
        assert QueueEvent.STARTED.value == "started"
        assert QueueEvent.ITEM_STARTED.value == "item_started"
        assert QueueEvent.ITEM_COMPLETED.value == "item_completed"
        assert QueueEvent.ITEM_FAILED.value == "item_failed"
        assert QueueEvent.ITEM_PAUSED.value == "item_paused"
        assert QueueEvent.COMPLETED.value == "completed"
        assert QueueEvent.HALTED.value == "halted"


class TestQueueItem:
    """Tests for QueueItem dataclass."""

    def test_creation(self):
        """QueueItem can be created with required fields."""
        item = QueueItem(
            id="item-1",
            position=0,
            plan_path="/path/to/plan.md",
            feature_description="Test feature",
            status="pending",
        )

        assert item.id == "item-1"
        assert item.position == 0
        assert item.plan_path == "/path/to/plan.md"
        assert item.feature_description == "Test feature"
        assert item.status == "pending"
        assert item.session_id is None
        assert item.error_message is None


class TestQueueState:
    """Tests for QueueState dataclass."""

    def test_default_values(self):
        """QueueState has sensible defaults."""
        state = QueueState()

        assert state.items == []
        assert state.current_index == 0
        assert state.is_running is False
        assert state.completed_count == 0
        assert state.failed_count == 0
        assert state.paused_count == 0


class TestWatchControllerInit:
    """Tests for WatchController initialization."""

    def test_init_with_defaults(self, tmp_path):
        """Controller initializes with default values."""
        controller = WatchController(plans_dir=tmp_path)

        assert controller.plans_dir == tmp_path.resolve()
        assert controller.poll_interval == 2
        assert controller.auto_convert is False  # Default changed to disabled
        assert controller._should_stop is False

    def test_init_with_custom_values(self, tmp_path):
        """Controller accepts custom configuration."""
        on_event = Mock()

        controller = WatchController(
            plans_dir=tmp_path,
            poll_interval=5,
            auto_convert=False,
            on_event=on_event,
            auto_commit=True,
        )

        assert controller.poll_interval == 5
        assert controller.auto_convert is False
        assert controller.on_event is on_event
        assert controller.auto_commit is True


class TestWatchControllerCandidates:
    """Tests for watch candidate detection."""

    def test_valid_md_file_is_candidate(self, tmp_path):
        """Regular .md file is a watch candidate."""
        controller = WatchController(plans_dir=tmp_path)
        plan = tmp_path / "feature.md"
        plan.touch()

        assert controller.is_watch_candidate(plan) is True

    def test_non_md_file_is_not_candidate(self, tmp_path):
        """Non-.md files are not candidates."""
        controller = WatchController(plans_dir=tmp_path)
        txt_file = tmp_path / "readme.txt"
        txt_file.touch()

        assert controller.is_watch_candidate(txt_file) is False

    def test_quarantined_file_is_not_candidate(self, tmp_path):
        """Files with quarantine prefix are not candidates."""
        controller = WatchController(plans_dir=tmp_path)
        quarantined = tmp_path / "_orchestrator-skip__feature.md"
        quarantined.touch()

        assert controller.is_watch_candidate(quarantined) is False

    def test_done_file_is_not_candidate(self, tmp_path):
        """Files with _done suffix are not candidates."""
        controller = WatchController(plans_dir=tmp_path)
        done = tmp_path / "feature_done.md"
        done.touch()

        assert controller.is_watch_candidate(done) is False

    def test_failed_file_is_not_candidate(self, tmp_path):
        """Files with _failed suffix are not candidates."""
        controller = WatchController(plans_dir=tmp_path)
        failed = tmp_path / "feature_failed.md"
        failed.touch()

        assert controller.is_watch_candidate(failed) is False

    def test_paused_file_is_not_candidate(self, tmp_path):
        """Files with _paused suffix are not candidates."""
        controller = WatchController(plans_dir=tmp_path)
        paused = tmp_path / "feature_paused.md"
        paused.touch()

        assert controller.is_watch_candidate(paused) is False


class TestWatchControllerPendingPlans:
    """Tests for pending plan detection."""

    def test_empty_directory(self, tmp_path):
        """Empty directory returns empty list."""
        controller = WatchController(plans_dir=tmp_path)

        assert controller.get_pending_plans() == []

    def test_single_plan(self, tmp_path):
        """Single valid plan is returned."""
        controller = WatchController(plans_dir=tmp_path)
        plan = tmp_path / "feature.md"
        plan.write_text("# Feature")

        pending = controller.get_pending_plans()

        assert len(pending) == 1
        assert pending[0] == plan

    def test_filters_non_candidates(self, tmp_path):
        """Non-candidate files are filtered out."""
        controller = WatchController(plans_dir=tmp_path)

        (tmp_path / "feature.md").write_text("# Feature")
        (tmp_path / "done_done.md").write_text("# Done")
        (tmp_path / "_orchestrator-skip__old.md").write_text("# Old")

        pending = controller.get_pending_plans()

        assert len(pending) == 1
        assert pending[0].name == "feature.md"


class TestWatchControllerTerminalRename:
    """Tests for terminal state renaming."""

    def test_strip_terminal_suffix_done(self, tmp_path):
        """Strips _done suffix."""
        controller = WatchController(plans_dir=tmp_path)

        assert controller._strip_terminal_suffix("feature_done") == "feature"

    def test_strip_terminal_suffix_failed(self, tmp_path):
        """Strips _failed suffix."""
        controller = WatchController(plans_dir=tmp_path)

        assert controller._strip_terminal_suffix("feature_failed") == "feature"

    def test_strip_terminal_suffix_paused(self, tmp_path):
        """Strips _paused suffix."""
        controller = WatchController(plans_dir=tmp_path)

        assert controller._strip_terminal_suffix("feature_paused") == "feature"

    def test_strip_terminal_suffix_no_suffix(self, tmp_path):
        """Returns unchanged if no terminal suffix."""
        controller = WatchController(plans_dir=tmp_path)

        assert controller._strip_terminal_suffix("feature") == "feature"

    def test_rename_to_terminal_success(self, tmp_path):
        """Successfully renames file to terminal state."""
        controller = WatchController(plans_dir=tmp_path)
        plan = tmp_path / "feature.md"
        plan.write_text("# Feature")

        success, new_path = controller.rename_to_terminal(plan, "_done")

        assert success is True
        assert "feature_done.md" in new_path
        assert (tmp_path / "feature_done.md").exists()
        assert not plan.exists()

    def test_rename_replaces_existing_terminal_suffix(self, tmp_path):
        """Renaming replaces existing terminal suffix."""
        controller = WatchController(plans_dir=tmp_path)
        paused = tmp_path / "feature_paused.md"
        paused.write_text("# Feature")

        success, new_path = controller.rename_to_terminal(paused, "_done")

        assert success is True
        assert "feature_done.md" in new_path
        assert (tmp_path / "feature_done.md").exists()


class TestWatchControllerConvertedPath:
    """Tests for converted path finding."""

    def test_first_converted_path(self, tmp_path):
        """Returns _converted.md when no collisions."""
        controller = WatchController(plans_dir=tmp_path)
        original = tmp_path / "feature.md"

        result = controller._find_available_converted_path(original)

        assert result == tmp_path / "feature_converted.md"

    def test_second_converted_path(self, tmp_path):
        """Returns _converted_2.md when first exists."""
        controller = WatchController(plans_dir=tmp_path)
        original = tmp_path / "feature.md"
        (tmp_path / "feature_converted.md").write_text("# Converted")

        result = controller._find_available_converted_path(original)

        assert result == tmp_path / "feature_converted_2.md"


class TestWatchEvent:
    """Tests for WatchEvent enum."""

    def test_event_values(self):
        """All expected events are defined."""
        assert WatchEvent.STARTED.value == "started"
        assert WatchEvent.FILE_FOUND.value == "file_found"
        assert WatchEvent.FILE_COMPLETED.value == "file_completed"
        assert WatchEvent.FILE_FAILED.value == "file_failed"
        assert WatchEvent.FILE_PAUSED.value == "file_paused"
        assert WatchEvent.FILE_SKIPPED.value == "file_skipped"
        assert WatchEvent.STOPPED.value == "stopped"


class TestWatchResult:
    """Tests for WatchResult dataclass."""

    def test_creation(self):
        """WatchResult can be created with required fields."""
        result = WatchResult(status="completed")

        assert result.status == "completed"
        assert result.session_id is None
        assert result.executed_path is None
        assert result.error is None

    def test_creation_with_all_fields(self, tmp_path):
        """WatchResult can be created with all fields."""
        path = tmp_path / "feature.md"
        result = WatchResult(
            status="failed",
            session_id="sess-123",
            executed_path=path,
            error="Some error",
        )

        assert result.status == "failed"
        assert result.session_id == "sess-123"
        assert result.executed_path == path
        assert result.error == "Some error"


class TestWatchState:
    """Tests for WatchState dataclass."""

    def test_default_values(self):
        """WatchState has sensible defaults."""
        state = WatchState()

        assert state.poll_interval == 2
        assert state.auto_convert is False  # Default changed to disabled
        assert state.is_running is False
        assert state.is_paused is False
        assert state.completed_count == 0
        assert state.failed_count == 0


class TestWatchControllerState:
    """Tests for watch state management."""

    def test_get_state(self, tmp_path):
        """get_state returns current state."""
        controller = WatchController(
            plans_dir=tmp_path,
            poll_interval=10,
            auto_convert=False,
        )

        state = controller.get_state()

        assert state.directory == tmp_path.resolve()
        assert state.poll_interval == 10
        assert state.auto_convert is False
        assert state.is_running is True  # hasn't stopped yet
        assert state.is_paused is False

    def test_stop_sets_flag(self, tmp_path):
        """stop() sets _should_stop flag."""
        controller = WatchController(plans_dir=tmp_path)

        assert controller._should_stop is False
        controller.stop()
        assert controller._should_stop is True
