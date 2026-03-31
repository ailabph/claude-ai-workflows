"""File input modal screen — single-line text input for file path."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class FileInputScreen(ModalScreen[str | None]):
    """Modal screen with single-line text input for file path.

    Returns the file path on submit, or None on dismiss.
    """

    DEFAULT_CSS = """
    FileInputScreen {
        align: center middle;
    }
    FileInputScreen #file-container {
        width: 70%;
        max-width: 80;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 2 3;
    }
    FileInputScreen .fi-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    FileInputScreen .fi-hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    FileInputScreen .fi-error {
        color: $error;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Cancel"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._error_label: Label | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="file-container"):
            yield Label("Add File Context", classes="fi-title")
            yield Label("Enter the path to a file:", classes="fi-hint")
            yield Input(placeholder="/path/to/file", id="file-path-input")
            self._error_label = Label("", classes="fi-error")
            self._error_label.display = False
            yield self._error_label

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key on the input field."""
        path = event.value.strip()
        if not path:
            self._show_error("Please enter a file path.")
            return
        self.dismiss(path)

    def action_dismiss_modal(self) -> None:
        """Dismiss the modal without submitting."""
        self.dismiss(None)

    def show_error(self, message: str) -> None:
        """Show an error message inline (called by the parent app)."""
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        if self._error_label is not None:
            self._error_label.update(message)
            self._error_label.display = True
