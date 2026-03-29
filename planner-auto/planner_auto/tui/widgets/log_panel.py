"""Log panel widget — callback-derived timeline events."""

from __future__ import annotations

from textual.widgets import RichLog


# Filter levels: each level shows messages at that level and above.
FILTER_LEVELS = ["all", "warn+", "error"]


class LogPanel(RichLog):
    """Scrollable log panel that shows callback-derived timeline events.

    Source contract: log entries come from the TUI adapter translating
    engine callbacks into human-readable lines (e.g., "R3: NO_GO — 2 issues").
    This is NOT a raw Python logger stream.

    Max 500 lines — older entries are discarded.

    Supports filtering: ``cycle_filter()`` rotates through all → warn+ → error.
    """

    DEFAULT_CSS = """
    LogPanel {
        height: 100%;
        border: solid $surface;
        padding: 0 1;
    }
    """

    MAX_LINES = 500

    def __init__(self, **kwargs) -> None:
        super().__init__(max_lines=self.MAX_LINES, wrap=True, **kwargs)
        self._filter_index: int = 0
        self._entries: list[tuple[str, str]] = []  # (message, level)

    @property
    def filter_level(self) -> str:
        """Current filter level name."""
        return FILTER_LEVELS[self._filter_index]

    def log_message(self, message: str, level: str = "info") -> None:
        """Append a log entry with color-coding by level.

        Args:
            message: The log text.
            level: One of "info", "success", "warning", "error".
        """
        self._entries.append((message, level))
        if self._entries_len_cap():
            self._entries = self._entries[-self.MAX_LINES:]

        if self._should_show(level):
            self._write_styled(message, level)

    def cycle_filter(self) -> str:
        """Rotate through filter levels: all → warn+ → error → all.

        Returns:
            The new filter level name.
        """
        self._filter_index = (self._filter_index + 1) % len(FILTER_LEVELS)
        self._rerender()
        return self.filter_level

    def _should_show(self, level: str) -> bool:
        """Check if a message at the given level passes the current filter."""
        filt = self.filter_level
        if filt == "all":
            return True
        elif filt == "warn+":
            return level in ("warning", "error")
        elif filt == "error":
            return level == "error"
        return True

    def _rerender(self) -> None:
        """Clear and re-render all entries matching the current filter."""
        self.clear()
        for message, level in self._entries:
            if self._should_show(level):
                self._write_styled(message, level)

    def _write_styled(self, message: str, level: str) -> None:
        """Write a single styled message."""
        style_map = {
            "info": "",
            "success": "[green]",
            "warning": "[yellow]",
            "error": "[red]",
        }
        close_map = {
            "info": "",
            "success": "[/green]",
            "warning": "[/yellow]",
            "error": "[/red]",
        }
        prefix = style_map.get(level, "")
        suffix = close_map.get(level, "")
        self.write(f"{prefix}{message}{suffix}")

    def _entries_len_cap(self) -> bool:
        """Check if entries list exceeds cap."""
        return len(self._entries) > self.MAX_LINES * 2
