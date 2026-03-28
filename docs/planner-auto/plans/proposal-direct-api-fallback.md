# Proposal: Direct Anthropic API Fallback for planner-auto (v2)

## Problem

planner-auto is unusable while the user has an active Claude Code session. This is the #1 production blocker.

**Root cause:** `sdk_wrapper.py` uses `claude-agent-sdk` which spawns a `claude` CLI subprocess. This subprocess shares rate-limit quota with any active Claude Code sessions. When the user is talking to Claude Code (the primary use case — they're planning while coding), the subprocess gets throttled and returns `RateLimitEvent` before even starting.

**Confirmed by testing:**
- Direct Anthropic API call via `anthropic` package → works fine (no rate limit)
- Same key via `claude-agent-sdk` subprocess → rate limited immediately
- The `openai` package in `reviewer/direct_api.py` → works fine (no subprocess)

**The irony:** planner-auto was designed to be used alongside Claude Code, but the SDK subprocess architecture makes this impossible.

---

## Design Principles

1. **`query_claude()` stays the only public API** — all callers (`agents.py`, `loop/engine.py`) continue to call `sdk_wrapper.query_claude()` with the same signature and return type (`str`). No caller changes.
2. **Backend selection happens inside the wrapper** — `sdk_wrapper.py` gains an internal `_backend` choice: `"direct"` (Anthropic API) or `"sdk"` (subprocess). Callers don't know or care which backend is active.
3. **Direct API is the default** — the SDK subprocess is opt-in for cases that need tool access (future).
4. **`anthropic` becomes a declared dependency** — added to `pyproject.toml`.

---

## Architecture

### Current (broken with active Claude Code)

```
agents.py / engine.py
    → sdk_wrapper.query_claude()       # returns str
        → claude-agent-sdk.query()     # spawns claude CLI subprocess
            → RATE LIMITED (shares quota with Claude Code)
```

### Proposed (works alongside Claude Code)

```
agents.py / engine.py
    → sdk_wrapper.query_claude()       # returns str (UNCHANGED)
        → backend = config["claude_backend"]
        ├── "direct" (default):
        │   → anthropic.AsyncAnthropic().messages.create()
        │   → extract text → return str
        └── "sdk" (opt-in):
            → claude-agent-sdk.query()
            → extract ResultMessage.result → return str
```

### Return Contract (unchanged)

```python
async def query_claude(
    messages: list[dict],
    system_prompt: str,
    model: str,
    timeout_sec: int = 120,
    effort: str | None = None,
    thinking: bool = False,
    max_turns: int | None = None,
    backend: str | None = None,      # NEW: "direct" or "sdk", defaults to module-level setting
) -> str:
    """Returns response text. Callers do not change."""
```

The only addition is the optional `backend` parameter. All existing callers continue to work without modification.

---

## Backend Selection Semantics

### Default

Module-level default in `sdk_wrapper.py`:

```python
DEFAULT_BACKEND = "direct"  # Use Anthropic API directly (no subprocess)
```

### Override hierarchy (highest wins)

1. **Per-call `backend=` param** — for specific calls that need a different backend
2. **Session config `claude_backend`** — stored in `session_config.config_json["claude_backend"]`; set at session start
3. **CLI flag `--claude-backend direct|sdk`** — on `start` command; persisted in session config
4. **Module default `DEFAULT_BACKEND`** — `"direct"`

### Which commands use it

| Command | Claude calls | Backend source |
|---------|-------------|---------------|
| `discuss` | `agents.discuss()` | Session config (set at `start`) |
| `generate` | `agents.generate_plan()`, `agents.synthesize_context()` | Session config |
| `review` | `loop/engine.py` revision calls | Session config |
| `check --probe` | Test Claude call | Module default (no session) |

All go through `query_claude()`. Backend is resolved once per call from the hierarchy above.

### Session config persistence

```json
{
  "project": "my-api",
  "claude_backend": "direct",
  "model_default": "claude-opus-4-6",
  ...
}
```

Logged at session start: `INFO: Claude backend: direct (Anthropic API)` or `INFO: Claude backend: sdk (CLI subprocess)`.

---

## Direct API Implementation (inside sdk_wrapper.py)

New internal function added to `sdk_wrapper.py`:

```python
async def _execute_direct(
    prompt: str,
    system_prompt: str,
    model: str,
    max_tokens: int = 16384,
    timeout_sec: int = 120,
    thinking: bool = False,
    thinking_budget: int = 10000,
) -> tuple[str, dict]:
    """Call Claude via anthropic package directly. Returns (text, usage)."""
    client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env

    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": prompt}],
    }

    if thinking:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
        # Extended thinking requires beta header — handled by anthropic package
        # if available; falls back gracefully (see Thinking Fallback below)

    response = await asyncio.wait_for(
        client.messages.create(**kwargs),
        timeout=timeout_sec,
    )

    text_parts = [b.text for b in response.content if b.type == "text"]
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }

    return "\n".join(text_parts), usage
```

The existing `_execute_query()` (SDK subprocess path) is renamed to `_execute_sdk()` and kept as-is.

`query_claude()` dispatches:

```python
async def query_claude(..., backend=None) -> str:
    resolved_backend = backend or _get_default_backend()

    if resolved_backend == "direct":
        text, usage = await _with_retries(_execute_direct, ...)
    else:
        text, usage = await _with_retries(_execute_sdk, ...)

    # Log usage
    logger.info("Claude call: backend=%s, model=%s, tokens=%d+%d", ...)

    return text  # same return type as before
```

Retry logic (`_with_retries`) is shared between both backends: rate limit 3x with 2/4/8s backoff, timeout once after 2s, auth error immediate.

---

## Thinking Fallback (explicit)

The `effort` parameter maps to thinking configuration:

| effort | Direct API config | Fallback if thinking unavailable |
|--------|------------------|----------------------------------|
| `None` | `thinking=False`, `max_tokens=16384` | N/A |
| `"low"` | `thinking=False`, `max_tokens=8192` | N/A |
| `"medium"` | `thinking=True`, `budget_tokens=10000` | `thinking=False`, `max_tokens=16384` |
| `"high"` | `thinking=True`, `budget_tokens=20000` | `thinking=False`, `max_tokens=16384` |
| `"max"` | `thinking=True`, `budget_tokens=50000` | `thinking=False`, `max_tokens=32768` |

**Fallback behavior:** If `client.messages.create()` raises an error indicating thinking is unavailable (beta not enabled, model doesn't support it), retry the same call without thinking and log a warning:

```python
except anthropic.BadRequestError as e:
    if "thinking" in str(e).lower():
        logger.warning("Extended thinking not available, falling back to non-thinking mode")
        kwargs.pop("thinking", None)
        response = await client.messages.create(**kwargs)
    else:
        raise
```

**Impact on convergence defaults:** The v1 config uses `effort="medium"` + `thinking=True`. If thinking falls back to non-thinking, the plan quality may be slightly lower (similar to Sonnet baseline in POC experiments — still produces good plans, just needs 1-2 more review rounds). This is acceptable and logged.

---

## Changes to `check` Command

Current `check` validates:
- `claude` CLI on PATH ← only relevant for SDK backend
- `claude_agent_sdk` importable ← only relevant for SDK backend
- `openai` importable

Updated `check` validates based on default backend:

```
planner-auto check

  Environment:
    ANTHROPIC_API_KEY set: true
    OPENAI_API_KEY set: true
  Claude backend: direct
    anthropic package: true (v0.40.0)
  Reviewer:
    openai package: true (v2.30.0)
  Database:
    DB path writable: true
    Schema version: 2

  With --probe:
    Claude API (direct): OK (1.2s, 15 tokens)
    OpenAI API: OK (0.8s, 12 tokens)
```

When backend is `sdk`, check also validates `claude` on PATH and `claude_agent_sdk` importable. When `direct`, those checks are skipped (not needed).

---

## Dependency Change

Add to `planner-auto/pyproject.toml`:

```toml
dependencies = [
    "click>=8.0",
    "claude-agent-sdk>=0.1.50,<0.2.0",  # kept for --claude-backend sdk
    "anthropic>=0.40.0",                  # NEW: direct API backend
    "prompt_toolkit>=3.0",
    "openai>=2.0",
]
```

`claude-agent-sdk` stays as a dependency for the SDK backend opt-in. `anthropic` is added for the default direct backend.

---

## Observability

| What | Where | Level |
|------|-------|-------|
| Backend resolved | `query_claude()` entry | DEBUG |
| Direct API call start | `_execute_direct()` | DEBUG |
| Direct API call complete | `_execute_direct()` | INFO (model, latency, tokens) |
| Thinking fallback triggered | `_execute_direct()` | WARNING |
| Backend stored in session | `cli.py start` | INFO |
| Backend in session config | `session_config.config_json` | Persisted |

---

## What This Fixes

| Issue | Before | After |
|-------|--------|-------|
| **H2: Rate limit during Claude Code** | Unusable — subprocess shares quota | Works — direct API has own quota |
| **H3: anyio traceback noise** | Multiple tracebacks on every error | Gone — no subprocess = no anyio |
| **H1: Opus + thinking empty results** | SDK subprocess + tool use = empty | Direct API + thinking = text only (no tools to consume turns) |
| **M1: Multiple session conflicts** | Intermittent crashes | Gone — no subprocess |

---

## Test Changes

- **No caller test changes** — `agents.py` and `loop/engine.py` tests mock `sdk_wrapper.query_claude()` which still returns `str`. Mocks continue to work.
- **New `sdk_wrapper` tests** — test backend dispatch: `backend="direct"` routes to `_execute_direct`, `backend="sdk"` routes to `_execute_sdk`. Test retry logic shared for both. Test thinking fallback. ~8 new tests.
- **Updated `check` tests** — validate correct checks for each backend mode.

---

## Scope

**In scope:**
- Backend selection inside `sdk_wrapper.py` (direct default, sdk opt-in)
- `_execute_direct()` using `anthropic` package
- Shared retry logic for both backends
- Thinking fallback with explicit config
- `--claude-backend` flag on `start` command, persisted in session config
- `check` command updated for backend-aware validation
- `anthropic` added to `pyproject.toml`
- Logging/observability for backend choice

**Out of scope:**
- Tool access via direct API (not needed — all calls are text-in/text-out)
- Removing `claude-agent-sdk` dependency (kept for opt-in SDK backend)
- Changes to `agents.py`, `loop/engine.py`, or any caller of `query_claude()` (no changes needed)
