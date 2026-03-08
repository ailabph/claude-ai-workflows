"""
Chat-mode TUI application.

Provides a dedicated chat interface for direct conversation with the Planner agent.
"""

from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Header, Footer, Button, Label, Static
from textual.worker import Worker

from .widgets.chat_message_view import ChatMessageView
from .widgets.chat_input_bar import ChatInputBar
from .widgets.verbose_panel import VerbosePanel
from .messages import (
    ChatChunkReceived,
    ChatResponseComplete,
    ChatNotification,
    ChatToolEvent,
    ChatSendFailed,
)


class HelpModal(ModalScreen):
    """Modal screen listing all keyboard shortcuts."""

    DEFAULT_CSS = """
    HelpModal {
        align: center middle;
    }
    HelpModal > Container {
        width: 60;
        height: auto;
        max-height: 24;
        background: $surface;
        border: heavy $primary;
        padding: 1 2;
    }
    HelpModal .help-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    HelpModal .help-row {
        height: 1;
        margin: 0;
    }
    HelpModal .help-key {
        width: 20;
        text-style: bold;
        color: $warning;
    }
    HelpModal .help-desc {
        width: 1fr;
    }
    HelpModal .help-footer {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("f1", "dismiss", "Close"),
    ]

    SHORTCUTS = [
        ("Ctrl+Enter", "Send message"),
        ("Enter", "Add newline in input"),
        ("Ctrl+C / Q", "Quit (with confirm)"),
        ("Ctrl+L", "Clear chat"),
        ("F1", "Toggle this help screen"),
        ("F2", "Toggle verbose panel"),
        ("Tab", "Cycle focus: input / verbose"),
        ("PgUp / PgDn", "Scroll chat history"),
        ("Ctrl+Home", "Scroll to top of chat"),
        ("Ctrl+End", "Scroll to bottom of chat"),
        ("/clear", "Clear chat (in input)"),
    ]

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("[b]Keyboard Shortcuts[/b]", classes="help-title")
            for key, desc in self.SHORTCUTS:
                with Horizontal(classes="help-row"):
                    yield Static(key, classes="help-key")
                    yield Static(desc, classes="help-desc")
            yield Label("Press Escape or F1 to close", classes="help-footer")

    def action_dismiss(self) -> None:
        self.dismiss(None)


class ConfirmModal(ModalScreen[bool]):
    """Modal screen for yes/no confirmation."""

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
    }
    ConfirmModal > Container {
        width: 45;
        height: auto;
        background: $surface;
        border: heavy $primary;
        padding: 1 2;
    }
    ConfirmModal .confirm-prompt {
        text-align: center;
        margin-bottom: 1;
    }
    ConfirmModal .confirm-buttons {
        align: center middle;
        margin-top: 1;
    }
    ConfirmModal Button {
        margin: 0 1;
        min-width: 10;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, prompt: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(self._prompt, classes="confirm-prompt")
            with Horizontal(classes="confirm-buttons"):
                yield Button("Yes", id="confirm-yes", variant="error")
                yield Button("No", id="confirm-no", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#confirm-no").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-yes":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)


class ChatTUIApp(App):
    """TUI chat application for direct freeform chat with the Planner agent."""

    TITLE = "Chat Mode"
    SUB_TITLE = "Planner Agent"

    CSS = """
    Screen {
        layout: vertical;
    }
    #main-area {
        height: 1fr;
    }
    #chat-view {
        width: 1fr;
    }
    #verbose-panel {
        width: 35;
        min-width: 20;
    }
    #input-bar {
        height: auto;
    }

    Screen.layout-small #input-bar {
        layout: vertical;
    }
    Screen.layout-small #input-bar TextArea {
        width: 100%;
    }
    Screen.layout-small #input-bar Button {
        width: 100%;
        margin-left: 0;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("q", "quit", "Quit", show=False),
        Binding("f1", "show_help", "Help"),
        Binding("f2", "toggle_verbose", "Verbose"),
        Binding("ctrl+l", "clear_chat", "Clear"),
        Binding("tab", "focus_cycle", "Focus", show=False),
        Binding("pageup", "scroll_up_chat", "PgUp", show=False),
        Binding("pagedown", "scroll_down_chat", "PgDn", show=False),
        Binding("ctrl+home", "scroll_top_chat", show=False),
        Binding("ctrl+end", "scroll_bottom_chat", show=False),
    ]

    def __init__(
        self,
        model: str = "opus",
        verbose: bool = False,
        system_prompt: Optional[str] = None,
        tools_enabled: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._model = model
        self._verbose = verbose
        self._system_prompt = system_prompt
        self._tools_enabled = tools_enabled
        self._current_bubble_id: Optional[str] = None
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._total_cost: float = 0.0
        self._backend = None
        self._active_worker: Optional[Worker] = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        if self._verbose:
            with Horizontal(id="main-area"):
                yield ChatMessageView(id="chat-view")
                yield VerbosePanel(id="verbose-panel")
        else:
            yield ChatMessageView(id="chat-view")
        yield ChatInputBar(id="input-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Create backend and focus the input on startup."""
        from ..chat_backend import ChatBackend

        self._backend = ChatBackend(
            model=self._model,
            system_prompt=self._system_prompt,
            tools_enabled=self._tools_enabled,
        )
        self._apply_responsive_layout()
        try:
            self.query_one("#chat-input").focus()
        except Exception:
            pass

    def on_resize(self, event) -> None:
        """Apply responsive layout on resize."""
        self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        width = self.size.width
        self.screen.remove_class("layout-small")
        if width < 80:
            self.screen.add_class("layout-small")

    def on_chat_input_bar_send_message(self, event: ChatInputBar.SendMessage) -> None:
        """Handle user sending a message."""
        self._handle_user_message(event.content)

    def _handle_user_message(self, content: str) -> None:
        """Append user bubble, lock input, start worker thread for backend call."""
        # Intercept /clear command before sending to backend
        if content.strip() == "/clear":
            self.action_clear_chat()
            return

        view = self.query_one("#chat-view", ChatMessageView)
        view.append_user_message(content)
        bubble_id = view.begin_assistant_message()
        self._current_bubble_id = bubble_id

        # Lock input during streaming
        self.query_one("#input-bar", ChatInputBar).disabled = True

        # Create adapter with per-message bubble_id and wire callbacks
        from .chat_adapter import ChatAdapter

        adapter = ChatAdapter(self, bubble_id)

        # Wire notification/tool_event via instance attrs (used by agent factory lambdas)
        self._backend.on_notification = adapter.on_notification
        self._backend.on_tool_event = adapter.on_tool_event

        def _run_send(bid: str, msg: str, adp: ChatAdapter) -> None:
            try:
                self._backend.send(
                    msg,
                    on_chunk=adp.on_chunk,
                    on_response_complete=adp.on_response_complete,
                )
            except Exception as exc:
                self.call_from_thread(
                    self.post_message,
                    ChatSendFailed(bubble_id=bid, error=str(exc)),
                )

        self._active_worker = self.run_worker(
            lambda: _run_send(bubble_id, content, adapter),
            thread=True,
            name="chat-send",
        )

    def on_chat_chunk_received(self, event: ChatChunkReceived) -> None:
        """Append streaming chunk to the assistant bubble."""
        view = self.query_one("#chat-view", ChatMessageView)
        view.append_chunk(event.bubble_id, event.chunk)
        view.scroll_end(animate=False)

    def _cancel_active_worker(self) -> None:
        """Cancel the in-flight worker if any."""
        if self._active_worker is not None:
            try:
                self._active_worker.cancel()
            except Exception:
                pass
            self._active_worker = None

    def on_chat_response_complete(self, event: ChatResponseComplete) -> None:
        """Finalize bubble, update stats, re-enable input."""
        if event.bubble_id != self._current_bubble_id:
            return  # Stale completion from a cleared/cancelled request
        view = self.query_one("#chat-view", ChatMessageView)
        view.finalize_assistant_message(event.bubble_id)
        self._current_bubble_id = None
        self._active_worker = None

        # Update token stats
        usage = event.usage or {}
        self._total_input_tokens += usage.get("input_tokens", 0)
        self._total_output_tokens += usage.get("output_tokens", 0)
        self._total_cost += usage.get("cost_usd", 0.0)
        self._update_subtitle()

        # Re-enable input and refocus
        input_bar = self.query_one("#input-bar", ChatInputBar)
        input_bar.disabled = False
        try:
            self.query_one("#chat-input").focus()
        except Exception:
            pass

    def on_chat_send_failed(self, event: ChatSendFailed) -> None:
        """Handle backend send() failure: finalize bubble, show error, re-enable input."""
        if event.bubble_id != self._current_bubble_id:
            return  # Stale failure from a cleared/cancelled request
        view = self.query_one("#chat-view", ChatMessageView)
        view.finalize_assistant_message(event.bubble_id)
        self._current_bubble_id = None
        self._active_worker = None
        # Show error as a user-visible message
        view.append_user_message(f"[Error] {event.error}")
        # Re-enable input
        input_bar = self.query_one("#input-bar", ChatInputBar)
        input_bar.disabled = False
        try:
            self.query_one("#chat-input").focus()
        except Exception:
            pass

    def on_chat_notification(self, event: ChatNotification) -> None:
        """Forward notification to verbose panel if present."""
        try:
            panel = self.query_one("#verbose-panel", VerbosePanel)
            panel.add_notification(
                event.notification.get("message", ""),
                event.notification.get("type", "info"),
            )
        except Exception:
            pass

    def on_chat_tool_event(self, event: ChatToolEvent) -> None:
        """Forward tool event to verbose panel if present."""
        try:
            panel = self.query_one("#verbose-panel", VerbosePanel)
            result_str = str(event.tool_response)[:80] if event.tool_response else None
            panel.add_tool_event(event.tool_name, event.tool_input, result_str)
        except Exception:
            pass

    def _update_subtitle(self) -> None:
        """Update header subtitle with token count and cost."""
        total = self._total_input_tokens + self._total_output_tokens
        self.sub_title = f"Tokens: {total:,} | Cost: ${self._total_cost:.4f}"

    def action_quit(self) -> None:
        """Quit with confirmation."""
        def _on_quit_confirmed(confirmed: bool) -> None:
            if confirmed:
                self._cancel_active_worker()
                try:
                    self._backend.reset()
                except Exception:
                    pass
                self.exit()

        self.push_screen(ConfirmModal("End chat session?"), _on_quit_confirmed)

    def action_show_help(self) -> None:
        """Toggle the help overlay."""
        self.push_screen(HelpModal())

    def action_toggle_verbose(self) -> None:
        """Toggle verbose panel visibility."""
        try:
            panel = self.query_one("#verbose-panel", VerbosePanel)
            panel.display = not panel.display
        except Exception:
            pass

    def action_clear_chat(self) -> None:
        """Clear all chat messages and reset backend conversation context."""
        self._cancel_active_worker()
        view = self.query_one("#chat-view", ChatMessageView)
        view.clear_messages()
        self._current_bubble_id = None
        # Reset backend conversation history
        if self._backend is not None:
            self._backend.reset()
        # Re-enable input in case clear happens mid-stream
        self.query_one("#input-bar", ChatInputBar).disabled = False
        # Also clear verbose panel if present
        try:
            panel = self.query_one("#verbose-panel", VerbosePanel)
            panel.clear_events()
        except Exception:
            pass

    def action_focus_cycle(self) -> None:
        """Cycle focus between input and verbose panel."""
        try:
            chat_input = self.query_one("#chat-input")
            if chat_input.has_focus:
                # Try to focus verbose panel if visible
                try:
                    panel = self.query_one("#verbose-panel", VerbosePanel)
                    if panel.display:
                        panel.focus()
                        return
                except Exception:
                    pass
            # Default: focus back to input
            chat_input.focus()
        except Exception:
            pass

    def action_scroll_up_chat(self) -> None:
        """Scroll chat history up by one page."""
        view = self.query_one("#chat-view", ChatMessageView)
        view.scroll_page_up(animate=False)

    def action_scroll_down_chat(self) -> None:
        """Scroll chat history down by one page."""
        view = self.query_one("#chat-view", ChatMessageView)
        view.scroll_page_down(animate=False)

    def action_scroll_top_chat(self) -> None:
        """Scroll to top of chat history."""
        view = self.query_one("#chat-view", ChatMessageView)
        view.scroll_home(animate=False)

    def action_scroll_bottom_chat(self) -> None:
        """Scroll to bottom of chat history."""
        view = self.query_one("#chat-view", ChatMessageView)
        view.scroll_end(animate=False)
