"""
Secrets detection for orchestrator-auto.

Provides pattern matching to detect potential secrets in git diffs
before sending them to external APIs for analysis.

Security principle: Never log or return actual secret values,
only return pattern names that were matched.
"""

import re
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class SecretPattern:
    """A named pattern for detecting potential secrets."""
    name: str        # Human-readable identifier for logging (e.g., "API_KEY_ASSIGNMENT")
    pattern: str     # Regex pattern to match


# List of patterns to detect potential secrets in diffs.
# Each pattern has a descriptive name that is safe to log.
SECRETS_PATTERNS: List[SecretPattern] = [
    # Generic API key assignments
    SecretPattern(
        "API_KEY_ASSIGNMENT",
        r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?[a-zA-Z0-9]{20,}'
    ),
    # Password/secret assignments
    SecretPattern(
        "PASSWORD_ASSIGNMENT",
        r'(?i)(secret|password|passwd|pwd)\s*[=:]\s*["\']?.{8,}'
    ),
    # Generic token assignments
    SecretPattern(
        "TOKEN_ASSIGNMENT",
        r'(?i)(token)\s*[=:]\s*["\']?[a-zA-Z0-9_-]{20,}'
    ),
    # Bearer tokens in headers/code
    SecretPattern(
        "BEARER_TOKEN",
        r'(?i)bearer\s+[a-zA-Z0-9_-]{20,}'
    ),
    # Private key blocks (RSA, EC, DSA, OPENSSH)
    SecretPattern(
        "PRIVATE_KEY_BLOCK",
        r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'
    ),
    # AWS credentials
    SecretPattern(
        "AWS_CREDENTIAL",
        r'(?i)aws[_-]?(access[_-]?key|secret)'
    ),
    # GitHub Personal Access Tokens (new format: ghp_)
    SecretPattern(
        "GITHUB_PAT",
        r'ghp_[a-zA-Z0-9]{36}'
    ),
    # OpenAI API keys (sk- prefix)
    SecretPattern(
        "OPENAI_API_KEY",
        r'sk-[a-zA-Z0-9]{48}'
    ),
    # Anthropic API key references
    SecretPattern(
        "ANTHROPIC_API_KEY",
        r'(?i)anthropic[_-]?api[_-]?key'
    ),
]


def contains_secrets(diff: str) -> Tuple[bool, List[str]]:
    """
    Check if a diff contains potential secrets.

    Scans the diff text against all known secret patterns.
    Returns only pattern names, NEVER actual values.

    Args:
        diff: The git diff text to scan

    Returns:
        Tuple of (has_secrets: bool, matched_pattern_names: list[str])
        Example: (True, ["API_KEY_ASSIGNMENT", "GITHUB_PAT"])

    Security:
        - Only pattern names are returned, never matched values
        - Safe to log the returned pattern names
    """
    if not diff:
        return (False, [])

    matched: List[str] = []

    for sp in SECRETS_PATTERNS:
        if re.search(sp.pattern, diff):
            matched.append(sp.name)

    return (len(matched) > 0, matched)


def get_pattern_count() -> int:
    """Return the number of secret patterns configured."""
    return len(SECRETS_PATTERNS)
