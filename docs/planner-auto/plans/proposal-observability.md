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

### 1. Logger Architecture (shared root logger + session context)

**Problem with the original proposal:** The current `setup_session_logger()` creates a logger named `planner-auto.<session-id>`, but modules log to fixed names like `planner-auto.reviewer`, `planner-auto.loop.feedback`, etc. These are sibling loggers, not children of the session logger, so "re-attach per command" would not capture module logs.

**Revised design: shared root logger + session-id context injection.**

All modules use `logging.getLogger("planner_auto.module_name")` — these are children of the `planner_auto` root logger. The session setup attaches file + stderr handlers to the **root** `planner_auto` logger, and uses a `logging.Filter` to inject `session_id` into all log records:

```python
class SessionFilter(logging.Filter):
    def __init__(self, session_id: str):
        self.session_id = session_id
    def filter(self, record):
        record.session_id = self.session_id
        return True

def setup_session_logging(session_id, verbose=False, debug=False):
    root = logging.getLogger("planner_auto")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    fmt = "%(asctime)s [%(levelname)s] %(name)s (%(session_id)s): %(message)s"
    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    # File handler — always DEBUG, always written
    fh = logging.FileHandler(f"~/.planner-auto/logs/{session_id}.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    fh.addFilter(SessionFilter(session_id))
    root.addHandler(fh)

    # Stderr handler — only if verbose/debug
    if debug or verbose:
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(logging.DEBUG if debug else logging.INFO)
        sh.setFormatter(formatter)
        sh.addFilter(SessionFilter(session_id))
        root.addHandler(sh)
```

This way, `logging.getLogger("planner_auto.loop.engine")` in engine.py automatically flows through the root's handlers into the session log file — no per-module wiring needed.

**--verbose / --debug flags:** Keep as **per-command options** (not global group flags) to avoid the breaking UX change from `planner-auto start --debug` to `planner-auto --debug start`. Every command that takes `session-id` accepts `--verbose` and `--debug` and calls `setup_session_logging()`. The `start` command also gets these flags (as it does today). Consistency without breaking the CLI shape.

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

# Reconstruct the history context that WOULD be sent to GPT for a given round
planner-auto inspect history <session-id> --round 4

# Show raw GPT response for a round (⚠ may contain repo content — see Security)
planner-auto inspect raw-response <session-id> --round 2

# Dump full session state as JSON (for bug reports)
planner-auto inspect dump <session-id>
planner-auto inspect dump <session-id> --output session-debug.json
```

**History inspection design choice:** History context is built on-demand by `loop/history.py` and is NOT persisted in the DB. `inspect history` will **reconstruct** the context from stored reviews + dispositions using the same `build_review_context()` function. This is documented as "reconstructed, not stored" — the output matches what GPT would have seen, but is regenerated from DB state.

**Alternative considered:** Persisting the exact history string per round. Rejected because: (a) it duplicates data already in reviews + dispositions tables, (b) history strings can be 5-8 KB per round adding storage bloat, (c) reconstruction is deterministic from DB state so there's no fidelity risk.

Implementation: new `planner_auto/inspect.py` module with query functions, wired as a Click subgroup.

### 4. Review Loop Visibility

The engine outputs structured progress at three tiers. **Default is quiet/headless** (consistent with the planner-auto design philosophy for pipeline use). Rich output is opt-in.

**Default mode (headless — suitable for piping and .kafra pipeline):**
```
Round 1: NO_GO (5 issues) → revising...
Round 2: NO_GO (4 issues) → revising...
Round 3: GO (3 notes)
Converged in 3 rounds. $0.62 total.
```

One line per round. Machine-parseable. No noise.

**Verbose mode (--verbose):**
```
── Round 1 ─────────────────────────────────
Review:   NO_GO (5 issues: 1 critical, 4 major, filtered from 7 total)
  GPT model: gpt-5.4 (reasoning=high)
  Latency: 14.2s | Tokens: 1,280 (in:574, out:706) | Cost: $0.007
  Keep: [3 items] | Trim: [2 items]
Validating feedback...
  [1/5] ACCEPT: Missing error handling [critical] → "Add try/except in endpoint"
  [2/5] ACCEPT: No migration strategy [major] → "Add Alembic migration step"
  [3/5] DEFER:  Redis requirement [major] → "Deployment config, not feature scope"
  [4/5] ACCEPT: Incomplete API contract [major] → "Define request/response schemas"
  [5/5] REJECT: Observability overkill [minor] → "Already filtered by severity"
Revising plan (3 accepted, 1 deferred, 1 rejected)...
  Planner: claude-opus-4-6 (effort=medium, thinking=adaptive)
  Revision latency: 35.3s | Cost: $0.084
Draft #2 saved. Plan size: 8.5 KB (was 5.2 KB)
History context for next round: 3.2 KB (1 cumulative defer)
```

**Debug mode (--debug):** All of verbose plus:
- Raw GPT response text (full unstructured output)
- Full history context string sent to GPT
- Full revision prompt text sent to Claude
- Stack traces on all errors

**Security note:** Debug output can contain repository content from loaded context files, raw API responses, and potentially sensitive information from the plan itself. `--debug` output should be treated as sensitive and not shared in public channels or bug reports without redaction. The `inspect raw-response` command carries the same caveat.

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
planner-auto check          # Safe checks only (no API calls)
planner-auto check --probe  # Include live API round-trips
```

**Default (safe, no API calls):**
- `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` env var is set
- `OPENAI_API_KEY` env var is set (for reviewer)
- `claude` CLI binary found on PATH
- `openai` Python package importable
- SQLite DB path writable (`~/.planner-auto/planner.db`)
- Schema version is current (no pending migrations)

**With --probe (live API calls — costs a few cents):**
- Claude SDK subprocess can spawn and respond to a trivial prompt
- OpenAI API returns a response for a trivial prompt
- Measures and displays latency for both APIs

---

## Scope Boundaries

**In scope:**
- Shared root logger architecture with session-id context injection
- Per-command --verbose/--debug flags (no breaking CLI shape change)
- Structured logging in all modules (key decisions only)
- `inspect` CLI commands for DB state (reviews, dispositions, config, reconstructed history, raw responses, full dump)
- Review loop progress output (headless default / verbose / debug tiers)
- Error traceback printing on --debug
- `check` command for environment validation (safe by default, --probe for live API)
- Security note on --debug and inspect raw-response output

**Out of scope (future):**
- TUI dashboard with live log panel
- Remote log shipping (Sentry, etc.)
- Performance profiling / token cost analytics dashboard
- Log rotation / cleanup (files just accumulate for now)
- Persisting exact history context strings per round (reconstructed from DB instead)

---

## Estimated Impact

| Module | Changes |
|--------|---------|
| `cli.py` | Per-command --verbose/--debug, session logging setup, error traceback, check command, inspect subgroup |
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
| `logging.py` | Rewrite: shared root logger, SessionFilter, session-id context injection |
| **Tests** | ~20 new tests for inspect commands + check command |

---

## Priority

**High.** Without this, debugging a stuck review loop or unexpected convergence behavior requires manual DB queries and artifact inspection. Every issue found in the Plan 2 review rounds (disposition indexing, metadata gaps, round lookup) would have been caught earlier with proper logging.

This should be implemented before the first real user session — diagnosing issues in a 20-round complex planning session without observability would be painful.
