"""Help screen — lists all keybindings with descriptions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from planner_auto.tui.bindings import REVIEW_BINDINGS


# Additional context-dependent bindings not in REVIEW_BINDINGS.
_EXTRA_BINDINGS: list[tuple[str, str]] = [
    ("Enter", "Open round detail"),
    ("Escape", "Back / Close modal"),
    ("n", "Next round (in detail view)"),
    ("p", "Previous round (in detail view)"),
    ("r", "Raw GPT response (in detail view)"),
]


class HelpScreen(ModalScreen):
    """Modal screen listing all keybindings with descriptions.

    Auto-generated from ``REVIEW_BINDINGS`` plus context-dependent
    bindings for drill-down views.
    """

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen #help-container {
        width: 60%;
        max-width: 70;
        height: auto;
        max-height: 80%;
        border: solid $accent;
        background: $surface;
        padding: 2 3;
    }
    HelpScreen .help-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    HelpScreen .help-section {
        text-style: bold;
        color: $accent;
        margin-top: 1;
        margin-bottom: 0;
    }
    HelpScreen .help-row {
        height: 1;
        padding: 0;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Back"),
        Binding("question_mark", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-container"):
            yield Label("Keybindings", classes="help-title")

            yield Label("Global", classes="help-section")
            for key, _action, description in REVIEW_BINDINGS:
                display_key = "?" if key == "question_mark" else key
                yield Static(
                    f"  [bold]{display_key:>8}[/bold]  {description}",
                    classes="help-row",
                )

            yield Label("Drill-down", classes="help-section")
            for key, description in _EXTRA_BINDINGS:
                yield Static(
                    f"  [bold]{key:>8}[/bold]  {description}",
                    classes="help-row",
                )
