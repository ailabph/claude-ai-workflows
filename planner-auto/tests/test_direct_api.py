"""Tests for planner_auto.reviewer.direct_api.DirectAPIAdapter.

All OpenAI API calls are mocked — no network access required.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from planner_auto.errors import (
    ReviewerAuthError,
    ReviewerRateLimitError,
    ReviewerResponseError,
    ReviewerTimeoutError,
)
from planner_auto.reviewer.contract import ReviewerResponse, Severity, Verdict
from planner_auto.reviewer.direct_api import DirectAPIAdapter


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_response(content: str, prompt_tokens: int = 100, completion_tokens: int = 50):
    """Build a mock OpenAI ChatCompletion response."""
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    message = MagicMock()
    message.content = content

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    response.model = "gpt-5.4"
    return response


def _go_json() -> str:
    return json.dumps({"verdict": "GO", "issues": [], "summary": "Looks good."})


def _nogo_json(issues: list[dict] | None = None) -> str:
    return json.dumps({
        "verdict": "NO_GO",
        "issues": issues or [
            {"severity": "critical", "description": "Missing error handling", "rationale": "R"}
        ],
        "summary": "Needs work.",
    })


def _make_adapter(**kwargs) -> tuple[DirectAPIAdapter, AsyncMock]:
    """Return an adapter with a fully mocked OpenAI client.

    Injects a mock client via the ``_client`` constructor parameter so that
    no ``OPENAI_API_KEY`` is needed and no real HTTP calls are made.
    """
    mock_create = AsyncMock()
    mock_completions = MagicMock()
    mock_completions.create = mock_create
    mock_chat = MagicMock()
    mock_chat.completions = mock_completions
    mock_client = MagicMock()
    mock_client.chat = mock_chat

    adapter = DirectAPIAdapter(_client=mock_client, **kwargs)
    return adapter, mock_create


# ---------------------------------------------------------------------------
# 1. Successful GO response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSuccessfulGoResponse:
    async def test_go_verdict_returned(self):
        adapter, mock_create = _make_adapter()
        mock_create.return_value = _make_response(_go_json())

        result = await adapter.review("# My Plan\nMilestone 1: ...")
        assert result.verdict == Verdict.GO
        assert result.issues == []

    async def test_go_summary_populated(self):
        adapter, mock_create = _make_adapter()
        mock_create.return_value = _make_response(
            json.dumps({"verdict": "GO", "issues": [], "summary": "All systems go."})
        )
        result = await adapter.review("plan text")
        assert result.summary == "All systems go."


# ---------------------------------------------------------------------------
# 2. Successful NO_GO response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSuccessfulNoGoResponse:
    async def test_nogo_verdict_returned(self):
        adapter, mock_create = _make_adapter()
        mock_create.return_value = _make_response(_nogo_json())

        result = await adapter.review("# My Plan")
        assert result.verdict == Verdict.NO_GO

    async def test_nogo_issues_populated(self):
        adapter, mock_create = _make_adapter()
        mock_create.return_value = _make_response(
            _nogo_json([
                {"severity": "critical", "description": "No auth", "rationale": "R"},
                {"severity": "major", "description": "No pagination", "rationale": "R"},
            ])
        )
        result = await adapter.review("plan")
        assert len(result.issues) == 2
        assert result.issues[0].severity == Severity.CRITICAL


# ---------------------------------------------------------------------------
# 3. Authentication error — no retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAuthError:
    async def test_auth_error_raises_reviewer_auth_error(self):
        adapter, mock_create = _make_adapter()
        mock_create.side_effect = openai.AuthenticationError(
            "Invalid API key",
            response=MagicMock(status_code=401),
            body=None,
        )
        with pytest.raises(ReviewerAuthError, match="authentication"):
            await adapter.review("plan")

    async def test_auth_error_does_not_retry(self):
        adapter, mock_create = _make_adapter()
        mock_create.side_effect = openai.AuthenticationError(
            "Invalid API key",
            response=MagicMock(status_code=401),
            body=None,
        )
        with pytest.raises(ReviewerAuthError):
            await adapter.review("plan")
        # Only one attempt — no retries on auth errors.
        assert mock_create.call_count == 1


# ---------------------------------------------------------------------------
# 4. Rate limit exhaustion — retries 3×
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRateLimitRetry:
    @patch("planner_auto.reviewer.direct_api.asyncio.sleep", new_callable=AsyncMock)
    async def test_rate_limit_retries_three_times(self, mock_sleep):
        adapter, mock_create = _make_adapter()
        mock_create.side_effect = openai.RateLimitError(
            "rate limited",
            response=MagicMock(status_code=429),
            body=None,
        )
        with pytest.raises(ReviewerRateLimitError):
            await adapter.review("plan")
        # 1 initial + 3 retries = 4 attempts
        assert mock_create.call_count == 4

    @patch("planner_auto.reviewer.direct_api.asyncio.sleep", new_callable=AsyncMock)
    async def test_rate_limit_backoff_delays(self, mock_sleep):
        adapter, mock_create = _make_adapter()
        mock_create.side_effect = openai.RateLimitError(
            "rate limited",
            response=MagicMock(status_code=429),
            body=None,
        )
        with pytest.raises(ReviewerRateLimitError):
            await adapter.review("plan")
        sleep_delays = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_delays == [2, 4, 8]

    @patch("planner_auto.reviewer.direct_api.asyncio.sleep", new_callable=AsyncMock)
    async def test_rate_limit_succeeds_on_retry(self, mock_sleep):
        """If rate limit clears on the 3rd attempt, succeed."""
        adapter, mock_create = _make_adapter()
        rate_exc = openai.RateLimitError(
            "rate limited", response=MagicMock(status_code=429), body=None
        )
        mock_create.side_effect = [
            rate_exc,
            rate_exc,
            _make_response(_go_json()),
        ]
        result = await adapter.review("plan")
        assert result.verdict == Verdict.GO
        assert mock_create.call_count == 3


# ---------------------------------------------------------------------------
# 5. Timeout — retry once
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestTimeoutRetry:
    @patch("planner_auto.reviewer.direct_api.asyncio.sleep", new_callable=AsyncMock)
    async def test_timeout_retries_once(self, mock_sleep):
        adapter, mock_create = _make_adapter()
        mock_create.side_effect = openai.APITimeoutError(request=MagicMock())
        with pytest.raises(ReviewerTimeoutError):
            await adapter.review("plan")
        # 1 initial + 1 retry = 2 attempts
        assert mock_create.call_count == 2
        mock_sleep.assert_called_once_with(2)

    @patch("planner_auto.reviewer.direct_api.asyncio.sleep", new_callable=AsyncMock)
    async def test_timeout_succeeds_on_retry(self, mock_sleep):
        adapter, mock_create = _make_adapter()
        mock_create.side_effect = [
            openai.APITimeoutError(request=MagicMock()),
            _make_response(_go_json()),
        ]
        result = await adapter.review("plan")
        assert result.verdict == Verdict.GO
        assert mock_create.call_count == 2


# ---------------------------------------------------------------------------
# 6. Parse failure — unparseable response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestParseFailure:
    async def test_unparseable_response_returns_nogo_parse_failure(self):
        adapter, mock_create = _make_adapter()
        mock_create.return_value = _make_response("!@#$ garbage that cannot be parsed")
        result = await adapter.review("plan")
        # parse_reviewer_response() falls back to NO_GO with critical parse-failure issue
        assert result.verdict == Verdict.NO_GO
        assert result.issues[0].description == "Reviewer output could not be parsed"

    async def test_empty_content_returns_nogo(self):
        adapter, mock_create = _make_adapter()
        mock_create.return_value = _make_response("")
        result = await adapter.review("plan")
        assert result.verdict == Verdict.NO_GO


# ---------------------------------------------------------------------------
# 7. previous_context in user prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPreviousContext:
    async def test_previous_context_prepended_to_user_message(self):
        adapter, mock_create = _make_adapter()
        mock_create.return_value = _make_response(_go_json())

        await adapter.review("# Plan\nContent", previous_context="Round 1: NO_GO issued")

        # Inspect the messages argument passed to create()
        call_args = mock_create.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        user_content = next(m["content"] for m in messages if m["role"] == "user")

        assert "Round 1: NO_GO issued" in user_content
        assert "DEFERRED" in user_content
        assert "# Plan" in user_content

    async def test_no_previous_context_sends_plain_prompt(self):
        adapter, mock_create = _make_adapter()
        mock_create.return_value = _make_response(_go_json())

        await adapter.review("# Plan\nContent", previous_context=None)

        call_args = mock_create.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        user_content = next(m["content"] for m in messages if m["role"] == "user")

        # No history header should appear.
        assert "Review History Context" not in user_content
        assert "# Plan" in user_content


# ---------------------------------------------------------------------------
# 8. reasoning_effort disables temperature
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestReasoningEffort:
    async def test_reasoning_effort_included_in_api_call(self):
        adapter, mock_create = _make_adapter(reasoning_effort="high")
        mock_create.return_value = _make_response(_go_json())

        await adapter.review("plan")

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs.get("reasoning_effort") == "high"

    async def test_reasoning_effort_omits_temperature(self):
        adapter, mock_create = _make_adapter(reasoning_effort="high")
        mock_create.return_value = _make_response(_go_json())

        await adapter.review("plan")

        call_kwargs = mock_create.call_args.kwargs
        assert "temperature" not in call_kwargs

    async def test_no_reasoning_effort_omits_reasoning_param(self):
        adapter, mock_create = _make_adapter(reasoning_effort=None)
        mock_create.return_value = _make_response(_go_json())

        await adapter.review("plan")

        call_kwargs = mock_create.call_args.kwargs
        assert "reasoning_effort" not in call_kwargs

    async def test_reasoning_effort_values_forwarded(self):
        for effort in ("low", "medium", "high"):
            adapter, mock_create = _make_adapter(reasoning_effort=effort)
            mock_create.return_value = _make_response(_go_json())
            await adapter.review("plan")
            assert mock_create.call_args.kwargs.get("reasoning_effort") == effort


# ---------------------------------------------------------------------------
# 9. prompt_mode selects the correct system prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPromptMode:
    async def test_basic_mode_uses_basic_prompt(self):
        from planner_auto.reviewer.prompts import REVIEWER_SYSTEM_PROMPT

        adapter, mock_create = _make_adapter(prompt_mode="basic")
        mock_create.return_value = _make_response(_go_json())
        await adapter.review("plan")

        messages = mock_create.call_args.kwargs.get("messages")
        sys_content = next(m["content"] for m in messages if m["role"] == "system")
        assert sys_content == REVIEWER_SYSTEM_PROMPT

    async def test_guidance_mode_uses_guidance_prompt(self):
        from planner_auto.reviewer.prompts import REVIEWER_SYSTEM_PROMPT_WITH_GUIDANCE

        adapter, mock_create = _make_adapter(prompt_mode="guidance")
        mock_create.return_value = _make_response(_go_json())
        await adapter.review("plan")

        messages = mock_create.call_args.kwargs.get("messages")
        sys_content = next(m["content"] for m in messages if m["role"] == "system")
        assert sys_content == REVIEWER_SYSTEM_PROMPT_WITH_GUIDANCE

    async def test_keep_trim_mode_uses_keep_trim_prompt(self):
        from planner_auto.reviewer.prompts import REVIEWER_SYSTEM_PROMPT_WITH_KEEP_TRIM

        adapter, mock_create = _make_adapter(prompt_mode="keep_trim")
        mock_create.return_value = _make_response(_go_json())
        await adapter.review("plan")

        messages = mock_create.call_args.kwargs.get("messages")
        sys_content = next(m["content"] for m in messages if m["role"] == "system")
        assert sys_content == REVIEWER_SYSTEM_PROMPT_WITH_KEEP_TRIM

    async def test_invalid_prompt_mode_raises_value_error(self):
        with pytest.raises(ValueError, match="prompt_mode"):
            DirectAPIAdapter(prompt_mode="invalid")


# ---------------------------------------------------------------------------
# 10. Generic API error mapped to ReviewerResponseError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGenericApiError:
    async def test_api_error_raises_reviewer_response_error(self):
        adapter, mock_create = _make_adapter()
        mock_create.side_effect = openai.InternalServerError(
            "internal error",
            response=MagicMock(status_code=500),
            body=None,
        )
        with pytest.raises(ReviewerResponseError, match="API error"):
            await adapter.review("plan")
