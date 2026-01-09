"""
AI-powered plan conversion for orchestrator-auto.

Converts regular markdown plans into orchestrator-compatible format
with properly formatted milestone headers (### Milestone N: Name).

Uses Claude to intelligently restructure plans while preserving content.
"""

import asyncio
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import (
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)


# Default model for conversion (good quality/cost balance)
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# Timeout for AI conversion (60 seconds - plans can be large)
DEFAULT_TIMEOUT = 60

# Default maximum milestones to create
DEFAULT_MAX_MILESTONES = 5


class ConversionError(Exception):
    """Raised when plan conversion fails after retries."""
    pass


# System prompt for plan conversion
CONVERT_SYSTEM_PROMPT = """You are a plan converter for the Claude Orchestrator system.

Your ONLY job is to restructure markdown plans into orchestrator-compatible format.

## Output Requirements

1. Every milestone MUST have exactly this header format:
   ### Milestone N: Name

   Where N is a sequential number starting at 1, and Name is a descriptive title.

2. Keep the original content and intent - just restructure into milestones.

3. Each milestone should include (where applicable):
   **Prerequisites:** (what must be done before this milestone)
   **Tasks:**
   1. First task
   2. Second task

   **Deliverables:**
   - [ ] Deliverable one
   - [ ] Deliverable two

4. Include a feature description at the top. If the plan has a title, use that.
   Format as either:
   - YAML frontmatter: ---\\nfeature: Description\\n---
   - Or header: # Feature: Description
   - Or: # Implementation Plan: Description

5. Combine related work to stay within the milestone limit. Each milestone should be a meaningful unit of work.

## Rules

- Output ONLY the converted markdown - no explanations, no code fences around the entire output
- Preserve code blocks, links, and formatting within sections
- Do NOT add tasks or content not in the original
- Do NOT remove important details from the original
- Use clear, action-oriented milestone names
- Milestone numbering must be sequential starting at 1
- If original has numbered steps/phases/tasks, convert them to milestones

## Example Output Format

---
feature: User Authentication System
---

# Implementation Plan: User Authentication System

## Overview
Brief description from the original plan.

### Milestone 1: Database Schema and Models
**Tasks:**
1. Create user model with required fields
2. Add database migration

**Deliverables:**
- [ ] User model created
- [ ] Migration applied successfully

### Milestone 2: Authentication Service
**Tasks:**
1. Implement JWT token generation
2. Add login/logout endpoints

**Deliverables:**
- [ ] JWT service working
- [ ] Endpoints responding correctly
"""

# User prompt template
CONVERT_USER_PROMPT = """Convert this plan to orchestrator-compatible format:

{content}

Requirements:
- Create at most {max_milestones} milestones (combine related work if needed)
- Use exactly this format for milestone headers: ### Milestone N: Name
- Preserve all technical details and content from the original
- Output only the converted markdown, no explanations or wrapper code fences"""

# Enhanced prompt for retry (more explicit)
CONVERT_RETRY_PROMPT = """The previous conversion did not produce valid milestone headers.

CRITICAL: You MUST use exactly this header format for each milestone:
### Milestone 1: Name Here
### Milestone 2: Another Name

The "###" prefix, "Milestone", number, colon, and name are ALL required.

Convert this plan:

{content}

Output only the converted markdown with proper ### Milestone N: Name headers."""


def validate_plan_content(content: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Validate if content is orchestrator-compatible.

    Checks for properly formatted milestone headers:
    ### Milestone N: Name

    Args:
        content: Plan content as string

    Returns:
        Tuple of (is_valid, details) where details includes:
        - milestones: int - number of milestones found
        - milestone_names: List[str] - extracted milestone names
        - error: Optional[str] - error message if invalid
    """
    # Pattern: ### Milestone N: Name
    milestone_pattern = r'###\s*Milestone\s*(\d+):\s*(.+)'
    matches = re.findall(milestone_pattern, content, re.IGNORECASE)

    if not matches:
        return False, {
            "milestones": 0,
            "milestone_names": [],
            "error": "No milestones found. Expected format: ### Milestone N: Name"
        }

    milestone_names = [name.strip() for _, name in matches]

    return True, {
        "milestones": len(matches),
        "milestone_names": milestone_names,
        "error": None
    }


def _build_prompt(content: str, max_milestones: int, is_retry: bool = False) -> str:
    """Build the user prompt for conversion."""
    if is_retry:
        return CONVERT_RETRY_PROMPT.format(content=content)
    return CONVERT_USER_PROMPT.format(content=content, max_milestones=max_milestones)


def _strip_outer_code_fences(text: str) -> str:
    """Remove outer markdown code fences if present."""
    text = text.strip()
    # Remove ```markdown or ``` at start
    text = re.sub(r'^```(?:markdown|md)?\n?', '', text)
    # Remove ``` at end
    text = re.sub(r'\n?```$', '', text)
    return text.strip()


def _extract_feature(content: str) -> Optional[str]:
    """Extract feature description from converted plan."""
    # Try YAML frontmatter
    yaml_match = re.search(r'^---\s*\n.*?feature:\s*(.+?)\n.*?---', content, re.DOTALL | re.IGNORECASE)
    if yaml_match:
        return yaml_match.group(1).strip()

    # Try # Feature: header
    feature_match = re.search(r'^#\s*Feature:\s*(.+)$', content, re.MULTILINE | re.IGNORECASE)
    if feature_match:
        return feature_match.group(1).strip()

    # Try # Implementation Plan: header
    impl_match = re.search(r'^#\s*Implementation Plan:\s*(.+)$', content, re.MULTILINE | re.IGNORECASE)
    if impl_match:
        return impl_match.group(1).strip()

    # Try first H1
    h1_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if h1_match:
        title = h1_match.group(1).strip()
        # Strip common suffixes
        title = re.sub(r'\s*-\s*Implementation Plan$', '', title, flags=re.IGNORECASE)
        return title

    return None


async def convert_plan_async(
    content: str,
    model: str = DEFAULT_MODEL,
    max_milestones: int = DEFAULT_MAX_MILESTONES,
    timeout: int = DEFAULT_TIMEOUT,
) -> Tuple[str, Dict[str, Any]]:
    """
    Convert a markdown plan to orchestrator-compatible format (async).

    Uses Claude AI to intelligently restructure the plan with proper
    milestone headers while preserving all original content.

    Args:
        content: Original plan markdown content
        model: Claude model to use (full ID or alias)
        max_milestones: Maximum number of milestones to create
        timeout: API timeout in seconds

    Returns:
        Tuple of (converted_content, metadata) where metadata includes:
        - milestones: int - number of milestones created
        - milestone_names: List[str] - milestone names
        - feature: Optional[str] - extracted feature description
        - model_used: str - actual model ID used
        - retry_used: bool - whether retry was needed

    Raises:
        ConversionError: If conversion fails after retries
        asyncio.TimeoutError: If API call times out
    """
    if not content or not content.strip():
        raise ConversionError("Empty content provided")

    options = ClaudeAgentOptions(
        system_prompt=CONVERT_SYSTEM_PROMPT,
        tools=[],  # No tools needed for conversion
        model=model,
        permission_mode="default",
    )

    async def _query_and_convert(is_retry: bool = False) -> Tuple[Optional[str], bool, Dict]:
        """Inner function to query Claude and validate result."""
        prompt = _build_prompt(content, max_milestones, is_retry=is_retry)

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

            # Clean up response
            converted = _strip_outer_code_fences(response_text)

            # Validate
            is_valid, details = validate_plan_content(converted)

            return converted if is_valid else None, is_valid, details

    # First attempt
    try:
        converted, is_valid, details = await asyncio.wait_for(
            _query_and_convert(is_retry=False),
            timeout=timeout
        )

        if is_valid and converted:
            feature = _extract_feature(converted)
            return converted, {
                "milestones": details["milestones"],
                "milestone_names": details["milestone_names"],
                "feature": feature,
                "model_used": model,
                "retry_used": False,
            }

        # Retry with enhanced prompt
        converted, is_valid, details = await asyncio.wait_for(
            _query_and_convert(is_retry=True),
            timeout=timeout
        )

        if is_valid and converted:
            feature = _extract_feature(converted)
            return converted, {
                "milestones": details["milestones"],
                "milestone_names": details["milestone_names"],
                "feature": feature,
                "model_used": model,
                "retry_used": True,
            }

        # Both attempts failed
        raise ConversionError(
            f"Conversion produced invalid output after retry: {details.get('error', 'Unknown error')}"
        )

    except asyncio.TimeoutError:
        raise ConversionError(f"Conversion timed out after {timeout} seconds")
    except ConversionError:
        raise
    except Exception as e:
        raise ConversionError(f"Conversion failed: {str(e)}")


def convert_plan(
    content: str,
    model: str = DEFAULT_MODEL,
    max_milestones: int = DEFAULT_MAX_MILESTONES,
    timeout: int = DEFAULT_TIMEOUT,
) -> Tuple[str, Dict[str, Any]]:
    """
    Convert a markdown plan to orchestrator-compatible format (sync wrapper).

    Uses Claude AI to intelligently restructure the plan with proper
    milestone headers while preserving all original content.

    Args:
        content: Original plan markdown content
        model: Claude model to use (full ID or alias)
        max_milestones: Maximum number of milestones to create
        timeout: API timeout in seconds

    Returns:
        Tuple of (converted_content, metadata) where metadata includes:
        - milestones: int - number of milestones created
        - milestone_names: List[str] - milestone names
        - feature: Optional[str] - extracted feature description
        - model_used: str - actual model ID used
        - retry_used: bool - whether retry was needed

    Raises:
        ConversionError: If conversion fails after retries

    Example:
        from orchestrator_auto.convert import convert_plan, validate_plan_content

        # Read plan file
        content = Path("my_plan.md").read_text()

        # Check if already valid
        is_valid, details = validate_plan_content(content)
        if is_valid:
            print(f"Already valid with {details['milestones']} milestones")
        else:
            # Convert
            converted, metadata = convert_plan(content)
            print(f"Converted to {metadata['milestones']} milestones")
            Path("converted_plan.md").write_text(converted)
    """
    return asyncio.run(
        convert_plan_async(
            content=content,
            model=model,
            max_milestones=max_milestones,
            timeout=timeout,
        )
    )


# Export public API
__all__ = [
    "convert_plan",
    "convert_plan_async",
    "validate_plan_content",
    "ConversionError",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT",
    "DEFAULT_MAX_MILESTONES",
    # Internal functions exposed for testing
    "_build_prompt",
    "_strip_outer_code_fences",
    "_extract_feature",
]
