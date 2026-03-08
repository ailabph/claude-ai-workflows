"""
Chat input bar widget — text input + Send button for chat-mode TUI.
"""

from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import Button, TextArea
from textual.widget import Widget


class ChatInputBar(Widget):
    """Text input with a Send button. Posts SendMessage on submit."""

    class SendMessage(Message):
        """Posted when the user submits a message."""

        def __init__(self, content: str) -> None:
            self.content = content
            super().__init__()

    DEFAULT_CSS = """
    ChatInputBar {
        height: auto;
        max-height: 8;
        layout: horizontal;
        padding: 0 1;
        border-top: solid $primary;
    }
    ChatInputBar TextArea {
        width: 1fr;
        height: auto;
        min-height: 1;
        max-height: 6;
    }
    ChatInputBar Button {
        width: 10;
        height: 3;
        margin-left: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._disabled_state = False

    def compose(self) -> ComposeResult:
        yield TextArea(id="chat-input")
        yield Button("Send", id="send-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            self._submit()

    def on_key(self, event) -> None:
        if event.key == "ctrl+enter":
            self._submit()

    def _submit(self) -> None:
        if self._disabled_state:
            return
        ta = self.query_one("#chat-input", TextArea)
        content = ta.text.strip()
        if content:
            ta.clear()
            self.post_message(self.SendMessage(content=content))

    @property
    def disabled(self) -> bool:
        return self._disabled_state

    @disabled.setter
    def disabled(self, value: bool) -> None:
        self._disabled_state = value
        try:
            btn = self.query_one("#send-btn", Button)
            btn.disabled = value
            ta = self.query_one("#chat-input", TextArea)
            ta.disabled = value
        except Exception:
            pass
