"""
Unit tests for GitStatusPanel widget.
"""

import pytest
import tempfile
from pathlib import Path
from orchestrator_auto.tui.widgets import GitStatusPanel


class TestGitStatusPanel:
    """Test suite for GitStatusPanel widget."""

    def test_instantiation(self):
        """Test that GitStatusPanel can be instantiated."""
        panel = GitStatusPanel()
        assert panel is not None
        assert panel._branch == "—"
        assert panel._is_git_repo is True

    def test_format_file_count(self):
        """Test file count formatting."""
        panel = GitStatusPanel()

        assert panel._format_file_count(0) == "0"
        assert panel._format_file_count(1) == "1 file"
        assert panel._format_file_count(5) == "5 files"
        assert panel._format_file_count(100) == "100 files"

    def test_format_diff_stats_no_changes(self):
        """Test diff stats formatting with no changes."""
        panel = GitStatusPanel()
        panel._lines_added = 0
        panel._lines_removed = 0

        assert panel._format_diff_stats() == "No changes"

    def test_format_diff_stats_with_changes(self):
        """Test diff stats formatting with changes."""
        panel = GitStatusPanel()

        # Only additions
        panel._lines_added = 10
        panel._lines_removed = 0
        result = panel._format_diff_stats()
        assert "+10" in result
        assert "lines" in result

        # Only deletions
        panel._lines_added = 0
        panel._lines_removed = 5
        result = panel._format_diff_stats()
        assert "-5" in result
        assert "lines" in result

        # Both additions and deletions
        panel._lines_added = 10
        panel._lines_removed = 5
        result = panel._format_diff_stats()
        assert "+10" in result
        assert "-5" in result
        assert "lines" in result

    def test_format_status_marker(self):
        """Test git status marker formatting."""
        panel = GitStatusPanel()

        # Staged changes
        assert panel._format_status_marker('M', ' ') == 'M'  # Modified (staged)
        assert panel._format_status_marker('A', ' ') == 'A'  # Added (staged)
        assert panel._format_status_marker('D', ' ') == 'D'  # Deleted (staged)
        assert panel._format_status_marker('R', ' ') == 'R'  # Renamed (staged)

        # Unstaged changes
        assert panel._format_status_marker(' ', 'M') == 'M'  # Modified
        assert panel._format_status_marker(' ', 'D') == 'D'  # Deleted

        # Untracked
        assert panel._format_status_marker('?', '?') == '??'  # Untracked

    def test_refresh_in_git_repo(self):
        """Test refresh_git_status in a git repository."""
        panel = GitStatusPanel()

        # This test assumes we're running in the orchestrator-auto git repo
        panel.refresh_git_status()

        # Should have detected git repo
        assert panel._is_git_repo is True
        # Should have a branch name (not "—" or "Not a git repo")
        assert panel._branch != "—"
        assert panel._branch != "Not a git repo"
        # Counts should be non-negative
        assert panel._staged_count >= 0
        assert panel._changed_count >= 0
        assert panel._lines_added >= 0
        assert panel._lines_removed >= 0

    def test_refresh_in_non_git_directory(self):
        """Test refresh_git_status in a non-git directory."""
        panel = GitStatusPanel()

        # Test in a temp directory (not a git repo)
        with tempfile.TemporaryDirectory() as tmpdir:
            panel.refresh_git_status(tmpdir)

            # Should have detected non-git repo
            assert panel._is_git_repo is False
            assert panel._branch == "Not a git repo"
            # All counts should be zero
            assert panel._staged_count == 0
            assert panel._changed_count == 0
            assert panel._lines_added == 0
            assert panel._lines_removed == 0
            assert len(panel._modified_files) == 0

    def test_get_branch_name(self):
        """Test _get_branch_name method."""
        panel = GitStatusPanel()

        # In a git repo, should return a branch name
        branch = panel._get_branch_name()
        assert branch != "—"
        assert len(branch) > 0

    def test_get_branch_name_non_git(self):
        """Test _get_branch_name in non-git directory."""
        panel = GitStatusPanel()

        with tempfile.TemporaryDirectory() as tmpdir:
            branch = panel._get_branch_name(tmpdir)
            # Should return default value
            assert branch == "—"

    def test_get_file_status(self):
        """Test _get_file_status method."""
        panel = GitStatusPanel()

        # In a git repo
        staged, changed, files = panel._get_file_status()

        # Should return valid counts
        assert staged >= 0
        assert changed >= 0
        assert isinstance(files, list)
        # Files list should be limited to 6 items
        assert len(files) <= 6
        # Each file should be a tuple of (filename, status)
        for filename, status in files:
            assert isinstance(filename, str)
            assert isinstance(status, str)

    def test_get_file_status_non_git(self):
        """Test _get_file_status in non-git directory."""
        panel = GitStatusPanel()

        with tempfile.TemporaryDirectory() as tmpdir:
            staged, changed, files = panel._get_file_status(tmpdir)

            # Should return zeros
            assert staged == 0
            assert changed == 0
            assert len(files) == 0

    def test_get_diff_stats(self):
        """Test _get_diff_stats method."""
        panel = GitStatusPanel()

        # In a git repo
        added, removed = panel._get_diff_stats()

        # Should return valid counts
        assert added >= 0
        assert removed >= 0

    def test_get_diff_stats_non_git(self):
        """Test _get_diff_stats in non-git directory."""
        panel = GitStatusPanel()

        with tempfile.TemporaryDirectory() as tmpdir:
            added, removed = panel._get_diff_stats(tmpdir)

            # Should return zeros
            assert added == 0
            assert removed == 0

    def test_multiple_refreshes(self):
        """Test that multiple refreshes work correctly."""
        panel = GitStatusPanel()

        # First refresh
        panel.refresh_git_status()
        first_branch = panel._branch
        first_is_git = panel._is_git_repo

        # Second refresh (should work the same)
        panel.refresh_git_status()
        assert panel._branch == first_branch
        assert panel._is_git_repo == first_is_git

    def test_refresh_switches_between_git_and_non_git(self):
        """Test that panel correctly switches between git and non-git directories."""
        panel = GitStatusPanel()

        # First refresh in git repo
        panel.refresh_git_status()
        assert panel._is_git_repo is True

        # Refresh in non-git directory
        with tempfile.TemporaryDirectory() as tmpdir:
            panel.refresh_git_status(tmpdir)
            assert panel._is_git_repo is False
            assert panel._branch == "Not a git repo"

        # Refresh back in git repo
        panel.refresh_git_status()
        assert panel._is_git_repo is True
        assert panel._branch != "Not a git repo"
