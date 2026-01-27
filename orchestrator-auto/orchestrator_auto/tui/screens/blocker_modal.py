"""
Blocker modal screen for displaying full blocker questions.

Shows the complete blocker question with option to respond.
"""

from datetime import datetime
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static, Label, Button
from typing import Optional


class BlockerModal(ModalScreen):
    """
    Modal screen showing the full blocker question.

    Press Escape or 'q' to close.
    Press 'r' or click Respond to respond to the blocker.
    """

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("q", "close", "Close"),
        Binding("r", "respond", "Respond"),
    ]

    CSS = """
    BlockerModal {
        align: center middle;
    }

    BlockerModal > Vertical {
        width: 80;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: heavy $warning;
        padding: 1 2;
    }

    BlockerModal .blocker-title {
        text-align: center;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }

    BlockerModal .blocker-meta {
        color: $text-muted;
        margin-bottom: 1;
    }

    BlockerModal .blocker-agent {
        color: $accent;
        text-style: bold;
    }

    BlockerModal .blocker-session {
        color: $text-muted;
    }

    BlockerModal .blocker-question-container {
        height: auto;
        max-height: 20;
        border: round $panel;
        padding: 1;
        margin-bottom: 1;
    }

    BlockerModal .blocker-question {
        color: $text;
    }

    BlockerModal .blocker-footer {
        height: 3;
        align: center middle;
    }

    BlockerModal Button {
        margin: 0 1;
    }

    BlockerModal #respond-btn {
        background: $warning;
    }
    """

    def __init__(
        self,
        question: str,
        session_id: str,
        agent: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Initialize blocker modal.

        Args:
            question: The full blocker question text
            session_id: The session ID
            agent: The agent that raised the blocker (planner/executor)
            timestamp: When the blocker was raised
        """
        super().__init__()
        self.question = question
        self.session_id = session_id
        self.agent = agent or "unknown"
        self.timestamp = timestamp

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("⚠ BLOCKER", classes="blocker-title")

            # Metadata row
            with Horizontal(classes="blocker-meta"):
                yield Label(f"Agent: ", classes="blocker-session")
                yield Label(self.agent.upper(), classes="blocker-agent")
                yield Label(f"  |  Session: {self.session_id[:8]}...", classes="blocker-session")
                if self.timestamp:
                    time_str = self.timestamp.strftime("%H:%M:%S")
                    yield Label(f"  |  {time_str}", classes="blocker-session")

            # Scrollable question container
            with VerticalScroll(classes="blocker-question-container"):
                yield Static(self.question, classes="blocker-question")

            # Footer with buttons
            with Horizontal(classes="blocker-footer"):
                yield Button("Respond [r]", id="respond-btn", variant="warning")
                yield Button("Close [Esc]", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "respond-btn":
            self.action_respond()
        elif event.button.id == "close-btn":
            self.action_close()

    def action_close(self) -> None:
        """Close the modal."""
        self.dismiss(False)

    def action_respond(self) -> None:
        """Respond to the blocker."""
        self.dismiss(True)
