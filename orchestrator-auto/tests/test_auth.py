"""
Unit tests for authentication source detection.
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto.auth import (
    AuthSource,
    AuthSignal,
    AuthInfo,
    detect_auth,
    _check_credentials_file,
    mask_key,
    format_auth_display,
)


# ============================================================================
# AuthSource Enum Tests
# ============================================================================


class TestAuthSourceEnum:
    """Test AuthSource enum values."""

    def test_enum_values(self):
        """Test all expected enum values exist."""
        assert AuthSource.API_KEY.value == "api_key"
        assert AuthSource.OAUTH_TOKEN.value == "oauth_token"
        assert AuthSource.CREDENTIALS_FILE.value == "credentials_file"
        assert AuthSource.BEDROCK.value == "bedrock"
        assert AuthSource.VERTEX.value == "vertex"
        assert AuthSource.FOUNDRY.value == "foundry"
        assert AuthSource.MULTIPLE.value == "multiple"
        assert AuthSource.UNKNOWN.value == "unknown"

    def test_enum_count(self):
        """Test that we have exactly 8 auth sources."""
        assert len(AuthSource) == 8


# ============================================================================
# AuthSignal Dataclass Tests
# ============================================================================


class TestAuthSignal:
    """Test AuthSignal dataclass."""

    def test_create_with_env_var(self):
        """Test creating signal with env var."""
        signal = AuthSignal(
            source=AuthSource.API_KEY,
            env_var="ANTHROPIC_API_KEY",
            key_hint="sk-ant-api03-..."
        )
        assert signal.source == AuthSource.API_KEY
        assert signal.env_var == "ANTHROPIC_API_KEY"
        assert signal.key_hint == "sk-ant-api03-..."
        assert signal.file_path is None

    def test_create_with_file_path(self):
        """Test creating signal with file path."""
        signal = AuthSignal(
            source=AuthSource.CREDENTIALS_FILE,
            file_path="/home/user/.claude/.credentials.json"
        )
        assert signal.source == AuthSource.CREDENTIALS_FILE
        assert signal.file_path == "/home/user/.claude/.credentials.json"
        assert signal.env_var is None
        assert signal.key_hint is None


# ============================================================================
# AuthInfo Dataclass Tests
# ============================================================================


class TestAuthInfo:
    """Test AuthInfo dataclass."""

    def test_empty_signals(self):
        """Test AuthInfo with no signals."""
        auth_info = AuthInfo(signals=[])
        assert auth_info.auth_source_for_db == "unknown"
        assert auth_info.is_configured is False
        assert auth_info.has_multiple is False

    def test_single_signal(self):
        """Test AuthInfo with single signal."""
        signal = AuthSignal(AuthSource.API_KEY, env_var="ANTHROPIC_API_KEY")
        auth_info = AuthInfo(signals=[signal])
        assert auth_info.auth_source_for_db == "api_key"
        assert auth_info.is_configured is True
        assert auth_info.has_multiple is False

    def test_multiple_signals(self):
        """Test AuthInfo with multiple signals."""
        signals = [
            AuthSignal(AuthSource.API_KEY, env_var="ANTHROPIC_API_KEY"),
            AuthSignal(AuthSource.OAUTH_TOKEN, env_var="CLAUDE_CODE_OAUTH_TOKEN"),
        ]
        auth_info = AuthInfo(signals=signals)
        assert auth_info.auth_source_for_db == "multiple"
        assert auth_info.is_configured is True
        assert auth_info.has_multiple is True

    def test_to_db_dict(self):
        """Test database serialization."""
        signal = AuthSignal(
            AuthSource.API_KEY,
            env_var="ANTHROPIC_API_KEY",
            key_hint="sk-ant-api03-..."  # Should NOT appear in db dict
        )
        auth_info = AuthInfo(signals=[signal])
        db_dict = auth_info.to_db_dict()

        assert db_dict["auth_source"] == "api_key"
        assert "api_key" in db_dict["auth_signals"]
        assert "auth_detected_at" in db_dict
        # Ensure key_hint is NOT in db_dict
        assert "sk-ant" not in str(db_dict)

    def test_to_db_dict_multiple(self):
        """Test database serialization with multiple signals."""
        signals = [
            AuthSignal(AuthSource.API_KEY, env_var="ANTHROPIC_API_KEY"),
            AuthSignal(AuthSource.BEDROCK, env_var="CLAUDE_CODE_USE_BEDROCK"),
        ]
        auth_info = AuthInfo(signals=signals)
        db_dict = auth_info.to_db_dict()

        assert db_dict["auth_source"] == "multiple"
        signals_json = json.loads(db_dict["auth_signals"])
        assert "api_key" in signals_json
        assert "bedrock" in signals_json


# ============================================================================
# mask_key Function Tests
# ============================================================================


class TestMaskKey:
    """Test key masking function."""

    def test_mask_long_key(self):
        """Test masking a long key shows first 12 chars."""
        key = "sk-ant-api03-abcdef123456789"
        result = mask_key(key)
        assert result == "sk-ant-api03..."

    def test_mask_short_key(self):
        """Test masking a short key returns ***."""
        result = mask_key("short")
        assert result == "***"

    def test_mask_exact_length_key(self):
        """Test key exactly at visible_chars length."""
        result = mask_key("123456789012")  # Exactly 12 chars
        assert result == "***"

    def test_mask_empty_key(self):
        """Test empty key returns ***."""
        result = mask_key("")
        assert result == "***"

    def test_mask_none_key(self):
        """Test None-like empty key returns ***."""
        result = mask_key(None)  # type: ignore
        assert result == "***"

    def test_mask_custom_visible_chars(self):
        """Test custom visible_chars parameter."""
        key = "sk-ant-api03-abcdef"
        result = mask_key(key, visible_chars=6)
        assert result == "sk-ant..."

    def test_mask_oauth_token(self):
        """Test masking OAuth token format."""
        key = "sk-ant-oat01-abcdef123456789"
        result = mask_key(key)
        assert result == "sk-ant-oat01..."


# ============================================================================
# detect_auth Function Tests
# ============================================================================


class TestDetectAuth:
    """Test authentication detection function."""

    def test_detect_api_key_only(self, monkeypatch):
        """Test detection when only ANTHROPIC_API_KEY is set."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-test123456789")
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)

        result = detect_auth(check_credentials_file=False)

        assert len(result.signals) == 1
        assert result.signals[0].source == AuthSource.API_KEY
        assert result.signals[0].env_var == "ANTHROPIC_API_KEY"
        assert result.auth_source_for_db == "api_key"

    def test_detect_oauth_token_only(self, monkeypatch):
        """Test detection when only CLAUDE_CODE_OAUTH_TOKEN is set."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-test123456789")
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)

        result = detect_auth(check_credentials_file=False)

        assert len(result.signals) == 1
        assert result.signals[0].source == AuthSource.OAUTH_TOKEN
        assert result.signals[0].env_var == "CLAUDE_CODE_OAUTH_TOKEN"
        assert result.auth_source_for_db == "oauth_token"

    def test_detect_bedrock(self, monkeypatch):
        """Test detection when CLAUDE_CODE_USE_BEDROCK=1."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)

        result = detect_auth(check_credentials_file=False)

        assert len(result.signals) == 1
        assert result.signals[0].source == AuthSource.BEDROCK
        assert result.signals[0].env_var == "CLAUDE_CODE_USE_BEDROCK"
        assert result.auth_source_for_db == "bedrock"

    def test_detect_vertex(self, monkeypatch):
        """Test detection when CLAUDE_CODE_USE_VERTEX=1."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)

        result = detect_auth(check_credentials_file=False)

        assert len(result.signals) == 1
        assert result.signals[0].source == AuthSource.VERTEX
        assert result.signals[0].env_var == "CLAUDE_CODE_USE_VERTEX"
        assert result.auth_source_for_db == "vertex"

    def test_detect_foundry(self, monkeypatch):
        """Test detection when CLAUDE_CODE_USE_FOUNDRY=1."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_USE_FOUNDRY", "1")

        result = detect_auth(check_credentials_file=False)

        assert len(result.signals) == 1
        assert result.signals[0].source == AuthSource.FOUNDRY
        assert result.signals[0].env_var == "CLAUDE_CODE_USE_FOUNDRY"
        assert result.auth_source_for_db == "foundry"

    def test_detect_multiple_signals(self, monkeypatch):
        """Test detection with multiple auth sources set."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-test123456789")
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-test123456789")
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)

        result = detect_auth(check_credentials_file=False)

        assert len(result.signals) == 2
        assert result.has_multiple is True
        assert result.auth_source_for_db == "multiple"
        sources = [s.source for s in result.signals]
        assert AuthSource.API_KEY in sources
        assert AuthSource.OAUTH_TOKEN in sources

    def test_detect_none_returns_unknown(self, monkeypatch):
        """Test detection returns UNKNOWN when no env vars set."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)

        result = detect_auth(check_credentials_file=False)

        assert len(result.signals) == 0
        assert result.is_configured is False
        assert result.auth_source_for_db == "unknown"

    def test_bedrock_requires_value_1(self, monkeypatch):
        """Test that BEDROCK only detected when value is '1'."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "true")  # Not "1"
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)

        result = detect_auth(check_credentials_file=False)

        assert len(result.signals) == 0

    def test_api_key_masking(self, monkeypatch):
        """Test that API key is masked in signal."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-abcdef123456789")
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)

        result = detect_auth(check_credentials_file=False)

        assert result.signals[0].key_hint == "sk-ant-api03..."
        # Full key should not be in key_hint
        assert "abcdef123456789" not in result.signals[0].key_hint


# ============================================================================
# _check_credentials_file Function Tests
# ============================================================================


class TestCheckCredentialsFile:
    """Test credentials file detection."""

    def test_credentials_file_detected(self, tmp_path, monkeypatch):
        """Test detection when credentials file exists with claudeAiOauth."""
        # Create mock credentials file
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_file.write_text('{"claudeAiOauth": {"token": "test"}}')

        # Mock Path.home() to return tmp_path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = _check_credentials_file()

        assert result is not None
        assert result.source == AuthSource.CREDENTIALS_FILE
        assert ".credentials.json" in result.file_path

    def test_credentials_file_missing(self, tmp_path, monkeypatch):
        """Test no signal when credentials file doesn't exist."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = _check_credentials_file()

        assert result is None

    def test_credentials_file_no_oauth_key(self, tmp_path, monkeypatch):
        """Test no signal when file exists but lacks claudeAiOauth."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_file.write_text('{"otherKey": "value"}')

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = _check_credentials_file()

        assert result is None

    def test_credentials_file_invalid_json(self, tmp_path, monkeypatch):
        """Test silent failure on invalid JSON."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_file.write_text('not valid json {{{')

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = _check_credentials_file()

        assert result is None  # Silent failure

    def test_credentials_file_permission_error(self, tmp_path, monkeypatch):
        """Test silent failure on PermissionError."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_file.write_text('{"claudeAiOauth": "test"}')

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Mock open to raise PermissionError
        original_open = open

        def mock_open_permission_error(path, *args, **kwargs):
            if ".credentials.json" in str(path):
                raise PermissionError("Access denied")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open_permission_error)

        result = _check_credentials_file()

        assert result is None  # Silent failure

    def test_credentials_file_io_error(self, tmp_path, monkeypatch):
        """Test silent failure on IOError."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_file.write_text('{"claudeAiOauth": "test"}')

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Mock open to raise IOError
        original_open = open

        def mock_open_io_error(path, *args, **kwargs):
            if ".credentials.json" in str(path):
                raise IOError("I/O error")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open_io_error)

        result = _check_credentials_file()

        assert result is None  # Silent failure


# ============================================================================
# format_auth_display Function Tests
# ============================================================================


class TestFormatAuthDisplay:
    """Test CLI display formatting."""

    def test_format_unknown(self):
        """Test display format when no auth detected."""
        auth_info = AuthInfo(signals=[])
        result = format_auth_display(auth_info)

        assert "Auth: Unknown" in result
        assert "no env vars detected" in result
        assert "keychain" in result
        assert "ANTHROPIC_API_KEY" in result

    def test_format_single_api_key(self):
        """Test display format for single API key."""
        signal = AuthSignal(
            AuthSource.API_KEY,
            env_var="ANTHROPIC_API_KEY",
            key_hint="sk-ant-api03-..."
        )
        auth_info = AuthInfo(signals=[signal])
        result = format_auth_display(auth_info)

        assert result == "Auth: ANTHROPIC_API_KEY (sk-ant-api03-...)"

    def test_format_single_oauth_token(self):
        """Test display format for single OAuth token."""
        signal = AuthSignal(
            AuthSource.OAUTH_TOKEN,
            env_var="CLAUDE_CODE_OAUTH_TOKEN",
            key_hint="sk-ant-oat01-..."
        )
        auth_info = AuthInfo(signals=[signal])
        result = format_auth_display(auth_info)

        assert result == "Auth: CLAUDE_CODE_OAUTH_TOKEN (sk-ant-oat01-...)"

    def test_format_single_bedrock(self):
        """Test display format for AWS Bedrock."""
        signal = AuthSignal(AuthSource.BEDROCK, env_var="CLAUDE_CODE_USE_BEDROCK")
        auth_info = AuthInfo(signals=[signal])
        result = format_auth_display(auth_info)

        assert result == "Auth: AWS Bedrock (CLAUDE_CODE_USE_BEDROCK)"

    def test_format_single_vertex(self):
        """Test display format for Google Vertex AI."""
        signal = AuthSignal(AuthSource.VERTEX, env_var="CLAUDE_CODE_USE_VERTEX")
        auth_info = AuthInfo(signals=[signal])
        result = format_auth_display(auth_info)

        assert result == "Auth: Google Vertex AI (CLAUDE_CODE_USE_VERTEX)"

    def test_format_single_foundry(self):
        """Test display format for Azure Foundry."""
        signal = AuthSignal(AuthSource.FOUNDRY, env_var="CLAUDE_CODE_USE_FOUNDRY")
        auth_info = AuthInfo(signals=[signal])
        result = format_auth_display(auth_info)

        assert result == "Auth: Azure Foundry (CLAUDE_CODE_USE_FOUNDRY)"

    def test_format_single_credentials_file(self):
        """Test display format for credentials file."""
        signal = AuthSignal(
            AuthSource.CREDENTIALS_FILE,
            file_path="/home/user/.claude/.credentials.json"
        )
        auth_info = AuthInfo(signals=[signal])
        result = format_auth_display(auth_info)

        assert result == "Auth: Credentials file (/home/user/.claude/.credentials.json)"

    def test_format_multiple_sources(self):
        """Test display format for multiple auth sources."""
        signals = [
            AuthSignal(AuthSource.API_KEY, env_var="ANTHROPIC_API_KEY", key_hint="sk-ant-api03-..."),
            AuthSignal(AuthSource.OAUTH_TOKEN, env_var="CLAUDE_CODE_OAUTH_TOKEN", key_hint="sk-ant-oat01-..."),
        ]
        auth_info = AuthInfo(signals=signals)
        result = format_auth_display(auth_info)

        assert "⚠ Multiple auth sources detected:" in result
        assert "ANTHROPIC_API_KEY (sk-ant-api03-...)" in result
        assert "CLAUDE_CODE_OAUTH_TOKEN (sk-ant-oat01-...)" in result
        assert "Claude Code will choose one" in result

    def test_format_multiple_with_credentials_file(self):
        """Test display format with credentials file in multiple sources."""
        signals = [
            AuthSignal(AuthSource.API_KEY, env_var="ANTHROPIC_API_KEY", key_hint="sk-ant-api03-..."),
            AuthSignal(AuthSource.CREDENTIALS_FILE, file_path="/home/user/.claude/.credentials.json"),
        ]
        auth_info = AuthInfo(signals=signals)
        result = format_auth_display(auth_info)

        assert "⚠ Multiple auth sources detected:" in result
        assert "ANTHROPIC_API_KEY" in result
        assert "/home/user/.claude/.credentials.json" in result

    def test_format_api_key_without_hint(self):
        """Test display format for API key without key hint."""
        signal = AuthSignal(AuthSource.API_KEY, env_var="ANTHROPIC_API_KEY")
        auth_info = AuthInfo(signals=[signal])
        result = format_auth_display(auth_info)

        assert result == "Auth: ANTHROPIC_API_KEY"

    def test_format_multiple_env_var_only(self):
        """Test multiple format with env var only (no hint)."""
        signals = [
            AuthSignal(AuthSource.BEDROCK, env_var="CLAUDE_CODE_USE_BEDROCK"),
            AuthSignal(AuthSource.VERTEX, env_var="CLAUDE_CODE_USE_VERTEX"),
        ]
        auth_info = AuthInfo(signals=signals)
        result = format_auth_display(auth_info)

        assert "⚠ Multiple auth sources detected:" in result
        assert "- CLAUDE_CODE_USE_BEDROCK" in result
        assert "- CLAUDE_CODE_USE_VERTEX" in result


# ============================================================================
# Integration Tests
# ============================================================================


class TestDetectAuthIntegration:
    """Integration tests for detect_auth with credentials file."""

    def test_detect_with_credentials_file(self, tmp_path, monkeypatch):
        """Test detect_auth includes credentials file when found."""
        # Clear env vars
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)

        # Create mock credentials file
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_file.write_text('{"claudeAiOauth": {"token": "test"}}')

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = detect_auth(check_credentials_file=True)

        assert len(result.signals) == 1
        assert result.signals[0].source == AuthSource.CREDENTIALS_FILE
        assert result.auth_source_for_db == "credentials_file"

    def test_detect_env_and_credentials_file(self, tmp_path, monkeypatch):
        """Test detect_auth with both env var and credentials file."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-test123456789")
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)

        # Create mock credentials file
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_file.write_text('{"claudeAiOauth": {"token": "test"}}')

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = detect_auth(check_credentials_file=True)

        assert len(result.signals) == 2
        assert result.has_multiple is True
        assert result.auth_source_for_db == "multiple"

    def test_detect_skip_credentials_file(self, tmp_path, monkeypatch):
        """Test detect_auth skips credentials file when disabled."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)

        # Create mock credentials file
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_file.write_text('{"claudeAiOauth": {"token": "test"}}')

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = detect_auth(check_credentials_file=False)

        assert len(result.signals) == 0
        assert result.auth_source_for_db == "unknown"


# ============================================================================
# Workflow Integration Tests (Database & Engine)
# ============================================================================


class TestAuthWorkflowIntegration:
    """Integration tests for auth detection with database and engine."""

    def test_session_stores_auth_source_api_key(self, tmp_path, monkeypatch):
        """Test that session creation stores auth_source when API key is set."""
        # Import here to avoid circular imports
        from orchestrator_auto import db

        # Set up clean env with only API key
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-test123456789")
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Create temp database
        db_path = str(tmp_path / "test.db")
        db.init_db(db_path)

        # Detect auth and create session
        auth_info = detect_auth(check_credentials_file=False)
        session_id = db.create_session(
            feature_description="Test feature",
            auth_info=auth_info.to_db_dict(),
            db_path=db_path,
        )

        # Verify auth stored in session
        session = db.get_session(session_id, db_path)
        assert session["auth_source"] == "api_key"
        assert "api_key" in session["auth_signals"]
        assert session["auth_detected_at"] is not None

    def test_session_stores_auth_source_oauth_token(self, tmp_path, monkeypatch):
        """Test that session creation stores auth_source when OAuth token is set."""
        from orchestrator_auto import db

        # Set up clean env with only OAuth token
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-test123456789")
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        db_path = str(tmp_path / "test.db")
        db.init_db(db_path)

        auth_info = detect_auth(check_credentials_file=False)
        session_id = db.create_session(
            feature_description="Test feature",
            auth_info=auth_info.to_db_dict(),
            db_path=db_path,
        )

        session = db.get_session(session_id, db_path)
        assert session["auth_source"] == "oauth_token"
        assert "oauth_token" in session["auth_signals"]

    def test_session_stores_auth_source_multiple(self, tmp_path, monkeypatch):
        """Test that session stores 'multiple' when multiple auth sources detected."""
        from orchestrator_auto import db

        # Set up env with multiple auth sources
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-test123456789")
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-test123456789")
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        db_path = str(tmp_path / "test.db")
        db.init_db(db_path)

        auth_info = detect_auth(check_credentials_file=False)
        session_id = db.create_session(
            feature_description="Test feature",
            auth_info=auth_info.to_db_dict(),
            db_path=db_path,
        )

        session = db.get_session(session_id, db_path)
        assert session["auth_source"] == "multiple"
        assert "api_key" in session["auth_signals"]
        assert "oauth_token" in session["auth_signals"]

    def test_session_stores_auth_source_unknown(self, tmp_path, monkeypatch):
        """Test that session stores 'unknown' when no auth detected."""
        from orchestrator_auto import db

        # Clear all auth env vars
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        db_path = str(tmp_path / "test.db")
        db.init_db(db_path)

        auth_info = detect_auth(check_credentials_file=False)
        session_id = db.create_session(
            feature_description="Test feature",
            auth_info=auth_info.to_db_dict(),
            db_path=db_path,
        )

        session = db.get_session(session_id, db_path)
        assert session["auth_source"] == "unknown"
        # Verify Unknown message says "no env vars" not "no auth configured"
        display = format_auth_display(auth_info)
        assert "Unknown" in display
        assert "no env vars detected" in display
        assert "keychain" in display  # Suggests keychain may still work

    def test_session_stores_credentials_file_auth(self, tmp_path, monkeypatch):
        """Test that credentials file detection stores auth in session."""
        from orchestrator_auto import db

        # Clear env vars
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)

        # Create mock credentials file
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_file.write_text('{"claudeAiOauth": {"token": "test"}}')
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        db_path = str(tmp_path / "test.db")
        db.init_db(db_path)

        auth_info = detect_auth(check_credentials_file=True)
        session_id = db.create_session(
            feature_description="Test feature",
            auth_info=auth_info.to_db_dict(),
            db_path=db_path,
        )

        session = db.get_session(session_id, db_path)
        assert session["auth_source"] == "credentials_file"
        assert "credentials_file" in session["auth_signals"]

    def test_session_without_auth_info_has_null_columns(self, tmp_path):
        """Test that sessions created without auth_info have NULL auth columns."""
        from orchestrator_auto import db

        db_path = str(tmp_path / "test.db")
        db.init_db(db_path)

        # Create session without auth_info (backwards compatibility)
        session_id = db.create_session(
            feature_description="Test feature",
            db_path=db_path,
        )

        session = db.get_session(session_id, db_path)
        assert session["auth_source"] is None
        assert session["auth_signals"] is None
        assert session["auth_detected_at"] is None

    def test_cloud_provider_auth_bedrock(self, tmp_path, monkeypatch):
        """Test that AWS Bedrock auth is detected and stored."""
        from orchestrator_auto import db

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        db_path = str(tmp_path / "test.db")
        db.init_db(db_path)

        auth_info = detect_auth(check_credentials_file=False)
        session_id = db.create_session(
            feature_description="Test feature",
            auth_info=auth_info.to_db_dict(),
            db_path=db_path,
        )

        session = db.get_session(session_id, db_path)
        assert session["auth_source"] == "bedrock"

    def test_cloud_provider_auth_vertex(self, tmp_path, monkeypatch):
        """Test that Google Vertex AI auth is detected and stored."""
        from orchestrator_auto import db

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
        monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        db_path = str(tmp_path / "test.db")
        db.init_db(db_path)

        auth_info = detect_auth(check_credentials_file=False)
        session_id = db.create_session(
            feature_description="Test feature",
            auth_info=auth_info.to_db_dict(),
            db_path=db_path,
        )

        session = db.get_session(session_id, db_path)
        assert session["auth_source"] == "vertex"
