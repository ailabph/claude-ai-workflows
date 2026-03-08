"""
Verbose panel widget — displays tool calls and notifications for chat-mode TUI.

Only mounted when --verbose flag is set. Shows real-time tool usage and
notification events from the agent in a scrollable sidebar.
"""

from typing import Dict, Optional

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static


class VerbosePanel(VerticalScroll):
    """Displays tool calls and notifications when --verbose is active."""

    DEFAULT_CSS = """
    VerbosePanel {
        width: 35;
        min-width: 20;
        border-left: solid $panel;
        padding: 0 1;
    }
    VerbosePanel .verbose-header {
        height: 1;
        color: $text;
        text-style: bold;
        margin-bottom: 1;
    }
    VerbosePanel .tool-entry {
        color: $text-muted;
        margin-bottom: 1;
    }
    VerbosePanel .notif-entry {
        color: $accent;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("VERBOSE", classes="verbose-header")

    def add_tool_event(
        self, tool_name: str, tool_input: Dict, result: Optional[str] = None
    ) -> None:
        """Append a tool call entry."""
        # Format key=value pairs from tool_input (truncate long values)
        parts = []
        for k, v in tool_input.items():
            val_str = str(v)
            if len(val_str) > 40:
                val_str = val_str[:37] + "..."
            parts.append(f"   {k}: {val_str}")
        params = "\n".join(parts) if parts else "   (no params)"

        result_line = ""
        if result is not None:
            result_str = str(result)
            if len(result_str) > 60:
                result_str = result_str[:57] + "..."
            result_line = f"\n   -> {result_str}"

        entry = Static(
            f"[bold $warning]T[/] {tool_name}\n{params}{result_line}",
            classes="tool-entry",
        )
        self.mount(entry)
        self.scroll_end(animate=False)

    def add_notification(self, message: str, level: str = "info") -> None:
        """Append a notification entry."""
        entry = Static(f"[bold $accent]N[/] {message}", classes="notif-entry")
        self.mount(entry)
        self.scroll_end(animate=False)

    def clear_events(self) -> None:
        """Clear all entries except the header."""
        for child in list(self.children):
            if "verbose-header" not in child.classes:
                child.remove()
