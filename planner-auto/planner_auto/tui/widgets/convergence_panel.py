"""Convergence panel — issue trend, sparkline, cumulative cost/tokens."""

from __future__ import annotations

import re

from textual.widgets import Static, Label
from textual.containers import Vertical


# Unicode block elements for sparkline.
_BLOCKS = "▁▂▃▄▅▆▇█"


def _sparkline(values: list[int]) -> str:
    """Render a sparkline string from a list of non-negative ints."""
    if not values:
        return ""
    max_val = max(values) or 1
    return "".join(
        _BLOCKS[min(int(v / max_val * (len(_BLOCKS) - 1)), len(_BLOCKS) - 1)]
        for v in values
    )


class ConvergencePanel(Static):
    """Shows issue trend, sparkline, cumulative GPT cost and tokens."""

    DEFAULT_CSS = """
    ConvergencePanel {
        height: auto;
        padding: 1;
    }
    ConvergencePanel .cp-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    ConvergencePanel .cp-line {
        margin-bottom: 0;
    }
    ConvergencePanel .cp-sparkline {
        color: $accent;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._issue_counts: list[int] = []
        self._costs: list[float] = []
        self._tokens: list[int] = []

    def compose(self):
        yield Label("Convergence", classes="cp-title")
        with Vertical():
            yield Label("Trend: —", id="cp-trend", classes="cp-line")
            yield Label("Sparkline: ", id="cp-sparkline", classes="cp-line cp-sparkline")
            yield Label("GPT cost: $0.0000", id="cp-cost", classes="cp-line")
            yield Label("GPT tokens: 0", id="cp-tokens", classes="cp-line")

    def update(self, round_num: int, issue_count: int, cost: float, tokens: int) -> None:
        """Append round data and re-render all fields."""
        self._issue_counts.append(issue_count)
        self._costs.append(cost)
        self._tokens.append(tokens)

        # Trend: 3→1→2→_
        trend = "→".join(str(c) for c in self._issue_counts)
        try:
            self.query_one("#cp-trend", Label).update(f"Trend: {trend}")
        except Exception:
            pass

        # Sparkline
        spark = _sparkline(self._issue_counts)
        try:
            self.query_one("#cp-sparkline", Label).update(f"Sparkline: {spark}")
        except Exception:
            pass

        # Cumulative cost
        total_cost = sum(self._costs)
        try:
            self.query_one("#cp-cost", Label).update(f"GPT cost: ${total_cost:.4f}")
        except Exception:
            pass

        # Cumulative tokens
        total_tokens = sum(self._tokens)
        try:
            self.query_one("#cp-tokens", Label).update(f"GPT tokens: {total_tokens:,}")
        except Exception:
            pass
