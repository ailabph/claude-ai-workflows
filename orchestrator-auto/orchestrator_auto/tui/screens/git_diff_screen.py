"""
Git diff screen for TUI applications.

Displays git diff output in a scrollable modal.
"""

import subprocess
from pathlib import Path
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, RichLog


class GitDiffScreen(ModalScreen):
    """
    Modal screen showing git diff output.

    Keybindings:
    - Escape or 'q': Close
    - 's': Toggle between unstaged and staged diff
    """

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("q", "close", "Close"),
        Binding("s", "toggle_staged", "Toggle Staged"),
    ]

    CSS = """
    GitDiffScreen {
        align: center middle;
    }

    GitDiffScreen > Vertical {
        width: 90%;
        height: 90%;
        background: $surface;
        border: heavy $primary;
    }

    GitDiffScreen .diff-header {
        dock: top;
        height: 3;
        background: $primary;
        color: $text;
        text-align: center;
        padding: 1;
    }

    GitDiffScreen .diff-content {
        height: 1fr;
        border: solid $secondary;
        scrollbar-size: 1 1;
    }

    GitDiffScreen .no-changes {
        text-align: center;
        color: $text-muted;
        padding: 2;
    }
    """

    def __init__(self, directory: str) -> None:
        """
        Initialize git diff screen.

        Args:
            directory: Directory to run git diff in
        """
        super().__init__()
        self.directory = Path(directory)
        self.show_staged = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", id="diff-header", classes="diff-header")
            yield RichLog(
                id="diff-content",
                classes="diff-content",
                highlight=True,
                markup=False,
                wrap=False,
            )

    def on_mount(self) -> None:
        """Load and display git diff when mounted."""
        self._refresh_diff()

    def _refresh_diff(self) -> None:
        """Refresh the git diff display."""
        try:
            # Update header
            header = self.query_one("#diff-header", Static)
            if self.show_staged:
                header.update("GIT DIFF --staged (Staged Changes)\nPress 's' to show unstaged | 'q' or Esc to close")
            else:
                header.update("GIT DIFF (Unstaged Changes)\nPress 's' to show staged | 'q' or Esc to close")

            # Get diff content
            content = self.query_one("#diff-content", RichLog)
            content.clear()

            # Run git diff
            cmd = ["git", "diff"]
            if self.show_staged:
                cmd.append("--cached")

            result = subprocess.run(
                cmd,
                cwd=str(self.directory),
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                diff_output = result.stdout.strip()
                if diff_output:
                    # Write diff line by line for better handling
                    for line in diff_output.split('\n'):
                        content.write(line)
                else:
                    # No changes
                    if self.show_staged:
                        content.write("No staged changes.", style="dim")
                    else:
                        content.write("No unstaged changes.", style="dim")
            else:
                # Error running git diff
                content.write(f"Error running git diff: {result.stderr}", style="bold red")

        except subprocess.TimeoutExpired:
            content = self.query_one("#diff-content", RichLog)
            content.clear()
            content.write("Error: git diff command timed out", style="bold red")
        except Exception as e:
            content = self.query_one("#diff-content", RichLog)
            content.clear()
            content.write(f"Error: {str(e)}", style="bold red")

    def action_close(self) -> None:
        """Close the git diff screen."""
        self.dismiss()

    def action_toggle_staged(self) -> None:
        """Toggle between staged and unstaged diff."""
        self.show_staged = not self.show_staged
        self._refresh_diff()
