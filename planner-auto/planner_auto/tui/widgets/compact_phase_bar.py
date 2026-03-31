"""Compact phase bar widget for small terminals (<80 cols).

Renders as: ✓ ✓ ▶ ○ ○ ○  4ctx  6msg  $0.00
"""

from __future__ import annotations

from textual.widgets import Static

from planner_auto.tui.widgets.phase_list import ICON_ACTIVE, ICON_COMPLETED, ICON_PENDING, PHASE_ORDER


class CompactPhaseBar(Static):
    """Single-line widget showing phase icons inline + key metrics."""

    DEFAULT_CSS = """
    CompactPhaseBar {
        height: 1;
        padding: 0 1;
        color: $accent;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._phase_icons: list[str] = [ICON_PENDING] * len(PHASE_ORDER)
        self._context_count: int = 0
        self._message_count: int = 0
        self._cost: float = 0.0

    def update(
        self,
        phases: list[str] | None = None,
        context_count: int | None = None,
        message_count: int | None = None,
        cost: float | None = None,
    ) -> None:
        """Update the compact bar display."""
        if phases is not None:
            self._phase_icons = phases
        if context_count is not None:
            self._context_count = context_count
        if message_count is not None:
            self._message_count = message_count
        if cost is not None:
            self._cost = cost
        self._refresh_display()

    def _refresh_display(self) -> None:
        icons = " ".join(self._phase_icons)
        metrics = f"  {self._context_count}ctx  {self._message_count}msg  ${self._cost:.2f}"
        self.update(f"{icons}{metrics}")

    def set_active_phase(self, phase: str) -> None:
        """Update icons based on active phase."""
        active_idx = None
        for i, p in enumerate(PHASE_ORDER):
            if p.value == phase:
                active_idx = i
                break
        if active_idx is None:
            return
        icons = []
        for i in range(len(PHASE_ORDER)):
            if i < active_idx:
                icons.append(ICON_COMPLETED)
            elif i == active_idx:
                icons.append(ICON_ACTIVE)
            else:
                icons.append(ICON_PENDING)
        self._phase_icons = icons
        self._refresh_display()

    def _refresh_display(self) -> None:
        icons = " ".join(self._phase_icons)
        metrics = f"  {self._context_count}ctx  {self._message_count}msg  ${self._cost:.2f}"
        super().update(f"{icons}{metrics}")
