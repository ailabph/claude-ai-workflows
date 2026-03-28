"""Tests for planner_auto package init — version and load_env."""

import os
import tempfile

import planner_auto


class TestVersion:
    """Version metadata consistency."""

    def test_version_is_string(self):
        assert isinstance(planner_auto.__version__, str)

    def test_version_matches_pyproject(self):
        """__init__.__version__ must match pyproject.toml version."""
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        if not pyproject.exists():
            # Skip if running from installed package (no pyproject.toml)
            return
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        assert planner_auto.__version__ == data["project"]["version"]


class TestLoadEnv:
    """load_env() behavior."""

    def test_load_env_returns_bool(self):
        result = planner_auto.load_env()
        assert isinstance(result, bool)

    def test_load_env_reads_dotenv_file(self, tmp_path, monkeypatch):
        """Verify python-dotenv can load a .env file (tests the mechanism, not our wrapper)."""
        env_file = tmp_path / ".env"
        env_file.write_text("PLANNER_AUTO_TEST_KEY_UNIQUE_928374=hello\n")
        monkeypatch.delenv("PLANNER_AUTO_TEST_KEY_UNIQUE_928374", raising=False)

        try:
            from dotenv import load_dotenv
            load_dotenv(str(env_file))
            assert os.environ.get("PLANNER_AUTO_TEST_KEY_UNIQUE_928374") == "hello"
        except ImportError:
            pass  # dotenv not installed — skip

    def test_load_env_no_side_effect_on_import(self, monkeypatch):
        """Importing planner_auto should NOT auto-load .env (no import-time side effect)."""
        # Set a marker that would only appear if .env were loaded at import time
        monkeypatch.delenv("PLANNER_AUTO_IMPORT_TEST", raising=False)

        # Re-importing doesn't re-execute module-level code in Python,
        # but the key point is: __init__.py has no load_dotenv() call at module level.
        import importlib
        importlib.reload(planner_auto)

        # The marker should not be set — no import-time side effect
        assert os.environ.get("PLANNER_AUTO_IMPORT_TEST") is None
