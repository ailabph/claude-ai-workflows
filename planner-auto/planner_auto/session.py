"""
SessionManager: enforces phase transitions and command permissions.
"""

import sqlite3

from planner_auto.db import (
    create_blocker,
    get_open_blockers,
    get_session,
    resolve_blocker,
    transaction,
    update_session_phase,
    update_session_status,
)
from planner_auto.errors import (
    CommandNotAllowedError,
    InvalidTransitionError,
    SessionNotFoundError,
)
from planner_auto.state import (
    PAUSED_ALLOWED_COMMANDS,
    PHASE_ALLOWED_COMMANDS,
    VALID_PHASE_TRANSITIONS,
    Phase,
    Status,
)


class SessionManager:
    """Manages session lifecycle, phase transitions, and command permissions.

    Args:
        conn: An open SQLite connection with schema initialized.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _get_session_or_raise(self, session_id: str) -> sqlite3.Row:
        """Fetch session row or raise SessionNotFoundError."""
        session = get_session(self.conn, session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session

    def advance_phase(self, session_id: str, target_phase: str) -> None:
        """Advance a session to the target phase.

        Validates the transition against VALID_PHASE_TRANSITIONS.

        Args:
            session_id: Session ID.
            target_phase: The phase to transition to.

        Raises:
            SessionNotFoundError: If session doesn't exist.
            InvalidTransitionError: If the transition is not allowed.
        """
        session = self._get_session_or_raise(session_id)
        current_phase = session["phase"]

        try:
            current = Phase(current_phase)
            target = Phase(target_phase)
        except ValueError:
            raise InvalidTransitionError(current_phase, target_phase)

        allowed_targets = VALID_PHASE_TRANSITIONS.get(current, set())
        if target not in allowed_targets:
            raise InvalidTransitionError(current_phase, target_phase)

        update_session_phase(self.conn, session_id, target_phase)
        self.conn.commit()

    def check_command(self, session_id: str, command_name: str) -> None:
        """Check if a command is allowed in the session's current phase/status.

        Rules:
        1. 'export' is allowed in any phase/status.
        2. PAUSED status only allows 'resume', 'status', 'export'.
        3. 'complete' requires zero open blockers.
        4. Otherwise, check PHASE_ALLOWED_COMMANDS for the current phase.

        Args:
            session_id: Session ID.
            command_name: The command to check.

        Raises:
            SessionNotFoundError: If session doesn't exist.
            CommandNotAllowedError: If the command is not allowed.
        """
        session = self._get_session_or_raise(session_id)
        phase = session["phase"]
        status = session["status"]

        # Rule 1: export always allowed
        if command_name == "export":
            return

        # Rule 2: PAUSED status restrictions
        if status == Status.PAUSED.value:
            if command_name not in PAUSED_ALLOWED_COMMANDS:
                raise CommandNotAllowedError(
                    command_name, phase, status,
                    reason="Session is PAUSED. Only 'resume', 'status', and 'export' are allowed.",
                )
            return

        # Rule 3: complete requires zero open blockers
        if command_name == "complete":
            blockers = get_open_blockers(self.conn, session_id)
            if blockers:
                questions = [b["question"] for b in blockers]
                raise CommandNotAllowedError(
                    command_name, phase, status,
                    reason=f"Cannot complete with {len(blockers)} open blocker(s): {questions}",
                )
            return

        # Rule 4: check phase-based permissions
        try:
            current_phase = Phase(phase)
        except ValueError:
            raise CommandNotAllowedError(
                command_name, phase, status,
                reason=f"Unknown phase: {phase}",
            )

        allowed = PHASE_ALLOWED_COMMANDS.get(current_phase, set())
        if command_name not in allowed:
            raise CommandNotAllowedError(
                command_name, phase, status,
                reason=f"Command '{command_name}' is not allowed in the {phase} phase.",
            )

    def pause_with_blocker(self, session_id: str, source: str, question: str) -> int:
        """Pause a session and insert a blocker in one transaction.

        Sets status=PAUSED and creates an open blocker.

        Args:
            session_id: Session ID.
            source: Source of the blocker (e.g. 'planner', 'user').
            question: The blocking question.

        Returns:
            The blocker row ID.

        Raises:
            SessionNotFoundError: If session doesn't exist.
        """
        self._get_session_or_raise(session_id)
        with transaction(self.conn):
            update_session_status(self.conn, session_id, Status.PAUSED.value)
            blocker_id = create_blocker(self.conn, session_id, source, question)
        return blocker_id

    def resolve_and_resume(self, session_id: str, blocker_id: int, answer: str) -> None:
        """Resolve a blocker and resume the session if no open blockers remain.

        Resolves the specified blocker. If no open blockers remain after
        resolution, sets the session status back to ACTIVE.

        Args:
            session_id: Session ID.
            blocker_id: The blocker row ID to resolve.
            answer: The answer resolving the blocker.

        Raises:
            SessionNotFoundError: If session doesn't exist.
        """
        self._get_session_or_raise(session_id)
        with transaction(self.conn):
            resolve_blocker(self.conn, blocker_id, answer)
            remaining = get_open_blockers(self.conn, session_id)
            if not remaining:
                update_session_status(self.conn, session_id, Status.ACTIVE.value)
