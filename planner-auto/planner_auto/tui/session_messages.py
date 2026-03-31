"""Textual message types for the session TUI.

Each message carries typed fields for the TUI widgets to consume.
"""

from __future__ import annotations

from textual.message import Message


class SessionStarted(Message):
    """Dispatched when the session TUI mounts successfully."""

    def __init__(self, session_id: str, project: str) -> None:
        super().__init__()
        self.session_id = session_id
        self.project = project


class ContextAdded(Message):
    """Dispatched after a context entry is successfully added."""

    def __init__(self, entry_type: str, key: str, size: int) -> None:
        super().__init__()
        self.entry_type = entry_type
        self.key = key
        self.size = size


class PhaseAdvanced(Message):
    """Dispatched when the session phase changes."""

    def __init__(self, from_phase: str, to_phase: str) -> None:
        super().__init__()
        self.from_phase = from_phase
        self.to_phase = to_phase


class SessionError(Message):
    """Dispatched when an error occurs during a session operation."""

    def __init__(self, error_message: str, phase: str) -> None:
        super().__init__()
        self.error_message = error_message
        self.phase = phase


class DiscussMessageSent(Message):
    """Dispatched when a user sends a discussion message."""

    def __init__(self, content: str, char_count: int) -> None:
        super().__init__()
        self.content = content
        self.char_count = char_count


class DiscussResponseReceived(Message):
    """Dispatched when Claude's discussion response arrives."""

    def __init__(self, content: str, latency_ms: int) -> None:
        super().__init__()
        self.content = content
        self.latency_ms = latency_ms


class DiscussThinking(Message):
    """Dispatched when Claude is thinking (processing a discussion message)."""
    pass


# --- Planning/Generation messages ---


class SynthesisStarted(Message):
    """Dispatched when context synthesis begins."""

    def __init__(self, file_count: int, note_count: int) -> None:
        super().__init__()
        self.file_count = file_count
        self.note_count = note_count


class SynthesisComplete(Message):
    """Dispatched when context synthesis finishes."""

    def __init__(self, output_size: int, latency_ms: int) -> None:
        super().__init__()
        self.output_size = output_size
        self.latency_ms = latency_ms


class PlanGenerationStarted(Message):
    """Dispatched when plan generation begins."""

    def __init__(self, model: str) -> None:
        super().__init__()
        self.model = model


class PlanGenerated(Message):
    """Dispatched when plan generation finishes."""

    def __init__(
        self,
        draft_number: int,
        size: int,
        milestone_count: int,
        latency_ms: int,
        validation_ok: bool,
        warnings: list[str],
    ) -> None:
        super().__init__()
        self.draft_number = draft_number
        self.size = size
        self.milestone_count = milestone_count
        self.latency_ms = latency_ms
        self.validation_ok = validation_ok
        self.warnings = warnings


# --- Review/Completion messages ---


class SessionCompleted(Message):
    """Dispatched when the session completes successfully after review."""

    def __init__(
        self,
        export_paths: list[str],
        kafra_path: str | None,
        total_cost: float,
    ) -> None:
        super().__init__()
        self.export_paths = export_paths
        self.kafra_path = kafra_path
        self.total_cost = total_cost


class BlockerCreated(Message):
    """Dispatched when review finishes with cap+criticals (blocker)."""

    def __init__(self, source: str, question: str, blocker_id: int) -> None:
        super().__init__()
        self.source = source
        self.question = question
        self.blocker_id = blocker_id


class BlockerResolved(Message):
    """Dispatched when a blocker is resolved and the session resumes."""

    def __init__(self, blocker_id: int, phase: str) -> None:
        super().__init__()
        self.blocker_id = blocker_id
        self.phase = phase
