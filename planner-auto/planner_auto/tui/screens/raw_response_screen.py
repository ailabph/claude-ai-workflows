"""Raw response screen — shows raw GPT response for a selected round."""

from __future__ import annotations

import sqlite3
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static, TextArea


class RawResponseScreen(ModalScreen):
    """Modal screen showing the raw GPT response for a specific round.

    Data is sourced from the ``reviews.raw_response`` DB column via the
    TUI main thread's read-only connection. Only accessible from the
    round detail view via ``r`` key.
    """

    DEFAULT_CSS = """
    RawResponseScreen {
        align: center middle;
    }
    RawResponseScreen #raw-container {
        width: 90%;
        height: 85%;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    RawResponseScreen .raw-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    RawResponseScreen .raw-warning {
        color: $warning;
        text-style: bold;
        margin-bottom: 1;
    }
    RawResponseScreen #raw-text {
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
        round_num: int,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._conn = conn
        self._session_id = session_id
        self._round_num = round_num

    def compose(self) -> ComposeResult:
        with Vertical(id="raw-container"):
            yield Label(f"Raw Response — Round {self._round_num}", classes="raw-title")
            yield Static(
                "⚠ This contains the raw API response. Do not share publicly.",
                classes="raw-warning",
            )
            yield TextArea("", id="raw-text", read_only=True)

    def on_mount(self) -> None:
        raw_text = self._load_raw_response()
        text_area: TextArea = self.query_one("#raw-text", TextArea)
        text_area.load_text(raw_text)

    def _load_raw_response(self) -> str:
        """Load the raw GPT response for this round from DB."""
        if self._conn:
            try:
                row = self._conn.execute(
                    """
                    SELECT raw_response
                    FROM reviews
                    WHERE session_id = ? AND round_number = ?
                    """,
                    (self._session_id, self._round_num),
                ).fetchone()
                if row and row[0]:
                    return row[0]
            except Exception:
                pass

        return "(No raw response available for this round)"
