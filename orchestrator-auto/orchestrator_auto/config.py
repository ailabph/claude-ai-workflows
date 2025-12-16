"""
Configuration management for orchestrator-auto.

Handles model aliases, config file loading, and model resolution.
"""

from pathlib import Path
from typing import Optional, Dict, Any


# Model aliases mapping to full model IDs (latest versions)
MODEL_ALIASES = {
    "opus": "claude-opus-4-5-20251101",
    "sonnet": "claude-sonnet-4-5-20250929",
    "haiku": "claude-haiku-3-5-20241022",
}

# Default models
DEFAULT_PLANNER_MODEL = "claude-opus-4-5-20251101"
DEFAULT_EXECUTOR_MODEL = "claude-sonnet-4-5-20250929"

# Config file location
CONFIG_DIR = Path.home() / ".claude_orchestrator"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


def get_config_path() -> Path:
    """Get path to config file."""
    return CONFIG_FILE


def load_config() -> Dict[str, Any]:
    """
    Load config from ~/.claude_orchestrator/config.yaml.

    Returns:
        Config dictionary, empty if file doesn't exist
    """
    config_path = get_config_path()
    if config_path.exists():
        try:
            import yaml
            content = config_path.read_text()
            return yaml.safe_load(content) or {}
        except Exception:
            # If config file is invalid, return empty config
            return {}
    return {}


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

import os


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
