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
CLI command (discuss, generate, review)
    → reads session_config["claude_backend"] from DB
    → passes backend= to agents.py / engine.py
        → sdk_wrapper.query_claude(..., backend="direct")    # returns str
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
    backend: str | None = None,      # NEW: "direct" or "sdk", defaults to DEFAULT_BACKEND
) -> str:
    """Returns response text. Return type unchanged."""
```

### Caller Wiring (small, explicit changes)

`query_claude()` has no access to `conn` or session config. Callers must resolve the backend from session config and pass it explicitly. This follows the same pattern as `model`, `effort`, and `thinking` — all resolved by callers, passed as params.

**Changes required in callers:**

| File | Call site | Change |
|------|-----------|--------|
| `agents.py: discuss()` | `query_claude(messages, ...)` | Add `backend=backend` param (passed from CLI) |
| `agents.py: synthesize_context()` | `query_claude(messages, ...)` | Add `backend=backend` param |
| `agents.py: generate_plan()` | `query_claude(messages, ...)` | Add `backend=backend` param |
| `loop/engine.py` | Revision calls via `query_claude()` | Add `backend=self.config.get("claude_backend", "direct")` |

Each function gains a `backend: str = "direct"` parameter. CLI commands read `session_config["claude_backend"]` and pass it through. This is ~4 lines per call site — the same wiring pattern already used for `effort` and `thinking`.

---

## Backend Selection Semantics

### Default

Module-level default in `sdk_wrapper.py`:

```python
DEFAULT_BACKEND = "direct"  # Use Anthropic API directly (no subprocess)
```

### Resolution (two levels, no ambiguity)

1. **Per-call `backend=` param** — explicit at call site, highest priority
2. **Module default `DEFAULT_BACKEND`** — fallback when `backend=None`

There is no wrapper-internal config lookup. The wrapper is stateless — it dispatches based on the `backend=` parameter it receives.

### How CLI commands resolve the backend

Each session-aware CLI command:
1. Reads `session_config.config_json["claude_backend"]` from DB (set at `start`)
2. Passes the value to agents/engine calls
3. If no session config exists (e.g., `check --probe`), uses `DEFAULT_BACKEND`

```python
# In cli.py, each session-aware command:
config = get_session_config(conn, session_id)
claude_backend = json.loads(config["config_json"]).get("claude_backend", "direct")

# Passed through to agents:
response = asyncio.run(discuss(session_id, message, conn, backend=claude_backend))
```

### `--claude-backend` flag

On `start` command only. Persisted in session config. Later commands (`discuss`, `generate`, `review`) read it from session config — no per-command flag needed.

```bash
planner-auto start --project my-feature --claude-backend sdk    # opt into SDK subprocess
planner-auto start --project my-feature                         # default: direct
```

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

`check` validates **both backends** when their dependencies are installed. This ensures the user knows what's available regardless of which backend a specific session uses.

```
planner-auto check

  Environment:
    ANTHROPIC_API_KEY set: true
    OPENAI_API_KEY set: true
  Claude backends:
    direct (anthropic): true (v0.40.0) ← default
    sdk (claude-agent-sdk): true (v0.1.50), claude CLI: /opt/homebrew/bin/claude
  Reviewer:
    openai: true (v2.30.0)
  Database:
    DB path writable: true
    Schema version: 2
  Default backend: direct

  With --probe:
    Claude API (direct): OK (1.2s, 15 tokens)
    OpenAI API: OK (0.8s, 12 tokens)
```

With `--probe --claude-backend sdk`:
```
    Claude API (sdk subprocess): OK (3.4s, 15 tokens)
    # or: RATE LIMITED (subprocess shares quota with active Claude Code sessions)
```

With `--session <id>`:
```
planner-auto check --session abc123
  Session abc123 backend: direct
  (validates the specific backend this session uses)
```

This covers:
- Default check: validates both backends are installable
- `--probe`: tests the default backend (direct) live
- `--probe --claude-backend sdk`: tests the SDK backend live
- `--session <id>`: validates the specific backend a session is configured to use

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

- **Caller tests mostly unchanged** — tests mock `sdk_wrapper.query_claude()` which still returns `str`. Existing mocks work. Tests that construct `agents.discuss()` or `generate_plan()` calls need to add `backend=` in the mock call signature (~4 test files, ~1 line each).
- **New `sdk_wrapper` tests** — test backend dispatch: `backend="direct"` routes to `_execute_direct`, `backend="sdk"` routes to `_execute_sdk`. Test retry logic shared for both. Test thinking fallback. Test `backend=None` uses `DEFAULT_BACKEND`. ~10 new tests.
- **Updated `check` tests** — validates both backends present, `--probe` tests default backend, `--session` validates session-specific backend.
- **CLI tests** — verify `--claude-backend` flag persisted in session config, verify `discuss`/`generate`/`review` read it from config and pass through.

---

## Scope

**In scope:**
- Backend dispatch inside `sdk_wrapper.py` (direct default, sdk opt-in)
- `_execute_direct()` using `anthropic` package
- Shared retry logic for both backends
- Thinking fallback with explicit config
- `--claude-backend` flag on `start` command, persisted in session config
- Small caller wiring: `agents.py` (3 functions) and `loop/engine.py` (1 call site) gain `backend=` param (~4 lines each)
- CLI commands read session config and pass `claude_backend` to callers
- `check` command validates both backends, `--probe` and `--session` options
- `anthropic` added to `pyproject.toml`
- Logging/observability for backend choice

**Out of scope:**
- Tool access via direct API (not needed — all calls are text-in/text-out)
- Removing `claude-agent-sdk` dependency (kept for opt-in SDK backend)
