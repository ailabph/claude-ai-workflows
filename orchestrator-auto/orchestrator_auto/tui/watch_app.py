"""
Watch mode TUI application for orchestrator-auto.

Provides a TUI for directory-based plan watching and execution.
"""

from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Header, Footer
from textual.worker import Worker
from typing import Optional, Dict, Any, TYPE_CHECKING

from . import messages
from .adapter import TUIOutputAdapter, TUIInputProvider
from .bindings import GLOBAL_BINDINGS, WATCH_BINDINGS
from .widgets import (
    StatusPanel,
    MilestoneList,
    AgentOutput,
    LogPanel,
    InputModal,
    WatchPanel,
)
from .screens import HelpScreen
from ..config import get_project_identity

if TYPE_CHECKING:
    from ..controllers.watch_controller import WatchController, WatchEvent


class WatchTUI(App):
    """
    Text User Interface for watch mode.

    Shows:
    - Watch panel with directory info and file status
    - Current session details (status, milestones, output)
    - Log panel for orchestrator messages

    Usage:
        app = WatchTUI(plans_dir="/path/to/plans")
        app.run()

    Known Limitations:
        - Blocker responses must be provided via CLI (`orchestrator respond ...`).
          The engine's blocker handling transitions to paused state and the
          WatchController polls for external resume. A future enhancement could
          add in-TUI blocker response via the InputModal and resume API.
    """

    TITLE = "Orchestrator Auto - Watch Mode"
    SUB_TITLE = "Directory Watcher"
    CSS_PATH = "styles/theme.tcss"

    CSS = """
    Screen {
        layout: grid;
        grid-size: 3 3;
        grid-columns: 1fr 1fr 2fr;
        grid-rows: auto 1fr auto;
    }

    #watch-panel {
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

    BINDINGS = GLOBAL_BINDINGS + WATCH_BINDINGS

    def __init__(
        self,
        plans_dir: str,
        db_path: Optional[str] = None,
        poll_interval: int = 2,
        auto_convert: bool = True,
        planner_model: Optional[str] = None,
        executor_model: Optional[str] = None,
        auto_commit: bool = False,
        smart_commit: Optional[bool] = None,
        **kwargs,
    ) -> None:
        """
        Initialize the Watch TUI.

        Args:
            plans_dir: Directory to watch for plan files
            db_path: Optional database path
            poll_interval: Seconds between directory polls
            auto_convert: Whether to auto-convert invalid plans
            planner_model: Model for planner agent
            executor_model: Model for executor agent
            auto_commit: Whether to auto-commit on completion
            smart_commit: Whether to use AI-generated commit messages
        """
        super().__init__(**kwargs)
        self.plans_dir = Path(plans_dir).resolve()
        self.db_path = db_path
        self.poll_interval = poll_interval
        self.auto_convert = auto_convert
        self.planner_model = planner_model
        self.executor_model = executor_model
        self.auto_commit = auto_commit
        self.smart_commit = smart_commit

        # Get project identity for DB operations
        self.project_id, _ = get_project_identity()

        # Create adapters
        self._adapter = TUIOutputAdapter(self)
        self._input_provider = TUIInputProvider(self._adapter)

        # Controller (created when watch starts)
        self._controller: Optional["WatchController"] = None
        self._worker: Optional[Worker] = None
        self._timer: Optional[Timer] = None

        # Track counts for UI updates
        self._completed: int = 0
        self._failed: int = 0
        self._paused: int = 0

        # Track currently processing file to handle renames
        self._current_processing_file: Optional[str] = None

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        yield Header()
        with Horizontal():
            yield WatchPanel(id="watch-panel")
            with Vertical():
                yield StatusPanel(id="status-panel")
                yield MilestoneList(id="milestone-list")
            yield AgentOutput(id="agent-output")
        yield LogPanel(id="log-panel")
        yield Footer()

    def on_mount(self) -> None:
        """Handle app mount - start the watch."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_info("Watch Mode TUI Started")
        log_panel.log_info(f"Watching: {self.plans_dir}")

        # Set initial models if provided
        if self.planner_model or self.executor_model:
            status_panel = self.query_one("#status-panel", StatusPanel)
            status_panel.update_models(
                self.planner_model or "default",
                self.executor_model or "default"
            )

        # Start elapsed timer
        self._timer = self.set_interval(1.0, self._update_elapsed)

        # Start watch in worker thread
        self._start_watch()

    def _start_watch(self) -> None:
        """Start the watch controller in a worker thread."""
        status_panel = self.query_one("#status-panel", StatusPanel)
        status_panel.start_timer()

        self._worker = self.run_worker(
            self._run_watch,
            thread=True,
            name="watch-controller",
        )

    def _run_watch(self) -> None:
        """Run the watch controller (called in worker thread - must be sync)."""
        from ..controllers.watch_controller import WatchController
        from .. import db

        try:
            # Initialize database
            db.init_db(self.db_path)

            # Create controller with TUI adapters
            self._controller = WatchController(
                plans_dir=self.plans_dir,
                db_path=self.db_path,
                poll_interval=self.poll_interval,
                auto_convert=self.auto_convert,
                on_event=self._on_watch_event,
                on_output=self._adapter.on_output,
                on_chunk=self._adapter.on_chunk,
                on_state_change=self._adapter.on_state_change,
                input_provider=self._input_provider,
                planner_model=self.planner_model,
                executor_model=self.executor_model,
                auto_commit=self.auto_commit,
                smart_commit=self.smart_commit,
                show_activity=False,  # TUI handles display
            )

            # Run the watch loop
            self._controller.run()

        except Exception as e:
            self._adapter.notify_workflow_error(str(e))

    def _on_watch_event(self, event: "WatchEvent", data: Dict[str, Any]) -> None:
        """
        Handle watch controller events.

        Thread-safe: posts messages to TUI main thread.
        """
        from ..controllers.watch_controller import WatchEvent

        if event == WatchEvent.STARTED:
            self.call_from_thread(
                self.post_message,
                messages.WatchStarted(
                    directory=data.get("directory", ""),
                    poll_interval=data.get("poll_interval", 2),
                    auto_convert=data.get("auto_convert", True),
                )
            )

        elif event == WatchEvent.FILE_FOUND:
            filename = data.get("plan_path", "")
            self._current_processing_file = filename
            self.call_from_thread(
                self.post_message,
                messages.WatchFileUpdated(
                    filename=filename,
                    status="processing",
                )
            )
            # Reset UI for new file processing
            self.call_from_thread(self._reset_for_new_file, filename)

        elif event == WatchEvent.FILE_COMPLETED:
            self._completed += 1
            original = self._current_processing_file
            self._current_processing_file = None
            self.call_from_thread(
                self.post_message,
                messages.WatchFileUpdated(
                    filename=data.get("new_path", ""),
                    status="completed",
                    original_filename=original,
                )
            )
            self.call_from_thread(self._update_watch_counts)

        elif event == WatchEvent.FILE_FAILED:
            self._failed += 1
            original = self._current_processing_file
            self._current_processing_file = None
            self.call_from_thread(
                self.post_message,
                messages.WatchFileUpdated(
                    filename=data.get("new_path", ""),
                    status="failed",
                    error=data.get("error"),
                    original_filename=original,
                )
            )
            self.call_from_thread(self._update_watch_counts)

        elif event == WatchEvent.FILE_PAUSED:
            self._paused += 1
            original = self._current_processing_file
            self._current_processing_file = None
            self.call_from_thread(
                self.post_message,
                messages.WatchPaused(
                    session_id=data.get("session_id", ""),
                    plan_path=data.get("new_path", ""),
                )
            )
            self.call_from_thread(
                self.post_message,
                messages.WatchFileUpdated(
                    filename=data.get("new_path", ""),
                    status="paused",
                    original_filename=original,
                )
            )
            self.call_from_thread(self._update_watch_counts)

        elif event == WatchEvent.FILE_SKIPPED:
            # Skipped files don't proceed to terminal rename, clear tracker
            self._current_processing_file = None
            self.call_from_thread(
                self.post_message,
                messages.WatchFileUpdated(
                    filename=data.get("plan_path", ""),
                    status="skipped",
                    error=data.get("reason"),
                )
            )

        elif event == WatchEvent.FILE_CONVERTED:
            # Conversion is a rename: update existing entry, track new filename
            original = data.get("original", "")
            converted = data.get("converted", "")
            # Update tracker to converted filename (terminal rename will use this)
            if self._current_processing_file == original:
                self._current_processing_file = converted
            self.call_from_thread(
                self.post_message,
                messages.WatchFileUpdated(
                    filename=converted,
                    status="converted",
                    original_filename=original,
                )
            )

        elif event == WatchEvent.CONVERSION_FAILED:
            # Conversion failed, file is quarantined, clear tracker
            self._current_processing_file = None
            self.call_from_thread(
                self.post_message,
                messages.WatchFileUpdated(
                    filename=data.get("plan_path", ""),
                    status="failed",
                    error="Conversion failed",
                )
            )

        elif event == WatchEvent.RESUMED_COMPLETED:
            self._completed += 1
            self._paused -= 1
            self.call_from_thread(
                self.post_message,
                messages.WatchFileUpdated(
                    filename=data.get("new_path", ""),
                    status="completed",
                )
            )
            self.call_from_thread(self._update_watch_counts)
            # Clear paused state
            self.call_from_thread(self._set_watch_running)

        elif event == WatchEvent.RESUMED_FAILED:
            self._failed += 1
            self._paused -= 1
            self.call_from_thread(
                self.post_message,
                messages.WatchFileUpdated(
                    filename=data.get("new_path", ""),
                    status="failed",
                )
            )
            self.call_from_thread(self._update_watch_counts)
            # Clear paused state
            self.call_from_thread(self._set_watch_running)

        elif event == WatchEvent.STOPPED:
            self.call_from_thread(
                self.post_message,
                messages.WatchStopped(
                    completed=data.get("completed", 0),
                    failed=data.get("failed", 0),
                    paused=data.get("paused", 0),
                )
            )

        elif event in (WatchEvent.INFO, WatchEvent.WARNING):
            level = "warning" if event == WatchEvent.WARNING else "info"
            self.call_from_thread(
                self.post_message,
                messages.OutputReceived(
                    message=data.get("message", ""),
                    level=level,
                )
            )

    def _reset_for_new_file(self, filename: str) -> None:
        """Reset UI elements for processing a new file."""
        try:
            status_panel = self.query_one("#status-panel", StatusPanel)
            status_panel.update_phase("DISCOVERY", "ACTIVE")

            milestone_list = self.query_one("#milestone-list", MilestoneList)
            milestone_list.set_milestones([])

            agent_output = self.query_one("#agent-output", AgentOutput)
            agent_output.clear_output()
            agent_output.write_message(f"Processing: {filename[:50]}...", "bold")
        except Exception:
            pass

    def _update_watch_counts(self) -> None:
        """Update the watch panel counts."""
        try:
            watch_panel = self.query_one("#watch-panel", WatchPanel)
            watch_panel.update_counts(self._completed, self._failed, self._paused)
        except Exception:
            pass

    def _set_watch_running(self) -> None:
        """Set watch panel to running state."""
        try:
            watch_panel = self.query_one("#watch-panel", WatchPanel)
            watch_panel.set_running()
        except Exception:
            pass

    def _update_elapsed(self) -> None:
        """Update the elapsed time display."""
        try:
            status_panel = self.query_one("#status-panel", StatusPanel)
            status_panel.update_elapsed()
        except Exception:
            pass

    # Message handlers

    def on_watch_started(self, message: messages.WatchStarted) -> None:
        """Handle watch started."""
        watch_panel = self.query_one("#watch-panel", WatchPanel)
        watch_panel.set_config(
            message.directory,
            message.poll_interval,
            message.auto_convert,
        )

        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_success(f"Watching {message.directory}")

    def on_watch_stopped(self, message: messages.WatchStopped) -> None:
        """Handle watch stopped."""
        watch_panel = self.query_one("#watch-panel", WatchPanel)
        watch_panel.set_stopped()
        watch_panel.update_counts(message.completed, message.failed, message.paused)

        status_panel = self.query_one("#status-panel", StatusPanel)
        status_panel.update_phase("STOPPED", "COMPLETED")

        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_success(
            f"Watch stopped: {message.completed} completed, "
            f"{message.failed} failed, {message.paused} paused"
        )

    def on_watch_paused(self, message: messages.WatchPaused) -> None:
        """Handle watch paused on blocker."""
        watch_panel = self.query_one("#watch-panel", WatchPanel)
        watch_panel.set_paused(message.session_id, message.plan_path)

        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_warning(f"Paused on blocker: {message.plan_path}")

    def on_watch_file_updated(self, message: messages.WatchFileUpdated) -> None:
        """Handle file status update."""
        watch_panel = self.query_one("#watch-panel", WatchPanel)
        watch_panel.update_file(
            message.filename,
            message.status,
            message.error,
            message.original_filename,
        )

        log_panel = self.query_one("#log-panel", LogPanel)
        if message.status == "processing":
            log_panel.log_info(f"Found: {message.filename}")
        elif message.status == "completed":
            log_panel.log_success(f"Completed: {message.filename}")
        elif message.status == "failed":
            error_msg = f": {message.error}" if message.error else ""
            log_panel.log_error(f"Failed: {message.filename}{error_msg}")
        elif message.status == "paused":
            log_panel.log_warning(f"Paused: {message.filename}")
        elif message.status == "skipped":
            log_panel.log_warning(f"Skipped: {message.filename}")
        elif message.status == "converted":
            log_panel.log_info(f"Converted: {message.filename}")

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

        # Update session_id from state
        session_id = getattr(state, 'session_id', None)
        if session_id:
            status_panel.update_session(session_id)

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

    def on_workflow_error(self, message: messages.WorkflowError) -> None:
        """Handle workflow error."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_error(f"Error: {message.error}")

    # Actions

    def action_quit(self) -> None:
        """Quit the application."""
        if self._controller:
            self._controller.stop()
        if self._timer:
            self._timer.stop()
        self.exit()

    def action_show_help(self) -> None:
        """Show help screen."""
        self.push_screen(HelpScreen(mode="watch"))

    def action_refresh(self) -> None:
        """Refresh the display."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_info("Refreshed")

    def action_clear(self) -> None:
        """Clear the file list."""
        watch_panel = self.query_one("#watch-panel", WatchPanel)
        watch_panel.clear_files()
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_info("Cleared file list")

    def action_back(self) -> None:
        """Handle escape."""
        pass
