"""
Watch controller for directory-based plan execution.

Provides reusable watch logic for CLI and TUI interfaces.
"""

import signal
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any, TYPE_CHECKING

from .. import db
from ..engine import Orchestrator
from ..state import Phase, Status
from ..config import get_planner_model, get_executor_model, get_project_identity

if TYPE_CHECKING:
    from ..io import InputProvider
    from ..telegram import TelegramNotifier


class WatchEvent(Enum):
    """Events emitted by the watch controller."""
    STARTED = "started"
    PENDING_UPDATED = "pending_updated"  # Emitted each poll with current pending files
    SESSION_STARTED = "session_started"  # Emitted when orchestrator session begins
    FILE_FOUND = "file_found"
    FILE_COMPLETED = "file_completed"
    FILE_FAILED = "file_failed"
    FILE_PAUSED = "file_paused"
    FILE_SKIPPED = "file_skipped"
    FILE_CONVERTED = "file_converted"
    CONVERSION_FAILED = "conversion_failed"
    RESUMED_COMPLETED = "resumed_completed"
    RESUMED_FAILED = "resumed_failed"
    TOKEN_USAGE = "token_usage"  # Actual token usage from API
    POLLING_PAUSED = "polling_paused"  # Emitted when polling is paused
    POLLING_RESUMED = "polling_resumed"  # Emitted when polling is resumed
    STOPPED = "stopped"
    INFO = "info"
    WARNING = "warning"

    # Exploration sub-agent events
    EXPLORE_STARTED = "explore_started"      # Exploration phase beginning
    EXPLORE_QUERY = "explore_query"          # Individual query status update
    EXPLORE_QUERY_DONE = "explore_query_done"  # Individual query completed
    EXPLORE_COMPLETED = "explore_completed"  # Exploration phase finished

    # Validation sub-agent events
    VALIDATE_STARTED = "validate_started"    # Validation phase beginning
    VALIDATOR_STARTED = "validator_started"  # Individual validator running
    VALIDATOR_DONE = "validator_done"        # Individual validator completed
    VALIDATE_COMPLETED = "validate_completed"  # Validation phase finished


@dataclass
class WatchResult:
    """Result of processing a plan file in watch mode."""
    status: str  # 'completed', 'failed', 'paused', 'skipped', 'conversion_failed'
    session_id: Optional[str] = None
    executed_path: Optional[Path] = None
    error: Optional[str] = None


@dataclass
class WatchState:
    """Current state of the watch controller."""
    directory: Path = field(default_factory=lambda: Path.cwd())
    poll_interval: int = 2
    auto_convert: bool = False
    is_running: bool = False
    is_paused: bool = False
    paused_session_id: Optional[str] = None
    paused_plan_path: Optional[Path] = None
    completed_count: int = 0
    failed_count: int = 0
    paused_count: int = 0
    last_processed: Optional[str] = None


class WatchController:
    """
    Reusable watch controller for directory-based plan execution.

    This controller monitors a directory for plan files and executes
    them oldest-first, emitting events for UI integration.
    """

    # File naming constants
    QUARANTINE_PREFIX = "_orchestrator-skip__"
    TERMINAL_SUFFIXES = ("_done", "_failed", "_paused")

    def __init__(
        self,
        plans_dir: Path,
        db_path: Optional[str] = None,
        poll_interval: int = 2,
        auto_convert: bool = False,
        on_event: Optional[Callable[[WatchEvent, Dict[str, Any]], None]] = None,
        on_output: Optional[Callable[[str], None]] = None,
        on_chunk: Optional[Callable[[str, str], None]] = None,
        on_state_change: Optional[Callable] = None,
        input_provider: Optional["InputProvider"] = None,
        planner_model: Optional[str] = None,
        executor_model: Optional[str] = None,
        auto_commit: bool = False,
        smart_commit: Optional[bool] = None,
        telegram_notifier: Optional["TelegramNotifier"] = None,
        show_activity: bool = True,
        mcp_config_path: Optional[str] = None,
        headless: bool = False,
        explore_enabled: bool = False,
        validate_enabled: bool = False,
    ):
        """
        Initialize watch controller.

        Args:
            plans_dir: Directory to watch for .md files
            db_path: Optional database path
            poll_interval: Seconds between directory polls
            auto_convert: Whether to auto-convert invalid plans
            on_event: Callback for watch events (event_type, event_data)
            on_output: Callback for orchestrator output
            on_chunk: Callback for streaming chunks (chunk, agent_name)
            on_state_change: Callback for state transitions
            input_provider: Input provider for user interaction
            planner_model: Model for planner agent
            executor_model: Model for executor agent
            auto_commit: Whether to auto-commit on completion
            smart_commit: Whether to use AI-generated commit messages
            telegram_notifier: Optional Telegram notifier
            show_activity: Whether to show activity indicators
            mcp_config_path: Path to MCP configuration
            headless: Whether to run browsers in headless mode
            explore_enabled: Whether to run exploration sub-agent before milestones
            validate_enabled: Whether to run validation pipeline after milestones
        """
        self.plans_dir = Path(plans_dir).resolve()
        self.db_path = db_path
        self.poll_interval = poll_interval
        self.auto_convert = auto_convert
        self.on_event = on_event or (lambda e, d: None)
        self.on_output = on_output

        # Token usage callback that emits events
        def _on_token_usage(agent_name: str, usage_data: dict) -> None:
            self.on_event(WatchEvent.TOKEN_USAGE, {
                "agent": agent_name,
                "input_tokens": usage_data.get("input_tokens", 0),
                "output_tokens": usage_data.get("output_tokens", 0),
                "cache_read_tokens": usage_data.get("cache_read_input_tokens", 0),
                "model": usage_data.get("model", ""),
                "cost_usd": usage_data.get("cost_usd", 0.0),
            })
        self._on_token_usage = _on_token_usage
        self.on_chunk = on_chunk
        self.on_state_change = on_state_change
        self.input_provider = input_provider
        self.planner_model = get_planner_model(planner_model)
        self.executor_model = get_executor_model(executor_model)
        self.auto_commit = auto_commit
        self.smart_commit = smart_commit
        self.telegram_notifier = telegram_notifier
        self.show_activity = show_activity
        self.mcp_config_path = mcp_config_path
        self.headless = headless
        self.explore_enabled = explore_enabled
        self.validate_enabled = validate_enabled

        self._should_stop = False
        self._polling_paused = False  # Pause polling without stopping execution
        self._currently_processing: set = set()
        self._paused_session_id: Optional[str] = None
        self._paused_plan_path: Optional[Path] = None
        self._state = WatchState(
            directory=self.plans_dir,
            poll_interval=poll_interval,
            auto_convert=auto_convert,
        )

        # Get project identity for DB queries
        self._project_id, _ = get_project_identity()

        # Sub-agent instances (lazy initialized)
        self._explore_agent = None
        self._validation_pipeline = None

        # Milestone tracking for sub-agent triggers
        self._last_milestone = 0
        self._current_milestone_names: List[str] = []

    def get_state(self) -> WatchState:
        """Get current watch state."""
        return WatchState(
            directory=self.plans_dir,
            poll_interval=self.poll_interval,
            auto_convert=self.auto_convert,
            is_running=not self._should_stop,
            is_paused=self._paused_session_id is not None,
            paused_session_id=self._paused_session_id,
            paused_plan_path=self._paused_plan_path,
            completed_count=self._state.completed_count,
            failed_count=self._state.failed_count,
            paused_count=self._state.paused_count,
            last_processed=self._state.last_processed,
        )

    def is_watch_candidate(self, path: Path) -> bool:
        """
        Check if file should be considered for processing.

        A file is a candidate if:
        - It has .md extension
        - It does not start with quarantine prefix
        - It does not end with terminal suffix (_done, _failed, _paused)
        """
        name = path.name
        stem = path.stem

        # Must be .md file
        if path.suffix.lower() != '.md':
            return False

        # Skip quarantined files
        if name.startswith(self.QUARANTINE_PREFIX):
            return False

        # Skip terminal states
        for suffix in self.TERMINAL_SUFFIXES:
            if stem.endswith(suffix):
                return False

        return True

    def get_pending_plans(self) -> List[Path]:
        """
        Get candidate plans sorted by mtime ascending, then filename.

        Provides deterministic oldest-first processing order.
        Handles race conditions where files may be deleted.
        """
        candidates = [
            p for p in self.plans_dir.glob('*.md')
            if self.is_watch_candidate(p)
        ]

        # Build list with mtime, handling race condition
        sortable = []
        for p in candidates:
            try:
                mtime = p.stat().st_mtime
                sortable.append((mtime, p.name, p))
            except FileNotFoundError:
                # File was deleted between glob() and stat()
                continue

        # Sort by (mtime, filename) and extract paths
        sortable.sort(key=lambda x: (x[0], x[1]))
        return [item[2] for item in sortable]

    def _strip_terminal_suffix(self, stem: str) -> str:
        """Strip terminal suffixes from a filename stem."""
        for suffix in self.TERMINAL_SUFFIXES:
            if stem.endswith(suffix):
                return stem[:-len(suffix)]
        return stem

    def _find_available_converted_path(self, original: Path) -> Path:
        """
        Find available path for converted file with collision handling.

        Tries <stem>_converted.md first, then <stem>_converted_2.md, etc.
        """
        base = original.parent / f"{original.stem}_converted.md"
        if not base.exists():
            return base

        for i in range(2, 101):
            candidate = original.parent / f"{original.stem}_converted_{i}.md"
            if not candidate.exists():
                return candidate

        raise RuntimeError(f"Too many converted files for {original.name}")

    def rename_to_terminal(
        self,
        plan_path: Path,
        suffix: str,
        session_id: Optional[str] = None,
    ) -> tuple:
        """
        Rename plan file to terminal state and update DB.

        Args:
            plan_path: Path to the plan file
            suffix: Terminal suffix ('_done', '_failed', '_paused')
            session_id: Optional session ID to update in DB

        Returns:
            Tuple of (success, new_path_or_error_message)
        """
        base_stem = self._strip_terminal_suffix(plan_path.stem)
        new_name = f"{base_stem}{suffix}{plan_path.suffix}"
        new_path = plan_path.parent / new_name

        try:
            plan_path.rename(new_path)

            # Update DB so resume/export find the file
            if session_id:
                db.update_session(session_id, {'plan_path': str(new_path)}, self.db_path)

            return True, str(new_path)
        except OSError as e:
            return False, str(e)

    def quarantine_and_convert(self, plan_path: Path) -> Optional[Path]:
        """
        Quarantine invalid plan and create converted copy if enabled.

        Args:
            plan_path: Path to the invalid plan

        Returns:
            Path to converted file, or None if conversion failed/disabled
        """
        from ..convert import convert_plan, ConversionError

        content = plan_path.read_text()

        if not self.auto_convert:
            # Just quarantine, no conversion
            quarantine_path = plan_path.parent / f"{self.QUARANTINE_PREFIX}{plan_path.name}"
            plan_path.rename(quarantine_path)
            return None

        try:
            converted_content, metadata = convert_plan(content)
        except (ConversionError, Exception):
            # Conversion failed - quarantine original
            quarantine_path = plan_path.parent / f"{self.QUARANTINE_PREFIX}{plan_path.name}"
            plan_path.rename(quarantine_path)
            return None

        # Find available converted path
        converted_path = self._find_available_converted_path(plan_path)

        # Write converted content
        converted_path.write_text(converted_content)

        # Quarantine original
        quarantine_path = plan_path.parent / f"{self.QUARANTINE_PREFIX}{plan_path.name}"
        plan_path.rename(quarantine_path)

        self.on_event(WatchEvent.FILE_CONVERTED, {
            "original": plan_path.name,
            "converted": converted_path.name,
        })

        return converted_path

    def _process_file(self, plan_path: Path) -> WatchResult:
        """
        Process a single plan file.

        Validates the plan, converts if needed, and runs the orchestrator.
        """
        from ..convert import validate_plan_content
        from ..parser import parse_plan_file

        # Validate the plan
        content = plan_path.read_text()
        is_valid, details = validate_plan_content(content)

        executed_path = plan_path

        if not is_valid:
            self.on_event(WatchEvent.INFO, {
                "message": f"Plan needs conversion: {details.get('error', 'No milestones found')}",
            })

            if self.auto_convert:
                converted_path = self.quarantine_and_convert(plan_path)
                if converted_path:
                    executed_path = converted_path
                else:
                    self.on_event(WatchEvent.CONVERSION_FAILED, {
                        "plan_path": plan_path.name,
                    })
                    return WatchResult(
                        status='conversion_failed',
                        error="Could not convert plan to valid format",
                    )
            else:
                self.quarantine_and_convert(plan_path)
                return WatchResult(
                    status='skipped',
                    error="Plan invalid and auto-convert disabled",
                )

        # Parse plan for feature extraction
        parse_result = parse_plan_file(str(executed_path))
        if not parse_result.get('valid'):
            return WatchResult(
                status='skipped',
                error=f"Parse error: {parse_result.get('error')}",
            )

        feature = parse_result.get('feature') or executed_path.stem
        milestone_count = parse_result.get('milestones', 0)
        milestone_names = parse_result.get('milestone_names', [])

        # Store milestone names for exploration query generation
        self._current_milestone_names = milestone_names
        # Reset milestone tracking for new file
        self._last_milestone = 0

        # Create state change wrapper for milestone boundary detection
        state_change_callback = self._create_state_change_wrapper(self.on_state_change)

        # Create and run orchestrator
        try:
            orch = Orchestrator(
                feature_description=feature,
                db_path=self.db_path,
                plan_path=str(executed_path),
                on_output=self.on_output,
                on_chunk=self.on_chunk,
                on_state_change=state_change_callback,
                on_token_usage=self._on_token_usage,
                input_provider=self.input_provider,
                show_activity=self.show_activity,
                planner_model=self.planner_model,
                executor_model=self.executor_model,
                telegram_notifier=self.telegram_notifier,
                mcp_config_path=self.mcp_config_path,
                headless=self.headless,
            )

            # Emit session started event BEFORE blocking start() call
            # This ensures TUI displays milestones and feature info during execution
            self.on_event(WatchEvent.SESSION_STARTED, {
                "session_id": orch.session_id,
                "planner_model": orch.planner_model or "opus",
                "executor_model": orch.executor_model or "sonnet",
                "phase": "execution",  # Initial phase before start()
                "feature": feature,
                "milestone_count": milestone_count,
                "milestone_names": milestone_names,
            })

            orch.start()

            # Check final state
            final_phase = orch.state.phase
            final_status = orch.state.status

            if final_phase == Phase.COMPLETED and final_status == Status.COMPLETED:
                # Handle auto-commit if enabled
                if self.auto_commit:
                    self._do_auto_commit(feature, orch.session_id)

                return WatchResult(
                    status='completed',
                    session_id=orch.session_id,
                    executed_path=executed_path,
                )

            elif final_phase == Phase.PAUSED or final_status == Status.PAUSED:
                return WatchResult(
                    status='paused',
                    session_id=orch.session_id,
                    executed_path=executed_path,
                )

            elif final_status == Status.FAILED:
                return WatchResult(
                    status='failed',
                    session_id=orch.session_id,
                    executed_path=executed_path,
                    error="Workflow failed",
                )

            else:
                return WatchResult(
                    status='failed',
                    session_id=orch.session_id,
                    executed_path=executed_path,
                    error=f"Unexpected final state: {final_phase}/{final_status}",
                )

        except Exception as e:
            return WatchResult(
                status='failed',
                error=str(e),
            )

    def _do_auto_commit(self, feature: str, session_id: str) -> None:
        """Perform auto-commit if enabled, using same logic as CLI."""
        from ..git import auto_commit
        from ..config import get_smart_commit_enabled, get_auto_commit_model

        milestones = db.get_milestones(session_id, self.db_path)

        # Determine if smart commit should be used (mirrors CLI behavior)
        use_smart = get_smart_commit_enabled(self.smart_commit)

        # Determine which model to use for smart commit
        commit_model = get_auto_commit_model(None, self.executor_model)

        # Status callback that emits events (mirrors CLI on_status)
        def on_status(msg: str) -> None:
            if "Secrets detected" in msg:
                self.on_event(WatchEvent.WARNING, {"message": msg})
            elif "failed" in msg.lower() or "error" in msg.lower():
                self.on_event(WatchEvent.WARNING, {"message": msg})
            else:
                self.on_event(WatchEvent.INFO, {"message": msg})

        try:
            # Use full auto_commit signature for parity with CLI
            success, result, fallback_reason = auto_commit(
                feature_description=feature,
                milestones=milestones,
                use_smart_commit=use_smart,
                smart_commit_model=commit_model,
                on_status=on_status,
            )

            if success:
                self.on_event(WatchEvent.INFO, {"message": f"Auto-commit: {result}"})
                # Show fallback reason if applicable
                if fallback_reason == "secrets_detected":
                    self.on_event(WatchEvent.WARNING, {
                        "message": "Used static message due to potential secrets in diff"
                    })
                elif fallback_reason == "ai_generation_failed":
                    self.on_event(WatchEvent.WARNING, {
                        "message": "Used static message - AI generation unavailable"
                    })
                elif not fallback_reason and use_smart:
                    self.on_event(WatchEvent.INFO, {"message": "AI-generated commit message"})
            else:
                self.on_event(WatchEvent.WARNING, {"message": f"Commit failed: {result}"})
        except Exception as e:
            self.on_event(WatchEvent.WARNING, {"message": f"Commit error: {e}"})

    def _check_paused_session(self) -> bool:
        """
        Check if paused session has been resumed externally.

        Returns:
            True if still paused, False if resumed or completed
        """
        if not self._paused_session_id:
            return False

        session = db.get_session(self._paused_session_id, self.db_path)

        if not session or session.get('phase') == Phase.PAUSED:
            return True

        # Session was resumed externally - do post-resume reconciliation
        final_phase = session.get('phase')
        final_status = session.get('status')

        # Check status FIRST - failed status takes precedence
        if final_status == Status.FAILED:
            if self._paused_plan_path and self._paused_plan_path.exists():
                success, new_path = self.rename_to_terminal(
                    self._paused_plan_path, '_failed', self._paused_session_id
                )
                if success:
                    self.on_event(WatchEvent.RESUMED_FAILED, {
                        "new_path": Path(new_path).name
                    })
                else:
                    self.on_event(WatchEvent.WARNING, {
                        "message": f"Could not rename: {new_path}"
                    })

            if self._paused_plan_path:
                self._currently_processing.discard(self._paused_plan_path.name)

            self._paused_session_id = None
            self._paused_plan_path = None
            self._state.failed_count += 1
            return False

        elif final_phase == Phase.COMPLETED:
            if self._paused_plan_path and self._paused_plan_path.exists():
                success, new_path = self.rename_to_terminal(
                    self._paused_plan_path, '_done', self._paused_session_id
                )
                if success:
                    self.on_event(WatchEvent.RESUMED_COMPLETED, {
                        "new_path": Path(new_path).name
                    })
                else:
                    self.on_event(WatchEvent.WARNING, {
                        "message": f"Could not rename: {new_path}"
                    })

            if self._paused_plan_path:
                self._currently_processing.discard(self._paused_plan_path.name)

            self._paused_session_id = None
            self._paused_plan_path = None
            self._state.completed_count += 1
            return False

        else:
            # Still in progress (discovery/planning/execution)
            return True

    def _restore_paused_session(self) -> None:
        """
        Restore paused session state from database on startup.

        This ensures that if the TUI is restarted while a session is paused,
        it will continue polling for the blocker response.
        """
        try:
            # Query for paused sessions in this project
            paused_sessions = db.list_sessions(
                db_path=self.db_path,
                status="paused",
                project_id=self._project_id,
            )

            if not paused_sessions:
                return

            # Take the most recent paused session
            session = paused_sessions[0]
            session_id = session.get('id')  # DB column is 'id', not 'session_id'
            plan_path_str = session.get('plan_path', '')

            if not session_id:
                return

            # Find the corresponding *_paused.md file
            paused_file = None
            if plan_path_str:
                # Try exact path first
                candidate = Path(plan_path_str)
                if candidate.exists() and candidate.name.endswith('_paused.md'):
                    paused_file = candidate
                else:
                    # Search in plans directory
                    for f in self.plans_dir.glob('*_paused.md'):
                        # Match by plan path or session ID prefix in filename
                        if plan_path_str in str(f) or session_id[:8] in f.name:
                            paused_file = f
                            break

            if not paused_file:
                # Search by any _paused.md file (fallback)
                paused_files = list(self.plans_dir.glob('*_paused.md'))
                if paused_files:
                    paused_file = paused_files[0]

            if paused_file and paused_file.exists():
                self._paused_session_id = session_id
                self._paused_plan_path = paused_file
                self._state.paused_count = 1

                # Parse plan file for milestone info
                from ..parser import parse_plan_file
                parse_result = parse_plan_file(str(paused_file))
                milestone_count = parse_result.get('milestones', 0)
                milestone_names = parse_result.get('milestone_names', [])
                feature = session.get('feature_description', '')

                self.on_event(WatchEvent.INFO, {
                    "message": f"Restored paused session: {session_id[:8]} ({paused_file.name})"
                })

                # Emit SESSION_STARTED to populate UI with session details
                self.on_event(WatchEvent.SESSION_STARTED, {
                    "session_id": session_id,
                    "planner_model": session.get('planner_model', '') or self.planner_model,
                    "executor_model": session.get('executor_model', '') or self.executor_model,
                    "phase": session.get('phase', 'paused'),
                    "feature": feature,
                    "milestone_count": milestone_count,
                    "milestone_names": milestone_names,
                    "current_milestone": session.get('current_milestone', 0),
                })

                self.on_event(WatchEvent.FILE_PAUSED, {
                    "session_id": session_id,
                    "new_path": paused_file.name,
                })

        except Exception as e:
            self.on_event(WatchEvent.WARNING, {
                "message": f"Could not restore paused session: {e}"
            })

    def _init_explore_agent(self):
        """Lazy initialize the exploration sub-agent."""
        if self._explore_agent is None and self.explore_enabled:
            from ..explore import ExploreSubAgent
            # Use project root (repo root) for exploration, not plans_dir
            # This allows exploration to search the entire codebase
            self._explore_agent = ExploreSubAgent(
                cwd=Path(self._project_id),
            )
        return self._explore_agent

    def _init_validation_pipeline(self):
        """Lazy initialize the validation pipeline."""
        if self._validation_pipeline is None and self.validate_enabled:
            from ..validation.pipeline import create_default_pipeline
            self._validation_pipeline = create_default_pipeline()
        return self._validation_pipeline

    def _create_state_change_wrapper(self, original_callback: Optional[Callable]) -> Callable:
        """
        Create a wrapper for on_state_change that detects milestone boundaries.

        The wrapper intercepts state changes to:
        - Detect milestone START (current_milestone increased) → trigger exploration
        - Detect milestone COMPLETION (previous milestone done) → trigger validation
        """
        def wrapper(state) -> None:
            current = getattr(state, 'current_milestone', 0)

            # Detect milestone COMPLETION (current > last means previous just completed)
            if current > self._last_milestone and self._last_milestone > 0:
                # Previous milestone just completed - run validation
                if self.validate_enabled:
                    self._run_validation(self._last_milestone)

            # Detect milestone START (current increased from last known)
            if current > self._last_milestone:
                # New milestone starting - run exploration
                if self.explore_enabled:
                    self._run_exploration(current)

            self._last_milestone = current

            # Forward to original callback
            if original_callback:
                original_callback(state)

        return wrapper

    def _get_milestone_text(self, milestone_num: int) -> str:
        """Get milestone text/title for exploration query generation."""
        if 0 < milestone_num <= len(self._current_milestone_names):
            return self._current_milestone_names[milestone_num - 1]
        return f"Milestone {milestone_num}"

    def _run_exploration(self, milestone_num: int) -> None:
        """
        Run exploration sub-agent before milestone execution.

        Emits EXPLORE_* events for UI updates.
        """
        agent = self._init_explore_agent()
        if not agent:
            return

        try:
            from ..explore import generate_exploration_queries

            milestone_text = self._get_milestone_text(milestone_num)
            queries = generate_exploration_queries(milestone_text)

            if not queries:
                return

            self.on_event(WatchEvent.EXPLORE_STARTED, {
                "milestone": milestone_num,
                "query_count": len(queries),
            })

            # Emit pending status for each query
            for i, query in enumerate(queries):
                self.on_event(WatchEvent.EXPLORE_QUERY, {
                    "index": i,
                    "query": query,
                    "status": "pending",
                })

            # Run exploration (sync wrapper around async)
            results = []
            for i, query in enumerate(queries):
                self.on_event(WatchEvent.EXPLORE_QUERY, {
                    "index": i,
                    "query": query,
                    "status": "running",
                })

                result = agent.explore(query)
                results.append(result)

                status = "completed" if result.is_success() else "failed"
                self.on_event(WatchEvent.EXPLORE_QUERY_DONE, {
                    "index": i,
                    "query": query,
                    "status": status,
                    "tokens_used": result.tokens_used,
                    "is_partial": result.is_partial,
                })

            self.on_event(WatchEvent.EXPLORE_COMPLETED, {
                "milestone": milestone_num,
                "query_count": len(queries),
                "success_count": sum(1 for r in results if r.is_success()),
            })

        except Exception as e:
            self.on_event(WatchEvent.WARNING, {
                "message": f"Exploration failed: {e}"
            })

    def _run_validation(self, milestone_num: int) -> None:
        """
        Run validation pipeline after milestone completion.

        Emits VALIDATE_* events for UI updates.
        """
        pipeline = self._init_validation_pipeline()
        if not pipeline:
            return

        try:
            from ..git import get_changed_files, get_full_diff
            import asyncio

            # Get changed files and diff from project root (not plans_dir)
            project_root = Path(self._project_id)
            changed_file_strings = get_changed_files(str(project_root))
            # Convert to absolute paths using project root as base
            changed_files = [(project_root / f).resolve() for f in changed_file_strings]
            diff = get_full_diff(str(project_root))

            if not changed_files and not diff:
                # No changes to validate
                return

            context = f"Milestone {milestone_num}"

            self.on_event(WatchEvent.VALIDATE_STARTED, {
                "milestone": milestone_num,
                "file_count": len(changed_files),
            })

            # Emit running status for each validator
            for validator in pipeline.validators:
                self.on_event(WatchEvent.VALIDATOR_STARTED, {
                    "name": validator.name,
                    "status": "running",
                })

            # Run validation (async, so we need to run in event loop)
            loop = asyncio.new_event_loop()
            try:
                report = loop.run_until_complete(
                    pipeline.run(changed_files, diff, context)
                )
            finally:
                loop.close()

            # Emit results for each validator
            for result in report.results:
                status = "passed"
                if result.error:
                    status = "failed"
                elif result.high_count > 0 or result.medium_count > 0:
                    # Use "issues" for any severity (SubAgentPanel shows count details)
                    status = "issues"

                self.on_event(WatchEvent.VALIDATOR_DONE, {
                    "name": result.validator_name,
                    "status": status,
                    "issue_count": len(result.issues),
                    "high_count": result.high_count,
                    "medium_count": result.medium_count,
                    "duration_ms": result.duration_ms,
                })

            self.on_event(WatchEvent.VALIDATE_COMPLETED, {
                "milestone": milestone_num,
                "total_issues": report.total_issues,
                "high_count": report.high_count,
                "passed": report.passed,
            })

        except Exception as e:
            self.on_event(WatchEvent.WARNING, {
                "message": f"Validation failed: {e}"
            })

    def run(self) -> WatchState:
        """
        Run watch loop until stopped.

        This is a blocking call - run in a worker thread for TUI.

        Returns:
            Final watch state
        """
        self._should_stop = False

        # Initialize database
        db.init_db(self.db_path)

        # Restore any paused session from previous run
        self._restore_paused_session()

        self.on_event(WatchEvent.STARTED, {
            "directory": str(self.plans_dir),
            "poll_interval": self.poll_interval,
            "auto_convert": self.auto_convert,
        })

        try:
            while not self._should_stop:
                # If halted on pause, check for external resume
                if self._paused_session_id:
                    if self._check_paused_session():
                        time.sleep(self.poll_interval)
                        continue

                # If polling is paused, skip file detection but stay in loop
                if self._polling_paused:
                    time.sleep(self.poll_interval)
                    continue

                # Get oldest pending plan
                pending = self.get_pending_plans()
                pending = [p for p in pending if p.name not in self._currently_processing]

                # Emit pending files update for UI refresh
                self.on_event(WatchEvent.PENDING_UPDATED, {
                    "pending_files": [p.name for p in pending],
                })

                if not pending:
                    time.sleep(self.poll_interval)
                    continue

                plan_path = pending[0]
                self.on_event(WatchEvent.FILE_FOUND, {"plan_path": plan_path.name})

                # Process the plan
                result = self._process_file(plan_path)

                # Use executed_path for rename (may differ if converted)
                target_path = result.executed_path or plan_path
                self._state.last_processed = target_path.name

                # Handle result
                if result.status == 'completed':
                    success, new_path = self.rename_to_terminal(
                        target_path, '_done', result.session_id
                    )
                    if success:
                        self.on_event(WatchEvent.FILE_COMPLETED, {
                            "new_path": Path(new_path).name
                        })
                    else:
                        self.on_event(WatchEvent.WARNING, {
                            "message": f"Complete but could not rename: {new_path}"
                        })
                        self._currently_processing.add(target_path.name)
                    self._state.completed_count += 1

                elif result.status == 'failed':
                    success, new_path = self.rename_to_terminal(
                        target_path, '_failed', result.session_id
                    )
                    if success:
                        self.on_event(WatchEvent.FILE_FAILED, {
                            "new_path": Path(new_path).name,
                            "error": result.error,
                        })
                    else:
                        self.on_event(WatchEvent.WARNING, {
                            "message": f"Failed but could not rename: {new_path}"
                        })
                        self._currently_processing.add(target_path.name)
                    self._state.failed_count += 1

                elif result.status == 'paused':
                    success, new_path = self.rename_to_terminal(
                        target_path, '_paused', result.session_id
                    )
                    self._paused_session_id = result.session_id
                    self._paused_plan_path = Path(new_path) if success else target_path

                    if not success:
                        self._currently_processing.add(target_path.name)

                    self.on_event(WatchEvent.FILE_PAUSED, {
                        "session_id": result.session_id,
                        "new_path": Path(new_path).name if success else target_path.name,
                    })
                    self._state.paused_count += 1

                elif result.status == 'conversion_failed':
                    # Already handled in _process_file
                    pass

                elif result.status == 'skipped':
                    self.on_event(WatchEvent.FILE_SKIPPED, {
                        "plan_path": plan_path.name,
                        "reason": result.error,
                    })

                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            pass

        self.on_event(WatchEvent.STOPPED, {
            "completed": self._state.completed_count,
            "failed": self._state.failed_count,
            "paused": self._state.paused_count,
        })

        return self.get_state()

    def stop(self) -> None:
        """Signal watch loop to stop."""
        self._should_stop = True

    def pause_polling(self) -> None:
        """
        Pause directory polling without stopping execution.

        In-flight executions will complete, but no new files will be picked up.
        Useful when editing plan files mid-watch.
        """
        if not self._polling_paused:
            self._polling_paused = True
            self.on_event(WatchEvent.POLLING_PAUSED, {})

    def resume_polling(self) -> None:
        """Resume directory polling."""
        if self._polling_paused:
            self._polling_paused = False
            self.on_event(WatchEvent.POLLING_RESUMED, {})

    def is_polling_paused(self) -> bool:
        """Check if polling is paused."""
        return self._polling_paused
