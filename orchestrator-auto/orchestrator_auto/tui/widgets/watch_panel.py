"""
Watch panel widget for displaying watch mode status.

Shows directory being watched, poll interval, pending files,
and status of recently processed files.
"""

from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Label, ListView, ListItem
from typing import Optional, List, Dict


class WatchFileItem(ListItem):
    """A single file item in the watch file list."""

    MARKERS = {
        "pending": "○",
        "processing": "▶",
        "completed": "✓",
        "failed": "✗",
        "paused": "⏸",
        "skipped": "⊘",
        "converted": "↻",
    }

    def __init__(
        self,
        filename: str,
        status: str = "pending",
        error: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.filename = filename
        self.file_status = status
        self.error = error
        self._update_classes()

    def _update_classes(self) -> None:
        """Update CSS classes based on status."""
        for status in self.MARKERS:
            self.remove_class(f"watch-{status}")
        self.add_class(f"watch-{self.file_status}")

    def update_status(self, status: str, error: Optional[str] = None) -> None:
        """Update the file status."""
        self.file_status = status
        self.error = error
        self._update_classes()
        self._update_display()

    def update_filename(self, filename: str) -> None:
        """Update the displayed filename (for renames)."""
        self.filename = filename
        self._update_display()

    def _update_display(self) -> None:
        """Update the displayed marker and filename labels."""
        try:
            marker = self.MARKERS.get(self.file_status, "○")
            self.query_one(".watch-marker", Label).update(marker)
            self.query_one(".watch-filename", Label).update(self.filename)
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        marker = self.MARKERS.get(self.file_status, "○")
        with Horizontal(classes="watch-file-row"):
            yield Label(marker, classes="watch-marker")
            yield Label(self.filename, classes="watch-filename")


class WatchPanel(Static):
    """
    Panel showing watch mode status and files.

    Displays:
    - Directory being watched
    - Poll interval
    - Auto-convert setting
    - Status counts (completed/failed/paused)
    - List of recent files with their status
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._directory: str = "—"
        self._poll_interval: int = 2
        self._auto_convert: bool = False
        self._is_paused: bool = False
        self._paused_session: Optional[str] = None
        self._completed: int = 0
        self._failed: int = 0
        self._paused: int = 0
        self._files: Dict[str, WatchFileItem] = {}

    def compose(self) -> ComposeResult:
        yield Label("WATCH", classes="title")
        with Vertical(classes="watch-info"):
            with Horizontal(classes="stat-row"):
                yield Label("Directory:", classes="stat-label")
                yield Label(self._directory, id="watch-dir", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("Interval:", classes="stat-label")
                yield Label(f"{self._poll_interval}s", id="watch-interval", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("Convert:", classes="stat-label")
                yield Label("Yes" if self._auto_convert else "No", id="watch-convert", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("Status:", classes="stat-label")
                yield Label("Watching", id="watch-status", classes="stat-value")
        yield Label("", classes="spacer")
        with Horizontal(classes="counts-row"):
            yield Label(f"✓ {self._completed}", id="count-completed", classes="count-completed")
            yield Label(f"✗ {self._failed}", id="count-failed", classes="count-failed")
            yield Label(f"⏸ {self._paused}", id="count-paused", classes="count-paused")
        yield Label("", classes="spacer")
        yield Label("Recent Files:", classes="section-title")
        yield ListView(id="watch-files")

    def set_config(self, directory: str, poll_interval: int, auto_convert: bool) -> None:
        """Set watch configuration."""
        self._directory = directory
        self._poll_interval = poll_interval
        self._auto_convert = auto_convert

        try:
            # Truncate directory for display
            dir_display = directory
            if len(dir_display) > 25:
                dir_display = "..." + dir_display[-22:]

            self.query_one("#watch-dir", Label).update(dir_display)
            self.query_one("#watch-interval", Label).update(f"{poll_interval}s")
            self.query_one("#watch-convert", Label).update("Yes" if auto_convert else "No")
        except Exception:
            pass

    def set_paused(self, session_id: str, plan_path: str) -> None:
        """Mark watch as paused on a blocker."""
        self._is_paused = True
        self._paused_session = session_id

        try:
            status_label = self.query_one("#watch-status", Label)
            status_label.update(f"Paused: {Path(plan_path).name[:20]}")
            status_label.add_class("phase-paused")
        except Exception:
            pass

    def set_running(self) -> None:
        """Mark watch as running."""
        self._is_paused = False
        self._paused_session = None

        try:
            status_label = self.query_one("#watch-status", Label)
            status_label.update("Watching")
            status_label.remove_class("phase-paused")
        except Exception:
            pass

    def set_stopped(self) -> None:
        """Mark watch as stopped."""
        try:
            status_label = self.query_one("#watch-status", Label)
            status_label.update("Stopped")
            status_label.add_class("phase-completed")
        except Exception:
            pass

    def update_counts(self, completed: int, failed: int, paused: int) -> None:
        """Update the status counts."""
        self._completed = completed
        self._failed = failed
        self._paused = paused

        try:
            self.query_one("#count-completed", Label).update(f"✓ {completed}")
            self.query_one("#count-failed", Label).update(f"✗ {failed}")
            self.query_one("#count-paused", Label).update(f"⏸ {paused}")
        except Exception:
            pass

    def add_file(self, filename: str, status: str = "pending") -> None:
        """Add a file to the watch list."""
        if filename in self._files:
            self.update_file(filename, status)
            return

        try:
            list_view = self.query_one("#watch-files", ListView)
            item = WatchFileItem(filename, status)
            self._files[filename] = item
            list_view.append(item)

            # Keep list manageable - remove oldest if too many
            if len(self._files) > 10:
                oldest = list(self._files.keys())[0]
                self.remove_file(oldest)
        except Exception:
            pass

    def update_file(
        self,
        filename: str,
        status: str,
        error: Optional[str] = None,
        original_filename: Optional[str] = None,
    ) -> None:
        """Update a file's status, handling renames.

        Args:
            filename: Current filename (may be renamed)
            status: New status
            error: Optional error message
            original_filename: If file was renamed, the original filename to update
        """
        # If this is a rename, update the original entry instead of creating new
        if original_filename and original_filename in self._files:
            item = self._files[original_filename]
            # Update the status and displayed filename
            item.update_status(status, error)
            item.update_filename(filename)
            # Re-key in our dict (remove old, add with new key)
            self._files.pop(original_filename)
            self._files[filename] = item
        elif filename in self._files:
            self._files[filename].update_status(status, error)
        else:
            self.add_file(filename, status)

    def remove_file(self, filename: str) -> None:
        """Remove a file from the list."""
        if filename in self._files:
            try:
                item = self._files.pop(filename)
                item.remove()
            except Exception:
                pass

    def clear_files(self) -> None:
        """Clear all files from the list."""
        try:
            list_view = self.query_one("#watch-files", ListView)
            list_view.clear()
            self._files.clear()
        except Exception:
            pass

    def sync_pending_files(self, pending_files: List[str]) -> None:
        """
        Sync the pending files list with the current directory state.

        Adds new pending files and removes files that are no longer pending
        (unless they have a non-pending status like processing, completed, etc).
        """
        pending_set = set(pending_files)

        # Add new pending files
        for filename in pending_files:
            if filename not in self._files:
                self.add_file(filename, "pending")

        # Remove files that are no longer pending and were in pending state
        for filename in list(self._files.keys()):
            if filename not in pending_set:
                item = self._files.get(filename)
                # Only remove if it was pending (not processing/completed/etc)
                if item and item.file_status == "pending":
                    self.remove_file(filename)
