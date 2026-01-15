# Debugging: Claude CLI “terminated process” failures (orchestrator-auto)

## Context

We hit a recurring failure while running `orchestrator resume <session-id> --force` in a real repo workflow session:

- Planner completes review and emits `[CHANGES_REQUESTED]`.
- Orchestrator prints `Executor working...`.
- Then the underlying Claude process exits and the SDK reports:
  - `Fatal error in message reader: Command failed with exit code 1 (exit code: 1)`
  - `Error output: Check stderr output for details`
  - `✗ Error: Cannot write to terminated process (exit code: 1)`

This typically leaves the orchestrator session “ACTIVE” in the DB, but the run is dead.

## What’s Actually Failing

This error is not a Python stack trace from orchestrator-auto itself.

It’s coming from the **Claude Agent SDK** subprocess transport that runs the `claude` CLI under the hood:

- The SDK reads `claude` stdout as a stream protocol.
- If the `claude` process exits unexpectedly, any attempt to continue the stream causes:
  - `Fatal error in message reader ...` (logged by the SDK)
  - `Cannot write to terminated process ...` (raised by the SDK)

Key code locations (for reference):

- `claude_agent_sdk/_internal/query.py` logs `Fatal error in message reader: ...`.
- `claude_agent_sdk/_internal/transport/subprocess_cli.py` raises `Cannot write to terminated process ...`.

## Why It’s Hard To Debug Today

The SDK can surface the *real* reason for exit code 1 via Claude CLI stderr, but orchestrator-auto does not currently capture it.

- `claude-agent-sdk` only pipes stderr if either:
  - `ClaudeAgentOptions.stderr` callback is set, OR
  - the special SDK flag `--debug-to-stderr` is enabled via `ClaudeAgentOptions.extra_args`.
- orchestrator-auto currently builds `ClaudeAgentOptions(...)` without setting `stderr`, and without passing CLI debug flags.

Result: you see “Check stderr output for details”, but orchestrator never prints those details.

## Findings From Environment

The environment used during the failure was:

- `claude` CLI: `2.1.5 (Claude Code)`
- `claude-agent-sdk`: `0.1.16`
- `orchestrator-auto` codebase version: `0.12.0` (local checkout)

This failure mode often correlates with:

- A `claude` CLI internal error / crash (stderr would say why)
- A protocol mismatch between the CLI and SDK after a recent update
- An auth or workspace trust issue (stderr would show prompts/errors)

## Proposed Solution: Add First-Class Debugging Hooks

### 1) Add a CLI flag to pipe Claude stderr

Add a CLI option (examples):

- `orchestrator start/resume --claude-stderr`
- `orchestrator start/resume --claude-stderr-file path/to/log.txt`

Implementation idea:

- In `orchestrator_auto/agents.py`, when constructing `ClaudeAgentOptions`, set:
  - `stderr=lambda line: <emit or store line>`

Recommended behavior:

- Default: off (keep output clean)
- When enabled:
  - print stderr lines to terminal (prefixed), and/or
  - append stderr to a log file under `~/.claude_orchestrator/logs/` keyed by session_id and agent (`planner`/`executor`).

This alone should reveal the actual exit reason.

### 2) Add a CLI flag to enable Claude Code debug output

Claude Code supports `--debug` (with optional category filtering).

Add a CLI option like:

- `orchestrator start/resume --claude-debug api,hooks`

Implementation idea:

- Pass `ClaudeAgentOptions.extra_args={"debug": "api,hooks"}`.
- Combine with (1) so the debug output is actually visible.

Suggested default categories:

- `api` (request/response lifecycle)
- `hooks` (tool permission / hooks pipeline)

### 3) Add orchestrator-level `--traceback` for Python exceptions

This won’t fix the “terminated process” by itself (since that’s the `claude` subprocess), but it helps with other crashes.

Implementation idea:

- In `orchestrator_auto/cli.py` top-level `except Exception as e:` blocks, if `--traceback` is set:
  - call `traceback.print_exc()` before exiting.

### 4) Persist last stderr lines to DB for post-mortem

Optional but extremely useful when runs are long.

Implementation idea:

- Add a small table like `session_logs(session_id, agent, stream, line, created_at)` or a single text field for “last 200 stderr lines”.
- Or store in filesystem logs and persist only the path in DB.

## Usage (Once Implemented)

Minimal noisy run to reproduce and capture root cause:

```bash
orchestrator resume 74497fa4 --force --claude-stderr --claude-debug api
```

If file logging exists:

```bash
orchestrator resume 74497fa4 --force --claude-debug api --claude-stderr-file ~/.claude_orchestrator/logs/74497fa4_executor.stderr.log
```

## Immediate Workarounds (No Code Changes)

1) Sanity-check Claude Code outside the orchestrator:

```bash
claude --debug api -p "Say ok"
```

If this fails with stderr output, the orchestrator failure is very likely reproducible.

2) Try updating the SDK if a CLI update recently happened:

- `pip install -U claude-agent-sdk`

(Only do this intentionally; it may require adjusting orchestrator compatibility.)

## Expected Outcome

With stderr piping enabled, the next time the executor process exits with code 1, you should immediately see something actionable:

- auth failure / token expired
- workspace trust / permission prompt
- internal CLI crash with a report
- protocol mismatch hint

This turns “Cannot write to terminated process” from a dead-end into a fixable error.
