"""
Configuration management for orchestrator-auto.

Handles model aliases, config file loading, and model resolution.
Supports repo-local config with merge semantics.
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List


# Model aliases mapping to full model IDs (latest versions)
MODEL_ALIASES = {
    "opus": "claude-opus-4-5-20251101",
    "sonnet": "claude-sonnet-4-5-20250929",
    "haiku": "claude-3-5-haiku-20241022",
}

# Default models
DEFAULT_PLANNER_MODEL = "claude-opus-4-5-20251101"
DEFAULT_EXECUTOR_MODEL = "claude-sonnet-4-5-20250929"

# Config file locations
GLOBAL_CONFIG_DIR = Path.home() / ".claude_orchestrator"
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.yaml"
REPO_CONFIG_DIR_NAME = ".claude_orchestrator"
REPO_CONFIG_FILE_NAME = "config.yaml"


# ============================================================================
# Repo-Local Config Discovery
# ============================================================================

def find_repo_root(start_path: Optional[Path] = None) -> Optional[Path]:
    """
    Find the git repository root by walking up from start_path.

    Args:
        start_path: Starting directory (defaults to cwd)

    Returns:
        Path to repo root if found, None otherwise
    """
    current = Path(start_path) if start_path else Path.cwd()
    current = current.resolve()

    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent

    # Check root directory
    if (current / ".git").exists():
        return current

    return None


def find_repo_config(start_path: Optional[Path] = None) -> Optional[Path]:
    """
    Find repo-local config file by walking up from start_path.

    Discovery rules:
    1. Walk upward from start_path to filesystem root
    2. At each directory, check for .claude_orchestrator/config.yaml
    3. Stop walking after reaching a .git directory (git root boundary)
    4. Return the nearest config found (closest to start_path)

    Args:
        start_path: Starting directory (defaults to cwd)

    Returns:
        Path to repo config file if found, None otherwise
    """
    current = Path(start_path) if start_path else Path.cwd()
    current = current.resolve()
    candidates = []

    while current != current.parent:
        config_path = current / REPO_CONFIG_DIR_NAME / REPO_CONFIG_FILE_NAME
        if config_path.exists():
            candidates.append(config_path)

        # Stop at git root boundary (but include this directory's check)
        if (current / ".git").exists():
            break

        current = current.parent

    # Return nearest (first found, closest to cwd)
    return candidates[0] if candidates else None


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dictionaries. Override values take precedence.

    Args:
        base: Base dictionary
        override: Dictionary with override values

    Returns:
        Merged dictionary
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_global_config() -> Dict[str, Any]:
    """
    Load global config from ~/.claude_orchestrator/config.yaml.

    Returns:
        Config dictionary, empty if file doesn't exist or is invalid
    """
    if GLOBAL_CONFIG_FILE.exists():
        try:
            import yaml
            content = GLOBAL_CONFIG_FILE.read_text()
            return yaml.safe_load(content) or {}
        except Exception:
            return {}
    return {}


def load_repo_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load repo-local config file.

    Args:
        config_path: Path to config file (or None to auto-discover)

    Returns:
        Config dictionary, empty if not found or invalid
    """
    if config_path is None:
        config_path = find_repo_config()

    if config_path and config_path.exists():
        try:
            import yaml
            content = config_path.read_text()
            return yaml.safe_load(content) or {}
        except Exception:
            return {}
    return {}


def load_config() -> Dict[str, Any]:
    """
    Load merged config (global + repo-local).

    Merge semantics:
    - Load global config first as base
    - Load repo-local config and deep-merge over global
    - Nested dicts (like telegram) are merged recursively

    Priority: repo config > global config

    Returns:
        Merged config dictionary
    """
    global_config = load_global_config()
    repo_config = load_repo_config()

    if repo_config:
        return _deep_merge(global_config, repo_config)
    return global_config


# ============================================================================
# Project Identity
# ============================================================================

def get_project_identity(cwd: Optional[Path] = None) -> Tuple[str, Optional[str]]:
    """
    Get project identity for session scoping.

    Args:
        cwd: Working directory (defaults to cwd)

    Returns:
        Tuple of (project_id, project_remote):
        - project_id: Absolute path to repo root (or cwd if no git repo)
        - project_remote: Git origin URL if available, None otherwise
    """
    start_path = Path(cwd) if cwd else Path.cwd()
    start_path = start_path.resolve()

    # Find repo root
    repo_root = find_repo_root(start_path)
    if repo_root:
        project_id = str(repo_root)
    else:
        # No git repo, use cwd as project root
        project_id = str(start_path)

    # Try to get git remote URL
    project_remote = None
    if repo_root:
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                project_remote = result.stdout.strip()
        except Exception:
            pass

    return project_id, project_remote


# ============================================================================
# Legacy Compatibility
# ============================================================================

# Keep these for backward compatibility
CONFIG_DIR = GLOBAL_CONFIG_DIR
CONFIG_FILE = GLOBAL_CONFIG_FILE


def get_config_path() -> Path:
    """Get path to global config file."""
    return GLOBAL_CONFIG_FILE


def resolve_model(model: Optional[str]) -> Optional[str]:
    """
    Resolve model alias to full model ID.

    Args:
        model: Model alias (opus, sonnet, haiku) or full model ID

    Returns:
        Full model ID, or None if input was None
    """
    if model is None:
        return None
    return MODEL_ALIASES.get(model.lower(), model)


def get_model_display_name(model: str) -> str:
    """
    Get a short display name for a model.

    Args:
        model: Full model ID

    Returns:
        Short display name (e.g., "opus-4.5")
    """
    # Reverse lookup in aliases
    for alias, full_id in MODEL_ALIASES.items():
        if model == full_id:
            # Extract version from model ID
            if "opus-4-5" in model:
                return "opus-4.5"
            elif "sonnet-4-5" in model:
                return "sonnet-4.5"
            elif "haiku-3-5" in model:
                return "haiku-3.5"
            return alias

    # If not in aliases, return shortened version
    if "claude-" in model:
        return model.replace("claude-", "").split("-202")[0]
    return model


def get_planner_model(cli_model: Optional[str] = None) -> str:
    """
    Get planner model with priority: CLI > config > default.

    Args:
        cli_model: Model specified via CLI flag (optional)

    Returns:
        Full model ID for planner
    """
    if cli_model:
        return resolve_model(cli_model)

    config = load_config()
    config_model = config.get("models", {}).get("planner")
    if config_model:
        return resolve_model(config_model)

    return DEFAULT_PLANNER_MODEL


def get_executor_model(cli_model: Optional[str] = None) -> str:
    """
    Get executor model with priority: CLI > config > default.

    Args:
        cli_model: Model specified via CLI flag (optional)

    Returns:
        Full model ID for executor
    """
    if cli_model:
        return resolve_model(cli_model)

    config = load_config()
    config_model = config.get("models", {}).get("executor")
    if config_model:
        return resolve_model(config_model)

    return DEFAULT_EXECUTOR_MODEL


def get_planner_effort(cli_effort: Optional[str] = None) -> Optional[str]:
    """
    Get planner effort with priority: CLI > config > default (None).

    Args:
        cli_effort: Effort specified via CLI flag (optional)

    Returns:
        Effort level string or None
    """
    if cli_effort:
        return cli_effort

    config = load_config()
    return config.get("effort", {}).get("planner")


def get_executor_effort(cli_effort: Optional[str] = None) -> Optional[str]:
    """
    Get executor effort with priority: CLI > config > default (None).

    Args:
        cli_effort: Effort specified via CLI flag (optional)

    Returns:
        Effort level string or None
    """
    if cli_effort:
        return cli_effort

    config = load_config()
    return config.get("effort", {}).get("executor")


def get_thinking(cli_thinking: Optional[str] = None) -> Optional[str]:
    """
    Get thinking config with priority: CLI > config > default (None).

    Args:
        cli_thinking: Thinking specified via CLI flag (optional)

    Returns:
        Thinking config string or None
    """
    if cli_thinking:
        return cli_thinking

    config = load_config()
    return config.get("thinking")


def list_available_models() -> Dict[str, str]:
    """
    Get list of available model aliases.

    Returns:
        Dictionary of alias -> full model ID
    """
    return MODEL_ALIASES.copy()


# ============================================================================
# Telegram Configuration
# ============================================================================


def get_telegram_config() -> Dict[str, Any]:
    """
    Get Telegram configuration with priority: env vars > config file.

    Environment variables:
        ORCHESTRATOR_TELEGRAM_BOT_TOKEN
        ORCHESTRATOR_TELEGRAM_CHAT_ID
        ORCHESTRATOR_TELEGRAM_ENABLED (true/false)

    Returns:
        Telegram config dict with bot_token, chat_id, enabled, etc.
    """
    config = load_config()
    telegram_config = config.get("telegram", {})

    # Override with environment variables
    env_token = os.environ.get("ORCHESTRATOR_TELEGRAM_BOT_TOKEN")
    env_chat_id = os.environ.get("ORCHESTRATOR_TELEGRAM_CHAT_ID")
    env_enabled = os.environ.get("ORCHESTRATOR_TELEGRAM_ENABLED")

    if env_token:
        telegram_config["bot_token"] = env_token
    if env_chat_id:
        telegram_config["chat_id"] = env_chat_id
    if env_enabled is not None:
        telegram_config["enabled"] = env_enabled.lower() in ("true", "1", "yes")

    return telegram_config


def is_telegram_configured() -> bool:
    """
    Check if Telegram is configured (has bot_token and chat_id).

    Returns:
        True if Telegram can be used
    """
    config = get_telegram_config()
    return bool(config.get("bot_token") and config.get("chat_id"))


# ============================================================================
# Stuck Sessions Configuration
# ============================================================================

DEFAULT_STUCK_INACTIVE_MINUTES = 20

# Smart commit defaults
DEFAULT_SMART_COMMIT_ENABLED = True


# ============================================================================
# Smart Commit Configuration
# ============================================================================


def get_smart_commit_enabled(cli_flag: Optional[bool] = None) -> bool:
    """
    Get smart commit enabled setting with priority: CLI > env var > config > default.

    Smart commit uses AI to analyze diffs and generate meaningful commit messages
    following Conventional Commits format.

    Config file shape:
        auto_commit:
          smart: true

    Environment variable:
        ORCHESTRATOR_SMART_COMMIT (true/false)

    Args:
        cli_flag: CLI flag value (--smart-commit/--no-smart-commit)

    Returns:
        True if smart commit should be used
    """
    # CLI flag has highest priority
    if cli_flag is not None:
        return cli_flag

    # Check environment variable
    env_value = os.environ.get("ORCHESTRATOR_SMART_COMMIT")
    if env_value is not None:
        return env_value.lower() in ("true", "1", "yes")

    # Check config file
    config = load_config()
    auto_commit_config = config.get("auto_commit", {})
    if "smart" in auto_commit_config:
        return bool(auto_commit_config["smart"])

    # Default
    return DEFAULT_SMART_COMMIT_ENABLED


def get_auto_commit_model(
    cli_model: Optional[str] = None,
    executor_model: Optional[str] = None,
) -> str:
    """
    Get model for smart auto-commit with priority: CLI > env var > config > executor model.

    Config file shape:
        auto_commit:
          smart: true
          model: sonnet  # or full model ID

    Environment variable:
        ORCHESTRATOR_AUTO_COMMIT_MODEL (alias or full model ID)

    Args:
        cli_model: CLI flag value (--auto-commit-model)
        executor_model: Resolved executor model for the session (fallback)

    Returns:
        Full model ID for smart commit generation
    """
    # CLI flag has highest priority
    if cli_model:
        return resolve_model(cli_model)

    # Check environment variable
    env_value = os.environ.get("ORCHESTRATOR_AUTO_COMMIT_MODEL")
    if env_value:
        return resolve_model(env_value)

    # Check config file
    config = load_config()
    auto_commit_config = config.get("auto_commit", {})
    config_model = auto_commit_config.get("model")
    if config_model:
        return resolve_model(config_model)

    # Fall back to executor model
    if executor_model:
        return executor_model

    # Ultimate fallback: use default executor model
    return get_executor_model(None)


def get_stuck_sessions_config() -> Dict[str, Any]:
    """
    Get stuck session detection configuration.

    Config file shape:
        telegram:
          stuck_sessions:
            enabled: true
            inactive_minutes: 20

    Environment variables:
        ORCHESTRATOR_TELEGRAM_STUCK_ENABLED (true/false)
        ORCHESTRATOR_TELEGRAM_STUCK_MINUTES (integer)

    Returns:
        Dict with 'enabled' (bool) and 'inactive_minutes' (int)
    """
    config = load_config()
    telegram_config = config.get("telegram", {})
    stuck_config = telegram_config.get("stuck_sessions", {})

    # Defaults
    result = {
        "enabled": True,  # Enabled by default if telegram is configured
        "inactive_minutes": DEFAULT_STUCK_INACTIVE_MINUTES,
    }

    # Override from config file
    if "enabled" in stuck_config:
        result["enabled"] = bool(stuck_config["enabled"])
    if "inactive_minutes" in stuck_config:
        try:
            result["inactive_minutes"] = int(stuck_config["inactive_minutes"])
        except (ValueError, TypeError):
            pass

    # Override from environment variables
    env_enabled = os.environ.get("ORCHESTRATOR_TELEGRAM_STUCK_ENABLED")
    env_minutes = os.environ.get("ORCHESTRATOR_TELEGRAM_STUCK_MINUTES")

    if env_enabled is not None:
        result["enabled"] = env_enabled.lower() in ("true", "1", "yes")
    if env_minutes:
        try:
            result["inactive_minutes"] = int(env_minutes)
        except ValueError:
            pass

    return result


# ============================================================================
# Exploration Configuration (Phase 1A)
# ============================================================================

# Exploration defaults
DEFAULT_EXPLORE_ENABLED = False  # Initial default: off
DEFAULT_EXPLORE_MAX_TURNS = 5
DEFAULT_EXPLORE_MAX_TOKENS = 25_000
DEFAULT_EXPLORE_TIMEOUT = 30  # seconds


def get_exploration_config() -> Dict[str, Any]:
    """
    Get exploration configuration with priority: env vars > config file > defaults.

    Config file shape:
        executor:
          auto_explore: false
          explore_max_turns: 5
          explore_max_tokens: 25000
          explore_timeout: 30

    Environment variables:
        ORCHESTRATOR_EXPLORE_ENABLED (true/false)
        ORCHESTRATOR_EXPLORE_MAX_TURNS (integer)
        ORCHESTRATOR_EXPLORE_MAX_TOKENS (integer)
        ORCHESTRATOR_EXPLORE_TIMEOUT (integer, seconds)

    Returns:
        Dict with exploration settings
    """
    config = load_config()
    executor_config = config.get("executor", {})

    # Defaults
    result = {
        "enabled": DEFAULT_EXPLORE_ENABLED,
        "max_turns": DEFAULT_EXPLORE_MAX_TURNS,
        "max_tokens": DEFAULT_EXPLORE_MAX_TOKENS,
        "timeout": DEFAULT_EXPLORE_TIMEOUT,
    }

    # Override from config file
    if "auto_explore" in executor_config:
        result["enabled"] = bool(executor_config["auto_explore"])
    if "explore_max_turns" in executor_config:
        try:
            result["max_turns"] = int(executor_config["explore_max_turns"])
        except (ValueError, TypeError):
            pass
    if "explore_max_tokens" in executor_config:
        try:
            result["max_tokens"] = int(executor_config["explore_max_tokens"])
        except (ValueError, TypeError):
            pass
    if "explore_timeout" in executor_config:
        try:
            result["timeout"] = int(executor_config["explore_timeout"])
        except (ValueError, TypeError):
            pass

    # Override from environment variables
    env_enabled = os.environ.get("ORCHESTRATOR_EXPLORE_ENABLED")
    env_max_turns = os.environ.get("ORCHESTRATOR_EXPLORE_MAX_TURNS")
    env_max_tokens = os.environ.get("ORCHESTRATOR_EXPLORE_MAX_TOKENS")
    env_timeout = os.environ.get("ORCHESTRATOR_EXPLORE_TIMEOUT")

    if env_enabled is not None:
        result["enabled"] = env_enabled.lower() in ("true", "1", "yes")
    if env_max_turns:
        try:
            result["max_turns"] = int(env_max_turns)
        except ValueError:
            pass
    if env_max_tokens:
        try:
            result["max_tokens"] = int(env_max_tokens)
        except ValueError:
            pass
    if env_timeout:
        try:
            result["timeout"] = int(env_timeout)
        except ValueError:
            pass

    return result


def get_explore_enabled(cli_flag: Optional[bool] = None) -> bool:
    """
    Get exploration enabled setting with priority: CLI > env > config > default.

    Args:
        cli_flag: CLI flag value (--explore/--no-explore)

    Returns:
        True if exploration should be performed
    """
    if cli_flag is not None:
        return cli_flag
    return get_exploration_config()["enabled"]


# ============================================================================
# Validation Configuration (Phase 1B)
# ============================================================================

# Validation defaults
DEFAULT_VALIDATION_ENABLED = False  # Initial default: off
DEFAULT_VALIDATION_MAX_PARALLEL = 3
DEFAULT_VALIDATION_TOTAL_TIMEOUT = 45  # seconds
DEFAULT_VALIDATION_AUTO_REJECT_HIGH = True


def get_validation_config() -> Dict[str, Any]:
    """
    Get validation configuration with priority: env vars > config file > defaults.

    Config file shape:
        validation:
          enabled: false
          auto_reject_on_high: true
          max_parallel: 3
          total_timeout: 45
          validators:
            security:
              enabled: true
              severity_threshold: medium
            performance:
              enabled: true
              severity_threshold: high
            api:
              enabled: true
              severity_threshold: medium

    Environment variables:
        ORCHESTRATOR_VALIDATE_ENABLED (true/false)
        ORCHESTRATOR_VALIDATE_AUTO_REJECT (true/false)
        ORCHESTRATOR_VALIDATE_MAX_PARALLEL (integer)
        ORCHESTRATOR_VALIDATE_TIMEOUT (integer, seconds)

    Returns:
        Dict with validation settings
    """
    config = load_config()
    validation_config = config.get("validation", {})

    # Defaults
    result = {
        "enabled": DEFAULT_VALIDATION_ENABLED,
        "auto_reject_on_high": DEFAULT_VALIDATION_AUTO_REJECT_HIGH,
        "max_parallel": DEFAULT_VALIDATION_MAX_PARALLEL,
        "total_timeout": DEFAULT_VALIDATION_TOTAL_TIMEOUT,
        "validators": {
            "security": {"enabled": True, "severity_threshold": "medium"},
            "performance": {"enabled": True, "severity_threshold": "high"},
            "api": {"enabled": True, "severity_threshold": "medium"},
        },
    }

    # Override from config file
    if "enabled" in validation_config:
        result["enabled"] = bool(validation_config["enabled"])
    if "auto_reject_on_high" in validation_config:
        result["auto_reject_on_high"] = bool(validation_config["auto_reject_on_high"])
    if "max_parallel" in validation_config:
        try:
            result["max_parallel"] = int(validation_config["max_parallel"])
        except (ValueError, TypeError):
            pass
    if "total_timeout" in validation_config:
        try:
            result["total_timeout"] = int(validation_config["total_timeout"])
        except (ValueError, TypeError):
            pass
    if "validators" in validation_config:
        # Deep merge validators config
        for name, validator_cfg in validation_config["validators"].items():
            if name not in result["validators"]:
                result["validators"][name] = {}
            result["validators"][name].update(validator_cfg)

    # Override from environment variables
    env_enabled = os.environ.get("ORCHESTRATOR_VALIDATE_ENABLED")
    env_auto_reject = os.environ.get("ORCHESTRATOR_VALIDATE_AUTO_REJECT")
    env_max_parallel = os.environ.get("ORCHESTRATOR_VALIDATE_MAX_PARALLEL")
    env_timeout = os.environ.get("ORCHESTRATOR_VALIDATE_TIMEOUT")

    if env_enabled is not None:
        result["enabled"] = env_enabled.lower() in ("true", "1", "yes")
    if env_auto_reject is not None:
        result["auto_reject_on_high"] = env_auto_reject.lower() in ("true", "1", "yes")
    if env_max_parallel:
        try:
            result["max_parallel"] = int(env_max_parallel)
        except ValueError:
            pass
    if env_timeout:
        try:
            result["total_timeout"] = int(env_timeout)
        except ValueError:
            pass

    return result


def get_validation_enabled(cli_flag: Optional[bool] = None) -> bool:
    """
    Get validation enabled setting with priority: CLI > env > config > default.

    Args:
        cli_flag: CLI flag value (--validate/--no-validate)

    Returns:
        True if validation should be performed
    """
    if cli_flag is not None:
        return cli_flag
    return get_validation_config()["enabled"]


# ============================================================================
# MCP Configuration
# ============================================================================


def expand_env_vars(obj: Any) -> Any:
    """
    Recursively expand environment variables in a config object.

    Supports ${VAR} and $VAR syntax in string values.

    Args:
        obj: Config object (dict, list, or scalar)

    Returns:
        Object with environment variables expanded
    """
    if isinstance(obj, dict):
        return {k: expand_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [expand_env_vars(item) for item in obj]
    elif isinstance(obj, str):
        # Expand ${VAR} syntax
        pattern = r'\$\{([^}]+)\}'

        def replace(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))

        expanded = re.sub(pattern, replace, obj)
        # Also expand $VAR syntax (but not $$)
        expanded = os.path.expandvars(expanded)
        return expanded
    else:
        return obj


def load_mcp_config_raw(
    mcp_config_path: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Load MCP configuration from file WITHOUT environment variable expansion.

    Use this when you need to store config in DB (preserves ${VAR} for security).
    Call expand_env_vars() separately for runtime use.

    Priority:
    1. Explicit path (--mcp-config flag)
    2. Project .mcp.json
    3. Global ~/.mcp.json

    Returns:
        Tuple of (mcp_servers, planner_config, executor_config)
        - mcp_servers: Full MCP server definitions (${VAR} preserved)
        - planner_config: Planner-specific MCP settings
        - executor_config: Executor-specific MCP settings
    """
    config_path = None

    # Priority 1: Explicit path
    if mcp_config_path:
        config_path = Path(mcp_config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"MCP config not found: {mcp_config_path}")

    # Priority 2: Project .mcp.json
    if not config_path and project_root:
        project_mcp = project_root / ".mcp.json"
        if project_mcp.exists():
            config_path = project_mcp

    # Priority 3: Global ~/.mcp.json
    if not config_path:
        global_mcp = Path.home() / ".mcp.json"
        if global_mcp.exists():
            config_path = global_mcp

    if not config_path:
        return None, None, None

    # Load and parse (NO env var expansion - preserves ${VAR})
    with open(config_path) as f:
        config = json.load(f)

    mcp_servers = config.get("mcpServers", {})
    orchestrator_config = config.get("orchestrator", {})
    planner_config = orchestrator_config.get("planner", {})
    executor_config = orchestrator_config.get("executor", {})

    return mcp_servers, planner_config, executor_config


def load_mcp_config(
    mcp_config_path: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Load MCP configuration from file WITH environment variable expansion.

    Convenience wrapper that loads raw config and expands env vars.
    For DB storage, use load_mcp_config_raw() instead.

    Returns:
        Tuple of (mcp_servers, planner_config, executor_config) with ${VAR} expanded
    """
    raw_servers, planner_cfg, executor_cfg = load_mcp_config_raw(
        mcp_config_path, project_root
    )

    if raw_servers:
        # Expand env vars for runtime use
        expanded = expand_env_vars({
            "servers": raw_servers,
            "planner": planner_cfg,
            "executor": executor_cfg,
        })
        return expanded["servers"], expanded["planner"], expanded["executor"]

    return None, None, None


def filter_mcp_servers(
    mcp_servers: Dict[str, Any],
    server_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Filter MCP servers to only include specified names.

    Args:
        mcp_servers: Full MCP server configuration
        server_names: List of server names to include (None = all)

    Returns:
        Filtered MCP server configuration
    """
    if server_names is None:
        return mcp_servers

    return {
        name: config
        for name, config in mcp_servers.items()
        if name in server_names
    }


def get_agent_mcp_config(
    mcp_servers: Dict[str, Any],
    agent_config: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Get MCP configuration for a specific agent.

    Args:
        mcp_servers: Full MCP server configuration
        agent_config: Agent-specific configuration (planner or executor)

    Returns:
        Tuple of (filtered_mcp_servers, tool_list)
    """
    # Filter to agent's allowed servers
    server_names = agent_config.get("mcpServers")  # List of server names
    filtered_servers = filter_mcp_servers(mcp_servers, server_names)

    # Get tool list (or generate from servers)
    tools = agent_config.get("tools", [])
    if not tools and filtered_servers:
        # Auto-generate wildcard tools for each server
        tools = [f"mcp__{name}__*" for name in filtered_servers.keys()]

    return filtered_servers, tools


def inject_headless_mode(mcp_servers: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Inject --headless flag into Playwright MCP server args.

    Modifies any MCP server that appears to be Playwright-based by
    adding --headless to its args if not already present.

    Args:
        mcp_servers: MCP server configuration dict

    Returns:
        Modified MCP server configuration with headless injected
    """
    if not mcp_servers:
        return mcp_servers

    import copy
    modified = copy.deepcopy(mcp_servers)

    for name, config in modified.items():
        # Detect Playwright MCP servers by name or package
        args = config.get("args", [])
        is_playwright = (
            "playwright" in name.lower() or
            any("playwright" in str(arg).lower() for arg in args)
        )

        if is_playwright and "--headless" not in args:
            # Inject --headless after the package name
            config["args"] = args + ["--headless"]

    return modified
