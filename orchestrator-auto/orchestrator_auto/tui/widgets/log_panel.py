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
    - Filter by log level (1=errors, 2=warn+, 3=info+ which excludes debug)
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

    # Map log levels to numeric values for filtering
    LEVEL_VALUES = {
        "debug": 4,
        "info": 3,
        "warning": 2,
        "error": 1,
    }

    def __init__(
        self,
        max_lines: int = 1000,
        show_filter_hints: bool = False,
        **kwargs,
    ) -> None:
        """
        Initialize LogPanel.

        Args:
            max_lines: Maximum number of lines to keep
            show_filter_hints: Show [1][2][3] filter key hints in title
        """
        super().__init__(
            highlight=True,
            markup=True,
            wrap=True,
            auto_scroll=True,
            max_lines=max_lines,
            **kwargs
        )
        # Filter level: 1=errors only, 2=warn+, 3=info+ (default, excludes debug)
        self._filter_level: int = 3
        self._show_filter_hints: bool = show_filter_hints

    def set_filter_level(self, level: int) -> None:
        """
        Set the log filter level.

        Args:
            level: 1=errors only, 2=warnings+, 3=info+ (default, excludes debug)
        """
        self._filter_level = max(1, min(3, level))
        self._update_title()

    def set_filter_hints_visible(self, visible: bool) -> None:
        """
        Show or hide filter key hints in title.

        Args:
            visible: Whether to show [1][2][3] hints
        """
        self._show_filter_hints = visible
        self._update_title()

    def _update_title(self) -> None:
        """Update border title based on filter level and hint visibility."""
        filter_labels = {
            1: "errors",
            2: "warn+",
            3: "info+",
        }
        label = filter_labels.get(self._filter_level, "info+")

        if self._show_filter_hints:
            # Show filter key hints with current level highlighted
            # Use parentheses instead of brackets to avoid Rich markup issues
            hints = []
            for i in range(1, 4):
                if i == self._filter_level:
                    hints.append(f"({i})")  # Current level - highlighted with parens
                else:
                    hints.append(f" {i} ")  # Other levels - plain
            hint_str = "".join(hints)
            self.border_title = f"LOG ({label}) {hint_str}"
        else:
            self.border_title = f"LOG ({label})"

    def _should_log(self, level: str) -> bool:
        """Check if a message at this level should be logged based on filter."""
        level_value = self.LEVEL_VALUES.get(level, 3)
        return level_value <= self._filter_level

    def log(self, message: str, level: str = "info") -> None:
        """
        Log a message with timestamp and level.

        Args:
            message: The message to log
            level: Log level (debug, info, warning, error)
        """
        if not self._should_log(level):
            return
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

    def log_system(self, message: str) -> None:
        """Log a system message that bypasses filters (for UI feedback)."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.write(
            f"[dim]{timestamp}[/dim] [cyan]{message}[/cyan]",
            scroll_end=True
        )

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
