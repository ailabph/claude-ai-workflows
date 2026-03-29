"""Plan panel — shows draft number, size, growth, milestone count."""

from __future__ import annotations

import re

from textual.widgets import Static, Label
from textual.containers import Vertical


class PlanPanel(Static):
    """Displays plan metrics: draft number, size, growth, milestones."""

    DEFAULT_CSS = """
    PlanPanel {
        height: auto;
        padding: 1;
    }
    PlanPanel .pp-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    PlanPanel .pp-line {
        margin-bottom: 0;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._original_size: int | None = None

    def compose(self):
        yield Label("Plan", classes="pp-title")
        with Vertical():
            yield Label("Draft: —", id="pp-draft", classes="pp-line")
            yield Label("Size: —", id="pp-size", classes="pp-line")
            yield Label("Growth: —", id="pp-growth", classes="pp-line")
            yield Label("Milestones: —", id="pp-milestones", classes="pp-line")

    def update(self, draft_num: int, size: int, original_size: int, plan_text: str) -> None:
        """Recalculate and re-render all plan fields."""
        if self._original_size is None:
            self._original_size = original_size

        try:
            self.query_one("#pp-draft", Label).update(f"Draft: #{draft_num}")
        except Exception:
            pass

        try:
            self.query_one("#pp-size", Label).update(f"Size: {size:,} chars")
        except Exception:
            pass

        # Growth percentage.
        if self._original_size and self._original_size > 0:
            growth_pct = ((size - self._original_size) / self._original_size) * 100
            sign = "+" if growth_pct >= 0 else ""
            try:
                self.query_one("#pp-growth", Label).update(f"Growth: {sign}{growth_pct:.1f}%")
            except Exception:
                pass
        else:
            try:
                self.query_one("#pp-growth", Label).update("Growth: —")
            except Exception:
                pass

        # Milestone count from ## Milestone headers.
        milestone_count = len(re.findall(r"^##\s+Milestone\s+\d+", plan_text, re.MULTILINE))
        try:
            self.query_one("#pp-milestones", Label).update(f"Milestones: {milestone_count}")
        except Exception:
            pass
