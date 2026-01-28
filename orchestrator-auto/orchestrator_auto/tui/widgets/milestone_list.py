"""
Milestone list widget for tracking workflow progress.
"""

from dataclasses import dataclass
from textual.app import ComposeResult
from textual.widgets import Static, Label, ListView, ListItem
from textual.containers import Horizontal, Vertical
from typing import List, Optional


@dataclass
class Milestone:
    """Represents a milestone in the workflow."""
    id: int
    title: str
    status: str  # "pending", "active", "completed", "failed"
    task_count: Optional[int] = None       # Total tasks in milestone
    tasks_completed: Optional[int] = None  # Completed tasks
    files_changed: Optional[int] = None    # Files modified


class MilestoneItem(ListItem):
    """A single milestone item in the list."""

    # CSS is defined in theme.tcss to avoid duplication

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
        # Store references to labels for direct updates (avoids dynamic ID queries)
        self._marker_label: Optional[Label] = None
        self._sub_info_label: Optional[Label] = None

    def compose(self) -> ComposeResult:
        """Compose with Vertical container for milestone + sub-info."""
        marker = self.MARKERS.get(self.milestone.status, "[ ]")
        with Vertical(classes="milestone-container"):
            # Main milestone row
            with Horizontal(classes="milestone-row"):
                self._marker_label = Label(marker, classes="milestone-marker")
                yield self._marker_label
                yield Label(f" M{self.milestone.id}: {self.milestone.title}", classes="milestone-title")
            # Sub-info row (task progress or files changed)
            self._sub_info_label = Label(self._format_sub_info(), classes="milestone-sub-info")
            yield self._sub_info_label

    def _format_sub_info(self) -> str:
        """Format the sub-info line (task progress or files changed)."""
        m = self.milestone
        # Show files changed for completed milestones
        if m.status == "completed" and m.files_changed is not None and m.files_changed > 0:
            return f"  └ {m.files_changed} files"
        # Show task progress if available (any status)
        if m.task_count is not None and m.task_count > 0:
            completed = m.tasks_completed or 0
            return f"  └ {completed}/{m.task_count} tasks"
        return ""  # Empty if no info available

    def update_status(self, status: str) -> None:
        """Update the milestone status."""
        # Remove old status class
        self.remove_class(f"milestone-{self.milestone.status}")
        # Update status
        self.milestone.status = status
        # Add new status class
        self.add_class(f"milestone-{status}")
        # Update marker using stored reference
        marker = self.MARKERS.get(status, "[ ]")
        if self._marker_label is not None:
            self._marker_label.update(marker)
        self._refresh_sub_info()

    def update_tasks(self, tasks_completed: int, task_count: int) -> None:
        """Update task progress for this milestone."""
        self.milestone.tasks_completed = tasks_completed
        self.milestone.task_count = task_count
        self._refresh_sub_info()

    def update_files(self, files_changed: int) -> None:
        """Update files changed count for this milestone."""
        self.milestone.files_changed = files_changed
        self._refresh_sub_info()

    def _refresh_sub_info(self) -> None:
        """Refresh the sub-info display using stored reference."""
        if self._sub_info_label is not None:
            self._sub_info_label.update(self._format_sub_info())


class MilestoneList(Static, can_focus=True):
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

    MilestoneList .milestone-container {
        height: auto;
    }

    MilestoneList .milestone-sub-info {
        height: 1;
        color: $text-muted;
        text-style: italic;
        padding-left: 2;
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
            milestones: List of dicts with 'id', 'title', and optionally 'status',
                       'task_count', 'tasks_completed', 'files_changed'
        """
        self._milestones = [
            Milestone(
                id=m.get("id", i + 1),
                title=m.get("title", f"Milestone {i + 1}"),
                status=m.get("status", "pending"),
                task_count=m.get("task_count"),
                tasks_completed=m.get("tasks_completed"),
                files_changed=m.get("files_changed"),
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

    def update_milestone_tasks(
        self,
        milestone_num: int,
        tasks_completed: int,
        tasks_total: int,
    ) -> None:
        """
        Update task progress for a milestone.

        Args:
            milestone_num: Milestone number (1-indexed)
            tasks_completed: Number of completed tasks
            tasks_total: Total number of tasks
        """
        for milestone in self._milestones:
            if milestone.id == milestone_num:
                milestone.tasks_completed = tasks_completed
                milestone.task_count = tasks_total
                break

        if milestone_num in self._milestone_items:
            self._milestone_items[milestone_num].update_tasks(tasks_completed, tasks_total)

    def update_milestone_files(
        self,
        milestone_num: int,
        files_count: int,
    ) -> None:
        """
        Update files changed count for a milestone.

        Args:
            milestone_num: Milestone number (1-indexed)
            files_count: Number of files changed
        """
        for milestone in self._milestones:
            if milestone.id == milestone_num:
                milestone.files_changed = files_count
                break

        if milestone_num in self._milestone_items:
            self._milestone_items[milestone_num].update_files(files_count)

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
