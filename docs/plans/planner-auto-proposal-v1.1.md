# Planner Auto: Automated Plan Generation Pipeline — v1.1

**Revision history:**
- v1.0 — Initial proposal (original idea, manual workflow, automation design)
- v1.1 — Incorporates senior dev review feedback, Kagi research findings, and architectural refinements

**Companion docs:**
- [v1.0 — Original proposal](planner-auto-proposal-v1.md)
- [Research findings](planner-auto-proposal-v1-research.md)

---

## Problem

Before `orchestrator-auto` can execute, it needs a high-quality milestone plan. Today that plan is created manually through a multi-step, multi-agent review loop involving copy-paste between Claude, OpenCode, and the terminal. This tool automates that loop.

---

## Current Manual Workflow

_(Unchanged from v1.0 — see original for full details)_

1. Load context files into Claude, confirm understanding
2. Describe feature/issue, Claude generates milestone plan
3. Send plan to GPT-5.4 (via OpenCode) for go/no-go review
4. If no-go: copy feedback to Claude, assess validity, revise plan
5. Repeat 3-4 until reviewer says "go"

---

## Architecture: Session Core + Reviewer Adapter

v1.1 reframes the architecture as two layers with a clean interface between them, based on senior dev feedback.

```
┌─────────────────────────────────────────────────────────────┐
│                       PLANNER-AUTO                           │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              SESSION CORE (Plan 1)                     │  │
│  │                                                       │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  │  │
│  │  │  Session     │  │  Planner     │  │  Artifact   │  │  │
│  │  │  Engine      │  │  Interaction │  │  Exporter   │  │  │
│  │  │             │  │  Loop        │  │             │  │  │
│  │  │  • SQLite   │  │  • Context   │  │  • chat.csv │  │  │
│  │  │    state    │  │    loading   │  │  • plan.md  │  │  │
│  │  │  • Session  │  │  • Feature   │  │  • review   │  │  │
│  │  │    CRUD     │  │    discussion│  │    .md      │  │  │
│  │  │  • Message  │  │  • Plan      │  │  • context  │  │  │
│  │  │    log      │  │    generation│  │    .md      │  │  │
│  │  └─────────────┘  └──────────────┘  └─────────────┘  │  │
│  │                          │                            │  │
│  │                          ▼                            │  │
│  │              ┌───────────────────────┐                │  │
│  │              │   ReviewerContract    │                │  │
│  │              │   (interface)         │                │  │
│  │              └───────────┬───────────┘                │  │
│  └──────────────────────────┼────────────────────────────┘  │
│                             │                               │
│  ┌──────────────────────────┼────────────────────────────┐  │
│  │          REVIEWER ADAPTER (Plan 2)                     │  │
│  │                          │                             │  │
│  │              ┌───────────▼───────────┐                 │  │
│  │              │  ReviewerAdapter      │                 │  │
│  │              │  (implements contract)│                 │  │
│  │              └───────────┬───────────┘                 │  │
│  │                          │                             │  │
│  │           ┌──────────────┼──────────────┐              │  │
│  │           ▼              ▼              ▼              │  │
│  │    ┌────────────┐ ┌────────────┐ ┌────────────┐       │  │
│  │    │ Codex MCP  │ │ Direct API │ │ OpenCode   │       │  │
│  │    │ (primary)  │ │ (fallback) │ │ (future)   │       │  │
│  │    └────────────┘ └────────────┘ └────────────┘       │  │
│  │                          │                             │  │
│  │                          ▼                             │  │
│  │              ┌───────────────────────┐                 │  │
│  │              │  Review-Fix Loop      │                 │  │
│  │              │  Orchestrator         │                 │  │
│  │              └───────────┬───────────┘                 │  │
│  │                          │                             │  │
│  │                          ▼                             │  │
│  │              Copy final plan to                        │  │
│  │              <repo>/.kafra/a-01-plans/                 │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Key change from v1.0:** The boundary is "session core" vs "reviewer adapter", not "phases 1-4" vs "phases 5-8". This makes the reviewer pluggable behind a contract interface.

---

## Canonical State: SQLite, Not Files

**v1.0 approach (superseded):** Files as live state — `chat.csv` and `context-tracker-live.md` are the source of truth.

**v1.1 approach:** SQLite as canonical state. File artifacts are exported views.

| Aspect | v1.0 | v1.1 |
|--------|------|------|
| Source of truth | `chat.csv`, `context-tracker-live.md` | SQLite database |
| File artifacts | Live state, read/written by tool | Exported views for audit and human inspection |
| Risk | Drift between tool state and file content | None — DB is authoritative, exports are snapshots |
| Consistency with orchestrator-auto | Different approach | Same pattern (SQLite sessions/messages/milestones) |

### Database Tables (planner-auto)

| Table | Purpose |
|-------|---------|
| `sessions` | Session metadata, phase, status |
| `messages` | Append-only conversation log (replaces chat.csv as state) |
| `context_entries` | Loaded files, entities, decisions (replaces context-tracker-live.md as state) |
| `plan_drafts` | Versioned plan content with draft number |
| `reviews` | Reviewer responses with parsed verdict and issues |

### Exported Artifacts

Artifacts are generated from the DB on demand or at phase transitions. They are **not read back** by the tool.

| Artifact | Generated When | Content |
|----------|---------------|---------|
| `chat.csv` | On export or session end | Full conversation log from `messages` table |
| `context-summary.md` | On export or before plan generation | Synthesized context from `context_entries` table |
| `a-01-plan.md` | After plan generation | Plan content from `plan_drafts` table |
| `a-02-review.md` | After each review round | Review content from `reviews` table |
| `a-<N>-plan-final.md` | On reviewer GO verdict | Final plan from `plan_drafts` table |

---

## Reviewer Contract

Defined in Plan 1 (session core), implemented in Plan 2 (reviewer adapter). This enables stubbing and manual testing before the real integration lands.

### ReviewerResponse Schema

```
ReviewerResponse:
  verdict: GO | NO_GO
  issues: [
    {
      severity: critical | major | minor
      description: str
      rationale: str
    }
  ]
  summary: str
```

### Edge Cases

| Scenario | Behavior |
|----------|----------|
| Malformed reviewer output | Parse failure → treat as NO_GO with a single `critical` issue: "Reviewer output could not be parsed" |
| Reviewer timeout / error | Retry once → if still fails, pause session as blocker for human intervention |
| GO with non-blocking notes | Treat as GO. Notes are logged in `reviews` table but do not trigger a revision round |
| All issues are `minor` only | Still NO_GO — planner assesses and may choose to accept minors, but the loop continues |

---

## Context Tracking: On-Demand, Not Per-Response

**v1.0 approach (deferred):** Sub-agent updates `context-tracker-live.md` after every agent response.

**v1.1 approach:** Append-only conversation logging to DB. Context synthesis happens on-demand at key moments, not after every response.

| Trigger | Action |
|---------|--------|
| User adds files | Log files to `context_entries` table |
| Before plan generation | Synthesize full context from `messages` + `context_entries` |
| On export | Generate `context-summary.md` from DB |

**Why:** Per-response tracking adds latency and fragility for marginal v1 benefit. Append-only logging captures everything; synthesis when needed is cheaper and safer.

The per-response sub-agent tracker remains a backlog item for post-v1 optimization.

---

## Automated Flow (Revised)

### Phase 1: Session Setup

1. Create session in SQLite database
2. Initialize session state: `phase=setup`, `status=active`

### Phase 2: Context Loading

3. User runs `planner-auto` and adds files for context
4. Files logged to `context_entries` table
5. Planner agent reads files, confirms understanding
6. Confirmation logged to `messages` table

### Phase 3: Feature Discussion

7. User describes feature or issue
8. Planner agent asks clarifying questions, builds understanding
9. All exchanges logged to `messages` table (append-only)

### Phase 4: Plan Generation

10. Context synthesized from `messages` + `context_entries`
11. Agent generates milestone plan (follows `CLAUDE_orch_v2.md` template)
12. Plan stored in `plan_drafts` table (draft_number=1)
13. **Artifact exported:** `a-01-plan.md`
14. Plan 1 scope ends here if no reviewer is configured

### Phase 5: Cross-Model Review (Plan 2)

15. Reviewer adapter invokes reviewer (Codex MCP primary, direct API fallback)
16. Reviewer prompt: structured request referencing plan content
17. Response parsed into `ReviewerResponse` schema
18. Review stored in `reviews` table (review_number=1)
19. **Artifact exported:** `a-02-review.md`

### Phase 6: Feedback Loop (Plan 2)

20. Planner agent reads review from `reviews` table
21. Assesses each issue by severity — applies valid feedback, discards noise
22. Produces revised plan, stored in `plan_drafts` (draft_number=2)
23. **Artifact exported:** `a-03-plan.md`

### Phase 7: Repeat Until GO (Plan 2)

24. Phases 5-6 repeat. Artifacts exported at each step:

```
a-01-plan.md      ← plan_drafts (draft 1)
a-02-review.md    ← reviews (review 1)
a-03-plan.md      ← plan_drafts (draft 2)
a-04-review.md    ← reviews (review 2)
a-05-plan.md      ← plan_drafts (draft 3)
a-06-review.md    ← reviews (review 3) → GO
```

25. When reviewer returns GO, final plan marked in DB

### Phase 8: Finalize (Plan 2)

26. **Artifact exported:** `a-<N>-plan-final.md`
27. Final plan copied to `<repo>/.kafra/a-01-plans/`
28. Session marked complete

---

## Artifact Export Timing

_Requested by senior dev reviewer for audit model clarity._

| Event | Artifacts Exported | Plan |
|-------|-------------------|------|
| Session created | _(none — DB only)_ | 1 |
| Context confirmed | _(none — DB only)_ | 1 |
| Plan generated | `a-01-plan.md` | 1 |
| Session exported (manual) | `chat.csv`, `context-summary.md` | 1 |
| Review received | `a-<N>-review.md` | 2 |
| Plan revised | `a-<N>-plan.md` | 2 |
| Reviewer says GO | `a-<N>-plan-final.md` | 2 |
| Handoff to .kafra | Copy of `a-<N>-plan-final.md` | 2 |

---

## Directory Structure (Revised)

### Session Artifacts (exported from DB)

```
~/.planner-auto/
├── planner.db                   # SQLite — canonical state for all sessions
└── sessions/
    └── <session-id>/
        ├── chat.csv             # Exported conversation log
        ├── context-summary.md   # Exported context synthesis
        ├── a-01-plan.md         # Exported plan draft 1
        ├── a-02-review.md       # Exported review 1
        ├── a-03-plan.md         # Exported plan draft 2 (revised)
        ├── ...                  # Continues until GO
        └── a-<N>-plan-final.md  # Exported final approved plan
```

Note: Changed from `~/.orchestrator-auto/` to `~/.planner-auto/` to avoid confusion with orchestrator-auto's own `~/.claude_orchestrator/` directory.

### Pipeline Folders (broader .kafra pipeline — out of scope)

```
<repo>/.kafra/
├── a-01-plans/       # Backlog: plans awaiting implementation
├── a-02-ongoing/     # Implementation: orchestrator watch picks up plans here
├── a-03-for-review/  # Post-implementation review
├── a-04-done/        # Completed and reviewed
└── a-05-archive/     # Historical
```

planner-auto's only interaction with `.kafra/` is copying the final plan to `a-01-plans/` (Plan 2 scope).

---

## Implementation Split (Revised)

### Plan 1: Session Core

| Aspect | Detail |
|--------|--------|
| **Owns** | Session engine (SQLite), planner interaction loop, artifact exporter, `ReviewerContract` interface definition |
| **Delivers** | `planner-auto` CLI that produces a structured milestone plan through interactive conversation, with DB persistence and artifact export |
| **"Done" means** | A finalized plan exists in `plan_drafts` table and is exported as `a-01-plan.md` in the session folder |
| **Does NOT include** | Reviewer invocation, review-fix loop, .kafra handoff |

Plan 1 builds the session model, artifact versioning, and planner loop so that a reviewer can plug in later behind a clean interface. The `ReviewerContract` is defined here (schema + edge case behavior) but not implemented.

### Plan 2: Reviewer Adapter

| Aspect | Detail |
|--------|--------|
| **Owns** | `ReviewerAdapter` implementation (Codex MCP primary, direct API fallback), review-fix loop orchestration, .kafra handoff |
| **Delivers** | Full automated cross-model review loop bolted onto Plan 1 |
| **"Done" means** | Plan passes go/no-go, `a-<N>-plan-final.md` exported and copied to `<repo>/.kafra/a-01-plans/` |
| **Depends on** | Plan 1's session engine and `ReviewerContract` interface |

### Cross-Model Integration (Research-Informed)

Based on [research findings](planner-auto-proposal-v1-research.md), the reviewer integration strategy has changed from v1.0:

| Approach | v1.0 | v1.1 |
|----------|------|------|
| Primary | OpenCode subprocess | **Codex MCP server** (proven by ARIS project) |
| Fallback | _(none)_ | **Direct OpenAI API** (plan text passed as prompt content) |
| Avoided | _(not considered)_ | OpenCode subprocess (known hanging issues) |

**Prior art:** [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) uses Codex MCP for Claude ↔ GPT cross-model review loops in ML research. Two papers accepted using this approach.

---

## Risk Consideration (Revised)

| Risk | Impact | Mitigation | Status |
|------|--------|------------|--------|
| OpenCode subprocess hangs | ~~Blocks Plan 2~~ | **Eliminated** — switched to Codex MCP | Resolved by research |
| Codex MCP setup complexity | Adds onboarding friction | Direct API fallback if MCP unavailable | New in v1.1 |
| GPT review output unpredictable | Complicates parsing | `ReviewerContract` schema + structured prompt + fallback to keyword matching | Strengthened in v1.1 |
| Per-response sub-agent latency | Affects Plan 1 UX | **Deferred** to post-v1 optimization | Descoped in v1.1 |
| File/DB state drift | Tool and artifacts disagree | **Eliminated** — DB is canonical, files are exports | Resolved in v1.1 |

## Pre-Implementation POCs (Revised)

| POC | Unknown | What to Validate | Blocks |
|-----|---------|-----------------|--------|
| 1. Codex MCP invocation | Can Claude invoke GPT-5.4 through Codex MCP and capture structured output? | MCP setup, prompt passthrough, response capture | Plan 2 |
| 2. Go/no-go parsing | Can reviewer output be reliably parsed into `ReviewerResponse` schema? | Structured prompt engineering, edge case handling | Plan 2 |
| 3. _(removed)_ | ~~Sub-agent file updates~~ | Deferred to post-v1 | — |

**POC location:** `scripts/poc/planner-auto/`

---

## Pipeline Context (Out of Scope)

planner-auto is one tool in a broader `.kafra` pipeline. Documented here for context only.

```
planner-auto → a-01-plans/ → PM agent → a-02-ongoing/ → orchestrator watch → a-03-for-review/ → reviewer-fixer-auto → a-04-done/ → PM agent → a-05-archive/
```

| Tool | Status | Pipeline Role |
|------|--------|---------------|
| `orchestrator-auto` | Built | Executes plans (implementation in `a-02-ongoing/`) |
| `planner-auto` | To be built | Generates reviewed plans (feeds `a-01-plans/`) |
| `reviewer-fixer-auto` | Not yet planned | Post-implementation review (processes `a-03-for-review/`) |
| PM agent | Not yet planned | Traffic controller across all pipeline stages |

---

## Changes from v1.0

| Area | v1.0 | v1.1 | Reason |
|------|------|------|--------|
| Architecture framing | Phases 1-4 vs 5-8 | Session Core vs Reviewer Adapter | Senior dev: architectural boundary, not chronological |
| Canonical state | Files (`chat.csv`, `context-tracker-live.md`) | SQLite database | Senior dev: avoid file/state drift, align with orchestrator-auto |
| File artifacts | Live state | Exported views from DB | Senior dev: files are audit trail, not source of truth |
| Context tracking | Sub-agent after every response | Append-only logging + on-demand synthesis | Senior dev: defer optimization, reduce v1 fragility |
| Reviewer contract | Implicit | Explicit schema with edge cases | Senior dev: unblock testing, define parsing target early |
| .kafra handoff | Ambiguous (Plan 1 or future) | Explicitly Plan 2 | Senior dev: clarify "done" boundary |
| Cross-model integration | OpenCode subprocess | Codex MCP (primary) + Direct API (fallback) | Research: subprocess has known bugs, ARIS proves MCP works |
| Home directory | `~/.orchestrator-auto/` | `~/.planner-auto/` | Avoid collision with orchestrator-auto |
| Artifact export timing | Not specified | Explicit table per event | Senior dev: audit model clarity |
