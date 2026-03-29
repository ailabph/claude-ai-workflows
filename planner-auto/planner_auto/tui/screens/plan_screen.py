"""Plan screen — scrollable read-only plan viewer."""

from __future__ import annotations

import sqlite3
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, TextArea


class PlanScreen(ModalScreen):
    """Modal screen showing the latest plan draft in a scrollable viewer.

    Data is sourced from the ``plan_drafts`` DB table via the TUI main
    thread's read-only connection. Falls back to the initial plan text
    from PreparedReview if DB is unavailable.
    """

    DEFAULT_CSS = """
    PlanScreen {
        align: center middle;
    }
    PlanScreen #plan-container {
        width: 90%;
        height: 85%;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    PlanScreen .plan-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    PlanScreen #plan-text {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Back"),
    ]

    def __init__(
        self,
        conn: Optional[sqlite3.Connection],
        session_id: str,
        fallback_plan: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._conn = conn
        self._session_id = session_id
        self._fallback_plan = fallback_plan

    def compose(self) -> ComposeResult:
        with Vertical(id="plan-container"):
            yield Label("Plan", id="plan-title-label", classes="plan-title")
            yield TextArea("", id="plan-text", read_only=True)

    def on_mount(self) -> None:
        draft_num, plan_text = self._load_plan()

        title_label: Label = self.query_one("#plan-title-label", Label)
        title_label.update(f"Plan — Draft #{draft_num} ({len(plan_text):,} chars)")

        text_area: TextArea = self.query_one("#plan-text", TextArea)
        text_area.load_text(plan_text)

    def _load_plan(self) -> tuple[int, str]:
        """Load the latest plan draft. Returns (draft_number, text)."""
        if self._conn:
            try:
                row = self._conn.execute(
                    """
                    SELECT draft_number, content
                    FROM plan_drafts
                    WHERE session_id = ?
                    ORDER BY draft_number DESC
                    LIMIT 1
                    """,
                    (self._session_id,),
                ).fetchone()
                if row:
                    return (row[0], row[1])
            except Exception:
                pass

        return (1, self._fallback_plan)
