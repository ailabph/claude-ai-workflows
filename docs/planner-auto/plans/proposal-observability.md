# Planner-Auto Observability & Debug Proposal

## Problem

planner-auto runs multi-round planning sessions involving two AI models (Claude + GPT), SQLite state, artifact export, and a convergence loop. When something goes wrong — a stuck review loop, unexpected disposition, empty plan, or silent fallback — there is no practical way to diagnose it.

Current state:
- Session log files exist but are only created on `start` (not re-attached on `review`, `discuss`, `generate`)
- `--debug` / `--verbose` flags only work on the `start` command
- Most modules have zero log calls (cli, session, agents, parser, prompts, validation)
- No way to inspect review history, dispositions, config snapshots, or raw GPT responses from the CLI
- No way to see what history context was sent to GPT each round
- No traceback printing on errors in `review`, `discuss`, `generate` commands
- The review loop's internal decisions (severity filtering, feedback validation, keep/trim) are invisible

This makes complex sessions a black box. When the POC experiments surfaced issues (oscillating criticals, scope creep, plan bloat), diagnosis required reading exported artifacts manually. A production tool needs better.

---

## Goals

1. **Every command attaches to the session logger** — not just `start`
2. **--debug and --verbose work on all commands** — consistent flags
3. **Structured logging in all modules** — log key decisions, not just errors
4. **DB inspection CLI commands** — inspect reviews, dispositions, config, history
5. **Review loop visibility** — see what GPT received, what Claude decided, why the loop stopped
6. **Error diagnostics** — stack traces on --debug, actionable messages otherwise

---

## Proposed Changes

### 1. Logger Lifecycle (attach to any command)

Currently `setup_session_logger()` is only called in `start`. Every command that takes a `session-id` should re-attach to the existing logger:

```python
# In every command that takes session_id:
logger = setup_session_logger(session_id, verbose=verbose, debug=debug)
```

This means `--verbose` and `--debug` need to be **global flags on the CLI group**, not per-command options:

```python
@cli.group()
@click.option("--verbose", is_flag=True)
@click.option("--debug", is_flag=True)
@click.option("--db-path", default=None)
@click.pass_context
def cli(ctx, verbose, debug, db_path):
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["debug"] = debug
```

Then each command reads from `ctx.obj` and attaches the logger.

### 2. Structured Logging Per Module

Add logger calls at key decision points. Not every line — just the decisions that affect session state:

| Module | What to Log | Level |
|--------|-------------|-------|
| `cli.py` | Command invoked, session_id, flags | INFO |
| `session.py` | Phase transitions, pause/resume, blocker creation | INFO |
| `agents.py` | SDK call start/end, model, token count, synthesis result size | INFO |
| `sdk_wrapper.py` | Retry attempts, timeout, effort/thinking config applied | WARNING/INFO |
| `db.py` | Schema migration executed, version change | WARNING |
| `reviewer/direct_api.py` | GPT call: model, latency, tokens, cost, verdict | INFO |
| `reviewer/parser.py` | Parse stage used (JSON/XML/free-form), fallback triggered | DEBUG |
| `loop/engine.py` | Round start/end, verdict, issue count, stop reason, total cost | INFO |
| `loop/feedback.py` | Per-issue disposition (ACCEPT/DEFER/REJECT) with reason | INFO |
| `loop/history.py` | Context size sent to GPT, deferred issue count included | DEBUG |
| `loop/convergence.py` | Complexity detected, keywords matched, cap selected | INFO |
| `export.py` | Files written, paths, .kafra handoff success/skip | INFO |
| `git_utils.py` | Repo root discovered/failed | DEBUG |

### 3. DB Inspection CLI Commands

New `inspect` command group for debugging sessions from the terminal:

```bash
# Show all reviews for a session with verdict/issues/cost
planner-auto inspect reviews <session-id>

# Show dispositions for a specific round
planner-auto inspect dispositions <session-id> --round 3

# Show the config snapshot
planner-auto inspect config <session-id>

# Show what history context was stored per round
planner-auto inspect history <session-id> --round 4

# Show raw GPT response for a round (unstructured text)
planner-auto inspect raw-response <session-id> --round 2

# Dump full session state as JSON (for bug reports)
planner-auto inspect dump <session-id>
planner-auto inspect dump <session-id> --output session-debug.json
```

Implementation: new `planner_auto/inspect.py` module with query functions, wired as a Click subgroup.

### 4. Review Loop Visibility

During the review loop, the engine should print structured progress that's useful in both normal and verbose modes:

**Normal mode (default):**
```
── Round 1 ─────────────────────────────────
Review:   NO_GO (5 issues: 1 critical, 4 major)
Action:   Validating feedback...
  ACCEPT: Missing error handling [critical]
  ACCEPT: No migration strategy [major]
  DEFER:  Redis requirement (out of scope) [major]
  ACCEPT: Incomplete API contract [major]
Revising plan (3 accepted issues)...
Draft #2 saved.
```

**Verbose mode (--verbose):**
```
── Round 1 ─────────────────────────────────
Review:   NO_GO (5 issues: 1 critical, 4 major, filtered from 7 total)
  GPT model: gpt-5.4 (reasoning=high)
  Latency: 14.2s | Tokens: 1,280 (in:574, out:706) | Cost: $0.007
  Keep: [3 items] | Trim: [2 items]
Action:   Validating feedback...
  [1/5] ACCEPT: Missing error handling [critical] → "Add try/except in endpoint"
  [2/5] ACCEPT: No migration strategy [major] → "Add Alembic migration step"
  [3/5] DEFER:  Redis requirement [major] → "Deployment config, not feature scope"
  [4/5] ACCEPT: Incomplete API contract [major] → "Define request/response schemas"
  [5/5] REJECT: Observability overkill [minor] → "Already filtered by severity"
Revising plan (3 accepted issues, 1 deferred, 1 rejected)...
  Planner: claude-opus-4-6 (effort=medium, thinking=adaptive)
  Revision latency: 35.3s | Cost: $0.084
Draft #2 saved. Plan size: 8.5 KB (was 5.2 KB)
History context for next round: 3.2 KB (1 cumulative defer)
```

**Debug mode (--debug):** all of verbose plus raw GPT response text, full history context string, revision prompt text, and stack traces on errors.

### 5. Error Diagnostics

Currently errors are caught and printed as one-line messages. With `--debug`, print full tracebacks:

```python
except SDKError as e:
    click.echo(f"Error: {e}", err=True)
    if ctx.obj.get("debug"):
        import traceback
        traceback.print_exc()
    ctx.exit(1)
```

Also add a `planner-auto check` command (like orchestrator-auto has):

```bash
planner-auto check
```

Validates:
- `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` set
- `OPENAI_API_KEY` set (for reviewer)
- Claude SDK subprocess can spawn and respond
- SQLite DB writable
- Schema version is current

---

## Scope Boundaries

**In scope:**
- Logger lifecycle (attach on every command)
- Global --verbose/--debug flags
- Structured logging in all modules (key decisions only)
- `inspect` CLI commands for DB state
- Review loop progress output (normal/verbose/debug tiers)
- Error traceback printing on --debug
- `check` command for environment validation

**Out of scope (future):**
- TUI dashboard with live log panel
- Remote log shipping (Sentry, etc.)
- Performance profiling / token cost analytics dashboard
- Log rotation / cleanup (files just accumulate for now)

---

## Estimated Impact

| Module | Changes |
|--------|---------|
| `cli.py` | Global flags, logger re-attach per command, error traceback, check command |
| `session.py` | 5-8 log calls (transitions, pause/resume) |
| `agents.py` | 4-6 log calls (SDK calls, synthesis) |
| `sdk_wrapper.py` | Already has 4 calls, add 2-3 more (config applied, retry decisions) |
| `db.py` | 2-3 log calls (migration, version check) |
| `reviewer/direct_api.py` | Already has 4 calls, may be sufficient |
| `reviewer/parser.py` | 3-4 log calls (stage used, fallback) |
| `loop/engine.py` | 8-10 log calls (round progress, stop reason, cost) + stdout progress output |
| `loop/feedback.py` | 5-6 log calls (per-issue disposition) |
| `loop/history.py` | 3-4 log calls (context size, defer count) |
| `loop/convergence.py` | Already has 2 calls, add 1-2 more |
| `export.py` | 3-4 log calls (files written, handoff) |
| `inspect.py` | New module (~150 lines) |
| `logging.py` | Minor changes (re-attach semantics) |
| **Tests** | ~20 new tests for inspect commands + check command |

---

## Priority

**High.** Without this, debugging a stuck review loop or unexpected convergence behavior requires manual DB queries and artifact inspection. Every issue found in the Plan 2 review rounds (disposition indexing, metadata gaps, round lookup) would have been caught earlier with proper logging.

This should be implemented before the first real user session — diagnosing issues in a 20-round complex planning session without observability would be painful.
