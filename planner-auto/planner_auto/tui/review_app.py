"""Review TUI — Textual-based dashboard for the review loop.

Milestone 4: Drill-down screens, round detail, log filtering,
keybinding system, and polish.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, Label, Static
from textual import work

from planner_auto.loop.engine import LoopResult, ReviewLoopEngine
from planner_auto.review_workflow import ReviewWorkflow
from planner_auto.tui.adapter import TUIAdapter
from planner_auto.tui.bindings import REVIEW_BINDINGS
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
from planner_auto.tui.screens.disposition_screen import DispositionScreen
from planner_auto.tui.screens.help_screen import HelpScreen
from planner_auto.tui.screens.plan_screen import PlanScreen
from planner_auto.tui.screens.raw_response_screen import RawResponseScreen
from planner_auto.tui.widgets.convergence_panel import ConvergencePanel
from planner_auto.tui.widgets.current_round import CurrentRound
from planner_auto.tui.widgets.log_panel import LogPanel
from planner_auto.tui.widgets.plan_panel import PlanPanel
from planner_auto.tui.widgets.round_detail import RoundDetail
from planner_auto.tui.widgets.round_list import RoundList
from planner_auto.tui.widgets.session_panel import SessionPanel

if TYPE_CHECKING:
    from planner_auto.review_workflow import PreparedReview

logger = logging.getLogger(__name__)


class ReviewTUI(App):
    """Textual app for the review loop dashboard.

    Args:
        prepared: ``PreparedReview`` from ``ReviewWorkflow.prepare()``.
        session_id: Session ID.
        db_path: Path to the SQLite database for read-only queries.
            The app opens its own connection — no connection is shared
            with the CLI thread.
    """

    CSS_PATH = "styles/theme.tcss"
    TITLE = "planner-auto review"

    BINDINGS = [Binding(*b) for b in REVIEW_BINDINGS]

    def __init__(
        self,
        prepared: PreparedReview,
        session_id: str,
        db_path: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._prepared = prepared
        self._session_id = session_id
        self._db_path = db_path

        # Quit-guard and handoff state.
        self._review_active: bool = False
        self._quit_requested: bool = False
        self.loop_result: Optional[LoopResult] = None
        self.loop_error: Optional[str] = None

        # Read-only DB connection (opened on mount).
        self._ro_conn: Optional[sqlite3.Connection] = None

        # Original plan size for growth tracking.
        self._original_plan_size: int = len(prepared.current_plan)

        # Tick timer handle.
        self._tick_timer = None

        # Track round data for internal use.
        self._round_data: dict[int, dict] = {}
        self._latest_round: int = 0
        self._loop_finished_count: int = 0

        # Round detail view state.
        self._detail_round: Optional[int] = None  # None = dashboard view

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="review-grid"):
            with Container(id="sidebar"):
                yield SessionPanel(id="session-panel")
                yield RoundList(id="round-list")
                yield ConvergencePanel(id="convergence-panel")
                yield PlanPanel(id="plan-panel")
            with Container(id="main-panel"):
                yield CurrentRound(id="current-round")
                yield Static("", id="result-summary")
        with Container(id="log-container"):
            yield LogPanel(id="log-panel")
        yield Footer()

    # ------------------------------------------------------------------
    # Mount — populate sidebar from DB, start timer, launch worker
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        """Open read-only DB connection, populate sidebar, and start review."""
        if self._db_path:
            try:
                self._ro_conn = sqlite3.connect(
                    f"file:{self._db_path}?mode=ro",
                    uri=True,
                )
                self._ro_conn.row_factory = sqlite3.Row
            except Exception:
                try:
                    self._ro_conn = sqlite3.connect(self._db_path)
                    self._ro_conn.row_factory = sqlite3.Row
                except Exception:
                    logger.warning("Could not open DB for sidebar queries")
                    self._ro_conn = None

        panel: SessionPanel = self.query_one("#session-panel", SessionPanel)

        # Populate from PreparedReview.
        panel.set_field("session_id", self._session_id[:8])
        panel.set_field("complexity", self._prepared.complexity)
        panel.set_field("max_rounds", str(self._prepared.max_rounds))
        panel.set_field("backend", self._prepared.engine_config.get("claude_backend", "direct"))

        # Populate from DB if available.
        if self._ro_conn:
            try:
                row = self._ro_conn.execute(
                    "SELECT * FROM sessions WHERE id = ?",
                    (self._session_id,),
                ).fetchone()
                if row:
                    panel.set_field("phase", row["phase"])
                    panel.set_field("status", row["status"])
                    panel.set_field("project", row["project"])
            except Exception:
                logger.warning("Could not read session from DB", exc_info=True)

        # Initialize plan panel with the starting plan.
        plan_panel: PlanPanel = self.query_one("#plan-panel", PlanPanel)
        plan_panel.update(
            draft_num=1,
            size=self._original_plan_size,
            original_size=self._original_plan_size,
            plan_text=self._prepared.current_plan,
        )

        # Log startup message.
        log_panel: LogPanel = self.query_one("#log-panel", LogPanel)
        log_panel.log_message("Dashboard loaded. Starting review loop...", level="info")

        # Start 1-second tick timer for elapsed time updates.
        self._tick_timer = self.set_interval(1.0, self._on_tick)

        # Launch the review loop in a worker thread.
        self.run_review_loop()

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    @work(thread=True)
    def run_review_loop(self) -> None:
        """Run the review loop in a worker thread.

        Opens its own DB connection. The engine's ``on_loop_finished``
        callback is the ONLY source of ``LoopFinished`` messages — this
        worker never posts ``LoopFinished``.
        """
        worker_conn: Optional[sqlite3.Connection] = None
        try:
            self._review_active = True

            # Open a fresh connection for engine use.
            if self._db_path:
                worker_conn = sqlite3.connect(self._db_path)
                worker_conn.row_factory = sqlite3.Row
                worker_conn.execute("PRAGMA foreign_keys=ON")
            else:
                # Fallback — shouldn't happen in normal use.
                worker_conn = sqlite3.connect(":memory:")
                worker_conn.row_factory = sqlite3.Row

            # Create adapter for thread-safe message dispatch.
            adapter = TUIAdapter(self)

            # Create engine with worker-owned connection.
            engine = ReviewLoopEngine(
                conn=worker_conn,
                session_id=self._session_id,
                reviewer=self._prepared.reviewer,
                planner_model=self._prepared.planner_model,
                config=self._prepared.engine_config,
                callbacks=adapter.as_dict(),
            )

            # Run the loop. LoopFinished is dispatched by the engine's
            # _emit_final() callback — we do NOT post it here.
            ReviewWorkflow.run(engine, self._prepared.current_plan, self._prepared.max_rounds)

            # Normal completion — _review_active is cleared by on_loop_finished handler.

        except Exception as exc:
            # Post error message (NOT LoopFinished).
            adapter_err = TUIAdapter(self)
            adapter_err.on_error(str(exc), round_num=self._latest_round or None)
            self._review_active = False
        finally:
            if worker_conn:
                try:
                    worker_conn.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Tick timer
    # ------------------------------------------------------------------

    def _on_tick(self) -> None:
        """Called every 1 second to update elapsed timers."""
        try:
            current_round: CurrentRound = self.query_one("#current-round", CurrentRound)
            current_round.tick()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def on_round_started(self, message: RoundStarted) -> None:
        """Handle RoundStarted — add round to list, update current-round."""
        self._latest_round = message.round_num
        self._round_data[message.round_num] = {"max_rounds": message.max_rounds}

        round_list: RoundList = self.query_one("#round-list", RoundList)
        round_list.add_round(message.round_num)

        current_round: CurrentRound = self.query_one("#current-round", CurrentRound)
        current_round.set_gpt_review(message.round_num)

        log_panel: LogPanel = self.query_one("#log-panel", LogPanel)
        log_panel.log_message(
            f"R{message.round_num}/{message.max_rounds}: GPT reviewing...",
            level="info",
        )

    def on_review_complete(self, message: ReviewComplete) -> None:
        """Handle ReviewComplete — update round list and convergence."""
        rdata = self._round_data.setdefault(message.round_num, {})
        rdata.update({
            "verdict": message.verdict,
            "issue_count": message.issue_count,
            "cost": message.cost,
            "latency_ms": message.latency_ms,
            "input_tokens": message.input_tokens,
            "output_tokens": message.output_tokens,
            "keep_count": message.keep_count,
            "trim_count": message.trim_count,
            "issues": message.issues,
        })

        # Update round list.
        round_list: RoundList = self.query_one("#round-list", RoundList)
        round_list.update_round(
            message.round_num,
            verdict=message.verdict,
            issue_count=message.issue_count,
            cost=message.cost,
        )

        # Update convergence panel.
        total_tokens = (message.input_tokens or 0) + (message.output_tokens or 0)
        conv: ConvergencePanel = self.query_one("#convergence-panel", ConvergencePanel)
        conv.update(
            message.round_num,
            message.issue_count,
            message.cost or 0.0,
            total_tokens,
        )

        # Log.
        log_panel: LogPanel = self.query_one("#log-panel", LogPanel)
        cost_str = f"${message.cost:.4f}" if message.cost else "$?"
        level = "success" if message.verdict == "GO" else "info"
        log_panel.log_message(
            f"R{message.round_num}: {message.verdict} — {message.issue_count} issues, "
            f"{message.latency_ms}ms, {cost_str}",
            level=level,
        )

        # If GO, clear current-round (no revision follows).
        if message.verdict == "GO":
            current_round: CurrentRound = self.query_one("#current-round", CurrentRound)
            current_round.clear()

    def on_feedback_validated(self, message: FeedbackValidated) -> None:
        """Handle FeedbackValidated — show disposition summary."""
        accepted = deferred = rejected = 0
        if message.dispositions:
            for d in message.dispositions:
                disp = d.get("disposition", "")
                if disp == "ACCEPT":
                    accepted += 1
                elif "DEFER" in disp:
                    deferred += 1
                elif "REJECT" in disp:
                    rejected += 1

        current_round: CurrentRound = self.query_one("#current-round", CurrentRound)
        current_round.set_feedback(accepted, deferred, rejected)

        if message.dispositions:
            log_panel: LogPanel = self.query_one("#log-panel", LogPanel)
            log_panel.log_message(
                f"R{message.round_num}: Dispositions — "
                f"{accepted}A/{deferred}D/{rejected}R",
                level="info",
            )

    def on_revision_started(self, message: RevisionStarted) -> None:
        """Handle RevisionStarted — switch to Claude revising phase."""
        current_round: CurrentRound = self.query_one("#current-round", CurrentRound)
        current_round.set_revision(message.round_num)

        log_panel: LogPanel = self.query_one("#log-panel", LogPanel)
        log_panel.log_message(
            f"R{message.round_num}: Claude revising... "
            f"({message.accepted_count}A/{message.deferred_count}D/{message.rejected_count}R)",
            level="info",
        )

    def on_revision_complete(self, message: RevisionComplete) -> None:
        """Handle RevisionComplete — update plan panel, clear current-round."""
        # Store revision data for round detail view.
        rdata = self._round_data.setdefault(message.round_num, {})
        rdata.update({
            "revision_latency_ms": message.latency_ms,
            "prev_size": message.prev_size,
            "new_size": message.new_size,
            "history_context_size": message.history_context_size,
        })

        current_round: CurrentRound = self.query_one("#current-round", CurrentRound)
        current_round.record_revision_latency(message.latency_ms)
        current_round.clear()

        # Update plan panel.
        plan_panel: PlanPanel = self.query_one("#plan-panel", PlanPanel)
        # We don't have the plan text here — just update size metrics.
        # draft_num is approximate: round_num + 1 (original is #1).
        plan_panel.update(
            draft_num=message.round_num + 1,
            size=message.new_size,
            original_size=self._original_plan_size,
            plan_text="",  # text not available from callback — milestones show 0
        )

        delta = message.new_size - message.prev_size
        sign = "+" if delta >= 0 else ""

        log_panel: LogPanel = self.query_one("#log-panel", LogPanel)
        log_panel.log_message(
            f"R{message.round_num}: Revision done — "
            f"{message.prev_size}→{message.new_size} chars ({sign}{delta}), "
            f"{message.latency_ms}ms",
            level="info",
        )

    def on_loop_finished(self, message: LoopFinished) -> None:
        """Handle LoopFinished — save result, update UI, handle deferred quit.

        This is the SINGLE source of LoopFinished. The worker thread
        never posts LoopFinished — only the engine callback does.
        """
        self._loop_finished_count += 1

        # Construct LoopResult for CLI handoff.
        # We don't have final_plan text or draft_number from the message,
        # but the CLI's finalize() reads them from DB, so we provide
        # the fields we have and set defaults for the rest.
        self.loop_result = LoopResult(
            converged=message.converged,
            rounds=message.rounds,
            final_plan="",  # CLI reads from DB
            final_draft_number=0,  # CLI reads from DB
            total_cost=message.total_cost,
            stop_reason=message.stop_reason,
            final_round_number=self._latest_round,
        )

        self._review_active = False

        # Stop tick timer.
        if self._tick_timer:
            self._tick_timer.stop()

        # Update session panel.
        panel: SessionPanel = self.query_one("#session-panel", SessionPanel)
        current_round: CurrentRound = self.query_one("#current-round", CurrentRound)
        current_round.clear()

        log_panel: LogPanel = self.query_one("#log-panel", LogPanel)
        result_widget: Static = self.query_one("#result-summary", Static)

        if message.converged:
            panel.update_phase("COMPLETE")
            panel.update_status("COMPLETE")

            summary = (
                f"[green]Converged[/green] in {message.rounds} rounds. "
                f"${message.total_cost:.4f} total."
            )
            result_widget.update(summary)
            log_panel.log_message(
                f"Converged ({message.stop_reason}) in {message.rounds} rounds. "
                f"${message.total_cost:.4f} total.",
                level="success",
            )
        else:
            panel.update_status("PAUSED")

            # Show blocker info with CLI commands.
            blocker_lines = [
                f"[yellow]Review cap reached[/yellow] after {message.rounds} rounds.",
                f"Stop reason: {message.stop_reason}",
                f"Cost: ${message.total_cost:.4f}",
                "",
                "Critical issues remain. Next steps:",
                f"  planner-auto resume {self._session_id}",
                f"  planner-auto review {self._session_id} --max-rounds N",
                f"  planner-auto complete {self._session_id}",
            ]
            result_widget.update("\n".join(blocker_lines))
            log_panel.log_message(
                f"Cap reached ({message.stop_reason}) after {message.rounds} rounds. "
                f"${message.total_cost:.4f} total.",
                level="warning",
            )

        log_panel.log_message("Press q to exit.", level="info")

        # Handle deferred quit.
        if self._quit_requested:
            self._cleanup()
            self.exit()

    def on_loop_error(self, message: LoopError) -> None:
        """Handle LoopError — save error, update UI, handle deferred quit."""
        self.loop_error = message.error_message
        self._review_active = False

        # Stop tick timer.
        if self._tick_timer:
            self._tick_timer.stop()

        current_round: CurrentRound = self.query_one("#current-round", CurrentRound)
        current_round.clear()

        result_widget: Static = self.query_one("#result-summary", Static)
        round_info = f" (round {message.round_num})" if message.round_num else ""
        result_widget.update(f"[red]Error{round_info}:[/red] {message.error_message}")

        log_panel: LogPanel = self.query_one("#log-panel", LogPanel)
        log_panel.log_message(
            f"Error{round_info}: {message.error_message}",
            level="error",
        )
        log_panel.log_message("Press q to exit.", level="info")

        panel: SessionPanel = self.query_one("#session-panel", SessionPanel)
        panel.update_status("ERROR")

        if self._quit_requested:
            self._cleanup()
            self.exit()

    def on_revision_timeout(self, message: RevisionTimeout) -> None:
        """Handle RevisionTimeout — show retry status."""
        current_round: CurrentRound = self.query_one("#current-round", CurrentRound)
        current_round.set_retry(message.round_num, message.timeout_sec, message.retry_count)

        log_panel: LogPanel = self.query_one("#log-panel", LogPanel)
        log_panel.log_message(
            f"R{message.round_num}: Timeout after {message.timeout_sec}s — "
            f"retry #{message.retry_count}",
            level="warning",
        )

    # ------------------------------------------------------------------
    # Responsive layout
    # ------------------------------------------------------------------

    def on_resize(self) -> None:
        """Switch CSS classes for responsive layout."""
        width = self.size.width
        self.remove_class("layout-stacked", "layout-wide")
        if width < 80:
            self.add_class("layout-stacked")
        elif width >= 120:
            self.add_class("layout-wide")

    # ------------------------------------------------------------------
    # Quit action
    # ------------------------------------------------------------------

    def action_quit(self) -> None:
        """Quit the app with graceful shutdown during active review."""
        if not self._review_active:
            self._cleanup()
            self.exit()
        else:
            # Defer quit until the current round finishes.
            self._quit_requested = True
            log_panel: LogPanel = self.query_one("#log-panel", LogPanel)
            log_panel.log_message(
                "Waiting for current round to finish before quitting...",
                level="warning",
            )

    # ------------------------------------------------------------------
    # Keybinding actions
    # ------------------------------------------------------------------

    def action_dispositions(self) -> None:
        """Push the disposition screen showing cross-round disposition table."""
        self.push_screen(
            DispositionScreen(
                conn=self._ro_conn,
                session_id=self._session_id,
                round_data=self._round_data,
            )
        )

    def action_plan(self) -> None:
        """Push the plan screen showing the latest plan draft."""
        self.push_screen(
            PlanScreen(
                conn=self._ro_conn,
                session_id=self._session_id,
                fallback_plan=self._prepared.current_plan,
            )
        )

    def action_log_filter(self) -> None:
        """Cycle the log panel filter: all → warn+ → error → all."""
        log_panel: LogPanel = self.query_one("#log-panel", LogPanel)
        new_level = log_panel.cycle_filter()
        log_panel.log_message(f"Log filter: {new_level}", level="info")

    def action_help(self) -> None:
        """Push the help screen listing all keybindings."""
        self.push_screen(HelpScreen())

    async def action_select_round(self) -> None:
        """Show round detail for the latest round (or toggle back)."""
        if self._detail_round is not None:
            # Already in detail view — go back.
            await self._exit_detail_view()
            return

        if not self._round_data:
            return

        # Show detail for the latest completed round.
        target = self._latest_round
        if target and target in self._round_data:
            await self._show_round_detail(target)

    async def action_back(self) -> None:
        """Return from detail view to dashboard. Escape pops modals first."""
        if self._detail_round is not None:
            await self._exit_detail_view()

    async def action_next_round(self) -> None:
        """Navigate to the next round in detail view."""
        if self._detail_round is None:
            return
        rounds = sorted(self._round_data.keys())
        idx = rounds.index(self._detail_round) if self._detail_round in rounds else -1
        if idx < len(rounds) - 1:
            await self._show_round_detail(rounds[idx + 1])

    def action_raw_response(self) -> None:
        """Push the raw response screen (only in round detail view)."""
        if self._detail_round is None:
            return
        self.push_screen(
            RawResponseScreen(
                conn=self._ro_conn,
                session_id=self._session_id,
                round_num=self._detail_round,
            )
        )

    # ------------------------------------------------------------------
    # Round detail view
    # ------------------------------------------------------------------

    async def _show_round_detail(self, round_num: int) -> None:
        """Replace main-panel content with RoundDetail for the given round."""
        self._detail_round = round_num
        main_panel = self.query_one("#main-panel", Container)

        # Remove existing main-panel children and await cleanup.
        for child in list(main_panel.children):
            await child.remove()

        # Mount round detail.
        rdata = self._round_data.get(round_num, {})
        detail = RoundDetail(round_num, rdata, id="round-detail")
        await main_panel.mount(detail)

    async def _exit_detail_view(self) -> None:
        """Restore the main-panel to dashboard view."""
        self._detail_round = None
        main_panel = self.query_one("#main-panel", Container)

        # Remove round detail.
        for child in list(main_panel.children):
            await child.remove()

        # Restore dashboard widgets.
        await main_panel.mount(CurrentRound(id="current-round"))
        await main_panel.mount(Static("", id="result-summary"))

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup(self) -> None:
        """Close the read-only DB connection and stop timer."""
        if self._tick_timer:
            try:
                self._tick_timer.stop()
            except Exception:
                pass
        if self._ro_conn:
            try:
                self._ro_conn.close()
            except Exception:
                pass
            self._ro_conn = None
