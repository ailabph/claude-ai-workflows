"""
Agent toggle panel widget for compact mode - single panel with planner/executor toggle.
"""

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import RichLog, Static, Label
from textual.containers import Vertical, Horizontal
from typing import Optional


class AgentTogglePanel(Vertical):
    """
    Single agent output panel with toggle between planner and executor.

    Buffers output from both agents but only displays the active one.
    Press '[' for planner, ']' for executor.
    """

    DEFAULT_CSS = """
    AgentTogglePanel {
        border: solid $secondary;
        background: $background;
        height: 1fr;
    }

    AgentTogglePanel:focus-within {
        border: solid $primary;
    }

    AgentTogglePanel .toggle-header {
        dock: top;
        height: 1;
        background: $secondary;
        color: $text;
    }

    AgentTogglePanel .toggle-header-content {
        width: 100%;
        height: 1;
    }

    AgentTogglePanel .toggle-title {
        width: 1fr;
        padding: 0 1;
    }

    AgentTogglePanel .toggle-indicator {
        width: auto;
        padding: 0 1;
    }

    AgentTogglePanel .toggle-btn {
        width: 3;
        text-align: center;
    }

    AgentTogglePanel .toggle-btn-active {
        background: $primary;
        color: $background;
        text-style: bold;
    }

    AgentTogglePanel .toggle-btn-inactive {
        color: $text-muted;
    }

    AgentTogglePanel.planner-active .toggle-header {
        background: #00d7ff;
        color: black;
    }

    AgentTogglePanel.executor-active .toggle-header {
        background: #00ff00;
        color: black;
    }

    AgentTogglePanel .output-content {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._active_agent = "executor"  # Default to executor
        self._planner_buffer: list[str] = []
        self._executor_buffer: list[str] = []
        self._planner_agent_prefix_shown = False
        self._executor_agent_prefix_shown = False

        # Start with executor-active class
        self.add_class("executor-active")

    def compose(self) -> ComposeResult:
        """Compose the widget with header and content area."""
        with Horizontal(classes="toggle-header"):
            with Horizontal(classes="toggle-header-content"):
                yield Label(self._get_title(), classes="toggle-title", id="title")
                with Horizontal(classes="toggle-indicator"):
                    yield Label("[", classes="toggle-btn toggle-btn-inactive", id="btn-planner")
                    yield Label("]", classes="toggle-btn toggle-btn-active", id="btn-executor")

        yield RichLog(
            id="output-content",
            classes="output-content",
            highlight=True,
            markup=False,
            wrap=True,
            auto_scroll=True,
        )

    def _get_title(self) -> str:
        """Get the header title based on active agent."""
        if self._active_agent == "planner":
            return "PLANNER"
        return "EXECUTOR"

    def toggle_agent(self) -> None:
        """Switch between planner and executor view."""
        if self._active_agent == "executor":
            self.set_agent("planner")
        else:
            self.set_agent("executor")

    def set_agent(self, agent: str) -> None:
        """
        Set specific agent view ('planner' or 'executor').

        Args:
            agent: Agent name to display
        """
        if agent not in ("planner", "executor"):
            return  # Ignore invalid agents

        if agent == self._active_agent:
            return  # Already showing this agent

        # Update state
        old_agent = self._active_agent
        self._active_agent = agent

        # Update CSS classes
        self.remove_class(f"{old_agent}-active")
        self.add_class(f"{agent}-active")

        # Update button styling
        self._update_toggle_buttons()

        # Update title
        if self.is_mounted:
            try:
                self.query_one("#title", Label).update(self._get_title())
            except Exception:
                pass

        # Refresh display with buffered content
        self._refresh_display()

    def _update_toggle_buttons(self) -> None:
        """Update the toggle button styling."""
        if not self.is_mounted:
            return

        try:
            btn_planner = self.query_one("#btn-planner", Label)
            btn_executor = self.query_one("#btn-executor", Label)

            btn_planner.remove_class("toggle-btn-active", "toggle-btn-inactive")
            btn_executor.remove_class("toggle-btn-active", "toggle-btn-inactive")

            if self._active_agent == "planner":
                btn_planner.add_class("toggle-btn-active")
                btn_executor.add_class("toggle-btn-inactive")
            else:
                btn_planner.add_class("toggle-btn-inactive")
                btn_executor.add_class("toggle-btn-active")
        except Exception:
            pass

    def write_chunk(self, chunk: str, agent: str) -> None:
        """
        Buffer chunk and display if from active agent.

        Both agents' output is buffered so switching shows full history.

        Args:
            chunk: The text chunk to append
            agent: Name of the agent producing the output ('planner' or 'executor')
        """
        # Buffer to appropriate agent buffer
        if agent == "planner":
            self._planner_buffer.append(chunk)
        elif agent == "executor":
            self._executor_buffer.append(chunk)
        else:
            return  # Unknown agent

        # Only write to display if from active agent
        if agent == self._active_agent:
            self._write_to_display(chunk)

    def _write_to_display(self, chunk: str) -> None:
        """Write a chunk to the RichLog display."""
        try:
            content = self.query_one("#output-content", RichLog)
            content.write(chunk, scroll_end=True)
        except Exception:
            pass

    def _refresh_display(self) -> None:
        """Refresh display with buffered content from active agent."""
        if not self.is_mounted:
            return

        try:
            content = self.query_one("#output-content", RichLog)
            content.clear()

            # Get appropriate buffer
            buffer = self._planner_buffer if self._active_agent == "planner" else self._executor_buffer

            # Write all buffered content
            for chunk in buffer:
                content.write(chunk, scroll_end=False)

            # Scroll to end
            content.scroll_end(animate=False)
        except Exception:
            pass

    def get_active_agent(self) -> str:
        """Return currently active agent name."""
        return self._active_agent

    def clear_buffers(self) -> None:
        """Clear both agent buffers (for new session)."""
        self._planner_buffer = []
        self._executor_buffer = []
        self._planner_agent_prefix_shown = False
        self._executor_agent_prefix_shown = False

        if self.is_mounted:
            try:
                content = self.query_one("#output-content", RichLog)
                content.clear()
            except Exception:
                pass

    def clear_output(self) -> None:
        """Clear the current display and buffer for active agent."""
        if self._active_agent == "planner":
            self._planner_buffer = []
        else:
            self._executor_buffer = []

        if self.is_mounted:
            try:
                content = self.query_one("#output-content", RichLog)
                content.clear()
            except Exception:
                pass

    def write_message(self, message: str, style: str = "") -> None:
        """
        Write a complete message with optional styling.

        Args:
            message: The message to write
            style: Optional Rich style string (e.g., "bold green")
        """
        # Buffer the message for active agent
        if self._active_agent == "planner":
            self._planner_buffer.append(message)
        else:
            self._executor_buffer.append(message)

        try:
            content = self.query_one("#output-content", RichLog)
            if style:
                styled_text = Text(message, style=style)
                content.write(styled_text, scroll_end=True)
            else:
                content.write(message, scroll_end=True)
        except Exception:
            pass

    def write_separator(self) -> None:
        """Write a visual separator line."""
        separator = "─" * 60

        # Buffer for active agent
        if self._active_agent == "planner":
            self._planner_buffer.append(separator)
        else:
            self._executor_buffer.append(separator)

        try:
            content = self.query_one("#output-content", RichLog)
            styled = Text(separator, style="dim")
            content.write(styled, scroll_end=True)
        except Exception:
            pass

    def scroll_down(self, animate: bool = False) -> None:
        """Scroll the output content down."""
        try:
            content = self.query_one("#output-content", RichLog)
            content.scroll_down(animate=animate)
        except Exception:
            pass

    def scroll_up(self, animate: bool = False) -> None:
        """Scroll the output content up."""
        try:
            content = self.query_one("#output-content", RichLog)
            content.scroll_up(animate=animate)
        except Exception:
            pass
