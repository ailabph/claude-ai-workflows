"""Tests for planner_auto.sdk_wrapper — all SDK calls are mocked."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from planner_auto.errors import (
    SDKAuthError,
    SDKRateLimitError,
    SDKResponseError,
    SDKTimeoutError,
)
from planner_auto.sdk_wrapper import query_claude, _execute_query, _build_prompt


# Helper to create a fake async iterator of messages
def _make_result_message(text: str):
    """Create a mock ResultMessage with a TextBlock."""
    block = MagicMock()
    block.text = text
    # Make it pass isinstance checks
    block.__class__ = MagicMock()

    msg = MagicMock()
    msg.content = [block]
    return msg, block


async def _fake_query_success(**kwargs):
    """Fake SDK query that yields a ResultMessage with text."""
    block = MagicMock()
    block.text = "Hello from Claude"
    # We need to make isinstance checks work, so we patch at call site
    msg = MagicMock()
    msg.content = [block]
    yield msg


@pytest.mark.asyncio
class TestQueryClaude:
    """Tests for query_claude()."""

    @patch("planner_auto.sdk_wrapper._execute_query")
    async def test_successful_call(self, mock_exec):
        mock_exec.return_value = "Hello from Claude"
        result = await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="You are helpful.",
            model="claude-sonnet-4-6",
        )
        assert result == "Hello from Claude"
        mock_exec.assert_called_once()

    @patch("planner_auto.sdk_wrapper._execute_query")
    async def test_auth_error_no_retry(self, mock_exec):
        """Auth errors should propagate immediately without retry."""
        mock_exec.side_effect = SDKAuthError("Invalid API key")
        with pytest.raises(SDKAuthError, match="Invalid API key"):
            await query_claude(
                messages=[{"role": "user", "content": "Hi"}],
                system_prompt="test",
                model="claude-sonnet-4-6",
            )
        # Should only be called once — no retry
        assert mock_exec.call_count == 1

    @patch("planner_auto.sdk_wrapper._execute_query")
    @patch("planner_auto.sdk_wrapper.asyncio.sleep", new_callable=AsyncMock)
    async def test_rate_limit_retries_with_backoff(self, mock_sleep, mock_exec):
        """Rate limit should retry 3 times with exponential backoff, then raise."""
        mock_exec.side_effect = SDKRateLimitError("Rate limited")
        with pytest.raises(SDKRateLimitError):
            await query_claude(
                messages=[{"role": "user", "content": "Hi"}],
                system_prompt="test",
                model="claude-sonnet-4-6",
            )
        # 1 initial + 3 retries = 4 attempts
        assert mock_exec.call_count == 4
        # Check backoff delays: 2, 4, 8
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_calls == [2, 4, 8]

    @patch("planner_auto.sdk_wrapper._execute_query")
    @patch("planner_auto.sdk_wrapper.asyncio.sleep", new_callable=AsyncMock)
    async def test_timeout_retries_once(self, mock_sleep, mock_exec):
        """Timeout/connection errors should retry once after 2s."""
        mock_exec.side_effect = SDKTimeoutError("Timed out")
        with pytest.raises(SDKTimeoutError):
            await query_claude(
                messages=[{"role": "user", "content": "Hi"}],
                system_prompt="test",
                model="claude-sonnet-4-6",
            )
        # 1 initial + 1 retry = 2 attempts
        assert mock_exec.call_count == 2
        mock_sleep.assert_called_with(2)

    @patch("planner_auto.sdk_wrapper._execute_query")
    async def test_empty_response_error(self, mock_exec):
        """Empty response should raise SDKResponseError."""
        mock_exec.return_value = ""
        with pytest.raises(SDKResponseError, match="Empty response"):
            await query_claude(
                messages=[{"role": "user", "content": "Hi"}],
                system_prompt="test",
                model="claude-sonnet-4-6",
            )

    @patch("planner_auto.sdk_wrapper._execute_query")
    async def test_whitespace_only_response_error(self, mock_exec):
        """Whitespace-only response should raise SDKResponseError."""
        mock_exec.return_value = "   \n  "
        with pytest.raises(SDKResponseError, match="Empty response"):
            await query_claude(
                messages=[{"role": "user", "content": "Hi"}],
                system_prompt="test",
                model="claude-sonnet-4-6",
            )


class TestBuildPrompt:
    """Tests for _build_prompt helper."""

    def test_single_message(self):
        result = _build_prompt([{"role": "user", "content": "Hello"}])
        assert result == "Hello"

    def test_multiple_messages(self):
        msgs = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "How are you?"},
        ]
        result = _build_prompt(msgs)
        assert "Previous conversation" in result
        assert "[User]: Hi" in result
        assert "[Assistant]: Hello!" in result
        assert "How are you?" in result

    def test_empty_messages(self):
        assert _build_prompt([]) == ""
