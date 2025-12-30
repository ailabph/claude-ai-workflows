"""
Unit tests for secrets detection module.

Tests use synthetic (fake) secrets that match patterns but are not real credentials.
"""

import pytest
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto.secrets import (
    contains_secrets,
    get_pattern_count,
    SecretPattern,
    SECRETS_PATTERNS,
)


class TestSecretPatternDataclass:
    """Test SecretPattern dataclass structure."""

    def test_secret_pattern_has_name_and_pattern(self):
        """Test that SecretPattern has required fields."""
        sp = SecretPattern(name="TEST_PATTERN", pattern=r"test.*")
        assert sp.name == "TEST_PATTERN"
        assert sp.pattern == r"test.*"

    def test_all_patterns_have_uppercase_names(self):
        """Test that all pattern names are uppercase identifiers."""
        for sp in SECRETS_PATTERNS:
            assert sp.name == sp.name.upper(), f"Pattern name should be uppercase: {sp.name}"
            assert "_" in sp.name or sp.name.isalpha(), f"Pattern name should be SCREAMING_SNAKE_CASE: {sp.name}"


class TestSecretsPatternCount:
    """Test that we have the expected number of patterns."""

    def test_has_nine_patterns(self):
        """Test that we have exactly 9 secret patterns as specified."""
        assert get_pattern_count() == 9
        assert len(SECRETS_PATTERNS) == 9


class TestContainsSecretsAPIKey:
    """Test API key pattern detection."""

    def test_detects_api_key_equals(self):
        """Test detection of api_key = 'value' pattern."""
        diff = '''
+API_KEY = "abcdefghijklmnopqrstuvwxyz1234567890"
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "API_KEY_ASSIGNMENT" in patterns

    def test_detects_apikey_colon(self):
        """Test detection of apikey: value pattern (YAML/JSON)."""
        diff = '''
+apikey: "abcdefghijklmnopqrstuvwxyz1234567890"
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "API_KEY_ASSIGNMENT" in patterns

    def test_detects_api_key_hyphen(self):
        """Test detection of api-key pattern."""
        diff = '''
+api-key = "abcdefghijklmnopqrstuvwxyz1234567890"
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "API_KEY_ASSIGNMENT" in patterns

    def test_ignores_short_api_key(self):
        """Test that short values (< 20 chars) don't trigger."""
        diff = '''
+API_KEY = "short"
'''
        has_secrets, patterns = contains_secrets(diff)
        # Should NOT match because value is too short
        assert "API_KEY_ASSIGNMENT" not in patterns


class TestContainsSecretsPassword:
    """Test password/secret pattern detection."""

    def test_detects_password_equals(self):
        """Test detection of password = 'value' pattern."""
        diff = '''
+password = "mysecretpassword123"
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "PASSWORD_ASSIGNMENT" in patterns

    def test_detects_secret_colon(self):
        """Test detection of secret: value pattern."""
        diff = '''
+secret: "this_is_a_secret_value"
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "PASSWORD_ASSIGNMENT" in patterns

    def test_detects_pwd(self):
        """Test detection of pwd = value pattern."""
        diff = '''
+pwd = "mypassword"
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "PASSWORD_ASSIGNMENT" in patterns


class TestContainsSecretsToken:
    """Test token pattern detection."""

    def test_detects_token_equals(self):
        """Test detection of token = 'value' pattern."""
        diff = '''
+token = "abcdefghijklmnopqrstuvwxyz1234567890"
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "TOKEN_ASSIGNMENT" in patterns

    def test_detects_bearer_token(self):
        """Test detection of Bearer token in authorization header."""
        diff = '''
+Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "BEARER_TOKEN" in patterns


class TestContainsSecretsPrivateKey:
    """Test private key block detection."""

    def test_detects_rsa_private_key(self):
        """Test detection of RSA private key header."""
        diff = '''
+-----BEGIN RSA PRIVATE KEY-----
+MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC7...
+-----END RSA PRIVATE KEY-----
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "PRIVATE_KEY_BLOCK" in patterns

    def test_detects_ec_private_key(self):
        """Test detection of EC private key header."""
        diff = '''
+-----BEGIN EC PRIVATE KEY-----
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "PRIVATE_KEY_BLOCK" in patterns

    def test_detects_openssh_private_key(self):
        """Test detection of OpenSSH private key header."""
        diff = '''
+-----BEGIN OPENSSH PRIVATE KEY-----
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "PRIVATE_KEY_BLOCK" in patterns

    def test_detects_generic_private_key(self):
        """Test detection of generic private key header."""
        diff = '''
+-----BEGIN PRIVATE KEY-----
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "PRIVATE_KEY_BLOCK" in patterns


class TestContainsSecretsAWS:
    """Test AWS credential pattern detection."""

    def test_detects_aws_access_key(self):
        """Test detection of AWS access key pattern."""
        diff = '''
+AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "AWS_CREDENTIAL" in patterns

    def test_detects_aws_secret(self):
        """Test detection of AWS secret pattern."""
        diff = '''
+aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "AWS_CREDENTIAL" in patterns


class TestContainsSecretsGitHub:
    """Test GitHub PAT pattern detection."""

    def test_detects_github_pat(self):
        """Test detection of GitHub Personal Access Token (ghp_ format)."""
        diff = '''
+GITHUB_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "GITHUB_PAT" in patterns

    def test_ignores_partial_github_pat(self):
        """Test that incomplete GitHub PAT pattern doesn't trigger."""
        diff = '''
+# ghp_ prefix is used for GitHub tokens
'''
        has_secrets, patterns = contains_secrets(diff)
        # Should NOT match because no 36-char suffix
        assert "GITHUB_PAT" not in patterns


class TestContainsSecretsOpenAI:
    """Test OpenAI API key pattern detection."""

    def test_detects_openai_key(self):
        """Test detection of OpenAI API key (sk- format, 48 chars)."""
        diff = '''
+OPENAI_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "OPENAI_API_KEY" in patterns

    def test_ignores_short_sk_prefix(self):
        """Test that short sk- strings don't trigger."""
        diff = '''
+sk-short
'''
        has_secrets, patterns = contains_secrets(diff)
        # Should NOT match because too short
        assert "OPENAI_API_KEY" not in patterns


class TestContainsSecretsAnthropic:
    """Test Anthropic API key pattern detection."""

    def test_detects_anthropic_api_key_env(self):
        """Test detection of ANTHROPIC_API_KEY environment variable."""
        diff = '''
+ANTHROPIC_API_KEY = "sk-ant-..."
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "ANTHROPIC_API_KEY" in patterns

    def test_detects_anthropic_api_key_hyphen(self):
        """Test detection of anthropic-api-key pattern."""
        diff = '''
+anthropic-api-key: "value"
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "ANTHROPIC_API_KEY" in patterns


class TestContainsSecretsCleanDiff:
    """Test that clean diffs don't trigger false positives."""

    def test_clean_diff_no_secrets(self):
        """Test that normal code changes don't trigger detection."""
        diff = '''
diff --git a/app.py b/app.py
index 1234567..abcdefg 100644
--- a/app.py
+++ b/app.py
@@ -1,5 +1,7 @@
 def hello():
-    return "Hello"
+    return "Hello, World!"
+
+def goodbye():
+    return "Goodbye!"
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is False
        assert patterns == []

    def test_empty_diff_no_secrets(self):
        """Test that empty diff returns no secrets."""
        has_secrets, patterns = contains_secrets("")
        assert has_secrets is False
        assert patterns == []

    def test_none_safe(self):
        """Test that None-like values don't crash."""
        # Empty string should work
        has_secrets, patterns = contains_secrets("")
        assert has_secrets is False
        assert patterns == []

    def test_comments_about_secrets_partial_match(self):
        """Test that comments discussing secrets may trigger patterns."""
        # Note: Comments like "set your api_key here" might trigger
        # This is intentional - better safe than sorry
        diff = '''
+# TODO: Set your API_KEY = "your-key-here-replace-me"
'''
        # This WILL match because it has the pattern structure
        # Even in comments, we want to be cautious
        has_secrets, patterns = contains_secrets(diff)
        # The pattern matches regardless of context - this is by design


class TestContainsSecretsMultiplePatterns:
    """Test detection of multiple secrets in one diff."""

    def test_detects_multiple_patterns(self):
        """Test that multiple different secrets are all detected."""
        diff = '''
+API_KEY = "abcdefghijklmnopqrstuvwxyz1234567890"
+password = "mysecretpassword"
+-----BEGIN RSA PRIVATE KEY-----
'''
        has_secrets, patterns = contains_secrets(diff)
        assert has_secrets is True
        assert "API_KEY_ASSIGNMENT" in patterns
        assert "PASSWORD_ASSIGNMENT" in patterns
        assert "PRIVATE_KEY_BLOCK" in patterns
        assert len(patterns) == 3


class TestContainsSecretsNoValueLeak:
    """Test that actual secret values are never returned."""

    def test_returns_pattern_names_not_values(self):
        """Critical: Verify only pattern names are returned, not matched values."""
        fake_secret = "ghp_SuperSecretTokenThatShouldNeverBeLogged"
        diff = f'+GITHUB_TOKEN = "{fake_secret}"'

        has_secrets, patterns = contains_secrets(diff)

        # Should return pattern name
        assert "GITHUB_PAT" in patterns

        # Should NEVER contain the actual secret value
        for pattern in patterns:
            assert fake_secret not in pattern
            assert "SuperSecret" not in pattern

        # Pattern names should only be uppercase identifiers
        for pattern in patterns:
            assert pattern == pattern.upper()
            assert pattern.replace("_", "").isalpha()

    def test_returns_pattern_names_not_regex(self):
        """Verify regex patterns themselves are not returned."""
        diff = '+API_KEY = "abcdefghijklmnopqrstuvwxyz1234567890"'

        has_secrets, patterns = contains_secrets(diff)

        # Should not contain regex metacharacters
        for pattern in patterns:
            assert "(?i)" not in pattern
            assert "[" not in pattern
            assert "]" not in pattern
            assert "*" not in pattern
            assert "+" not in pattern
            assert "\\" not in pattern


class TestContainsSecretsCaseInsensitive:
    """Test case insensitivity of patterns where appropriate."""

    def test_api_key_case_insensitive(self):
        """Test that API_KEY, api_key, Api_Key all match."""
        diffs = [
            '+API_KEY = "abcdefghijklmnopqrstuvwxyz1234567890"',
            '+api_key = "abcdefghijklmnopqrstuvwxyz1234567890"',
            '+Api_Key = "abcdefghijklmnopqrstuvwxyz1234567890"',
        ]
        for diff in diffs:
            has_secrets, patterns = contains_secrets(diff)
            assert has_secrets is True
            assert "API_KEY_ASSIGNMENT" in patterns

    def test_password_case_insensitive(self):
        """Test that PASSWORD, password, Password all match."""
        diffs = [
            '+PASSWORD = "mysecretpassword"',
            '+password = "mysecretpassword"',
            '+Password = "mysecretpassword"',
        ]
        for diff in diffs:
            has_secrets, patterns = contains_secrets(diff)
            assert has_secrets is True
            assert "PASSWORD_ASSIGNMENT" in patterns
