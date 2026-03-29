"""Textual message types for the review TUI.

Each message maps to an engine callback and carries typed fields for
the TUI widgets to consume.
"""

from __future__ import annotations

from typing import Optional

from textual.message import Message


class RoundStarted(Message):
    """Dispatched before a GPT review call begins."""

    def __init__(self, round_num: int, max_rounds: int) -> None:
        super().__init__()
        self.round_num = round_num
        self.max_rounds = max_rounds


class ReviewComplete(Message):
    """Dispatched after the GPT reviewer returns."""

    def __init__(
        self,
        round_num: int,
        verdict: str,
        issue_count: int,
        latency_ms: int,
        input_tokens: Optional[int],
        output_tokens: Optional[int],
        cost: Optional[float],
        keep_count: int,
        trim_count: int,
        issues: list,
    ) -> None:
        super().__init__()
        self.round_num = round_num
        self.verdict = verdict
        self.issue_count = issue_count
        self.latency_ms = latency_ms
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost = cost
        self.keep_count = keep_count
        self.trim_count = trim_count
        self.issues = issues


class FeedbackValidated(Message):
    """Dispatched after feedback validation with disposition details."""

    def __init__(self, round_num: int, dispositions: Optional[list]) -> None:
        super().__init__()
        self.round_num = round_num
        self.dispositions = dispositions


class RevisionStarted(Message):
    """Dispatched before the Claude revision call.

    Triggers the "Claude revising..." phase in CurrentRound widget.
    """

    def __init__(
        self,
        round_num: int,
        accepted_count: int,
        deferred_count: int,
        rejected_count: int,
    ) -> None:
        super().__init__()
        self.round_num = round_num
        self.accepted_count = accepted_count
        self.deferred_count = deferred_count
        self.rejected_count = rejected_count


class RevisionComplete(Message):
    """Dispatched after the Claude revision finishes."""

    def __init__(
        self,
        round_num: int,
        prev_size: int,
        new_size: int,
        latency_ms: int,
        history_context_size: int,
    ) -> None:
        super().__init__()
        self.round_num = round_num
        self.prev_size = prev_size
        self.new_size = new_size
        self.latency_ms = latency_ms
        self.history_context_size = history_context_size


class LoopFinished(Message):
    """Dispatched when the review loop ends (from engine callback only)."""

    def __init__(
        self,
        converged: bool,
        stop_reason: str,
        rounds: int,
        total_cost: float,
        final_plan_path: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.converged = converged
        self.stop_reason = stop_reason
        self.rounds = rounds
        self.total_cost = total_cost
        self.final_plan_path = final_plan_path


class RevisionTimeout(Message):
    """Dispatched when a revision call times out and will be retried."""

    def __init__(self, round_num: int, timeout_sec: int, retry_count: int) -> None:
        super().__init__()
        self.round_num = round_num
        self.timeout_sec = timeout_sec
        self.retry_count = retry_count


class LoopError(Message):
    """Dispatched when the worker thread catches an unhandled exception."""

    def __init__(self, error_message: str, round_num: Optional[int] = None) -> None:
        super().__init__()
        self.error_message = error_message
        self.round_num = round_num
