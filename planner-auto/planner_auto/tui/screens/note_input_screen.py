"""Note input modal screen — multiline TextArea for note content."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, TextArea, Button


class NoteInputScreen(ModalScreen[str | None]):
    """Modal screen with multiline TextArea for note content.

    Returns the note content on submit, or None on Esc.
    """

    DEFAULT_CSS = """
    NoteInputScreen {
        align: center middle;
    }
    NoteInputScreen #note-container {
        width: 70%;
        max-width: 80;
        height: 60%;
        max-height: 20;
        border: solid $accent;
        background: $surface;
        padding: 2 3;
    }
    NoteInputScreen .ni-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    NoteInputScreen .ni-hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    NoteInputScreen #note-submit {
        margin-top: 1;
        width: auto;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="note-container"):
            yield Label("Add Note", classes="ni-title")
            yield Label("Enter your note (press Submit or Ctrl+S to save):", classes="ni-hint")
            yield TextArea(id="note-textarea")
            yield Button("Submit", id="note-submit", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle submit button press."""
        if event.button.id == "note-submit":
            self._submit()

    def _submit(self) -> None:
        textarea = self.query_one("#note-textarea", TextArea)
        content = textarea.text.strip()
        if content:
            self.dismiss(content)

    def action_dismiss_modal(self) -> None:
        """Dismiss the modal without submitting."""
        self.dismiss(None)
