"""
State machine for orchestrator workflow phase transitions.

Manages the workflow state and validates transitions between phases:
- discovery → planning → execution → completed
- any → paused (on blocker)
- paused → previous phase (on human response)
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
from enum import Enum

from . import db


class Phase(str, Enum):
    """Workflow phases."""
    DISCOVERY = "discovery"
    PLANNING = "planning"
    EXECUTION = "execution"
    COMPLETED = "completed"
    PAUSED = "paused"


class Status(str, Enum):
    """Workflow status."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class TransitionEvent(str, Enum):
    """State transition events."""
    READY = "ready"  # User says /ready in discovery
    PLAN_APPROVED = "plan_approved"  # Plan is approved, start execution
    MILESTONE_APPROVED = "milestone_approved"  # Milestone approved, continue
    ALL_MILESTONES_DONE = "all_milestones_done"  # All milestones complete
    HUMAN_INPUT_NEEDED = "human_input_needed"  # Blocker occurred
    HUMAN_RESPONDED = "human_responded"  # Human provided response
    FAILED = "failed"  # Workflow failed


@dataclass
class WorkflowState:
    """
    Current state of the workflow.

    Attributes:
        session_id: Unique session identifier
        phase: Current phase (discovery, planning, execution, completed, paused)
        status: Current status (active, paused, completed, failed)
        current_milestone: Current milestone number (0 if not in execution)
        total_milestones: Total number of milestones
        previous_phase: Phase before pause (for resuming)
        plan_path: Path to plan document
        feature_description: Description of feature being implemented
    """
    session_id: str
    phase: str
    status: str
    current_milestone: int = 0
    total_milestones: int = 0
    previous_phase: Optional[str] = None
    plan_path: Optional[str] = None
    feature_description: Optional[str] = None

    @classmethod
    def from_db(cls, session_data: Dict[str, Any]) -> "WorkflowState":
        """Create WorkflowState from database session data."""
        return cls(
            session_id=session_data["id"],
            phase=session_data["phase"],
            status=session_data["status"],
            current_milestone=session_data.get("current_milestone", 0),
            total_milestones=session_data.get("total_milestones", 0),
            previous_phase=session_data.get("previous_phase"),
            plan_path=session_data.get("plan_path"),
            feature_description=session_data.get("feature_description"),
        )

    def to_db_update(self) -> Dict[str, Any]:
        """Convert state to database update dict."""
        return {
            "phase": self.phase,
            "status": self.status,
            "current_milestone": self.current_milestone,
            "total_milestones": self.total_milestones,
            "previous_phase": self.previous_phase,
            "plan_path": self.plan_path,
        }


class StateMachine:
    """
    Manages workflow state transitions.

    Validates transitions and persists state to database.
    """

    # Valid transitions: (from_phase, event) -> to_phase
    TRANSITIONS = {
        (Phase.DISCOVERY, TransitionEvent.READY): Phase.PLANNING,
        (Phase.PLANNING, TransitionEvent.PLAN_APPROVED): Phase.EXECUTION,
        (Phase.EXECUTION, TransitionEvent.MILESTONE_APPROVED): Phase.EXECUTION,
        (Phase.EXECUTION, TransitionEvent.ALL_MILESTONES_DONE): Phase.COMPLETED,
        # Pause transitions (from any phase)
        (Phase.DISCOVERY, TransitionEvent.HUMAN_INPUT_NEEDED): Phase.PAUSED,
        (Phase.PLANNING, TransitionEvent.HUMAN_INPUT_NEEDED): Phase.PAUSED,
        (Phase.EXECUTION, TransitionEvent.HUMAN_INPUT_NEEDED): Phase.PAUSED,
        # Resume from pause
        (Phase.PAUSED, TransitionEvent.HUMAN_RESPONDED): None,  # Resume to previous phase
        # Failure transitions
        (Phase.DISCOVERY, TransitionEvent.FAILED): Phase.COMPLETED,
        (Phase.PLANNING, TransitionEvent.FAILED): Phase.COMPLETED,
        (Phase.EXECUTION, TransitionEvent.FAILED): Phase.COMPLETED,
    }

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the state machine.

        Args:
            db_path: Optional path to database
        """
        self.db_path = db_path

    def get_state(self, session_id: str) -> Optional[WorkflowState]:
        """
        Load workflow state from database.

        Args:
            session_id: Session identifier

        Returns:
            WorkflowState or None if session not found
        """
        session = db.get_session(session_id, self.db_path)
        if not session:
            return None

        return WorkflowState.from_db(session)

    def can_transition(
        self,
        current_phase: str,
        event: str
    ) -> bool:
        """
        Check if a transition is valid.

        Args:
            current_phase: Current workflow phase
            event: Transition event

        Returns:
            True if transition is allowed
        """
        try:
            phase_enum = Phase(current_phase)
            event_enum = TransitionEvent(event)
            return (phase_enum, event_enum) in self.TRANSITIONS
        except (ValueError, KeyError):
            return False

    def transition(
        self,
        session_id: str,
        event: str,
        **kwargs
    ) -> Tuple[bool, Optional[WorkflowState], Optional[str]]:
        """
        Attempt a state transition.

        Args:
            session_id: Session identifier
            event: Transition event
            **kwargs: Additional data for the transition (e.g., plan_path, milestone_number)

        Returns:
            Tuple of (success, new_state, error_message)
        """
        # Load current state
        state = self.get_state(session_id)
        if not state:
            return False, None, f"Session {session_id} not found"

        # Check if transition is valid
        if not self.can_transition(state.phase, event):
            return False, state, f"Invalid transition: {state.phase} -> {event}"

        try:
            event_enum = TransitionEvent(event)
        except ValueError:
            return False, state, f"Unknown event: {event}"

        # Determine new phase
        phase_enum = Phase(state.phase)
        new_phase_enum = self.TRANSITIONS.get((phase_enum, event_enum))

        # Handle special cases
        if event_enum == TransitionEvent.HUMAN_RESPONDED and phase_enum == Phase.PAUSED:
            # Resume to previous phase
            if state.previous_phase:
                new_phase = state.previous_phase
                state.previous_phase = None
            else:
                new_phase = Phase.DISCOVERY.value
            state.phase = new_phase
            state.status = Status.ACTIVE.value

        elif event_enum == TransitionEvent.HUMAN_INPUT_NEEDED:
            # Save current phase before pausing
            state.previous_phase = state.phase
            state.phase = Phase.PAUSED.value
            state.status = Status.PAUSED.value

        elif event_enum == TransitionEvent.MILESTONE_APPROVED:
            # Stay in execution, increment milestone
            # If current_milestone is provided in kwargs, it's the milestone that was just approved
            # Otherwise, use the state's current milestone
            if "current_milestone" in kwargs:
                # The provided milestone was approved, so the next one is current_milestone + 1
                state.current_milestone = kwargs["current_milestone"] + 1
            else:
                # No milestone specified, just increment the current one
                state.current_milestone = state.current_milestone + 1

        elif event_enum == TransitionEvent.ALL_MILESTONES_DONE:
            state.phase = Phase.COMPLETED.value
            state.status = Status.COMPLETED.value

        elif event_enum == TransitionEvent.FAILED:
            state.phase = Phase.COMPLETED.value
            state.status = Status.FAILED.value

        elif new_phase_enum:
            # Standard transition
            state.phase = new_phase_enum.value

            # Update status based on new phase
            if new_phase_enum == Phase.COMPLETED:
                state.status = Status.COMPLETED.value
            else:
                state.status = Status.ACTIVE.value

        # Apply additional kwargs
        # Note: current_milestone is handled separately for MILESTONE_APPROVED event
        if "plan_path" in kwargs:
            state.plan_path = kwargs["plan_path"]
        if "total_milestones" in kwargs:
            state.total_milestones = kwargs["total_milestones"]
        if "current_milestone" in kwargs and event_enum != TransitionEvent.MILESTONE_APPROVED:
            # Only apply current_milestone from kwargs if it's NOT a milestone approval
            # (milestone approvals handle it specially by incrementing)
            state.current_milestone = kwargs["current_milestone"]

        # Persist to database
        db.update_session(
            session_id,
            state.to_db_update(),
            self.db_path
        )

        return True, state, None

    def reset_to_phase(
        self,
        session_id: str,
        phase: str
    ) -> Tuple[bool, Optional[WorkflowState], Optional[str]]:
        """
        Reset workflow to a specific phase (for error recovery).

        Args:
            session_id: Session identifier
            phase: Target phase

        Returns:
            Tuple of (success, new_state, error_message)
        """
        state = self.get_state(session_id)
        if not state:
            return False, None, f"Session {session_id} not found"

        try:
            Phase(phase)  # Validate phase
        except ValueError:
            return False, state, f"Invalid phase: {phase}"

        state.phase = phase
        state.status = Status.ACTIVE.value

        db.update_session(
            session_id,
            state.to_db_update(),
            self.db_path
        )

        return True, state, None
