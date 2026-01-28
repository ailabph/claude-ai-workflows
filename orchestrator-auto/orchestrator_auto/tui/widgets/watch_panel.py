"""
Watch panel widget for displaying watch mode status.

Shows directory being watched, poll interval, and files
organized by category: Pending, Ongoing, Done.
"""

from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Label, ListView, ListItem
from typing import Optional, List, Dict


class WatchFileItem(ListItem):
    """A single file item in the watch file list."""

    DEFAULT_CSS = """
    WatchFileItem .watch-elapsed {
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

    def __init__(
        self,
        filename: str,
        status: str = "pending",
        error: Optional[str] = None,
        elapsed_seconds: Optional[int] = None,
    ) -> None:
        super().__init__()
        self.filename = filename
        self.file_status = status
        self.error = error
        self.elapsed_seconds = elapsed_seconds
        self._update_classes()

    def _update_classes(self) -> None:
        """Update CSS classes based on status."""
        for status in self.MARKERS:
            self.remove_class(f"watch-{status}")
        self.add_class(f"watch-{self.file_status}")

    def update_status(self, status: str, error: Optional[str] = None, elapsed_seconds: Optional[int] = None) -> None:
        """Update the file status."""
        self.file_status = status
        self.error = error
        if elapsed_seconds is not None:
            self.elapsed_seconds = elapsed_seconds
        self._update_classes()
        self._update_display()

    def update_filename(self, filename: str) -> None:
        """Update the displayed filename (for renames)."""
        self.filename = filename
        self._update_display()

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

    def _elapsed_label(self) -> str:
        """Get elapsed time label text, or empty string if not applicable."""
        if self.elapsed_seconds is not None and self.file_status in ("completed", "failed"):
            return f"  {self._format_elapsed(self.elapsed_seconds)}"
        return ""

    def _update_display(self) -> None:
        """Update the displayed marker and filename labels."""
        try:
            marker = self.MARKERS.get(self.file_status, "○")
            self.query_one(".watch-marker", Label).update(marker)
            self.query_one(".watch-filename", Label).update(self.filename)
            elapsed_lbl = self.query_one(".watch-elapsed", Label)
            text = self._elapsed_label()
            elapsed_lbl.update(text)
            elapsed_lbl.display = bool(text)
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        marker = self.MARKERS.get(self.file_status, "○")
        elapsed = self._elapsed_label()
        with Horizontal(classes="watch-file-row"):
            yield Label(marker, classes="watch-marker")
            yield Label(self.filename, classes="watch-filename")
        lbl = Label(elapsed, classes="watch-elapsed")
        lbl.display = bool(elapsed)
        yield lbl


class WatchPanel(Static):
    """
    Panel showing watch mode status and files organized by category.

    Displays:
    - Directory being watched
    - Poll interval
    - Auto-convert setting
    - Watch status (watching/paused/stopped)
    - Status counts (completed/failed/paused)
    - Files by category: PENDING, ONGOING, DONE
    """

    # Map statuses to categories
    CATEGORY_PENDING = "pending"
    CATEGORY_ONGOING = "ongoing"
    CATEGORY_DONE = "done"
    CATEGORY_PAUSED = "paused"
    CATEGORY_FAILED = "failed"

    STATUS_TO_CATEGORY = {
        "pending": CATEGORY_PENDING,
        "processing": CATEGORY_ONGOING,
        "completed": CATEGORY_DONE,
        "failed": CATEGORY_FAILED,
        "paused": CATEGORY_PAUSED,
        "skipped": CATEGORY_FAILED,
        "converted": None,  # Transitional, keeps current category
    }

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

        # Track files by category
        self._pending_files: Dict[str, WatchFileItem] = {}
        self._ongoing_files: Dict[str, WatchFileItem] = {}
        self._done_files: Dict[str, WatchFileItem] = {}
        self._paused_files: Dict[str, WatchFileItem] = {}
        self._failed_files: Dict[str, WatchFileItem] = {}

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

        # Category: PENDING
        yield Label("PENDING", id="pending-header", classes="category-header")
        yield ListView(id="pending-files", classes="category-list")

        # Category: ONGOING
        yield Label("ONGOING", id="ongoing-header", classes="category-header category-ongoing")
        yield ListView(id="ongoing-files", classes="category-list")

        # Category: DONE
        yield Label("DONE", id="done-header", classes="category-header category-done")
        yield ListView(id="done-files", classes="category-list")

        # Category: PAUSED
        yield Label("PAUSED", id="paused-header", classes="category-header category-paused")
        yield ListView(id="paused-files", classes="category-list")

        # Category: FAILED
        yield Label("FAILED", id="failed-header", classes="category-header category-failed")
        yield ListView(id="failed-files", classes="category-list")

    def _get_category(self, status: str) -> Optional[str]:
        """Get category for a given status."""
        return self.STATUS_TO_CATEGORY.get(status, self.CATEGORY_PENDING)

    def _get_files_dict(self, category: str) -> Dict[str, WatchFileItem]:
        """Get the files dict for a category."""
        if category == self.CATEGORY_PENDING:
            return self._pending_files
        elif category == self.CATEGORY_ONGOING:
            return self._ongoing_files
        elif category == self.CATEGORY_DONE:
            return self._done_files
        elif category == self.CATEGORY_PAUSED:
            return self._paused_files
        elif category == self.CATEGORY_FAILED:
            return self._failed_files
        return self._pending_files

    def _get_list_id(self, category: str) -> str:
        """Get ListView ID for a category."""
        if category == self.CATEGORY_PENDING:
            return "#pending-files"
        elif category == self.CATEGORY_ONGOING:
            return "#ongoing-files"
        elif category == self.CATEGORY_DONE:
            return "#done-files"
        elif category == self.CATEGORY_PAUSED:
            return "#paused-files"
        elif category == self.CATEGORY_FAILED:
            return "#failed-files"
        return "#pending-files"

    def _find_file_category(self, filename: str) -> Optional[str]:
        """Find which category a file is currently in."""
        if filename in self._pending_files:
            return self.CATEGORY_PENDING
        elif filename in self._ongoing_files:
            return self.CATEGORY_ONGOING
        elif filename in self._done_files:
            return self.CATEGORY_DONE
        elif filename in self._paused_files:
            return self.CATEGORY_PAUSED
        elif filename in self._failed_files:
            return self.CATEGORY_FAILED
        return None

    def _update_category_headers(self) -> None:
        """Update category headers to show counts."""
        try:
            counts = {
                "pending": len(self._pending_files),
                "ongoing": len(self._ongoing_files),
                "done": len(self._done_files),
                "paused": len(self._paused_files),
                "failed": len(self._failed_files),
            }

            headers = {
                "pending": (self.query_one("#pending-header", Label), "PENDING"),
                "ongoing": (self.query_one("#ongoing-header", Label), "ONGOING"),
                "done": (self.query_one("#done-header", Label), "DONE"),
                "paused": (self.query_one("#paused-header", Label), "PAUSED"),
                "failed": (self.query_one("#failed-header", Label), "FAILED"),
            }

            for key, (header, label) in headers.items():
                count = counts[key]
                header.update(f"{label} ({count})" if count else label)
                if count:
                    header.add_class("has-items")
                else:
                    header.remove_class("has-items")
        except Exception:
            pass

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

    def set_polling_paused(self, paused: bool) -> None:
        """Mark polling as paused/resumed (independent of blocker pause)."""
        try:
            status_label = self.query_one("#watch-status", Label)
            if paused:
                status_label.update("⏸ PAUSED (p to resume)")
                status_label.add_class("phase-paused")
            else:
                status_label.update("Watching")
                status_label.remove_class("phase-paused")
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
        """Add a file to the appropriate category list."""
        # Check if file already exists in any category
        current_category = self._find_file_category(filename)
        if current_category is not None:
            self.update_file(filename, status)
            return

        # Determine target category
        target_category = self._get_category(status)
        if target_category is None:
            target_category = self.CATEGORY_PENDING

        try:
            list_id = self._get_list_id(target_category)
            list_view = self.query_one(list_id, ListView)
            files_dict = self._get_files_dict(target_category)

            item = WatchFileItem(filename, status)
            files_dict[filename] = item
            list_view.append(item)

            # Keep each category list manageable
            if len(files_dict) > 8:
                oldest = list(files_dict.keys())[0]
                self._remove_file_from_category(oldest, target_category)

            self._update_category_headers()
        except Exception:
            pass

    def update_file(
        self,
        filename: str,
        status: str,
        error: Optional[str] = None,
        original_filename: Optional[str] = None,
        elapsed_seconds: Optional[int] = None,
    ) -> None:
        """Update a file's status, moving between categories as needed.

        Args:
            filename: Current filename (may be renamed)
            status: New status
            error: Optional error message
            original_filename: If file was renamed, the original filename to update
            elapsed_seconds: Time spent processing this file
        """
        # Handle renames: find the file by original name
        lookup_name = original_filename if original_filename else filename
        current_category = self._find_file_category(lookup_name)

        if current_category is None:
            # File not found, add it
            self.add_file(filename, status)
            return

        # Determine target category
        target_category = self._get_category(status)
        if target_category is None:
            # Transitional status (like converted), keep in current category
            target_category = current_category

        # Get current item
        files_dict = self._get_files_dict(current_category)
        item = files_dict.get(lookup_name)
        if not item:
            self.add_file(filename, status)
            return

        if current_category == target_category:
            # Same category, just update
            item.update_status(status, error, elapsed_seconds)
            if original_filename and filename != original_filename:
                item.update_filename(filename)
                files_dict.pop(lookup_name)
                files_dict[filename] = item
        else:
            # Move to different category
            self._move_file_to_category(lookup_name, filename, status, error, current_category, target_category, elapsed_seconds)

        self._update_category_headers()

    def _move_file_to_category(
        self,
        old_filename: str,
        new_filename: str,
        status: str,
        error: Optional[str],
        from_category: str,
        to_category: str,
        elapsed_seconds: Optional[int] = None,
    ) -> None:
        """Move a file from one category to another."""
        try:
            # Remove from old category
            old_files = self._get_files_dict(from_category)
            old_item = old_files.pop(old_filename, None)
            if old_item:
                old_item.remove()

            # Add to new category
            new_list_id = self._get_list_id(to_category)
            new_list = self.query_one(new_list_id, ListView)
            new_files = self._get_files_dict(to_category)

            new_item = WatchFileItem(new_filename, status, error, elapsed_seconds)
            new_files[new_filename] = new_item
            new_list.append(new_item)

            # Keep list manageable
            if len(new_files) > 8:
                oldest = list(new_files.keys())[0]
                self._remove_file_from_category(oldest, to_category)
        except Exception:
            pass

    def _remove_file_from_category(self, filename: str, category: str) -> None:
        """Remove a file from a specific category."""
        try:
            files_dict = self._get_files_dict(category)
            item = files_dict.pop(filename, None)
            if item:
                item.remove()
        except Exception:
            pass

    def remove_file(self, filename: str) -> None:
        """Remove a file from whichever category it's in."""
        category = self._find_file_category(filename)
        if category:
            self._remove_file_from_category(filename, category)
            self._update_category_headers()

    def clear_files(self) -> None:
        """Clear all files from all category lists."""
        try:
            for list_id in ["#pending-files", "#ongoing-files", "#done-files", "#paused-files", "#failed-files"]:
                list_view = self.query_one(list_id, ListView)
                list_view.clear()

            self._pending_files.clear()
            self._ongoing_files.clear()
            self._done_files.clear()
            self._paused_files.clear()
            self._failed_files.clear()
            self._update_category_headers()
        except Exception:
            pass

    def sync_pending_files(self, pending_files: List[str]) -> None:
        """
        Sync the pending files list with the current directory state.

        Adds new pending files and removes files that are no longer pending
        (unless they have moved to a different category).
        """
        pending_set = set(pending_files)

        # Add new pending files
        for filename in pending_files:
            if self._find_file_category(filename) is None:
                self.add_file(filename, "pending")

        # Remove files from pending that are no longer in the directory
        # (only if they're still in pending state)
        for filename in list(self._pending_files.keys()):
            if filename not in pending_set:
                self._remove_file_from_category(filename, self.CATEGORY_PENDING)

        self._update_category_headers()
