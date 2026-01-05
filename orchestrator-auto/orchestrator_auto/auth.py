"""Authentication source detection for orchestrator-auto."""
import os
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List


class AuthSource(Enum):
    """Authentication sources supported by Claude SDK."""
    API_KEY = "api_key"           # ANTHROPIC_API_KEY env var
    OAUTH_TOKEN = "oauth_token"   # CLAUDE_CODE_OAUTH_TOKEN env var
    CREDENTIALS_FILE = "credentials_file"  # ~/.claude/.credentials.json
    BEDROCK = "bedrock"           # AWS Bedrock
    VERTEX = "vertex"             # Google Vertex AI
    FOUNDRY = "foundry"           # Azure Foundry
    MULTIPLE = "multiple"         # Multiple sources detected (sentinel)
    UNKNOWN = "unknown"           # No detection possible


@dataclass
class AuthSignal:
    """A single detected authentication signal."""
    source: AuthSource
    env_var: Optional[str] = None
    file_path: Optional[str] = None
    key_hint: Optional[str] = None  # Masked first chars (for display only)


@dataclass
class AuthInfo:
    """Authentication detection result."""
    signals: List[AuthSignal] = field(default_factory=list)
    detected_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def auth_source_for_db(self) -> str:
        """
        Return auth source value for database storage.

        - If exactly one signal: return that source's value
        - If multiple signals: return "multiple" (we don't pick a winner)
        - If no signals: return "unknown"
        """
        if len(self.signals) == 0:
            return AuthSource.UNKNOWN.value
        if len(self.signals) == 1:
            return self.signals[0].source.value
        return AuthSource.MULTIPLE.value

    @property
    def is_configured(self) -> bool:
        """True if any auth signal detected."""
        return len(self.signals) > 0

    @property
    def has_multiple(self) -> bool:
        """True if multiple auth sources detected."""
        return len(self.signals) > 1

    def to_db_dict(self) -> dict:
        """Return dict for database storage. Does NOT store sensitive key hints."""
        return {
            "auth_source": self.auth_source_for_db,
            "auth_signals": json.dumps([s.source.value for s in self.signals]),
            "auth_detected_at": self.detected_at.isoformat(),
        }


def detect_auth(check_credentials_file: bool = True) -> AuthInfo:
    """
    Detect authentication sources from environment and filesystem.

    Args:
        check_credentials_file: Check ~/.claude/.credentials.json (Linux only)

    Returns:
        AuthInfo with all detected signals (may be empty)

    Note:
        Detection order is deterministic but does NOT imply priority.
        Claude Code's actual runtime selection may differ.
    """
    signals = []

    # 1. Check cloud provider env vars
    if os.environ.get("CLAUDE_CODE_USE_BEDROCK") == "1":
        signals.append(AuthSignal(AuthSource.BEDROCK, env_var="CLAUDE_CODE_USE_BEDROCK"))

    if os.environ.get("CLAUDE_CODE_USE_VERTEX") == "1":
        signals.append(AuthSignal(AuthSource.VERTEX, env_var="CLAUDE_CODE_USE_VERTEX"))

    if os.environ.get("CLAUDE_CODE_USE_FOUNDRY") == "1":
        signals.append(AuthSignal(AuthSource.FOUNDRY, env_var="CLAUDE_CODE_USE_FOUNDRY"))

    # 2. Check API key env var
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        signals.append(AuthSignal(
            AuthSource.API_KEY,
            env_var="ANTHROPIC_API_KEY",
            key_hint=mask_key(api_key),
        ))

    # 3. Check OAuth token env var
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if oauth_token:
        signals.append(AuthSignal(
            AuthSource.OAUTH_TOKEN,
            env_var="CLAUDE_CODE_OAUTH_TOKEN",
            key_hint=mask_key(oauth_token),
        ))

    # 4. Check credentials file (Linux/Ubuntu - macOS uses Keychain)
    if check_credentials_file:
        creds_signal = _check_credentials_file()
        if creds_signal:
            signals.append(creds_signal)

    return AuthInfo(signals=signals)


def _check_credentials_file() -> Optional[AuthSignal]:
    """
    Check for ~/.claude/.credentials.json with OAuth tokens.

    Best-effort detection - file format is not guaranteed stable.
    All errors are silently ignored.
    """
    creds_path = Path.home() / ".claude" / ".credentials.json"

    if not creds_path.exists():
        return None

    try:
        with open(creds_path, "r") as f:
            data = json.load(f)

        if "claudeAiOauth" in data:
            return AuthSignal(
                AuthSource.CREDENTIALS_FILE,
                file_path=str(creds_path),
            )
    except (json.JSONDecodeError, IOError, PermissionError, OSError):
        # Silent failure - this is best-effort detection
        pass

    return None


def mask_key(key: str, visible_chars: int = 12) -> str:
    """Mask API key/token for safe display."""
    if not key or len(key) <= visible_chars:
        return "***"
    return key[:visible_chars] + "..."


def format_auth_display(auth_info: AuthInfo) -> str:
    """Format auth info for CLI display. Shows env var name + masked key hint."""
    if not auth_info.is_configured:
        return (
            "Auth: Unknown (no env vars detected)\n"
            "  Note: Claude Code may still authenticate via keychain or other methods.\n"
            "  If this fails, set ANTHROPIC_API_KEY or run 'claude setup-token'."
        )

    if auth_info.has_multiple:
        lines = ["⚠ Multiple auth sources detected:"]
        for signal in auth_info.signals:
            if signal.env_var and signal.key_hint:
                lines.append(f"  - {signal.env_var} ({signal.key_hint})")
            elif signal.env_var:
                lines.append(f"  - {signal.env_var}")
            elif signal.file_path:
                lines.append(f"  - {signal.file_path}")
        lines.append("  Claude Code will choose one. Consider unsetting one to avoid ambiguity.")
        return "\n".join(lines)

    # Single source - format: "Auth: ENV_VAR_NAME (masked_hint)"
    signal = auth_info.signals[0]

    if signal.source == AuthSource.API_KEY:
        hint = f" ({signal.key_hint})" if signal.key_hint else ""
        return f"Auth: {signal.env_var}{hint}"

    if signal.source == AuthSource.OAUTH_TOKEN:
        hint = f" ({signal.key_hint})" if signal.key_hint else ""
        return f"Auth: {signal.env_var}{hint}"

    if signal.source == AuthSource.CREDENTIALS_FILE:
        return f"Auth: Credentials file ({signal.file_path})"

    if signal.source == AuthSource.BEDROCK:
        return f"Auth: AWS Bedrock ({signal.env_var})"

    if signal.source == AuthSource.VERTEX:
        return f"Auth: Google Vertex AI ({signal.env_var})"

    if signal.source == AuthSource.FOUNDRY:
        return f"Auth: Azure Foundry ({signal.env_var})"

    return f"Auth: {signal.source.value}"
