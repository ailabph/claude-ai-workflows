"""
Queue controller for sequential plan execution.

Provides reusable queue logic for CLI and TUI interfaces.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any, TYPE_CHECKING

from .. import db
from ..engine import Orchestrator
from ..state import Phase, Status
from ..config import get_planner_model, get_executor_model, get_stuck_sessions_config

if TYPE_CHECKING:
    from ..io import InputProvider
    from ..telegram import TelegramNotifier


class QueueEvent(Enum):
    """Events emitted by the queue controller."""
    STARTED = "started"
    ITEM_STARTED = "item_started"
    ITEM_COMPLETED = "item_completed"
    ITEM_FAILED = "item_failed"
    ITEM_PAUSED = "item_paused"
    COMPLETED = "completed"
    HALTED = "halted"
    RECONCILED = "reconciled"
    INFO = "info"
    WARNING = "warning"


@dataclass
class QueueItem:
    """Represents a queue item."""
    id: str
    position: int
    plan_path: str
    feature_description: str
    status: str
    session_id: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class QueueState:
    """Current state of the queue."""
    items: List[QueueItem] = field(default_factory=list)
    current_index: int = 0
    is_running: bool = False
    completed_count: int = 0
    failed_count: int = 0
    paused_count: int = 0


class QueueController:
    """
    Reusable queue runner for sequential plan execution.

    This controller manages the queue lifecycle and emits events
    that can be handled by CLI or TUI interfaces.
    """

    def __init__(
        self,
        project_id: str,
        db_path: Optional[str] = None,
        on_event: Optional[Callable[[QueueEvent, Dict[str, Any]], None]] = None,
        on_output: Optional[Callable[[str], None]] = None,
        on_chunk: Optional[Callable[[str, str], None]] = None,
        on_state_change: Optional[Callable] = None,
        input_provider: Optional["InputProvider"] = None,
        planner_model: Optional[str] = None,
        executor_model: Optional[str] = None,
        auto_commit: bool = False,
        smart_commit: Optional[bool] = None,
        auto_commit_model: Optional[str] = None,
        telegram_notifier: Optional["TelegramNotifier"] = None,
        show_activity: bool = True,
        mcp_config_path: Optional[str] = None,
        headless: bool = False,
        no_rename: bool = False,
    ):
        """
        Initialize queue controller.

        Args:
            project_id: Project identifier for scoping queue items
            db_path: Optional database path
            on_event: Callback for queue events (event_type, event_data)
            on_output: Callback for orchestrator output
            on_chunk: Callback for streaming chunks (chunk, agent_name)
            on_state_change: Callback for state transitions
            input_provider: Input provider for user interaction
            planner_model: Model for planner agent
            executor_model: Model for executor agent
            auto_commit: Whether to auto-commit on completion
            smart_commit: Whether to use AI-generated commit messages
            auto_commit_model: Model for commit message generation
            telegram_notifier: Optional Telegram notifier
            show_activity: Whether to show activity indicators
            mcp_config_path: Path to MCP configuration
            headless: Whether to run browsers in headless mode
            no_rename: Whether to skip plan file renaming
        """
        self.project_id = project_id
        self.db_path = db_path
        self.on_event = on_event or (lambda e, d: None)
        self.on_output = on_output
        self.on_chunk = on_chunk
        self.on_state_change = on_state_change
        self.input_provider = input_provider
        self.planner_model = get_planner_model(planner_model)
        self.executor_model = get_executor_model(executor_model)
        self.auto_commit = auto_commit
        self.smart_commit = smart_commit
        self.auto_commit_model = auto_commit_model
        self.telegram_notifier = telegram_notifier
        self.show_activity = show_activity
        self.mcp_config_path = mcp_config_path
        self.headless = headless
        self.no_rename = no_rename

        self._current_orchestrator: Optional[Orchestrator] = None
        self._should_stop = False
        self._state = QueueState()
        self._reconciled_completed_count = 0  # Track completions found during reconciliation

    def get_state(self) -> QueueState:
        """Get current queue state."""
        items = db.list_queue_items(self.project_id, self.db_path, include_completed=True)
        queue_items = [
            QueueItem(
                id=item["id"],
                position=item["position"],
                plan_path=item["plan_path"],
                feature_description=item["feature_description"],
                status=item["status"],
                session_id=item.get("session_id"),
                error_message=item.get("error_message"),
                started_at=item.get("started_at"),
                completed_at=item.get("completed_at"),
            )
            for item in items
        ]
        return QueueState(
            items=queue_items,
            current_index=self._find_current_index(items),
            is_running=self._current_orchestrator is not None,
            completed_count=sum(1 for i in items if i["status"] == "completed"),
            failed_count=sum(1 for i in items if i["status"] == "failed"),
            paused_count=sum(1 for i in items if i["status"] == "paused"),
        )

    def _find_current_index(self, items: List[Dict]) -> int:
        """Find index of current/next item to process."""
        for i, item in enumerate(items):
            if item["status"] in ("pending", "running"):
                return i
        return len(items)

    def is_heartbeat_recent(self, session: dict, inactive_minutes: int = 20) -> bool:
        """
        Check if a session's heartbeat is recent.

        Port of _is_heartbeat_recent() from cli.py.
        """
        from datetime import timedelta

        last_activity_str = session.get('heartbeat_at') or session.get('updated_at')
        if not last_activity_str:
            return False

        try:
            if 'T' in last_activity_str:
                last_activity = datetime.fromisoformat(last_activity_str)
            else:
                last_activity = datetime.strptime(last_activity_str, "%Y-%m-%d %H:%M:%S")

            threshold = datetime.now() - timedelta(minutes=inactive_minutes)
            return last_activity >= threshold
        except (ValueError, TypeError):
            return False

    def reconcile_head(self) -> tuple:
        """
        Reconcile the head active queue item before processing.

        Returns:
            Tuple of (action, head_item) where action is one of:
            - "ready": Safe to run the head pending item
            - "empty": No active items, queue is done
            - "halt_paused": Queue halted on paused item
            - "halt_active": Another runner is active
            - "halt_orphaned": Session orphaned
        """
        stuck_config = get_stuck_sessions_config()
        inactive_minutes = stuck_config.get("inactive_minutes", 20)

        while True:
            items = db.list_queue_items(self.project_id, self.db_path, include_completed=False)

            if not items:
                return ("empty", None)

            head = items[0]
            status = head["status"]
            session_id = head.get("session_id")

            if status == "pending":
                return ("ready", head)

            if status == "paused":
                self.on_event(QueueEvent.WARNING, {
                    "message": f"Queue halted: item {head['position'] + 1} is paused",
                    "session_id": session_id,
                })
                return ("halt_paused", head)

            if status == "running":
                if not session_id:
                    # No session - mark failed
                    self.on_event(QueueEvent.WARNING, {
                        "message": f"Queue item {head['position'] + 1} has no session - marking failed",
                    })
                    db.update_queue_item(
                        head["id"],
                        self.db_path,
                        status="failed",
                        error_message="No session_id (crash before session created)",
                        completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    continue

                session = db.get_session(session_id, self.db_path)
                if not session:
                    self.on_event(QueueEvent.WARNING, {
                        "message": f"Queue item {head['position'] + 1} session not found - marking failed",
                    })
                    db.update_queue_item(
                        head["id"],
                        self.db_path,
                        status="failed",
                        error_message=f"Session not found: {session_id}",
                        completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    continue

                session_phase = session.get("phase")
                session_status = session.get("status")

                if session_phase == Phase.COMPLETED or session_status == Status.COMPLETED:
                    # Reconcile completed session
                    self.on_event(QueueEvent.RECONCILED, {
                        "message": f"Queue item {head['position'] + 1} session already completed",
                        "item": head,
                    })
                    db.update_queue_item(
                        head["id"],
                        self.db_path,
                        status="completed",
                        completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    # Emit ITEM_COMPLETED so CLI can handle auto-commit/rename
                    self.on_event(QueueEvent.ITEM_COMPLETED, {
                        "position": head["position"] + 1,
                        "feature_description": head["feature_description"],
                        "session_id": session_id,
                        "reconciled": True,  # Flag to indicate this was a reconciliation
                    })
                    # Track for final summary
                    self._reconciled_completed_count += 1
                    continue

                if session_phase == Phase.PAUSED or session_status == Status.PAUSED:
                    db.update_queue_item(head["id"], self.db_path, status="paused")
                    return ("halt_paused", head)

                # Check heartbeat
                if self.is_heartbeat_recent(session, inactive_minutes):
                    self.on_event(QueueEvent.WARNING, {
                        "message": "Another queue runner appears to be active",
                        "session_id": session_id,
                    })
                    return ("halt_active", head)
                else:
                    self.on_event(QueueEvent.WARNING, {
                        "message": f"Queue item {head['position'] + 1} has orphaned session",
                        "session_id": session_id,
                        "inactive_minutes": inactive_minutes,
                    })
                    return ("halt_orphaned", head)

            # Unknown status
            self.on_event(QueueEvent.WARNING, {
                "message": f"Queue item {head['position'] + 1} has unknown status '{status}'",
            })
            db.update_queue_item(
                head["id"],
                self.db_path,
                status="failed",
                error_message=f"Unknown status: {status}",
                completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

    def run(self) -> QueueState:
        """
        Run queue to completion or until halted.

        This is a blocking call - run in a worker thread for TUI.

        Returns:
            Final queue state
        """
        self._should_stop = False
        self._state = self.get_state()
        self._reconciled_completed_count = 0  # Reset for this run

        # Initial reconciliation
        action, head_item = self.reconcile_head()

        if action == "empty":
            self.on_event(QueueEvent.INFO, {"message": "Queue is empty - nothing to run"})
            return self.get_state()

        if action in ("halt_paused", "halt_active", "halt_orphaned"):
            self.on_event(QueueEvent.HALTED, {"reason": action, "item": head_item})
            return self.get_state()

        # Notify queue started
        all_items = db.list_queue_items(self.project_id, self.db_path, include_completed=False)
        self.on_event(QueueEvent.STARTED, {"item_count": len(all_items)})

        if self.telegram_notifier:
            self.telegram_notifier.notify_queue_started(len(all_items))

        completed_count = 0
        failed_count = 0
        paused_count = 0

        while not self._should_stop:
            action, next_item = self.reconcile_head()

            if action == "empty":
                break

            if action == "halt_paused":
                paused_count += 1
                break

            if action in ("halt_active", "halt_orphaned"):
                break

            if action != "ready":
                self.on_event(QueueEvent.WARNING, {
                    "message": f"Unexpected reconciliation action: {action}"
                })
                break

            # Process item
            result = self._run_item(next_item)

            if result == "completed":
                completed_count += 1
            elif result == "failed":
                failed_count += 1
            elif result == "paused":
                paused_count += 1
                break

        # Include reconciled completions in total
        total_completed = completed_count + self._reconciled_completed_count

        # Final state
        final_state = QueueState(
            items=self.get_state().items,
            is_running=False,
            completed_count=total_completed,
            failed_count=failed_count,
            paused_count=paused_count,
        )

        self.on_event(QueueEvent.COMPLETED, {
            "completed": total_completed,
            "failed": failed_count,
            "paused": paused_count,
        })

        return final_state

    def _run_item(self, item: dict) -> str:
        """
        Run a single queue item.

        Returns:
            Result status: "completed", "failed", or "paused"
        """
        item_id = item["id"]
        plan_path = item["plan_path"]
        feature_desc = item["feature_description"]
        position = item["position"] + 1

        self.on_event(QueueEvent.ITEM_STARTED, {
            "position": position,
            "plan_path": plan_path,
            "feature_description": feature_desc,
        })

        if self.telegram_notifier:
            self.telegram_notifier.notify_queue_item_started(position, feature_desc)

        try:
            # Mark as running
            db.update_queue_item(
                item_id,
                self.db_path,
                status="running",
                started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

            # Create orchestrator
            orch = Orchestrator(
                feature_description=feature_desc,
                db_path=self.db_path,
                plan_path=plan_path,
                on_output=self.on_output,
                on_chunk=self.on_chunk,
                on_state_change=self.on_state_change,
                input_provider=self.input_provider,
                show_activity=self.show_activity,
                planner_model=self.planner_model,
                executor_model=self.executor_model,
                telegram_notifier=self.telegram_notifier,
                mcp_config_path=self.mcp_config_path,
                headless=self.headless,
            )
            self._current_orchestrator = orch

            # Store session_id
            db.update_queue_item(item_id, self.db_path, session_id=orch.session_id)

            # Run workflow
            orch.start()

            # Check final status
            final_phase = orch.state.phase
            final_status = orch.state.status

            if final_phase == Phase.COMPLETED:
                db.update_queue_item(
                    item_id,
                    self.db_path,
                    status="completed",
                    completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                self.on_event(QueueEvent.ITEM_COMPLETED, {
                    "position": position,
                    "feature_description": feature_desc,
                    "session_id": orch.session_id,
                })

                if self.telegram_notifier:
                    self.telegram_notifier.notify_queue_item_completed(position, feature_desc)

                return "completed"

            elif final_phase == Phase.PAUSED or final_status == Status.PAUSED:
                db.update_queue_item(item_id, self.db_path, status="paused")
                self.on_event(QueueEvent.ITEM_PAUSED, {
                    "position": position,
                    "feature_description": feature_desc,
                    "session_id": orch.session_id,
                })

                if self.telegram_notifier:
                    self.telegram_notifier.notify_queue_item_paused(position, feature_desc)

                return "paused"

            else:
                # Unexpected state - treat as failed
                db.update_queue_item(
                    item_id,
                    self.db_path,
                    status="failed",
                    error_message=f"Unexpected final state: {final_phase}/{final_status}",
                    completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                return "failed"

        except Exception as e:
            db.update_queue_item(
                item_id,
                self.db_path,
                status="failed",
                error_message=str(e),
                completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            self.on_event(QueueEvent.ITEM_FAILED, {
                "position": position,
                "feature_description": feature_desc,
                "error": str(e),
            })

            if self.telegram_notifier:
                self.telegram_notifier.notify_queue_item_failed(position, feature_desc, str(e))

            return "failed"

        finally:
            self._current_orchestrator = None

    def stop(self) -> None:
        """Signal queue to stop after current item."""
        self._should_stop = True

    def skip_current(self) -> None:
        """Skip the current/next pending item."""
        items = db.list_queue_items(self.project_id, self.db_path, include_completed=False)
        for item in items:
            if item["status"] == "pending":
                db.update_queue_item(
                    item["id"],
                    self.db_path,
                    status="failed",
                    error_message="Skipped by user",
                    completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                self.on_event(QueueEvent.INFO, {
                    "message": f"Skipped queue item {item['position'] + 1}"
                })
                break
