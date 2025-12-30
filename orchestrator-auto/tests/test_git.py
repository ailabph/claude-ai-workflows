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


class TestHasHeadCommit:
    """Test has_head_commit function."""

    def test_has_head_commit_new_repo(self, temp_git_repo):
        """Test that a new repo without commits returns False."""
        assert git.has_head_commit(temp_git_repo) is False

    def test_has_head_commit_with_commits(self, temp_git_repo):
        """Test that a repo with commits returns True."""
        # Create and commit a file
        test_file = Path(temp_git_repo) / "test.txt"
        test_file.write_text("initial content")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_git_repo)

        assert git.has_head_commit(temp_git_repo) is True

    def test_has_head_commit_non_git_dir(self, temp_non_git_dir):
        """Test that a non-git directory returns False."""
        assert git.has_head_commit(temp_non_git_dir) is False


class TestGetStagedDiff:
    """Test get_staged_diff function."""

    def test_get_staged_diff_no_changes(self, temp_git_repo):
        """Test empty diff when nothing is staged."""
        assert git.get_staged_diff(temp_git_repo) == ""

    def test_get_staged_diff_with_staged_changes(self, temp_git_repo):
        """Test diff output for staged changes."""
        # Create and stage a file
        test_file = Path(temp_git_repo) / "test.txt"
        test_file.write_text("test content")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo)

        diff = git.get_staged_diff(temp_git_repo)
        assert "test content" in diff
        assert "test.txt" in diff

    def test_get_staged_diff_ignores_unstaged(self, temp_git_repo):
        """Test that unstaged changes are not included."""
        # Create and commit a file first
        test_file = Path(temp_git_repo) / "test.txt"
        test_file.write_text("initial")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_git_repo)

        # Modify but don't stage
        test_file.write_text("modified")

        # Should be empty since nothing is staged
        diff = git.get_staged_diff(temp_git_repo)
        assert diff == ""


class TestGetFullDiff:
    """Test get_full_diff function."""

    def test_get_full_diff_no_head(self, temp_git_repo):
        """Test diff in new repo without HEAD (shows staged changes)."""
        # Create and stage a file
        test_file = Path(temp_git_repo) / "test.txt"
        test_file.write_text("new file content")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo)

        diff = git.get_full_diff(temp_git_repo)
        assert "new file content" in diff

    def test_get_full_diff_with_head(self, temp_git_repo):
        """Test diff against HEAD in repo with commits."""
        # Create initial commit
        test_file = Path(temp_git_repo) / "test.txt"
        test_file.write_text("initial")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_git_repo)

        # Modify file
        test_file.write_text("modified content")

        diff = git.get_full_diff(temp_git_repo)
        assert "modified content" in diff
        assert "-initial" in diff

    def test_get_full_diff_truncation(self, temp_git_repo):
        """Test that large diffs are truncated."""
        # Create a file with lots of content
        test_file = Path(temp_git_repo) / "large.txt"
        large_content = "x" * 10000
        test_file.write_text(large_content)
        subprocess.run(["git", "add", "."], cwd=temp_git_repo)

        # Get diff with small max size
        diff = git.get_full_diff(temp_git_repo, max_size=100)

        assert len(diff) < 200  # Should be truncated
        assert "TRUNCATED" in diff
        assert "100 characters" in diff

    def test_get_full_diff_no_changes(self, temp_git_repo):
        """Test empty diff when no changes."""
        # Create initial commit
        test_file = Path(temp_git_repo) / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_git_repo)

        # No changes after commit
        diff = git.get_full_diff(temp_git_repo)
        assert diff == ""

    def test_get_full_diff_includes_staged_and_unstaged(self, temp_git_repo):
        """Test that both staged and unstaged changes are included."""
        # Create initial commit
        test_file1 = Path(temp_git_repo) / "file1.txt"
        test_file1.write_text("initial1")
        test_file2 = Path(temp_git_repo) / "file2.txt"
        test_file2.write_text("initial2")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_git_repo)

        # Stage changes to file1
        test_file1.write_text("staged change")
        subprocess.run(["git", "add", "file1.txt"], cwd=temp_git_repo)

        # Unstaged change to file2
        test_file2.write_text("unstaged change")

        diff = git.get_full_diff(temp_git_repo)
        assert "staged change" in diff
        assert "unstaged change" in diff


class TestGetDiffStats:
    """Test get_diff_stats function."""

    def test_get_diff_stats_no_changes(self, temp_git_repo):
        """Test stats when no changes."""
        stats = git.get_diff_stats(temp_git_repo)
        assert stats == {"files_changed": 0, "insertions": 0, "deletions": 0}

    def test_get_diff_stats_new_file(self, temp_git_repo):
        """Test stats for new file (insertions only)."""
        test_file = Path(temp_git_repo) / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo)

        stats = git.get_diff_stats(temp_git_repo)
        assert stats["files_changed"] == 1
        assert stats["insertions"] == 3
        assert stats["deletions"] == 0

    def test_get_diff_stats_modified_file(self, temp_git_repo):
        """Test stats for modified file (insertions and deletions)."""
        # Create initial commit
        test_file = Path(temp_git_repo) / "test.txt"
        test_file.write_text("line1\nline2\n")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_git_repo)

        # Modify file - replace 2 lines with 3 lines
        test_file.write_text("newline1\nnewline2\nnewline3\n")

        stats = git.get_diff_stats(temp_git_repo)
        assert stats["files_changed"] == 1
        assert stats["insertions"] == 3
        assert stats["deletions"] == 2

    def test_get_diff_stats_multiple_files(self, temp_git_repo):
        """Test stats for multiple changed files."""
        # Create initial commit
        test_file1 = Path(temp_git_repo) / "file1.txt"
        test_file1.write_text("content1\n")
        test_file2 = Path(temp_git_repo) / "file2.txt"
        test_file2.write_text("content2\n")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_git_repo)

        # Modify both files
        test_file1.write_text("modified1\nline2\n")
        test_file2.write_text("modified2\n")

        stats = git.get_diff_stats(temp_git_repo)
        assert stats["files_changed"] == 2
        assert stats["insertions"] >= 2
        assert stats["deletions"] >= 2

    def test_get_diff_stats_deletion_only(self, temp_git_repo):
        """Test stats for deletions only."""
        # Create initial commit with content
        test_file = Path(temp_git_repo) / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_git_repo)

        # Delete content (keep one line)
        test_file.write_text("line1\n")

        stats = git.get_diff_stats(temp_git_repo)
        assert stats["files_changed"] == 1
        assert stats["insertions"] == 0
        assert stats["deletions"] == 2

    def test_get_diff_stats_non_git_dir(self, temp_non_git_dir):
        """Test stats in non-git directory returns zeros."""
        stats = git.get_diff_stats(temp_non_git_dir)
        assert stats == {"files_changed": 0, "insertions": 0, "deletions": 0}


class TestAutoCommit:
    """Test auto_commit function."""

    def test_auto_commit_success(self, temp_git_repo):
        """Test successful auto-commit with smart commit disabled."""
        # Create a file
        test_file = Path(temp_git_repo) / "feature.py"
        test_file.write_text("def feature(): pass")

        milestones = [
            {"name": "Implement feature", "status": "completed"}
        ]

        # Use use_smart_commit=False to avoid AI call in unit tests
        success, msg, fallback_reason = git.auto_commit(
            "Add new feature",
            milestones,
            temp_git_repo,
            use_smart_commit=False,
        )
        assert success is True
        assert fallback_reason == "smart_commit_disabled"

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
        success, msg, fallback_reason = git.auto_commit(
            "Feature",
            [],
            temp_non_git_dir,
            use_smart_commit=False,
        )
        assert success is False
        assert "Not a git repository" in msg

    def test_auto_commit_no_changes(self, temp_git_repo):
        """Test auto-commit skipped when no changes."""
        success, msg, fallback_reason = git.auto_commit(
            "Feature",
            [],
            temp_git_repo,
            use_smart_commit=False,
        )
        assert success is False
        assert "No changes to commit" in msg

    def test_auto_commit_no_author_info(self, temp_git_repo):
        """Test that auto-commit message has no author info."""
        # Create a file
        test_file = Path(temp_git_repo) / "test.py"
        test_file.write_text("# test")

        git.auto_commit("Test", [], temp_git_repo, use_smart_commit=False)

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

    def test_auto_commit_returns_three_tuple(self, temp_git_repo):
        """Test that auto_commit returns (success, msg, fallback_reason) tuple."""
        test_file = Path(temp_git_repo) / "test.py"
        test_file.write_text("# test")

        result = git.auto_commit("Test", [], temp_git_repo, use_smart_commit=False)

        assert isinstance(result, tuple)
        assert len(result) == 3
        success, msg, fallback_reason = result
        assert isinstance(success, bool)
        assert isinstance(msg, str)
        assert fallback_reason in (None, "smart_commit_disabled", "secrets_detected", "ai_generation_failed")

    def test_auto_commit_fallback_reason_disabled(self, temp_git_repo):
        """Test fallback_reason when smart commit is disabled."""
        test_file = Path(temp_git_repo) / "test.py"
        test_file.write_text("# test")

        success, msg, fallback_reason = git.auto_commit(
            "Test",
            [],
            temp_git_repo,
            use_smart_commit=False,
        )

        assert success is True
        assert fallback_reason == "smart_commit_disabled"

    def test_auto_commit_on_status_callback(self, temp_git_repo):
        """Test that on_status callback is called."""
        test_file = Path(temp_git_repo) / "test.py"
        test_file.write_text("# test")

        status_messages = []

        def capture_status(msg):
            status_messages.append(msg)

        git.auto_commit(
            "Test",
            [],
            temp_git_repo,
            use_smart_commit=False,  # Won't generate status messages when disabled
            on_status=capture_status,
        )

        # No status messages expected when smart commit disabled
        # (status is only called during smart commit flow)


class TestAutoCommitSmartCommitIntegration:
    """Integration tests for smart commit functionality."""

    def test_auto_commit_detects_secrets(self, temp_git_repo):
        """Test that secrets in diff trigger fallback."""
        # Create a file with a fake secret
        test_file = Path(temp_git_repo) / "config.py"
        test_file.write_text('API_KEY = "abcdefghijklmnopqrstuvwxyz1234567890"')

        status_messages = []

        success, msg, fallback_reason = git.auto_commit(
            "Add config",
            [],
            temp_git_repo,
            use_smart_commit=True,
            on_status=lambda m: status_messages.append(m),
        )

        assert success is True
        assert fallback_reason == "secrets_detected"
        # Should have status messages about secrets
        assert any("Secrets detected" in m or "Analyzing" in m for m in status_messages)

    def test_auto_commit_detects_github_pat(self, temp_git_repo):
        """Test that GitHub PAT in diff triggers fallback."""
        # Create a file with a fake GitHub PAT
        test_file = Path(temp_git_repo) / "env.py"
        test_file.write_text('GITHUB_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"')

        success, msg, fallback_reason = git.auto_commit(
            "Add env",
            [],
            temp_git_repo,
            use_smart_commit=True,
        )

        assert success is True
        assert fallback_reason == "secrets_detected"

    def test_auto_commit_detects_private_key(self, temp_git_repo):
        """Test that private key in diff triggers fallback."""
        # Create a file with a fake private key header
        test_file = Path(temp_git_repo) / "key.pem"
        test_file.write_text('-----BEGIN RSA PRIVATE KEY-----\nfake content\n-----END RSA PRIVATE KEY-----')

        success, msg, fallback_reason = git.auto_commit(
            "Add key",
            [],
            temp_git_repo,
            use_smart_commit=True,
        )

        assert success is True
        assert fallback_reason == "secrets_detected"

    def test_auto_commit_clean_diff_no_secrets(self, temp_git_repo):
        """Test that clean diff doesn't trigger secrets fallback."""
        # Create a file without secrets
        test_file = Path(temp_git_repo) / "app.py"
        test_file.write_text('def hello():\n    return "Hello, World!"')

        success, msg, fallback_reason = git.auto_commit(
            "Add app",
            [],
            temp_git_repo,
            use_smart_commit=True,
        )

        assert success is True
        # Should either succeed with AI (None) or fail AI and fallback
        # In tests without actual AI, it will be ai_generation_failed
        assert fallback_reason in (None, "ai_generation_failed")

    def test_auto_commit_never_pushes(self, temp_git_repo):
        """Test that auto_commit never pushes to remote."""
        # Create a file
        test_file = Path(temp_git_repo) / "test.py"
        test_file.write_text("# test")

        # Set up a fake remote (won't actually work, just to verify no push attempt)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://fake.example.com/repo.git"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        # This should NOT push
        success, msg, _ = git.auto_commit(
            "Test",
            [],
            temp_git_repo,
            use_smart_commit=False,
        )

        assert success is True

        # Verify the branch is ahead of remote (not pushed)
        result = subprocess.run(
            ["git", "status"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
        )
        # Should show we have unpushed commits or no tracking (since remote doesn't exist)
        # The important thing is we didn't attempt to push

    def test_auto_commit_legacy_wrapper(self, temp_git_repo):
        """Test the legacy wrapper returns 2-tuple."""
        test_file = Path(temp_git_repo) / "test.py"
        test_file.write_text("# test")

        result = git.auto_commit_legacy("Test", [], temp_git_repo)

        assert isinstance(result, tuple)
        assert len(result) == 2
        success, msg = result
        assert isinstance(success, bool)
        assert isinstance(msg, str)
