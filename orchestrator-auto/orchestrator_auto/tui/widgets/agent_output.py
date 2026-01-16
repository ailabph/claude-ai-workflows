"""
Agent output widget for streaming agent responses.
"""

from textual.widgets import RichLog


class AgentOutput(RichLog):
    """
    Panel showing streaming agent output.

    Features:
    - Auto-scroll to bottom as new content arrives
    - Rich text formatting support
    - Syntax highlighting for code blocks
    """

    DEFAULT_CSS = """
    AgentOutput {
        border: solid $secondary;
        background: $background;
        height: 1fr;
        scrollbar-size: 1 1;
    }

    AgentOutput:focus {
        border: solid $primary;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            highlight=True,
            markup=True,
            wrap=True,
            auto_scroll=True,
            **kwargs
        )
        self._current_agent = ""

    def write_chunk(self, chunk: str, agent: str = "") -> None:
        """
        Write a streaming chunk to the output.

        Args:
            chunk: The text chunk to append
            agent: Name of the agent producing the output
        """
        # Add agent prefix if agent changed
        if agent and agent != self._current_agent:
            self._current_agent = agent
            self.write(f"\n[bold cyan]> {agent}:[/bold cyan]")

        # Write the chunk (RichLog.write handles the actual display)
        self.write(chunk, scroll_end=True)

    def write_message(self, message: str, style: str = "") -> None:
        """
        Write a complete message with optional styling.

        Args:
            message: The message to write
            style: Optional Rich style string (e.g., "bold green")
        """
        if style:
            self.write(f"[{style}]{message}[/{style}]", scroll_end=True)
        else:
            self.write(message, scroll_end=True)

    def write_separator(self) -> None:
        """Write a visual separator line."""
        self.write("[dim]" + "─" * 60 + "[/dim]", scroll_end=True)

    def clear_output(self) -> None:
        """Clear all output."""
        self.clear()
        self._current_agent = ""
