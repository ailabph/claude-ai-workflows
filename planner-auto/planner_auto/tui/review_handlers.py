"""Review handler mixin — decoupled review message handling logic.

Extracted from ReviewTUI to enable reuse in SessionTUI's embedded review.
Each handler method takes the message + target widgets as parameters —
no query_one() calls, no coupling to a specific app's widget tree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from planner_auto.tui.messages import (
        FeedbackValidated,
        LoopFinished,
        ReviewComplete,
        RevisionComplete,
        RevisionStarted,
        RevisionTimeout,
        RoundStarted,
    )
    from planner_auto.tui.widgets.convergence_panel import ConvergencePanel
    from planner_auto.tui.widgets.current_round import CurrentRound
    from planner_auto.tui.widgets.log_panel import LogPanel
    from planner_auto.tui.widgets.plan_panel import PlanPanel
    from planner_auto.tui.widgets.round_list import RoundList
    from planner_auto.tui.widgets.session_panel import SessionPanel


class ReviewHandlerMixin:
    """Standalone review message handler logic, decoupled from widget tree.

    All methods take the message + target widgets as explicit parameters.
    The caller (ReviewTUI or SessionTUI) passes widgets via query_one().

    Also tracks round_data and latest_round internally.
    """

    def __init__(self) -> None:
        self.round_data: dict[int, dict] = {}
        self.latest_round: int = 0
        self.original_plan_size: int = 0

    def handle_round_started(
        self,
        msg: RoundStarted,
        round_list: RoundList,
        current_round: CurrentRound,
        log_panel: LogPanel,
    ) -> None:
        """Handle RoundStarted — add round to list, update current-round."""
        self.latest_round = msg.round_num
        self.round_data[msg.round_num] = {"max_rounds": msg.max_rounds}

        round_list.add_round(msg.round_num)
        current_round.set_gpt_review(msg.round_num)
        log_panel.log_message(
            f"R{msg.round_num}/{msg.max_rounds}: GPT reviewing...",
            level="info",
        )

    def handle_review_complete(
        self,
        msg: ReviewComplete,
        round_list: RoundList,
        convergence_panel: ConvergencePanel,
        current_round: CurrentRound,
        log_panel: LogPanel,
    ) -> None:
        """Handle ReviewComplete — update round list and convergence."""
        rdata = self.round_data.setdefault(msg.round_num, {})
        rdata.update({
            "verdict": msg.verdict,
            "issue_count": msg.issue_count,
            "cost": msg.cost,
            "latency_ms": msg.latency_ms,
            "input_tokens": msg.input_tokens,
            "output_tokens": msg.output_tokens,
            "keep_count": msg.keep_count,
            "trim_count": msg.trim_count,
            "issues": msg.issues,
        })

        round_list.update_round(
            msg.round_num,
            verdict=msg.verdict,
            issue_count=msg.issue_count,
            cost=msg.cost,
        )

        total_tokens = (msg.input_tokens or 0) + (msg.output_tokens or 0)
        convergence_panel.update(
            msg.round_num,
            msg.issue_count,
            msg.cost or 0.0,
            total_tokens,
        )

        cost_str = f"${msg.cost:.4f}" if msg.cost else "$?"
        level = "success" if msg.verdict == "GO" else "info"
        log_panel.log_message(
            f"R{msg.round_num}: {msg.verdict} \u2014 {msg.issue_count} issues, "
            f"{msg.latency_ms}ms, {cost_str}",
            level=level,
        )

        if msg.verdict == "GO":
            current_round.clear()

    def handle_feedback_validated(
        self,
        msg: FeedbackValidated,
        current_round: CurrentRound,
        log_panel: LogPanel,
    ) -> None:
        """Handle FeedbackValidated — show disposition summary."""
        accepted = deferred = rejected = 0
        if msg.dispositions:
            for d in msg.dispositions:
                disp = d.get("disposition", "")
                if disp == "ACCEPT":
                    accepted += 1
                elif "DEFER" in disp:
                    deferred += 1
                elif "REJECT" in disp:
                    rejected += 1

        current_round.set_feedback(accepted, deferred, rejected)

        if msg.dispositions:
            log_panel.log_message(
                f"R{msg.round_num}: Dispositions \u2014 "
                f"{accepted}A/{deferred}D/{rejected}R",
                level="info",
            )

    def handle_revision_started(
        self,
        msg: RevisionStarted,
        current_round: CurrentRound,
        log_panel: LogPanel,
    ) -> None:
        """Handle RevisionStarted — switch to Claude revising phase."""
        current_round.set_revision(msg.round_num)
        log_panel.log_message(
            f"R{msg.round_num}: Claude revising... "
            f"({msg.accepted_count}A/{msg.deferred_count}D/{msg.rejected_count}R)",
            level="info",
        )

    def handle_revision_complete(
        self,
        msg: RevisionComplete,
        plan_panel: PlanPanel,
        current_round: CurrentRound,
        log_panel: LogPanel,
    ) -> None:
        """Handle RevisionComplete — update plan panel, clear current-round."""
        rdata = self.round_data.setdefault(msg.round_num, {})
        rdata.update({
            "revision_latency_ms": msg.latency_ms,
            "prev_size": msg.prev_size,
            "new_size": msg.new_size,
            "history_context_size": msg.history_context_size,
        })

        current_round.record_revision_latency(msg.latency_ms)
        current_round.clear()

        plan_panel.update(
            draft_num=msg.round_num + 1,
            size=msg.new_size,
            original_size=self.original_plan_size,
            plan_text="",
        )

        delta = msg.new_size - msg.prev_size
        sign = "+" if delta >= 0 else ""
        log_panel.log_message(
            f"R{msg.round_num}: Revision done \u2014 "
            f"{msg.prev_size}\u2192{msg.new_size} chars ({sign}{delta}), "
            f"{msg.latency_ms}ms",
            level="info",
        )

    def handle_loop_finished(
        self,
        msg: LoopFinished,
        session_panel: SessionPanel,
        current_round: CurrentRound,
        log_panel: LogPanel,
    ) -> None:
        """Handle LoopFinished — update review widgets ONLY.

        Does NOT trigger phase transitions. Phase transitions are handled
        by SessionCompleted/BlockerCreated messages posted by the worker
        after finalize() returns.
        """
        current_round.clear()

        if msg.converged:
            log_panel.log_message(
                f"Converged ({msg.stop_reason}) in {msg.rounds} rounds. "
                f"${msg.total_cost:.4f} total.",
                level="success",
            )
        else:
            log_panel.log_message(
                f"Cap reached ({msg.stop_reason}) after {msg.rounds} rounds. "
                f"${msg.total_cost:.4f} total.",
                level="warning",
            )

    def handle_revision_timeout(
        self,
        msg: RevisionTimeout,
        current_round: CurrentRound,
        log_panel: LogPanel,
    ) -> None:
        """Handle RevisionTimeout — show retry status."""
        current_round.set_retry(msg.round_num, msg.timeout_sec, msg.retry_count)
        log_panel.log_message(
            f"R{msg.round_num}: Timeout after {msg.timeout_sec}s \u2014 "
            f"retry #{msg.retry_count}",
            level="warning",
        )
