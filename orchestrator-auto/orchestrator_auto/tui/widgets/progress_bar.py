"""
Milestone progress bar widget - full-width progress with milestone chips.
"""

from typing import List
from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.containers import Horizontal, Vertical


class MilestoneProgressBar(Static):
    """
    Full-width progress bar with milestone chip indicators.

    Displays:
    - Current file name being processed
    - Visual progress bar (filled/empty characters)
    - Milestone number and percentage
    - Milestone chips with status icons
    """

    DEFAULT_CSS = """
    MilestoneProgressBar {
        height: 3;
        padding: 0 1;
        background: $surface;
    }

    MilestoneProgressBar > Vertical {
        height: 100%;
    }

    MilestoneProgressBar .progress-filename {
        height: 1;
        color: $accent;
    }

    MilestoneProgressBar .progress-row {
        height: 1;
        width: 100%;
    }

    MilestoneProgressBar .progress-bar {
        width: 1fr;
        color: $text;
    }

    MilestoneProgressBar .progress-text {
        width: auto;
        color: $text-muted;
        padding-left: 1;
    }

    MilestoneProgressBar .chip-row {
        height: 1;
        width: 100%;
    }

    MilestoneProgressBar .chip {
        width: auto;
        padding-right: 1;
    }

    MilestoneProgressBar .chip-completed {
        color: $success;
    }

    MilestoneProgressBar .chip-active {
        color: $warning;
    }

    MilestoneProgressBar .chip-pending {
        color: $text-muted;
    }

    MilestoneProgressBar .chip-failed {
        color: $error;
    }
    """

    # Status icons
    ICONS = {
        "completed": "[green]✓[/green]",
        "active": "[yellow]▶[/yellow]",
        "pending": "[dim]○[/dim]",
        "failed": "[red]✗[/red]",
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_file: str = ""
        self._current_milestone: int = 0
        self._total_milestones: int = 0
        self._milestone_names: List[str] = []
        self._milestone_statuses: List[str] = []  # "completed", "active", "pending", "failed"
        self._bar_width: int = 50  # Default bar width

    def compose(self) -> ComposeResult:
        with Vertical():
            # Line 1: Filename
            yield Label(
                self._format_filename(),
                classes="progress-filename",
                id="filename",
            )
            # Line 2: Progress bar + percentage
            with Horizontal(classes="progress-row"):
                yield Label(
                    self._format_progress_bar(),
                    classes="progress-bar",
                    id="bar",
                )
                yield Label(
                    self._format_progress_text(),
                    classes="progress-text",
                    id="text",
                )
            # Line 3: Milestone chips
            yield Label(
                self._format_chips(),
                classes="chip-row",
                id="chips",
            )

    def update_progress(
        self,
        current_file: str = "",
        current_milestone: int = 0,
        total_milestones: int = 0,
        milestone_names: List[str] = None,
        milestone_statuses: List[str] = None,
    ) -> None:
        """
        Update progress display.

        Args:
            current_file: File being processed
            current_milestone: Current milestone number (1-indexed)
            total_milestones: Total number of milestones
            milestone_names: List of milestone names/titles
            milestone_statuses: List of statuses ("completed", "active", "pending", "failed")
        """
        if current_file:
            self._current_file = current_file
        if total_milestones > 0:
            self._total_milestones = total_milestones
        if current_milestone > 0:
            self._current_milestone = current_milestone
        if milestone_names is not None:
            self._milestone_names = milestone_names
        if milestone_statuses is not None:
            self._milestone_statuses = milestone_statuses

        # Auto-generate statuses if not provided
        if not self._milestone_statuses and self._total_milestones > 0:
            self._milestone_statuses = []
            for i in range(self._total_milestones):
                if i + 1 < self._current_milestone:
                    self._milestone_statuses.append("completed")
                elif i + 1 == self._current_milestone:
                    self._milestone_statuses.append("active")
                else:
                    self._milestone_statuses.append("pending")

        self._refresh_display()

    def set_milestone_status(self, milestone_num: int, status: str) -> None:
        """
        Set status for a specific milestone.

        Args:
            milestone_num: Milestone number (1-indexed)
            status: Status ("completed", "active", "pending", "failed")
        """
        idx = milestone_num - 1
        if 0 <= idx < len(self._milestone_statuses):
            self._milestone_statuses[idx] = status
            self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh all display elements."""
        if not self.is_mounted:
            return

        try:
            self.query_one("#filename", Label).update(self._format_filename())
            self.query_one("#bar", Label).update(self._format_progress_bar())
            self.query_one("#text", Label).update(self._format_progress_text())
            self.query_one("#chips", Label).update(self._format_chips())
        except Exception:
            pass

    def _format_filename(self) -> str:
        """Format the filename display."""
        if self._current_file:
            return f"[bold]▶ {self._current_file}[/bold]"
        return "[dim]No file processing[/dim]"

    def _format_progress_bar(self) -> str:
        """Format the visual progress bar."""
        if self._total_milestones == 0:
            return "[dim]" + "░" * self._bar_width + "[/dim]"

        # Calculate fill ratio
        completed = max(0, self._current_milestone - 1)
        ratio = completed / self._total_milestones

        filled = int(ratio * self._bar_width)
        empty = self._bar_width - filled

        # Use block characters for progress
        return "[green]" + "═" * filled + "[/green][dim]" + "░" * empty + "[/dim]"

    def _format_progress_text(self) -> str:
        """Format the progress percentage text."""
        if self._total_milestones == 0:
            return "M-/- (0%)"

        completed = max(0, self._current_milestone - 1)
        percent = int((completed / self._total_milestones) * 100)
        return f"M{self._current_milestone}/{self._total_milestones} ({percent}%)"

    def _format_chips(self) -> str:
        """Format the milestone chips row."""
        if not self._milestone_statuses:
            return ""

        chips = []
        for i, status in enumerate(self._milestone_statuses):
            icon = self.ICONS.get(status, self.ICONS["pending"])
            # Use milestone name if available, else just number
            if i < len(self._milestone_names) and self._milestone_names[i]:
                # Truncate long names
                name = self._milestone_names[i][:10]
            else:
                name = str(i + 1)
            chips.append(f"{icon}{name}")

        return "  ".join(chips)
