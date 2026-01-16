"""
Main TUI application for orchestrator-auto.

Provides a rich text user interface for running workflows.
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Header, Footer
from textual.worker import Worker
from typing import Optional, TYPE_CHECKING

from . import messages
from .adapter import TUIOutputAdapter, TUIInputProvider
from .bindings import GLOBAL_BINDINGS, SESSION_BINDINGS
from .widgets import StatusPanel, MilestoneList, AgentOutput, LogPanel, InputModal

if TYPE_CHECKING:
    from ..engine import Orchestrator


class OrchestratorTUI(App):
    """
    Text User Interface for orchestrator-auto.

    Provides a rich interface for running workflows with:
    - Real-time streaming output
    - Status panel showing phase/status/stats
    - Milestone progress tracking
    - Log panel for orchestrator messages
    - Support for input prompts via modal

    Usage:
        app = OrchestratorTUI(feature="My feature")
        app.run()
    """

    TITLE = "Orchestrator Auto"
    SUB_TITLE = "AI Workflow Manager"
    CSS_PATH = "styles/theme.tcss"

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 3;
        grid-columns: 1fr 2fr;
        grid-rows: auto 1fr auto;
    }

    #left-panel {
        column-span: 1;
        row-span: 2;
        layout: vertical;
    }

    #status-panel {
        height: auto;
    }

    #milestone-list {
        height: 1fr;
    }

    #right-panel {
        column-span: 1;
        row-span: 2;
        layout: vertical;
    }

    #agent-output {
        height: 1fr;
    }

    #log-panel {
        column-span: 2;
        height: 8;
    }

    Header {
        dock: top;
    }

    Footer {
        dock: bottom;
    }
    """

    BINDINGS = GLOBAL_BINDINGS + SESSION_BINDINGS

    def __init__(
        self,
        feature: str = "",
        db_path: Optional[str] = None,
        plan_path: Optional[str] = None,
        planner_model: Optional[str] = None,
        executor_model: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> None:
        """
        Initialize the TUI.

        Args:
            feature: Feature description for new workflows.
            db_path: Optional database path.
            plan_path: Optional plan file path.
            planner_model: Model for planner agent.
            executor_model: Model for executor agent.
            session_id: Session ID to resume (if resuming).
        """
        super().__init__(**kwargs)
        self.feature = feature
        self.db_path = db_path
        self.plan_path = plan_path
        self.planner_model = planner_model
        self.executor_model = executor_model
        self.session_id = session_id

        # Create adapters
        self._adapter = TUIOutputAdapter(self)
        self._input_provider = TUIInputProvider(self._adapter)

        # Orchestrator (created when workflow starts)
        self._orchestrator: Optional["Orchestrator"] = None
        self._worker: Optional[Worker] = None
        self._timer: Optional[Timer] = None

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        yield Header()
        with Horizontal():
            with Vertical(id="left-panel"):
                yield StatusPanel(id="status-panel")
                yield MilestoneList(id="milestone-list")
            with Vertical(id="right-panel"):
                yield AgentOutput(id="agent-output")
        yield LogPanel(id="log-panel")
        yield Footer()

    def on_mount(self) -> None:
        """Handle app mount - start the workflow."""
        # Log startup
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_info("Orchestrator TUI Started")
        if self.feature:
            log_panel.log_info(f"Feature: {self.feature}")

        # Set initial models if provided
        if self.planner_model or self.executor_model:
            status_panel = self.query_one("#status-panel", StatusPanel)
            status_panel.update_models(
                self.planner_model or "default",
                self.executor_model or "default"
            )

        # Start elapsed timer (updates every second)
        self._timer = self.set_interval(1.0, self._update_elapsed)

        # Start workflow in worker thread
        if self.feature or self.session_id:
            self._start_workflow()

    def _start_workflow(self) -> None:
        """Start the orchestrator workflow in a worker thread."""
        # Start the timer
        status_panel = self.query_one("#status-panel", StatusPanel)
        status_panel.start_timer()

        self._worker = self.run_worker(
            self._run_orchestrator,
            thread=True,
            name="orchestrator",
        )

    def _run_orchestrator(self) -> None:
        """Run the orchestrator (called in worker thread - must be sync)."""
        from ..engine import Orchestrator

        try:
            # Create orchestrator with TUI adapters
            self._orchestrator = Orchestrator(
                feature_description=self.feature,
                db_path=self.db_path,
                plan_path=self.plan_path,
                session_id=self.session_id,
                on_chunk=self._adapter.on_chunk,
                on_state_change=self._adapter.on_state_change,
                on_output=self._adapter.on_output,
                input_provider=self._input_provider,
                planner_model=self.planner_model,
                executor_model=self.executor_model,
                show_activity=False,  # TUI handles display
            )

            # Notify TUI with model info
            self._adapter.notify_models_set(
                self._orchestrator.planner_model or "default",
                self._orchestrator.executor_model or "default"
            )

            # Notify TUI
            self._adapter.notify_workflow_started(
                self._orchestrator.session_id,
                self.feature
            )

            # Run the workflow
            self._orchestrator.start()

            # Notify completion
            self._adapter.notify_workflow_completed(
                self._orchestrator.session_id,
                success=True,
                message="Workflow completed successfully"
            )

        except Exception as e:
            self._adapter.notify_workflow_error(str(e))

    def _update_elapsed(self) -> None:
        """Update the elapsed time display."""
        try:
            status_panel = self.query_one("#status-panel", StatusPanel)
            status_panel.update_elapsed()
        except Exception:
            pass

    # Message handlers

    def on_chunk_received(self, message: messages.ChunkReceived) -> None:
        """Handle chunk received from agent."""
        output = self.query_one("#agent-output", AgentOutput)
        output.write_chunk(message.chunk, message.agent)

        # Estimate tokens from chunk (rough approximation)
        status_panel = self.query_one("#status-panel", StatusPanel)
        # Estimate ~4 chars per token
        estimated_tokens = max(1, len(message.chunk) // 4)
        status_panel.add_tokens(estimated_tokens)

    def on_state_changed(self, message: messages.StateChanged) -> None:
        """Handle state change."""
        state = message.state
        status_panel = self.query_one("#status-panel", StatusPanel)
        log_panel = self.query_one("#log-panel", LogPanel)
        milestone_list = self.query_one("#milestone-list", MilestoneList)

        # Update status panel
        phase = getattr(state, 'phase', '—')
        status = getattr(state, 'status', '—')
        status_panel.update_phase(phase, status)

        if self._orchestrator:
            status_panel.update_session(self._orchestrator.session_id)

        # Increment API calls on state change (rough proxy)
        status_panel.increment_api_calls()

        # Log phase change
        if message.previous_phase and message.previous_phase != phase:
            log_panel.log_phase_change(phase.upper())

        # Update milestone progress
        current_milestone = getattr(state, 'current_milestone', 0)
        total_milestones = getattr(state, 'total_milestones', 0)

        if total_milestones > 0 and current_milestone > 0:
            milestone_list.set_current_milestone(current_milestone)

    def on_output_received(self, message: messages.OutputReceived) -> None:
        """Handle general output message."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log(message.message, message.level)

    def on_input_requested(self, message: messages.InputRequested) -> None:
        """Handle input request - show input modal."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_warning(f"Input requested: {message.prompt_text}")
        # Push the input modal to get user input
        self.push_screen(InputModal(message.prompt_text, self._input_provider))

    def on_workflow_started(self, message: messages.WorkflowStarted) -> None:
        """Handle workflow started."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_success(f"Workflow started: {message.session_id[:8]}")

        status_panel = self.query_one("#status-panel", StatusPanel)
        status_panel.update_phase("DISCOVERY", "ACTIVE")
        status_panel.update_session(message.session_id)

    def on_workflow_completed(self, message: messages.WorkflowCompleted) -> None:
        """Handle workflow completed."""
        log_panel = self.query_one("#log-panel", LogPanel)
        status_panel = self.query_one("#status-panel", StatusPanel)

        if message.success:
            log_panel.log_success("Workflow completed successfully!")
            status_panel.update_phase("COMPLETED", "COMPLETED")
        else:
            log_panel.log_error(f"Workflow failed: {message.message}")
            status_panel.update_phase("COMPLETED", "FAILED")

    def on_workflow_error(self, message: messages.WorkflowError) -> None:
        """Handle workflow error."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_error(f"Error: {message.error}")

    def on_milestone_updated(self, message: messages.MilestoneUpdated) -> None:
        """Handle milestone status update."""
        milestone_list = self.query_one("#milestone-list", MilestoneList)
        milestone_list.update_milestone(message.milestone_id, message.status, message.title)

        log_panel = self.query_one("#log-panel", LogPanel)
        if message.status == "active":
            log_panel.log_milestone_start(message.milestone_id, message.title)
        elif message.status == "completed":
            log_panel.log_milestone_complete(message.milestone_id)

    def on_milestones_loaded(self, message: messages.MilestonesLoaded) -> None:
        """Handle milestones loaded from plan."""
        milestone_list = self.query_one("#milestone-list", MilestoneList)
        milestone_list.set_milestones(message.milestones)

        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_info(f"Loaded {len(message.milestones)} milestones")

    def on_models_set(self, message: messages.ModelsSet) -> None:
        """Handle model configuration."""
        status_panel = self.query_one("#status-panel", StatusPanel)
        status_panel.update_models(message.planner_model, message.executor_model)

    def on_stats_updated(self, message: messages.StatsUpdated) -> None:
        """Handle stats update."""
        status_panel = self.query_one("#status-panel", StatusPanel)
        if message.api_calls is not None:
            status_panel.api_calls = message.api_calls
        if message.tokens is not None:
            status_panel.token_count = message.tokens

    # Actions

    def action_quit(self) -> None:
        """Quit the application."""
        if self._timer:
            self._timer.stop()
        if self._orchestrator:
            self._orchestrator._cleanup()
        self.exit()

    def action_show_help(self) -> None:
        """Show help screen."""
        # TODO: Implement help screen in Phase 6
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_info("Help: q=quit, l=toggle logs, m=toggle milestones, ?=help")

    def action_toggle_logs(self) -> None:
        """Toggle log panel visibility."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.display = not log_panel.display

    def action_toggle_milestones(self) -> None:
        """Toggle milestones panel visibility."""
        milestone_list = self.query_one("#milestone-list", MilestoneList)
        milestone_list.display = not milestone_list.display

    def action_show_status(self) -> None:
        """Show detailed status."""
        log_panel = self.query_one("#log-panel", LogPanel)
        status_panel = self.query_one("#status-panel", StatusPanel)
        milestone_list = self.query_one("#milestone-list", MilestoneList)

        log_panel.log_info("--- Status ---")
        log_panel.log_info(f"Phase: {status_panel.phase}")
        log_panel.log_info(f"Session: {status_panel.session_id}")
        log_panel.log_info(f"API Calls: {status_panel.api_calls}")
        log_panel.log_info(f"Tokens: {status_panel.token_count}")
        log_panel.log_info(f"Milestones: {milestone_list.completed_count}/{milestone_list.total_count}")

    def action_back(self) -> None:
        """Handle escape - go back or cancel."""
        pass
