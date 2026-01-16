"""
Agent output widget for streaming agent responses.

Uses markup=False to safely display agent output that may contain
orchestrator tags like [PROGRESS_REPORT] which would otherwise be
parsed as Rich markup and cause MarkupError.
"""

from rich.text import Text
from textual.widgets import RichLog


class AgentOutput(RichLog):
    """
    Panel showing streaming agent output.

    Features:
    - Auto-scroll to bottom as new content arrives
    - Safe handling of orchestrator tags (markup=False)
    - Syntax highlighting for code blocks
    - Styled output via rich.text.Text objects
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
            markup=False,  # Disable markup to safely display agent tags
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
        try:
            # Add agent prefix if agent changed
            if agent and agent != self._current_agent:
                self._current_agent = agent
                # Use Text object for styling since markup=False
                prefix = Text()
                prefix.append("\n")
                prefix.append(f"> {agent}:", style="bold cyan")
                self.write(prefix)

            # Write the chunk (RichLog.write handles the actual display)
            self.write(chunk, scroll_end=True)
        except Exception:
            # Defensive fallback: write plain text if anything fails
            try:
                self.write(str(chunk), scroll_end=True)
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
            if style:
                # Use Text object for styling since markup=False
                styled_text = Text(message, style=style)
                self.write(styled_text, scroll_end=True)
            else:
                self.write(message, scroll_end=True)
        except Exception:
            # Defensive fallback: write plain text if styling fails
            try:
                self.write(str(message), scroll_end=True)
            except Exception:
                pass

    def write_separator(self) -> None:
        """Write a visual separator line."""
        try:
            separator = Text("─" * 60, style="dim")
            self.write(separator, scroll_end=True)
        except Exception:
            try:
                self.write("-" * 60, scroll_end=True)
            except Exception:
                pass

    def clear_output(self) -> None:
        """Clear all output."""
        self.clear()
        self._current_agent = ""
