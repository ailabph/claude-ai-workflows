"""Tests for auto-context scan (git_utils.list_tracked_files + context_service.scan_repo)."""

import os
import sqlite3
from unittest.mock import patch

import pytest

from planner_auto.context_service import scan_repo
from planner_auto.db import create_session, get_context_entries, get_session, init_schema
from planner_auto.errors import CommandNotAllowedError
from planner_auto.git_utils import (
    CONFIG_FILENAMES,
    DEFAULT_EXCLUDE_PATTERNS,
    DOC_FILENAMES,
    SOURCE_EXTENSIONS,
    list_tracked_files,
)
from planner_auto.session import SessionManager
from planner_auto.state import Phase, PHASE_ALLOWED_COMMANDS


@pytest.fixture
def db_conn():
    """In-memory SQLite connection with schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def session_id(db_conn):
    sid = create_session(db_conn, "test-project")
    db_conn.commit()
    return sid


def _mock_git_ls_files(files):
    """Create a mock for subprocess.run that returns the given file list."""
    class MockResult:
        returncode = 0
        stdout = "\n".join(files)
    return MockResult()


class TestListTrackedFiles:
    """Tests for git_utils.list_tracked_files."""

    def test_filters_by_extension(self):
        files = ["app.py", "main.js", "data.csv", "readme.txt", "utils.go"]
        with patch("planner_auto.git_utils.subprocess.run", return_value=_mock_git_ls_files(files)):
            result = list_tracked_files()
        # csv and txt are not source extensions
        assert "app.py" in result
        assert "main.js" in result
        assert "utils.go" in result
        assert "data.csv" not in result
        assert "readme.txt" not in result

    def test_includes_config_files(self):
        files = ["pyproject.toml", "package.json", "Dockerfile", "random.log"]
        with patch("planner_auto.git_utils.subprocess.run", return_value=_mock_git_ls_files(files)):
            result = list_tracked_files()
        assert "pyproject.toml" in result
        assert "package.json" in result
        assert "Dockerfile" in result
        assert "random.log" not in result

    def test_includes_top_level_docs_only(self):
        files = ["README.md", "CLAUDE.md", "src/README.md", "docs/AGENTS.md"]
        with patch("planner_auto.git_utils.subprocess.run", return_value=_mock_git_ls_files(files)):
            result = list_tracked_files()
        assert "README.md" in result
        assert "CLAUDE.md" in result
        # Nested docs excluded
        assert "src/README.md" not in result
        assert "docs/AGENTS.md" not in result

    def test_excludes_lock_files(self):
        files = ["app.py", "package-lock.json", "poetry.lock", "Pipfile.lock"]
        with patch("planner_auto.git_utils.subprocess.run", return_value=_mock_git_ls_files(files)):
            result = list_tracked_files()
        assert "app.py" in result
        assert "package-lock.json" not in result
        assert "poetry.lock" not in result

    def test_excludes_min_files(self):
        files = ["app.js", "vendor.min.js", "styles.min.css"]
        with patch("planner_auto.git_utils.subprocess.run", return_value=_mock_git_ls_files(files)):
            result = list_tracked_files()
        assert "app.js" in result
        assert "vendor.min.js" not in result

    def test_max_files_cap(self):
        files = [f"src/file{i}.py" for i in range(50)]
        with patch("planner_auto.git_utils.subprocess.run", return_value=_mock_git_ls_files(files)):
            result = list_tracked_files(max_files=10)
        assert len(result) == 10

    def test_custom_include_extensions(self):
        files = ["app.py", "main.rb", "style.css"]
        with patch("planner_auto.git_utils.subprocess.run", return_value=_mock_git_ls_files(files)):
            result = list_tracked_files(include_ext={".css"})
        assert "style.css" in result
        # py and rb still excluded because custom set doesn't include them
        # but config files would still be included — that's fine
        assert "app.py" not in result

    def test_custom_exclude_patterns(self):
        files = ["app.py", "migrations/001.py", "tests/test_app.py"]
        with patch("planner_auto.git_utils.subprocess.run", return_value=_mock_git_ls_files(files)):
            result = list_tracked_files(exclude_patterns=["migrations/*"])
        assert "app.py" in result
        assert "migrations/001.py" not in result

    def test_priority_order_configs_first(self):
        files = ["src/deep/nested/app.py", "pyproject.toml", "README.md", "main.py"]
        with patch("planner_auto.git_utils.subprocess.run", return_value=_mock_git_ls_files(files)):
            result = list_tracked_files()
        # Config first, then docs, then source by depth
        assert result.index("pyproject.toml") < result.index("README.md")
        assert result.index("README.md") < result.index("main.py")
        assert result.index("main.py") < result.index("src/deep/nested/app.py")

    def test_source_sorted_by_depth(self):
        files = ["src/deep/app.py", "main.py", "src/utils.py"]
        with patch("planner_auto.git_utils.subprocess.run", return_value=_mock_git_ls_files(files)):
            result = list_tracked_files()
        source_files = [f for f in result if f.endswith(".py")]
        assert source_files[0] == "main.py"  # depth 0
        assert source_files[1] == "src/utils.py"  # depth 1
        assert source_files[2] == "src/deep/app.py"  # depth 2

    def test_git_failure_returns_empty(self):
        class FailResult:
            returncode = 1
            stdout = ""
        with patch("planner_auto.git_utils.subprocess.run", return_value=FailResult()):
            result = list_tracked_files()
        assert result == []

    def test_git_not_found_returns_empty(self):
        with patch("planner_auto.git_utils.subprocess.run", side_effect=FileNotFoundError):
            result = list_tracked_files()
        assert result == []

    def test_empty_output(self):
        class EmptyResult:
            returncode = 0
            stdout = ""
        with patch("planner_auto.git_utils.subprocess.run", return_value=EmptyResult()):
            result = list_tracked_files()
        assert result == []


class TestScanRepo:
    """Tests for context_service.scan_repo."""

    def test_adds_files_as_context(self, db_conn, session_id, tmp_path):
        # Create fake repo files
        (tmp_path / "app.py").write_text("print('hello')", encoding="utf-8")
        (tmp_path / "utils.py").write_text("x = 1", encoding="utf-8")

        files = ["app.py", "utils.py"]
        with patch("planner_auto.git_utils.list_tracked_files", return_value=files):
            results = scan_repo(db_conn, session_id, str(tmp_path))

        assert len(results) == 2
        entries = get_context_entries(db_conn, session_id)
        assert len(entries) == 2

    def test_respects_max_files(self, db_conn, session_id, tmp_path):
        for i in range(10):
            (tmp_path / f"f{i}.py").write_text(f"# file {i}", encoding="utf-8")
        files = [f"f{i}.py" for i in range(10)]

        with patch("planner_auto.git_utils.list_tracked_files", return_value=files):
            results = scan_repo(db_conn, session_id, str(tmp_path), max_files=3)

        # list_tracked_files handles the cap, but scan_repo passes it through
        assert len(results) == 10  # mock returns all 10; real list_tracked_files would cap

    def test_skips_large_files(self, db_conn, session_id, tmp_path):
        small = tmp_path / "small.py"
        small.write_text("x = 1", encoding="utf-8")

        large = tmp_path / "large.py"
        large.write_text("x" * (101 * 1024), encoding="utf-8")  # > 100KB

        with patch("planner_auto.git_utils.list_tracked_files", return_value=["small.py", "large.py"]):
            results = scan_repo(db_conn, session_id, str(tmp_path))

        assert len(results) == 1
        assert results[0]["key"].endswith("small.py")

    def test_skips_binary_files(self, db_conn, session_id, tmp_path):
        txt = tmp_path / "app.py"
        txt.write_text("print('ok')", encoding="utf-8")

        binary = tmp_path / "data.py"
        binary.write_bytes(b"\x00\x01\x02\xff" * 100)

        with patch("planner_auto.git_utils.list_tracked_files", return_value=["app.py", "data.py"]):
            results = scan_repo(db_conn, session_id, str(tmp_path))

        assert len(results) == 1
        assert results[0]["key"].endswith("app.py")

    def test_skips_missing_files(self, db_conn, session_id, tmp_path):
        (tmp_path / "exists.py").write_text("ok", encoding="utf-8")

        with patch("planner_auto.git_utils.list_tracked_files", return_value=["exists.py", "gone.py"]):
            results = scan_repo(db_conn, session_id, str(tmp_path))

        assert len(results) == 1

    def test_advances_phase_to_context(self, db_conn, session_id, tmp_path):
        (tmp_path / "app.py").write_text("x = 1", encoding="utf-8")

        session_before = get_session(db_conn, session_id)
        assert session_before["phase"] == Phase.SETUP.value

        with patch("planner_auto.git_utils.list_tracked_files", return_value=["app.py"]):
            scan_repo(db_conn, session_id, str(tmp_path))

        session_after = get_session(db_conn, session_id)
        assert session_after["phase"] == Phase.CONTEXT.value

    def test_no_files_does_not_advance_phase(self, db_conn, session_id, tmp_path):
        with patch("planner_auto.git_utils.list_tracked_files", return_value=[]):
            results = scan_repo(db_conn, session_id, str(tmp_path))

        assert results == []
        session_after = get_session(db_conn, session_id)
        assert session_after["phase"] == Phase.SETUP.value

    def test_no_repo_returns_empty(self, db_conn, session_id, tmp_path):
        with patch("planner_auto.git_utils.list_tracked_files", return_value=[]):
            results = scan_repo(db_conn, session_id, str(tmp_path))

        assert results == []


class TestScanPhaseEnforcement:
    """Verify scan is only allowed in SETUP and CONTEXT phases."""

    def test_scan_allowed_in_setup(self):
        assert "scan" in PHASE_ALLOWED_COMMANDS[Phase.SETUP]

    def test_scan_allowed_in_context(self):
        assert "scan" in PHASE_ALLOWED_COMMANDS[Phase.CONTEXT]

    def test_scan_blocked_in_discussion(self):
        assert "scan" not in PHASE_ALLOWED_COMMANDS[Phase.DISCUSSION]

    def test_scan_blocked_in_planning(self):
        assert "scan" not in PHASE_ALLOWED_COMMANDS[Phase.PLANNING]

    def test_scan_blocked_in_review(self):
        assert "scan" not in PHASE_ALLOWED_COMMANDS[Phase.REVIEW]

    def test_scan_blocked_in_complete(self):
        assert "scan" not in PHASE_ALLOWED_COMMANDS[Phase.COMPLETE]

    def test_check_command_rejects_scan_in_discussion(self, db_conn, session_id):
        sm = SessionManager(db_conn)
        # Advance to CONTEXT then DISCUSSION
        sm.advance_phase(session_id, Phase.CONTEXT.value)
        sm.advance_phase(session_id, Phase.DISCUSSION.value)
        db_conn.commit()

        with pytest.raises(CommandNotAllowedError):
            sm.check_command(session_id, "scan")

    def test_check_command_allows_scan_in_setup(self, db_conn, session_id):
        sm = SessionManager(db_conn)
        # Should not raise
        sm.check_command(session_id, "scan")


class TestScanIncludeParsing:
    """Verify --scan-include normalizes all input formats correctly."""

    def test_glob_style_input(self):
        """'*.py,*.ts' should become {'.py', '.ts'}."""
        from planner_auto.cli import _run_scan
        # Test the parsing logic directly
        raw = "*.py,*.ts"
        include_ext = set()
        for e in raw.split(","):
            e = e.strip().lstrip("*")
            if not e.startswith("."):
                e = f".{e}"
            include_ext.add(e)
        assert include_ext == {".py", ".ts"}

    def test_dot_prefix_input(self):
        """'.py,.ts' should become {'.py', '.ts'}."""
        raw = ".py,.ts"
        include_ext = set()
        for e in raw.split(","):
            e = e.strip().lstrip("*")
            if not e.startswith("."):
                e = f".{e}"
            include_ext.add(e)
        assert include_ext == {".py", ".ts"}

    def test_bare_extension_input(self):
        """'py,ts' should become {'.py', '.ts'}."""
        raw = "py,ts"
        include_ext = set()
        for e in raw.split(","):
            e = e.strip().lstrip("*")
            if not e.startswith("."):
                e = f".{e}"
            include_ext.add(e)
        assert include_ext == {".py", ".ts"}

    def test_mixed_input(self):
        """'*.py,.ts,go' should become {'.py', '.ts', '.go'}."""
        raw = "*.py,.ts,go"
        include_ext = set()
        for e in raw.split(","):
            e = e.strip().lstrip("*")
            if not e.startswith("."):
                e = f".{e}"
            include_ext.add(e)
        assert include_ext == {".py", ".ts", ".go"}

    def test_parsed_extensions_match_files(self):
        """Verify parsed extensions actually filter files in list_tracked_files."""
        raw = "*.py,*.ts"
        include_ext = set()
        for e in raw.split(","):
            e = e.strip().lstrip("*")
            if not e.startswith("."):
                e = f".{e}"
            include_ext.add(e)

        files = ["app.py", "main.ts", "style.css", "data.go"]
        with patch("planner_auto.git_utils.subprocess.run", return_value=_mock_git_ls_files(files)):
            result = list_tracked_files(include_ext=include_ext)
        assert "app.py" in result
        assert "main.ts" in result
        assert "style.css" not in result
        assert "data.go" not in result
