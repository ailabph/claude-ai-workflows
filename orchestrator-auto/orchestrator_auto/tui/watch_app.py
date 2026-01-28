"""
Watch mode TUI application for orchestrator-auto.

Provides a TUI for directory-based plan watching and execution.
"""

import subprocess
from datetime import datetime
from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Header, Footer
from textual.worker import Worker
from typing import Optional, Dict, Any, TYPE_CHECKING

from . import messages
from .messages import (
    EXPLORE_STATUS_PENDING,
    EXPLORE_STATUS_RUNNING,
    EXPLORE_PHASE_COMPLETED,
    VALIDATE_PHASE_RUNNING,
    VALIDATE_PHASE_COMPLETED,
)
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
    # Compact mode widgets
    CompactSidebar,
    AgentTogglePanel,
    StatusBar,
    # Layout B widgets
    HeaderBar,
    MilestoneProgressBar,
    StatsPanel,
    SubAgentPanel,
    ExplorationQuery,
    ValidatorStatus,
)
from .screens import HelpScreen, GitDiffScreen, BlockerModal
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

    # Verbose mode CSS (3-column layout with dual agent panels)
    CSS_VERBOSE = """
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

    # Compact mode CSS (2-column layout with single toggleable agent panel)
    CSS_COMPACT = """
    #main-row {
        width: 100%;
        height: 1fr;
    }

    #sidebar {
        width: 1fr;
        height: 100%;
    }

    #agent-panel {
        width: 3fr;
        height: 100%;
    }

    #status-bar {
        dock: bottom;
        height: 1;
    }
    """

    # Layout B CSS (Sub-Agent Aware verbose layout)
    CSS_LAYOUT_B = """
    /* Header and progress bar - full width */
    #header-bar {
        dock: top;
        height: 1;
    }

    #progress-bar {
        dock: top;
        height: 3;
    }

    /* Main 3-column content area */
    #layout-b-content {
        height: 1fr;
        width: 100%;
    }

    /* Left column: Milestones + Watch */
    #lb-left-col {
        width: 1fr;
        min-width: 18;
        max-width: 28;
        height: 100%;
    }

    #lb-milestone-list {
        height: 1fr;
        min-height: 8;
    }

    #lb-watch-panel {
        height: 1fr;
        min-height: 24;
        max-height: 40;
    }

    /* Middle column: Sub-agents + Stats */
    #lb-middle-col {
        width: 1fr;
        min-width: 18;
        max-width: 25;
        height: 100%;
    }

    #lb-subagent-panel {
        height: 1fr;
    }

    #lb-stats-panel {
        height: auto;
        max-height: 5;
    }

    /* Right column: Agent outputs */
    #lb-right-col {
        width: 3fr;
        min-width: 60;
        height: 100%;
    }

    #lb-output-row {
        height: 1fr;
    }

    #lb-planner-output {
        width: 1fr;
        min-width: 30;
    }

    #lb-executor-output {
        width: 1fr;
        min-width: 30;
    }

    /* Bottom: Log panel */
    #lb-log-panel {
        dock: bottom;
        height: 8;
        min-height: 4;
        max-height: 12;
    }
    """

    # Combined CSS - all layout rules (non-conflicting IDs)
    CSS = CSS_VERBOSE + CSS_COMPACT + CSS_LAYOUT_B

    BINDINGS = GLOBAL_BINDINGS + WATCH_BINDINGS

    def __init__(
        self,
        plans_dir: str,
        verbose: bool = False,
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
        explore: bool = False,
        validate: bool = False,
        **kwargs,
    ) -> None:
        """
        Initialize the Watch TUI.

        Args:
            plans_dir: Directory to watch for plan files
            verbose: Use expanded layout with dual agent panels (default: compact)
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
            explore: Whether to run exploration sub-agent before milestones
            validate: Whether to run validation pipeline after milestones
        """
        super().__init__(**kwargs)
        self.verbose = verbose
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
        self.explore = explore
        self.validate = validate

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

        # Track current session ID for copy action
        self._current_session_id: Optional[str] = None

        # Phase 2: Focus tracking for panel navigation
        # Focusable panels depend on layout mode
        if self.verbose:
            if self._use_layout_b:
                # Layout B: include milestone list, subagent panel, planner, executor, log
                self._focusable_panels = [
                    "#lb-milestone-list",
                    "#lb-subagent-panel",
                    "#lb-planner-output",
                    "#lb-executor-output",
                    "#lb-log-panel",
                ]
            else:
                self._focusable_panels = ["#planner-output", "#executor-output", "#log-panel"]
        else:
            self._focusable_panels = ["#agent-panel"]
        self._focused_panel_index: int = -1  # -1 means no panel focused

    @property
    def _use_layout_b(self) -> bool:
        """Determine if Layout B (sub-agent aware) should be used."""
        # Layout B is used when verbose AND at least one sub-agent is enabled
        return self.verbose and (self.explore or self.validate)

    def _get_repo_name(self) -> str:
        """Get repository name from git or directory name."""
        try:
            # Try to get repo root
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=str(self.plans_dir),
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                repo_path = Path(result.stdout.strip())
                return repo_path.name
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass
        # Fallback to plans directory parent name
        return self.plans_dir.parent.name

    def _get_branch_name(self) -> str:
        """Get current git branch name."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(self.plans_dir),
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                # Truncate long branch names
                if len(branch) > 25:
                    return branch[:22] + "..."
                return branch
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass
        return "—"

    def _update_subtitle(self) -> None:
        """Update the app subtitle with repo and branch info."""
        repo = self._get_repo_name()
        branch = self._get_branch_name()
        self.sub_title = f"📁 {repo} ({branch})"

    def compose(self) -> ComposeResult:
        """Compose the TUI layout with containers."""
        yield Header()

        if self._use_layout_b:
            # Layout B: Sub-agent aware verbose layout
            yield HeaderBar(
                watch_dir=str(self.plans_dir),
                poll_interval=self.poll_interval,
                id="header-bar",
            )
            yield MilestoneProgressBar(id="progress-bar")

            with Horizontal(id="layout-b-content"):
                # Left column: Milestones + Watch
                with Vertical(id="lb-left-col"):
                    yield MilestoneList(id="lb-milestone-list")
                    yield WatchPanel(id="lb-watch-panel")

                # Middle column: Sub-agents + Stats
                with Vertical(id="lb-middle-col"):
                    yield SubAgentPanel(id="lb-subagent-panel")
                    yield StatsPanel(id="lb-stats-panel")

                # Right column: Planner + Executor outputs
                with Vertical(id="lb-right-col"):
                    with Horizontal(id="lb-output-row"):
                        yield AgentOutput(
                            id="lb-planner-output",
                            agent_filter="planner",
                            header_title="PLANNER"
                        )
                        yield AgentOutput(
                            id="lb-executor-output",
                            agent_filter="executor",
                            header_title="EXECUTOR"
                        )

            yield LogPanel(id="lb-log-panel", show_filter_hints=True)

        elif self.verbose:
            # Verbose layout: 3 columns with dual agent panels (legacy)
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
        else:
            # Compact layout: sidebar + single toggleable agent panel
            with Horizontal(id="main-row"):
                yield CompactSidebar(id="sidebar")
                yield AgentTogglePanel(id="agent-panel")
            yield StatusBar(id="status-bar")

        yield Footer()

    def on_mount(self) -> None:
        """Handle app mount - start the watch."""
        # Set repo/branch in subtitle
        self._update_subtitle()

        if self._use_layout_b:
            # Layout B: Sub-agent aware verbose layout
            log_panel = self.query_one("#lb-log-panel", LogPanel)
            log_panel.log_info("Watch Mode TUI Started (Layout B)")
            log_panel.log_info(f"Watching: {self.plans_dir}")
            if self.explore:
                log_panel.log_info("Exploration sub-agent enabled")
            if self.validate:
                log_panel.log_info("Validation pipeline enabled")

            # Initialize header bar with git status
            header_bar = self.query_one("#header-bar", HeaderBar)
            header_bar.update_git(self._get_branch_name(), 0)

            # Initialize sub-agent panel with enabled states
            subagent_panel = self.query_one("#lb-subagent-panel", SubAgentPanel)
            subagent_panel.set_enabled(self.explore, self.validate)

            # Initialize stats panel
            stats_panel = self.query_one("#lb-stats-panel", StatsPanel)
            stats_panel.update_stats(0, 0.0, 0, "00:00")

        elif self.verbose:
            # Verbose mode: use LogPanel for logging
            log_panel = self.query_one("#log-panel", LogPanel)
            log_panel.log_info("Watch Mode TUI Started (verbose)")
            log_panel.log_info(f"Watching: {self.plans_dir}")

            # Set initial models if provided
            if self.planner_model or self.executor_model:
                status_panel = self.query_one("#status-panel", StatusPanel)
                status_panel.update_models(
                    self.planner_model or "default",
                    self.executor_model or "default"
                )
        else:
            # Compact mode: use StatusBar for logging
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.log("Watch Mode TUI Started", "info")

            # Initialize sidebar with config
            sidebar = self.query_one("#sidebar", CompactSidebar)
            sidebar.update_current_file("—", 0, 0, "STARTING")

        # Start elapsed timer
        if self._use_layout_b:
            self._timer = self.set_interval(1.0, self._update_elapsed_layout_b)
        elif self.verbose:
            self._timer = self.set_interval(1.0, self._update_elapsed)

        # Start git status refresh timer (every 5 seconds)
        if self._use_layout_b:
            self.set_interval(5.0, self._refresh_git_status_layout_b)
            self._refresh_git_status_layout_b()
        elif self.verbose:
            self.set_interval(5.0, self._refresh_git_status)
            self._refresh_git_status()

        # Start subtitle refresh timer (every 30 seconds to catch branch switches)
        self.set_interval(30.0, self._update_subtitle)

        # Start watch in worker thread
        self._start_watch()

    def _start_watch(self) -> None:
        """Start the watch controller in a worker thread."""
        # Start timer for original verbose layout (not Layout B)
        # Layout B timer is already handled via set_interval in on_mount
        if self.verbose and not self._use_layout_b:
            status_panel = self.query_one("#status-panel", StatusPanel)
            status_panel.start_timer()
        # Compact mode: timer is handled via _update_elapsed_time calls

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
                explore_enabled=self.explore,
                validate_enabled=self.validate,
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
                    current_milestone=data.get("current_milestone", 0),
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

        elif event == WatchEvent.POLLING_PAUSED:
            self.call_from_thread(self._set_polling_paused, True)

        elif event == WatchEvent.POLLING_RESUMED:
            self.call_from_thread(self._set_polling_paused, False)

        elif event in (WatchEvent.INFO, WatchEvent.WARNING):
            level = "warning" if event == WatchEvent.WARNING else "info"
            self.call_from_thread(
                self.post_message,
                messages.OutputReceived(
                    message=data.get("message", ""),
                    level=level,
                )
            )

        # Sub-agent events (Layout B)
        # Use helper to avoid drift between EXPLORE_QUERY and EXPLORE_QUERY_DONE
        elif event == WatchEvent.EXPLORE_STARTED:
            self.call_from_thread(
                self.post_message,
                messages.ExploreStarted(
                    milestone=data.get("milestone", 0),
                    query_count=data.get("query_count", 0),
                )
            )

        elif event in (WatchEvent.EXPLORE_QUERY, WatchEvent.EXPLORE_QUERY_DONE):
            # Unified handler for both query events - status comes from payload
            self.call_from_thread(
                self.post_message,
                messages.ExploreQueryUpdate(
                    index=data.get("index", 0),
                    query=data.get("query", ""),
                    status=data.get("status", "pending"),
                    tokens_used=data.get("tokens_used", 0),
                    is_partial=data.get("is_partial", False),
                )
            )

        elif event == WatchEvent.EXPLORE_COMPLETED:
            self.call_from_thread(
                self.post_message,
                messages.ExploreCompleted(
                    milestone=data.get("milestone", 0),
                    query_count=data.get("query_count", 0),
                    success_count=data.get("success_count", 0),
                )
            )

        elif event == WatchEvent.VALIDATE_STARTED:
            self.call_from_thread(
                self.post_message,
                messages.ValidateStarted(
                    milestone=data.get("milestone", 0),
                    file_count=data.get("file_count", 0),
                )
            )

        elif event == WatchEvent.VALIDATOR_STARTED:
            self.call_from_thread(
                self.post_message,
                messages.ValidatorUpdate(
                    name=data.get("name", ""),
                    status=data.get("status", "running"),
                )
            )

        elif event == WatchEvent.VALIDATOR_DONE:
            self.call_from_thread(
                self.post_message,
                messages.ValidatorUpdate(
                    name=data.get("name", ""),
                    status=data.get("status", "passed"),
                    issue_count=data.get("issue_count", 0),
                    high_count=data.get("high_count", 0),
                    medium_count=data.get("medium_count", 0),
                )
            )

        elif event == WatchEvent.VALIDATE_COMPLETED:
            self.call_from_thread(
                self.post_message,
                messages.ValidateCompleted(
                    milestone=data.get("milestone", 0),
                    total_issues=data.get("total_issues", 0),
                    high_count=data.get("high_count", 0),
                    passed=data.get("passed", False),
                )
            )

    def _reset_for_new_file(self, filename: str) -> None:
        """Reset UI elements for processing a new file."""
        try:
            if self._use_layout_b:
                # Layout B: Reset progress bar, milestone list, sub-agent panel, stats
                progress_bar = self.query_one("#progress-bar", MilestoneProgressBar)
                progress_bar.update_progress(
                    current_file=filename,
                    current_milestone=0,
                    total_milestones=0,
                    milestone_names=[],
                    milestone_statuses=[],
                )

                milestone_list = self.query_one("#lb-milestone-list", MilestoneList)
                milestone_list.set_milestones([])

                subagent_panel = self.query_one("#lb-subagent-panel", SubAgentPanel)
                subagent_panel.reset()
                subagent_panel.set_enabled(self.explore, self.validate)

                stats_panel = self.query_one("#lb-stats-panel", StatsPanel)
                stats_panel.reset()

                # Reset Layout B token/cost tracking
                self._lb_total_tokens = 0
                self._lb_total_cost = 0.0
                self._lb_total_api_calls = 0

                planner_output = self.query_one("#lb-planner-output", AgentOutput)
                planner_output.clear_output()
                planner_output.write_message(f"Processing: {filename[:50]}...", "bold")

                executor_output = self.query_one("#lb-executor-output", AgentOutput)
                executor_output.clear_output()
                executor_output.write_message(f"Processing: {filename[:50]}...", "bold")

                log_panel = self.query_one("#lb-log-panel", LogPanel)
                log_panel.log_info(f"Processing: {filename}")

            elif self.verbose:
                # Verbose mode: reset StatusPanel, MilestoneList, AgentOutput panels
                status_panel = self.query_one("#status-panel", StatusPanel)
                status_panel.update_phase("STARTING", "ACTIVE")
                status_panel.update_feature("—")  # Clear feature until session starts
                status_panel.update_current_plan(filename)  # Show current plan with timer

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
            else:
                # Compact mode: reset sidebar and agent panel
                sidebar = self.query_one("#sidebar", CompactSidebar)
                sidebar.update_current_file(filename, 0, 0, "STARTING")
                sidebar.update_stats(0, 0.0, "00:00", 0)
                sidebar.update_milestones([], 0)

                # Reset compact mode token/cost tracking
                self._total_tokens = 0
                self._total_cost = 0.0
                self._total_api_calls = 0

                agent_panel = self.query_one("#agent-panel", AgentTogglePanel)
                agent_panel.clear_buffers()
                agent_panel.write_message(f"Processing: {filename[:50]}...", "bold")

                status_bar = self.query_one("#status-bar", StatusBar)
                status_bar.set_milestone(0, 0)
                status_bar.set_activity(f"Processing: {filename[:40]}...")
        except Exception:
            pass

    def _update_watch_counts(self) -> None:
        """Update the watch panel counts."""
        try:
            if self._use_layout_b:
                watch_panel = self.query_one("#lb-watch-panel", WatchPanel)
                watch_panel.update_counts(self._completed, self._failed, self._paused)
            elif self.verbose:
                watch_panel = self.query_one("#watch-panel", WatchPanel)
                watch_panel.update_counts(self._completed, self._failed, self._paused)
            else:
                sidebar = self.query_one("#sidebar", CompactSidebar)
                sidebar.update_queue_counts(self._completed, self._failed, self._paused)
        except Exception:
            pass

    def _set_watch_running(self) -> None:
        """Set watch panel to running state and clear paused session."""
        self._paused_session_id = None  # Clear paused session on resume
        try:
            if self._use_layout_b:
                watch_panel = self.query_one("#lb-watch-panel", WatchPanel)
            else:
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
        """Update the elapsed time display (total and per-file)."""
        try:
            status_panel = self.query_one("#status-panel", StatusPanel)
            status_panel.update_elapsed()
            status_panel.update_plan_elapsed()  # Update per-file elapsed
        except Exception:
            pass

    def _update_elapsed_layout_b(self) -> None:
        """Update elapsed time for Layout B."""
        try:
            # Update header bar clock
            header_bar = self.query_one("#header-bar", HeaderBar)
            header_bar.update_time()

            # Update stats panel elapsed time
            stats_panel = self.query_one("#lb-stats-panel", StatsPanel)
            stats_panel.tick_elapsed()
        except Exception:
            pass

    def _refresh_git_status_layout_b(self) -> None:
        """Refresh git status for Layout B header bar."""
        try:
            header_bar = self.query_one("#header-bar", HeaderBar)
            branch = self._get_branch_name()
            # Count uncommitted changes
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self.plans_dir),
                capture_output=True,
                text=True,
                timeout=2.0
            )
            changes = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
            header_bar.update_git(branch, changes)
        except Exception:
            pass

    # Message handlers

    def on_watch_started(self, message: messages.WatchStarted) -> None:
        """Handle watch started."""
        if self._use_layout_b:
            watch_panel = self.query_one("#lb-watch-panel", WatchPanel)
            watch_panel.set_config(
                message.directory,
                message.poll_interval,
                message.auto_convert,
            )

            log_panel = self.query_one("#lb-log-panel", LogPanel)
            log_panel.log_success(f"Watching {message.directory}")
        elif self.verbose:
            watch_panel = self.query_one("#watch-panel", WatchPanel)
            watch_panel.set_config(
                message.directory,
                message.poll_interval,
                message.auto_convert,
            )

            log_panel = self.query_one("#log-panel", LogPanel)
            log_panel.log_success(f"Watching {message.directory}")
        else:
            # Compact mode: log to status bar
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.log(f"Watching: {message.directory}", "success")

    def on_watch_stopped(self, message: messages.WatchStopped) -> None:
        """Handle watch stopped."""
        if self._use_layout_b:
            watch_panel = self.query_one("#lb-watch-panel", WatchPanel)
            watch_panel.set_stopped()
            watch_panel.update_counts(message.completed, message.failed, message.paused)

            log_panel = self.query_one("#lb-log-panel", LogPanel)
            log_panel.log_success(
                f"Watch stopped: {message.completed} completed, "
                f"{message.failed} failed, {message.paused} paused"
            )
        elif self.verbose:
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
        else:
            sidebar = self.query_one("#sidebar", CompactSidebar)
            sidebar.update_current_file("STOPPED", 0, 0, "COMPLETED")
            sidebar.update_queue_counts(message.completed, message.failed, message.paused)

            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.log(
                f"Stopped: {message.completed}✓ {message.failed}✗ {message.paused}⏸",
                "success"
            )

    def on_watch_paused(self, message: messages.WatchPaused) -> None:
        """Handle watch paused on blocker."""
        self._paused_session_id = message.session_id  # Track for in-TUI response

        if self._use_layout_b:
            watch_panel = self.query_one("#lb-watch-panel", WatchPanel)
            watch_panel.set_paused(message.session_id, message.plan_path)

            log_panel = self.query_one("#lb-log-panel", LogPanel)
            log_panel.log_warning(f"Paused on blocker: {message.plan_path}")
            log_panel.log_info("Press 'r' to respond to blocker")
        elif self.verbose:
            watch_panel = self.query_one("#watch-panel", WatchPanel)
            watch_panel.set_paused(message.session_id, message.plan_path)

            log_panel = self.query_one("#log-panel", LogPanel)
            log_panel.log_warning(f"Paused on blocker: {message.plan_path}")
            log_panel.log_info("Press 'r' to respond to blocker")
        else:
            sidebar = self.query_one("#sidebar", CompactSidebar)
            sidebar.set_polling_paused(True)

            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.log("Paused on blocker - press 'r' to respond", "warning")

    def on_watch_file_updated(self, message: messages.WatchFileUpdated) -> None:
        """Handle file status update."""
        if self._use_layout_b:
            # Update watch panel file list
            watch_panel = self.query_one("#lb-watch-panel", WatchPanel)
            watch_panel.update_file(
                message.filename,
                message.status,
                message.error,
                message.original_filename,
            )

            log_panel = self.query_one("#lb-log-panel", LogPanel)
            if message.status == "processing":
                log_panel.log_info(f"Found: {message.filename}")
                # Update progress bar with current file
                progress_bar = self.query_one("#progress-bar", MilestoneProgressBar)
                progress_bar.update_progress(current_file=message.filename)
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
        elif self.verbose:
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
        else:
            # Compact mode: update sidebar file list
            sidebar = self.query_one("#sidebar", CompactSidebar)
            sidebar.update_file(
                message.filename,
                message.status,
                message.original_filename,
            )

            # Update status bar with status message
            status_bar = self.query_one("#status-bar", StatusBar)
            level = "info"
            if message.status == "completed":
                level = "success"
            elif message.status == "failed":
                level = "error"
            elif message.status in ("paused", "skipped"):
                level = "warning"
            status_bar.log(f"{message.status.title()}: {message.filename[:30]}", level)

    def on_watch_pending_updated(self, message: messages.WatchPendingUpdated) -> None:
        """Handle pending files list update."""
        if self._use_layout_b:
            watch_panel = self.query_one("#lb-watch-panel", WatchPanel)
            watch_panel.sync_pending_files(message.pending_files)
        elif self.verbose:
            watch_panel = self.query_one("#watch-panel", WatchPanel)
            watch_panel.sync_pending_files(message.pending_files)
        else:
            # Compact mode: update sidebar file list
            sidebar = self.query_one("#sidebar", CompactSidebar)
            sidebar.clear_files()
            for filename in message.pending_files[:6]:  # Limit to 6 files
                sidebar.add_file(filename, "pending")

    def on_watch_session_started(self, message: messages.WatchSessionStarted) -> None:
        """Handle session started - update status panel with session info."""
        # Track current session ID for copy action
        self._current_session_id = message.session_id

        # Build milestones list from names
        milestones = []
        milestone_statuses = []
        if message.milestone_names:
            for i, name in enumerate(message.milestone_names):
                milestone_num = i + 1
                if milestone_num < message.current_milestone:
                    status = "completed"
                elif milestone_num == message.current_milestone:
                    status = "active"
                else:
                    status = "pending"
                milestones.append({"id": milestone_num, "title": name, "status": status})
                milestone_statuses.append(status)

        if self._use_layout_b:
            # Layout B: Update progress bar, milestone list, log
            progress_bar = self.query_one("#progress-bar", MilestoneProgressBar)
            progress_bar.update_progress(
                current_file=self._current_processing_file or message.feature or "—",
                current_milestone=message.current_milestone,
                total_milestones=message.milestone_count,
                milestone_names=message.milestone_names or [],
                milestone_statuses=milestone_statuses,
            )

            if milestones:
                milestone_list = self.query_one("#lb-milestone-list", MilestoneList)
                milestone_list.set_milestones(milestones)

            log_panel = self.query_one("#lb-log-panel", LogPanel)
            log_panel.log_info(f"Session: {message.session_id[:8]}...")

        elif self.verbose:
            status_panel = self.query_one("#status-panel", StatusPanel)
            status_panel.update_session(message.session_id)
            status_panel.update_feature(message.feature or "")
            status_panel.update_models(message.planner_model, message.executor_model)
            status_panel.update_phase(message.phase.upper(), "ACTIVE")

            # Update milestone progress if we have milestones
            if message.milestone_count > 0:
                status_panel.update_milestone_progress(
                    message.current_milestone, message.milestone_count
                )

            # Load milestones into the milestone list
            if milestones:
                milestone_list = self.query_one("#milestone-list", MilestoneList)
                milestone_list.set_milestones(milestones)
        else:
            # Compact mode: update sidebar
            sidebar = self.query_one("#sidebar", CompactSidebar)
            sidebar.update_current_file(
                self._current_processing_file or message.feature or "—",
                message.current_milestone,
                message.milestone_count,
                message.phase.upper()
            )

            # Update milestones in sidebar
            if milestones:
                sidebar.update_milestones(milestones, message.current_milestone)

            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.set_milestone(message.current_milestone, message.milestone_count)
            status_bar.set_activity(f"Session: {message.session_id[:8]}...")

    def on_chunk_received(self, message: messages.ChunkReceived) -> None:
        """Handle chunk received from agent."""
        try:
            if self._use_layout_b:
                # Layout B: write to both output panels - they filter based on agent
                planner_output = self.query_one("#lb-planner-output", AgentOutput)
                planner_output.write_chunk(message.chunk, message.agent)

                executor_output = self.query_one("#lb-executor-output", AgentOutput)
                executor_output.write_chunk(message.chunk, message.agent)
            elif self.verbose:
                # Verbose mode: write to both output panels - they filter based on agent
                planner_output = self.query_one("#planner-output", AgentOutput)
                planner_output.write_chunk(message.chunk, message.agent)

                executor_output = self.query_one("#executor-output", AgentOutput)
                executor_output.write_chunk(message.chunk, message.agent)
            else:
                # Compact mode: write to toggle panel (it buffers both agents)
                agent_panel = self.query_one("#agent-panel", AgentTogglePanel)
                agent_panel.write_chunk(message.chunk, message.agent)
        except Exception:
            pass

        # Note: Token counting now done via on_tokens_used handler using actual API counts
        # The chunk estimation is kept as fallback but will be replaced by actual counts

    def on_tokens_used(self, message: messages.TokensUsed) -> None:
        """Handle token usage report from agent."""
        try:
            total_tokens = message.input_tokens + message.output_tokens

            if self._use_layout_b:
                # Layout B: update stats panel
                if not hasattr(self, '_lb_total_tokens'):
                    self._lb_total_tokens = 0
                    self._lb_total_cost = 0.0
                    self._lb_total_api_calls = 0

                self._lb_total_tokens += total_tokens
                self._lb_total_api_calls += 1
                if message.cost_usd is not None:
                    self._lb_total_cost += message.cost_usd

                stats_panel = self.query_one("#lb-stats-panel", StatsPanel)
                stats_panel.add_tokens(
                    message.input_tokens,
                    message.output_tokens,
                    message.cost_usd or 0.0
                )

            elif self.verbose:
                status_panel = self.query_one("#status-panel", StatusPanel)
                status_panel.add_tokens(total_tokens)

                # Update cost if provided
                if message.cost_usd is not None:
                    status_panel.add_cost(message.cost_usd)
            else:
                # Compact mode: update sidebar stats
                # We need to accumulate tokens/cost - store in instance vars
                if not hasattr(self, '_total_tokens'):
                    self._total_tokens = 0
                    self._total_cost = 0.0
                    self._total_api_calls = 0

                self._total_tokens += total_tokens
                self._total_api_calls += 1
                if message.cost_usd is not None:
                    self._total_cost += message.cost_usd

                sidebar = self.query_one("#sidebar", CompactSidebar)
                sidebar.update_stats(
                    self._total_tokens,
                    self._total_cost,
                    "—",  # elapsed handled separately
                    self._total_api_calls
                )
        except Exception:
            pass

    def on_state_changed(self, message: messages.StateChanged) -> None:
        """Handle state change."""
        state = message.state

        phase = getattr(state, 'phase', '—')
        status = getattr(state, 'status', '—')
        current_milestone = getattr(state, 'current_milestone', 0)
        total_milestones = getattr(state, 'total_milestones', 0)

        if self._use_layout_b:
            # Layout B: Update progress bar, milestone list, log
            log_panel = self.query_one("#lb-log-panel", LogPanel)
            milestone_list = self.query_one("#lb-milestone-list", MilestoneList)
            progress_bar = self.query_one("#progress-bar", MilestoneProgressBar)

            if message.previous_phase and message.previous_phase != phase:
                log_panel.log_phase_change(phase.upper())

            if total_milestones > 0 and current_milestone > 0:
                # Update milestone list highlighting
                milestone_list.set_current_milestone(current_milestone)

                # Update progress bar - rebuild statuses based on current milestone
                milestone_names = [m.title for m in milestone_list.milestones]
                milestone_statuses = []
                for m in milestone_list.milestones:
                    milestone_statuses.append(m.status)

                progress_bar.update_progress(
                    current_milestone=current_milestone,
                    total_milestones=total_milestones,
                    milestone_names=milestone_names,
                    milestone_statuses=milestone_statuses,
                )

        elif self.verbose:
            # Verbose mode: use StatusPanel, LogPanel, MilestoneList
            status_panel = self.query_one("#status-panel", StatusPanel)
            log_panel = self.query_one("#log-panel", LogPanel)
            milestone_list = self.query_one("#milestone-list", MilestoneList)

            status_panel.update_phase(phase, status)

            # Update session_id from state
            session_id = getattr(state, 'session_id', None)
            if session_id:
                status_panel.update_session(session_id)

            status_panel.increment_api_calls()

            if message.previous_phase and message.previous_phase != phase:
                log_panel.log_phase_change(phase.upper())

            if total_milestones > 0:
                # Update milestone progress in status panel
                status_panel.update_milestone_progress(current_milestone, total_milestones)
                # Update milestone list highlighting
                if current_milestone > 0:
                    milestone_list.set_current_milestone(current_milestone)
        else:
            # Compact mode: use CompactSidebar and StatusBar
            sidebar = self.query_one("#sidebar", CompactSidebar)
            status_bar = self.query_one("#status-bar", StatusBar)

            # Update sidebar with current state
            sidebar.update_current_file(
                self._current_processing_file or "—",
                current_milestone,
                total_milestones,
                phase.upper() if phase else "—"
            )

            # Update status bar
            status_bar.set_milestone(current_milestone, total_milestones)

            if message.previous_phase and message.previous_phase != phase:
                status_bar.log(f"Phase: {phase.upper()}", "info")

            # Update milestones in sidebar
            if current_milestone > 0:
                sidebar.set_current_milestone(current_milestone)

    def on_output_received(self, message: messages.OutputReceived) -> None:
        """Handle general output message."""
        if self._use_layout_b:
            log_panel = self.query_one("#lb-log-panel", LogPanel)
            log_panel.log(message.message, message.level)
        elif self.verbose:
            log_panel = self.query_one("#log-panel", LogPanel)
            log_panel.log(message.message, message.level)
        else:
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.log(message.message, message.level)

    def on_input_requested(self, message: messages.InputRequested) -> None:
        """Handle input request - show input modal."""
        if self._use_layout_b:
            log_panel = self.query_one("#lb-log-panel", LogPanel)
            log_panel.log_warning(f"Input requested: {message.prompt_text}")
        elif self.verbose:
            log_panel = self.query_one("#log-panel", LogPanel)
            log_panel.log_warning(f"Input requested: {message.prompt_text}")
        else:
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.log(f"Input requested: {message.prompt_text[:30]}...", "warning")
        self.push_screen(InputModal(message.prompt_text, self._input_provider))

    def on_milestone_updated(self, message: messages.MilestoneUpdated) -> None:
        """Handle milestone status update."""
        if self._use_layout_b:
            milestone_list = self.query_one("#lb-milestone-list", MilestoneList)
            milestone_list.update_milestone(message.milestone_id, message.status, message.title)

            log_panel = self.query_one("#lb-log-panel", LogPanel)
            if message.status == "active":
                log_panel.log_milestone_start(message.milestone_id, message.title)
            elif message.status == "completed":
                log_panel.log_milestone_complete(message.milestone_id)

            # Update progress bar
            progress_bar = self.query_one("#progress-bar", MilestoneProgressBar)
            progress_bar.set_milestone_status(message.milestone_id, message.status)

        elif self.verbose:
            milestone_list = self.query_one("#milestone-list", MilestoneList)
            milestone_list.update_milestone(message.milestone_id, message.status, message.title)

            log_panel = self.query_one("#log-panel", LogPanel)
            if message.status == "active":
                log_panel.log_milestone_start(message.milestone_id, message.title)
            elif message.status == "completed":
                log_panel.log_milestone_complete(message.milestone_id)
        else:
            # Compact mode: update sidebar milestone display
            sidebar = self.query_one("#sidebar", CompactSidebar)
            sidebar.set_current_milestone(message.milestone_id)

            status_bar = self.query_one("#status-bar", StatusBar)
            if message.status == "active":
                status_bar.set_activity(f"M{message.milestone_id}: {message.title[:30]}...")
            elif message.status == "completed":
                status_bar.log(f"M{message.milestone_id} completed", "success")

    def on_milestones_loaded(self, message: messages.MilestonesLoaded) -> None:
        """Handle milestones loaded from plan."""
        if self._use_layout_b:
            milestone_list = self.query_one("#lb-milestone-list", MilestoneList)
            milestone_list.set_milestones(message.milestones)

            # Update progress bar
            milestone_names = [m.get("title", "") for m in message.milestones]
            milestone_statuses = [m.get("status", "pending") for m in message.milestones]
            progress_bar = self.query_one("#progress-bar", MilestoneProgressBar)
            progress_bar.update_progress(
                total_milestones=len(message.milestones),
                milestone_names=milestone_names,
                milestone_statuses=milestone_statuses,
            )
        elif self.verbose:
            milestone_list = self.query_one("#milestone-list", MilestoneList)
            milestone_list.set_milestones(message.milestones)
        else:
            sidebar = self.query_one("#sidebar", CompactSidebar)
            sidebar.update_milestones(message.milestones, 0)

    def on_models_set(self, message: messages.ModelsSet) -> None:
        """Handle model configuration."""
        if self.verbose:
            status_panel = self.query_one("#status-panel", StatusPanel)
            status_panel.update_models(message.planner_model, message.executor_model)
        # Compact mode: models not displayed in sidebar (too cramped)

    def on_workflow_error(self, message: messages.WorkflowError) -> None:
        """Handle workflow error."""
        if self._use_layout_b:
            log_panel = self.query_one("#lb-log-panel", LogPanel)
            log_panel.log_error(f"Error: {message.error}")
        elif self.verbose:
            log_panel = self.query_one("#log-panel", LogPanel)
            log_panel.log_error(f"Error: {message.error}")
        else:
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.log(f"Error: {message.error[:40]}...", "error")

    # Sub-agent message handlers (Layout B)

    def on_explore_started(self, message: messages.ExploreStarted) -> None:
        """Handle exploration started."""
        if not self._use_layout_b:
            return

        try:
            subagent_panel = self.query_one("#lb-subagent-panel", SubAgentPanel)
            subagent_panel.set_explore_status(EXPLORE_STATUS_RUNNING)
            # Clear any previous queries - they'll be added via EXPLORE_QUERY events
            subagent_panel.clear_explore_queries()

            log_panel = self.query_one("#lb-log-panel", LogPanel)
            log_panel.log_info(f"Exploring M{message.milestone}: {message.query_count} queries")
        except Exception as e:
            self._log_debug(f"on_explore_started error: {e}")

    def on_explore_query_update(self, message: messages.ExploreQueryUpdate) -> None:
        """Handle exploration query status update."""
        if not self._use_layout_b:
            return

        try:
            subagent_panel = self.query_one("#lb-subagent-panel", SubAgentPanel)
            # Add query if pending (first time seeing it), otherwise update/upsert
            if message.status == EXPLORE_STATUS_PENDING:
                subagent_panel.add_explore_query(message.query, message.status)
            else:
                # Pass query for upsert in case index doesn't exist yet
                subagent_panel.update_explore_query(
                    message.index,
                    message.status,
                    message.tokens_used,
                    message.is_partial,
                    query=message.query,
                )
        except Exception as e:
            self._log_debug(f"on_explore_query_update error: {e}")

    def on_explore_completed(self, message: messages.ExploreCompleted) -> None:
        """Handle exploration completed."""
        if not self._use_layout_b:
            return

        try:
            subagent_panel = self.query_one("#lb-subagent-panel", SubAgentPanel)
            subagent_panel.set_explore_status(EXPLORE_PHASE_COMPLETED)

            log_panel = self.query_one("#lb-log-panel", LogPanel)
            log_panel.log_success(
                f"Exploration complete: {message.success_count}/{message.query_count} queries"
            )
        except Exception as e:
            self._log_debug(f"on_explore_completed error: {e}")

    def on_validate_started(self, message: messages.ValidateStarted) -> None:
        """Handle validation started."""
        if not self._use_layout_b:
            return

        try:
            subagent_panel = self.query_one("#lb-subagent-panel", SubAgentPanel)
            subagent_panel.set_validate_status(VALIDATE_PHASE_RUNNING)
            # Clear any previous validators - they'll be added via VALIDATOR_STARTED events
            subagent_panel.set_validators([])

            log_panel = self.query_one("#lb-log-panel", LogPanel)
            log_panel.log_info(f"Validating M{message.milestone}: {message.file_count} files")
        except Exception as e:
            self._log_debug(f"on_validate_started error: {e}")

    def on_validator_update(self, message: messages.ValidatorUpdate) -> None:
        """Handle validator status update."""
        if not self._use_layout_b:
            return

        try:
            subagent_panel = self.query_one("#lb-subagent-panel", SubAgentPanel)
            # update_validator handles both adding new and updating existing
            subagent_panel.update_validator(
                message.name,
                message.status,
                message.issue_count,
                message.high_count,
                message.medium_count,
            )
        except Exception as e:
            self._log_debug(f"on_validator_update error: {e}")

    def on_validate_completed(self, message: messages.ValidateCompleted) -> None:
        """Handle validation completed."""
        if not self._use_layout_b:
            return

        try:
            subagent_panel = self.query_one("#lb-subagent-panel", SubAgentPanel)
            subagent_panel.set_validate_status(VALIDATE_PHASE_COMPLETED)

            log_panel = self.query_one("#lb-log-panel", LogPanel)
            if message.total_issues > 0:
                log_panel.log_warning(
                    f"Validation: {message.total_issues} issues ({message.high_count} high)"
                )
            else:
                log_panel.log_success("Validation: passed")
        except Exception as e:
            self._log_debug(f"on_validate_completed error: {e}")

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
        if self._use_layout_b:
            log_panel = self.query_one("#lb-log-panel", LogPanel)
        elif self.verbose:
            log_panel = self.query_one("#log-panel", LogPanel)
        else:
            # Compact mode has no log panel, use status bar
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.log("Refreshed", "info")
            return
        log_panel.log_info("Refreshed")

    def action_clear(self) -> None:
        """Clear the file list."""
        if self._use_layout_b:
            watch_panel = self.query_one("#lb-watch-panel", WatchPanel)
            watch_panel.clear_files()
            log_panel = self.query_one("#lb-log-panel", LogPanel)
            log_panel.log_info("Cleared file list")
        elif self.verbose:
            watch_panel = self.query_one("#watch-panel", WatchPanel)
            watch_panel.clear_files()
            log_panel = self.query_one("#log-panel", LogPanel)
            log_panel.log_info("Cleared file list")
        else:
            sidebar = self.query_one("#sidebar", CompactSidebar)
            sidebar.clear_files()
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.log("Cleared file list", "info")

    def action_back(self) -> None:
        """Handle escape."""
        pass

    def action_respond(self) -> None:
        """Open input modal to respond to a paused blocker."""
        if not self._paused_session_id:
            self._log_to_ui("No paused session to respond to", "warning")
            return

        # Prevent overlapping modals
        if self._input_provider.current_prompt:
            self._log_to_ui("Input already in progress", "warning")
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
        Note: _paused_session_id is cleared by _set_watch_running() when
        WatchController emits RESUMED_COMPLETED or RESUMED_FAILED events.
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
                    # Normalize whitespace and truncate for modal display
                    question = " ".join(question.split())  # Collapse newlines/whitespace
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

            self.call_from_thread(self._log_info, "Response submitted, resuming workflow...")

            # Create token usage callback for accurate token tracking
            def on_token_usage(agent_name: str, usage_data: dict) -> None:
                self.call_from_thread(
                    self.post_message,
                    messages.TokensUsed(
                        agent=agent_name,
                        input_tokens=usage_data.get("input_tokens", 0),
                        output_tokens=usage_data.get("output_tokens", 0),
                        cache_creation_input_tokens=usage_data.get("cache_creation_input_tokens", 0),
                        cache_read_input_tokens=usage_data.get("cache_read_input_tokens", 0),
                        model=usage_data.get("model"),
                        cost_usd=usage_data.get("cost_usd"),
                    )
                )

            # Create Orchestrator and resume
            # Note: Don't clear _paused_session_id here - let _set_watch_running()
            # handle it when WatchController emits RESUMED_* events. This ensures
            # user can retry with 'r' if resume() fails.
            orch = Orchestrator(
                session_id=session_id,
                db_path=self.db_path,
                on_output=self._adapter.on_output,
                on_chunk=self._adapter.on_chunk,
                on_state_change=self._adapter.on_state_change,
                on_token_usage=on_token_usage,
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
            self.call_from_thread(
                self._log_error,
                f"Resume failed: {e}. Press 'r' to retry or use: orchestrator resume {session_id[:8]}"
            )

    def _log_to_ui(self, message: str, level: str = "info") -> None:
        """
        Log message to appropriate widget for current layout mode.

        Args:
            message: The message to log
            level: Log level - "info", "warning", "error", "success", or "debug"
        """
        try:
            if self._use_layout_b:
                log_panel = self.query_one("#lb-log-panel", LogPanel)
                getattr(log_panel, f"log_{level}", log_panel.log_info)(message)
            elif self.verbose:
                log_panel = self.query_one("#log-panel", LogPanel)
                getattr(log_panel, f"log_{level}", log_panel.log_info)(message)
            else:
                # Compact mode: use StatusBar
                status_bar = self.query_one("#status-bar", StatusBar)
                status_bar.log(message, level)
        except Exception:
            pass  # Silent - UI logging is best-effort

    def _log_info(self, message: str) -> None:
        """Helper to log info from worker thread."""
        self._log_to_ui(message, "info")

    def _log_error(self, message: str) -> None:
        """Helper to log error (safe for use anywhere including worker threads)."""
        self._log_to_ui(message, "error")

    def _log_debug(self, message: str) -> None:
        """Helper to log debug messages for diagnosing UI issues."""
        self._log_to_ui(message, "debug")

    def action_copy_session_id(self) -> None:
        """Copy current or paused session ID to clipboard."""
        session_id = self._current_session_id or self._paused_session_id
        if session_id:
            self.copy_to_clipboard(session_id)
            self._log_to_ui(f"Copied: {session_id[:8]}...", "info")
        else:
            self._log_to_ui("No session ID to copy", "warning")

    def action_show_blocker(self) -> None:
        """Show full blocker question in modal."""
        from .. import db

        session_id = self._paused_session_id or self._current_session_id
        if not session_id:
            self._log_to_ui("No session with blocker", "warning")
            return

        try:
            # Load blocker from database
            blockers = db.get_unresolved_blockers(session_id, self.db_path)
            if not blockers:
                self._log_to_ui("No unresolved blocker found", "warning")
                return

            blocker = blockers[0]
            question = blocker.get("question", "No question available")
            agent = blocker.get("agent", "unknown")

            # Parse timestamp if available
            timestamp = None
            if blocker.get("created_at"):
                try:
                    timestamp = datetime.fromisoformat(blocker["created_at"])
                except (ValueError, TypeError):
                    pass

            # Show the blocker modal
            def handle_result(should_respond: bool) -> None:
                if should_respond:
                    self.action_respond()

            self.push_screen(
                BlockerModal(
                    question=question,
                    session_id=session_id,
                    agent=agent,
                    timestamp=timestamp,
                ),
                handle_result,
            )

        except Exception as e:
            self._log_to_ui(f"Failed to load blocker: {e}", "error")

    # Phase 2: Panel navigation actions

    def action_focus_next(self) -> None:
        """Cycle focus to the next panel."""
        if not self._focusable_panels:
            return

        # Move to next panel (wrap around)
        self._focused_panel_index = (self._focused_panel_index + 1) % len(self._focusable_panels)
        self._apply_panel_focus()

    def action_focus_prev(self) -> None:
        """Cycle focus to the previous panel."""
        if not self._focusable_panels:
            return

        # Move to previous panel (wrap around)
        if self._focused_panel_index <= 0:
            self._focused_panel_index = len(self._focusable_panels) - 1
        else:
            self._focused_panel_index -= 1
        self._apply_panel_focus()

    def _apply_panel_focus(self) -> None:
        """Apply focus to the current panel and update visual state."""
        if self._focused_panel_index < 0:
            return

        try:
            panel_id = self._focusable_panels[self._focused_panel_index]
            panel = self.query_one(panel_id)

            # For AgentOutput panels, focus the inner RichLog to trigger :focus-within
            if isinstance(panel, AgentOutput):
                from textual.widgets import RichLog
                inner = panel.query_one(".output-content", RichLog)
                inner.focus()
            elif isinstance(panel, AgentTogglePanel):
                # For AgentTogglePanel, focus the inner RichLog
                from textual.widgets import RichLog
                inner = panel.query_one("#output-content", RichLog)
                inner.focus()
            else:
                panel.focus()
        except Exception as e:
            self._log_error(f"Focus failed: {e}")

    def action_scroll_down(self) -> None:
        """Scroll the focused panel down."""
        if self._focused_panel_index < 0:
            return
        try:
            panel_id = self._focusable_panels[self._focused_panel_index]
            panel = self.query_one(panel_id)
            panel.scroll_down()
        except Exception as e:
            self._log_error(f"Scroll down failed: {e}")

    def action_scroll_up(self) -> None:
        """Scroll the focused panel up."""
        if self._focused_panel_index < 0:
            return
        try:
            panel_id = self._focusable_panels[self._focused_panel_index]
            panel = self.query_one(panel_id)
            panel.scroll_up()
        except Exception as e:
            self._log_error(f"Scroll up failed: {e}")

    # Phase 2: Log filter actions

    def action_filter_errors(self) -> None:
        """Set log filter to errors only."""
        try:
            if self._use_layout_b:
                log_panel = self.query_one("#lb-log-panel", LogPanel)
            else:
                log_panel = self.query_one("#log-panel", LogPanel)
            log_panel.set_filter_level(1)
            log_panel.log_system("Filter: errors only")
        except Exception:
            pass

    def action_filter_warnings(self) -> None:
        """Set log filter to errors + warnings."""
        try:
            if self._use_layout_b:
                log_panel = self.query_one("#lb-log-panel", LogPanel)
            else:
                log_panel = self.query_one("#log-panel", LogPanel)
            log_panel.set_filter_level(2)
            log_panel.log_system("Filter: warnings+")
        except Exception:
            pass

    def action_filter_all(self) -> None:
        """Set log filter to info+ (excludes debug)."""
        try:
            if self._use_layout_b:
                log_panel = self.query_one("#lb-log-panel", LogPanel)
            else:
                log_panel = self.query_one("#log-panel", LogPanel)
            log_panel.set_filter_level(3)
            log_panel.log_system("Filter: info+")
        except Exception:
            pass

    # Phase 3: Execution control actions

    def _set_polling_paused(self, paused: bool) -> None:
        """Update UI when polling is paused/resumed."""
        try:
            if self._use_layout_b:
                watch_panel = self.query_one("#lb-watch-panel", WatchPanel)
                watch_panel.set_polling_paused(paused)

                log_panel = self.query_one("#lb-log-panel", LogPanel)
                if paused:
                    log_panel.log_warning("Polling paused - press 'p' to resume")
                else:
                    log_panel.log_info("Polling resumed")
            elif self.verbose:
                watch_panel = self.query_one("#watch-panel", WatchPanel)
                watch_panel.set_polling_paused(paused)

                log_panel = self.query_one("#log-panel", LogPanel)
                if paused:
                    log_panel.log_warning("Polling paused - press 'p' to resume")
                else:
                    log_panel.log_info("Polling resumed")
            else:
                sidebar = self.query_one("#sidebar", CompactSidebar)
                sidebar.set_polling_paused(paused)

                status_bar = self.query_one("#status-bar", StatusBar)
                if paused:
                    status_bar.log("Polling paused - press 'p' to resume", "warning")
                else:
                    status_bar.log("Polling resumed", "info")
        except Exception:
            pass

    def action_toggle_pause(self) -> None:
        """Toggle polling pause state."""
        if not self._controller:
            return

        try:
            if self._controller.is_polling_paused():
                self._controller.resume_polling()
            else:
                self._controller.pause_polling()
        except Exception as e:
            self._log_error(f"Pause toggle failed: {e}")

    # Compact mode: Agent toggle actions

    def action_show_planner(self) -> None:
        """Show planner output (compact mode only)."""
        if self.verbose:
            return  # No-op in verbose mode (both panels visible)

        try:
            agent_panel = self.query_one("#agent-panel", AgentTogglePanel)
            agent_panel.set_agent("planner")

            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.set_activity("Viewing: Planner output")
        except Exception:
            pass

    def action_show_executor(self) -> None:
        """Show executor output (compact mode only)."""
        if self.verbose:
            return  # No-op in verbose mode (both panels visible)

        try:
            agent_panel = self.query_one("#agent-panel", AgentTogglePanel)
            agent_panel.set_agent("executor")

            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.set_activity("Viewing: Executor output")
        except Exception:
            pass
