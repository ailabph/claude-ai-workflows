"""
Queue mode TUI application for orchestrator-auto.

Provides a TUI for running multiple workflows sequentially.
"""

from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Header, Footer
from textual.worker import Worker
from typing import Optional, List, Dict, Any, TYPE_CHECKING

from . import messages
from .adapter import TUIOutputAdapter, TUIInputProvider
from .bindings import GLOBAL_BINDINGS, QUEUE_BINDINGS
from .widgets import (
    StatusPanel,
    MilestoneList,
    AgentOutput,
    LogPanel,
    InputModal,
    QueuePanel,
)

if TYPE_CHECKING:
    from ..controllers.queue_controller import QueueController, QueueEvent


class QueueTUI(App):
    """
    Text User Interface for queue mode.

    Shows:
    - Queue panel with all items and their status
    - Current session details (status, milestones, output)
    - Log panel for orchestrator messages

    Usage:
        app = QueueTUI(plan_paths=["plan1.md", "plan2.md"])
        app.run()
    """

    TITLE = "Orchestrator Auto - Queue Mode"
    SUB_TITLE = "Sequential Workflow Runner"
    CSS_PATH = "styles/theme.tcss"

    CSS = """
    Screen {
        layout: grid;
        grid-size: 3 3;
        grid-columns: 1fr 1fr 2fr;
        grid-rows: auto 1fr auto;
    }

    #queue-panel {
        column-span: 1;
        row-span: 2;
    }

    #status-panel {
        column-span: 1;
        row-span: 1;
    }

    #milestone-list {
        column-span: 1;
        row-span: 1;
    }

    #agent-output {
        column-span: 1;
        row-span: 2;
    }

    #log-panel {
        column-span: 3;
        height: 8;
    }

    Header {
        dock: top;
    }

    Footer {
        dock: bottom;
    }
    """

    BINDINGS = GLOBAL_BINDINGS + QUEUE_BINDINGS

    def __init__(
        self,
        plan_paths: Optional[List[str]] = None,
        project_id: Optional[str] = None,
        db_path: Optional[str] = None,
        planner_model: Optional[str] = None,
        executor_model: Optional[str] = None,
        auto_commit: bool = False,
        smart_commit: Optional[bool] = None,
        no_rename: bool = False,
        **kwargs,
    ) -> None:
        """
        Initialize the Queue TUI.

        Args:
            plan_paths: List of plan file paths to queue
            project_id: Project identifier
            db_path: Optional database path
            planner_model: Model for planner agent
            executor_model: Model for executor agent
            auto_commit: Whether to auto-commit on completion
            smart_commit: Whether to use AI-generated commit messages
            no_rename: Whether to skip plan file renaming
        """
        super().__init__(**kwargs)
        self.plan_paths = plan_paths or []
        self.project_id = project_id or str(Path.cwd())
        self.db_path = db_path
        self.planner_model = planner_model
        self.executor_model = executor_model
        self.auto_commit = auto_commit
        self.smart_commit = smart_commit
        self.no_rename = no_rename

        # Create adapters
        self._adapter = TUIOutputAdapter(self)
        self._input_provider = TUIInputProvider(self._adapter)

        # Controller (created when queue starts)
        self._controller: Optional["QueueController"] = None
        self._worker: Optional[Worker] = None
        self._timer: Optional[Timer] = None

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        yield Header()
        with Horizontal():
            yield QueuePanel(id="queue-panel")
            with Vertical():
                yield StatusPanel(id="status-panel")
                yield MilestoneList(id="milestone-list")
            yield AgentOutput(id="agent-output")
        yield LogPanel(id="log-panel")
        yield Footer()

    def on_mount(self) -> None:
        """Handle app mount - start the queue."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_info("Queue Mode TUI Started")
        log_panel.log_info(f"Plans: {len(self.plan_paths)}")

        # Set initial models if provided
        if self.planner_model or self.executor_model:
            status_panel = self.query_one("#status-panel", StatusPanel)
            status_panel.update_models(
                self.planner_model or "default",
                self.executor_model or "default"
            )

        # Start elapsed timer
        self._timer = self.set_interval(1.0, self._update_elapsed)

        # Start queue in worker thread
        if self.plan_paths:
            self._start_queue()

    def _start_queue(self) -> None:
        """Start the queue controller in a worker thread."""
        status_panel = self.query_one("#status-panel", StatusPanel)
        status_panel.start_timer()

        self._worker = self.run_worker(
            self._run_queue,
            thread=True,
            name="queue-controller",
        )

    def _run_queue(self) -> None:
        """Run the queue controller (called in worker thread - must be sync)."""
        from ..controllers.queue_controller import QueueController, QueueEvent
        from .. import db

        try:
            # Enqueue plan files
            for plan_path in self.plan_paths:
                path = Path(plan_path)
                if path.exists():
                    # Read feature description from plan
                    content = path.read_text()
                    feature = content[:100].strip().replace("\n", " ")
                    db.enqueue_plan(
                        str(path.resolve()),
                        feature,
                        self.project_id,
                        self.db_path
                    )

            # Create controller with TUI adapters
            self._controller = QueueController(
                project_id=self.project_id,
                db_path=self.db_path,
                on_event=self._on_queue_event,
                on_output=self._adapter.on_output,
                on_chunk=self._adapter.on_chunk,
                on_state_change=self._adapter.on_state_change,
                input_provider=self._input_provider,
                planner_model=self.planner_model,
                executor_model=self.executor_model,
                auto_commit=self.auto_commit,
                smart_commit=self.smart_commit,
                show_activity=False,  # TUI handles display
                no_rename=self.no_rename,
            )

            # Run the queue
            self._controller.run()

        except Exception as e:
            self._adapter.notify_workflow_error(str(e))

    def _on_queue_event(self, event: "QueueEvent", data: Dict[str, Any]) -> None:
        """
        Handle queue controller events.

        Thread-safe: posts messages to TUI main thread.
        """
        from ..controllers.queue_controller import QueueEvent

        if event == QueueEvent.STARTED:
            items = data.get("items", [])
            self.call_from_thread(
                self.post_message,
                messages.QueueStarted(
                    total_items=len(items),
                    items=[
                        {
                            "position": i.get("position", idx + 1),
                            "feature": i.get("feature_description", ""),
                            "status": "pending",
                        }
                        for idx, i in enumerate(items)
                    ]
                )
            )

        elif event == QueueEvent.ITEM_STARTED:
            self.call_from_thread(
                self.post_message,
                messages.QueueItemUpdated(
                    position=data.get("position", 0),
                    status="running",
                    feature=data.get("feature_description", ""),
                    session_id=data.get("session_id"),
                )
            )
            # Also notify workflow started for status panel
            session_id = data.get("session_id", "")
            if session_id:
                self.call_from_thread(
                    self.post_message,
                    messages.WorkflowStarted(
                        session_id=session_id,
                        feature=data.get("feature_description", "")
                    )
                )

        elif event == QueueEvent.ITEM_COMPLETED:
            self.call_from_thread(
                self.post_message,
                messages.QueueItemUpdated(
                    position=data.get("position", 0),
                    status="completed",
                    feature=data.get("feature_description", ""),
                    session_id=data.get("session_id"),
                )
            )

        elif event == QueueEvent.ITEM_FAILED:
            self.call_from_thread(
                self.post_message,
                messages.QueueItemUpdated(
                    position=data.get("position", 0),
                    status="failed",
                    feature=data.get("feature_description", ""),
                    session_id=data.get("session_id"),
                    error=data.get("error"),
                )
            )

        elif event == QueueEvent.ITEM_PAUSED:
            self.call_from_thread(
                self.post_message,
                messages.QueueItemUpdated(
                    position=data.get("position", 0),
                    status="paused",
                    feature=data.get("feature_description", ""),
                    session_id=data.get("session_id"),
                )
            )

        elif event == QueueEvent.COMPLETED:
            self.call_from_thread(
                self.post_message,
                messages.QueueCompleted(
                    completed=data.get("completed", 0),
                    failed=data.get("failed", 0),
                    paused=data.get("paused", 0),
                    total=data.get("total", 0),
                )
            )

        elif event == QueueEvent.HALTED:
            self.call_from_thread(
                self.post_message,
                messages.QueueHalted(
                    reason=data.get("reason", "Unknown"),
                    position=data.get("position", 0),
                )
            )

        elif event in (QueueEvent.INFO, QueueEvent.WARNING):
            level = "warning" if event == QueueEvent.WARNING else "info"
            self.call_from_thread(
                self.post_message,
                messages.OutputReceived(
                    message=data.get("message", ""),
                    level=level,
                )
            )

    def _update_elapsed(self) -> None:
        """Update the elapsed time display."""
        try:
            status_panel = self.query_one("#status-panel", StatusPanel)
            status_panel.update_elapsed()
        except Exception:
            pass

    # Message handlers

    def on_queue_started(self, message: messages.QueueStarted) -> None:
        """Handle queue started."""
        queue_panel = self.query_one("#queue-panel", QueuePanel)
        queue_panel.set_items(message.items)

        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_success(f"Queue started with {message.total_items} items")

    def on_queue_item_updated(self, message: messages.QueueItemUpdated) -> None:
        """Handle queue item update."""
        queue_panel = self.query_one("#queue-panel", QueuePanel)
        queue_panel.update_item(
            message.position,
            message.status,
            message.session_id,
            message.error
        )

        log_panel = self.query_one("#log-panel", LogPanel)
        if message.status == "running":
            log_panel.log_info(f"Starting item {message.position}: {message.feature[:50]}...")
        elif message.status == "completed":
            log_panel.log_success(f"Item {message.position} completed")
        elif message.status == "failed":
            log_panel.log_error(f"Item {message.position} failed: {message.error or 'Unknown error'}")
        elif message.status == "paused":
            log_panel.log_warning(f"Item {message.position} paused (blocker)")

    def on_queue_completed(self, message: messages.QueueCompleted) -> None:
        """Handle queue completed."""
        log_panel = self.query_one("#log-panel", LogPanel)
        status_panel = self.query_one("#status-panel", StatusPanel)

        summary = f"Queue complete: {message.completed}/{message.total} completed"
        if message.failed > 0:
            summary += f", {message.failed} failed"
        if message.paused > 0:
            summary += f", {message.paused} paused"

        log_panel.log_success(summary)
        status_panel.update_phase("COMPLETED", "COMPLETED")

    def on_queue_halted(self, message: messages.QueueHalted) -> None:
        """Handle queue halted."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_error(f"Queue halted at item {message.position}: {message.reason}")

    def on_chunk_received(self, message: messages.ChunkReceived) -> None:
        """Handle chunk received from agent."""
        output = self.query_one("#agent-output", AgentOutput)
        output.write_chunk(message.chunk, message.agent)

        status_panel = self.query_one("#status-panel", StatusPanel)
        estimated_tokens = max(1, len(message.chunk) // 4)
        status_panel.add_tokens(estimated_tokens)

    def on_state_changed(self, message: messages.StateChanged) -> None:
        """Handle state change."""
        state = message.state
        status_panel = self.query_one("#status-panel", StatusPanel)
        log_panel = self.query_one("#log-panel", LogPanel)
        milestone_list = self.query_one("#milestone-list", MilestoneList)

        phase = getattr(state, 'phase', '—')
        status = getattr(state, 'status', '—')
        status_panel.update_phase(phase, status)

        status_panel.increment_api_calls()

        if message.previous_phase and message.previous_phase != phase:
            log_panel.log_phase_change(phase.upper())

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
        self.push_screen(InputModal(message.prompt_text, self._input_provider))

    def on_workflow_started(self, message: messages.WorkflowStarted) -> None:
        """Handle workflow started (for current queue item)."""
        status_panel = self.query_one("#status-panel", StatusPanel)
        status_panel.update_phase("DISCOVERY", "ACTIVE")
        status_panel.update_session(message.session_id)

        # Clear milestone list for new item
        milestone_list = self.query_one("#milestone-list", MilestoneList)
        milestone_list.set_milestones([])

        # Clear agent output for new item
        agent_output = self.query_one("#agent-output", AgentOutput)
        agent_output.clear_output()
        agent_output.write_message(f"Starting: {message.feature[:60]}...", "bold")

    def on_workflow_completed(self, message: messages.WorkflowCompleted) -> None:
        """Handle workflow completed."""
        # Status will be updated by queue item update
        pass

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

    def on_models_set(self, message: messages.ModelsSet) -> None:
        """Handle model configuration."""
        status_panel = self.query_one("#status-panel", StatusPanel)
        status_panel.update_models(message.planner_model, message.executor_model)

    # Actions

    def action_quit(self) -> None:
        """Quit the application."""
        if self._timer:
            self._timer.stop()
        self.exit()

    def action_show_help(self) -> None:
        """Show help screen."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_info("Help: q=quit, n=next, k=skip, r=refresh")

    def action_toggle_logs(self) -> None:
        """Toggle log panel visibility."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.display = not log_panel.display

    def action_next_item(self) -> None:
        """Advance to next queue item (placeholder)."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_info("Next item (not implemented - queue runs automatically)")

    def action_skip_item(self) -> None:
        """Skip current queue item (placeholder)."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_warning("Skip not implemented")

    def action_refresh(self) -> None:
        """Refresh the display."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_info("Refreshed")

    def action_back(self) -> None:
        """Handle escape."""
        pass
