"""Tests for the direct Anthropic API backend in sdk_wrapper.

All API calls are mocked — no API keys needed.
Tests cover: backend dispatch, resolve_default_backend, error mapping,
thinking fallback, empty response, effort-to-thinking mapping, retry logic.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from planner_auto.errors import (
    SDKAuthError,
    SDKRateLimitError,
    SDKResponseError,
    SDKTimeoutError,
)
from planner_auto.sdk_wrapper import (
    _EFFORT_THINKING_MAP,
    _execute_direct,
    _execute_direct_with_timeout,
    query_claude,
    resolve_default_backend,
)


# ---------------------------------------------------------------------------
# resolve_default_backend
# ---------------------------------------------------------------------------

class TestResolveDefaultBackend:
    def test_api_key_returns_direct(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
            os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
            assert resolve_default_backend() == "direct"

    def test_oauth_only_returns_sdk(self):
        with patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "tok"}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            assert resolve_default_backend() == "sdk"

    def test_both_returns_direct(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test", "CLAUDE_CODE_OAUTH_TOKEN": "tok"}):
            assert resolve_default_backend() == "direct"

    def test_neither_returns_direct(self):
        with patch.dict(os.environ, {}, clear=True):
            assert resolve_default_backend() == "direct"


# ---------------------------------------------------------------------------
# Backend dispatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestBackendDispatch:
    @patch("planner_auto.sdk_wrapper._execute_direct_with_timeout")
    async def test_backend_direct_dispatches_to_direct(self, mock_direct):
        mock_direct.return_value = ("response", {"input_tokens": 5, "output_tokens": 3})
        result = await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            backend="direct",
        )
        assert result == "response"
        mock_direct.assert_called_once()

    @patch("planner_auto.sdk_wrapper._execute_sdk_with_timeout")
    async def test_backend_sdk_dispatches_to_sdk(self, mock_sdk):
        mock_sdk.return_value = ("response", {"input_tokens": 5, "output_tokens": 3})
        result = await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            backend="sdk",
        )
        assert result == "response"
        mock_sdk.assert_called_once()

    @patch("planner_auto.sdk_wrapper.resolve_default_backend", return_value="direct")
    @patch("planner_auto.sdk_wrapper._execute_direct_with_timeout")
    async def test_backend_none_uses_default(self, mock_direct, mock_resolve):
        mock_direct.return_value = ("response", {"input_tokens": 5, "output_tokens": 3})
        result = await query_claude(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="sys",
            model="claude-sonnet-4-6",
            backend=None,
        )
        assert result == "response"
        mock_resolve.assert_called_once()
        mock_direct.assert_called_once()


# ---------------------------------------------------------------------------
# Error mapping (_execute_direct)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDirectErrorMapping:
    """Verify that anthropic exceptions are mapped to SDKError subclasses."""

    @patch("planner_auto.sdk_wrapper.anthropic")
    async def test_auth_error_maps_to_sdk_auth(self, mock_anthropic_mod):
        import anthropic
        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=anthropic.AuthenticationError(
            message="invalid key",
            response=MagicMock(status_code=401),
            body=None,
        ))
        mock_anthropic_mod.AsyncAnthropic.return_value = client
        mock_anthropic_mod.AuthenticationError = anthropic.AuthenticationError
        mock_anthropic_mod.RateLimitError = anthropic.RateLimitError
        mock_anthropic_mod.APITimeoutError = anthropic.APITimeoutError
        mock_anthropic_mod.APIConnectionError = anthropic.APIConnectionError
        mock_anthropic_mod.BadRequestError = anthropic.BadRequestError
        mock_anthropic_mod.APIError = anthropic.APIError

        with pytest.raises(SDKAuthError, match="Invalid API key"):
            await _execute_direct("hello", "sys", "model")

    @patch("planner_auto.sdk_wrapper.anthropic")
    async def test_rate_limit_maps_to_sdk_rate_limit(self, mock_anthropic_mod):
        import anthropic
        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=anthropic.RateLimitError(
            message="too many",
            response=MagicMock(status_code=429),
            body=None,
        ))
        mock_anthropic_mod.AsyncAnthropic.return_value = client
        mock_anthropic_mod.AuthenticationError = anthropic.AuthenticationError
        mock_anthropic_mod.RateLimitError = anthropic.RateLimitError
        mock_anthropic_mod.APITimeoutError = anthropic.APITimeoutError
        mock_anthropic_mod.APIConnectionError = anthropic.APIConnectionError
        mock_anthropic_mod.BadRequestError = anthropic.BadRequestError
        mock_anthropic_mod.APIError = anthropic.APIError

        with pytest.raises(SDKRateLimitError, match="Rate limited"):
            await _execute_direct("hello", "sys", "model")

    @patch("planner_auto.sdk_wrapper.anthropic")
    async def test_timeout_maps_to_sdk_timeout(self, mock_anthropic_mod):
        import anthropic
        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=anthropic.APITimeoutError(
            request=MagicMock(),
        ))
        mock_anthropic_mod.AsyncAnthropic.return_value = client
        mock_anthropic_mod.AuthenticationError = anthropic.AuthenticationError
        mock_anthropic_mod.RateLimitError = anthropic.RateLimitError
        mock_anthropic_mod.APITimeoutError = anthropic.APITimeoutError
        mock_anthropic_mod.APIConnectionError = anthropic.APIConnectionError
        mock_anthropic_mod.BadRequestError = anthropic.BadRequestError
        mock_anthropic_mod.APIError = anthropic.APIError

        with pytest.raises(SDKTimeoutError, match="Connection error"):
            await _execute_direct("hello", "sys", "model")

    @patch("planner_auto.sdk_wrapper.anthropic")
    async def test_connection_error_maps_to_sdk_timeout(self, mock_anthropic_mod):
        import anthropic
        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=anthropic.APIConnectionError(
            request=MagicMock(),
        ))
        mock_anthropic_mod.AsyncAnthropic.return_value = client
        mock_anthropic_mod.AuthenticationError = anthropic.AuthenticationError
        mock_anthropic_mod.RateLimitError = anthropic.RateLimitError
        mock_anthropic_mod.APITimeoutError = anthropic.APITimeoutError
        mock_anthropic_mod.APIConnectionError = anthropic.APIConnectionError
        mock_anthropic_mod.BadRequestError = anthropic.BadRequestError
        mock_anthropic_mod.APIError = anthropic.APIError

        with pytest.raises(SDKTimeoutError, match="Connection error"):
            await _execute_direct("hello", "sys", "model")

    @patch("planner_auto.sdk_wrapper.anthropic")
    async def test_bad_request_non_thinking_maps_to_sdk_response(self, mock_anthropic_mod):
        import anthropic
        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=anthropic.BadRequestError(
            message="invalid parameter",
            response=MagicMock(status_code=400),
            body=None,
        ))
        mock_anthropic_mod.AsyncAnthropic.return_value = client
        mock_anthropic_mod.AuthenticationError = anthropic.AuthenticationError
        mock_anthropic_mod.RateLimitError = anthropic.RateLimitError
        mock_anthropic_mod.APITimeoutError = anthropic.APITimeoutError
        mock_anthropic_mod.APIConnectionError = anthropic.APIConnectionError
        mock_anthropic_mod.BadRequestError = anthropic.BadRequestError
        mock_anthropic_mod.APIError = anthropic.APIError

        with pytest.raises(SDKResponseError, match="Bad request"):
            await _execute_direct("hello", "sys", "model")

    @patch("planner_auto.sdk_wrapper.anthropic")
    async def test_generic_api_error_maps_to_sdk_response(self, mock_anthropic_mod):
        import anthropic
        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=anthropic.APIError(
            message="server error",
            request=MagicMock(),
            body=None,
        ))
        mock_anthropic_mod.AsyncAnthropic.return_value = client
        mock_anthropic_mod.AuthenticationError = anthropic.AuthenticationError
        mock_anthropic_mod.RateLimitError = anthropic.RateLimitError
        mock_anthropic_mod.APITimeoutError = anthropic.APITimeoutError
        mock_anthropic_mod.APIConnectionError = anthropic.APIConnectionError
        mock_anthropic_mod.BadRequestError = anthropic.BadRequestError
        mock_anthropic_mod.APIError = anthropic.APIError

        with pytest.raises(SDKResponseError, match="API error"):
            await _execute_direct("hello", "sys", "model")


# ---------------------------------------------------------------------------
# Thinking fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestThinkingFallback:
    @patch("planner_auto.sdk_wrapper.anthropic")
    async def test_thinking_error_falls_back_to_non_thinking(self, mock_anthropic_mod):
        """When thinking raises BadRequestError with 'thinking' in message, retry without it."""
        import anthropic

        # First call with thinking fails, second without thinking succeeds
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "fallback response"

        usage = MagicMock()
        usage.input_tokens = 10
        usage.output_tokens = 20

        success_response = MagicMock()
        success_response.content = [text_block]
        success_response.usage = usage

        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=[
            anthropic.BadRequestError(
                message="thinking is not supported for this model",
                response=MagicMock(status_code=400),
                body=None,
            ),
            success_response,
        ])

        mock_anthropic_mod.AsyncAnthropic.return_value = client
        mock_anthropic_mod.AuthenticationError = anthropic.AuthenticationError
        mock_anthropic_mod.RateLimitError = anthropic.RateLimitError
        mock_anthropic_mod.APITimeoutError = anthropic.APITimeoutError
        mock_anthropic_mod.APIConnectionError = anthropic.APIConnectionError
        mock_anthropic_mod.BadRequestError = anthropic.BadRequestError
        mock_anthropic_mod.APIError = anthropic.APIError

        text, usage_info = await _execute_direct(
            "hello", "sys", "model", thinking=True, thinking_budget=10000
        )
        assert text == "fallback response"
        assert usage_info["input_tokens"] == 10

        # Verify it was called twice (first with thinking, second without)
        assert client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Empty response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEmptyResponse:
    @patch("planner_auto.sdk_wrapper._execute_direct_with_timeout")
    async def test_empty_response_raises_sdk_response_error(self, mock_direct):
        mock_direct.return_value = ("", {})
        with pytest.raises(SDKResponseError, match="Empty response"):
            await query_claude(
                messages=[{"role": "user", "content": "Hi"}],
                system_prompt="sys",
                model="claude-sonnet-4-6",
                backend="direct",
            )

    @patch("planner_auto.sdk_wrapper._execute_direct_with_timeout")
    async def test_whitespace_response_raises_sdk_response_error(self, mock_direct):
        mock_direct.return_value = ("  \n  ", {})
        with pytest.raises(SDKResponseError, match="Empty response"):
            await query_claude(
                messages=[{"role": "user", "content": "Hi"}],
                system_prompt="sys",
                model="claude-sonnet-4-6",
                backend="direct",
            )


# ---------------------------------------------------------------------------
# Effort-to-thinking mapping
# ---------------------------------------------------------------------------

class TestEffortToThinkingMap:
    def test_none_effort_no_thinking(self):
        cfg = _EFFORT_THINKING_MAP[None]
        assert cfg["thinking"] is False
        assert cfg["max_tokens"] == 16384

    def test_low_effort_no_thinking(self):
        cfg = _EFFORT_THINKING_MAP["low"]
        assert cfg["thinking"] is False
        assert cfg["max_tokens"] == 8192

    def test_medium_effort_thinking(self):
        cfg = _EFFORT_THINKING_MAP["medium"]
        assert cfg["thinking"] is True
        assert cfg["budget_tokens"] == 10000

    def test_high_effort_thinking(self):
        cfg = _EFFORT_THINKING_MAP["high"]
        assert cfg["thinking"] is True
        assert cfg["budget_tokens"] == 20000

    def test_max_effort_thinking(self):
        cfg = _EFFORT_THINKING_MAP["max"]
        assert cfg["thinking"] is True
        assert cfg["budget_tokens"] == 50000
        assert cfg["max_tokens"] == 32768


# ---------------------------------------------------------------------------
# Retry logic (shared for both backends)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRetryLogic:
    @patch("planner_auto.sdk_wrapper._execute_direct_with_timeout")
    @patch("planner_auto.sdk_wrapper.asyncio.sleep", new_callable=AsyncMock)
    async def test_rate_limit_retries_3x_then_raises(self, mock_sleep, mock_exec):
        mock_exec.side_effect = SDKRateLimitError("rate limited")
        with pytest.raises(SDKRateLimitError):
            await query_claude(
                messages=[{"role": "user", "content": "Hi"}],
                system_prompt="sys",
                model="test",
                backend="direct",
            )
        assert mock_exec.call_count == 4  # 1 + 3 retries
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_calls == [2, 4, 8]

    @patch("planner_auto.sdk_wrapper._execute_direct_with_timeout")
    @patch("planner_auto.sdk_wrapper.asyncio.sleep", new_callable=AsyncMock)
    async def test_timeout_retries_1x_then_raises(self, mock_sleep, mock_exec):
        mock_exec.side_effect = SDKTimeoutError("timeout")
        with pytest.raises(SDKTimeoutError):
            await query_claude(
                messages=[{"role": "user", "content": "Hi"}],
                system_prompt="sys",
                model="test",
                backend="direct",
            )
        assert mock_exec.call_count == 2  # 1 + 1 retry
        mock_sleep.assert_called_with(2)

    @patch("planner_auto.sdk_wrapper._execute_direct_with_timeout")
    async def test_auth_error_not_retried(self, mock_exec):
        mock_exec.side_effect = SDKAuthError("bad key")
        with pytest.raises(SDKAuthError):
            await query_claude(
                messages=[{"role": "user", "content": "Hi"}],
                system_prompt="sys",
                model="test",
                backend="direct",
            )
        assert mock_exec.call_count == 1
