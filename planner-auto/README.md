# planner-auto

Automated planning session manager that produces milestone plans through interactive conversation with Claude, reviewed by GPT for quality. Plans are persisted in SQLite and exported as markdown artifacts ready for [orchestrator-auto](../orchestrator-auto/) to implement.

## How It Works

```
You describe a feature
    → Claude asks clarifying questions
        → Claude generates a milestone plan
            → GPT reviews and critiques
                → Claude revises based on feedback
                    → Repeat until GPT says GO
                        → Plan exported for orchestrator-auto
```

Each session follows a strict lifecycle: **SETUP → CONTEXT → DISCUSSION → PLANNING → REVIEW → COMPLETE**. All state lives in SQLite. File artifacts (plans, reviews, chat logs) are exported views, not source of truth.

## Installation

```bash
cd planner-auto/
pip install -e .           # Production
pip install -e ".[dev]"    # With pytest

# Required
export ANTHROPIC_API_KEY="your-key"     # For Claude (planner)
# OR
export CLAUDE_CODE_OAUTH_TOKEN="token"  # Claude Pro/Max subscription

# Required for Plan 2 (reviewer)
export OPENAI_API_KEY="your-key"        # For GPT-5.4 (reviewer)
```

## Quick Start

```bash
# Start a session
planner-auto start --project my-api

# Add context files
planner-auto add-context <session-id> --file src/app.py
planner-auto add-context <session-id> --file src/models.py
planner-auto add-context <session-id> --note "Uses PostgreSQL, deployed on AWS"

# Discuss the feature (interactive mode)
planner-auto discuss <session-id> --interactive
# Type your feature description, Claude asks questions
# Type /done when ready to move to planning

# Or one-shot discuss with auto-advance
planner-auto discuss <session-id> "Add user registration with email validation" --done

# Generate the plan
planner-auto generate <session-id>
planner-auto generate <session-id> --model claude-opus-4-6  # Override model

# Export artifacts
planner-auto export <session-id>
planner-auto export <session-id> --output-dir ./my-plans/

# Complete the session
planner-auto complete <session-id>
```

## CLI Reference

### Session Commands (Plan 1)

| Command | Description |
|---------|-------------|
| `start --project <name>` | Create a new planning session |
| `add-context <id> --file <path>` | Add a file to session context |
| `add-context <id> --note "text"` | Add a text note to session context |
| `discuss <id> "message"` | Send a single discussion message |
| `discuss <id> --interactive` | Enter interactive discussion mode (type `/done` to advance) |
| `discuss <id> "message" --done` | Send message and advance to PLANNING |
| `generate <id>` | Generate milestone plan from context + conversation |
| `generate <id> --model <model>` | Generate with a specific Claude model |
| `list` | List all sessions |
| `list --status active` | Filter sessions by status |
| `status <id>` | Show session details (phase, counts, blockers) |
| `resume <id>` | Resume a paused session (answer open blockers) |
| `export <id>` | Export session artifacts to disk |
| `export <id> --output-dir <path>` | Export to custom directory |
| `complete <id>` | Complete session (checks blockers, auto-exports) |

### Global Flags

| Flag | Description |
|------|-------------|
| `--db-path <path>` | Override database path (default: `~/.planner-auto/planner.db`) |
| `--verbose` | Print detailed output |
| `--debug` | Print debug-level output + stack traces |

### Review Commands (Plan 2)

| Command | Description |
|---------|-------------|
| `review <id>` | Run automated GPT review loop on current plan |
| `review <id> --fast` | Fast mode: 4 rounds, no history, basic prompt |
| `review <id> --max-rounds <n>` | Override round cap |
| `review <id> --no-review-history` | Disable review history context |
| `review <id> --reviewer-model <model>` | Override GPT model (default: gpt-5.4) |
| `review <id> --reviewer-reasoning <level>` | Reasoning effort (default: high) |
| `review <id> --complexity standard\|complex` | Override complexity detection |
| `review <id> --repo-root <path>` | Override repo root for .kafra handoff |

**Review loop features:**
- GPT-5.4 reviews with `resolution_guidance` + `target_section` per issue
- `keep/trim` sections: GPT tells Claude what to preserve and what to simplify
- `validate feedback`: Claude assesses each issue as ACCEPT / DEFER / REJECT
- Severity filtering: only `critical` + `major` issues reach Claude
- Review history: GPT sees previous plan + cumulative DEFER decisions across all rounds
- Complexity detection: auto-adjusts round cap (standard=8, complex=12)
- Convergence: GPT GO, or cap with zero criticals = accepted
- Cap with criticals = session paused for human review
- Final plan copied to `<repo>/.kafra/a-01-plans/`
- Review metadata persisted: model, cost, tokens, raw response per round

## Session Lifecycle

```
SETUP ──► CONTEXT ──► DISCUSSION ──► PLANNING ──► REVIEW ──► COMPLETE
                                        │            │          ▲
                                        │            └──────────┘
                                        │            (revise & re-review)
                                        └───────────────────────┘
                                        (skip review — direct complete)

Any phase can transition to PAUSED via blockers.
PAUSED only allows: resume, status, export.
```

| Phase | What Happens | Allowed Commands |
|-------|-------------|-----------------|
| SETUP | Session created, config saved | start, add-context, status, export |
| CONTEXT | Files and notes loaded | add-context, status, export |
| DISCUSSION | User describes feature, Claude asks questions | discuss, status, export |
| PLANNING | Context synthesized, plan generated | generate, review, complete, status, export |
| REVIEW | GPT review loop running | review, complete, status, export |
| COMPLETE | Session finished, artifacts exported | status, export |

## Database Schema

All state lives in SQLite at `~/.planner-auto/planner.db`. 7 tables:

| Table | Purpose |
|-------|---------|
| `sessions` | Session metadata: project, phase, status, timestamps |
| `messages` | Append-only conversation log (user + assistant turns) |
| `context_entries` | Loaded files, notes, and synthesized context |
| `plan_drafts` | Versioned plan content with draft number |
| `reviews` | Reviewer responses with verdict and issues (Plan 2) |
| `blockers` | Pause/resume lifecycle with source, question, answer |
| `session_config` | Config snapshot per session (models, prompt hashes) |

### Transaction Contract

CRUD functions do NOT auto-commit. Callers manage transactions:

```python
from planner_auto.db import transaction, add_message

# Single operation — explicit commit
add_message(conn, session_id, "user", "hello")
conn.commit()

# Atomic multi-operation — transaction context manager
with transaction(conn):
    add_message(conn, session_id, "user", user_input)
    add_message(conn, session_id, "assistant", response)
# Both committed together, or both rolled back on error
```

## Artifact Export

Artifacts are generated from the DB on demand. They are NOT read back by the tool.

```
~/.planner-auto/sessions/<session-id>/
├── chat.csv                  # Full conversation (id, timestamp, role, content)
├── context-summary.md        # Context entries grouped by type
├── plan-draft-1.md           # First plan draft
├── plan-draft-2.md           # Revised draft (after review, Plan 2)
├── ...
└── plan-draft-N.md           # Latest draft
```

With Plan 2 (reviewer), additional files:
```
├── a-01-plan.md              # Draft 1
├── a-02-review.md            # Review 1
├── a-03-plan.md              # Draft 2 (revised)
├── a-04-review.md            # Review 2
├── ...
└── a-<N>-plan-final.md       # GPT-approved final plan
```

## Architecture (For Agents & Devs)

```
planner_auto/
├── cli.py              # Click CLI — all user-facing commands
├── db.py               # SQLite schema (v2), CRUD, transaction(), schema migration
├── session.py          # SessionManager — phase transitions, pause/resume
├── state.py            # Phase/Status enums, transition rules, command permissions
├── agents.py           # discuss(), synthesize_context(), generate_plan()
├── sdk_wrapper.py      # Claude Agent SDK wrapper — retry, timeout, effort/thinking
├── prompts.py          # System prompts with version hashing
├── export.py           # Artifact export — plans, reviews, .kafra handoff
├── validation.py       # Plan format validation (milestone headers, checkboxes)
├── errors.py           # Custom exceptions (SDK, reviewer, session errors)
├── git_utils.py        # Repo root discovery (git rev-parse + --repo-root)
├── logging.py          # Session-scoped log file setup
├── reviewer/
│   ├── contract.py     # ReviewerContract ABC, ReviewerResponse, ReviewIssue
│   ├── direct_api.py   # DirectAPIAdapter — GPT-5.4 via OpenAI SDK
│   ├── parser.py       # Response parser (JSON/XML/free-form fallback)
│   └── prompts.py      # Reviewer system prompts (basic, guidance, keep_trim)
└── loop/
    ├── engine.py       # ReviewLoopEngine — review → revise → repeat
    ├── feedback.py     # Validate feedback (ACCEPT/DEFER/REJECT per issue)
    ├── history.py      # Review context builder (cumulative deferred)
    └── convergence.py  # Complexity detection, caps, fast mode
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| SQLite as canonical state | Files drift from tool state. DB is authoritative, files are exports. |
| Callers manage commits | Enables atomic multi-operation transactions without CRUD-level coupling. |
| Phase-gated commands | Prevents out-of-order operations (e.g., generate before discuss). |
| PLANNING→COMPLETE or PLANNING→REVIEW→COMPLETE | Direct complete skips review; `review` command runs the GPT loop. |
| `asyncio.wait_for` on SDK calls | Prevents hung SDK subprocess from blocking forever. |
| Prompt version hashing | Config snapshot per session enables reproducibility and regression detection. |

### For Agents

When working with planner-auto code:
- All DB access goes through `db.py` functions — never raw SQL in other modules
- All phase transitions go through `SessionManager` — never direct DB updates
- SDK calls go through `sdk_wrapper.py` — handles retry, timeout, error mapping
- Tests use in-memory SQLite (`:memory:`) with explicit commits
- Tests mock all SDK calls — no real API calls in test suite

## Development

```bash
# Setup
cd planner-auto/
pip install -e ".[dev]"

# Run tests
pytest tests/ -v                           # All tests
pytest tests/test_db.py -v                 # Single file
pytest tests/test_session.py::TestCheckCommand -v  # Single class
pytest -k "complete" -v                    # Filter by name

# Current test count: 283 passing
```

## Config Versioning

Every session captures its configuration at creation time in `session_config`:

```json
{
  "project": "my-api",
  "model_default": "claude-sonnet-4-6",
  "prompt_hashes": {
    "planner": "sha256:abc123...",
    "synthesis": "sha256:def456..."
  }
}
```

Plan 2 extends this with reviewer settings:

```json
{
  "project": "my-api",
  "model_default": "claude-opus-4-6",
  "repo_root": "/Users/me/my-api",
  "reviewer_model": "gpt-5.4",
  "reasoning_effort": "high",
  "prompt_mode": "keep_trim",
  "review_history": true,
  "validate_feedback": true,
  "filter_severity": ["critical", "major"],
  "fast_mode": false,
  "complexity": "standard",
  "max_rounds": 8
}
```

## Known Issues

### Claude Agent SDK + Opus + Thinking Mode + Large Prompts

When using Opus with adaptive thinking on complex feature descriptions (200+ words), the Claude Agent SDK subprocess can produce empty results or crash. This was discovered during POC dogfooding — the same feature description that works with Sonnet (max_turns=1) or in a direct SDK call fails when the e2e loop script spawns it as a background task with multiple active Claude sessions.

**Symptoms:**
- `ResultMessage.result` is empty (0 chars) despite `is_error=False`
- SDK subprocess exits with code 1: "Command failed with exit code 1"
- Opus uses all available turns on tool calls (Read, Write) instead of generating text

**Root cause:** The SDK spawns `claude` as a subprocess. Opus with thinking enabled is more aggressive about using tools (reading files, exploring the codebase) rather than generating text-only responses. With `max_turns=1`, it uses the single turn on a tool call and returns empty. With unlimited turns, it can spiral into extensive codebase exploration ($3.83 in one test) or crash when competing with other active Claude sessions for resources.

**Current workarounds:**
- `sdk_wrapper.py` defaults to unlimited turns when thinking is enabled (prevents the empty-result issue)
- Revision calls pass effort/thinking/max_turns through config
- For plan generation with very large feature descriptions, Sonnet at max_turns=1 is more reliable than Opus with thinking

**What we want (goal):** planner-auto should reliably handle complex planning sessions with Opus + thinking — these produce the highest quality plans (POC experiments showed 4→1→1 issue reduction with Opus vs 6→8→7 oscillation with Sonnet). The ideal fix would be:

1. **Text-only mode for plan generation** — a way to tell the SDK "thinking is OK, tool use is not" so Opus can reason deeply without reading files. `allowed_tools=[]` was attempted but crashes the SDK.
2. **Chunked context injection** — instead of passing 200+ word feature descriptions in a single prompt, inject context files separately via the SDK's context mechanism so the prompt stays small.
3. **Retry with fallback** — if Opus + thinking returns empty after N attempts, automatically fall back to Opus without thinking (effort=high, max_turns=1) which is still better than Sonnet.
4. **Session isolation** — ensure SDK subprocess doesn't conflict with other active Claude sessions (may require `--session-id` isolation or a dedicated subprocess pool).

This is a priority item for production readiness. The review loop itself works well — the bottleneck is reliable plan generation and revision with the strongest model configuration.

## Roadmap

- [x] **Plan 1: Session Core** — CLI, DB, lifecycle, context, plan generation, export
- [x] **Plan 2: Reviewer Adapter** — GPT review loop, convergence, .kafra handoff
- [ ] **Opus + thinking reliability** — Fix SDK subprocess issues for complex planning sessions
- [ ] **TUI mode** — Rich terminal UI (like orchestrator-auto's TUI)
- [ ] **Telegram notifications** — Notify on plan approval or blocker
- [ ] **Homebrew formula** — `brew install planner-auto`
