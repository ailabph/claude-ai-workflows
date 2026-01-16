"""
TUI adapters for orchestrator integration.

Provides thread-safe bridges between the orchestrator worker thread
and the Textual TUI main thread.
"""

import threading
from typing import Optional, Tuple, List, TYPE_CHECKING

from ..io import InputProvider
from . import messages

if TYPE_CHECKING:
    from textual.app import App


class TUIOutputAdapter:
    """
    Thread-safe bridge from orchestrator callbacks to TUI messages.

    This adapter receives callbacks from the orchestrator (running in a
    worker thread) and posts messages to the TUI app (running in the
    main thread) using call_from_thread().

    Usage:
        adapter = TUIOutputAdapter(app)
        orchestrator = Orchestrator(
            on_chunk=adapter.on_chunk,
            on_state_change=adapter.on_state_change,
            on_output=adapter.on_output,
        )
    """

    def __init__(self, app: "App") -> None:
        """
        Initialize the adapter.

        Args:
            app: The Textual app instance to post messages to.
        """
        self.app = app

    def on_chunk(self, chunk: str, agent: str) -> None:
        """
        Handle a streaming chunk from an agent.

        Thread-safe: posts message to TUI main thread.
        """
        self.app.call_from_thread(
            self.app.post_message,
            messages.ChunkReceived(chunk=chunk, agent=agent)
        )

    def on_state_change(self, state) -> None:
        """
        Handle an orchestrator state change.

        Thread-safe: posts message to TUI main thread.
        """
        self.app.call_from_thread(
            self.app.post_message,
            messages.StateChanged(state=state)
        )

    def on_output(self, message: str) -> None:
        """
        Handle a general output message.

        Thread-safe: posts message to TUI main thread.
        """
        self.app.call_from_thread(
            self.app.post_message,
            messages.OutputReceived(message=message)
        )

    def request_input(self, prompt_text: str, context: str = "input") -> None:
        """
        Request input from the user.

        Thread-safe: posts message to TUI main thread.
        """
        self.app.call_from_thread(
            self.app.post_message,
            messages.InputRequested(prompt_text=prompt_text, context=context)
        )

    def notify_workflow_started(self, session_id: str, feature: str) -> None:
        """Notify TUI that workflow started."""
        self.app.call_from_thread(
            self.app.post_message,
            messages.WorkflowStarted(session_id=session_id, feature=feature)
        )

    def notify_workflow_completed(self, session_id: str, success: bool, message: str = "") -> None:
        """Notify TUI that workflow completed."""
        self.app.call_from_thread(
            self.app.post_message,
            messages.WorkflowCompleted(session_id=session_id, success=success, message=message)
        )

    def notify_workflow_error(self, error: str, session_id: Optional[str] = None) -> None:
        """Notify TUI of a workflow error."""
        self.app.call_from_thread(
            self.app.post_message,
            messages.WorkflowError(error=error, session_id=session_id)
        )

    def notify_milestone_updated(self, milestone_id: int, title: str, status: str) -> None:
        """Notify TUI of milestone status change."""
        self.app.call_from_thread(
            self.app.post_message,
            messages.MilestoneUpdated(milestone_id=milestone_id, title=title, status=status)
        )

    def notify_milestones_loaded(self, milestones: list) -> None:
        """Notify TUI that milestones were loaded from plan."""
        self.app.call_from_thread(
            self.app.post_message,
            messages.MilestonesLoaded(milestones=milestones)
        )

    def notify_models_set(self, planner_model: str, executor_model: str) -> None:
        """Notify TUI of model configuration."""
        self.app.call_from_thread(
            self.app.post_message,
            messages.ModelsSet(planner_model=planner_model, executor_model=executor_model)
        )

    def notify_stats_updated(
        self,
        api_calls: int = None,
        tokens: int = None,
        elapsed_seconds: int = None
    ) -> None:
        """Notify TUI of stats update."""
        self.app.call_from_thread(
            self.app.post_message,
            messages.StatsUpdated(
                api_calls=api_calls,
                tokens=tokens,
                elapsed_seconds=elapsed_seconds
            )
        )

    def notify_tokens_used(
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
        Notify TUI of token usage from an API call.

        Args:
            agent: Agent name ("planner" or "executor")
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated
            cache_creation_input_tokens: Tokens used for cache creation
            cache_read_input_tokens: Tokens read from cache
            model: Model used
            cost_usd: Cost of the API call in USD
        """
        self.app.call_from_thread(
            self.app.post_message,
            messages.TokensUsed(
                agent=agent,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_creation_input_tokens=cache_creation_input_tokens,
                cache_read_input_tokens=cache_read_input_tokens,
                model=model,
                cost_usd=cost_usd
            )
        )


class TUIInputProvider(InputProvider):
    """
    Input provider that gets input from the TUI.

    Uses threading.Event for cross-thread synchronization between
    the worker thread (orchestrator) and the main thread (TUI).

    The workflow:
    1. Worker thread calls prompt() -> blocks on event
    2. TUI shows input modal and waits for user input
    3. User provides input, TUI calls provide_input()
    4. Worker thread unblocks and returns the input
    """

    def __init__(self, adapter: TUIOutputAdapter) -> None:
        """
        Initialize the input provider.

        Args:
            adapter: TUI output adapter for requesting input.
        """
        self.adapter = adapter
        self._input_event = threading.Event()
        self._input_result: Optional[Tuple[str, str]] = None
        self._current_prompt: Optional[str] = None

    def prompt(self, prompt_text: str, return_none_on_eof: bool = False) -> Tuple[Optional[str], Optional[str]]:
        """
        Prompt for user input.

        This method blocks the worker thread until input is provided
        via provide_input() from the TUI main thread.

        Args:
            prompt_text: The prompt to display.
            return_none_on_eof: If True, return (None, None) on EOF.

        Returns:
            Tuple of (display_text, full_content).
        """
        # Reset state
        self._input_event.clear()
        self._input_result = None
        self._current_prompt = prompt_text

        # Request input from TUI
        self.adapter.request_input(prompt_text, context="input")

        # Block until input is provided
        self._input_event.wait()

        # Return the result
        if self._input_result is None:
            if return_none_on_eof:
                return (None, None)
            return ("", "")

        return self._input_result

    def prompt_choice(self, prompt_text: str, choices: List[str], default: Optional[str] = None) -> str:
        """
        Prompt for a choice from a list.

        Args:
            prompt_text: The prompt to display.
            choices: List of choices.
            default: Default choice if user enters empty.

        Returns:
            The selected choice.
        """
        # Reset state
        self._input_event.clear()
        self._input_result = None
        self._current_prompt = prompt_text

        # Request choice input from TUI
        self.adapter.request_input(prompt_text, context="choice")

        # Block until input is provided
        self._input_event.wait()

        # Parse result
        if self._input_result is None or not self._input_result[1]:
            return default or (choices[0] if choices else "")

        # Return the choice (should be one of the choices)
        _, content = self._input_result
        if content in choices:
            return content
        return default or (choices[0] if choices else "")

    def provide_input(self, display_text: str, full_content: str) -> None:
        """
        Provide input in response to a prompt.

        Called from the TUI main thread when user provides input.

        Args:
            display_text: What was displayed to user.
            full_content: Full content of input (may include pasted content).
        """
        self._input_result = (display_text, full_content)
        self._input_event.set()

    def cancel_input(self) -> None:
        """
        Cancel the current input request.

        Called from the TUI main thread when user cancels.
        """
        self._input_result = None
        self._input_event.set()

    @property
    def current_prompt(self) -> Optional[str]:
        """Get the current pending prompt text."""
        return self._current_prompt
