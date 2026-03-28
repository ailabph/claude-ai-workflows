"""Custom exception classes for planner-auto."""


class PlannerAutoError(Exception):
    """Base exception for planner-auto."""
    pass


class InvalidTransitionError(PlannerAutoError):
    """Raised when an invalid phase transition is attempted."""

    def __init__(self, current_phase: str, target_phase: str):
        self.current_phase = current_phase
        self.target_phase = target_phase
        super().__init__(
            f"Invalid phase transition: {current_phase} -> {target_phase}"
        )


class CommandNotAllowedError(PlannerAutoError):
    """Raised when a command is not allowed in the current phase/status."""

    def __init__(self, command: str, phase: str, status: str, reason: str = ""):
        self.command = command
        self.phase = phase
        self.status = status
        msg = f"Command '{command}' not allowed in phase={phase}, status={status}"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class SessionNotFoundError(PlannerAutoError):
    """Raised when a session ID is not found."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")


# ---------------------------------------------------------------------------
# SDK wrapper errors
# ---------------------------------------------------------------------------

class SDKError(PlannerAutoError):
    """Base exception for SDK wrapper errors."""
    pass


class SDKAuthError(SDKError):
    """Raised on authentication failures (invalid API key)."""
    pass


class SDKRateLimitError(SDKError):
    """Raised after exhausting rate-limit retries."""
    pass


class SDKTimeoutError(SDKError):
    """Raised after exhausting timeout/connection retries."""
    pass


class SDKResponseError(SDKError):
    """Raised on empty or malformed SDK responses."""
    pass


# ---------------------------------------------------------------------------
# Reviewer errors (Plan 2 — GPT-based reviewer adapter)
# ---------------------------------------------------------------------------

class ReviewerError(PlannerAutoError):
    """Base exception for reviewer adapter errors."""
    pass


class ReviewerAuthError(ReviewerError):
    """Raised when the OpenAI API key is missing or invalid."""
    pass


class ReviewerRateLimitError(ReviewerError):
    """Raised after exhausting rate-limit retries against the reviewer API."""
    pass


class ReviewerTimeoutError(ReviewerError):
    """Raised after exhausting timeout/connection retries against the reviewer API."""
    pass


class ReviewerResponseError(ReviewerError):
    """Raised when the reviewer returns an empty or unparseable response."""
    pass
