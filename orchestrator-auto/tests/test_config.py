"""
Unit tests for configuration management.
"""

import pytest
import tempfile
import os
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto import config


class TestModelAliases:
    """Test model alias resolution."""

    def test_resolve_opus_alias(self):
        """Test that 'opus' resolves to full model ID."""
        result = config.resolve_model("opus")
        assert result == "claude-opus-4-6"

    def test_resolve_sonnet_alias(self):
        """Test that 'sonnet' resolves to full model ID."""
        result = config.resolve_model("sonnet")
        assert result == "claude-sonnet-4-6"

    def test_resolve_haiku_alias(self):
        """Test that 'haiku' resolves to full model ID."""
        result = config.resolve_model("haiku")
        assert result == "claude-3-5-haiku-20241022"

    def test_resolve_alias_case_insensitive(self):
        """Test that alias resolution is case insensitive."""
        assert config.resolve_model("OPUS") == "claude-opus-4-6"
        assert config.resolve_model("Sonnet") == "claude-sonnet-4-6"
        assert config.resolve_model("HaIkU") == "claude-3-5-haiku-20241022"

    def test_resolve_full_model_id(self):
        """Test that full model IDs pass through unchanged."""
        full_id = "claude-opus-4-6"
        result = config.resolve_model(full_id)
        assert result == full_id

    def test_resolve_none(self):
        """Test that None input returns None."""
        result = config.resolve_model(None)
        assert result is None


class TestModelDisplayName:
    """Test model display name generation."""

    def test_display_name_opus(self):
        """Test display name for opus model."""
        result = config.get_model_display_name("claude-opus-4-6")
        assert result == "opus-4.5"

    def test_display_name_sonnet(self):
        """Test display name for sonnet model."""
        result = config.get_model_display_name("claude-sonnet-4-6")
        assert result == "sonnet-4.5"

    def test_display_name_haiku(self):
        """Test display name for haiku model."""
        result = config.get_model_display_name("claude-3-5-haiku-20241022")
        assert result == "haiku-3.5"

    def test_display_name_unknown_model(self):
        """Test display name for unknown model with 202x date."""
        # The function strips "claude-" prefix and cuts at "-202" pattern
        result = config.get_model_display_name("claude-future-model-20260101")
        assert result == "future-model"

    def test_display_name_unknown_model_no_date(self):
        """Test display name for model without date pattern."""
        result = config.get_model_display_name("claude-custom-model")
        assert result == "custom-model"


class TestDefaultModels:
    """Test default model getters."""

    def test_default_planner_model(self):
        """Test that default planner model is opus."""
        result = config.get_planner_model(None)
        assert result == "claude-opus-4-6"

    def test_default_executor_model(self):
        """Test that default executor model is sonnet."""
        result = config.get_executor_model(None)
        assert result == "claude-sonnet-4-6"

    def test_cli_planner_model_override(self):
        """Test that CLI model overrides default."""
        result = config.get_planner_model("haiku")
        assert result == "claude-3-5-haiku-20241022"

    def test_cli_executor_model_override(self):
        """Test that CLI model overrides default."""
        result = config.get_executor_model("opus")
        assert result == "claude-opus-4-6"


class TestListModels:
    """Test model listing."""

    def test_list_available_models(self):
        """Test that available models are listed."""
        models = config.list_available_models()

        assert "opus" in models
        assert "sonnet" in models
        assert "haiku" in models
        assert len(models) == 3


# ============================================================================
# Phase 2: Repo-Local Config Tests
# ============================================================================


class TestRepoConfigDiscovery:
    """Test repo-local config discovery."""

    def test_find_repo_root_in_git_repo(self, tmp_path):
        """Test finding repo root in a git repository."""
        # Create a fake git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        subdir = tmp_path / "src" / "components"
        subdir.mkdir(parents=True)

        # Find repo root from subdir
        result = config.find_repo_root(subdir)
        assert result == tmp_path

    def test_find_repo_root_no_git(self, tmp_path):
        """Test finding repo root when not in git repo."""
        subdir = tmp_path / "some" / "deep" / "path"
        subdir.mkdir(parents=True)

        result = config.find_repo_root(subdir)
        assert result is None

    def test_find_repo_config_exists(self, tmp_path):
        """Test finding repo config when it exists."""
        # Create fake git repo and config
        (tmp_path / ".git").mkdir()
        config_dir = tmp_path / ".claude_orchestrator"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("telegram:\n  enabled: true\n")

        # Find config from repo root
        result = config.find_repo_config(tmp_path)
        assert result == config_file

    def test_find_repo_config_in_subdir(self, tmp_path):
        """Test finding repo config from a subdirectory."""
        # Create fake git repo and config
        (tmp_path / ".git").mkdir()
        config_dir = tmp_path / ".claude_orchestrator"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("telegram:\n  enabled: true\n")

        # Create subdirectory
        subdir = tmp_path / "src" / "components"
        subdir.mkdir(parents=True)

        # Find config from subdir
        result = config.find_repo_config(subdir)
        assert result == config_file

    def test_find_repo_config_stops_at_git_boundary(self, tmp_path):
        """Test that config search stops at git root."""
        # Create parent config (should NOT be found)
        parent_config = tmp_path / ".claude_orchestrator"
        parent_config.mkdir()
        (parent_config / "config.yaml").write_text("parent: true\n")

        # Create nested git repo (no config inside)
        nested_repo = tmp_path / "nested_project"
        nested_repo.mkdir()
        (nested_repo / ".git").mkdir()

        # Search from nested repo should NOT find parent config
        result = config.find_repo_config(nested_repo)
        assert result is None

    def test_find_repo_config_none_exists(self, tmp_path):
        """Test finding repo config when it doesn't exist."""
        (tmp_path / ".git").mkdir()

        result = config.find_repo_config(tmp_path)
        assert result is None


class TestConfigMerge:
    """Test config merge semantics."""

    def test_deep_merge_simple(self):
        """Test simple deep merge."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}

        result = config._deep_merge(base, override)

        assert result == {"a": 1, "b": 3, "c": 4}

    def test_deep_merge_nested(self):
        """Test deep merge with nested dicts."""
        base = {
            "telegram": {"enabled": True, "bot_token": "old"},
            "models": {"planner": "opus"}
        }
        override = {
            "telegram": {"bot_token": "new", "chat_id": "123"}
        }

        result = config._deep_merge(base, override)

        assert result["telegram"]["enabled"] is True  # from base
        assert result["telegram"]["bot_token"] == "new"  # from override
        assert result["telegram"]["chat_id"] == "123"  # from override
        assert result["models"]["planner"] == "opus"  # from base

    def test_load_repo_config(self, tmp_path):
        """Test loading repo config file."""
        config_dir = tmp_path / ".claude_orchestrator"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("telegram:\n  bot_token: test123\n")

        result = config.load_repo_config(config_file)

        assert result["telegram"]["bot_token"] == "test123"

    def test_load_repo_config_invalid_yaml(self, tmp_path):
        """Test loading invalid yaml returns empty dict."""
        config_dir = tmp_path / ".claude_orchestrator"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("invalid: yaml: content:")

        result = config.load_repo_config(config_file)

        assert result == {}


class TestProjectIdentity:
    """Test project identity functions."""

    def test_project_identity_in_git_repo(self, tmp_path):
        """Test project identity in a git repo."""
        (tmp_path / ".git").mkdir()
        subdir = tmp_path / "src"
        subdir.mkdir()

        project_id, project_remote = config.get_project_identity(subdir)

        assert project_id == str(tmp_path)
        # No git origin configured, so remote should be None
        assert project_remote is None

    def test_project_identity_no_git(self, tmp_path):
        """Test project identity when not in git repo."""
        subdir = tmp_path / "some" / "path"
        subdir.mkdir(parents=True)

        project_id, project_remote = config.get_project_identity(subdir)

        # Should use cwd as project_id when no git
        assert project_id == str(subdir.resolve())
        assert project_remote is None


class TestSmartCommitConfig:
    """Test smart commit configuration."""

    def test_default_smart_commit_enabled(self):
        """Test that smart commit is enabled by default."""
        # Without CLI flag, env var, or config, should default to True
        result = config.get_smart_commit_enabled(None)
        assert result is True

    def test_cli_flag_true_overrides(self):
        """Test that CLI flag True takes precedence."""
        result = config.get_smart_commit_enabled(True)
        assert result is True

    def test_cli_flag_false_overrides(self):
        """Test that CLI flag False takes precedence."""
        result = config.get_smart_commit_enabled(False)
        assert result is False

    def test_env_var_true(self, monkeypatch):
        """Test environment variable enables smart commit."""
        monkeypatch.setenv("ORCHESTRATOR_SMART_COMMIT", "true")
        result = config.get_smart_commit_enabled(None)
        assert result is True

    def test_env_var_false(self, monkeypatch):
        """Test environment variable disables smart commit."""
        monkeypatch.setenv("ORCHESTRATOR_SMART_COMMIT", "false")
        result = config.get_smart_commit_enabled(None)
        assert result is False

    def test_env_var_yes(self, monkeypatch):
        """Test environment variable 'yes' enables smart commit."""
        monkeypatch.setenv("ORCHESTRATOR_SMART_COMMIT", "yes")
        result = config.get_smart_commit_enabled(None)
        assert result is True

    def test_env_var_1(self, monkeypatch):
        """Test environment variable '1' enables smart commit."""
        monkeypatch.setenv("ORCHESTRATOR_SMART_COMMIT", "1")
        result = config.get_smart_commit_enabled(None)
        assert result is True

    def test_cli_flag_overrides_env_var(self, monkeypatch):
        """Test that CLI flag takes precedence over env var."""
        monkeypatch.setenv("ORCHESTRATOR_SMART_COMMIT", "true")
        result = config.get_smart_commit_enabled(False)
        assert result is False

    def test_config_file_enabled(self, tmp_path, monkeypatch):
        """Test config file enables smart commit."""
        # Create config file
        config_dir = tmp_path / ".claude_orchestrator"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("auto_commit:\n  smart: true\n")

        # Mock find_repo_config to return our test config
        monkeypatch.setattr(config, "find_repo_config", lambda: config_file)

        result = config.get_smart_commit_enabled(None)
        assert result is True

    def test_config_file_disabled(self, tmp_path, monkeypatch):
        """Test config file disables smart commit."""
        # Create config file
        config_dir = tmp_path / ".claude_orchestrator"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("auto_commit:\n  smart: false\n")

        # Mock find_repo_config to return our test config
        monkeypatch.setattr(config, "find_repo_config", lambda: config_file)

        result = config.get_smart_commit_enabled(None)
        assert result is False


class TestAutoCommitModelConfig:
    """Test auto-commit model configuration."""

    def test_cli_flag_takes_priority(self):
        """Test that CLI flag takes highest priority."""
        result = config.get_auto_commit_model("haiku", "claude-sonnet-4-6")
        assert result == "claude-3-5-haiku-20241022"

    def test_cli_flag_resolves_alias(self):
        """Test that CLI flag aliases are resolved."""
        result = config.get_auto_commit_model("opus", None)
        assert result == "claude-opus-4-6"

    def test_cli_flag_passes_full_model_id(self):
        """Test that full model IDs are passed through."""
        result = config.get_auto_commit_model("claude-custom-model-123", None)
        assert result == "claude-custom-model-123"

    def test_env_var_takes_priority_over_executor(self, monkeypatch):
        """Test that env var takes priority over executor model."""
        monkeypatch.setenv("ORCHESTRATOR_AUTO_COMMIT_MODEL", "haiku")
        result = config.get_auto_commit_model(None, "claude-sonnet-4-6")
        assert result == "claude-3-5-haiku-20241022"

    def test_env_var_resolves_alias(self, monkeypatch):
        """Test that env var aliases are resolved."""
        monkeypatch.setenv("ORCHESTRATOR_AUTO_COMMIT_MODEL", "opus")
        result = config.get_auto_commit_model(None, None)
        assert result == "claude-opus-4-6"

    def test_cli_flag_overrides_env_var(self, monkeypatch):
        """Test that CLI flag overrides env var."""
        monkeypatch.setenv("ORCHESTRATOR_AUTO_COMMIT_MODEL", "opus")
        result = config.get_auto_commit_model("haiku", None)
        assert result == "claude-3-5-haiku-20241022"

    def test_config_file_model(self, tmp_path, monkeypatch):
        """Test config file specifies commit model."""
        config_dir = tmp_path / ".claude_orchestrator"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("auto_commit:\n  model: haiku\n")

        monkeypatch.setattr(config, "find_repo_config", lambda: config_file)

        result = config.get_auto_commit_model(None, None)
        assert result == "claude-3-5-haiku-20241022"

    def test_config_file_overridden_by_cli(self, tmp_path, monkeypatch):
        """Test CLI flag overrides config file."""
        config_dir = tmp_path / ".claude_orchestrator"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("auto_commit:\n  model: haiku\n")

        monkeypatch.setattr(config, "find_repo_config", lambda: config_file)

        result = config.get_auto_commit_model("opus", None)
        assert result == "claude-opus-4-6"

    def test_executor_model_fallback(self):
        """Test fallback to executor model when no CLI/env/config."""
        result = config.get_auto_commit_model(None, "claude-sonnet-4-6")
        assert result == "claude-sonnet-4-6"

    def test_default_executor_model_ultimate_fallback(self):
        """Test ultimate fallback to default executor model."""
        result = config.get_auto_commit_model(None, None)
        assert result == config.DEFAULT_EXECUTOR_MODEL


# ============================================================================
# MCP Configuration Tests
# ============================================================================


class TestExpandEnvVars:
    """Test environment variable expansion in MCP config."""

    def test_expand_env_vars_substitutes_variables(self, monkeypatch):
        """Should expand ${VAR} syntax in config."""
        monkeypatch.setenv("MY_TOKEN", "secret123")

        obj = {"env": {"TOKEN": "${MY_TOKEN}"}}
        expanded = config.expand_env_vars(obj)

        assert expanded["env"]["TOKEN"] == "secret123"

    def test_expand_env_vars_leaves_unset_unchanged(self):
        """Should leave ${VAR} unchanged if not set."""
        obj = {"env": {"TOKEN": "${UNDEFINED_VAR_XYZ}"}}
        expanded = config.expand_env_vars(obj)

        assert expanded["env"]["TOKEN"] == "${UNDEFINED_VAR_XYZ}"

    def test_expand_env_vars_nested_dict(self, monkeypatch):
        """Should expand in nested dicts."""
        monkeypatch.setenv("NESTED_VAL", "deep_value")

        obj = {
            "level1": {
                "level2": {
                    "key": "${NESTED_VAL}"
                }
            }
        }
        expanded = config.expand_env_vars(obj)

        assert expanded["level1"]["level2"]["key"] == "deep_value"

    def test_expand_env_vars_list(self, monkeypatch):
        """Should expand in lists."""
        monkeypatch.setenv("LIST_VAL", "item_value")

        obj = {"items": ["${LIST_VAL}", "static"]}
        expanded = config.expand_env_vars(obj)

        assert expanded["items"][0] == "item_value"
        assert expanded["items"][1] == "static"

    def test_expand_env_vars_passthrough_non_string(self):
        """Should pass through non-string values."""
        obj = {"number": 42, "bool": True, "none": None}
        expanded = config.expand_env_vars(obj)

        assert expanded["number"] == 42
        assert expanded["bool"] is True
        assert expanded["none"] is None


class TestLoadMcpConfigRaw:
    """Test raw MCP config loading (no env expansion)."""

    def test_load_mcp_config_raw_explicit_path(self, tmp_path):
        """Load MCP config from explicit path."""
        import json

        config_file = tmp_path / "test-mcp.json"
        mcp_config = {
            "mcpServers": {
                "playwright": {"command": "npx", "args": ["@playwright/mcp"]}
            }
        }
        config_file.write_text(json.dumps(mcp_config))

        servers, planner_cfg, executor_cfg = config.load_mcp_config_raw(
            mcp_config_path=str(config_file)
        )

        assert servers == {"playwright": {"command": "npx", "args": ["@playwright/mcp"]}}
        assert planner_cfg == {}
        assert executor_cfg == {}

    def test_load_mcp_config_raw_preserves_env_vars(self, tmp_path):
        """Raw config should preserve ${VAR} syntax."""
        import json

        config_file = tmp_path / ".mcp.json"
        mcp_config = {
            "mcpServers": {
                "figma": {
                    "command": "npx",
                    "env": {"FIGMA_TOKEN": "${FIGMA_ACCESS_TOKEN}"}
                }
            }
        }
        config_file.write_text(json.dumps(mcp_config))

        servers, _, _ = config.load_mcp_config_raw(
            mcp_config_path=str(config_file)
        )

        # Should NOT expand env vars
        assert servers["figma"]["env"]["FIGMA_TOKEN"] == "${FIGMA_ACCESS_TOKEN}"

    def test_load_mcp_config_raw_with_orchestrator_section(self, tmp_path):
        """Load MCP config with orchestrator section."""
        import json

        config_file = tmp_path / ".mcp.json"
        mcp_config = {
            "mcpServers": {
                "playwright": {"command": "npx"},
                "figma": {"command": "figma-mcp"}
            },
            "orchestrator": {
                "planner": {"mcpServers": ["figma"]},
                "executor": {"mcpServers": ["playwright"]}
            }
        }
        config_file.write_text(json.dumps(mcp_config))

        servers, planner_cfg, executor_cfg = config.load_mcp_config_raw(
            mcp_config_path=str(config_file)
        )

        assert servers == {
            "playwright": {"command": "npx"},
            "figma": {"command": "figma-mcp"}
        }
        assert planner_cfg == {"mcpServers": ["figma"]}
        assert executor_cfg == {"mcpServers": ["playwright"]}

    def test_load_mcp_config_raw_file_not_found(self):
        """Should raise FileNotFoundError for missing explicit path."""
        with pytest.raises(FileNotFoundError):
            config.load_mcp_config_raw(mcp_config_path="/nonexistent/path.json")

    def test_load_mcp_config_raw_no_config(self, tmp_path, monkeypatch):
        """Should return None when no config found."""
        # Isolate from user's global ~/.mcp.json
        # Use *args to handle classmethod binding robustly
        monkeypatch.setattr(Path, "home", lambda *_: tmp_path / "fake_home")

        # No .mcp.json exists in project or fake home
        servers, planner_cfg, executor_cfg = config.load_mcp_config_raw(
            project_root=tmp_path
        )

        assert servers is None
        assert planner_cfg is None
        assert executor_cfg is None


class TestLoadMcpConfig:
    """Test MCP config loading with env expansion."""

    def test_load_mcp_config_expands_env_vars(self, tmp_path, monkeypatch):
        """Should expand env vars when loading config."""
        import json

        monkeypatch.setenv("FIGMA_TOKEN", "fig_123")

        config_file = tmp_path / ".mcp.json"
        mcp_config = {
            "mcpServers": {
                "figma": {
                    "command": "npx",
                    "env": {"FIGMA_ACCESS_TOKEN": "${FIGMA_TOKEN}"}
                }
            }
        }
        config_file.write_text(json.dumps(mcp_config))

        servers, _, _ = config.load_mcp_config(
            mcp_config_path=str(config_file)
        )

        assert servers["figma"]["env"]["FIGMA_ACCESS_TOKEN"] == "fig_123"


class TestFilterMcpServers:
    """Test MCP server filtering."""

    def test_filter_mcp_servers_all(self):
        """None filter returns all servers."""
        servers = {"a": {}, "b": {}, "c": {}}
        filtered = config.filter_mcp_servers(servers, None)

        assert filtered == servers

    def test_filter_mcp_servers_subset(self):
        """Filter to subset of servers."""
        servers = {"playwright": {}, "figma": {}, "github": {}}
        filtered = config.filter_mcp_servers(servers, ["playwright", "figma"])

        assert filtered == {"playwright": {}, "figma": {}}
        assert "github" not in filtered

    def test_filter_mcp_servers_missing(self):
        """Missing servers are silently skipped."""
        servers = {"playwright": {}}
        filtered = config.filter_mcp_servers(servers, ["playwright", "nonexistent"])

        assert filtered == {"playwright": {}}


class TestGetAgentMcpConfig:
    """Test agent-specific MCP config extraction."""

    def test_get_agent_mcp_config_filters_servers(self):
        """Should filter servers based on agent config."""
        mcp_servers = {
            "playwright": {"command": "npx"},
            "figma": {"command": "figma-mcp"},
            "github": {"command": "gh-mcp"}
        }
        agent_config = {"mcpServers": ["playwright"]}

        filtered_servers, tools = config.get_agent_mcp_config(
            mcp_servers, agent_config
        )

        assert filtered_servers == {"playwright": {"command": "npx"}}
        assert "mcp__playwright__*" in tools

    def test_get_agent_mcp_config_explicit_tools(self):
        """Should use explicit tools if specified."""
        mcp_servers = {"playwright": {"command": "npx"}}
        agent_config = {
            "mcpServers": ["playwright"],
            "tools": ["mcp__playwright__browser_navigate", "mcp__playwright__browser_click"]
        }

        filtered_servers, tools = config.get_agent_mcp_config(
            mcp_servers, agent_config
        )

        assert tools == [
            "mcp__playwright__browser_navigate",
            "mcp__playwright__browser_click"
        ]

    def test_get_agent_mcp_config_all_servers(self):
        """No filter means all servers."""
        mcp_servers = {"a": {}, "b": {}}
        agent_config = {}  # No mcpServers filter

        filtered_servers, tools = config.get_agent_mcp_config(
            mcp_servers, agent_config
        )

        assert filtered_servers == {"a": {}, "b": {}}
        assert "mcp__a__*" in tools
        assert "mcp__b__*" in tools
