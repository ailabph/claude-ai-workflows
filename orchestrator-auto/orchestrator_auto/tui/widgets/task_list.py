"""
Task list panel widget for todo mode.

Shows task list with status markers, progress counters,
and real-time updates as tasks complete.
"""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Label, ListView, ListItem
from typing import Optional, List, Dict

from ..messages import TodoTaskStarted, TodoTaskCompleted


class TaskItem(ListItem):
    """A single task item in the task list."""

    MARKERS = {
        "pending": "○",
        "processing": "▶",
        "done": "✓",
        "failed": "✗",
    }

    def __init__(
        self,
        task_index: int,
        task_content: str,
        status: str = "pending",
    ) -> None:
        super().__init__()
        self.task_index = task_index
        self.task_content = task_content
        self.task_status = status
        self._update_classes()

    def _update_classes(self) -> None:
        """Update CSS classes based on status."""
        for status in self.MARKERS:
            self.remove_class(f"task-{status}")
        self.add_class(f"task-{self.task_status}")

    def update_status(self, status: str) -> None:
        """Update the task status."""
        self.task_status = status
        self._update_classes()
        self._update_display()

    def _update_display(self) -> None:
        """Update the displayed marker and content labels."""
        try:
            marker = self.MARKERS.get(self.task_status, "○")
            self.query_one(".task-marker", Label).update(marker)
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        marker = self.MARKERS.get(self.task_status, "○")
        # Truncate long task content
        content = self.task_content
        if len(content) > 60:
            content = content[:57] + "..."

        with Horizontal(classes="task-row"):
            yield Label(marker, classes="task-marker")
            yield Label(content, classes="task-content")


class TaskListPanel(Static):
    """
    Panel showing todo task list and progress.

    Displays:
    - Total task count
    - Progress summary (completed/failed/pending)
    - List of all tasks with status markers
    - Real-time updates as tasks execute
    """

    DEFAULT_CSS = """
    TaskListPanel {
        border: solid $primary;
        height: 100%;
        padding: 0 1;
    }

    TaskListPanel .title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    TaskListPanel .task-info {
        margin-bottom: 1;
    }

    TaskListPanel .stat-row {
        height: auto;
        margin: 0 0 0 0;
    }

    TaskListPanel .stat-label {
        width: 12;
        color: $text-muted;
    }

    TaskListPanel .stat-value {
        color: $text;
    }

    TaskListPanel .spacer {
        height: 1;
    }

    TaskListPanel .counts-row {
        height: auto;
        margin: 0 0 1 0;
    }

    TaskListPanel .count-completed {
        color: $success;
        margin-right: 2;
    }

    TaskListPanel .count-failed {
        color: $error;
        margin-right: 2;
    }

    TaskListPanel .count-pending {
        color: $text-muted;
    }

    TaskListPanel .section-title {
        text-style: bold;
        color: $text-muted;
        margin-bottom: 1;
    }

    TaskListPanel TaskItem {
        height: auto;
        padding: 0 1;
    }

    TaskListPanel .task-row {
        height: auto;
    }

    TaskListPanel .task-marker {
        width: 3;
    }

    TaskListPanel .task-content {
        width: 1fr;
    }

    TaskListPanel .task-pending {
        color: $text-muted;
    }

    TaskListPanel .task-processing {
        color: $warning;
        text-style: bold;
    }

    TaskListPanel .task-done {
        color: $success;
    }

    TaskListPanel .task-failed {
        color: $error;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._total: int = 0
        self._completed: int = 0
        self._failed: int = 0
        self._tasks: Dict[int, TaskItem] = {}

    def compose(self) -> ComposeResult:
        yield Label("TASKS", classes="title")
        with Vertical(classes="task-info"):
            with Horizontal(classes="stat-row"):
                yield Label("Total:", classes="stat-label")
                yield Label("0", id="task-total", classes="stat-value")
        yield Label("", classes="spacer")
        with Horizontal(classes="counts-row"):
            yield Label(f"✓ {self._completed}", id="count-completed", classes="count-completed")
            yield Label(f"✗ {self._failed}", id="count-failed", classes="count-failed")
            yield Label(f"○ {self._total}", id="count-pending", classes="count-pending")
        yield Label("", classes="spacer")
        yield Label("Task List:", classes="section-title")
        yield ListView(id="task-list")

    def set_tasks(self, tasks: list) -> None:
        """
        Initialize the task list.

        Args:
            tasks: List of dicts with 'index', 'content', 'status'
        """
        self._total = len(tasks)
        self._completed = 0
        self._failed = 0
        self._tasks.clear()

        # Create task items (works regardless of mount state)
        for task in tasks:
            item = TaskItem(
                task_index=task["index"],
                task_content=task["content"],
                status=task.get("status", "pending"),
            )
            self._tasks[task["index"]] = item

        # Update UI (only if mounted)
        try:
            # Update total count
            self.query_one("#task-total", Label).update(str(self._total))

            # Update progress display
            self._update_progress_display()

            # Add tasks to list view
            list_view = self.query_one("#task-list", ListView)
            list_view.clear()

            for task_index in sorted(self._tasks.keys()):
                list_view.append(self._tasks[task_index])
        except Exception:
            pass

    def on_todo_task_started(self, message: TodoTaskStarted) -> None:
        """Handle task started event."""
        if message.task_index in self._tasks:
            self._tasks[message.task_index].update_status("processing")

    def on_todo_task_completed(self, message: TodoTaskCompleted) -> None:
        """Handle task completed event."""
        if message.task_index in self._tasks:
            # Update task status
            status = "done" if message.status == "done" else "failed"
            self._tasks[message.task_index].update_status(status)

            # Update counters
            if status == "done":
                self._completed += 1
            else:
                self._failed += 1

            # Update display
            self._update_progress_display()

    def _update_progress_display(self) -> None:
        """Update the progress summary display."""
        try:
            pending = self._total - self._completed - self._failed
            self.query_one("#count-completed", Label).update(f"✓ {self._completed}")
            self.query_one("#count-failed", Label).update(f"✗ {self._failed}")
            self.query_one("#count-pending", Label).update(f"○ {pending}")
        except Exception:
            pass
