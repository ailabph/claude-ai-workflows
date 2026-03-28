"""
SDK wrapper for Claude with dual-backend support.

Supports two backends:
- "direct": Calls the Anthropic API directly via the `anthropic` package.
  Default when ANTHROPIC_API_KEY is set. Works alongside active Claude Code sessions.
- "sdk": Calls via `claude-agent-sdk` subprocess. Required for OAuth-only auth.
  Shares rate-limit quota with active Claude Code sessions.

Both backends are wrapped with:
- Authentication error mapping
- Rate-limit retries with exponential backoff
- Timeout/connection retries
- Empty/malformed response detection
- Logging of model, token count, and latency

Backend selection: callers pass ``backend=`` explicitly (resolved from session
config). When ``backend=None``, ``resolve_default_backend()`` determines the
default based on available credentials.
"""

import asyncio
import logging
import os
import time
from typing import Optional

import anthropic
import claude_agent_sdk

from planner_auto.errors import (
    SDKAuthError,
    SDKRateLimitError,
    SDKResponseError,
    SDKTimeoutError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Effort-to-thinking mapping for direct backend
# ---------------------------------------------------------------------------

_EFFORT_THINKING_MAP: dict[str | None, dict] = {
    None:     {"thinking": False, "max_tokens": 16384},
    "low":    {"thinking": False, "max_tokens": 8192},
    "medium": {"thinking": True,  "budget_tokens": 10000, "max_tokens": 16384},
    "high":   {"thinking": True,  "budget_tokens": 20000, "max_tokens": 16384},
    "max":    {"thinking": True,  "budget_tokens": 50000, "max_tokens": 32768},
}


# ---------------------------------------------------------------------------
# Backend resolution
# ---------------------------------------------------------------------------

def resolve_default_backend() -> str:
    """Determine default backend based on available auth credentials.

    Returns:
        "direct" if ANTHROPIC_API_KEY is set (preferred — no subprocess quota conflict).
        "sdk" if only CLAUDE_CODE_OAUTH_TOKEN is set (OAuth requires CLI subprocess).
        "direct" if neither is set (will fail at call time with clear auth error).
    """
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_oauth = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))

    if has_api_key:
        return "direct"
    elif has_oauth:
        return "sdk"
    else:
        return "direct"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def query_claude(
    messages: list[dict],
    system_prompt: str,
    model: str,
    timeout_sec: int = 120,
    effort: Optional[str] = None,
    thinking: bool = False,
    max_turns: Optional[int] = None,
    backend: Optional[str] = None,
) -> str:
    """Query Claude with retry logic and error handling.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        system_prompt: System prompt to set agent behavior.
        model: Model identifier (e.g. 'claude-sonnet-4-6').
        timeout_sec: Timeout in seconds for the call.
        effort: Optional effort level ('low', 'medium', 'high', 'max').
        thinking: When True, enables extended thinking (SDK backend) or
            thinking config (direct backend).
        max_turns: Override the default single-turn cap (SDK backend only).
        backend: "direct" or "sdk". If None, resolved via
            ``resolve_default_backend()``.

    Returns:
        The assistant's text response.

    Raises:
        SDKAuthError: On authentication failures.
        SDKRateLimitError: After exhausting rate-limit retries.
        SDKTimeoutError: After exhausting timeout/connection retries.
        SDKResponseError: On empty or malformed responses.
    """
    resolved_backend = backend or resolve_default_backend()
    logger.debug("query_claude: backend=%s (requested=%s)", resolved_backend, backend)

    # Build prompt from messages
    prompt = _build_prompt(messages)

    # Rate-limit retry: up to 3 attempts with exponential backoff (2s, 4s, 8s)
    rate_limit_delays = [2, 4, 8]
    # Timeout/connection retry: tracked independently (1 retry after 2s)
    timeout_retries_used = 0
    max_timeout_retries = 1

    last_error = None

    for rate_attempt in range(len(rate_limit_delays) + 1):
        try:
            start_time = time.monotonic()

            if resolved_backend == "direct":
                response_text, usage_info = await _execute_direct_with_timeout(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model=model,
                    effort=effort,
                    thinking=thinking,
                    timeout_sec=timeout_sec,
                )
            else:
                response_text, usage_info = await _execute_sdk_with_timeout(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model=model,
                    effort=effort,
                    thinking=thinking,
                    max_turns=max_turns,
                    timeout_sec=timeout_sec,
                )

            elapsed = time.monotonic() - start_time
            input_tokens = usage_info.get("input_tokens", 0) if usage_info else 0
            output_tokens = usage_info.get("output_tokens", 0) if usage_info else 0
            logger.info(
                "Claude call completed: backend=%s, model=%s, elapsed=%.2fs, tokens=%d+%d, response_len=%d",
                resolved_backend, model, elapsed, input_tokens, output_tokens, len(response_text),
            )

            if not response_text or not response_text.strip():
                raise SDKResponseError("Empty response from Claude")

            return response_text

        except SDKAuthError:
            raise  # Don't retry auth errors

        except SDKRateLimitError as e:
            last_error = e
            if rate_attempt < len(rate_limit_delays):
                delay = rate_limit_delays[rate_attempt]
                logger.warning(
                    "Rate limited, retry %d/%d in %ds",
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
            if timeout_retries_used < max_timeout_retries:
                timeout_retries_used += 1
                logger.warning(
                    "Timeout after %ds, retrying (%d/%d)",
                    timeout_sec, timeout_retries_used, max_timeout_retries,
                )
                await asyncio.sleep(2)
                continue
            raise e from None

    # Should not reach here, but just in case
    if last_error:
        raise last_error
    raise SDKResponseError("Unexpected error in query_claude")


# ---------------------------------------------------------------------------
# Direct backend (anthropic package)
# ---------------------------------------------------------------------------

async def _execute_direct(
    prompt: str,
    system_prompt: str,
    model: str,
    max_tokens: int = 16384,
    thinking: bool = False,
    thinking_budget: int = 10000,
) -> tuple[str, dict]:
    """Call Claude via anthropic package directly. Returns (text, usage).

    Maps all anthropic exceptions to the SDKError hierarchy.
    """
    client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": prompt}],
    }

    if thinking:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

    try:
        response = await client.messages.create(**kwargs)
    except anthropic.AuthenticationError as e:
        raise SDKAuthError(f"Invalid API key: {e}") from e
    except anthropic.RateLimitError as e:
        raise SDKRateLimitError(f"Rate limited: {e}") from e
    except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
        raise SDKTimeoutError(f"Connection error: {e}") from e
    except anthropic.BadRequestError as e:
        if "thinking" in str(e).lower():
            logger.warning("Extended thinking not available, falling back to non-thinking mode")
            kwargs.pop("thinking", None)
            try:
                response = await client.messages.create(**kwargs)
            except anthropic.AuthenticationError as e2:
                raise SDKAuthError(f"Invalid API key: {e2}") from e2
            except anthropic.RateLimitError as e2:
                raise SDKRateLimitError(f"Rate limited: {e2}") from e2
            except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e2:
                raise SDKTimeoutError(f"Connection error: {e2}") from e2
            except anthropic.APIError as e2:
                raise SDKResponseError(f"API error: {e2}") from e2
        else:
            raise SDKResponseError(f"Bad request: {e}") from e
    except anthropic.APIError as e:
        raise SDKResponseError(f"API error: {e}") from e

    text_parts = [b.text for b in response.content if b.type == "text"]
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }

    return "\n".join(text_parts), usage


async def _execute_direct_with_timeout(
    prompt: str,
    system_prompt: str,
    model: str,
    effort: Optional[str] = None,
    thinking: bool = False,
    timeout_sec: int = 120,
) -> tuple[str, dict]:
    """Resolve effort-to-thinking config and call _execute_direct with timeout."""
    # Map effort to thinking config for direct backend
    effort_config = _EFFORT_THINKING_MAP.get(effort, _EFFORT_THINKING_MAP[None])
    use_thinking = effort_config.get("thinking", False) or thinking
    max_tokens = effort_config.get("max_tokens", 16384)
    thinking_budget = effort_config.get("budget_tokens", 10000)

    try:
        return await asyncio.wait_for(
            _execute_direct(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model,
                max_tokens=max_tokens,
                thinking=use_thinking,
                thinking_budget=thinking_budget,
            ),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        raise SDKTimeoutError(
            f"Request timed out after {timeout_sec}s (enforced by wait_for)"
        )


# ---------------------------------------------------------------------------
# SDK backend (claude-agent-sdk subprocess)
# ---------------------------------------------------------------------------

async def _execute_sdk(
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


async def _execute_sdk_with_timeout(
    prompt: str,
    system_prompt: str,
    model: str,
    effort: Optional[str] = None,
    thinking: bool = False,
    max_turns: Optional[int] = None,
    timeout_sec: int = 120,
) -> tuple[str, dict]:
    """Build SDK options and call _execute_sdk with timeout."""
    # Resolve effective max_turns for the SDK options object.
    if max_turns is not None and max_turns > 0:
        opts_max_turns: Optional[int] = max_turns
    elif max_turns == 0:
        opts_max_turns = None  # unlimited
    elif thinking:
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
    logger.debug(
        "SDK config applied: effort=%s, thinking=%s, max_turns=%s",
        effort, thinking, opts_max_turns,
    )

    return await asyncio.wait_for(
        _execute_sdk(prompt, options, timeout_sec),
        timeout=timeout_sec,
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

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
