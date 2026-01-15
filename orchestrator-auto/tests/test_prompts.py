"""
Unit tests for system prompts.
"""

import pytest
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto.prompts import (
    EXECUTOR_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    DEFAULT_CHAT_PROMPT,
)


class TestExecutorPrompt:
    """Test executor system prompt content."""

    def test_executor_prompt_contains_mcp_safety(self):
        """Test that executor prompt includes MCP Playwright safety rules."""
        assert "MCP Playwright Safety Rules" in EXECUTOR_SYSTEM_PROMPT

    def test_executor_prompt_warns_browser_snapshot(self):
        """Test that executor prompt warns against browser_snapshot on complex pages."""
        assert "browser_snapshot" in EXECUTOR_SYSTEM_PROMPT
        assert "NEVER use" in EXECUTOR_SYSTEM_PROMPT
        assert "Dashboards" in EXECUTOR_SYSTEM_PROMPT or "dashboards" in EXECUTOR_SYSTEM_PROMPT

    def test_executor_prompt_recommends_screenshot(self):
        """Test that executor prompt recommends browser_take_screenshot."""
        assert "browser_take_screenshot" in EXECUTOR_SYSTEM_PROMPT
        assert "SAFE" in EXECUTOR_SYSTEM_PROMPT or "safer" in EXECUTOR_SYSTEM_PROMPT.lower()

    def test_executor_prompt_has_recovery_guidance(self):
        """Test that executor prompt includes recovery guidance for crashes."""
        prompt_lower = EXECUTOR_SYSTEM_PROMPT.lower()
        assert "buffer" in prompt_lower or "response too large" in prompt_lower

    def test_executor_prompt_has_milestone_rules(self):
        """Test that executor prompt has core milestone rules."""
        assert "ONE MILESTONE ONLY" in EXECUTOR_SYSTEM_PROMPT
        assert "PROGRESS_REPORT" in EXECUTOR_SYSTEM_PROMPT

    def test_executor_prompt_has_response_tags(self):
        """Test that executor prompt defines response format tags."""
        assert "[PROGRESS_REPORT]" in EXECUTOR_SYSTEM_PROMPT
        assert "[BLOCKED]" in EXECUTOR_SYSTEM_PROMPT
        assert "[CLARIFICATION_NEEDED]" in EXECUTOR_SYSTEM_PROMPT


class TestPlannerPrompt:
    """Test planner system prompt content."""

    def test_planner_prompt_has_phases(self):
        """Test that planner prompt defines all phases."""
        assert "Discovery" in PLANNER_SYSTEM_PROMPT
        assert "Planning" in PLANNER_SYSTEM_PROMPT
        assert "Review" in PLANNER_SYSTEM_PROMPT or "Execution" in PLANNER_SYSTEM_PROMPT

    def test_planner_prompt_has_response_tags(self):
        """Test that planner prompt defines response format tags."""
        assert "[MILESTONE_APPROVED]" in PLANNER_SYSTEM_PROMPT
        assert "[CHANGES_REQUESTED]" in PLANNER_SYSTEM_PROMPT
        assert "[PLAN_READY]" in PLANNER_SYSTEM_PROMPT


class TestChatPrompt:
    """Test default chat prompt content."""

    def test_chat_prompt_is_concise(self):
        """Test that chat prompt is reasonably short."""
        # Should be a brief prompt for direct chat mode
        assert len(DEFAULT_CHAT_PROMPT) < 1000

    def test_chat_prompt_mentions_tools(self):
        """Test that chat prompt mentions available tools."""
        prompt_lower = DEFAULT_CHAT_PROMPT.lower()
        assert "bash" in prompt_lower or "commands" in prompt_lower
        assert "files" in prompt_lower or "read" in prompt_lower
