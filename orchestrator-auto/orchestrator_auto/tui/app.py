"""
Main TUI application for orchestrator-auto.

Provides a rich text user interface for running workflows.
"""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, RichLog, Label
from textual.worker import Worker, WorkerState
from typing import Optional, TYPE_CHECKING

from . import messages
from .adapter import TUIOutputAdapter, TUIInputProvider
from .bindings import GLOBAL_BINDINGS, SESSION_BINDINGS

if TYPE_CHECKING:
    from ..engine import Orchestrator


class StatusPanel(Static):
    """Panel showing current workflow status."""

    DEFAULT_CSS = """
    StatusPanel {
        height: 6;
        border: solid green;
        padding: 0 1;
    }

    StatusPanel .label {
        color: $text-muted;
    }

    StatusPanel .value {
        color: $text;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.phase = "—"
        self.status = "—"
        self.session_id = "—"

    def compose(self) -> ComposeResult:
        yield Label("[b]STATUS[/b]")
        yield Label(f"Phase: {self.phase}", id="phase")
        yield Label(f"Status: {self.status}", id="status")
        yield Label(f"Session: {self.session_id}", id="session")

    def update_status(self, phase: str, status: str, session_id: str = "") -> None:
        """Update the displayed status."""
        self.phase = phase
        self.status = status
        if session_id:
            self.session_id = session_id[:8]

        if self.is_mounted:
            self.query_one("#phase", Label).update(f"Phase: {self.phase}")
            self.query_one("#status", Label).update(f"Status: {self.status}")
            self.query_one("#session", Label).update(f"Session: {self.session_id}")


class AgentOutput(RichLog):
    """Panel showing streaming agent output."""

    DEFAULT_CSS = """
    AgentOutput {
        border: solid $primary;
        height: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(highlight=True, markup=True, wrap=True, **kwargs)


class LogPanel(RichLog):
    """Panel showing orchestrator log messages."""

    DEFAULT_CSS = """
    LogPanel {
        border: solid $secondary;
        height: 8;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(highlight=True, markup=True, wrap=True, **kwargs)


class OrchestratorTUI(App):
    """
    Text User Interface for orchestrator-auto.

    Provides a rich interface for running workflows with:
    - Real-time streaming output
    - Status panel showing phase/status
    - Log panel for orchestrator messages
    - Support for input prompts via modal

    Usage:
        app = OrchestratorTUI(feature="My feature")
        app.run()
    """

    TITLE = "Orchestrator Auto"
    SUB_TITLE = "AI Workflow Manager"

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 3;
        grid-columns: 1fr 2fr;
        grid-rows: auto 1fr auto;
    }

    #status-panel {
        column-span: 1;
        row-span: 1;
    }

    #agent-output {
        column-span: 2;
        row-span: 1;
    }

    #log-panel {
        column-span: 2;
        row-span: 1;
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

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        yield Header()
        yield StatusPanel(id="status-panel")
        yield AgentOutput(id="agent-output")
        yield LogPanel(id="log-panel")
        yield Footer()

    def on_mount(self) -> None:
        """Handle app mount - start the workflow."""
        # Log startup
        log_panel = self.query_one(LogPanel)
        log_panel.write(f"[bold cyan]Orchestrator TUI Started[/bold cyan]")
        log_panel.write(f"Feature: {self.feature}")

        # Start workflow in worker thread
        if self.feature or self.session_id:
            self._start_workflow()

    def _start_workflow(self) -> None:
        """Start the orchestrator workflow in a worker thread."""
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

    # Message handlers

    def on_chunk_received(self, message: messages.ChunkReceived) -> None:
        """Handle chunk received from agent."""
        output = self.query_one(AgentOutput)
        output.write(message.chunk, scroll_end=True)

    def on_state_changed(self, message: messages.StateChanged) -> None:
        """Handle state change."""
        state = message.state
        status_panel = self.query_one(StatusPanel)
        status_panel.update_status(
            phase=getattr(state, 'phase', '—'),
            status=getattr(state, 'status', '—'),
            session_id=getattr(self._orchestrator, 'session_id', '') if self._orchestrator else ''
        )

    def on_output_received(self, message: messages.OutputReceived) -> None:
        """Handle general output message."""
        log_panel = self.query_one(LogPanel)
        if message.level == "error":
            log_panel.write(f"[red]{message.message}[/red]")
        elif message.level == "warning":
            log_panel.write(f"[yellow]{message.message}[/yellow]")
        else:
            log_panel.write(message.message)

    def on_input_requested(self, message: messages.InputRequested) -> None:
        """Handle input request - show input modal."""
        # For now, just log that input is needed
        # TODO: Implement input modal in Phase 3
        log_panel = self.query_one(LogPanel)
        log_panel.write(f"[yellow]Input requested: {message.prompt_text}[/yellow]")

    def on_workflow_started(self, message: messages.WorkflowStarted) -> None:
        """Handle workflow started."""
        log_panel = self.query_one(LogPanel)
        log_panel.write(f"[green]Workflow started: {message.session_id[:8]}[/green]")

        status_panel = self.query_one(StatusPanel)
        status_panel.update_status("DISCOVERY", "ACTIVE", message.session_id)

    def on_workflow_completed(self, message: messages.WorkflowCompleted) -> None:
        """Handle workflow completed."""
        log_panel = self.query_one(LogPanel)
        if message.success:
            log_panel.write(f"[green bold]Workflow completed successfully![/green bold]")
        else:
            log_panel.write(f"[red]Workflow failed: {message.message}[/red]")

    def on_workflow_error(self, message: messages.WorkflowError) -> None:
        """Handle workflow error."""
        log_panel = self.query_one(LogPanel)
        log_panel.write(f"[red bold]Error: {message.error}[/red bold]")

    # Actions

    def action_quit(self) -> None:
        """Quit the application."""
        if self._orchestrator:
            self._orchestrator._cleanup()
        self.exit()

    def action_show_help(self) -> None:
        """Show help screen."""
        # TODO: Implement help screen in Phase 6
        log_panel = self.query_one(LogPanel)
        log_panel.write("[cyan]Help: Press q to quit, ? for help[/cyan]")

    def action_toggle_logs(self) -> None:
        """Toggle log panel visibility."""
        log_panel = self.query_one(LogPanel)
        log_panel.display = not log_panel.display

    def action_toggle_milestones(self) -> None:
        """Toggle milestones panel."""
        # TODO: Implement in Phase 3
        pass

    def action_show_status(self) -> None:
        """Show detailed status."""
        # TODO: Implement in Phase 3
        pass

    def action_back(self) -> None:
        """Handle escape - go back or cancel."""
        pass
