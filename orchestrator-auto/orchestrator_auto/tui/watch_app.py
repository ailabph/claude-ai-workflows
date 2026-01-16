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
    GitStatusPanel,
)
from .screens import HelpScreen, GitDiffScreen
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
    #main-row {
        width: 100%;
        height: 1fr;
    }

    /* Left column: Watch + Milestones */
    #left-col {
        width: 1fr;
        min-width: 20;
        max-width: 25;
        height: 100%;
    }

    #watch-panel {
        height: auto;
    }

    #milestone-list {
        height: 1fr;
        min-height: 10;
    }

    /* Middle column: Status + Git */
    #middle-col {
        width: 1fr;
        min-width: 20;
        max-width: 25;
        height: 100%;
    }

    #status-panel {
        height: auto;
        max-height: 15;
    }

    #git-panel {
        height: 1fr;
        min-height: 10;
    }

    /* Right column: Agent outputs + Log */
    #right-col {
        width: 3fr;
        min-width: 60;
        height: 100%;
    }

    #output-row {
        height: 1fr;
        min-height: 20;
    }

    #planner-output {
        width: 1fr;
        min-width: 30;
    }

    #executor-output {
        width: 1fr;
        min-width: 30;
    }

    #log-panel {
        height: 12;
        min-height: 8;
    }
    """

    BINDINGS = GLOBAL_BINDINGS + WATCH_BINDINGS

    def __init__(
        self,
        plans_dir: str,
        db_path: Optional[str] = None,
        poll_interval: int = 2,
        auto_convert: bool = False,
        planner_model: Optional[str] = None,
        executor_model: Optional[str] = None,
        auto_commit: bool = False,
        smart_commit: Optional[bool] = None,
        telegram: Optional[bool] = None,
        mcp_config: Optional[str] = None,
        headless: bool = False,
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
            telegram: Whether to enable Telegram notifications
            mcp_config: Path to MCP configuration file
            headless: Whether to run browsers in headless mode
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
        self.telegram = telegram
        self.mcp_config = mcp_config
        self.headless = headless

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

        # Track paused session for in-TUI response
        self._paused_session_id: Optional[str] = None

        # Store telegram notifier for resume parity
        self._telegram_notifier = None

    def compose(self) -> ComposeResult:
        """Compose the TUI layout with containers."""
        yield Header()
        with Horizontal(id="main-row"):
            with Vertical(id="left-col"):
                yield WatchPanel(id="watch-panel")
                yield MilestoneList(id="milestone-list")
            with Vertical(id="middle-col"):
                yield StatusPanel(id="status-panel")
                yield GitStatusPanel(id="git-panel")
            with Vertical(id="right-col"):
                with Horizontal(id="output-row"):
                    yield AgentOutput(
                        id="planner-output",
                        agent_filter="planner",
                        header_title="PLANNER"
                    )
                    yield AgentOutput(
                        id="executor-output",
                        agent_filter="executor",
                        header_title="EXECUTOR"
                    )
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

        # Start git status refresh timer (every 5 seconds)
        self.set_interval(5.0, self._refresh_git_status)
        # Do initial git status refresh
        self._refresh_git_status()

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

            # Create telegram notifier using shared function (same as CLI)
            telegram_notifier = None
            if self.telegram:
                try:
                    from ..telegram import create_notifier_from_config
                    from ..config import get_telegram_config
                    telegram_config = get_telegram_config()
                    telegram_notifier = create_notifier_from_config(
                        telegram_config, cli_enabled=self.telegram
                    )
                except ImportError:
                    # Telegram requires httpx - log to panel if available
                    pass
                except Exception:
                    # Configuration error - continue without telegram
                    pass

            # Store for use in _respond_worker()
            self._telegram_notifier = telegram_notifier

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
                telegram_notifier=telegram_notifier,
                mcp_config_path=self.mcp_config,
                headless=self.headless,
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

        elif event == WatchEvent.PENDING_UPDATED:
            self.call_from_thread(
                self.post_message,
                messages.WatchPendingUpdated(
                    pending_files=data.get("pending_files", []),
                )
            )

        elif event == WatchEvent.SESSION_STARTED:
            self.call_from_thread(
                self.post_message,
                messages.WatchSessionStarted(
                    session_id=data.get("session_id", ""),
                    planner_model=data.get("planner_model", ""),
                    executor_model=data.get("executor_model", ""),
                    phase=data.get("phase", "execution"),
                    feature=data.get("feature"),
                    milestone_count=data.get("milestone_count", 0),
                    milestone_names=data.get("milestone_names", []),
                )
            )

        elif event == WatchEvent.STOPPED:
            self.call_from_thread(
                self.post_message,
                messages.WatchStopped(
                    completed=data.get("completed", 0),
                    failed=data.get("failed", 0),
                    paused=data.get("paused", 0),
                )
            )

        elif event == WatchEvent.TOKEN_USAGE:
            self.call_from_thread(
                self.post_message,
                messages.TokensUsed(
                    agent=data.get("agent", ""),
                    input_tokens=data.get("input_tokens", 0),
                    output_tokens=data.get("output_tokens", 0),
                    cache_creation_input_tokens=data.get("cache_creation_tokens", 0),
                    cache_read_input_tokens=data.get("cache_read_tokens", 0),
                    model=data.get("model"),
                    cost_usd=data.get("cost_usd"),
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
            status_panel.update_phase("STARTING", "ACTIVE")
            status_panel.update_feature("—")  # Clear feature until session starts

            # Reset stats (tokens, cost, animations) for new session
            status_panel.reset_stats()

            milestone_list = self.query_one("#milestone-list", MilestoneList)
            milestone_list.set_milestones([])

            # Clear both output panels
            planner_output = self.query_one("#planner-output", AgentOutput)
            planner_output.clear_output()
            planner_output.write_message(f"Processing: {filename[:50]}...", "bold")

            executor_output = self.query_one("#executor-output", AgentOutput)
            executor_output.clear_output()
            executor_output.write_message(f"Processing: {filename[:50]}...", "bold")
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
        """Set watch panel to running state and clear paused session."""
        self._paused_session_id = None  # Clear paused session on resume
        try:
            watch_panel = self.query_one("#watch-panel", WatchPanel)
            watch_panel.set_running()
        except Exception:
            pass

    def _refresh_git_status(self) -> None:
        """Refresh the git status panel."""
        try:
            git_panel = self.query_one("#git-panel", GitStatusPanel)
            # Use the plans directory for git status
            git_panel.refresh_git_status(str(self.plans_dir))
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
        self._paused_session_id = message.session_id  # Track for in-TUI response

        watch_panel = self.query_one("#watch-panel", WatchPanel)
        watch_panel.set_paused(message.session_id, message.plan_path)

        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_warning(f"Paused on blocker: {message.plan_path}")
        log_panel.log_info("Press 'r' to respond to blocker")

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

    def on_watch_pending_updated(self, message: messages.WatchPendingUpdated) -> None:
        """Handle pending files list update."""
        watch_panel = self.query_one("#watch-panel", WatchPanel)
        watch_panel.sync_pending_files(message.pending_files)

    def on_watch_session_started(self, message: messages.WatchSessionStarted) -> None:
        """Handle session started - update status panel with session info."""
        status_panel = self.query_one("#status-panel", StatusPanel)
        status_panel.update_session(message.session_id)
        status_panel.update_feature(message.feature or "")
        status_panel.update_models(message.planner_model, message.executor_model)
        status_panel.update_phase(message.phase.upper(), "ACTIVE")

        # Update milestone progress if we have milestones
        if message.milestone_count > 0:
            status_panel.update_milestone_progress(0, message.milestone_count)

        # Load milestones into the milestone list
        if message.milestone_names:
            milestone_list = self.query_one("#milestone-list", MilestoneList)
            # Convert milestone names to the format expected by MilestoneList
            # Status starts as "pending" for all milestones
            milestones = [
                {"id": i + 1, "title": name, "status": "pending"}
                for i, name in enumerate(message.milestone_names)
            ]
            milestone_list.set_milestones(milestones)

    def on_chunk_received(self, message: messages.ChunkReceived) -> None:
        """Handle chunk received from agent."""
        try:
            # Write to both output panels - they filter based on agent
            planner_output = self.query_one("#planner-output", AgentOutput)
            planner_output.write_chunk(message.chunk, message.agent)

            executor_output = self.query_one("#executor-output", AgentOutput)
            executor_output.write_chunk(message.chunk, message.agent)
        except Exception:
            pass

        # Note: Token counting now done via on_tokens_used handler using actual API counts
        # The chunk estimation is kept as fallback but will be replaced by actual counts

    def on_tokens_used(self, message: messages.TokensUsed) -> None:
        """Handle token usage report from agent."""
        try:
            status_panel = self.query_one("#status-panel", StatusPanel)
            # Add actual tokens from API
            total_tokens = message.input_tokens + message.output_tokens
            status_panel.add_tokens(total_tokens)

            # Update cost if provided
            if message.cost_usd is not None:
                status_panel.add_cost(message.cost_usd)
        except Exception:
            pass

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

        if total_milestones > 0:
            # Update milestone progress in status panel
            status_panel.update_milestone_progress(current_milestone, total_milestones)
            # Update milestone list highlighting
            if current_milestone > 0:
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

    def action_show_git_diff(self) -> None:
        """Show git diff modal."""
        self.push_screen(GitDiffScreen(directory=str(self.plans_dir)))

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

    def action_respond(self) -> None:
        """Open input modal to respond to a paused blocker."""
        log_panel = self.query_one("#log-panel", LogPanel)

        if not self._paused_session_id:
            log_panel.log_warning("No paused session to respond to")
            return

        # Prevent overlapping modals
        if hasattr(self._input_provider, 'current_prompt') and self._input_provider.current_prompt:
            log_panel.log_warning("Input already in progress")
            return

        # Start respond worker in background thread
        self.run_worker(
            self._respond_worker,
            thread=True,
            name="respond-worker",
        )

    def _respond_worker(self) -> None:
        """
        Worker thread to handle blocker response.

        Prompts user for input, then resumes the workflow via Orchestrator.
        """
        from .. import db
        from ..engine import Orchestrator

        session_id = self._paused_session_id
        if not session_id:
            return

        try:
            # Load blocker question for context
            question_snip = ""
            try:
                blockers = db.get_unresolved_blockers(session_id, self.db_path)
                if blockers:
                    question = blockers[0].get("question", "")
                    # Truncate to ~100 chars for modal display
                    question_snip = question[:100] + "..." if len(question) > 100 else question
            except Exception:
                pass  # Continue without question context

            # Build prompt
            prompt = f"Response ({session_id[:8]})"
            if question_snip:
                prompt = f"{prompt}: {question_snip}"

            # Prompt user via existing modal mechanism
            display, answer = self._input_provider.prompt(prompt)

            if not answer or not answer.strip():
                self.call_from_thread(self._log_info, "Response cancelled")
                return

            # Clear paused session ID before resuming (prevent double-trigger)
            self._paused_session_id = None

            self.call_from_thread(self._log_info, "Response submitted, resuming workflow...")

            # Create Orchestrator and resume
            orch = Orchestrator(
                session_id=session_id,
                db_path=self.db_path,
                on_output=self._adapter.on_output,
                on_chunk=self._adapter.on_chunk,
                on_state_change=self._adapter.on_state_change,
                input_provider=self._input_provider,
                planner_model=self.planner_model,
                executor_model=self.executor_model,
                mcp_config_path=self.mcp_config,
                headless=self.headless,
                telegram_notifier=self._telegram_notifier,
            )

            # Resume the workflow with the answer
            orch.resume(answer=answer.strip())

        except Exception as e:
            self.call_from_thread(self._log_error, f"Resume failed: {e}")

    def _log_info(self, message: str) -> None:
        """Helper to log info from worker thread."""
        try:
            log_panel = self.query_one("#log-panel", LogPanel)
            log_panel.log_info(message)
        except Exception:
            pass

    def _log_error(self, message: str) -> None:
        """Helper to log error from worker thread."""
        try:
            log_panel = self.query_one("#log-panel", LogPanel)
            log_panel.log_error(message)
        except Exception:
            pass
