"""
Event dataclasses for orchestrator I/O.

These events are used to communicate state changes, streaming output,
and other notifications from the orchestrator to UI backends.
"""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..state import WorkflowState


@dataclass
class ChunkEvent:
    """
    Event for streaming text chunks from agents.

    Attributes:
        chunk: The text chunk received from the agent
        agent: Name of the agent ("planner" or "executor")
    """
    chunk: str
    agent: str


@dataclass
class StateChangeEvent:
    """
    Event for workflow state transitions.

    Attributes:
        state: The new workflow state
        previous_phase: The phase before this transition (if applicable)
        event_type: The transition event that caused this change
    """
    state: "WorkflowState"
    previous_phase: Optional[str] = None
    event_type: Optional[str] = None


@dataclass
class OutputEvent:
    """
    Event for orchestrator text output.

    Attributes:
        message: The output message text
        level: Log level ("info", "warning", "error", "debug")
    """
    message: str
    level: str = "info"


@dataclass
class InputRequestedEvent:
    """
    Event when the orchestrator needs user input.

    Used by TUI to show input modal when orchestrator
    calls input_provider.prompt() from worker thread.

    Attributes:
        prompt_text: The prompt to display to the user
        context: Additional context ("discovery", "blocker", etc.)
    """
    prompt_text: str
    context: str = "input"
