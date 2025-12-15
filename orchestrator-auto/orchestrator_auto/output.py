"""
Output utilities for orchestrator-auto.

Provides streaming activity indicators and throttled output handlers.
"""

import time
import sys
from typing import Optional, Callable


class StreamingIndicator:
    """
    Throttled streaming output for activity indication.

    Shows periodic snippets of agent responses to indicate progress
    without flooding the terminal with full output.

    Usage:
        indicator = StreamingIndicator(interval=1.5)

        response = agent.send_message(
            prompt,
            on_chunk=indicator.on_chunk
        )

        indicator.finish()
    """

    def __init__(
        self,
        interval: float = 1.5,
        snippet_length: int = 50,
        show_tokens: bool = True,
        output_func: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize the streaming indicator.

        Args:
            interval: Minimum seconds between updates (default: 1.5)
            snippet_length: Max characters to show in snippet (default: 50)
            show_tokens: Whether to show token count (default: True)
            output_func: Custom output function (default: print to stderr)
        """
        self.interval = interval
        self.snippet_length = snippet_length
        self.show_tokens = show_tokens
        self.output_func = output_func or self._default_output

        # State
        self.last_output_time: float = 0
        self.buffer: str = ""
        self.token_count: int = 0
        self._active: bool = False

    def _default_output(self, text: str) -> None:
        """Default output to stderr with carriage return."""
        sys.stderr.write(text)
        sys.stderr.flush()

    def on_chunk(self, text: str) -> None:
        """
        Handle incoming text chunk from streaming response.

        Args:
            text: Text chunk from agent response
        """
        self.buffer += text
        self.token_count += len(text.split())
        self._active = True

        now = time.time()
        if now - self.last_output_time >= self.interval:
            self._display_snippet()
            self.last_output_time = now

    def _display_snippet(self) -> None:
        """Display current snippet with progress info."""
        if not self.buffer:
            return

        # Get last N characters, clean up for display
        snippet = self.buffer[-self.snippet_length:]
        snippet = snippet.replace('\n', ' ').replace('\r', '').strip()

        # Truncate if needed and add ellipsis
        if len(snippet) > self.snippet_length:
            snippet = snippet[-self.snippet_length:]

        # Build output line
        if self.show_tokens:
            line = f"\r\033[K⏳ [{self.token_count} tokens] ...{snippet}"
        else:
            line = f"\r\033[K⏳ ...{snippet}"

        self.output_func(line)

    def finish(self) -> None:
        """Clear the indicator line and reset state."""
        if self._active:
            # Clear the line
            self.output_func("\r\033[K")
            self._active = False

    def reset(self) -> None:
        """Reset the indicator state for reuse."""
        self.buffer = ""
        self.token_count = 0
        self.last_output_time = 0
        self._active = False


def create_activity_indicator(
    enabled: bool = True,
    interval: float = 1.5,
    show_tokens: bool = True,
) -> Optional[StreamingIndicator]:
    """
    Factory function to create an activity indicator.

    Args:
        enabled: Whether to create an indicator (if False, returns None)
        interval: Seconds between updates
        show_tokens: Whether to show token count

    Returns:
        StreamingIndicator instance or None if disabled
    """
    if not enabled:
        return None

    return StreamingIndicator(
        interval=interval,
        show_tokens=show_tokens,
    )
