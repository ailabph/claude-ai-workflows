"""TUI adapter: bridges engine callbacks to Textual messages.

Each callback method translates engine arguments into a typed Textual
``Message`` and posts it to the app's main thread via ``call_from_thread``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from planner_auto.tui.messages import (
    FeedbackValidated,
    LoopError,
    LoopFinished,
    ReviewComplete,
    RevisionComplete,
    RevisionStarted,
    RevisionTimeout,
    RoundStarted,
)

if TYPE_CHECKING:
    from textual.app import App


class TUIAdapter:
    """Translates engine callbacks into thread-safe Textual messages.

    Args:
        app: The Textual ``App`` instance to post messages to.
    """

    def __init__(self, app: App) -> None:
        self.app = app

    # -- Callbacks matching engine dispatch keys --

    def on_round_start(self, round_num: int, max_rounds: int) -> None:
        self.app.call_from_thread(
            self.app.post_message,
            RoundStarted(round_num, max_rounds),
        )

    def on_review_complete(self, metrics: dict) -> None:
        self.app.call_from_thread(
            self.app.post_message,
            ReviewComplete(
                round_num=metrics["round_num"],
                verdict=metrics["verdict"],
                issue_count=metrics["issue_count"],
                latency_ms=metrics["latency_ms"],
                input_tokens=metrics.get("input_tokens"),
                output_tokens=metrics.get("output_tokens"),
                cost=metrics.get("cost"),
                keep_count=metrics.get("keep_count", 0),
                trim_count=metrics.get("trim_count", 0),
                issues=metrics.get("issues", []),
            ),
        )

    def on_feedback_validated(self, round_num: int, dispositions: list | None) -> None:
        self.app.call_from_thread(
            self.app.post_message,
            FeedbackValidated(round_num, dispositions),
        )

    def on_revision_start(
        self,
        round_num: int,
        accepted_count: int,
        deferred_count: int,
        rejected_count: int,
    ) -> None:
        self.app.call_from_thread(
            self.app.post_message,
            RevisionStarted(round_num, accepted_count, deferred_count, rejected_count),
        )

    def on_revision_complete(
        self,
        round_num: int,
        prev_size: int,
        new_size: int,
        latency_ms: int,
        history_context_size: int,
    ) -> None:
        self.app.call_from_thread(
            self.app.post_message,
            RevisionComplete(round_num, prev_size, new_size, latency_ms, history_context_size),
        )

    def on_loop_finished(self, result_dict: dict) -> None:
        self.app.call_from_thread(
            self.app.post_message,
            LoopFinished(
                converged=result_dict.get("converged", False),
                stop_reason=result_dict.get("stop_reason", "unknown"),
                rounds=result_dict.get("total_rounds", 0),
                total_cost=result_dict.get("total_cost", 0.0),
                final_plan_path=result_dict.get("final_plan_path"),
            ),
        )

    def on_revision_timeout(self, round_num: int, timeout_sec: int, retry_count: int) -> None:
        self.app.call_from_thread(
            self.app.post_message,
            RevisionTimeout(round_num, timeout_sec, retry_count),
        )

    def on_error(self, error_message: str, round_num: int | None = None) -> None:
        self.app.call_from_thread(
            self.app.post_message,
            LoopError(error_message, round_num),
        )

    def as_dict(self) -> dict:
        """Return a callbacks dict suitable for ``ReviewLoopEngine(callbacks=...)``.

        Keys match the engine's ``_dispatch()`` key names.
        """
        return {
            "on_round_start": self.on_round_start,
            "on_review_complete": self.on_review_complete,
            "on_feedback_validated": self.on_feedback_validated,
            "on_revision_start": self.on_revision_start,
            "on_revision_complete": self.on_revision_complete,
            "on_loop_finished": self.on_loop_finished,
            "on_revision_timeout": self.on_revision_timeout,
        }
