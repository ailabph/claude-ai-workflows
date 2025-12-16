"""
Unit tests for git operations.
"""

import pytest
import tempfile
import os
import subprocess
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto import git


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmpdir, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmpdir, capture_output=True
        )
        yield tmpdir


@pytest.fixture
def temp_non_git_dir():
    """Create a temporary non-git directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestIsGitRepo:
    """Test is_git_repo function."""

    def test_is_git_repo_true(self, temp_git_repo):
        """Test that a git repo is detected."""
        assert git.is_git_repo(temp_git_repo) is True

    def test_is_git_repo_false(self, temp_non_git_dir):
        """Test that a non-git directory is detected."""
        assert git.is_git_repo(temp_non_git_dir) is False


class TestHasChanges:
    """Test has_changes function."""

    def test_no_changes(self, temp_git_repo):
        """Test no changes in clean repo."""
        assert git.has_changes(temp_git_repo) is False

    def test_has_untracked_file(self, temp_git_repo):
        """Test detection of untracked files."""
        # Create an untracked file
        test_file = Path(temp_git_repo) / "test.txt"
        test_file.write_text("test content")

        assert git.has_changes(temp_git_repo) is True

    def test_has_modified_file(self, temp_git_repo):
        """Test detection of modified tracked files."""
        # Create and commit a file
        test_file = Path(temp_git_repo) / "test.txt"
        test_file.write_text("initial")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_git_repo)

        # Modify the file
        test_file.write_text("modified")

        assert git.has_changes(temp_git_repo) is True


class TestGetChangedFiles:
    """Test get_changed_files function."""

    def test_empty_repo(self, temp_git_repo):
        """Test no files in clean repo."""
        assert git.get_changed_files(temp_git_repo) == []

    def test_untracked_files(self, temp_git_repo):
        """Test listing untracked files."""
        test_file = Path(temp_git_repo) / "newfile.txt"
        test_file.write_text("content")

        files = git.get_changed_files(temp_git_repo)
        assert "newfile.txt" in files


class TestStageAll:
    """Test stage_all function."""

    def test_stage_untracked(self, temp_git_repo):
        """Test staging untracked files."""
        test_file = Path(temp_git_repo) / "test.txt"
        test_file.write_text("content")

        success, msg = git.stage_all(temp_git_repo)
        assert success is True

    def test_stage_nothing(self, temp_git_repo):
        """Test staging when nothing to stage."""
        success, msg = git.stage_all(temp_git_repo)
        assert success is True


class TestCreateCommit:
    """Test create_commit function."""

    def test_create_commit(self, temp_git_repo):
        """Test creating a commit."""
        # Create and stage a file
        test_file = Path(temp_git_repo) / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo)

        success, msg = git.create_commit("Test commit message", temp_git_repo)
        assert success is True

        # Verify commit was created
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True
        )
        assert "Test commit message" in result.stdout

    def test_commit_nothing_staged(self, temp_git_repo):
        """Test commit fails when nothing staged."""
        success, msg = git.create_commit("Empty commit", temp_git_repo)
        assert success is False


class TestGenerateCommitMessage:
    """Test generate_commit_message function."""

    def test_simple_message(self):
        """Test simple commit message generation."""
        msg = git.generate_commit_message(
            "Add user authentication",
            []
        )
        assert "Add user authentication" in msg
        # Should NOT contain author info
        assert "Co-Authored-By" not in msg
        assert "Generated with" not in msg

    def test_with_milestones(self):
        """Test commit message with milestones."""
        milestones = [
            {"name": "Setup database", "status": "completed"},
            {"name": "Add API endpoints", "status": "completed"},
            {"name": "Write tests", "status": "pending"},
        ]
        msg = git.generate_commit_message(
            "Implement feature X",
            milestones
        )
        assert "Implement feature X" in msg
        assert "Setup database" in msg
        assert "Add API endpoints" in msg
        assert "Write tests" not in msg  # Not completed
        # Should NOT contain author info
        assert "Co-Authored-By" not in msg

    def test_long_feature_truncated(self):
        """Test that long feature descriptions are truncated."""
        long_desc = "A" * 100
        msg = git.generate_commit_message(long_desc, [])
        # Title should be truncated to ~72 chars
        first_line = msg.split('\n')[0]
        assert len(first_line) <= 72

    def test_no_author_info(self):
        """Test that commit message never includes author information."""
        msg = git.generate_commit_message(
            "Test feature",
            [{"name": "Milestone 1", "status": "completed"}]
        )
        # Explicitly check for common author patterns
        assert "Co-Authored-By" not in msg
        assert "co-authored-by" not in msg.lower()
        assert "Generated with" not in msg
        assert "Claude" not in msg
        assert "noreply@anthropic.com" not in msg


class TestAutoCommit:
    """Test auto_commit function."""

    def test_auto_commit_success(self, temp_git_repo):
        """Test successful auto-commit."""
        # Create a file
        test_file = Path(temp_git_repo) / "feature.py"
        test_file.write_text("def feature(): pass")

        milestones = [
            {"name": "Implement feature", "status": "completed"}
        ]

        success, msg = git.auto_commit(
            "Add new feature",
            milestones,
            temp_git_repo
        )
        assert success is True

        # Verify commit
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True
        )
        assert "Add new feature" in result.stdout

    def test_auto_commit_not_git_repo(self, temp_non_git_dir):
        """Test auto-commit fails in non-git directory."""
        success, msg = git.auto_commit(
            "Feature",
            [],
            temp_non_git_dir
        )
        assert success is False
        assert "Not a git repository" in msg

    def test_auto_commit_no_changes(self, temp_git_repo):
        """Test auto-commit skipped when no changes."""
        success, msg = git.auto_commit(
            "Feature",
            [],
            temp_git_repo
        )
        assert success is False
        assert "No changes to commit" in msg

    def test_auto_commit_no_author_info(self, temp_git_repo):
        """Test that auto-commit message has no author info."""
        # Create a file
        test_file = Path(temp_git_repo) / "test.py"
        test_file.write_text("# test")

        git.auto_commit("Test", [], temp_git_repo)

        # Check commit message
        result = subprocess.run(
            ["git", "log", "-1", "--format=%B"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True
        )
        commit_msg = result.stdout
        assert "Co-Authored-By" not in commit_msg
        assert "Claude" not in commit_msg
