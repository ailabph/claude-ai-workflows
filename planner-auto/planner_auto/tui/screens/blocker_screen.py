"""Blocker resolution modal screen — shows blocker details and answer input.

Displays the blocker source, question text (scrollable), and a TextArea
for the user's answer. Enter submits the answer; Esc dismisses without
resolving (session stays paused).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, TextArea


class BlockerScreen(ModalScreen[str | None]):
    """Modal screen for resolving a blocker.

    Returns the answer text on submit, or None on dismiss (Esc).

    Args:
        source: Blocker source (e.g., "reviewer").
        question: The blocker question text.
    """

    DEFAULT_CSS = """
    BlockerScreen {
        align: center middle;
    }
    BlockerScreen #blocker-container {
        width: 80%;
        max-width: 100;
        height: 80%;
        max-height: 30;
        border: solid $warning;
        background: $surface;
        padding: 2 3;
    }
    BlockerScreen .bk-title {
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    BlockerScreen .bk-source {
        color: $accent;
        margin-bottom: 1;
    }
    BlockerScreen .bk-question-label {
        text-style: bold;
        color: $text;
        margin-bottom: 0;
    }
    BlockerScreen #bk-question-scroll {
        height: auto;
        max-height: 10;
        margin-bottom: 1;
        border: solid $surface;
        padding: 0 1;
    }
    BlockerScreen .bk-question-text {
        color: $text;
    }
    BlockerScreen .bk-answer-label {
        text-style: bold;
        color: $primary;
        margin-top: 1;
        margin-bottom: 0;
    }
    BlockerScreen #bk-answer {
        height: 5;
        margin-bottom: 1;
    }
    BlockerScreen #bk-submit {
        width: auto;
    }
    BlockerScreen .bk-hint {
        color: $text-muted;
        margin-top: 1;
    }
    BlockerScreen .bk-error {
        color: $error;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Cancel"),
    ]

    def __init__(
        self,
        source: str,
        question: str,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._source = source
        self._question = question
        self._error_label: Label | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="blocker-container"):
            yield Label("\u26a0 Blocker — Session Paused", classes="bk-title")
            yield Label(f"Source: {self._source}", classes="bk-source")
            yield Label("Question:", classes="bk-question-label")
            with VerticalScroll(id="bk-question-scroll"):
                yield Label(self._question, classes="bk-question-text")
            yield Label("Your answer:", classes="bk-answer-label")
            yield TextArea(id="bk-answer")
            yield Button("Submit Answer", id="bk-submit", variant="primary")
            yield Label("Press Esc to dismiss (session stays paused)", classes="bk-hint")
            self._error_label = Label("", classes="bk-error")
            self._error_label.display = False
            yield self._error_label

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle submit button press."""
        if event.button.id == "bk-submit":
            self._submit()

    def _submit(self) -> None:
        """Submit the answer."""
        textarea = self.query_one("#bk-answer", TextArea)
        answer = textarea.text.strip()
        if not answer:
            self._show_error("Please enter an answer.")
            return
        self.dismiss(answer)

    def action_dismiss_modal(self) -> None:
        """Dismiss the modal without resolving."""
        self.dismiss(None)

    def show_error(self, message: str) -> None:
        """Show an error message inline (called by the parent app)."""
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        if self._error_label is not None:
            self._error_label.update(message)
            self._error_label.display = True
