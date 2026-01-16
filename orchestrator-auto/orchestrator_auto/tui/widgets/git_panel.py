"""
Git status panel widget for displaying repository status.

Shows branch name, staged/unstaged file counts, diff stats,
and list of modified files.
"""

import subprocess
from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Label, ListView, ListItem
from typing import Optional, List, Tuple


class GitFileItem(ListItem):
    """A single file item in the git file list."""

    def __init__(self, filename: str, status: str) -> None:
        super().__init__()
        self.filename = filename
        self.status = status

    def compose(self) -> ComposeResult:
        # Truncate filename if too long
        display_name = self.filename
        if len(display_name) > 20:
            display_name = display_name[:17] + "..."

        with Horizontal(classes="git-file-row"):
            yield Label(self.status, classes="git-status-marker")
            yield Label(display_name, classes="git-filename")


class GitStatusPanel(Static):
    """
    Panel showing real-time git repository status.

    Displays:
    - Current branch name
    - Number of staged files
    - Number of unstaged/modified files
    - Lines added/removed summary
    - List of modified files (truncated)

    Handles non-git directories gracefully by showing "Not a git repo".
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._branch: str = "—"
        self._staged_count: int = 0
        self._changed_count: int = 0
        self._lines_added: int = 0
        self._lines_removed: int = 0
        self._modified_files: List[Tuple[str, str]] = []
        self._is_git_repo: bool = True

    def compose(self) -> ComposeResult:
        yield Label("[b]GIT STATUS[/b]", classes="title")
        with Vertical(classes="git-info"):
            with Horizontal(classes="stat-row"):
                yield Label("Branch:", classes="stat-label")
                yield Label(self._branch, id="git-branch", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("Staged:", classes="stat-label")
                yield Label(self._format_file_count(self._staged_count), id="git-staged", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("Changed:", classes="stat-label")
                yield Label(self._format_file_count(self._changed_count), id="git-changed", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("", classes="stat-label")
                yield Label(self._format_diff_stats(), id="git-diff-stats", classes="stat-value git-diff-stats")
        yield Label("", classes="spacer")
        yield Label("Modified:", classes="section-title")
        yield ListView(id="git-files")

    def refresh_git_status(self, directory: Optional[str] = None) -> None:
        """
        Refresh git status from the repository.

        Args:
            directory: Directory to check git status in (defaults to current directory)
        """
        # Check if we're in a git repo
        try:
            if directory:
                result = subprocess.run(
                    ["git", "rev-parse", "--is-inside-work-tree"],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )
            else:
                result = subprocess.run(
                    ["git", "rev-parse", "--is-inside-work-tree"],
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )

            if result.returncode != 0:
                self._handle_not_git_repo()
                return

            self._is_git_repo = True
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            self._handle_not_git_repo()
            return

        # Get branch name
        self._branch = self._get_branch_name(directory)

        # Get file status
        self._staged_count, self._changed_count, self._modified_files = self._get_file_status(directory)

        # Get diff stats
        self._lines_added, self._lines_removed = self._get_diff_stats(directory)

        # Update UI
        self._update_display()

    def _handle_not_git_repo(self) -> None:
        """Handle case where directory is not a git repository."""
        self._is_git_repo = False
        self._branch = "Not a git repo"
        self._staged_count = 0
        self._changed_count = 0
        self._lines_added = 0
        self._lines_removed = 0
        self._modified_files = []
        self._update_display()

    def _get_branch_name(self, directory: Optional[str] = None) -> str:
        """Get current git branch name."""
        try:
            if directory:
                result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )
            else:
                result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )

            if result.returncode == 0:
                branch = result.stdout.strip()
                # Truncate long branch names
                if len(branch) > 20:
                    return branch[:17] + "..."
                return branch
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        return "—"

    def _get_file_status(self, directory: Optional[str] = None) -> Tuple[int, int, List[Tuple[str, str]]]:
        """
        Get git file status counts and list of modified files.

        Returns:
            Tuple of (staged_count, changed_count, modified_files)
            where modified_files is a list of (filename, status) tuples
        """
        staged = 0
        changed = 0
        files = []

        try:
            if directory:
                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )
            else:
                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue

                    # Parse porcelain format: XY filename
                    if len(line) < 3:
                        continue

                    x_status = line[0]  # Staged status
                    y_status = line[1]  # Unstaged status
                    filename = line[3:].strip()

                    # Count staged files (X column not space)
                    if x_status != ' ' and x_status != '?':
                        staged += 1

                    # Count changed files (Y column not space or ?=untracked)
                    if y_status != ' ':
                        changed += 1

                    # For untracked files (??)
                    if x_status == '?' and y_status == '?':
                        changed += 1

                    # Add to list (limit to 6 most recent)
                    if len(files) < 6:
                        status_marker = self._format_status_marker(x_status, y_status)
                        files.append((filename, status_marker))

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        return staged, changed, files

    def _format_status_marker(self, x: str, y: str) -> str:
        """Format git status into a readable marker."""
        # Staged changes
        if x == 'M':
            return 'M'  # Modified (staged)
        elif x == 'A':
            return 'A'  # Added (staged)
        elif x == 'D':
            return 'D'  # Deleted (staged)
        elif x == 'R':
            return 'R'  # Renamed (staged)

        # Unstaged changes
        if y == 'M':
            return 'M'  # Modified
        elif y == 'D':
            return 'D'  # Deleted

        # Untracked
        if x == '?' and y == '?':
            return '??'  # Untracked

        return '??'

    def _get_diff_stats(self, directory: Optional[str] = None) -> Tuple[int, int]:
        """
        Get diff statistics (lines added/removed).

        Returns:
            Tuple of (lines_added, lines_removed)
        """
        added = 0
        removed = 0

        try:
            # Get diff stats for unstaged changes
            if directory:
                result = subprocess.run(
                    ["git", "diff", "--stat", "--stat-width=80"],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )
            else:
                result = subprocess.run(
                    ["git", "diff", "--stat", "--stat-width=80"],
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )

            if result.returncode == 0:
                # Parse the summary line (last line)
                lines = result.stdout.strip().split("\n")
                if lines and lines[-1]:
                    # Format: "N files changed, X insertions(+), Y deletions(-)"
                    summary = lines[-1]
                    if "insertion" in summary:
                        parts = summary.split(",")
                        for part in parts:
                            if "insertion" in part:
                                added = int(part.strip().split()[0])
                            elif "deletion" in part:
                                removed = int(part.strip().split()[0])

            # Also check staged changes
            if directory:
                result = subprocess.run(
                    ["git", "diff", "--cached", "--stat", "--stat-width=80"],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )
            else:
                result = subprocess.run(
                    ["git", "diff", "--cached", "--stat", "--stat-width=80"],
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )

            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if lines and lines[-1]:
                    summary = lines[-1]
                    if "insertion" in summary:
                        parts = summary.split(",")
                        for part in parts:
                            if "insertion" in part:
                                added += int(part.strip().split()[0])
                            elif "deletion" in part:
                                removed += int(part.strip().split()[0])

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        return added, removed

    def _format_file_count(self, count: int) -> str:
        """Format file count as 'N files' or '0'."""
        if count == 0:
            return "0"
        elif count == 1:
            return "1 file"
        else:
            return f"{count} files"

    def _format_diff_stats(self) -> str:
        """Format diff stats as '+N -M lines'."""
        if self._lines_added == 0 and self._lines_removed == 0:
            return "No changes"

        parts = []
        if self._lines_added > 0:
            parts.append(f"+{self._lines_added}")
        if self._lines_removed > 0:
            parts.append(f"-{self._lines_removed}")

        return " ".join(parts) + " lines"

    def _update_display(self) -> None:
        """Update all UI elements with current status."""
        if not self.is_mounted:
            return

        try:
            # Update branch
            self.query_one("#git-branch", Label).update(self._branch)

            # Update file counts
            self.query_one("#git-staged", Label).update(self._format_file_count(self._staged_count))
            self.query_one("#git-changed", Label).update(self._format_file_count(self._changed_count))

            # Update diff stats
            self.query_one("#git-diff-stats", Label).update(self._format_diff_stats())

            # Update file list
            list_view = self.query_one("#git-files", ListView)
            list_view.clear()

            for filename, status in self._modified_files:
                item = GitFileItem(filename, status)
                list_view.append(item)

        except Exception:
            pass
