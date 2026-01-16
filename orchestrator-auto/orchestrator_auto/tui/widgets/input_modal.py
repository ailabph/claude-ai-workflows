"""
Input modal widget for user input prompts.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Label, Input, Button
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..adapter import TUIInputProvider


class InputModal(ModalScreen):
    """
    Modal screen for user input.

    Used when the orchestrator needs input from the user,
    such as during discovery or when a blocker is encountered.
    """

    DEFAULT_CSS = """
    InputModal {
        align: center middle;
    }

    InputModal > Container {
        width: 70;
        height: auto;
        max-height: 20;
        background: $surface;
        border: heavy $primary;
        padding: 1 2;
    }

    InputModal .title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    InputModal .prompt {
        margin-bottom: 1;
        color: $text;
    }

    InputModal Input {
        margin: 1 0;
        background: $background;
        border: solid $secondary;
    }

    InputModal Input:focus {
        border: solid $primary;
    }

    InputModal .buttons {
        align: center middle;
        margin-top: 1;
    }

    InputModal Button {
        margin: 0 1;
        min-width: 12;
    }

    InputModal Button.submit {
        background: $primary;
        color: $background;
    }

    InputModal Button.cancel {
        background: $secondary;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "submit", "Submit", priority=True),
    ]

    def __init__(
        self,
        prompt: str,
        input_provider: "TUIInputProvider",
        title: str = "Input Required",
        **kwargs
    ) -> None:
        """
        Initialize the input modal.

        Args:
            prompt: The prompt text to display
            input_provider: The input provider to send input to
            title: Optional title for the modal
        """
        super().__init__(**kwargs)
        self.prompt = prompt
        self.input_provider = input_provider
        self.title_text = title

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(f"[b]{self.title_text}[/b]", classes="title")
            yield Label(self.prompt, classes="prompt")
            yield Input(placeholder="Enter your response...")
            with Horizontal(classes="buttons"):
                yield Button("Submit", id="submit", variant="primary", classes="submit")
                yield Button("Cancel", id="cancel", classes="cancel")

    def on_mount(self) -> None:
        """Focus the input field when modal opens."""
        self.query_one(Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "submit":
            self.action_submit()
        else:
            self.action_cancel()

    def action_submit(self) -> None:
        """Submit the input."""
        input_widget = self.query_one(Input)
        value = input_widget.value.strip()

        # Provide input to the waiting thread
        self.input_provider.provide_input(value, value)
        self.dismiss()

    def action_cancel(self) -> None:
        """Cancel input."""
        self.input_provider.cancel_input()
        self.dismiss()
