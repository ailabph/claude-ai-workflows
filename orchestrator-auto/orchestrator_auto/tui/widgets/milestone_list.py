"""
Milestone list widget for tracking workflow progress.
"""

from dataclasses import dataclass
from textual.app import ComposeResult
from textual.widgets import Static, Label, ListView, ListItem
from textual.containers import Vertical
from typing import List, Optional


@dataclass
class Milestone:
    """Represents a milestone in the workflow."""
    id: int
    title: str
    status: str  # "pending", "active", "completed", "failed"


class MilestoneItem(ListItem):
    """A single milestone item in the list."""

    DEFAULT_CSS = """
    MilestoneItem {
        height: 1;
        padding: 0 1;
    }

    MilestoneItem.milestone-pending .milestone-marker {
        color: $text-muted;
    }

    MilestoneItem.milestone-pending .milestone-title {
        color: $text-muted;
    }

    MilestoneItem.milestone-active .milestone-marker {
        color: $primary;
        text-style: bold;
    }

    MilestoneItem.milestone-active .milestone-title {
        color: $primary;
        text-style: bold;
    }

    MilestoneItem.milestone-completed .milestone-marker {
        color: $accent;
    }

    MilestoneItem.milestone-completed .milestone-title {
        color: $accent;
    }

    MilestoneItem.milestone-failed .milestone-marker {
        color: $error;
    }

    MilestoneItem.milestone-failed .milestone-title {
        color: $error;
    }
    """

    MARKERS = {
        "pending": "[ ]",
        "active": "[>]",
        "completed": "[x]",
        "failed": "[!]",
    }

    def __init__(self, milestone: Milestone, **kwargs) -> None:
        super().__init__(**kwargs)
        self.milestone = milestone
        self.add_class(f"milestone-{milestone.status}")

    def compose(self) -> ComposeResult:
        marker = self.MARKERS.get(self.milestone.status, "[ ]")
        yield Label(marker, classes="milestone-marker")
        yield Label(f" M{self.milestone.id}: {self.milestone.title}", classes="milestone-title")

    def update_status(self, status: str) -> None:
        """Update the milestone status."""
        # Remove old status class
        self.remove_class(f"milestone-{self.milestone.status}")
        # Update status
        self.milestone.status = status
        # Add new status class
        self.add_class(f"milestone-{status}")
        # Update marker
        marker = self.MARKERS.get(status, "[ ]")
        if self.is_mounted:
            self.query_one(".milestone-marker", Label).update(marker)


class MilestoneList(Static):
    """
    Panel showing milestone progress with checkmarks.

    Displays each milestone with status:
    - [ ] Pending (gray)
    - [>] Active/Current (green, bold)
    - [x] Completed (cyan)
    - [!] Failed (red)
    """

    DEFAULT_CSS = """
    MilestoneList {
        height: auto;
        min-height: 6;
        max-height: 12;
        border: solid $secondary;
        padding: 0 1;
        background: $surface;
    }

    MilestoneList .title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    MilestoneList ListView {
        height: auto;
        max-height: 10;
        background: transparent;
    }

    MilestoneList .empty-message {
        color: $text-muted;
        text-style: italic;
    }

    MilestoneList .progress-label {
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._milestones: List[Milestone] = []
        self._milestone_items: dict[int, MilestoneItem] = {}

    def compose(self) -> ComposeResult:
        yield Label("[b]MILESTONES[/b]", classes="title")
        with Vertical():
            if not self._milestones:
                yield Label("No milestones yet", classes="empty-message", id="empty-msg")
            yield ListView(id="milestone-list")
            yield Label("", classes="progress-label", id="progress-label")

    def set_milestones(self, milestones: List[dict]) -> None:
        """
        Set the list of milestones.

        Args:
            milestones: List of dicts with 'id', 'title', and optionally 'status'
        """
        self._milestones = [
            Milestone(
                id=m.get("id", i + 1),
                title=m.get("title", f"Milestone {i + 1}"),
                status=m.get("status", "pending")
            )
            for i, m in enumerate(milestones)
        ]
        self._rebuild_list()

    def update_milestone(self, milestone_id: int, status: str, title: Optional[str] = None) -> None:
        """
        Update a specific milestone's status.

        Args:
            milestone_id: The milestone ID to update
            status: New status ("pending", "active", "completed", "failed")
            title: Optional new title
        """
        for milestone in self._milestones:
            if milestone.id == milestone_id:
                milestone.status = status
                if title:
                    milestone.title = title
                break

        # Update the UI
        if milestone_id in self._milestone_items:
            self._milestone_items[milestone_id].update_status(status)

        self._update_progress_label()

    def set_current_milestone(self, milestone_num: int) -> None:
        """
        Set the current milestone (marks previous as completed, current as active).

        Args:
            milestone_num: The milestone number (1-indexed)
        """
        for milestone in self._milestones:
            if milestone.id < milestone_num:
                if milestone.status != "failed":
                    milestone.status = "completed"
            elif milestone.id == milestone_num:
                milestone.status = "active"
            else:
                if milestone.status not in ("completed", "failed"):
                    milestone.status = "pending"

            if milestone.id in self._milestone_items:
                self._milestone_items[milestone.id].update_status(milestone.status)

        self._update_progress_label()

    def _rebuild_list(self) -> None:
        """Rebuild the milestone list UI."""
        if not self.is_mounted:
            return

        # Hide empty message if we have milestones
        try:
            empty_msg = self.query_one("#empty-msg", Label)
            empty_msg.display = len(self._milestones) == 0
        except Exception:
            pass

        # Clear and rebuild list
        list_view = self.query_one("#milestone-list", ListView)
        list_view.clear()
        self._milestone_items.clear()

        for milestone in self._milestones:
            item = MilestoneItem(milestone)
            self._milestone_items[milestone.id] = item
            list_view.append(item)

        self._update_progress_label()

    def _update_progress_label(self) -> None:
        """Update the progress label."""
        if not self.is_mounted:
            return

        total = len(self._milestones)
        completed = sum(1 for m in self._milestones if m.status == "completed")
        failed = sum(1 for m in self._milestones if m.status == "failed")

        if total == 0:
            text = ""
        elif failed > 0:
            text = f"Progress: {completed}/{total} completed, {failed} failed"
        else:
            text = f"Progress: {completed}/{total}"

        try:
            self.query_one("#progress-label", Label).update(text)
        except Exception:
            pass

    @property
    def milestones(self) -> List[Milestone]:
        """Get the current list of milestones."""
        return self._milestones.copy()

    @property
    def completed_count(self) -> int:
        """Get the number of completed milestones."""
        return sum(1 for m in self._milestones if m.status == "completed")

    @property
    def total_count(self) -> int:
        """Get the total number of milestones."""
        return len(self._milestones)
