"""Session TUI — full-lifecycle Textual app for planner-auto sessions.

Phase-driven layout: sidebar stays constant, main panel switches per phase.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Footer, Header, Input, Label, Static
from textual import work

from planner_auto.context_service import ContextError, add_context_entry
from planner_auto.db import (
    get_context_entries,
    get_latest_plan_draft,
    get_messages,
    get_open_blockers,
    get_session,
    get_session_config,
    init_schema,
    open_db,
)
from planner_auto.loop.engine import LoopResult, ReviewLoopEngine
from planner_auto.review_workflow import FinalizeResult, PreparedReview, ReviewOpts, ReviewWorkflow
from planner_auto.sdk_wrapper import resolve_default_backend
from planner_auto.session import SessionManager
from planner_auto.state import Phase
from planner_auto.tui.adapter import TUIAdapter
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
from planner_auto.tui.review_handlers import ReviewHandlerMixin
from planner_auto.tui.session_bindings import SESSION_BINDINGS
from planner_auto.tui.session_messages import (
    BlockerCreated,
    BlockerResolved,
    ContextAdded,
    DiscussResponseReceived,
    PlanGenerated,
    PlanGenerationStarted,
    PhaseAdvanced,
    SessionCompleted,
    SessionError,
    SessionStarted,
    SynthesisComplete,
    SynthesisStarted,
)
from planner_auto.tui.widgets.compact_phase_bar import CompactPhaseBar
from planner_auto.tui.widgets.context_list import ContextList
from planner_auto.tui.widgets.convergence_panel import ConvergencePanel
from planner_auto.tui.widgets.current_round import CurrentRound
from planner_auto.tui.widgets.log_panel import LogPanel
from planner_auto.tui.widgets.phase_list import PhaseList
from planner_auto.tui.widgets.plan_panel import PlanPanel
from planner_auto.tui.widgets.round_list import RoundList
from planner_auto.tui.widgets.session_panel import SessionPanel

logger = logging.getLogger(__name__)


def _resolve_backend_from_config(conn: sqlite3.Connection, session_id: str) -> str:
    """Read claude_backend from session config, falling back to auto-detect."""
    cfg_row = get_session_config(conn, session_id)
    if cfg_row:
        try:
            cfg = json.loads(cfg_row["config_json"])
            backend = cfg.get("claude_backend")
            if backend in ("direct", "sdk"):
                return backend
        except (json.JSONDecodeError, TypeError):
            pass
    return resolve_default_backend()


class SessionTUI(App):
    """Textual app for the full session lifecycle.

    Args:
        session_id: Session ID.
        db_path: Path to the SQLite database.
    """

    CSS_PATH = "styles/theme.tcss"
    TITLE = "planner-auto session"

    # Default bindings — overridden dynamically per phase
    BINDINGS = [Binding(*b) for b in SESSION_BINDINGS["SETUP"]]

    def __init__(
        self,
        session_id: str,
        db_path: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._session_id = session_id
        self._db_path = db_path
        self._rw_conn: Optional[sqlite3.Connection] = None
        self._current_phase: str = Phase.SETUP.value
        self.exit_code: int = 0

        # Discussion state
        self._discuss_active: bool = False
        self._quit_requested: bool = False
        self._thinking_timer = None

        # Planning state
        self._plan_content: str = ""
        self._plan_model: str = ""
        self._generation_active: bool = False
        self._generation_timer = None

        # Review state
        self._review_active: bool = False
        self._review_handlers = ReviewHandlerMixin()
        self._prepared_review: Optional[PreparedReview] = None
        self._tick_timer = None

        # Blocker state
        self._blocker_id: Optional[int] = None
        self._blocker_source: str = ""
        self._blocker_question: str = ""
        self._resolve_active: bool = False

    def _update_bindings(self, phase: str) -> None:
        """Update keybindings for the current phase."""
        bindings_list = SESSION_BINDINGS.get(phase, SESSION_BINDINGS["SETUP"])
        # Rebuild BINDINGS list — Textual reads from _bindings
        try:
            self._bindings.key_to_bindings.clear()
            for key, action, desc in bindings_list:
                self.bind(key, action, description=desc)
        except (AttributeError, TypeError):
            # Fallback: some Textual versions have different internal APIs
            pass

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="session-grid"):
            with Container(id="sidebar"):
                yield SessionPanel(id="session-panel")
                yield PhaseList(id="phase-list")
                yield ContextList(id="context-list")
            with Container(id="main-panel"):
                yield Static("Loading...", id="main-content")
        yield CompactPhaseBar(id="compact-phase-bar")
        with Container(id="log-container"):
            yield LogPanel(id="log-panel")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app with session data from DB."""
        # Open read-write connection
        if self._db_path:
            self._rw_conn = open_db(self._db_path)
        else:
            self._rw_conn = open_db()
        init_schema(self._rw_conn)

        # Load session
        session = get_session(self._rw_conn, self._session_id)
        if session is None:
            self._log("error", f"Session not found: {self._session_id}")
            self.exit_code = 1
            self.exit()
            return

        # Populate session panel
        sp = self.query_one("#session-panel", SessionPanel)
        sp.set_field("session_id", session["id"][:12])
        sp.set_field("project", session["project"])
        sp.set_field("phase", session["phase"])
        sp.set_field("status", session["status"])

        # Set current phase — check status for PAUSED sessions
        session_status = session["status"]
        self._current_phase = session["phase"]

        # Populate phase list
        pl = self.query_one("#phase-list", PhaseList)

        # Load existing context entries
        entries = get_context_entries(self._rw_conn, self._session_id)
        cl = self.query_one("#context-list", ContextList)
        for entry in entries:
            cl.add_entry(entry["entry_type"], entry["entry_key"], len(entry["content"]))

        # Update phase list count
        if entries:
            pl.set_count("CONTEXT", str(len(entries)))

        # Load messages count for phase list
        messages = get_messages(self._rw_conn, self._session_id)
        if messages:
            pl.set_count("DISCUSSION", str(len(messages)))

        # Handle resume based on BOTH phase and status
        if session_status == "PAUSED":
            # Paused session — show blocker UI, not normal phase UI
            pl.set_paused(self._current_phase)
            self._update_bindings("PAUSED")
            # Load blocker info from DB
            from planner_auto.db import get_open_blockers
            blockers = get_open_blockers(self._rw_conn, self._session_id)
            if blockers:
                b = blockers[0]
                self._blocker_id = b["id"]
                self._blocker_source = b.get("source", "unknown")
                self._blocker_question = b.get("question", "")
                self._mount_paused_panel()
            else:
                # No open blockers but status is PAUSED — show info
                pl.set_active(self._current_phase)
                self._update_bindings(self._current_phase)
                self._switch_main_panel(self._current_phase)
        elif session_status == "COMPLETE" or self._current_phase == Phase.COMPLETE.value:
            # Completed session — populate result summary from DB
            pl.set_active(self._current_phase)
            self._update_bindings(self._current_phase)
            self._mount_complete_panel_from_db()
        elif self._current_phase == Phase.REVIEW.value:
            # Resuming into REVIEW — show plan + option to start review
            pl.set_active(self._current_phase)
            self._update_bindings(self._current_phase)
            self._mount_review_resume_panel()
        else:
            # Normal active session — show phase-appropriate content
            pl.set_active(self._current_phase)
            self._update_bindings(self._current_phase)
            self._switch_main_panel(self._current_phase)

        # Responsive layout
        self._apply_responsive_layout()

        # Compact bar hidden by default (shown in stacked layout)
        cpb = self.query_one("#compact-phase-bar", CompactPhaseBar)
        cpb.display = False

        self._log("info", f"Session {self._session_id[:12]} loaded (phase: {self._current_phase})")
        self.post_message(SessionStarted(self._session_id, session["project"]))

    def on_resize(self) -> None:
        """Toggle CSS classes for responsive layout."""
        self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        """Apply responsive layout based on terminal width."""
        width = self.size.width
        sidebar = self.query_one("#sidebar", Container)
        cpb = self.query_one("#compact-phase-bar", CompactPhaseBar)

        if width < 80:
            self.add_class("layout-stacked")
            self.remove_class("layout-wide")
            sidebar.display = False
            cpb.display = True
            cpb.set_active_phase(self._current_phase)
        elif width >= 120:
            self.remove_class("layout-stacked")
            self.add_class("layout-wide")
            sidebar.display = True
            cpb.display = False
        else:
            self.remove_class("layout-stacked")
            self.remove_class("layout-wide")
            sidebar.display = True
            cpb.display = False

    def _switch_main_panel(self, phase: str) -> None:
        """Switch the main panel content based on the current phase."""
        main = self.query_one("#main-panel", Container)

        # Remove old content (all known IDs)
        _known_ids = (
            "#main-content", "#phase-fallback", "#chat-view",
            "#generation-progress", "#plan-view", "#result-summary",
            "#review-round-list", "#review-convergence", "#review-current-round",
            "#review-plan-panel", "#blocker-display",
        )
        for sel in _known_ids:
            old = main.query(sel)
            for widget in old:
                widget.remove()

        # Stop thinking timer if switching away from discussion
        if self._thinking_timer is not None:
            self._thinking_timer.stop()
            self._thinking_timer = None

        # Stop generation timer if switching away from planning
        if self._generation_timer is not None:
            self._generation_timer.stop()
            self._generation_timer = None

        # Context phase shows contextual info
        if phase in (Phase.SETUP.value, Phase.CONTEXT.value):
            main.mount(Static(
                f"[bold $primary]Context Manager[/bold $primary]\n\n"
                f"  [f] Add file    [n] Add note    [d] Done\n\n"
                f"  Add files and notes to provide context for plan generation.",
                id="main-content",
            ))
        elif phase == Phase.DISCUSSION.value:
            # Mount ChatView for discussion phase
            from planner_auto.tui.widgets.chat_view import ChatView
            chat = ChatView(id="chat-view")
            main.mount(chat)
            # Load existing messages from DB
            if self._rw_conn:
                messages = get_messages(self._rw_conn, self._session_id)
                msg_list = [{"role": m["role"], "content": m["content"]} for m in messages]
                if msg_list:
                    self.call_later(lambda: chat.load_messages(msg_list))
        elif phase == Phase.PLANNING.value:
            self._mount_planning_panel()
        elif phase == Phase.REVIEW.value:
            self._mount_review_panel()
        elif phase == Phase.COMPLETE.value:
            self._mount_complete_panel()
        else:
            # Unknown phase — show info
            main.mount(Static(
                f"[bold $accent]Phase: {phase}[/bold $accent]",
                id="main-content",
            ))

    # ------------------------------------------------------------------
    # Planning panel mounting
    # ------------------------------------------------------------------

    def _mount_planning_panel(self) -> None:
        """Mount planning phase widgets into the main panel."""
        main = self.query_one("#main-panel", Container)

        # Check if we already have a plan draft
        if self._rw_conn:
            draft = get_latest_plan_draft(self._rw_conn, self._session_id)
            if draft:
                # Show existing plan
                from planner_auto.validation import validate_plan_format
                warnings = validate_plan_format(draft["content"])
                self._plan_content = draft["content"]
                self._plan_model = draft.get("model", "unknown")

                from planner_auto.tui.widgets.plan_view import PlanView
                pv = PlanView(id="plan-view")
                main.mount(pv)
                self.call_later(lambda: pv.set_plan(
                    draft_number=draft["draft_number"],
                    content=draft["content"],
                    model=draft.get("model", "unknown"),
                    validation_ok=len(warnings) == 0,
                    warnings=warnings if warnings else None,
                ))
                self._log("info", f"Plan loaded: Draft #{draft['draft_number']}, {len(draft['content']):,} chars")
                return

        # No plan yet — mount generation progress and auto-generate
        from planner_auto.tui.widgets.generation_progress import GenerationProgress
        gp = GenerationProgress(id="generation-progress")
        main.mount(gp)
        self._run_generate()

    def _mount_review_panel(self) -> None:
        """Mount review phase widgets into the main panel."""
        main = self.query_one("#main-panel", Container)
        main.mount(RoundList(id="review-round-list"))
        main.mount(ConvergencePanel(id="review-convergence"))
        main.mount(CurrentRound(id="review-current-round"))

        # Reset review handler mixin state
        self._review_handlers = ReviewHandlerMixin()
        if self._plan_content:
            self._review_handlers.original_plan_size = len(self._plan_content)

    def _mount_complete_panel(self) -> None:
        """Mount completion phase widgets (live — waits for SessionCompleted message)."""
        main = self.query_one("#main-panel", Container)
        from planner_auto.tui.widgets.result_summary import ResultSummary
        rs = ResultSummary(id="result-summary")
        main.mount(rs)

    def _mount_complete_panel_from_db(self) -> None:
        """Mount and populate completion panel from DB (resume scenario)."""
        main = self.query_one("#main-panel", Container)
        # Remove existing content
        for child in list(main.query("*")):
            child.remove()

        from planner_auto.tui.widgets.result_summary import ResultSummary
        rs = ResultSummary(id="result-summary")
        main.mount(rs)

        # Populate from DB data
        if self._rw_conn:
            from planner_auto.db import get_latest_plan_draft
            import re

            draft = get_latest_plan_draft(self._rw_conn, self._session_id)
            draft_number = draft["draft_number"] if draft else 0
            plan_size = len(draft["content"]) if draft else 0
            plan_text = draft["content"] if draft else ""
            milestone_count = len(re.findall(r"^## Milestone \d+:", plan_text, re.MULTILINE))

            # Count review rounds
            review_count_row = self._rw_conn.execute(
                "SELECT COUNT(*) as cnt FROM reviews WHERE session_id = ?",
                (self._session_id,),
            ).fetchone()
            review_rounds = review_count_row["cnt"] if review_count_row else 0

            # Get total cost from reviews
            cost_row = self._rw_conn.execute(
                "SELECT COALESCE(SUM(cost), 0.0) as total FROM reviews WHERE session_id = ?",
                (self._session_id,),
            ).fetchone()
            total_cost = cost_row["total"] if cost_row else 0.0

            # Get export paths (check if session dir exists)
            import os
            from planner_auto.export import DEFAULT_SESSIONS_DIR
            session_dir = os.path.join(DEFAULT_SESSIONS_DIR, self._session_id)
            export_paths = []
            if os.path.isdir(session_dir):
                export_paths = [os.path.join(session_dir, f) for f in sorted(os.listdir(session_dir))]

            # Check .kafra
            from planner_auto.db import get_session_config
            cfg_row = get_session_config(self._rw_conn, self._session_id)
            kafra_path = None
            if cfg_row:
                import json
                try:
                    cfg = json.loads(cfg_row["config_json"])
                    repo_root = cfg.get("repo_root")
                    project = cfg.get("project", self._session_id)
                    if repo_root:
                        candidate = os.path.join(repo_root, ".kafra", "a-01-plans", f"{project}.md")
                        if os.path.exists(candidate):
                            kafra_path = candidate
                except (json.JSONDecodeError, TypeError):
                    pass

            self.call_later(lambda: rs.set_summary(
                export_paths=export_paths,
                kafra_path=kafra_path,
                total_cost=total_cost,
                review_rounds=review_rounds,
                draft_number=draft_number,
                plan_size=plan_size,
                milestone_count=milestone_count,
            ))
            self._log("info", f"Session completed — {review_rounds} review rounds, ${total_cost:.4f}")

    def _mount_paused_panel(self) -> None:
        """Mount the paused/blocker display (resume scenario)."""
        main = self.query_one("#main-panel", Container)
        for child in list(main.query("*")):
            child.remove()

        blocker_text = (
            f"[bold $warning]Session Paused[/bold $warning]\n\n"
            f"[bold]Source:[/bold] {self._blocker_source}\n"
            f"[bold]Question:[/bold]\n{self._blocker_question}\n\n"
            f"Press [bold]Enter[/bold] to answer the blocker.\n"
            f"Press [bold]q[/bold] to exit."
        )
        main.mount(Static(blocker_text, id="blocker-display"))
        self._log("warning", f"Session is paused — {self._blocker_source} blocker")

    def _mount_review_resume_panel(self) -> None:
        """Mount review resume panel — shows last plan + option to start review."""
        main = self.query_one("#main-panel", Container)
        for child in list(main.query("*")):
            child.remove()

        # Load the plan
        if self._rw_conn:
            draft = get_latest_plan_draft(self._rw_conn, self._session_id)
            if draft:
                self._plan_content = draft["content"]

        # Show existing review history if any
        review_count_row = self._rw_conn.execute(
            "SELECT COUNT(*) as cnt FROM reviews WHERE session_id = ?",
            (self._session_id,),
        ).fetchone() if self._rw_conn else None
        review_count = review_count_row["cnt"] if review_count_row else 0

        info_text = (
            f"[bold $accent]Review Phase[/bold $accent]\n\n"
            f"Session is in REVIEW phase."
        )
        if review_count > 0:
            info_text += f"\n{review_count} previous review round(s) found.\n"
        info_text += (
            f"\nPress [bold]r[/bold] to start a new review loop.\n"
            f"Press [bold]p[/bold] to view the current plan.\n"
            f"Press [bold]q[/bold] to exit."
        )
        main.mount(Static(info_text, id="review-resume-info"))
        self._log("info", f"Review phase — {review_count} previous rounds. Press r to start review.")

    # --- Message handlers ---

    def on_context_added(self, message: ContextAdded) -> None:
        """Handle context entry addition."""
        cl = self.query_one("#context-list", ContextList)
        cl.add_entry(message.entry_type, message.key, message.size)

        # Update context summary
        pl = self.query_one("#phase-list", PhaseList)
        total = cl.get_file_count() + cl.get_note_count()
        pl.set_count("CONTEXT", str(total))

        self._log("success", f"Added {message.entry_type}: {message.key[-40:]}")

        # Check if phase changed (SETUP → CONTEXT on first add)
        if self._rw_conn:
            session = get_session(self._rw_conn, self._session_id)
            if session and session["phase"] != self._current_phase:
                old_phase = self._current_phase
                self.post_message(PhaseAdvanced(old_phase, session["phase"]))

    def on_phase_advanced(self, message: PhaseAdvanced) -> None:
        """Handle phase transitions."""
        self._current_phase = message.to_phase
        self._update_bindings(self._current_phase)

        # Update phase list
        pl = self.query_one("#phase-list", PhaseList)
        pl.set_active(self._current_phase)

        # Update session panel
        sp = self.query_one("#session-panel", SessionPanel)
        sp.set_field("phase", self._current_phase)

        # Update compact bar
        cpb = self.query_one("#compact-phase-bar", CompactPhaseBar)
        cpb.set_active_phase(self._current_phase)

        # Switch main panel
        self._switch_main_panel(self._current_phase)

        self._log("info", f"Phase: {message.from_phase} \u2192 {message.to_phase}")

    def on_session_error(self, message: SessionError) -> None:
        """Handle session errors."""
        self._log("error", f"[{message.phase}] {message.error_message}")

        # If error during discussion, re-enable input
        if self._current_phase == Phase.DISCUSSION.value:
            self._discuss_active = False
            try:
                from planner_auto.tui.widgets.chat_view import ChatView
                chat = self.query_one("#chat-view", ChatView)
                chat.clear_thinking()
                chat.enable_input()
            except Exception:
                pass

        # If error during generation, clear generation state
        if self._current_phase == Phase.PLANNING.value:
            self._generation_active = False
            if self._generation_timer is not None:
                self._generation_timer.stop()
                self._generation_timer = None

        # If error during review, clear review state
        if self._current_phase == Phase.REVIEW.value:
            self._review_active = False
            if self._tick_timer:
                self._tick_timer.stop()
                self._tick_timer = None

    # --- Discussion message handlers ---

    def on_discuss_response_received(self, message: DiscussResponseReceived) -> None:
        """Handle Claude's discussion response."""
        self._discuss_active = False

        # Stop thinking timer
        if self._thinking_timer is not None:
            self._thinking_timer.stop()
            self._thinking_timer = None

        try:
            from planner_auto.tui.widgets.chat_view import ChatView
            chat = self.query_one("#chat-view", ChatView)
            chat.clear_thinking()
            chat.add_message("assistant", message.content)
            chat.enable_input()
        except Exception:
            pass

        latency_s = message.latency_ms / 1000.0
        self._log(
            "info",
            f"Claude responded ({len(message.content)} chars, {latency_s:.1f}s)",
        )

        # Handle deferred quit
        if self._quit_requested:
            self._cleanup_and_exit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in chat input."""
        if self._current_phase != Phase.DISCUSSION.value:
            return
        if event.input.id != "chat-input":
            return
        if self._discuss_active:
            return

        text = event.value.strip()
        if not text:
            return

        try:
            from planner_auto.tui.widgets.chat_view import ChatView
            chat = self.query_one("#chat-view", ChatView)
        except Exception:
            return

        # Clear input, show message, start thinking, disable input
        chat.clear_input()
        chat.add_message("user", text)
        chat.show_thinking()
        chat.disable_input()
        self._discuss_active = True

        # Start thinking timer (updates elapsed every second)
        self._thinking_timer = self.set_interval(1.0, self._update_thinking)

        # Spawn worker
        self._send_discuss_message(text)

    def _update_thinking(self) -> None:
        """Update the thinking indicator elapsed time."""
        if self._current_phase != Phase.DISCUSSION.value:
            return
        try:
            from planner_auto.tui.widgets.chat_view import ChatView
            chat = self.query_one("#chat-view", ChatView)
            chat.update_thinking_elapsed()
        except Exception:
            pass

    @work(thread=True)
    def _send_discuss_message(self, content: str) -> None:
        """Send a discussion message in a worker thread.

        Opens its own DB connection, calls agents.discuss(), posts result.
        """
        from planner_auto.agents import discuss as discuss_fn

        worker_conn: Optional[sqlite3.Connection] = None
        t0 = time.monotonic()
        try:
            # Open own connection
            if self._db_path:
                worker_conn = open_db(self._db_path)
            else:
                worker_conn = open_db()
            init_schema(worker_conn)

            # Resolve backend
            backend = _resolve_backend_from_config(worker_conn, self._session_id)

            # Call discuss
            response = asyncio.run(
                discuss_fn(self._session_id, content, worker_conn, backend=backend)
            )
            latency_ms = int((time.monotonic() - t0) * 1000)

            # Post result to main thread
            self.call_from_thread(
                self.post_message,
                DiscussResponseReceived(response, latency_ms),
            )
        except Exception as exc:
            logger.error("Discussion error: %s", exc, exc_info=True)
            self.call_from_thread(
                self.post_message,
                SessionError(str(exc), Phase.DISCUSSION.value),
            )
        finally:
            if worker_conn:
                try:
                    worker_conn.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Planning message handlers
    # ------------------------------------------------------------------

    def on_synthesis_started(self, message: SynthesisStarted) -> None:
        """Handle synthesis start — update generation progress."""
        try:
            from planner_auto.tui.widgets.generation_progress import GenerationProgress
            gp = self.query_one("#generation-progress", GenerationProgress)
            gp.start_synthesis(message.file_count, message.note_count)
        except Exception:
            pass

    def on_synthesis_complete(self, message: SynthesisComplete) -> None:
        """Handle synthesis complete — update generation progress."""
        try:
            from planner_auto.tui.widgets.generation_progress import GenerationProgress
            gp = self.query_one("#generation-progress", GenerationProgress)
            gp.complete_synthesis(message.output_size, message.latency_ms)
        except Exception:
            pass

    def on_plan_generation_started(self, message: PlanGenerationStarted) -> None:
        """Handle plan generation start — update generation progress."""
        try:
            from planner_auto.tui.widgets.generation_progress import GenerationProgress
            gp = self.query_one("#generation-progress", GenerationProgress)
            gp.start_generation(message.model)
        except Exception:
            pass

    def on_plan_generated(self, message: PlanGenerated) -> None:
        """Handle plan generated — replace progress with plan view."""
        self._generation_active = False
        if self._generation_timer is not None:
            self._generation_timer.stop()
            self._generation_timer = None

        # Store plan content for review
        if self._rw_conn:
            draft = get_latest_plan_draft(self._rw_conn, self._session_id)
            if draft:
                self._plan_content = draft["content"]
                self._plan_model = draft.get("model", "unknown")

        # Replace GenerationProgress with PlanView
        main = self.query_one("#main-panel", Container)
        for sel in ("#generation-progress",):
            old = main.query(sel)
            for widget in old:
                widget.remove()

        from planner_auto.tui.widgets.plan_view import PlanView
        pv = PlanView(id="plan-view")
        main.mount(pv)

        self.call_later(lambda: pv.set_plan(
            draft_number=message.draft_number,
            content=self._plan_content,
            model=self._plan_model,
            validation_ok=message.validation_ok,
            warnings=message.warnings if message.warnings else None,
        ))

        self._log(
            "success",
            f"Plan generated: Draft #{message.draft_number}, "
            f"{message.size:,} chars, {message.milestone_count} milestones",
        )

    def _update_generation_elapsed(self) -> None:
        """Update elapsed timer on generation progress widget."""
        try:
            from planner_auto.tui.widgets.generation_progress import GenerationProgress
            gp = self.query_one("#generation-progress", GenerationProgress)
            gp.tick_elapsed()
        except Exception:
            pass

    @work(thread=True)
    def _run_generate(self) -> None:
        """Run plan generation in a worker thread.

        Calls generate_plan() which internally does synthesis + plan generation.
        Posts progress messages for each step. Note: generate_plan() calls
        synthesize_context() internally, so we do NOT call it separately here
        to avoid double synthesis.
        """
        from planner_auto.agents import generate_plan
        from planner_auto.validation import validate_plan_format

        self._generation_active = True

        # Start elapsed timer on main thread
        self.call_from_thread(self._start_generation_timer)

        worker_conn: Optional[sqlite3.Connection] = None
        t0 = time.monotonic()
        try:
            # Open own connection
            if self._db_path:
                worker_conn = open_db(self._db_path)
            else:
                worker_conn = open_db()
            init_schema(worker_conn)

            backend = _resolve_backend_from_config(worker_conn, self._session_id)

            # Count context entries for progress display
            entries = get_context_entries(worker_conn, self._session_id)
            file_count = sum(1 for e in entries if e["entry_type"] == "file")
            note_count = sum(1 for e in entries if e["entry_type"] == "note")

            # Resolve model
            cfg_row = get_session_config(worker_conn, self._session_id)
            model = "claude-sonnet-4-6"
            if cfg_row:
                try:
                    cfg = json.loads(cfg_row["config_json"])
                    model = cfg.get("model", model)
                except (json.JSONDecodeError, TypeError):
                    pass

            # generate_plan() internally calls synthesize_context() then
            # generates the plan — one call covers both steps.
            # We signal a single "generating" event (not two fake steps).
            self.call_from_thread(
                self.post_message,
                PlanGenerationStarted(model),
            )

            t_gen = time.monotonic()
            plan_content = asyncio.run(
                generate_plan(self._session_id, worker_conn, model=model, backend=backend)
            )
            gen_ms = int((time.monotonic() - t_gen) * 1000)

            # Validate plan
            warnings = validate_plan_format(plan_content)

            # Get draft number from DB
            draft = get_latest_plan_draft(worker_conn, self._session_id)
            draft_number = draft["draft_number"] if draft else 1

            # Count milestones
            import re
            milestone_count = len(re.findall(r"^## Milestone \d+:", plan_content, re.MULTILINE))

            self.call_from_thread(
                self.post_message,
                PlanGenerated(
                    draft_number=draft_number,
                    size=len(plan_content),
                    milestone_count=milestone_count,
                    latency_ms=plan_ms,
                    validation_ok=len(warnings) == 0,
                    warnings=warnings,
                ),
            )
        except Exception as exc:
            logger.error("Generation error: %s", exc, exc_info=True)
            self.call_from_thread(
                self.post_message,
                SessionError(str(exc), Phase.PLANNING.value),
            )
        finally:
            self._generation_active = False
            if worker_conn:
                try:
                    worker_conn.close()
                except Exception:
                    pass

    def _start_generation_timer(self) -> None:
        """Start the generation elapsed timer (called on main thread)."""
        if self._generation_timer is not None:
            self._generation_timer.stop()
        self._generation_timer = self.set_interval(1.0, self._update_generation_elapsed)

    # ------------------------------------------------------------------
    # Review message handlers
    # ------------------------------------------------------------------

    def on_round_started(self, message: RoundStarted) -> None:
        """Handle RoundStarted — delegate to ReviewHandlerMixin."""
        try:
            self._review_handlers.handle_round_started(
                message,
                self.query_one("#review-round-list", RoundList),
                self.query_one("#review-current-round", CurrentRound),
                self.query_one("#log-panel", LogPanel),
            )
        except Exception:
            pass

    def on_review_complete(self, message: ReviewComplete) -> None:
        """Handle ReviewComplete — delegate to ReviewHandlerMixin."""
        try:
            self._review_handlers.handle_review_complete(
                message,
                self.query_one("#review-round-list", RoundList),
                self.query_one("#review-convergence", ConvergencePanel),
                self.query_one("#review-current-round", CurrentRound),
                self.query_one("#log-panel", LogPanel),
            )
        except Exception:
            pass

    def on_feedback_validated(self, message: FeedbackValidated) -> None:
        """Handle FeedbackValidated — delegate to ReviewHandlerMixin."""
        try:
            self._review_handlers.handle_feedback_validated(
                message,
                self.query_one("#review-current-round", CurrentRound),
                self.query_one("#log-panel", LogPanel),
            )
        except Exception:
            pass

    def on_revision_started(self, message: RevisionStarted) -> None:
        """Handle RevisionStarted — delegate to ReviewHandlerMixin."""
        try:
            self._review_handlers.handle_revision_started(
                message,
                self.query_one("#review-current-round", CurrentRound),
                self.query_one("#log-panel", LogPanel),
            )
        except Exception:
            pass

    def on_revision_complete(self, message: RevisionComplete) -> None:
        """Handle RevisionComplete — delegate to ReviewHandlerMixin."""
        try:
            # Review panel doesn't have its own PlanPanel widget, use log only
            self._review_handlers.handle_revision_complete(
                message,
                PlanPanel(),  # dummy — session TUI doesn't have sidebar plan panel
                self.query_one("#review-current-round", CurrentRound),
                self.query_one("#log-panel", LogPanel),
            )
        except Exception:
            pass

    def on_revision_timeout(self, message: RevisionTimeout) -> None:
        """Handle RevisionTimeout — delegate to ReviewHandlerMixin."""
        try:
            self._review_handlers.handle_revision_timeout(
                message,
                self.query_one("#review-current-round", CurrentRound),
                self.query_one("#log-panel", LogPanel),
            )
        except Exception:
            pass

    def on_loop_finished(self, message: LoopFinished) -> None:
        """Handle LoopFinished — update review widgets only.

        Phase transitions are triggered by SessionCompleted/BlockerCreated,
        NOT by LoopFinished. This keeps review widget updates and session
        phase transitions as two separate responsibilities.
        """
        self._review_active = False
        if self._tick_timer:
            self._tick_timer.stop()
            self._tick_timer = None

        try:
            self._review_handlers.handle_loop_finished(
                message,
                self.query_one("#session-panel", SessionPanel),
                self.query_one("#review-current-round", CurrentRound),
                self.query_one("#log-panel", LogPanel),
            )
        except Exception:
            pass

    def on_loop_error(self, message: LoopError) -> None:
        """Handle LoopError from the review engine."""
        self._review_active = False
        if self._tick_timer:
            self._tick_timer.stop()
            self._tick_timer = None

        try:
            cr = self.query_one("#review-current-round", CurrentRound)
            cr.clear()
        except Exception:
            pass

        round_info = f" (round {message.round_num})" if message.round_num else ""
        self._log("error", f"Review error{round_info}: {message.error_message}")

        if self._quit_requested:
            self._cleanup_and_exit()

    def _on_review_tick(self) -> None:
        """Called every 1 second to update elapsed timers during review."""
        try:
            cr = self.query_one("#review-current-round", CurrentRound)
            cr.tick()
        except Exception:
            pass

    @work(thread=True)
    def _run_review_loop(self) -> None:
        """Run the review loop in a worker thread.

        Opens its own DB connection, runs prepare+run+finalize.
        Posts SessionCompleted or BlockerCreated after finalize.
        """
        self._review_active = True

        # Start tick timer on main thread
        self.call_from_thread(self._start_review_tick)

        worker_conn: Optional[sqlite3.Connection] = None
        try:
            if self._db_path:
                worker_conn = open_db(self._db_path)
            else:
                worker_conn = open_db()
            init_schema(worker_conn)

            backend = _resolve_backend_from_config(worker_conn, self._session_id)

            # Prepare review
            opts = ReviewOpts(verbosity="tui")
            prepared = ReviewWorkflow.prepare(
                worker_conn, self._session_id, opts, claude_backend=backend,
            )
            self._prepared_review = prepared

            # Create adapter for thread-safe message dispatch
            adapter = TUIAdapter(self)

            # Create engine with worker-owned connection
            engine = ReviewLoopEngine(
                conn=worker_conn,
                session_id=self._session_id,
                reviewer=prepared.reviewer,
                planner_model=prepared.planner_model,
                config=prepared.engine_config,
                callbacks=adapter.as_dict(),
            )

            # Run the loop
            result = ReviewWorkflow.run(engine, prepared.current_plan, prepared.max_rounds)

            # Always call finalize — handles both convergence and cap+criticals
            finalize_result = ReviewWorkflow.finalize(
                worker_conn, self._session_id, result, prepared,
            )

            # Post phase-transition message based on finalize result
            if finalize_result.converged:
                self.call_from_thread(
                    self.post_message,
                    SessionCompleted(
                        export_paths=finalize_result.export_paths,
                        kafra_path=finalize_result.kafra_path,
                        total_cost=finalize_result.total_cost,
                    ),
                )
            else:
                # Get blocker ID from DB
                blockers = get_open_blockers(worker_conn, self._session_id)
                blocker_id = blockers[-1]["id"] if blockers else 0
                self.call_from_thread(
                    self.post_message,
                    BlockerCreated(
                        source="reviewer",
                        question=finalize_result.blocker_text or "Review cap reached.",
                        blocker_id=blocker_id,
                    ),
                )
        except Exception as exc:
            logger.error("Review error: %s", exc, exc_info=True)
            adapter_err = TUIAdapter(self)
            adapter_err.on_error(str(exc), round_num=self._review_handlers.latest_round or None)
            self._review_active = False
        finally:
            if worker_conn:
                try:
                    worker_conn.close()
                except Exception:
                    pass

    def _start_review_tick(self) -> None:
        """Start the review tick timer (called on main thread)."""
        if self._tick_timer is not None:
            self._tick_timer.stop()
        self._tick_timer = self.set_interval(1.0, self._on_review_tick)

    # ------------------------------------------------------------------
    # Completion + blocker message handlers
    # ------------------------------------------------------------------

    def on_session_completed(self, message: SessionCompleted) -> None:
        """Handle SessionCompleted — advance to COMPLETE phase."""
        self._review_active = False

        old_phase = self._current_phase
        self.post_message(PhaseAdvanced(old_phase, Phase.COMPLETE.value))

        # Populate result summary
        self.call_later(lambda: self._populate_result_summary(message))

        sp = self.query_one("#session-panel", SessionPanel)
        sp.set_field("status", "COMPLETE")

        if self._quit_requested:
            self.call_later(self._cleanup_and_exit)

    def _populate_result_summary(self, message: SessionCompleted) -> None:
        """Populate the ResultSummary widget with completion data."""
        try:
            from planner_auto.tui.widgets.result_summary import ResultSummary
            rs = self.query_one("#result-summary", ResultSummary)

            # Query additional info from DB
            review_rounds = 0
            draft_number = 0
            plan_size = 0
            milestone_count = 0
            if self._rw_conn:
                draft = get_latest_plan_draft(self._rw_conn, self._session_id)
                if draft:
                    draft_number = draft["draft_number"]
                    plan_size = len(draft["content"])
                    import re
                    milestone_count = len(re.findall(
                        r"^## Milestone \d+:", draft["content"], re.MULTILINE
                    ))
                # Count review rounds
                try:
                    row = self._rw_conn.execute(
                        "SELECT COUNT(*) as cnt FROM reviews WHERE session_id = ?",
                        (self._session_id,),
                    ).fetchone()
                    if row:
                        review_rounds = row["cnt"] if isinstance(row["cnt"], int) else row[0]
                except Exception:
                    pass

            rs.set_summary(
                export_paths=message.export_paths,
                kafra_path=message.kafra_path,
                total_cost=message.total_cost,
                review_rounds=review_rounds,
                draft_number=draft_number,
                plan_size=plan_size,
                milestone_count=milestone_count,
            )
        except Exception as exc:
            logger.error("Error populating result summary: %s", exc, exc_info=True)

    def on_blocker_created(self, message: BlockerCreated) -> None:
        """Handle BlockerCreated — store blocker info, push BlockerScreen modal."""
        # Store blocker state
        self._blocker_id = message.blocker_id
        self._blocker_source = message.source
        self._blocker_question = message.question

        # Update phase list to show paused icon
        pl = self.query_one("#phase-list", PhaseList)
        pl.set_paused(self._current_phase)

        sp = self.query_one("#session-panel", SessionPanel)
        sp.set_field("status", "PAUSED")

        # Switch to PAUSED bindings
        self._update_bindings("PAUSED")

        # Mount blocker summary in main panel
        main = self.query_one("#main-panel", Container)
        # Remove review widgets
        for sel in ("#review-round-list", "#review-convergence", "#review-current-round"):
            old = main.query(sel)
            for widget in old:
                widget.remove()

        blocker_text = (
            f"[bold $warning]Session Paused[/bold $warning]\n\n"
            f"[bold]Source:[/bold] {message.source}\n"
            f"[bold]Question:[/bold]\n{message.question}\n\n"
            f"Press [bold]Enter[/bold] to answer the blocker.\n"
            f"Press [bold]q[/bold] to exit."
        )
        main.mount(Static(blocker_text, id="blocker-display"))

        self._log("warning", f"Session paused: {message.source} blocker created")

        # Immediately push the blocker screen
        self._push_blocker_screen()

        if self._quit_requested:
            self._cleanup_and_exit()

    def _push_blocker_screen(self) -> None:
        """Push the BlockerScreen modal for the current blocker."""
        from planner_auto.tui.screens.blocker_screen import BlockerScreen
        self.push_screen(
            BlockerScreen(source=self._blocker_source, question=self._blocker_question),
            callback=self._handle_blocker_answer,
        )

    def _handle_blocker_answer(self, answer: str | None) -> None:
        """Handle the result from BlockerScreen."""
        if answer is None:
            # Dismissed without answering — session stays paused
            self._log("info", "Blocker dismissed. Session remains paused. Press Enter to try again.")
            return
        if self._blocker_id is None:
            self._log("error", "No blocker to resolve.")
            return
        if self._resolve_active:
            self._log("warning", "Blocker resolution already in progress.")
            return

        self._resolve_active = True
        self._log("info", "Resolving blocker...")
        self._resolve_blocker(answer)

    @work(thread=True)
    def _resolve_blocker(self, answer: str) -> None:
        """Resolve the blocker in a worker thread.

        Opens its own DB connection, calls resolve_and_resume(),
        posts BlockerResolved on success.
        """
        worker_conn: Optional[sqlite3.Connection] = None
        try:
            if self._db_path:
                worker_conn = open_db(self._db_path)
            else:
                worker_conn = open_db()
            init_schema(worker_conn)

            sm = SessionManager(worker_conn)
            sm.resolve_and_resume(self._session_id, self._blocker_id, answer)

            # Read the session's current phase after resolution
            session = get_session(worker_conn, self._session_id)
            phase = session["phase"] if session else self._current_phase

            self.call_from_thread(
                self.post_message,
                BlockerResolved(blocker_id=self._blocker_id, phase=phase),
            )
        except Exception as exc:
            logger.error("Blocker resolution error: %s", exc, exc_info=True)
            self.call_from_thread(
                self.post_message,
                SessionError(str(exc), "PAUSED"),
            )
        finally:
            self._resolve_active = False
            if worker_conn:
                try:
                    worker_conn.close()
                except Exception:
                    pass

    def on_blocker_resolved(self, message: BlockerResolved) -> None:
        """Handle BlockerResolved — restore session to active state.

        Updates PhaseList (removes paused icon, restores previous phase),
        updates sidebar status, logs resolution. No automatic re-entry
        into review — user decides next action.
        """
        self._blocker_id = None
        self._blocker_source = ""
        self._blocker_question = ""

        # Restore phase list — set the current phase as active
        pl = self.query_one("#phase-list", PhaseList)
        pl.set_active(message.phase)

        # Update session panel
        sp = self.query_one("#session-panel", SessionPanel)
        sp.set_field("status", "ACTIVE")
        sp.set_field("phase", message.phase)

        # Update current phase and bindings
        self._current_phase = message.phase
        self._update_bindings(self._current_phase)

        # Update compact bar
        cpb = self.query_one("#compact-phase-bar", CompactPhaseBar)
        cpb.set_active_phase(self._current_phase)

        # Replace blocker display with phase-appropriate content
        self._switch_main_panel(self._current_phase)

        self._log("success", "Blocker resolved. Session resumed.")

    # --- Actions ---

    def action_add_file(self) -> None:
        """Open file input modal."""
        if self._current_phase not in (Phase.SETUP.value, Phase.CONTEXT.value):
            return
        from planner_auto.tui.screens.file_input_screen import FileInputScreen
        self.push_screen(FileInputScreen(), callback=self._handle_file_result)

    def _handle_file_result(self, path: str | None) -> None:
        """Handle the result from FileInputScreen."""
        if path is None:
            return
        if not self._rw_conn:
            return

        try:
            result = add_context_entry(
                self._rw_conn, self._session_id, "file", path,
            )
            self.post_message(ContextAdded(
                result["entry_type"], result["key"], result["size"],
            ))
        except ContextError as e:
            self._log("error", str(e))
            # Re-push the screen with error
            from planner_auto.tui.screens.file_input_screen import FileInputScreen
            screen = FileInputScreen()
            self.push_screen(screen, callback=self._handle_file_result)
            self.call_later(lambda: screen.show_error(str(e)))
        except Exception as e:
            self.post_message(SessionError(str(e), self._current_phase))

    def action_add_note(self) -> None:
        """Open note input modal."""
        if self._current_phase not in (Phase.SETUP.value, Phase.CONTEXT.value):
            return
        from planner_auto.tui.screens.note_input_screen import NoteInputScreen
        self.push_screen(NoteInputScreen(), callback=self._handle_note_result)

    def _handle_note_result(self, content: str | None) -> None:
        """Handle the result from NoteInputScreen."""
        if content is None:
            return
        if not self._rw_conn:
            return

        try:
            result = add_context_entry(
                self._rw_conn, self._session_id, "note", content,
            )
            self.post_message(ContextAdded(
                result["entry_type"], result["key"], result["size"],
            ))
        except Exception as e:
            self.post_message(SessionError(str(e), self._current_phase))

    def action_advance_discussion(self) -> None:
        """Advance from CONTEXT to DISCUSSION."""
        if self._current_phase != Phase.CONTEXT.value:
            return
        if not self._rw_conn:
            return

        try:
            sm = SessionManager(self._rw_conn)
            old_phase = self._current_phase
            sm.advance_phase(self._session_id, Phase.DISCUSSION.value)
            self.post_message(PhaseAdvanced(old_phase, Phase.DISCUSSION.value))
        except Exception as e:
            self.post_message(SessionError(str(e), self._current_phase))

    def action_advance_planning(self) -> None:
        """Advance from DISCUSSION to PLANNING (Ctrl+D)."""
        if self._current_phase != Phase.DISCUSSION.value:
            return
        if not self._rw_conn:
            return
        if self._discuss_active:
            self._log("warning", "Cannot advance while Claude is responding. Wait or press q to quit.")
            return

        try:
            sm = SessionManager(self._rw_conn)
            old_phase = self._current_phase
            sm.advance_phase(self._session_id, Phase.PLANNING.value)
            self.post_message(PhaseAdvanced(old_phase, Phase.PLANNING.value))
        except Exception as e:
            self.post_message(SessionError(str(e), self._current_phase))

    def action_regenerate(self) -> None:
        """Regenerate the plan (g key in PLANNING phase)."""
        if self._current_phase != Phase.PLANNING.value:
            return
        if self._generation_active:
            self._log("warning", "Generation already in progress.")
            return

        self._log("info", "Regenerating plan...")

        # Replace current panel content with generation progress
        main = self.query_one("#main-panel", Container)
        for sel in ("#plan-view", "#generation-progress"):
            old = main.query(sel)
            for widget in old:
                widget.remove()

        from planner_auto.tui.widgets.generation_progress import GenerationProgress
        gp = GenerationProgress(id="generation-progress")
        main.mount(gp)
        self._run_generate()

    def action_start_review(self) -> None:
        """Start the review loop (r key in PLANNING or REVIEW phase)."""
        if self._current_phase not in (Phase.PLANNING.value, Phase.REVIEW.value):
            return
        if not self._rw_conn:
            return
        if self._generation_active:
            self._log("warning", "Cannot start review while generation is in progress.")
            return

        # Check we have a plan
        if not self._plan_content:
            draft = get_latest_plan_draft(self._rw_conn, self._session_id)
            if not draft:
                self._log("error", "No plan draft found. Press g to generate first.")
                return
            self._plan_content = draft["content"]

        # Advance phase to REVIEW
        try:
            sm = SessionManager(self._rw_conn)
            old_phase = self._current_phase
            sm.advance_phase(self._session_id, Phase.REVIEW.value)
            self.post_message(PhaseAdvanced(old_phase, Phase.REVIEW.value))
        except Exception as e:
            self.post_message(SessionError(str(e), self._current_phase))
            return

        # Start the review loop worker
        self._run_review_loop()

    def action_dispositions(self) -> None:
        """Show dispositions screen (review phase)."""
        if self._current_phase != Phase.REVIEW.value:
            return
        from planner_auto.tui.screens.disposition_screen import DispositionScreen
        round_data = self._review_handlers.round_data if self._review_handlers else []
        self.push_screen(DispositionScreen(
            session_id=self._session_id,
            round_data=round_data,
            conn=self._rw_conn,
        ))

    def action_plan(self) -> None:
        """Show plan text (review/planning/complete phases)."""
        if self._current_phase not in (Phase.PLANNING.value, Phase.REVIEW.value, Phase.COMPLETE.value):
            return
        plan_text = self._plan_content
        if not plan_text and self._rw_conn:
            draft = get_latest_plan_draft(self._rw_conn, self._session_id)
            if draft:
                plan_text = draft["content"]
        if plan_text:
            from planner_auto.tui.screens.plan_screen import PlanScreen
            self.push_screen(PlanScreen(
                plan_text=plan_text,
                conn=self._rw_conn,
                session_id=self._session_id,
            ))
        else:
            self._log("info", "No plan content available.")

    def action_select_round(self) -> None:
        """Select round for detail (review phase)."""
        if self._current_phase != Phase.REVIEW.value:
            return
        if not self._review_handlers or not self._review_handlers.round_data:
            self._log("info", "No review rounds available yet.")
            return
        latest = self._review_handlers.latest_round
        if latest is not None:
            from planner_auto.tui.widgets.round_detail import RoundDetail
            rd = RoundDetail(round_data=self._review_handlers.round_data.get(latest, {}))
            self.push_screen(rd) if hasattr(rd, 'run') else self._log("info", f"Round {latest} detail available via standalone TUI.")

    def action_back(self) -> None:
        """Back action (dismiss modal/detail view)."""
        pass

    def action_next_round(self) -> None:
        """Next round action (review phase)."""
        pass

    def action_copy_plan_path(self) -> None:
        """Copy plan path to clipboard (complete phase)."""
        if self._current_phase != Phase.COMPLETE.value:
            return
        self._log("info", f"Plan path: use `planner-auto export {self._session_id[:12]}` to get artifacts.")

    def action_open_blocker(self) -> None:
        """Open blocker resolution screen (Enter key in PAUSED state)."""
        if self._blocker_id is None:
            self._log("warning", "No active blocker to resolve.")
            return
        if self._resolve_active:
            self._log("warning", "Blocker resolution already in progress.")
            return
        self._push_blocker_screen()

    def action_export(self) -> None:
        """Export session artifacts."""
        self._log("info", "Export: use CLI `planner-auto export <session-id>`")

    def action_log_filter(self) -> None:
        """Cycle log filter level."""
        lp = self.query_one("#log-panel", LogPanel)
        new_level = lp.cycle_filter()
        self._log("info", f"Log filter: {new_level}")

    def action_help(self) -> None:
        """Show help screen."""
        if self._current_phase == Phase.DISCUSSION.value:
            self._log("info", "Keybindings: Enter=send, Ctrl+D=done, e=export, l=log, q=quit")
        elif self._current_phase == Phase.PLANNING.value:
            self._log("info", "Keybindings: g=generate, r=review, e=export, l=log, q=quit")
        elif self._current_phase == Phase.REVIEW.value:
            self._log("info", "Keybindings: d=dispositions, p=plan, l=log, q=quit")
        elif self._current_phase == Phase.COMPLETE.value:
            self._log("info", "Keybindings: p=plan, c=copy path, e=export, l=log, q=quit")
        else:
            self._log("info", "Keybindings: f=file, n=note, d=done, e=export, l=log, q=quit")

    def action_quit(self) -> None:
        """Quit the TUI with deferred quit during active operations."""
        if not self._discuss_active and not self._review_active:
            self._cleanup_and_exit()
        else:
            # Defer quit until the current worker finishes
            self._quit_requested = True
            self._log("info", "Waiting for current operation to finish before quitting...")

    def _cleanup_and_exit(self) -> None:
        """Clean up resources and exit."""
        if self._thinking_timer is not None:
            self._thinking_timer.stop()
            self._thinking_timer = None
        if self._generation_timer is not None:
            self._generation_timer.stop()
            self._generation_timer = None
        if self._tick_timer is not None:
            self._tick_timer.stop()
            self._tick_timer = None
        if self._rw_conn:
            try:
                self._rw_conn.close()
            except Exception:
                pass
        self.exit()

    # --- Helpers ---

    def _log(self, level: str, message: str) -> None:
        """Write a message to the log panel."""
        try:
            lp = self.query_one("#log-panel", LogPanel)
            lp.log_message(message, level)
        except Exception:
            pass
