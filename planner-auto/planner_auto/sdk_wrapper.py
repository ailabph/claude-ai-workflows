"""
SDK wrapper for Claude Agent SDK with robust error handling.

Wraps claude_agent_sdk.query() with:
- Authentication error mapping
- Rate-limit retries with exponential backoff
- Timeout/connection retries
- Empty/malformed response detection
- Logging of model, token count, and latency
"""

import asyncio
import logging
import time
from typing import Optional

import claude_agent_sdk

from planner_auto.errors import (
    SDKAuthError,
    SDKRateLimitError,
    SDKResponseError,
    SDKTimeoutError,
)

logger = logging.getLogger("planner-auto.sdk")


async def query_claude(
    messages: list[dict],
    system_prompt: str,
    model: str,
    timeout_sec: int = 120,
    effort: Optional[str] = None,
    thinking: bool = False,
    max_turns: Optional[int] = None,
) -> str:
    """Query Claude via the Agent SDK with retry logic and error handling.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
            Used to build the prompt for the SDK.
        system_prompt: System prompt to set agent behavior.
        model: Model identifier (e.g. 'claude-sonnet-4-6').
        timeout_sec: Timeout in seconds for the SDK call.
        effort: Optional effort level ('low', 'medium', 'high', 'max').
            When provided, sets ``ClaudeAgentOptions.effort``.
        thinking: When True, enables adaptive thinking via
            ``ThinkingConfigAdaptive``.  Also causes ``max_turns`` to
            default to unlimited when not explicitly set.
        max_turns: Override the default single-turn cap.
            - ``> 0`` → use that value.
            - ``0`` → unlimited (None passed to SDK).
            - ``None`` + ``thinking=True`` → unlimited.
            - ``None`` + ``thinking=False`` → default of 1.

    Returns:
        The assistant's text response.

    Raises:
        SDKAuthError: On authentication failures.
        SDKRateLimitError: After exhausting rate-limit retries.
        SDKTimeoutError: After exhausting timeout/connection retries.
        SDKResponseError: On empty or malformed responses.
    """
    # Build prompt from messages — last user message is the prompt,
    # prior messages provide conversation context
    prompt = _build_prompt(messages)

    # Resolve effective max_turns for the SDK options object.
    if max_turns is not None and max_turns > 0:
        opts_max_turns: Optional[int] = max_turns
    elif max_turns == 0:
        opts_max_turns = None  # unlimited
    elif thinking:
        # Thinking mode: omit cap so the model can use as many turns as needed.
        opts_max_turns = None
    else:
        opts_max_turns = 1  # safe default for non-thinking calls

    # Build thinking config when requested.
    thinking_config = (
        claude_agent_sdk.ThinkingConfigAdaptive(type="adaptive") if thinking else None
    )

    options = claude_agent_sdk.ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=model,
        max_turns=opts_max_turns,
        thinking=thinking_config,
        effort=effort,
    )

    # Rate-limit retry: up to 3 attempts with exponential backoff (2s, 4s, 8s)
    rate_limit_delays = [2, 4, 8]
    # Timeout/connection retry: tracked independently (1 retry after 2s)
    timeout_retries_used = 0
    max_timeout_retries = 1

    last_error = None

    for rate_attempt in range(len(rate_limit_delays) + 1):
        try:
            start_time = time.monotonic()
            response_text, usage_info = await asyncio.wait_for(
                _execute_query(prompt, options, timeout_sec),
                timeout=timeout_sec,
            )
            elapsed = time.monotonic() - start_time

            input_tokens = usage_info.get("input_tokens", 0) if usage_info else 0
            output_tokens = usage_info.get("output_tokens", 0) if usage_info else 0
            logger.info(
                "SDK call completed: model=%s, elapsed=%.2fs, tokens=%d+%d, response_len=%d",
                model, elapsed, input_tokens, output_tokens, len(response_text),
            )

            if not response_text or not response_text.strip():
                raise SDKResponseError("Empty response from Claude SDK")

            return response_text

        except SDKAuthError:
            raise  # Don't retry auth errors

        except SDKRateLimitError as e:
            last_error = e
            if rate_attempt < len(rate_limit_delays):
                delay = rate_limit_delays[rate_attempt]
                logger.warning(
                    "Rate limited (attempt %d/%d), retrying in %ds...",
                    rate_attempt + 1, len(rate_limit_delays) + 1, delay,
                )
                await asyncio.sleep(delay)
                continue
            raise

        except (asyncio.TimeoutError, SDKTimeoutError) as e:
            if isinstance(e, asyncio.TimeoutError):
                e = SDKTimeoutError(
                    f"Request timed out after {timeout_sec}s (enforced by wait_for)"
                )
            last_error = e
            # Independent timeout retry counter (not coupled to rate-limit loop)
            if timeout_retries_used < max_timeout_retries:
                timeout_retries_used += 1
                logger.warning(
                    "Timeout/connection error (retry %d/%d), retrying in 2s...",
                    timeout_retries_used, max_timeout_retries,
                )
                await asyncio.sleep(2)
                continue
            raise e from None

    # Should not reach here, but just in case
    if last_error:
        raise last_error
    raise SDKResponseError("Unexpected error in query_claude")


async def _execute_query(
    prompt: str,
    options: claude_agent_sdk.ClaudeAgentOptions,
    timeout_sec: int,
) -> tuple[str, dict]:
    """Execute a single SDK query call and collect the response.

    Returns (response_text, usage_info) where usage_info is a dict with
    token counts from the ResultMessage, or empty dict if unavailable.

    Maps SDK errors to our custom error types.
    """
    try:
        result_parts = []
        usage_info: dict = {}
        async for message in claude_agent_sdk.query(
            prompt=prompt, options=options
        ):
            if isinstance(message, claude_agent_sdk.AssistantMessage):
                for block in message.content:
                    if isinstance(block, claude_agent_sdk.TextBlock):
                        result_parts.append(block.text)
            elif isinstance(message, claude_agent_sdk.ResultMessage):
                if message.result:
                    result_parts.append(message.result)
                if message.usage:
                    usage_info = message.usage
            elif isinstance(message, claude_agent_sdk.RateLimitEvent):
                raise SDKRateLimitError("Rate limited by API")

        return "".join(result_parts), usage_info

    except SDKRateLimitError:
        raise
    except SDKAuthError:
        raise
    except SDKTimeoutError:
        raise
    except claude_agent_sdk.CLIConnectionError as e:
        raise SDKTimeoutError(f"Connection error: {e}") from e
    except claude_agent_sdk.ProcessError as e:
        error_str = str(e).lower()
        if "auth" in error_str or "api key" in error_str or "unauthorized" in error_str:
            raise SDKAuthError(
                "Invalid API key \u2014 set ANTHROPIC_API_KEY"
            ) from e
        if "rate" in error_str and "limit" in error_str:
            raise SDKRateLimitError(f"Rate limited: {e}") from e
        if "timeout" in error_str or "timed out" in error_str:
            raise SDKTimeoutError(f"Request timed out: {e}") from e
        raise SDKResponseError(f"SDK process error: {e}") from e
    except asyncio.TimeoutError as e:
        raise SDKTimeoutError(f"Request timed out after {timeout_sec}s") from e
    except claude_agent_sdk.ClaudeSDKError as e:
        raise SDKResponseError(f"SDK error: {e}") from e
    except Exception as e:
        raise SDKResponseError(f"Unexpected error: {e}") from e


def _build_prompt(messages: list[dict]) -> str:
    """Build a single prompt string from message history.

    The SDK expects a single prompt string. We format conversation
    history as context, with the last user message as the main prompt.
    """
    if not messages:
        return ""

    if len(messages) == 1:
        return messages[0].get("content", "")

    # Format prior messages as context, last message as prompt
    context_parts = []
    for msg in messages[:-1]:
        role = msg.get("role", "user").capitalize()
        content = msg.get("content", "")
        context_parts.append(f"[{role}]: {content}")

    context = "\n\n".join(context_parts)
    last_content = messages[-1].get("content", "")

    return f"Previous conversation:\n{context}\n\nCurrent message:\n{last_content}"
