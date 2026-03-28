"""Direct OpenAI API reviewer adapter.

Calls GPT via ``openai.AsyncOpenAI`` with configurable model,
reasoning effort, and system-prompt mode.  Implements :class:`ReviewerContract`.

Retry policy:
- ``openai.AuthenticationError``  → raise ``ReviewerAuthError`` immediately
- ``openai.RateLimitError``       → retry 3× with 2 / 4 / 8 s backoff
- ``openai.APITimeoutError``      → retry once after 2 s
- All other ``openai.APIError``   → raise ``ReviewerResponseError``
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import openai

from planner_auto.errors import (
    ReviewerAuthError,
    ReviewerRateLimitError,
    ReviewerResponseError,
    ReviewerTimeoutError,
)
from planner_auto.reviewer.contract import ReviewerContract, ReviewerResponse
from planner_auto.reviewer.parser import parse_reviewer_response
from planner_auto.reviewer.prompts import PROMPT_BY_MODE, USER_PROMPT_TEMPLATE

logger = logging.getLogger("planner-auto.reviewer")

# Retry configuration
_RATE_LIMIT_DELAYS = [2, 4, 8]  # seconds between each of 3 retries
_TIMEOUT_RETRY_DELAY = 2        # seconds before the single timeout retry

# Context header prepended when previous_context is provided
_CONTEXT_HEADER = """\
## Review History Context

{previous_context}

---
IMPORTANT: The review history above shows prior rounds.
- DEFERRED issues are intentionally out of scope — do NOT re-raise them in any form.
- ACCEPTED issues should be verified as resolved in the current plan.
- Focus only on genuinely NEW issues that have not been addressed or deferred.
---

"""


class DirectAPIAdapter(ReviewerContract):
    """GPT-based reviewer that calls the OpenAI Chat Completions API.

    Args:
        model: OpenAI model identifier (default ``"gpt-5.4"``).
        reasoning_effort: OpenAI reasoning effort level
            (``"low"`` / ``"medium"`` / ``"high"``).  When set, ``temperature``
            is omitted from the API call as OpenAI requires the default
            temperature when reasoning is enabled.  Pass ``None`` to use a
            standard (non-reasoning) call with default temperature.
        prompt_mode: Which system-prompt variant to use:
            ``"basic"`` | ``"guidance"`` | ``"keep_trim"``.
    """

    def __init__(
        self,
        model: str = "gpt-5.4",
        reasoning_effort: Optional[str] = "high",
        prompt_mode: str = "basic",
        _client: Optional[object] = None,
    ) -> None:
        """Initialise the adapter.

        Args:
            model: OpenAI model identifier.
            reasoning_effort: Reasoning effort level, or ``None`` for standard.
            prompt_mode: System-prompt variant (``"basic"`` / ``"guidance"`` /
                ``"keep_trim"``).
            _client: Optional pre-constructed ``openai.AsyncOpenAI`` client
                (used in tests to inject a mock without needing an API key).
                Production callers should leave this as ``None``.
        """
        if prompt_mode not in PROMPT_BY_MODE:
            raise ValueError(
                f"prompt_mode must be one of {list(PROMPT_BY_MODE)}, got {prompt_mode!r}"
            )
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.prompt_mode = prompt_mode
        self._system_prompt = PROMPT_BY_MODE[prompt_mode]
        # Use the injected client for tests; create a real one for production.
        self._client = _client if _client is not None else openai.AsyncOpenAI()

    # ------------------------------------------------------------------
    # ReviewerContract implementation
    # ------------------------------------------------------------------

    async def review(
        self,
        plan_text: str,
        previous_context: Optional[str] = None,
    ) -> ReviewerResponse:
        """Review a plan draft via the OpenAI API.

        Args:
            plan_text: Full text of the plan draft to review.
            previous_context: Optional prior-round context (includes deferred
                issues list and previous verdicts).  When provided it is
                prepended to the user message so the reviewer can avoid
                re-raising deferred items.

        Returns:
            Parsed :class:`ReviewerResponse`.

        Raises:
            ReviewerAuthError: On authentication failures.
            ReviewerRateLimitError: After exhausting rate-limit retries.
            ReviewerTimeoutError: After exhausting timeout retries.
            ReviewerResponseError: On API / parse errors.
        """
        user_content = self._build_user_content(plan_text, previous_context)
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_content},
        ]
        return await self._call_with_retry(messages)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_user_content(
        self, plan_text: str, previous_context: Optional[str]
    ) -> str:
        """Build the user-turn message, optionally prefixed with context."""
        plan_section = USER_PROMPT_TEMPLATE.format(plan_text=plan_text)
        if previous_context:
            return _CONTEXT_HEADER.format(previous_context=previous_context) + plan_section
        return plan_section

    async def _call_with_retry(self, messages: list[dict]) -> ReviewerResponse:
        """Execute the API call with rate-limit and timeout retry logic."""
        rate_attempt = 0
        timeout_retried = False

        while True:
            try:
                return await self._single_call(messages)

            except openai.AuthenticationError as exc:
                raise ReviewerAuthError(
                    f"OpenAI authentication failed — check OPENAI_API_KEY: {exc}"
                ) from exc

            except openai.RateLimitError as exc:
                if rate_attempt < len(_RATE_LIMIT_DELAYS):
                    delay = _RATE_LIMIT_DELAYS[rate_attempt]
                    logger.warning(
                        "Rate limited (attempt %d/%d), retrying in %ds...",
                        rate_attempt + 1,
                        len(_RATE_LIMIT_DELAYS),
                        delay,
                    )
                    await asyncio.sleep(delay)
                    rate_attempt += 1
                    continue
                raise ReviewerRateLimitError(
                    f"Rate limit exhausted after {len(_RATE_LIMIT_DELAYS)} retries: {exc}"
                ) from exc

            except openai.APITimeoutError as exc:
                if not timeout_retried:
                    logger.warning(
                        "Timeout on reviewer API call, retrying once in %ds...",
                        _TIMEOUT_RETRY_DELAY,
                    )
                    await asyncio.sleep(_TIMEOUT_RETRY_DELAY)
                    timeout_retried = True
                    continue
                raise ReviewerTimeoutError(
                    f"Reviewer API timed out after retry: {exc}"
                ) from exc

            except openai.APIError as exc:
                raise ReviewerResponseError(
                    f"Reviewer API error: {exc}"
                ) from exc

    async def _single_call(self, messages: list[dict]) -> ReviewerResponse:
        """Make a single (non-retried) API call and return a ReviewerResponse."""
        start = time.monotonic()

        # Build keyword arguments; omit temperature when reasoning is enabled.
        create_kwargs: dict = {
            "model": self.model,
            "messages": messages,
        }
        if self.reasoning_effort is not None:
            create_kwargs["reasoning_effort"] = self.reasoning_effort
            # OpenAI requires default (unset) temperature when using reasoning.
        else:
            # Standard call — use default temperature (omit = API default 1.0).
            pass

        response = await self._client.chat.completions.create(**create_kwargs)

        elapsed = time.monotonic() - start

        # Extract content and usage.
        raw_text: str = ""
        if response.choices:
            raw_text = response.choices[0].message.content or ""

        input_tokens = 0
        output_tokens = 0
        if response.usage:
            input_tokens = response.usage.prompt_tokens or 0
            output_tokens = response.usage.completion_tokens or 0

        # Parse into structured response.
        reviewer_response = parse_reviewer_response(raw_text)

        logger.info(
            "Reviewer call: model=%s, elapsed=%.2fs, tokens=%d+%d, "
            "verdict=%s, issues=%d",
            self.model,
            elapsed,
            input_tokens,
            output_tokens,
            reviewer_response.verdict.value,
            len(reviewer_response.issues),
        )

        return reviewer_response
