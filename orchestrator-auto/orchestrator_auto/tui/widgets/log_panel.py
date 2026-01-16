"""
Log panel widget for orchestrator messages.
"""

from datetime import datetime
from textual.widgets import RichLog


class LogPanel(RichLog):
    """
    Panel showing orchestrator log messages.

    Features:
    - Timestamped log entries
    - Color-coded by log level
    - Auto-scroll to latest
    - Configurable max lines
    """

    DEFAULT_CSS = """
    LogPanel {
        border: solid $accent;
        background: $background;
        height: 8;
        scrollbar-size: 1 1;
    }

    LogPanel:focus {
        border: solid $primary;
    }
    """

    def __init__(self, max_lines: int = 1000, **kwargs) -> None:
        super().__init__(
            highlight=True,
            markup=True,
            wrap=True,
            auto_scroll=True,
            max_lines=max_lines,
            **kwargs
        )

    def log(self, message: str, level: str = "info") -> None:
        """
        Log a message with timestamp and level.

        Args:
            message: The message to log
            level: Log level (debug, info, warning, error)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        styled_message = self._style_message(message, level)
        self.write(f"[dim]{timestamp}[/dim] {styled_message}", scroll_end=True)

    def log_info(self, message: str) -> None:
        """Log an info message."""
        self.log(message, "info")

    def log_warning(self, message: str) -> None:
        """Log a warning message."""
        self.log(message, "warning")

    def log_error(self, message: str) -> None:
        """Log an error message."""
        self.log(message, "error")

    def log_debug(self, message: str) -> None:
        """Log a debug message."""
        self.log(message, "debug")

    def log_success(self, message: str) -> None:
        """Log a success message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.write(
            f"[dim]{timestamp}[/dim] [bold green]{message}[/bold green]",
            scroll_end=True
        )

    def log_phase_change(self, phase: str) -> None:
        """Log a phase change."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.write(
            f"[dim]{timestamp}[/dim] [bold cyan]Phase: {phase}[/bold cyan]",
            scroll_end=True
        )

    def log_milestone_start(self, milestone_num: int, title: str) -> None:
        """Log milestone start."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.write(
            f"[dim]{timestamp}[/dim] [bold]Starting M{milestone_num}:[/bold] {title}",
            scroll_end=True
        )

    def log_milestone_complete(self, milestone_num: int) -> None:
        """Log milestone completion."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.write(
            f"[dim]{timestamp}[/dim] [green]M{milestone_num} completed[/green]",
            scroll_end=True
        )

    def _style_message(self, message: str, level: str) -> str:
        """Apply styling based on log level."""
        level_styles = {
            "debug": "dim",
            "info": "",
            "warning": "yellow",
            "error": "bold red",
        }
        style = level_styles.get(level, "")
        if style:
            return f"[{style}]{message}[/{style}]"
        return message
