"""
Custom Textual messages for TUI communication.

These messages are used to communicate between the worker thread
(running the orchestrator) and the main TUI thread.
"""

from textual.message import Message
from typing import Optional, Any


class ChunkReceived(Message):
    """A chunk of output was received from an agent."""

    def __init__(self, chunk: str, agent: str) -> None:
        self.chunk = chunk
        self.agent = agent
        super().__init__()


class StateChanged(Message):
    """The orchestrator state changed."""

    def __init__(self, state: Any, previous_phase: Optional[str] = None, event_type: Optional[str] = None) -> None:
        self.state = state
        self.previous_phase = previous_phase
        self.event_type = event_type
        super().__init__()


class OutputReceived(Message):
    """A general output message was received."""

    def __init__(self, message: str, level: str = "info") -> None:
        self.message = message
        self.level = level
        super().__init__()


class InputRequested(Message):
    """The orchestrator is requesting user input."""

    def __init__(self, prompt_text: str, context: str = "input") -> None:
        self.prompt_text = prompt_text
        self.context = context
        super().__init__()


class InputProvided(Message):
    """User provided input in response to InputRequested."""

    def __init__(self, display_text: str, full_content: str) -> None:
        self.display_text = display_text
        self.full_content = full_content
        super().__init__()


class WorkflowStarted(Message):
    """Workflow has started."""

    def __init__(self, session_id: str, feature: str) -> None:
        self.session_id = session_id
        self.feature = feature
        super().__init__()


class WorkflowCompleted(Message):
    """Workflow has completed."""

    def __init__(self, session_id: str, success: bool, message: str = "") -> None:
        self.session_id = session_id
        self.success = success
        self.message = message
        super().__init__()


class WorkflowError(Message):
    """Workflow encountered an error."""

    def __init__(self, error: str, session_id: Optional[str] = None) -> None:
        self.error = error
        self.session_id = session_id
        super().__init__()


class MilestoneUpdated(Message):
    """A milestone status was updated."""

    def __init__(self, milestone_id: int, title: str, status: str) -> None:
        self.milestone_id = milestone_id
        self.title = title
        self.status = status
        super().__init__()


class QueueItemUpdated(Message):
    """A queue item status was updated."""

    def __init__(self, position: int, status: str, feature: str, session_id: Optional[str] = None, error: Optional[str] = None) -> None:
        self.position = position
        self.status = status
        self.feature = feature
        self.session_id = session_id
        self.error = error
        super().__init__()


class QueueStarted(Message):
    """Queue processing has started."""

    def __init__(self, total_items: int, items: list) -> None:
        """
        Args:
            total_items: Total number of items in the queue
            items: List of dicts with 'position', 'feature', 'status'
        """
        self.total_items = total_items
        self.items = items
        super().__init__()


class QueueCompleted(Message):
    """Queue processing has completed."""

    def __init__(self, completed: int, failed: int, paused: int, total: int) -> None:
        self.completed = completed
        self.failed = failed
        self.paused = paused
        self.total = total
        super().__init__()


class QueueHalted(Message):
    """Queue processing was halted (e.g., due to failure)."""

    def __init__(self, reason: str, position: int) -> None:
        self.reason = reason
        self.position = position
        super().__init__()


class WatchStarted(Message):
    """Watch mode has started."""

    def __init__(self, directory: str, poll_interval: int, auto_convert: bool) -> None:
        self.directory = directory
        self.poll_interval = poll_interval
        self.auto_convert = auto_convert
        super().__init__()


class WatchStopped(Message):
    """Watch mode has stopped."""

    def __init__(self, completed: int, failed: int, paused: int) -> None:
        self.completed = completed
        self.failed = failed
        self.paused = paused
        super().__init__()


class WatchPaused(Message):
    """Watch mode is paused waiting for session resume."""

    def __init__(self, session_id: str, plan_path: str) -> None:
        self.session_id = session_id
        self.plan_path = plan_path
        super().__init__()


class WatchFileUpdated(Message):
    """A watched file status was updated."""

    def __init__(
        self,
        filename: str,
        status: str,
        error: Optional[str] = None,
        original_filename: Optional[str] = None,
    ) -> None:
        self.filename = filename
        self.status = status
        self.error = error
        # For terminal renames: the original filename before rename
        self.original_filename = original_filename
        super().__init__()


class WatchPendingUpdated(Message):
    """Pending files list was updated."""

    def __init__(self, pending_files: list[str]) -> None:
        self.pending_files = pending_files
        super().__init__()


class StatsUpdated(Message):
    """Statistics were updated (API calls, tokens, etc.)."""

    def __init__(
        self,
        api_calls: Optional[int] = None,
        tokens: Optional[int] = None,
        elapsed_seconds: Optional[int] = None
    ) -> None:
        self.api_calls = api_calls
        self.tokens = tokens
        self.elapsed_seconds = elapsed_seconds
        super().__init__()


class ModelsSet(Message):
    """Model configuration was set."""

    def __init__(self, planner_model: str, executor_model: str) -> None:
        self.planner_model = planner_model
        self.executor_model = executor_model
        super().__init__()


class MilestonesLoaded(Message):
    """
    Milestones were loaded from the plan.

    Note: The adapter provides notify_milestones_loaded() to trigger this,
    but the actual plan parsing and milestone extraction will be wired
    in Phase 4 when the engine emits milestone data after plan approval.
    """

    def __init__(self, milestones: list) -> None:
        """
        Args:
            milestones: List of dicts with 'id', 'title', 'status'
        """
        self.milestones = milestones
        super().__init__()
