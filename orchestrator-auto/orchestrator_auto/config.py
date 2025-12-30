"""
Configuration management for orchestrator-auto.

Handles model aliases, config file loading, and model resolution.
Supports repo-local config with merge semantics.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple


# Model aliases mapping to full model IDs (latest versions)
MODEL_ALIASES = {
    "opus": "claude-opus-4-5-20251101",
    "sonnet": "claude-sonnet-4-5-20250929",
    "haiku": "claude-haiku-3-5-20241022",
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
