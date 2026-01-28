"""
Stats panel widget - comprehensive statistics display for watch mode.

Shows session totals, current file stats, and per-agent breakdown.
"""

from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.containers import Vertical


class StatsPanel(Static):
    """
    Statistics panel for Layout B with session and per-agent tracking.

    Displays:
    - Session totals (tokens, cost, API calls)
    - Current file stats
    - Per-agent breakdown (planner, executor, explore)
    """

    DEFAULT_CSS = """
    StatsPanel {
        height: auto;
        min-height: 12;
        max-height: 20;
        padding: 0 1;
        border: solid $border;
    }

    StatsPanel .stats-title {
        height: 1;
        color: $text;
        text-style: bold;
    }

    StatsPanel .stats-section {
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
    }

    StatsPanel .stats-row {
        height: 1;
        color: $text;
    }

    StatsPanel .stats-tokens {
        color: $primary;
    }

    StatsPanel .stats-cost {
        color: $success;
    }

    StatsPanel .agent-row {
        height: 1;
        color: $text;
        padding-left: 1;
    }

    StatsPanel .agent-planner {
        color: #00d7ff;
    }

    StatsPanel .agent-executor {
        color: #00ff00;
    }

    StatsPanel .agent-explore {
        color: #ffaf00;
    }
    """

    def __init__(self, show_title: bool = True, **kwargs) -> None:
        """Initialize stats panel."""
        super().__init__(**kwargs)
        self._show_title = show_title

        # Current file stats
        self._tokens: int = 0
        self._cost: float = 0.0
        self._api_calls: int = 0
        self._elapsed: str = "00:00"
        self._elapsed_seconds: int = 0

        # Session totals
        self._session_tokens: int = 0
        self._session_cost: float = 0.0
        self._session_api_calls: int = 0

        # Per-agent breakdown
        self._planner_tokens: int = 0
        self._executor_tokens: int = 0
        self._explore_tokens: int = 0
        self._planner_cost: float = 0.0
        self._executor_cost: float = 0.0
        self._explore_cost: float = 0.0

    def compose(self) -> ComposeResult:
        with Vertical():
            if self._show_title:
                yield Label("STATS", classes="stats-title")

            # Session totals section
            yield Label("SESSION", classes="stats-section", id="session-header")
            yield Label(
                self._format_session_line(),
                classes="stats-row",
                id="session-stats",
            )
            yield Label(
                self._format_session_calls(),
                classes="stats-row",
                id="session-calls",
            )

            # Current file section
            yield Label("FILE", classes="stats-section", id="file-header")
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

            # Per-agent breakdown
            yield Label("BY AGENT", classes="stats-section", id="agent-header")
            yield Label(
                self._format_planner_stats(),
                classes="agent-row agent-planner",
                id="planner-stats",
            )
            yield Label(
                self._format_executor_stats(),
                classes="agent-row agent-executor",
                id="executor-stats",
            )
            yield Label(
                self._format_explore_stats(),
                classes="agent-row agent-explore",
                id="explore-stats",
            )

    def add_tokens(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost: float = 0.0,
        agent: str = ""
    ) -> None:
        """Add tokens from a single API call (file-level tracking)."""
        self._tokens += input_tokens + output_tokens
        self._cost += cost
        self._api_calls += 1
        self._refresh_display()

    def update_session_stats(
        self,
        total_tokens: int,
        total_cost: float,
        total_api_calls: int,
        planner_tokens: int = 0,
        executor_tokens: int = 0,
        explore_tokens: int = 0,
        planner_cost: float = 0.0,
        executor_cost: float = 0.0,
        explore_cost: float = 0.0,
    ) -> None:
        """Update session-level statistics."""
        self._session_tokens = total_tokens
        self._session_cost = total_cost
        self._session_api_calls = total_api_calls
        self._planner_tokens = planner_tokens
        self._executor_tokens = executor_tokens
        self._explore_tokens = explore_tokens
        self._planner_cost = planner_cost
        self._executor_cost = executor_cost
        self._explore_cost = explore_cost
        self._refresh_display()

    def update_stats(
        self,
        tokens: int = None,
        cost: float = None,
        api_calls: int = None,
        elapsed: str = None,
    ) -> None:
        """Update file-level statistics display."""
        if tokens is not None:
            self._tokens = tokens
        if cost is not None:
            self._cost = cost
        if api_calls is not None:
            self._api_calls = api_calls
        if elapsed is not None:
            self._elapsed = elapsed
        self._refresh_display()

    def set_elapsed(self, seconds: int) -> None:
        """Set elapsed time from seconds."""
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
        """Reset file-level statistics (NOT session stats)."""
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
            self.query_one("#session-stats", Label).update(self._format_session_line())
            self.query_one("#session-calls", Label).update(self._format_session_calls())
            self.query_one("#tokens-cost", Label).update(self._format_tokens_cost())
            self.query_one("#calls-time", Label).update(self._format_calls_time())
            self.query_one("#planner-stats", Label).update(self._format_planner_stats())
            self.query_one("#executor-stats", Label).update(self._format_executor_stats())
            self.query_one("#explore-stats", Label).update(self._format_explore_stats())
        except Exception:
            pass

    def _format_tokens(self, tokens: int) -> str:
        """Format tokens with K/M suffix."""
        if tokens >= 1_000_000:
            return f"{tokens / 1_000_000:.1f}M"
        elif tokens >= 1000:
            return f"{tokens / 1000:.1f}K"
        else:
            return str(tokens)

    def _format_session_line(self) -> str:
        """Format session tokens and cost line."""
        tokens_str = self._format_tokens(self._session_tokens)
        return f"[bold]{tokens_str}[/bold] tok [dim]·[/dim] [green]${self._session_cost:.2f}[/green]"

    def _format_session_calls(self) -> str:
        """Format session API calls."""
        return f"{self._session_api_calls} API calls"

    def _format_tokens_cost(self) -> str:
        """Format file tokens and cost line."""
        tokens_str = self._format_tokens(self._tokens)
        return f"[bold]{tokens_str}[/bold] tok [dim]·[/dim] [green]${self._cost:.2f}[/green]"

    def _format_calls_time(self) -> str:
        """Format file API calls and elapsed time line."""
        return f"{self._api_calls} calls [dim]·[/dim] {self._elapsed}"

    def _format_planner_stats(self) -> str:
        """Format planner agent stats."""
        tokens_str = self._format_tokens(self._planner_tokens)
        return f"Planner: {tokens_str} · ${self._planner_cost:.2f}"

    def _format_executor_stats(self) -> str:
        """Format executor agent stats."""
        tokens_str = self._format_tokens(self._executor_tokens)
        return f"Executor: {tokens_str} · ${self._executor_cost:.2f}"

    def _format_explore_stats(self) -> str:
        """Format explore agent stats."""
        tokens_str = self._format_tokens(self._explore_tokens)
        return f"Explore: {tokens_str} · ${self._explore_cost:.2f}"
