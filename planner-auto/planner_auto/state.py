"""
Phase and status enums, transition rules, and command permissions for planner-auto.
"""

from enum import Enum


class Phase(str, Enum):
    """Session lifecycle phases."""
    SETUP = "SETUP"
    CONTEXT = "CONTEXT"
    DISCUSSION = "DISCUSSION"
    PLANNING = "PLANNING"
    REVIEW = "REVIEW"
    COMPLETE = "COMPLETE"


class Status(str, Enum):
    """Session status values."""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


# Valid phase transitions: source -> set of allowed targets
VALID_PHASE_TRANSITIONS: dict[Phase, set[Phase]] = {
    Phase.SETUP: {Phase.CONTEXT},
    Phase.CONTEXT: {Phase.DISCUSSION},
    Phase.DISCUSSION: {Phase.PLANNING},
    Phase.PLANNING: {Phase.REVIEW, Phase.COMPLETE},
    Phase.REVIEW: {Phase.PLANNING, Phase.COMPLETE},
    Phase.COMPLETE: set(),
}


# Commands allowed in each phase
# 'export' is allowed in any phase (handled separately)
PHASE_ALLOWED_COMMANDS: dict[Phase, set[str]] = {
    Phase.SETUP: {"start", "add-context", "status", "export"},
    Phase.CONTEXT: {"add-context", "status", "export"},
    Phase.DISCUSSION: {"discuss", "status", "export"},
    Phase.PLANNING: {"generate", "complete", "status", "export"},
    Phase.REVIEW: {"review", "complete", "status", "export"},
    Phase.COMPLETE: {"status", "export"},
}

# Commands allowed regardless of phase when status is PAUSED
PAUSED_ALLOWED_COMMANDS: set[str] = {"resume", "status", "export"}
