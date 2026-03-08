"""
Chat message view widget — scrollable bubble history for chat-mode TUI.
"""

from uuid import uuid4

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Markdown, Static


class _UserBubble(Vertical):
    """A right-aligned user message bubble."""

    DEFAULT_CSS = """
    _UserBubble {
        width: 100%;
        align-horizontal: right;
        padding: 0 1;
        margin: 1 0;
    }
    _UserBubble .bubble-label {
        text-align: right;
        color: $accent;
        text-style: bold;
    }
    _UserBubble .bubble-content {
        text-align: right;
        padding: 0 1;
    }
    """

    def __init__(self, content: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._label_widget = Static("[bold cyan]\\[You][/bold cyan]", classes="bubble-label")
        self._content_widget = Static(content, classes="bubble-content")

    def compose(self) -> ComposeResult:
        yield self._label_widget
        yield self._content_widget


class _AssistantBubble(Vertical):
    """A left-aligned assistant message bubble with streaming support and Markdown."""

    DEFAULT_CSS = """
    _AssistantBubble {
        width: 100%;
        padding: 0 1;
        margin: 1 0;
    }
    _AssistantBubble .bubble-label {
        color: $success;
        text-style: bold;
    }
    _AssistantBubble .bubble-content {
        padding: 0 1;
    }
    _AssistantBubble .streaming-cursor {
        padding: 0 1;
    }
    """

    def __init__(self, bubble_id: str, **kwargs) -> None:
        super().__init__(id=bubble_id, **kwargs)
        self.bubble_id = bubble_id
        self._text = ""
        self._streaming = True
        self._label_widget = Static("[bold green]\\[Planner][/bold green]", classes="bubble-label")
        self._content_widget = Markdown("", classes="bubble-content")
        self._cursor_widget = Static(" \u258c", classes="streaming-cursor")

    def compose(self) -> ComposeResult:
        yield self._label_widget
        yield self._content_widget
        yield self._cursor_widget

    def append_chunk(self, chunk: str) -> None:
        """Append a text chunk to the bubble content."""
        self._text += chunk
        self._content_widget.update(self._text)

    def finalize(self) -> None:
        """Remove the streaming cursor and do a final Markdown render."""
        self._streaming = False
        self._content_widget.update(self._text)
        self._cursor_widget.update("")

    @property
    def text(self) -> str:
        return self._text


class ChatMessageView(ScrollableContainer):
    """Scrollable chat history with user and assistant bubbles."""

    DEFAULT_CSS = """
    ChatMessageView {
        height: 1fr;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._bubbles: dict[str, _AssistantBubble] = {}

    def append_user_message(self, content: str) -> None:
        """Mount a new user bubble."""
        bubble = _UserBubble(content)
        self.mount(bubble)
        self.scroll_end(animate=False)

    def begin_assistant_message(self) -> str:
        """Mount an empty assistant bubble and return its bubble_id."""
        bubble_id = f"bubble-{uuid4().hex[:8]}"
        bubble = _AssistantBubble(bubble_id)
        self._bubbles[bubble_id] = bubble
        self.mount(bubble)
        self.scroll_end(animate=False)
        return bubble_id

    def append_chunk(self, bubble_id: str, chunk: str) -> None:
        """Append text to the in-progress assistant bubble."""
        bubble = self._bubbles.get(bubble_id)
        if bubble is not None:
            bubble.append_chunk(chunk)
            self.scroll_end(animate=False)

    def finalize_assistant_message(self, bubble_id: str) -> None:
        """Remove streaming cursor and mark bubble complete."""
        bubble = self._bubbles.get(bubble_id)
        if bubble is not None:
            bubble.finalize()

    def clear_messages(self) -> None:
        """Remove all bubbles."""
        self._bubbles.clear()
        self.remove_children()
