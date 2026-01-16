"""
Queue panel widget for displaying queue items and progress.
"""

from dataclasses import dataclass
from textual.app import ComposeResult
from textual.widgets import Static, Label, ListView, ListItem
from textual.containers import Horizontal, Vertical
from typing import List, Optional


@dataclass
class QueueItemData:
    """Represents a queue item for display."""
    position: int
    feature: str
    status: str  # "pending", "running", "completed", "failed", "paused"
    session_id: Optional[str] = None
    error: Optional[str] = None


class QueueListItem(ListItem):
    """A single queue item in the list."""

    # CSS is defined in theme.tcss

    MARKERS = {
        "pending": "○",
        "running": "▶",
        "completed": "✓",
        "failed": "✗",
        "paused": "⏸",
    }

    def __init__(self, item: QueueItemData, **kwargs) -> None:
        super().__init__(**kwargs)
        self.item = item
        self.add_class(f"queue-{item.status}")

    def compose(self) -> ComposeResult:
        """Compose with Horizontal container for proper rendering."""
        marker = self.MARKERS.get(self.item.status, "○")
        # Truncate feature to fit display
        feature = self.item.feature[:40] + "..." if len(self.item.feature) > 40 else self.item.feature

        with Horizontal(classes="queue-item-row"):
            yield Label(f"{self.item.position}.", classes="queue-position")
            yield Label(marker, classes="queue-marker")
            yield Label(feature, classes="queue-feature")

    def update_status(self, status: str) -> None:
        """Update the item status."""
        # Remove old status class
        self.remove_class(f"queue-{self.item.status}")
        # Update status
        self.item.status = status
        # Add new status class
        self.add_class(f"queue-{status}")
        # Update marker
        marker = self.MARKERS.get(status, "○")
        if self.is_mounted:
            self.query_one(".queue-marker", Label).update(marker)


class QueuePanel(Static):
    """
    Panel showing queue items with status.

    Displays each item with status:
    - ○ Pending (gray)
    - ▶ Running (green, bold)
    - ✓ Completed (cyan)
    - ✗ Failed (red)
    - ⏸ Paused (yellow)
    """

    # CSS is defined in theme.tcss

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._items: List[QueueItemData] = []
        self._list_items: dict[int, QueueListItem] = {}
        self._current_position: int = 0

    def compose(self) -> ComposeResult:
        yield Label("[b]QUEUE[/b]", classes="title")
        with Vertical():
            yield Label("No items in queue", classes="empty-message", id="empty-msg")
            yield ListView(id="queue-list")
            yield Label("", classes="progress-label", id="queue-progress")

    def set_items(self, items: List[dict]) -> None:
        """
        Set the queue items.

        Args:
            items: List of dicts with 'position', 'feature', 'status', optionally 'session_id', 'error'
        """
        self._items = [
            QueueItemData(
                position=item.get("position", i + 1),
                feature=item.get("feature", f"Item {i + 1}"),
                status=item.get("status", "pending"),
                session_id=item.get("session_id"),
                error=item.get("error"),
            )
            for i, item in enumerate(items)
        ]
        self._rebuild_list()

    def add_item(self, item: dict) -> None:
        """Add a single item to the queue."""
        queue_item = QueueItemData(
            position=item.get("position", len(self._items) + 1),
            feature=item.get("feature", f"Item {len(self._items) + 1}"),
            status=item.get("status", "pending"),
            session_id=item.get("session_id"),
            error=item.get("error"),
        )
        self._items.append(queue_item)
        self._rebuild_list()

    def update_item(self, position: int, status: str, session_id: Optional[str] = None, error: Optional[str] = None) -> None:
        """
        Update a specific queue item's status.

        Args:
            position: The item position (1-indexed)
            status: New status
            session_id: Optional session ID
            error: Optional error message
        """
        for item in self._items:
            if item.position == position:
                item.status = status
                if session_id:
                    item.session_id = session_id
                if error:
                    item.error = error
                break

        # Update the UI
        if position in self._list_items:
            self._list_items[position].update_status(status)

        # Track current position
        if status == "running":
            self._current_position = position

        self._update_progress_label()

    def set_current_item(self, position: int) -> None:
        """Set the current running item."""
        self._current_position = position
        for item in self._items:
            if item.position == position:
                item.status = "running"
            elif item.position < position and item.status not in ("failed", "paused"):
                item.status = "completed"

            if item.position in self._list_items:
                self._list_items[item.position].update_status(item.status)

        self._update_progress_label()

    def _rebuild_list(self) -> None:
        """Rebuild the queue list UI."""
        if not self.is_mounted:
            return

        # Hide empty message if we have items
        try:
            empty_msg = self.query_one("#empty-msg", Label)
            empty_msg.display = len(self._items) == 0
        except Exception:
            pass

        # Clear and rebuild list
        list_view = self.query_one("#queue-list", ListView)
        list_view.clear()
        self._list_items.clear()

        for item in self._items:
            list_item = QueueListItem(item)
            self._list_items[item.position] = list_item
            list_view.append(list_item)

        self._update_progress_label()

    def _update_progress_label(self) -> None:
        """Update the progress label."""
        if not self.is_mounted:
            return

        total = len(self._items)
        completed = sum(1 for i in self._items if i.status == "completed")
        failed = sum(1 for i in self._items if i.status == "failed")
        paused = sum(1 for i in self._items if i.status == "paused")

        if total == 0:
            text = ""
        else:
            parts = [f"{completed}/{total} completed"]
            if failed > 0:
                parts.append(f"{failed} failed")
            if paused > 0:
                parts.append(f"{paused} paused")
            text = ", ".join(parts)

        try:
            self.query_one("#queue-progress", Label).update(text)
        except Exception:
            pass

    @property
    def items(self) -> List[QueueItemData]:
        """Get the current list of items."""
        return self._items.copy()

    @property
    def completed_count(self) -> int:
        """Get the number of completed items."""
        return sum(1 for i in self._items if i.status == "completed")

    @property
    def failed_count(self) -> int:
        """Get the number of failed items."""
        return sum(1 for i in self._items if i.status == "failed")

    @property
    def total_count(self) -> int:
        """Get the total number of items."""
        return len(self._items)

    @property
    def current_position(self) -> int:
        """Get the current running position."""
        return self._current_position
