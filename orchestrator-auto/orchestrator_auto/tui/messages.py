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


class WatchSessionStarted(Message):
    """A new session has started in watch mode."""

    def __init__(
        self,
        session_id: str,
        planner_model: str,
        executor_model: str,
        phase: str = "execution",
        feature: Optional[str] = None,
        milestone_count: int = 0,
        milestone_names: Optional[list] = None,
        current_milestone: int = 0,
    ) -> None:
        self.session_id = session_id
        self.planner_model = planner_model
        self.executor_model = executor_model
        self.phase = phase
        self.feature = feature
        self.milestone_count = milestone_count
        self.milestone_names = milestone_names or []
        self.current_milestone = current_milestone
        super().__init__()


class TokenUsageReceived(Message):
    """Actual token usage received from API."""

    def __init__(
        self,
        agent: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        model: str = "",
        cost_usd: float = 0.0,
    ) -> None:
        self.agent = agent
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_tokens = cache_read_tokens
        self.model = model
        self.cost_usd = cost_usd
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


class TokensUsed(Message):
    """
    Token usage from an agent API call.

    Contains actual token counts from the Claude API response.
    """

    def __init__(
        self,
        agent: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
        model: Optional[str] = None,
        cost_usd: Optional[float] = None
    ) -> None:
        """
        Args:
            agent: Agent name ("planner" or "executor")
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated
            cache_creation_input_tokens: Tokens used for cache creation
            cache_read_input_tokens: Tokens read from cache
            model: Model used (e.g., "claude-opus-4-5-20251101")
            cost_usd: Cost of the API call in USD
        """
        self.agent = agent
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens
        self.model = model
        self.cost_usd = cost_usd
        super().__init__()


class TodoStarted(Message):
    """Emitted when todo execution starts."""

    def __init__(
        self,
        task_file: str,
        total_tasks: int,
        tasks: list,
    ) -> None:
        """
        Args:
            task_file: Path to the task file
            total_tasks: Total number of tasks to execute
            tasks: List of dicts with 'index', 'content', 'status'
        """
        self.task_file = task_file
        self.total_tasks = total_tasks
        self.tasks = tasks
        super().__init__()


class TodoTaskStarted(Message):
    """Emitted when a todo task starts."""

    def __init__(
        self,
        task_index: int,
        total_tasks: int,
        task_content: str,
    ) -> None:
        """
        Args:
            task_index: Current task index (1-based)
            total_tasks: Total number of tasks
            task_content: Content/description of the task
        """
        self.task_index = task_index
        self.total_tasks = total_tasks
        self.task_content = task_content
        super().__init__()


class TodoTaskCompleted(Message):
    """Emitted when a todo task completes."""

    def __init__(
        self,
        task_index: int,
        status: str,
        result: Optional[str],
        duration: float,
    ) -> None:
        """
        Args:
            task_index: Task index that completed (1-based)
            status: Task status ("done" | "failed")
            result: Result message or error message
            duration: Task execution duration in seconds
        """
        self.task_index = task_index
        self.status = status
        self.result = result
        self.duration = duration
        super().__init__()


class TodoCompleted(Message):
    """Emitted when all todo tasks complete (or stopped early)."""

    def __init__(
        self,
        completed: int,
        failed: int,
        total: int,
        duration: float,
        stopped: bool = False,
    ) -> None:
        """
        Args:
            completed: Number of completed tasks
            failed: Number of failed tasks
            total: Total number of tasks
            duration: Total execution duration in seconds
            stopped: True if stopped via q key before completion
        """
        self.completed = completed
        self.failed = failed
        self.total = total
        self.duration = duration
        self.stopped = stopped
        super().__init__()


# Sub-agent messages for Layout B
# Status constants to avoid string drift
EXPLORE_STATUS_PENDING = "pending"
EXPLORE_STATUS_RUNNING = "running"
EXPLORE_STATUS_COMPLETED = "completed"
EXPLORE_STATUS_FAILED = "failed"

VALIDATE_STATUS_PENDING = "pending"
VALIDATE_STATUS_RUNNING = "running"
VALIDATE_STATUS_PASSED = "passed"
VALIDATE_STATUS_ISSUES = "issues"
VALIDATE_STATUS_FAILED = "failed"
VALIDATE_STATUS_COMPLETED = "completed"  # For overall validation phase status


class ExploreStarted(Message):
    """Exploration sub-agent has started."""

    def __init__(self, milestone: int, query_count: int) -> None:
        """
        Args:
            milestone: Milestone number being explored
            query_count: Number of exploration queries to run
        """
        self.milestone = milestone
        self.query_count = query_count
        super().__init__()


class ExploreQueryUpdate(Message):
    """An exploration query status was updated."""

    def __init__(
        self,
        index: int,
        query: str,
        status: str,
        tokens_used: int = 0,
        is_partial: bool = False,
    ) -> None:
        """
        Args:
            index: Query index (0-based)
            query: Query text
            status: Query status (use EXPLORE_STATUS_* constants)
            tokens_used: Tokens used for this query
            is_partial: Whether result was truncated/timed out
        """
        self.index = index
        self.query = query
        self.status = status
        self.tokens_used = tokens_used
        self.is_partial = is_partial
        super().__init__()


class ExploreCompleted(Message):
    """Exploration sub-agent has completed."""

    def __init__(self, milestone: int, query_count: int, success_count: int) -> None:
        """
        Args:
            milestone: Milestone number that was explored
            query_count: Total number of queries run
            success_count: Number of successful queries
        """
        self.milestone = milestone
        self.query_count = query_count
        self.success_count = success_count
        # Computed field for convenience (clamped to prevent negative values)
        self.failed_count = max(0, query_count - success_count)
        super().__init__()


class ValidateStarted(Message):
    """Validation pipeline has started."""

    def __init__(self, milestone: int, file_count: int) -> None:
        """
        Args:
            milestone: Milestone number being validated
            file_count: Number of changed files to validate
        """
        self.milestone = milestone
        self.file_count = file_count
        super().__init__()


class ValidatorUpdate(Message):
    """A validator status was updated."""

    def __init__(
        self,
        name: str,
        status: str,
        issue_count: int = 0,
        high_count: int = 0,
        medium_count: int = 0,
    ) -> None:
        """
        Args:
            name: Validator name
            status: Status (use VALIDATE_STATUS_* constants)
            issue_count: Total issues found
            high_count: High severity issues
            medium_count: Medium severity issues
        """
        self.name = name
        self.status = status
        self.issue_count = issue_count
        self.high_count = high_count
        self.medium_count = medium_count
        super().__init__()


class ValidateCompleted(Message):
    """Validation pipeline has completed."""

    def __init__(
        self,
        milestone: int,
        total_issues: int,
        high_count: int,
        passed: bool,
    ) -> None:
        """
        Args:
            milestone: Milestone number that was validated
            total_issues: Total issues found across all validators
            high_count: Number of high severity issues
            passed: Whether validation passed (no blocking issues)
        """
        self.milestone = milestone
        self.total_issues = total_issues
        self.high_count = high_count
        self.passed = passed
        super().__init__()
