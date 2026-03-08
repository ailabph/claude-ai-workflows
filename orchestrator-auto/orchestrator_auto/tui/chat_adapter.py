"""
Thread-safe bridge from ChatBackend callbacks to TUI messages.

ChatAdapter receives callbacks from the ChatBackend (running in a worker thread)
and posts messages to the ChatTUIApp (running in the main thread) using
call_from_thread().
"""

from typing import Dict, Any, TYPE_CHECKING

from . import messages

if TYPE_CHECKING:
    from textual.app import App


class ChatAdapter:
    """Thread-safe bridge from ChatBackend callbacks to TUI messages."""

    def __init__(self, app: "App", bubble_id: str) -> None:
        self.app = app
        self.bubble_id = bubble_id

    def on_chunk(self, chunk: str) -> None:
        """Forward a streaming chunk to the TUI main thread."""
        self.app.call_from_thread(
            self.app.post_message,
            messages.ChatChunkReceived(chunk=chunk, bubble_id=self.bubble_id),
        )

    def on_response_complete(self, full_text: str, usage: Dict[str, Any]) -> None:
        """Forward response completion to the TUI main thread."""
        self.app.call_from_thread(
            self.app.post_message,
            messages.ChatResponseComplete(
                bubble_id=self.bubble_id, full_text=full_text, usage=usage
            ),
        )

    def on_notification(self, notification: Dict[str, Any]) -> None:
        """Forward a notification to the TUI main thread."""
        self.app.call_from_thread(
            self.app.post_message,
            messages.ChatNotification(notification=notification, bubble_id=self.bubble_id),
        )

    def on_tool_event(self, tool_name: str, tool_input: Dict[str, Any], tool_response: Any) -> None:
        """Forward a PostToolUse success event to the TUI main thread."""
        self.app.call_from_thread(
            self.app.post_message,
            messages.ChatToolEvent(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_response=tool_response,
                bubble_id=self.bubble_id,
            ),
        )
