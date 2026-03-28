"""Tests for Plan-2 additions to sdk_wrapper.query_claude():
effort, thinking, and max_turns parameters — all SDK calls are mocked."""

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

import claude_agent_sdk
from planner_auto.sdk_wrapper import query_claude


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_exec_success(text="OK response"):
    """Return a mock _execute_query that succeeds with *text*."""
    mock = AsyncMock(return_value=(text, {"input_tokens": 10, "output_tokens": 5}))
    return mock


# ---------------------------------------------------------------------------
# effort parameter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEffortParameter:
    @patch("planner_auto.sdk_wrapper._execute_query")
    async def test_effort_is_passed_to_options(self, mock_exec):
        """When effort='high', ClaudeAgentOptions must receive effort='high'."""
        mock_exec.side_effect = _mock_exec_success()

        await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            effort="high",
        )

        opts = mock_exec.call_args[0][1]  # positional arg 1 = options
        assert opts.effort == "high"

    @patch("planner_auto.sdk_wrapper._execute_query")
    async def test_no_effort_leaves_none(self, mock_exec):
        """When effort is not provided, options.effort must be None."""
        mock_exec.side_effect = _mock_exec_success()

        await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
        )

        opts = mock_exec.call_args[0][1]
        assert opts.effort is None

    @patch("planner_auto.sdk_wrapper._execute_query")
    async def test_effort_low(self, mock_exec):
        mock_exec.side_effect = _mock_exec_success()

        await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            effort="low",
        )

        opts = mock_exec.call_args[0][1]
        assert opts.effort == "low"


# ---------------------------------------------------------------------------
# thinking parameter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestThinkingParameter:
    @patch("planner_auto.sdk_wrapper._execute_query")
    async def test_thinking_true_sets_adaptive_config(self, mock_exec):
        """thinking=True must set ThinkingConfigAdaptive(type='adaptive')."""
        mock_exec.side_effect = _mock_exec_success()

        await query_claude(
            messages=[{"role": "user", "content": "Think hard"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            thinking=True,
        )

        opts = mock_exec.call_args[0][1]
        assert opts.thinking is not None
        assert opts.thinking.get("type") == "adaptive"

    @patch("planner_auto.sdk_wrapper._execute_query")
    async def test_thinking_false_leaves_none(self, mock_exec):
        """thinking=False (default) must leave options.thinking=None."""
        mock_exec.side_effect = _mock_exec_success()

        await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            thinking=False,
        )

        opts = mock_exec.call_args[0][1]
        assert opts.thinking is None

    @patch("planner_auto.sdk_wrapper._execute_query")
    async def test_thinking_true_sets_unlimited_max_turns(self, mock_exec):
        """When thinking=True and max_turns not given, max_turns must be None (unlimited)."""
        mock_exec.side_effect = _mock_exec_success()

        await query_claude(
            messages=[{"role": "user", "content": "Think"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            thinking=True,
        )

        opts = mock_exec.call_args[0][1]
        assert opts.max_turns is None


# ---------------------------------------------------------------------------
# max_turns parameter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMaxTurnsParameter:
    @patch("planner_auto.sdk_wrapper._execute_query")
    async def test_default_max_turns_is_1(self, mock_exec):
        """Default (no max_turns, no thinking) must use max_turns=1."""
        mock_exec.side_effect = _mock_exec_success()

        await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
        )

        opts = mock_exec.call_args[0][1]
        assert opts.max_turns == 1

    @patch("planner_auto.sdk_wrapper._execute_query")
    async def test_max_turns_positive_overrides_default(self, mock_exec):
        """max_turns=5 must be forwarded to options."""
        mock_exec.side_effect = _mock_exec_success()

        await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            max_turns=5,
        )

        opts = mock_exec.call_args[0][1]
        assert opts.max_turns == 5

    @patch("planner_auto.sdk_wrapper._execute_query")
    async def test_max_turns_zero_means_unlimited(self, mock_exec):
        """max_turns=0 must result in options.max_turns=None (unlimited)."""
        mock_exec.side_effect = _mock_exec_success()

        await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            max_turns=0,
        )

        opts = mock_exec.call_args[0][1]
        assert opts.max_turns is None

    @patch("planner_auto.sdk_wrapper._execute_query")
    async def test_max_turns_with_thinking_and_explicit_value(self, mock_exec):
        """Explicit positive max_turns takes precedence even with thinking=True."""
        mock_exec.side_effect = _mock_exec_success()

        await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            thinking=True,
            max_turns=3,
        )

        opts = mock_exec.call_args[0][1]
        assert opts.max_turns == 3
