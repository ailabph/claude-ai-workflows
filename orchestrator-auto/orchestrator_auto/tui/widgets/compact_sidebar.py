"""
Compact sidebar widget for watch mode - combines watch, status, queue, and milestones.
"""

from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, Label, ListView, ListItem
from typing import Optional, Dict, List

from .compact_milestone_row import CompactMilestoneRow


class CompactFileItem(ListItem):
    """A compact file item in the file list."""

    DEFAULT_CSS = """
    CompactFileItem .compact-file-elapsed {
        color: $text-muted;
        height: 1;
        padding-left: 2;
    }
    """

    MARKERS = {
        "pending": "○",
        "processing": "▶",
        "completed": "✓",
        "failed": "✗",
        "paused": "⏸",
        "skipped": "⊘",
        "converted": "↻",
    }

    def __init__(self, filename: str, status: str = "pending", elapsed_seconds: Optional[int] = None) -> None:
        super().__init__()
        self.filename = filename
        self.file_status = status
        self.elapsed_seconds = elapsed_seconds

    @staticmethod
    def _format_elapsed(seconds: int) -> str:
        """Format seconds into a compact time string."""
        if seconds >= 3600:
            h = seconds // 3600
            m = (seconds % 3600) // 60
            s = seconds % 60
            return f"{h}:{m:02d}:{s:02d}"
        else:
            m = seconds // 60
            s = seconds % 60
            return f"{m:02d}:{s:02d}"

    def _render_name_label(self) -> str:
        """Render marker + filename."""
        marker = self.MARKERS.get(self.file_status, "○")
        display_name = self.filename
        if len(display_name) > 40:
            display_name = display_name[:40] + ".."
        return f"{marker} {display_name}"

    def _elapsed_text(self) -> str:
        """Get elapsed time text, or empty string."""
        if self.elapsed_seconds is not None and self.file_status in ("completed", "failed"):
            return f"  {self._format_elapsed(self.elapsed_seconds)}"
        return ""

    def compose(self) -> ComposeResult:
        yield Label(self._render_name_label(), classes="compact-file-name")
        elapsed = self._elapsed_text()
        lbl = Label(elapsed, classes="compact-file-elapsed")
        lbl.display = bool(elapsed)
        yield lbl

    def update_status(self, status: str, elapsed_seconds: Optional[int] = None) -> None:
        """Update the file status."""
        self.file_status = status
        if elapsed_seconds is not None:
            self.elapsed_seconds = elapsed_seconds
        try:
            self.query_one(".compact-file-name", Label).update(self._render_name_label())
            elapsed_lbl = self.query_one(".compact-file-elapsed", Label)
            text = self._elapsed_text()
            elapsed_lbl.update(text)
            elapsed_lbl.display = bool(text)
        except Exception:
            pass

    def update_filename(self, filename: str) -> None:
        """Update the displayed filename."""
        self.filename = filename
        self.update_status(self.file_status)


class CompactSidebar(Static):
    """
    Condensed sidebar combining watch, status, queue, and milestones.

    18 characters wide, displays:
    - Current file and progress
    - Stats (tokens, cost, time, API calls)
    - Queue status counts
    - File list
    - Milestone icon row
    """

    DEFAULT_CSS = """
    CompactSidebar {
        width: 100%;
        height: 100%;
        border: solid $secondary;
        background: $surface;
        padding: 0;
    }

    CompactSidebar .section-title {
        text-style: bold;
        color: $primary;
        padding: 0 1;
        margin-top: 1;
    }

    CompactSidebar .current-file {
        color: $text;
        padding: 0 1;
        text-style: bold;
    }

    CompactSidebar .progress-line {
        color: $text-muted;
        padding: 0 1;
    }

    CompactSidebar .stat-line {
        color: $text;
        padding: 0 1;
    }

    CompactSidebar .counts-line {
        padding: 0 1;
    }

    CompactSidebar .count-completed {
        color: cyan;
    }

    CompactSidebar .count-failed {
        color: red;
    }

    CompactSidebar .count-paused {
        color: yellow;
    }

    CompactSidebar .file-list {
        height: auto;
        max-height: 8;
        padding: 0;
    }

    CompactSidebar .file-list > ListItem {
        padding: 0 1;
        height: 1;
    }

    CompactSidebar .milestone-row {
        padding: 0 1;
    }

    CompactSidebar .separator {
        color: $text-muted;
        padding: 0 1;
    }

    CompactSidebar .status-paused {
        color: yellow;
        text-style: bold;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Current file info
        self._current_file: str = "—"
        self._milestone_current: int = 0
        self._milestone_total: int = 0
        self._phase: str = "—"

        # Stats
        self._tokens: int = 0
        self._cost: float = 0.0
        self._elapsed: str = "00:00:00"
        self._api_calls: int = 0

        # Queue counts
        self._completed: int = 0
        self._failed: int = 0
        self._paused: int = 0

        # Polling state
        self._is_polling_paused: bool = False

        # Files
        self._files: Dict[str, CompactFileItem] = {}

        # Milestones
        self._milestones: List[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            # Current file section
            yield Label("▶ CURRENT", classes="section-title", id="section-current")
            yield Label(self._truncate(self._current_file, 50), classes="current-file", id="current-file")
            yield Label(self._format_progress(), classes="progress-line", id="progress-line")

            # Stats section
            yield Label("─" * 40, classes="separator")
            yield Label("STATS", classes="section-title")
            yield Label(self._format_stats_line1(), classes="stat-line", id="stats-line1")
            yield Label(self._format_stats_line2(), classes="stat-line", id="stats-line2")

            # Queue section
            yield Label("─" * 40, classes="separator")
            yield Label("QUEUE", classes="section-title")
            yield Label(self._format_counts(), classes="counts-line", id="counts-line")

            # File list
            yield ListView(id="file-list", classes="file-list")

            # Milestones section
            yield Label("─" * 40, classes="separator")
            yield Label("MILESTONES", classes="section-title")
            yield CompactMilestoneRow(id="milestone-row", classes="milestone-row")

    def _truncate(self, text: str, max_len: int) -> str:
        """Truncate text with ellipsis."""
        if len(text) > max_len:
            return text[:max_len - 2] + ".."
        return text

    def _format_progress(self) -> str:
        """Format milestone/phase line."""
        if self._is_polling_paused:
            return "⏸ PAUSED"
        if self._milestone_total == 0:
            return f"M-/- · {self._phase}"
        return f"M{self._milestone_current}/{self._milestone_total} · {self._phase}"

    def _format_stats_line1(self) -> str:
        """Format tokens/cost line."""
        tokens_display = self._format_tokens(self._tokens)
        return f"{tokens_display} · ${self._cost:.2f}"

    def _format_stats_line2(self) -> str:
        """Format time/API calls line."""
        # Truncate elapsed if needed
        elapsed = self._elapsed
        if len(elapsed) > 5:
            elapsed = elapsed[:5]
        return f"{elapsed} · {self._api_calls} calls"

    def _format_tokens(self, tokens: int) -> str:
        """Format token count compactly."""
        if tokens >= 1000000:
            return f"{tokens / 1000000:.1f}M"
        elif tokens >= 1000:
            return f"{tokens / 1000:.1f}K"
        return str(tokens)

    def _format_counts(self) -> str:
        """Format queue status counts."""
        return f"[cyan]✓{self._completed}[/cyan] [red]✗{self._failed}[/red] [yellow]⏸{self._paused}[/yellow]"

    def update_current_file(self, filename: str, milestone: int, total: int, phase: str) -> None:
        """Update current file and progress display."""
        self._current_file = filename
        self._milestone_current = milestone
        self._milestone_total = total
        self._phase = phase

        if self.is_mounted:
            try:
                self.query_one("#current-file", Label).update(self._truncate(filename, 50))
                self.query_one("#progress-line", Label).update(self._format_progress())
            except Exception:
                pass

    def update_stats(self, tokens: int, cost: float, elapsed: str, api_calls: int) -> None:
        """Update statistics section."""
        self._tokens = tokens
        self._cost = cost
        self._elapsed = elapsed
        self._api_calls = api_calls

        if self.is_mounted:
            try:
                self.query_one("#stats-line1", Label).update(self._format_stats_line1())
                self.query_one("#stats-line2", Label).update(self._format_stats_line2())
            except Exception:
                pass

    def update_queue_counts(self, completed: int, failed: int, paused: int) -> None:
        """Update queue status counts."""
        self._completed = completed
        self._failed = failed
        self._paused = paused

        if self.is_mounted:
            try:
                self.query_one("#counts-line", Label).update(self._format_counts())
            except Exception:
                pass

    def set_polling_paused(self, paused: bool) -> None:
        """Set polling paused state."""
        self._is_polling_paused = paused
        if self.is_mounted:
            try:
                progress_label = self.query_one("#progress-line", Label)
                progress_label.update(self._format_progress())
                if paused:
                    progress_label.add_class("status-paused")
                else:
                    progress_label.remove_class("status-paused")
            except Exception:
                pass

    def update_milestones(self, milestones: List[dict], current: int) -> None:
        """Update milestone icon row."""
        self._milestones = milestones

        if self.is_mounted:
            try:
                milestone_row = self.query_one("#milestone-row", CompactMilestoneRow)
                milestone_row.set_milestones(milestones, current)
            except Exception:
                pass

    def set_current_milestone(self, current: int) -> None:
        """Set the current milestone number."""
        self._milestone_current = current

        if self.is_mounted:
            try:
                self.query_one("#progress-line", Label).update(self._format_progress())
                milestone_row = self.query_one("#milestone-row", CompactMilestoneRow)
                milestone_row.set_current(current)
            except Exception:
                pass

    def add_file(self, filename: str, status: str = "pending") -> None:
        """Add file to the file list."""
        if filename in self._files:
            self.update_file(filename, status)
            return

        try:
            list_view = self.query_one("#file-list", ListView)
            item = CompactFileItem(filename, status)
            self._files[filename] = item
            list_view.append(item)

            # Keep list manageable
            if len(self._files) > 6:
                oldest = list(self._files.keys())[0]
                self.remove_file(oldest)
        except Exception:
            pass

    def update_file(self, filename: str, status: str, original_filename: Optional[str] = None, elapsed_seconds: Optional[int] = None) -> None:
        """Update file status in the list."""
        # Handle renames
        if original_filename and original_filename in self._files:
            item = self._files.pop(original_filename)
            item.update_filename(filename)
            item.update_status(status, elapsed_seconds)
            self._files[filename] = item
        elif filename in self._files:
            self._files[filename].update_status(status, elapsed_seconds)
        else:
            self.add_file(filename, status)

    def remove_file(self, filename: str) -> None:
        """Remove file from the list."""
        if filename in self._files:
            try:
                item = self._files.pop(filename)
                item.remove()
            except Exception:
                pass

    def clear_files(self) -> None:
        """Clear all files from the list."""
        try:
            list_view = self.query_one("#file-list", ListView)
            list_view.clear()
            self._files.clear()
        except Exception:
            pass
