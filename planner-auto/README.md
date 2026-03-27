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

### Implemented (Plan 1)

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

### Coming in Plan 2 (Reviewer Adapter)

| Command | Description |
|---------|-------------|
| `review <id>` | Run automated GPT review loop on current plan |
| `review <id> --fast` | Fast mode: skip history, cap at 4 rounds |
| `review <id> --max-rounds <n>` | Set round cap (default: 8 standard, 12 complex) |
| `review <id> --no-review-history` | Disable review history context |

**Review loop features (Plan 2):**
- GPT-5.4 reviews with `resolution_guidance` + `target_section` per issue
- `keep/trim` sections: GPT tells Claude what to preserve and what to simplify
- `validate feedback`: Claude assesses each issue as ACCEPT / DEFER / REJECT
- Severity filtering: only `critical` + `major` issues reach Claude
- Review history: GPT sees previous plan + previous review per round
- Complexity detection: auto-adjusts round cap based on feature keywords
- Convergence: GPT GO or zero-critical threshold
- Final plan copied to `<repo>/.kafra/a-01-plans/`

## Session Lifecycle

```
SETUP ──► CONTEXT ──► DISCUSSION ──► PLANNING ──► REVIEW ──► COMPLETE
                                        │                      ▲
                                        └──────────────────────┘
                                        (Plan 1: direct path)

Any phase can transition to PAUSED via blockers.
PAUSED only allows: resume, status, export.
```

| Phase | What Happens | Allowed Commands |
|-------|-------------|-----------------|
| SETUP | Session created, config saved | start, add-context, status, export |
| CONTEXT | Files and notes loaded | add-context, status, export |
| DISCUSSION | User describes feature, Claude asks questions | discuss, status, export |
| PLANNING | Context synthesized, plan generated | generate, complete, status, export |
| REVIEW | GPT review loop (Plan 2) | review, complete, status, export |
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
├── db.py               # SQLite schema, CRUD, transaction()
├── session.py          # SessionManager — phase transitions, pause/resume
├── state.py            # Phase/Status enums, transition rules, command permissions
├── agents.py           # discuss(), synthesize_context(), generate_plan()
├── sdk_wrapper.py      # Claude Agent SDK wrapper — retry, timeout, error handling
├── prompts.py          # System prompts with version hashing
├── export.py           # Artifact file generation from DB
├── validation.py       # Plan format validation (milestone headers, checkboxes)
├── errors.py           # Custom exceptions (SDKError, SessionStateError, etc.)
└── logging.py          # Session-scoped log file setup
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| SQLite as canonical state | Files drift from tool state. DB is authoritative, files are exports. |
| Callers manage commits | Enables atomic multi-operation transactions without CRUD-level coupling. |
| Phase-gated commands | Prevents out-of-order operations (e.g., generate before discuss). |
| PLANNING→COMPLETE direct path | Plan 1 skips REVIEW. Plan 2 adds the review loop. |
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

# Current test count: 103 passing
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

Plan 2 will extend this with: reviewer model, effort levels, thinking config, feature flags (history, keep/trim, validate feedback, severity filter).

## Roadmap

- [x] **Plan 1: Session Core** — CLI, DB, lifecycle, context, plan generation, export
- [ ] **Plan 2: Reviewer Adapter** — GPT review loop, convergence, .kafra handoff
- [ ] **TUI mode** — Rich terminal UI (like orchestrator-auto's TUI)
- [ ] **Telegram notifications** — Notify on plan approval or blocker
