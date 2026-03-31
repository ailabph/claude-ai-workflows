"""Chat view widget — scrollable message history with input area."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Input, Label, Static


class ChatView(Static):
    """Scrollable chat view with message history and input area.

    Shows messages with role coloring (user=green, assistant=cyan).
    Includes a thinking indicator and input field at the bottom.
    """

    DEFAULT_CSS = """
    ChatView {
        height: 1fr;
        layout: vertical;
    }
    ChatView #chat-scroll {
        height: 1fr;
    }
    ChatView .chat-user {
        color: #00ff41;
        margin: 0 0 1 0;
    }
    ChatView .chat-assistant {
        color: #00d9ff;
        margin: 0 0 1 0;
    }
    ChatView .chat-thinking {
        color: $text-muted;
        text-style: italic;
        margin: 0 0 1 0;
    }
    ChatView #chat-input-area {
        height: auto;
        max-height: 3;
        dock: bottom;
        border-top: solid $surface;
        padding: 0 1;
    }
    ChatView #chat-input {
        width: 100%;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._thinking_label: Label | None = None
        self._thinking_start: float | None = None
        self._scroll: VerticalScroll | None = None
        self._input: Input | None = None

    def compose(self) -> ComposeResult:
        self._scroll = VerticalScroll(id="chat-scroll")
        yield self._scroll
        with Vertical(id="chat-input-area"):
            self._input = Input(
                placeholder="Type a message... (Enter to send, Ctrl+D when done)",
                id="chat-input",
            )
            yield self._input

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the chat display.

        Args:
            role: 'user' or 'assistant'.
            content: Message text.
        """
        if role == "user":
            prefix = "[bold]You:[/bold] "
            css_class = "chat-user"
        else:
            prefix = "[bold]Claude:[/bold] "
            css_class = "chat-assistant"

        label = Label(f"{prefix}{content}", classes=css_class)
        if self._scroll is not None:
            self._scroll.mount(label)
            # Auto-scroll to bottom
            self._scroll.scroll_end(animate=False)

    def show_thinking(self) -> None:
        """Show the thinking indicator."""
        self._thinking_start = time.monotonic()
        self._thinking_label = Label(
            "[bold]Claude:[/bold] [thinking... 0s]",
            classes="chat-thinking",
            id="chat-thinking-indicator",
        )
        if self._scroll is not None:
            self._scroll.mount(self._thinking_label)
            self._scroll.scroll_end(animate=False)

    def update_thinking_elapsed(self) -> None:
        """Update the thinking indicator with elapsed time."""
        if self._thinking_label is not None and self._thinking_start is not None:
            elapsed = int(time.monotonic() - self._thinking_start)
            self._thinking_label.update(
                f"[bold]Claude:[/bold] [thinking... {elapsed}s]"
            )

    def clear_thinking(self) -> None:
        """Remove the thinking indicator."""
        if self._thinking_label is not None:
            try:
                self._thinking_label.remove()
            except Exception:
                pass
            self._thinking_label = None
            self._thinking_start = None

    def disable_input(self) -> None:
        """Disable the chat input field."""
        if self._input is not None:
            self._input.disabled = True

    def enable_input(self) -> None:
        """Enable the chat input field and focus it."""
        if self._input is not None:
            self._input.disabled = False
            self._input.focus()

    def get_input_value(self) -> str:
        """Get the current input field value."""
        if self._input is not None:
            return self._input.value
        return ""

    def clear_input(self) -> None:
        """Clear the input field."""
        if self._input is not None:
            self._input.value = ""

    @property
    def is_thinking(self) -> bool:
        """Whether the thinking indicator is currently shown."""
        return self._thinking_label is not None

    def load_messages(self, messages: list[dict]) -> None:
        """Load existing messages from DB on mount.

        Args:
            messages: List of dicts with 'role' and 'content' keys.
        """
        for msg in messages:
            self.add_message(msg["role"], msg["content"])
