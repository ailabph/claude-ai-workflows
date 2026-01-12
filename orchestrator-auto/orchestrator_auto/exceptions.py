"""
Custom exception hierarchy for orchestrator-auto.

All exceptions carry session context (session_id, log_path) for
user-friendly error reporting at the CLI boundary.
"""

from typing import Optional


class OrchestratorError(Exception):
    """
    Base exception for orchestrator errors.

    All orchestrator exceptions inherit from this class and carry
    session context for error reporting.

    Attributes:
        session_id: The session ID where the error occurred
        log_path: Path to the error log file (if available)
    """

    def __init__(
        self,
        message: str,
        session_id: Optional[str] = None,
        log_path: Optional[str] = None,
    ):
        self.session_id = session_id
        self.log_path = log_path
        super().__init__(message)


class AgentError(OrchestratorError):
    """
    Claude Agent SDK communication failure.

    Raised when agent calls fail due to:
    - Network/connection issues
    - API errors
    - Subprocess failures (exit code != 0)
    - Message reader errors
    """

    pass


class SessionStateError(OrchestratorError):
    """
    Invalid state transition or corrupted session.

    Raised when:
    - Invalid phase transition attempted
    - Session data is inconsistent
    - Required session fields are missing
    """

    pass


class PlanParseError(OrchestratorError):
    """
    Malformed plan file.

    Raised when:
    - Plan file cannot be read
    - Plan structure is invalid
    - Required milestone sections are missing
    """

    pass
