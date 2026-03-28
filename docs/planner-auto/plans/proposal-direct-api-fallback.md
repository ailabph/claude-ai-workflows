# Proposal: Direct Anthropic API Fallback for planner-auto

## Problem

planner-auto is unusable while the user has an active Claude Code session. This is the #1 production blocker.

**Root cause:** `sdk_wrapper.py` uses `claude-agent-sdk` which spawns a `claude` CLI subprocess. This subprocess shares rate-limit quota with any active Claude Code sessions. When the user is talking to Claude Code (the primary use case — they're planning while coding), the subprocess gets throttled and returns `RateLimitEvent` before even starting.

**Confirmed by testing:**
- Direct Anthropic API call via `anthropic` package → works fine (no rate limit)
- Same key via `claude-agent-sdk` subprocess → rate limited immediately
- The `openai` package in `reviewer/direct_api.py` → works fine (no subprocess)

**The irony:** planner-auto was designed to be used alongside Claude Code, but the SDK subprocess architecture makes this impossible.

## Context

planner-auto makes three types of Claude calls:

| Call | Module | Current Implementation | Purpose |
|------|--------|----------------------|---------|
| **discuss** | `agents.py: discuss()` | `sdk_wrapper.query_claude()` → `claude-agent-sdk` subprocess | Interactive conversation |
| **synthesize** | `agents.py: synthesize_context()` | `sdk_wrapper.query_claude()` → `claude-agent-sdk` subprocess | Context synthesis (Haiku) |
| **generate** | `agents.py: generate_plan()` | `sdk_wrapper.query_claude()` → `claude-agent-sdk` subprocess | Plan generation (Sonnet/Opus) |
| **revise** | `loop/engine.py` | `sdk_wrapper.query_claude()` → `claude-agent-sdk` subprocess | Plan revision during review loop |

All four go through `sdk_wrapper.query_claude()` which uses the SDK subprocess. None of them need tool access (Read, Write, Bash) — they're all text-in/text-out conversations.

The GPT reviewer already uses the `openai` package directly — no subprocess, no rate limit conflicts.

## Proposed Fix

Replace the `claude-agent-sdk` subprocess with direct `anthropic` package calls for all planner-auto Claude interactions. Keep the SDK as an optional backend for cases where tool access is needed (future).

### Why direct API, not fix the SDK

| Approach | Pros | Cons |
|----------|------|------|
| Fix SDK rate limit retry | Keeps tool access capability | Still shares quota with Claude Code; may need 30s+ backoff; fragile |
| Direct `anthropic` package | No rate limit conflict; simpler; faster startup (no subprocess spawn); already a dependency | No tool access (Read/Write/Bash); need to reimplement effort/thinking params |
| Hybrid (direct default, SDK opt-in) | Best of both | More code paths to maintain |

**Recommendation: Direct API as default, SDK as opt-in (`--use-sdk` flag).**

planner-auto's Claude calls are all text conversations — discuss, synthesize, generate, revise. None need file system access. The `anthropic` package supports:
- All models (Opus, Sonnet, Haiku) ✓
- System prompts ✓
- Temperature / max_tokens ✓
- Extended thinking (beta) ✓
- Streaming ✓
- Token usage in response ✓

What it doesn't support (that SDK does):
- Tool use (Read, Write, Bash) — not needed for planner-auto
- MCP servers — not needed
- Session continuity / resume — planner-auto manages its own sessions via SQLite

### Implementation

**New module: `planner_auto/claude_client.py`**

```python
"""Direct Anthropic API client for planner-auto.

Uses the `anthropic` package directly instead of `claude-agent-sdk` subprocess.
This avoids rate-limit conflicts with active Claude Code sessions.
"""

import anthropic
import time
import logging

logger = logging.getLogger(__name__)

async def query_claude_direct(
    messages: list[dict],
    system_prompt: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 16384,
    timeout_sec: int = 120,
    effort: str | None = None,
    thinking: bool = False,
    thinking_budget: int = 10000,
) -> tuple[str, dict]:
    """Call Claude via the Anthropic API directly.

    Returns (response_text, usage_info).
    """
    client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env

    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": messages,
    }

    if thinking:
        kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": thinking_budget,
        }

    # Note: effort is not directly supported by the Anthropic API
    # (it's a Claude Code / SDK concept). For direct API, we use
    # thinking budget as the equivalent lever.

    start = time.monotonic()
    response = await client.messages.create(**kwargs)
    elapsed = time.monotonic() - start

    # Extract text from response blocks
    text_parts = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)

    response_text = "\n".join(text_parts)

    usage_info = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }

    logger.info(
        "Claude direct API: model=%s, elapsed=%.2fs, tokens=%d+%d, len=%d",
        model, elapsed, usage_info["input_tokens"],
        usage_info["output_tokens"], len(response_text),
    )

    return response_text, usage_info
```

**Changes to existing modules:**

1. **`sdk_wrapper.py`** — Keep as-is but rename to `sdk_wrapper.py` (legacy). Add deprecation notice.
2. **`agents.py`** — Switch from `sdk_wrapper.query_claude()` to `claude_client.query_claude_direct()`. Same interface (messages, system_prompt, model) so the change is minimal.
3. **`loop/engine.py`** — Revision calls already go through agents.py or sdk_wrapper. Route to `claude_client` instead.
4. **`cli.py`** — Add `--use-sdk` flag for backward compatibility. Default is direct API.

### Retry Logic

The direct API client handles retries natively:

```python
# Rate limit: retry 3x with 2/4/8s backoff
# Timeout: asyncio.wait_for with retry once
# Auth error: fail immediately
# Empty response: raise SDKResponseError
```

Same retry semantics as current `sdk_wrapper.py` but against the HTTP API, not a subprocess.

### Effort / Thinking Mapping

| SDK Concept | Direct API Equivalent |
|-------------|----------------------|
| `effort="low"` | `thinking=False`, lower `max_tokens` |
| `effort="medium"` | `thinking=True`, `budget_tokens=10000` |
| `effort="high"` | `thinking=True`, `budget_tokens=20000` |
| `effort="max"` | `thinking=True`, `budget_tokens=50000` |
| `thinking=True` | `thinking={"type": "enabled", "budget_tokens": N}` |
| `max_turns=N` | Not applicable (no tool use = single turn always) |

Note: The Anthropic API's extended thinking is currently in beta and requires a beta header. Check availability before implementation.

## Impact

| Area | Change |
|------|--------|
| `claude_client.py` | New module (~100 lines) |
| `agents.py` | Switch import from `sdk_wrapper` to `claude_client` (~10 line changes) |
| `loop/engine.py` | Same — route through `claude_client` |
| `cli.py` | Add `--use-sdk` flag |
| `sdk_wrapper.py` | Keep for backward compat, add deprecation notice |
| Tests | Update mocks from `sdk_wrapper.query_claude` to `claude_client.query_claude_direct` |
| `pyproject.toml` | `anthropic` already a dependency — no change |

## What This Fixes

| Issue | Before | After |
|-------|--------|-------|
| **H2: Rate limit during Claude Code session** | Unusable — subprocess shares quota | Works — direct API has own quota |
| **H3: anyio traceback noise** | Multiple tracebacks on every error | Gone — no subprocess = no anyio |
| **H1: Opus + thinking + empty results** | SDK subprocess + tool use = empty | Direct API + thinking = text only |
| **M1: Multiple session conflicts** | Intermittent crashes | Gone — no subprocess |

This single change resolves 4 of the 5 open issues (H1, H2, H3, M1).

## Risk

| Risk | Mitigation |
|------|------------|
| Extended thinking API may be beta/limited | Check availability; fall back to non-thinking if unavailable |
| No tool access for future features | Keep SDK as `--use-sdk` opt-in for cases that need tools |
| Breaking change for tests | Tests mock the wrapper — update mock targets |
| Direct API may have different token limits | Anthropic API supports same models/limits as SDK |

## Recommendation

**Implement this as the next priority** — before stress testing or any other work. planner-auto is currently broken for its primary use case (planning while coding). This fix resolves 4 open issues with a single architectural change.

Estimated effort: ~2-3 hours. New module is ~100 lines. Most changes are import swaps.
