"""Phase list widget — shows session phases with status icons."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Static

from planner_auto.state import Phase

# Ordered list of all phases
PHASE_ORDER = [
    Phase.SETUP,
    Phase.CONTEXT,
    Phase.DISCUSSION,
    Phase.PLANNING,
    Phase.REVIEW,
    Phase.COMPLETE,
]

# Icons for each status
ICON_COMPLETED = "\u2713"  # ✓
ICON_ACTIVE = "\u25b6"     # ▶
ICON_PENDING = "\u25cb"    # ○
ICON_PAUSED = "\u26a0"     # ⚠


class PhaseList(Static):
    """Vertical widget showing 6 phases with status icons.

    Each phase row: icon + phase name + optional count.
    """

    DEFAULT_CSS = """
    PhaseList {
        height: auto;
        padding: 1;
    }
    PhaseList .pl-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    PhaseList .pl-row {
        height: 1;
    }
    PhaseList .pl-active {
        color: $accent;
        text-style: bold;
    }
    PhaseList .pl-completed {
        color: #00ff41;
    }
    PhaseList .pl-pending {
        color: $text-muted;
    }
    PhaseList .pl-paused {
        color: $warning;
        text-style: bold;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._icons: dict[str, str] = {}
        self._counts: dict[str, str] = {}
        self._labels: dict[str, Label] = {}
        self._active_phase: str | None = None

    def compose(self) -> ComposeResult:
        yield Label("Phases", classes="pl-title")
        with Vertical():
            for phase in PHASE_ORDER:
                lbl = Label(
                    f"  {ICON_PENDING} {phase.value}",
                    classes="pl-row pl-pending",
                    id=f"pl-{phase.value.lower()}",
                )
                self._labels[phase.value] = lbl
                self._icons[phase.value] = ICON_PENDING
                yield lbl

    def set_active(self, phase: str) -> None:
        """Set the active phase and update all icons accordingly."""
        self._active_phase = phase
        active_idx = None
        for i, p in enumerate(PHASE_ORDER):
            if p.value == phase:
                active_idx = i
                break

        if active_idx is None:
            return

        for i, p in enumerate(PHASE_ORDER):
            if i < active_idx:
                self.update_phase(p.value, ICON_COMPLETED)
            elif i == active_idx:
                self.update_phase(p.value, ICON_ACTIVE)
            else:
                self.update_phase(p.value, ICON_PENDING)

    def update_phase(self, phase: str, icon: str) -> None:
        """Update a single phase row's icon."""
        self._icons[phase] = icon
        if phase in self._labels:
            count_str = self._counts.get(phase, "")
            text = f"  {icon} {phase}"
            if count_str:
                text += f" ({count_str})"
            self._labels[phase].update(text)
            # Update CSS classes
            lbl = self._labels[phase]
            lbl.remove_class("pl-active", "pl-completed", "pl-pending", "pl-paused")
            if icon == ICON_ACTIVE:
                lbl.add_class("pl-active")
            elif icon == ICON_COMPLETED:
                lbl.add_class("pl-completed")
            elif icon == ICON_PAUSED:
                lbl.add_class("pl-paused")
            else:
                lbl.add_class("pl-pending")

    def set_paused(self, phase: str) -> None:
        """Mark a phase with the paused/warning icon (⚠)."""
        self.update_phase(phase, ICON_PAUSED)

    def set_count(self, phase: str, count: str) -> None:
        """Set the count suffix for a phase (e.g., '4' for CONTEXT)."""
        self._counts[phase] = count
        # Re-render with current icon
        if phase in self._icons:
            self.update_phase(phase, self._icons[phase])
