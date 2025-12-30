"""
AI-powered commit message generator for orchestrator-auto.

Uses Claude (via claude-agent-sdk) to analyze git diffs and generate
meaningful commit messages following Conventional Commits format.

Security: This module assumes secrets have already been checked.
Always call contains_secrets() before generate_smart_commit_message().
"""

import asyncio
import re
from typing import Optional, Dict

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import (
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

# Model for commit message generation (fast and cost-effective)
DEFAULT_MODEL = "claude-haiku-3-5-20241022"

# Timeout for AI generation (30 seconds)
DEFAULT_TIMEOUT = 30

# Maximum commit message length
MAX_MESSAGE_LENGTH = 500

# Maximum subject line length (first line) - git convention
MAX_SUBJECT_LENGTH = 72

# System prompt for commit message generation
SYSTEM_PROMPT = """You are a commit message generator. Your ONLY job is to output a commit message.

Rules:
1. Output ONLY the commit message - no explanations, no markdown code fences, no commentary
2. Follow Conventional Commits format exactly
3. Never mention AI, Claude, or that this message was generated
4. Be concise but descriptive

Format:
<type>: <description>

- bullet point for change 1
- bullet point for change 2

Types:
- feat: New user-visible functionality
- fix: Bug correction
- refactor: Code restructuring (no behavior change)
- docs: Documentation only
- test: Test files only
- chore: Config, build, dependencies
- style: Formatting only
- perf: Performance optimization"""

# User prompt template
USER_PROMPT_TEMPLATE = """Generate a commit message for these changes:

Feature context: {feature_hint}

Stats: {files_changed} files changed, {insertions} insertions(+), {deletions} deletions(-)

Diff:
```
{diff}
```

Output ONLY the commit message, nothing else."""

# Valid conventional commit types
VALID_TYPES = {"feat", "fix", "refactor", "docs", "test", "chore", "style", "perf"}

# Patterns to strip from AI output
FORBIDDEN_PATTERNS = [
    r"(?i)generated\s+(by|with|using)\s+",
    r"(?i)claude",
    r"(?i)anthropic",
    r"(?i)\bai\b",
    r"(?i)language\s+model",
    r"(?i)llm",
]


def _build_prompt(diff: str, stats: Dict[str, int], feature_hint: str) -> str:
    """Build the user prompt for commit message generation."""
    return USER_PROMPT_TEMPLATE.format(
        feature_hint=feature_hint or "Code changes",
        files_changed=stats.get("files_changed", 0),
        insertions=stats.get("insertions", 0),
        deletions=stats.get("deletions", 0),
        diff=diff[:6000],  # Truncate diff for prompt (leave room for rest)
    )


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from text."""
    # Remove ```commit or ```text or just ``` blocks
    text = re.sub(r"^```[\w]*\n?", "", text.strip())
    text = re.sub(r"\n?```$", "", text.strip())
    return text.strip()


def _contains_ai_mentions(text: str) -> bool:
    """Check if text contains AI/Claude mentions that should be removed."""
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def _validate_format(message: str) -> bool:
    """
    Validate that message follows Conventional Commits format.

    Expected formats:
    <type>: <description>
    <type>(scope): <description>
    <type>!: <description>           (breaking change)
    <type>(scope)!: <description>    (scoped breaking change)

    Optional body with bullet points.
    """
    if not message:
        return False

    lines = message.strip().split("\n")
    if not lines:
        return False

    first_line = lines[0]

    # Check for Conventional Commits format:
    # type[(scope)][!]: description
    # Examples: feat: add login, fix(auth): handle timeout, feat!: breaking change
    match = re.match(r"^(\w+)(?:\([^)]+\))?!?:\s+.+", first_line)
    if not match:
        return False

    commit_type = match.group(1).lower()
    if commit_type not in VALID_TYPES:
        return False

    return True


def _clean_and_validate(response: str) -> Optional[str]:
    """
    Clean and validate AI response.

    Returns None if:
    - Response is empty
    - Contains AI mentions
    - Doesn't follow Conventional Commits format

    Returns cleaned message if valid.
    """
    if not response:
        return None

    # Strip code fences
    message = _strip_code_fences(response)

    if not message:
        return None

    # Check for AI mentions
    if _contains_ai_mentions(message):
        return None

    # Validate format
    if not _validate_format(message):
        return None

    # Enforce 72-char subject line (first line)
    lines = message.split("\n")
    if len(lines[0]) > MAX_SUBJECT_LENGTH:
        # Truncate subject at word boundary if possible
        subject = lines[0][:MAX_SUBJECT_LENGTH]
        last_space = subject.rfind(" ")
        if last_space > MAX_SUBJECT_LENGTH // 2:
            subject = subject[:last_space]
        lines[0] = subject
        message = "\n".join(lines)

    # Truncate overall message if too long
    if len(message) > MAX_MESSAGE_LENGTH:
        # Try to truncate at a line boundary
        lines = message.split("\n")
        truncated = ""
        for line in lines:
            if len(truncated) + len(line) + 1 > MAX_MESSAGE_LENGTH - 3:
                break
            truncated += line + "\n"
        message = truncated.strip() + "..."

    return message


async def generate_smart_commit_message_async(
    diff: str,
    stats: Dict[str, int],
    feature_hint: str = "",
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """
    Generate a commit message using Claude AI (async).

    IMPORTANT: Always check for secrets BEFORE calling this function.
    Use secrets.contains_secrets(diff) first.

    Args:
        diff: Git diff content (should be pre-checked for secrets)
        stats: Dict with keys: files_changed, insertions, deletions
        feature_hint: Optional context about what feature is being worked on
        model: Claude model to use (default: Haiku for speed/cost)
        timeout: Timeout in seconds (default: 30)

    Returns:
        Commit message string following Conventional Commits format,
        or None if generation fails for any reason.

    Security:
        - This function does NOT check for secrets
        - Caller MUST check secrets before calling
        - Returns None on any error (graceful fallback)
    """
    if not diff:
        return None

    prompt = _build_prompt(diff, stats, feature_hint)

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        tools=[],  # No tools needed for text generation
        model=model,
        permission_mode="default",
    )

    async def _query_client() -> Optional[str]:
        """Inner async function to query the client."""
        async with ClaudeSDKClient(options) as client:
            await client.query(prompt)
            response_text = ""

            async for message in client.receive_messages():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_text += block.text
                elif isinstance(message, ResultMessage):
                    break

            return _clean_and_validate(response_text)

    try:
        # Use wait_for for Python 3.10 compatibility (asyncio.timeout is 3.11+)
        return await asyncio.wait_for(_query_client(), timeout=timeout)

    except asyncio.TimeoutError:
        # Timeout - return None for graceful fallback
        return None
    except Exception:
        # Any other error - return None for graceful fallback
        return None


def generate_smart_commit_message(
    diff: str,
    stats: Dict[str, int],
    feature_hint: str = "",
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """
    Generate a commit message using Claude AI (sync wrapper).

    IMPORTANT: Always check for secrets BEFORE calling this function.
    Use secrets.contains_secrets(diff) first.

    Args:
        diff: Git diff content (should be pre-checked for secrets)
        stats: Dict with keys: files_changed, insertions, deletions
        feature_hint: Optional context about what feature is being worked on
        model: Claude model to use (default: Haiku for speed/cost)
        timeout: Timeout in seconds (default: 30)

    Returns:
        Commit message string following Conventional Commits format,
        or None if generation fails for any reason.

    Example:
        from orchestrator_auto.secrets import contains_secrets
        from orchestrator_auto.commit_ai import generate_smart_commit_message

        # ALWAYS check for secrets first!
        has_secrets, patterns = contains_secrets(diff)
        if has_secrets:
            # Use fallback message instead
            return fallback_commit_message()

        # Safe to call AI
        message = generate_smart_commit_message(diff, stats, "Add user auth")
        if message is None:
            # Use fallback on any error
            return fallback_commit_message()
    """
    try:
        return asyncio.run(
            generate_smart_commit_message_async(
                diff=diff,
                stats=stats,
                feature_hint=feature_hint,
                model=model,
                timeout=timeout,
            )
        )
    except Exception:
        # Any error in async handling - return None
        return None


# Export constants for testing
__all__ = [
    "generate_smart_commit_message",
    "generate_smart_commit_message_async",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT",
    "MAX_MESSAGE_LENGTH",
    "MAX_SUBJECT_LENGTH",
    "VALID_TYPES",
    # Internal functions exposed for testing
    "_build_prompt",
    "_strip_code_fences",
    "_contains_ai_mentions",
    "_validate_format",
    "_clean_and_validate",
]
