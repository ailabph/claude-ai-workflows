"""
Agent output widget for streaming agent responses.

Uses markup=False to safely display agent output that may contain
orchestrator tags like [PROGRESS_REPORT] which would otherwise be
parsed as Rich markup and cause MarkupError.
"""

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import RichLog, Static
from textual.containers import Vertical
from typing import Optional


class AgentOutput(Vertical):
    """
    Panel showing streaming agent output with optional filtering.

    Features:
    - Auto-scroll to bottom as new content arrives
    - Safe handling of orchestrator tags (markup=False)
    - Syntax highlighting for code blocks
    - Styled output via rich.text.Text objects
    - Optional agent filtering (planner/executor)
    - Custom header with color coding
    """

    DEFAULT_CSS = """
    AgentOutput {
        border: solid $secondary;
        background: $background;
        height: 1fr;
    }

    AgentOutput:focus-within {
        border: solid $primary;
    }

    AgentOutput .output-header {
        dock: top;
        height: 1;
        background: $secondary;
        color: $text;
        text-align: center;
        padding: 0 1;
    }

    AgentOutput.planner-output .output-header {
        background: #00d7ff;
        color: black;
    }

    AgentOutput.executor-output .output-header {
        background: #00ff00;
        color: black;
    }

    AgentOutput .output-content {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """

    def __init__(
        self,
        agent_filter: Optional[str] = None,
        header_title: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Initialize the AgentOutput widget.

        Args:
            agent_filter: Optional agent name to filter output ("planner" or "executor")
            header_title: Optional header title to display (defaults to agent_filter)
            **kwargs: Additional arguments passed to parent container
        """
        super().__init__(**kwargs)
        self._agent_filter = agent_filter
        self._header_title = header_title or (agent_filter.upper() if agent_filter else "AGENT OUTPUT")
        self._current_agent = ""

        # Add CSS class for styling based on agent
        if agent_filter == "planner":
            self.add_class("planner-output")
        elif agent_filter == "executor":
            self.add_class("executor-output")

    def compose(self) -> ComposeResult:
        """Compose the widget with header and content area."""
        yield Static(self._header_title, classes="output-header")
        yield RichLog(
            id=f"{self.id}-content" if self.id else "output-content",
            classes="output-content",
            highlight=True,
            markup=False,  # Disable markup to safely display agent tags
            wrap=True,
            auto_scroll=True,
        )

    def write_chunk(self, chunk: str, agent: str = "") -> None:
        """
        Write a streaming chunk to the output.

        Args:
            chunk: The text chunk to append
            agent: Name of the agent producing the output
        """
        # Filter based on agent if filter is set
        if self._agent_filter and agent and agent != self._agent_filter:
            return  # Skip chunks from other agents

        try:
            # Get the RichLog content widget
            content = self.query_one(".output-content", RichLog)

            # Add agent prefix if agent changed (only when not filtering)
            if not self._agent_filter and agent and agent != self._current_agent:
                self._current_agent = agent
                # Use Text object for styling since markup=False
                prefix = Text()
                prefix.append("\n")
                prefix.append(f"> {agent}:", style="bold cyan")
                content.write(prefix)

            # Write the chunk (RichLog.write handles the actual display)
            content.write(chunk, scroll_end=True)
        except Exception:
            # Defensive fallback: write plain text if anything fails
            try:
                content = self.query_one(".output-content", RichLog)
                content.write(str(chunk), scroll_end=True)
            except Exception:
                pass  # Last resort: silently skip to avoid crashing TUI

    def write_message(self, message: str, style: str = "") -> None:
        """
        Write a complete message with optional styling.

        Args:
            message: The message to write
            style: Optional Rich style string (e.g., "bold green")
        """
        try:
            content = self.query_one(".output-content", RichLog)
            if style:
                # Use Text object for styling since markup=False
                styled_text = Text(message, style=style)
                content.write(styled_text, scroll_end=True)
            else:
                content.write(message, scroll_end=True)
        except Exception:
            # Defensive fallback: write plain text if styling fails
            try:
                content = self.query_one(".output-content", RichLog)
                content.write(str(message), scroll_end=True)
            except Exception:
                pass

    def write_separator(self) -> None:
        """Write a visual separator line."""
        try:
            content = self.query_one(".output-content", RichLog)
            separator = Text("─" * 60, style="dim")
            content.write(separator, scroll_end=True)
        except Exception:
            try:
                content = self.query_one(".output-content", RichLog)
                content.write("-" * 60, scroll_end=True)
            except Exception:
                pass

    def clear_output(self) -> None:
        """Clear all output."""
        try:
            content = self.query_one(".output-content", RichLog)
            content.clear()
            self._current_agent = ""
        except Exception:
            pass

    def scroll_down(self, animate: bool = False) -> None:
        """Scroll the output content down."""
        content = self.query_one(".output-content", RichLog)
        content.scroll_down(animate=animate)

    def scroll_up(self, animate: bool = False) -> None:
        """Scroll the output content up."""
        content = self.query_one(".output-content", RichLog)
        content.scroll_up(animate=animate)
