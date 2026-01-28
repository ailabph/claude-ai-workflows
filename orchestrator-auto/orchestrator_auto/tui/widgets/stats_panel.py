"""
Stats panel widget - compact statistics display for watch mode.
"""

from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.containers import Vertical


class StatsPanel(Static):
    """
    Compact statistics panel for Layout B.

    Displays:
    - Token count and estimated cost
    - API call count and elapsed time
    """

    DEFAULT_CSS = """
    StatsPanel {
        height: auto;
        min-height: 4;
        padding: 0 1;
        border: solid $border;
    }

    StatsPanel .stats-title {
        height: 1;
        color: $text;
        text-style: bold;
        border-bottom: solid $border;
        margin-bottom: 1;
    }

    StatsPanel .stats-row {
        height: 1;
        color: $text;
    }

    StatsPanel .stats-label {
        color: $text-muted;
    }

    StatsPanel .stats-value {
        color: $text;
    }

    StatsPanel .stats-tokens {
        color: $primary;
    }

    StatsPanel .stats-cost {
        color: $success;
    }
    """

    def __init__(self, show_title: bool = True, **kwargs) -> None:
        """
        Initialize stats panel.

        Args:
            show_title: Whether to show "STATS" title
        """
        super().__init__(**kwargs)
        self._show_title = show_title
        self._tokens: int = 0
        self._cost: float = 0.0
        self._api_calls: int = 0
        self._elapsed: str = "00:00"
        self._elapsed_seconds: int = 0

    def compose(self) -> ComposeResult:
        with Vertical():
            if self._show_title:
                yield Label("STATS", classes="stats-title")
            yield Label(
                self._format_tokens_cost(),
                classes="stats-row",
                id="tokens-cost",
            )
            yield Label(
                self._format_calls_time(),
                classes="stats-row",
                id="calls-time",
            )

    def update_stats(
        self,
        tokens: int = None,
        cost: float = None,
        api_calls: int = None,
        elapsed: str = None,
    ) -> None:
        """
        Update statistics display.

        Args:
            tokens: Total token count
            cost: Estimated cost in USD
            api_calls: Number of API calls
            elapsed: Elapsed time as "MM:SS" or "HH:MM:SS"
        """
        if tokens is not None:
            self._tokens = tokens
        if cost is not None:
            self._cost = cost
        if api_calls is not None:
            self._api_calls = api_calls
        if elapsed is not None:
            self._elapsed = elapsed

        self._refresh_display()

    def add_tokens(self, input_tokens: int = 0, output_tokens: int = 0, cost: float = 0.0) -> None:
        """
        Add tokens from a single API call.

        Args:
            input_tokens: Input tokens used
            output_tokens: Output tokens used
            cost: Cost for this call
        """
        self._tokens += input_tokens + output_tokens
        self._cost += cost
        self._api_calls += 1
        self._refresh_display()

    def set_elapsed(self, seconds: int) -> None:
        """
        Set elapsed time from seconds.

        Args:
            seconds: Elapsed seconds
        """
        self._elapsed_seconds = seconds
        self._format_elapsed_from_seconds()
        self._refresh_display()

    def tick_elapsed(self) -> None:
        """Increment elapsed time by 1 second."""
        self._elapsed_seconds += 1
        self._format_elapsed_from_seconds()
        self._refresh_display()

    def _format_elapsed_from_seconds(self) -> None:
        """Format elapsed string from internal seconds counter."""
        seconds = self._elapsed_seconds
        if seconds >= 3600:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            secs = seconds % 60
            self._elapsed = f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            minutes = seconds // 60
            secs = seconds % 60
            self._elapsed = f"{minutes:02d}:{secs:02d}"

    def reset(self) -> None:
        """Reset all statistics."""
        self._tokens = 0
        self._cost = 0.0
        self._api_calls = 0
        self._elapsed = "00:00"
        self._elapsed_seconds = 0
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh display elements."""
        if not self.is_mounted:
            return

        try:
            self.query_one("#tokens-cost", Label).update(self._format_tokens_cost())
            self.query_one("#calls-time", Label).update(self._format_calls_time())
        except Exception:
            pass

    def _format_tokens_cost(self) -> str:
        """Format tokens and cost line."""
        # Format tokens with K suffix for large numbers
        if self._tokens >= 1000:
            tokens_str = f"{self._tokens / 1000:.1f}K"
        else:
            tokens_str = str(self._tokens)

        return f"[bold]{tokens_str}[/bold] tok [dim]·[/dim] [green]${self._cost:.2f}[/green]"

    def _format_calls_time(self) -> str:
        """Format API calls and elapsed time line."""
        return f"{self._api_calls} calls [dim]·[/dim] {self._elapsed}"
