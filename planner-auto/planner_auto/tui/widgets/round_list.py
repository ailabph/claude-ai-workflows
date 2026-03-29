"""Round list widget — shows review rounds with status icons."""

from __future__ import annotations

from textual.widgets import Static, Label
from textual.containers import Vertical


# Status icons.
ICON_ACTIVE = "▶"
ICON_COMPLETED = "✓"
ICON_GO = "★"
ICON_CAP_CRITICALS = "⚠"
ICON_PENDING = "○"


class RoundRow(Static):
    """A single round row with icon + round number + details."""

    DEFAULT_CSS = """
    RoundRow {
        height: 1;
        padding: 0 1;
    }
    RoundRow.round-active {
        color: $accent;
    }
    RoundRow.round-go {
        color: $success;
    }
    RoundRow.round-completed {
        color: $text;
    }
    RoundRow.round-warning {
        color: $warning;
    }
    """

    def __init__(self, round_num: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self.round_num = round_num
        self._icon = ICON_ACTIVE
        self._detail = ""

    def update_status(self, verdict: str | None = None, issue_count: int = 0, cost: float | None = None) -> None:
        """Update the round row with verdict/cost info."""
        if verdict == "GO":
            self._icon = ICON_GO
            self.remove_class("round-active", "round-completed", "round-warning")
            self.add_class("round-go")
        elif verdict:
            self._icon = ICON_COMPLETED
            self.remove_class("round-active", "round-go", "round-warning")
            self.add_class("round-completed")
        cost_str = f" ${cost:.3f}" if cost is not None else ""
        issue_str = f" {issue_count}i" if issue_count else ""
        self._detail = f"{verdict or ''}{issue_str}{cost_str}"
        self._render_text()

    def set_active(self) -> None:
        """Mark this round as currently active."""
        self._icon = ICON_ACTIVE
        self.remove_class("round-completed", "round-go", "round-warning")
        self.add_class("round-active")
        self._detail = ""
        self._render_text()

    def set_cap_warning(self) -> None:
        """Mark this round as cap-with-criticals."""
        self._icon = ICON_CAP_CRITICALS
        self.remove_class("round-active", "round-completed", "round-go")
        self.add_class("round-warning")
        self._render_text()

    def _render_text(self) -> None:
        self.update(f" {self._icon} R{self.round_num} {self._detail}")


class RoundList(Static):
    """Vertical list of review rounds."""

    DEFAULT_CSS = """
    RoundList {
        height: auto;
        padding: 1 0;
    }
    RoundList .rl-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows: dict[int, RoundRow] = {}

    def compose(self):
        yield Label("Rounds", classes="rl-title")
        yield Vertical(id="round-rows")

    def add_round(self, round_num: int) -> None:
        """Add a new round row to the list."""
        row = RoundRow(round_num, id=f"round-{round_num}")
        row.set_active()
        self._rows[round_num] = row
        container = self.query_one("#round-rows", Vertical)
        container.mount(row)

    def update_round(self, round_num: int, verdict: str | None = None,
                     issue_count: int = 0, cost: float | None = None) -> None:
        """Update an existing round row."""
        if round_num in self._rows:
            self._rows[round_num].update_status(verdict, issue_count, cost)
