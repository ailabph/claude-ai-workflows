"""
Status bar widget for compact mode - single-line footer.
"""

from datetime import datetime
from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.containers import Horizontal


class StatusBar(Static):
    """
    Single-line status bar showing current activity.

    Displays: timestamp | milestone | current activity | hint
    """

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $surface;
        dock: bottom;
    }

    StatusBar > Horizontal {
        height: 1;
        width: 100%;
    }

    StatusBar .status-time {
        width: 10;
        color: $text-muted;
    }

    StatusBar .status-milestone {
        width: 8;
        color: $primary;
    }

    StatusBar .status-separator {
        width: 3;
        color: $text-muted;
    }

    StatusBar .status-activity {
        width: 1fr;
        color: $text;
    }

    StatusBar .status-hint {
        width: auto;
        color: $text-muted;
        text-align: right;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._milestone_current: int = 0
        self._milestone_total: int = 0
        self._milestone_name: str = ""
        self._activity: str = ""
        self._last_message: str = ""
        self._hint: str = "? Help"

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(self._format_time(), classes="status-time", id="time")
            yield Label(" → ", classes="status-separator")
            yield Label(self._format_milestone(), classes="status-milestone", id="milestone")
            yield Label(" │ ", classes="status-separator")
            yield Label(self._activity or "Ready", classes="status-activity", id="activity")
            yield Label(self._hint, classes="status-hint", id="hint")

    def set_milestone(self, current: int, total: int, name: str = "") -> None:
        """Update milestone display."""
        self._milestone_current = current
        self._milestone_total = total
        self._milestone_name = name
        self._update_milestone_label()

    def set_activity(self, message: str) -> None:
        """Set current activity message (truncated if needed)."""
        self._activity = message
        self._update_activity_label()

    def log(self, message: str, level: str = "info") -> None:
        """
        Log message to status bar.

        Shows most recent message. For verbose mode, use LogPanel instead.
        """
        self._last_message = message
        # For now, show in activity area with level indicator
        level_prefix = {
            "error": "[red]✗[/red]",
            "warning": "[yellow]![/yellow]",
            "info": "[cyan]→[/cyan]",
            "success": "[green]✓[/green]",
        }.get(level, "→")

        self._activity = f"{level_prefix} {message}"
        self._update_activity_label()

    def set_hint(self, hint: str) -> None:
        """Set the hint text shown on the right."""
        self._hint = hint
        if self.is_mounted:
            try:
                self.query_one("#hint", Label).update(hint)
            except Exception:
                pass

    def _format_time(self) -> str:
        """Format current time as HH:MM:SS."""
        return datetime.now().strftime("%H:%M:%S")

    def _format_milestone(self) -> str:
        """Format milestone as M#/#."""
        if self._milestone_total == 0:
            return "M-/-"
        return f"M{self._milestone_current}/{self._milestone_total}"

    def _update_milestone_label(self) -> None:
        """Update the milestone label."""
        if self.is_mounted:
            try:
                self.query_one("#milestone", Label).update(self._format_milestone())
            except Exception:
                pass

    def _update_activity_label(self) -> None:
        """Update the activity label."""
        if self.is_mounted:
            try:
                self.query_one("#activity", Label).update(self._activity or "Ready")
            except Exception:
                pass

    def update_time(self) -> None:
        """Update the time display. Call periodically if needed."""
        if self.is_mounted:
            try:
                self.query_one("#time", Label).update(self._format_time())
            except Exception:
                pass
