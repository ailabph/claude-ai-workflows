"""
Header bar widget for watch mode - single-line header with watch info, git, and clock.
"""

from datetime import datetime
from pathlib import Path
from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.containers import Horizontal


class HeaderBar(Static):
    """
    Single-line header bar for watch mode.

    Displays: watch_dir (poll_interval) | git_branch +changes | HH:MM:SS
    """

    DEFAULT_CSS = """
    HeaderBar {
        height: 1;
        background: $surface;
        dock: top;
    }

    HeaderBar > Horizontal {
        height: 1;
        width: 100%;
    }

    HeaderBar .header-watch-info {
        width: 1fr;
        color: $accent;
    }

    HeaderBar .header-git-status {
        width: auto;
        color: $text-muted;
        padding-right: 1;
    }

    HeaderBar .header-git-branch {
        color: $primary;
    }

    HeaderBar .header-git-changes {
        color: $warning;
    }

    HeaderBar .header-separator {
        width: 3;
        color: $text-muted;
    }

    HeaderBar .header-clock {
        width: 10;
        color: $text;
        text-align: right;
    }
    """

    def __init__(
        self,
        watch_dir: str = ".",
        poll_interval: int = 2,
        **kwargs,
    ) -> None:
        """
        Initialize header bar.

        Args:
            watch_dir: Directory being watched
            poll_interval: Poll interval in seconds
        """
        super().__init__(**kwargs)
        # Display relative path or basename for shorter display
        path = Path(watch_dir)
        try:
            self._watch_dir = f"./{path.relative_to(Path.cwd())}"
        except ValueError:
            self._watch_dir = path.name or str(watch_dir)

        self._poll_interval = poll_interval
        self._git_branch: str = ""
        self._git_changes: int = 0

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(
                self._format_watch_info(),
                classes="header-watch-info",
                id="watch-info",
            )
            yield Label(
                self._format_git_status(),
                classes="header-git-status",
                id="git-status",
            )
            yield Label(" | ", classes="header-separator")
            yield Label(
                self._format_time(),
                classes="header-clock",
                id="clock",
            )

    def update_git(self, branch: str, changes: int = 0) -> None:
        """
        Update git status display.

        Args:
            branch: Current branch name
            changes: Number of uncommitted changes
        """
        self._git_branch = branch
        self._git_changes = changes
        if self.is_mounted:
            try:
                self.query_one("#git-status", Label).update(self._format_git_status())
            except Exception:
                pass

    def update_time(self) -> None:
        """Update the clock display. Call every second."""
        if self.is_mounted:
            try:
                self.query_one("#clock", Label).update(self._format_time())
            except Exception:
                pass

    def _format_watch_info(self) -> str:
        """Format watch directory and poll interval."""
        return f"Watch: {self._watch_dir} ({self._poll_interval}s)"

    def _format_git_status(self) -> str:
        """Format git branch and change count."""
        if not self._git_branch:
            return ""

        if self._git_changes > 0:
            return f"[bold]{self._git_branch}[/bold] [yellow]+{self._git_changes}[/yellow]"
        return f"[bold]{self._git_branch}[/bold]"

    def _format_time(self) -> str:
        """Format current time as HH:MM:SS."""
        return datetime.now().strftime("%H:%M:%S")
