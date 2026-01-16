"""
Help screen for TUI applications.

Displays keybinding reference and usage information.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Label


class HelpScreen(ModalScreen):
    """
    Modal screen showing keybindings and help information.

    Press Escape or 'q' to close.
    """

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("q", "close", "Close"),
    ]

    CSS = """
    HelpScreen {
        align: center middle;
    }

    HelpScreen > Vertical {
        width: 60;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: heavy $primary;
        padding: 1 2;
    }

    HelpScreen .help-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    HelpScreen .help-section {
        margin-top: 1;
        color: $accent;
        text-style: bold;
    }

    HelpScreen .help-row {
        height: 1;
    }

    HelpScreen .help-key {
        width: 12;
        color: $primary;
    }

    HelpScreen .help-desc {
        color: $text;
    }

    HelpScreen .help-footer {
        margin-top: 1;
        text-align: center;
        color: $text-muted;
    }
    """

    def __init__(self, mode: str = "session") -> None:
        """
        Initialize help screen.

        Args:
            mode: Current TUI mode ("session", "queue", or "watch")
        """
        super().__init__()
        self.mode = mode

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("HELP", classes="help-title")

            # Global bindings
            yield Label("Global", classes="help-section")
            yield self._binding_row("q", "Quit application")
            yield self._binding_row("?", "Show this help")
            yield self._binding_row("Escape", "Close/back")

            # Mode-specific bindings
            if self.mode == "session":
                yield Label("Session Mode", classes="help-section")
                yield self._binding_row("l", "Toggle log panel")
                yield self._binding_row("m", "Toggle milestones")
                yield self._binding_row("s", "Show status details")

            elif self.mode == "queue":
                yield Label("Queue Mode", classes="help-section")
                yield self._binding_row("n", "Next item (auto)")
                yield self._binding_row("k", "Skip current item")
                yield self._binding_row("r", "Refresh display")
                yield self._binding_row("c", "Clear queue")

            elif self.mode == "watch":
                yield Label("Watch Mode", classes="help-section")
                yield self._binding_row("r", "Refresh display")
                yield self._binding_row("c", "Clear file list")
                yield self._binding_row("g", "Show git diff")

            # Input mode
            yield Label("Input Modal", classes="help-section")
            yield self._binding_row("Enter", "Submit input")
            yield self._binding_row("Escape", "Cancel input")
            yield self._binding_row("Ctrl+V", "Paste from clipboard")

            yield Label("Press Escape or 'q' to close", classes="help-footer")

    def _binding_row(self, key: str, description: str) -> Horizontal:
        """Create a help row for a keybinding."""
        row = Horizontal(classes="help-row")
        row.compose_add_child(Label(key, classes="help-key"))
        row.compose_add_child(Label(description, classes="help-desc"))
        return row

    def action_close(self) -> None:
        """Close the help screen."""
        self.dismiss()
