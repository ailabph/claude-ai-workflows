"""Tests for Plan-2 additions to sdk_wrapper.query_claude():
effort, thinking, and max_turns parameters — all backend calls are mocked.

These tests verify that parameters are forwarded correctly to the SDK backend
via _execute_sdk_with_timeout, and to the direct backend via
_execute_direct_with_timeout.
"""

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from planner_auto.sdk_wrapper import query_claude


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_exec_success(text="OK response"):
    """Return a mock async callable that succeeds with *text*."""
    return AsyncMock(return_value=(text, {"input_tokens": 10, "output_tokens": 5}))


# ---------------------------------------------------------------------------
# effort parameter (SDK backend)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEffortParameterSDK:
    @patch("planner_auto.sdk_wrapper._execute_sdk_with_timeout")
    async def test_effort_is_passed_to_sdk(self, mock_exec):
        """When effort='high' and backend='sdk', it must be forwarded."""
        mock_exec.return_value = ("OK response", {"input_tokens": 10, "output_tokens": 5})

        await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            effort="high",
            backend="sdk",
        )

        call_kwargs = mock_exec.call_args.kwargs
        assert call_kwargs.get("effort") == "high"

    @patch("planner_auto.sdk_wrapper._execute_sdk_with_timeout")
    async def test_no_effort_leaves_none(self, mock_exec):
        """When effort is not provided, sdk backend receives None."""
        mock_exec.return_value = ("OK response", {"input_tokens": 10, "output_tokens": 5})

        await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            backend="sdk",
        )

        call_kwargs = mock_exec.call_args.kwargs
        assert call_kwargs.get("effort") is None


# ---------------------------------------------------------------------------
# thinking parameter (SDK backend)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestThinkingParameterSDK:
    @patch("planner_auto.sdk_wrapper._execute_sdk_with_timeout")
    async def test_thinking_true_forwarded_to_sdk(self, mock_exec):
        """thinking=True must be forwarded to SDK backend."""
        mock_exec.return_value = ("OK response", {"input_tokens": 10, "output_tokens": 5})

        await query_claude(
            messages=[{"role": "user", "content": "Think hard"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            thinking=True,
            backend="sdk",
        )

        call_kwargs = mock_exec.call_args.kwargs
        assert call_kwargs.get("thinking") is True

    @patch("planner_auto.sdk_wrapper._execute_sdk_with_timeout")
    async def test_thinking_false_leaves_false(self, mock_exec):
        """thinking=False (default) must be forwarded as False."""
        mock_exec.return_value = ("OK response", {"input_tokens": 10, "output_tokens": 5})

        await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            thinking=False,
            backend="sdk",
        )

        call_kwargs = mock_exec.call_args.kwargs
        assert call_kwargs.get("thinking") is False


# ---------------------------------------------------------------------------
# max_turns parameter (SDK backend)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMaxTurnsParameterSDK:
    @patch("planner_auto.sdk_wrapper._execute_sdk_with_timeout")
    async def test_max_turns_forwarded(self, mock_exec):
        """max_turns=5 must be forwarded to SDK backend."""
        mock_exec.return_value = ("OK response", {"input_tokens": 10, "output_tokens": 5})

        await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            max_turns=5,
            backend="sdk",
        )

        call_kwargs = mock_exec.call_args.kwargs
        assert call_kwargs.get("max_turns") == 5

    @patch("planner_auto.sdk_wrapper._execute_sdk_with_timeout")
    async def test_max_turns_zero_forwarded(self, mock_exec):
        """max_turns=0 must be forwarded to SDK backend."""
        mock_exec.return_value = ("OK response", {"input_tokens": 10, "output_tokens": 5})

        await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            max_turns=0,
            backend="sdk",
        )

        call_kwargs = mock_exec.call_args.kwargs
        assert call_kwargs.get("max_turns") == 0


# ---------------------------------------------------------------------------
# Backend dispatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestBackendDispatch:
    @patch("planner_auto.sdk_wrapper._execute_direct_with_timeout")
    async def test_direct_backend_called(self, mock_direct):
        """backend='direct' routes to _execute_direct_with_timeout."""
        mock_direct.return_value = ("OK", {"input_tokens": 5, "output_tokens": 3})

        result = await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            backend="direct",
        )
        assert result == "OK"
        mock_direct.assert_called_once()

    @patch("planner_auto.sdk_wrapper._execute_sdk_with_timeout")
    async def test_sdk_backend_called(self, mock_sdk):
        """backend='sdk' routes to _execute_sdk_with_timeout."""
        mock_sdk.return_value = ("OK", {"input_tokens": 5, "output_tokens": 3})

        result = await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            backend="sdk",
        )
        assert result == "OK"
        mock_sdk.assert_called_once()
