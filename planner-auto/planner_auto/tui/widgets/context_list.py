"""Context list widget — scrollable list of context entries."""

from __future__ import annotations

import os

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Label, Static


class ContextList(Static):
    """Scrollable list showing context entries.

    Each row: #  Type  Path/Content  Size
    """

    DEFAULT_CSS = """
    ContextList {
        height: 1fr;
        padding: 0 1;
    }
    ContextList .cl-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    ContextList .cl-row {
        height: 1;
    }
    ContextList .cl-empty {
        color: $text-muted;
    }
    ContextList .cl-file {
        color: $accent;
    }
    ContextList .cl-note {
        color: #00ff41;
    }
    ContextList .cl-synthesis {
        color: $warning;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._entries: list[dict] = []
        self._scroll: VerticalScroll | None = None
        self._empty_label: Label | None = None

    def compose(self) -> ComposeResult:
        yield Label("Context", classes="cl-title")
        self._empty_label = Label("  No entries yet. Press [f] to add a file.", classes="cl-empty")
        yield self._empty_label
        self._scroll = VerticalScroll()
        yield self._scroll

    def add_entry(self, entry_type: str, key: str, size: int) -> None:
        """Add a context entry to the display."""
        self._entries.append({"entry_type": entry_type, "key": key, "size": size})

        # Hide empty label
        if self._empty_label is not None:
            self._empty_label.display = False

        idx = len(self._entries)
        display_key = self._format_key(entry_type, key)
        size_str = self._format_size(size)
        css_class = f"cl-row cl-{entry_type}"

        lbl = Label(f"  {idx:>2}  {entry_type:<5}  {display_key:<40}  {size_str}", classes=css_class)
        if self._scroll is not None:
            self._scroll.mount(lbl)

    def get_total_size(self) -> int:
        """Return total size of all entries."""
        return sum(e["size"] for e in self._entries)

    def get_file_count(self) -> int:
        """Return number of file entries."""
        return sum(1 for e in self._entries if e["entry_type"] == "file")

    def get_note_count(self) -> int:
        """Return number of note entries."""
        return sum(1 for e in self._entries if e["entry_type"] == "note")

    @staticmethod
    def _format_key(entry_type: str, key: str) -> str:
        if entry_type == "file":
            return os.path.basename(key)
        elif entry_type == "note":
            return key[:40] if len(key) > 40 else key
        elif entry_type == "synthesis":
            return "auto-generated"
        return key[:40]

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        return f"{size / (1024 * 1024):.1f}MB"
