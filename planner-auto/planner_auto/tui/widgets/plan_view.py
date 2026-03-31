"""Plan view widget — scrollable plan text with header info."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Label, Static


class PlanView(Static):
    """Scrollable widget showing plan text with header info.

    Shows: Draft #N, size, milestone count, model, validation status.
    """

    DEFAULT_CSS = """
    PlanView {
        height: 1fr;
        layout: vertical;
    }
    PlanView .pv-header {
        height: auto;
        padding: 1;
        border-bottom: solid $surface;
    }
    PlanView .pv-title {
        text-style: bold;
        color: $primary;
    }
    PlanView .pv-meta {
        color: $accent;
    }
    PlanView .pv-warning {
        color: $warning;
    }
    PlanView .pv-ok {
        color: #00ff41;
    }
    PlanView #pv-scroll {
        height: 1fr;
        padding: 0 1;
    }
    PlanView .pv-hint {
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._header_label: Label | None = None
        self._validation_label: Label | None = None
        self._plan_label: Label | None = None
        self._hint_label: Label | None = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="pv-header"):
            self._header_label = Label("Plan", classes="pv-title")
            yield self._header_label
            self._validation_label = Label("", classes="pv-ok")
            yield self._validation_label
        with VerticalScroll(id="pv-scroll"):
            self._plan_label = Label("", classes="pv-content")
            yield self._plan_label
        self._hint_label = Label(
            "  [g] Regenerate    [r] Start review",
            classes="pv-hint",
        )
        yield self._hint_label

    def set_plan(
        self,
        draft_number: int,
        content: str,
        model: str,
        validation_ok: bool,
        warnings: list[str] | None = None,
    ) -> None:
        """Set the plan content and header info."""
        if self._header_label:
            self._header_label.update(
                f"Draft #{draft_number}  \u2022  {len(content):,} chars  \u2022  {model}"
            )

        if self._validation_label:
            if validation_ok:
                self._validation_label.update("\u2713 Validation OK")
                self._validation_label.remove_class("pv-warning")
                self._validation_label.add_class("pv-ok")
            else:
                warn_text = "\u26a0 Warnings: " + "; ".join(warnings or ["unknown"])
                self._validation_label.update(warn_text)
                self._validation_label.remove_class("pv-ok")
                self._validation_label.add_class("pv-warning")

        if self._plan_label:
            self._plan_label.update(content)
