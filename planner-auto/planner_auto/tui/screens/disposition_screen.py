"""Disposition screen — cross-round disposition table."""

from __future__ import annotations

import sqlite3
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label, Static


class DispositionScreen(ModalScreen):
    """Modal screen showing all dispositions across all rounds.

    Data is sourced from the ``review_dispositions`` DB table via the
    TUI main thread's read-only connection.
    """

    DEFAULT_CSS = """
    DispositionScreen {
        align: center middle;
    }
    DispositionScreen #disp-container {
        width: 90%;
        height: 80%;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    DispositionScreen .disp-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    DispositionScreen #disp-empty {
        color: $text-muted;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Back"),
    ]

    def __init__(
        self,
        conn: Optional[sqlite3.Connection],
        session_id: str,
        round_data: dict[int, dict] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._conn = conn
        self._session_id = session_id
        self._round_data = round_data or {}

    def compose(self) -> ComposeResult:
        with Vertical(id="disp-container"):
            yield Label("Dispositions", classes="disp-title")
            yield DataTable(id="disp-table")
            yield Static("", id="disp-empty")

    def on_mount(self) -> None:
        table: DataTable = self.query_one("#disp-table", DataTable)
        table.add_columns("Round", "Issue", "Disposition", "Rationale")

        rows = self._load_dispositions()
        empty_label: Static = self.query_one("#disp-empty", Static)

        if not rows:
            empty_label.update("No dispositions recorded yet.")
        else:
            empty_label.update("")
            for row in rows:
                table.add_row(
                    str(row["round"]),
                    _truncate(row["issue"], 40),
                    row["disposition"],
                    _truncate(row["rationale"], 50),
                )

    def _load_dispositions(self) -> list[dict]:
        """Load dispositions from DB or from in-memory round data."""
        rows: list[dict] = []

        # Try DB first.
        if self._conn:
            try:
                cursor = self._conn.execute(
                    """
                    SELECT r.round_number, rd.issue_index, rd.disposition, rd.rationale
                    FROM review_dispositions rd
                    JOIN reviews r ON rd.review_id = r.id
                    WHERE r.session_id = ?
                    ORDER BY r.round_number, rd.issue_index
                    """,
                    (self._session_id,),
                )
                for db_row in cursor.fetchall():
                    rows.append({
                        "round": db_row[0] or "?",
                        "issue": f"Issue #{db_row[1] + 1}",
                        "disposition": db_row[2],
                        "rationale": db_row[3] or "",
                    })
                if rows:
                    return rows
            except Exception:
                pass

        # Fallback: extract from in-memory round_data (populated by callbacks).
        for round_num, rdata in sorted(self._round_data.items()):
            issues = rdata.get("issues", [])
            for i, issue in enumerate(issues):
                disp = issue.get("disposition", "—")
                desc = issue.get("description", issue.get("summary", f"Issue #{i + 1}"))
                rationale = issue.get("rationale", "")
                rows.append({
                    "round": round_num,
                    "issue": desc,
                    "disposition": disp,
                    "rationale": rationale,
                })

        return rows


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if too long."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
