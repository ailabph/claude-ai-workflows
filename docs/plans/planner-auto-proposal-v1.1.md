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
│  │    │ Direct API │ │ Codex MCP  │ │ OpenCode   │       │  │
│  │    │ (ship      │ │ (full      │ │ HTTP       │       │  │
│  │    │  first)    │ │  capability│ │ (alternative│       │  │
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
| `blockers` | Failure-triggered pause records with source, question, answer, and resolution status (validated by POC 5a) |

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

15. Reviewer adapter invokes reviewer (Direct API by default in v1; Codex MCP when reviewer tool access is needed; OpenCode HTTP as an alternative adapter)
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
| **Owns** | `ReviewerAdapter` implementation (Direct API ship-first, Codex MCP full-capability upgrade path, OpenCode HTTP alternative), review-fix loop orchestration, .kafra handoff |
| **Delivers** | Full automated cross-model review loop bolted onto Plan 1 |
| **"Done" means** | Plan passes go/no-go, `a-<N>-plan-final.md` exported and copied to `<repo>/.kafra/a-01-plans/` |
| **Depends on** | Plan 1's session engine and `ReviewerContract` interface |

### Cross-Model Integration (Research-Informed)

Based on [research findings](planner-auto-proposal-v1-research.md), the reviewer integration strategy has changed from v1.0:

| Approach | v1.0 | v1.1 |
|----------|------|------|
| Primary | OpenCode subprocess | **Direct OpenAI API** (fastest to ship, plan text as prompt content) |
| Full-capability | _(none)_ | **Codex MCP server** (if reviewer needs tool/repo access, proven by ARIS) |
| Alternative | _(none)_ | **OpenCode HTTP server** (for teams already invested in OpenCode) |
| Avoided | _(not considered)_ | OpenCode subprocess (known hanging issues — [#11891](https://github.com/anomalyco/opencode/issues/11891), [#17516](https://github.com/anomalyco/opencode/issues/17516)) |

**Recommended rollout:** Ship with Direct API first to prove the review loop and validate the `ReviewerContract`. Upgrade to Codex MCP if reviewer tool access becomes a real requirement. The adapter interface makes this swap transparent.

**Prior art:** [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) uses Codex MCP for Claude ↔ GPT cross-model review loops in ML research. Two papers accepted using this approach.

---

## Runtime Modes and Observability

planner-auto runs headless by default (minimal output, suitable for scripting and unattended use). Optional flags enable richer output for debugging and monitoring.

### Runtime Modes

| Flag | Mode | Output Behavior |
|------|------|----------------|
| _(default)_ | Headless | Phase transitions and final result only. Suitable for piping, scripting, CI. |
| `--verbose` | Verbose | Streams agent responses, logs DB writes, artifact exports, reviewer issue lists |
| `--tui` | TUI | Rich terminal UI with panels for conversation, status, logs, reviewer rounds |
| `--debug` | Debug | Full stack traces printed to stderr + verbose file logging |

Flags are combinable: `--tui --debug` gives the TUI with debug-level log panel.

### Session-Scoped Log Files

A log file is **always written** for every session, regardless of runtime mode:

```
~/.planner-auto/logs/<session-id>.log
```

### What Gets Logged

| Category | Logged Events | Verbosity |
|----------|--------------|-----------|
| Phase transitions | `setup → context → discussion → planning → review → complete` | Always |
| DB operations | Session created, messages appended, plan_drafts stored, reviews parsed, context synthesized | `--verbose` and above |
| Artifact exports | Which files written, paths, timestamps | `--verbose` and above |
| Agent responses | Full planner agent output (streaming) | `--verbose` and above |
| Reviewer invocation | Raw request prompt, raw response, parsed `ReviewerResponse`, invocation method (MCP/API) | `--verbose` and above |
| Reviewer round summary | "Review 1: NO_GO — 1 critical, 2 major, 0 minor" | Always |
| Errors | Error message + context | Always (stack traces only with `--debug`) |

### Log Levels

| Level | Written to log file | Printed to terminal |
|-------|--------------------|--------------------|
| ERROR | Always | Always (stderr) |
| WARN | Always | Always (stderr) |
| INFO | Always | `--verbose` / `--tui` / `--debug` |
| DEBUG | `--debug` only | `--debug` only |

### Debugging Reviewer Integration (Plan 2)

The reviewer round is the most likely failure point. Logs capture the full round-trip:

```
[INFO]  reviewer.invoke: method=codex_mcp, plan_draft=3
[DEBUG] reviewer.request: prompt="Assess if plan is go/no-go..."
[DEBUG] reviewer.raw_response: "The plan has several issues..."
[INFO]  reviewer.parsed: verdict=NO_GO, issues=3 (1 critical, 1 major, 1 minor)
[INFO]  artifact.export: a-06-review.md → ~/.planner-auto/sessions/abc123/
```

If parsing fails:
```
[ERROR] reviewer.parse_failed: could not extract verdict from response
[DEBUG] reviewer.raw_response: <full raw text>
[WARN]  reviewer.fallback: treating as NO_GO with parse-failure issue
```

### Consistency with orchestrator-auto

| Feature | orchestrator-auto | planner-auto |
|---------|-------------------|--------------|
| Debug flag | `--debug` | `--debug` |
| TUI flag | `--tui` | `--tui` |
| Log location | `~/.claude_orchestrator/logs/` | `~/.planner-auto/logs/` |
| Log naming | `error_<session-id>_<timestamp>.log` | `<session-id>.log` |
| Verbose streaming | Default (always streams) | `--verbose` (headless is quiet by default) |

Note: planner-auto defaults to headless/quiet because it's designed to run as part of the `.kafra` pipeline where output noise is undesirable. orchestrator-auto defaults to streaming because it's typically run interactively.

---

## Risk Consideration (Revised)

| Risk | Impact | Mitigation | Status |
|------|--------|------------|--------|
| OpenCode subprocess hangs | ~~Blocks Plan 2~~ | **Eliminated** — shipping Direct API first, subprocess avoided entirely | Resolved by research |
| Codex MCP setup complexity | Adds onboarding friction for full-capability adapter | Direct API ships first; Codex MCP is an upgrade path, not a prerequisite | New in v1.1 |
| GPT review output unpredictable | Complicates parsing | `ReviewerContract` schema + structured prompt + fallback to keyword matching | Strengthened in v1.1 |
| Per-response sub-agent latency | Affects Plan 1 UX | **Deferred** to post-v1 optimization | Descoped in v1.1 |
| File/DB state drift | Tool and artifacts disagree | **Eliminated** — DB is canonical, files are exports | Resolved in v1.1 |
| Review loop non-convergence | Loop runs indefinitely, cost escalates | Convergence strategy required (see below) | **New — discovered by POC 5b** |

---

## Review Loop Convergence (POC 5b Findings)

POC 5b ran the full plan→review→revise loop with real API calls (Claude Sonnet + GPT-5.4). **The loop did not converge in 6 rounds** ($0.785 total, 13 minutes). This matches the manual experience: planning takes ~30 minutes but eventually produces a high-quality plan that orchestrator-auto implements well.

### What Happens in the Loop

| Round | Issues | Plan Size | Revision Time | Round Cost |
|-------|--------|-----------|---------------|------------|
| 1 | 9 | 4 KB | 43s | $0.062 |
| 2 | 8 | 8 KB | 66s | $0.084 |
| 3 | 6 | 11 KB | 92s | $0.113 |
| 4 | 9 | 17 KB | 142s | $0.157 |
| 5 | 6 | 21 KB | 152s | $0.164 |
| 6 | 6 | 30 KB | 183s | $0.184 |

**Issue count oscillates (9→8→6→9→6→6)** instead of converging to zero. Plan size grows 7.5x (4KB→30KB).

### Why It Doesn't Converge

Analysis of all 6 review artifacts revealed three root causes:

**1. Claude adds features that create new issues.** When Claude fixes "authentication incomplete," it adds JWT with refresh tokens, which GPT then flags for "missing revocation strategy." Each fix expands the attack surface for the reviewer.

**2. GPT critiques symptoms, not root causes.** Round 1: "Migration strategy undefined." Round 4: "Alembic couples to app code." Round 6: "Migration gates depend on manual discipline." Same domain, different angle each round — GPT never says "here's what would make this acceptable."

**3. Plan bloat reduces revision quality.** By round 4+, Claude is revising a 17KB+ plan and spending 140s+ per revision. Larger plans mean more surface area for GPT to critique, creating a positive feedback loop.

### Issue Lifecycle (6 rounds, 40+ unique issues)

| Category | Count | Examples |
|----------|-------|---------|
| Resolved by round 6 | 6 (15%) | Logging, schema contracts, password policy — mostly documentation/clarification issues |
| Persistent 3+ rounds | 16+ (40%) | Migration safety, rate limiting, auth flow — architectural concerns that specification can't close |
| Newly introduced per round | 3-4 avg | Each revision creates new failure modes GPT catches |

### Convergence Experiments (POC 5b)

Three approaches were tested in A/B experiments:

**Experiment 1: Baseline (no intervention)**
- Issue trend (3 rounds): 6→8→7 (oscillating)
- Issue trend (6 rounds): 9→8→6→9→6→6 (oscillating, never converges)
- Cost: $0.26 (3r), $0.79 (6r)

**Experiment 2: Self-review (self-check → repair → wrap-up after each revision)**
- Issue trend (3 rounds): 7→6→7 (no improvement over baseline)
- Plan bloat: 29% smaller (wrap-up pass works)
- Cost: $0.79 (3r) — **3x baseline, not justified**
- Verdict: Full self-review too expensive. Standalone wrap-up pass is the useful piece.

**Experiment 3: Resolution guidance (GPT provides acceptance criteria per issue)**
- Issue trend (3 rounds): 8→5→5 (declining — best trajectory)
- Issue trend (6 rounds): 7→7→6→6→7→5 (marginally better than baseline)
- Cost: $0.31 (3r, +17%), $0.83 (6r, +6%)
- Plan bloat: same or slightly worse (guidance doesn't help bloat)
- Verdict: Helps most in first 3 rounds. Over 6 rounds, both variants stabilize around 5-6 issues.

**Experiment 4: Opus + high effort + thinking + guidance (8 rounds)**
- Planner: Claude Opus 4.6, effort=high, thinking=adaptive
- Reviewer: GPT-5.4, reasoning_effort=high, resolution guidance ON
- Issue trend (8 rounds): **4→1→1→1→4→1→4→5**
- Gets to **1 issue by round 2** — dramatically better than Sonnet's 5-8
- Oscillation pattern: GPT periodically finds new angles, Opus resolves them quickly
- Cost: $1.15 (8r) — Opus ~4x more per revision than Sonnet
- Cheap rounds ($0.02) = targeted fix; expensive rounds ($0.19) = section rewrite
- **Still doesn't converge to GO** — confirms threshold stop is required regardless of model

**Cross-configuration summary (3-round window):**

| Configuration | Issues R1/R2/R3 | Cost (3r) | Model Cost |
|---------------|----------------|-----------|------------|
| Sonnet baseline | 6/8/7 | $0.26 | Low |
| Sonnet + guidance | 8/5/5 | $0.31 | Low |
| **Opus + high + thinking + guidance** | **4/1/1** | ~$0.33 | High |

**Experiment 7: CONVERGED** — With the full feature set and a constrained planner prompt, GPT said GO at round 5 for the first time across all experiments.

| # | Configuration | Issues | Converged? | Cost | Time | Plan |
|---|---------------|--------|-----------|------|------|------|
| 1 | Sonnet baseline | 6→8→7 (3r) | No | $0.26 | 254s | 15 KB |
| 2 | Sonnet + self-review | 7→6→7 (3r) | No | $0.79 | 700s | 11 KB |
| 3 | Sonnet + guidance | 8→5→5 (3r) | No | $0.31 | 311s | 15 KB |
| 4 | Opus high mt=1 | 4→1→1→1→4→1→4→5 (8r) | No | $1.15 | 595s | 30 KB |
| 5 | Opus high mt=10 | 5→4→4→...→3 (10r) | No | $3.83 | 2959s | 29 KB |
| 6 | Opus med mt=5, old prompt | 5→6→4→4→4→4 (6r) | No | $1.67 | 1286s | ~25 KB |
| **7** | **Opus med mt=2, constrained** | **5→4→4→4→GO** | **YES (R5)** | **$0.87** | **791s** | **10 KB** |

### What Made It Converge (Experiment 7)

Six factors combined, all required:

| Factor | What | Impact |
|--------|------|--------|
| **Constrained planner prompt** | Max 8 tasks/milestone, 1-2 sentences per task, under 3000 words, "implement ONLY what was requested" | Plan stayed 10 KB (vs 30 KB unconstrained). Prevented scope creep. |
| **Validate feedback** | Claude assesses each issue: ACCEPT (fix), DEFER (out of scope), REJECT (not valid) | Claude deferred migration strategy and partial-accepted Redis requirement. Stopped blindly adding complexity. |
| **Filter severity** | Only critical + major issues passed to Claude | Removed minor noise. GPT still reports minors in review but Claude doesn't act on them. |
| **Keep/trim** | GPT lists what to preserve and what to simplify | Prevented good content from being accidentally removed. Actively reduced bloat. |
| **Resolution guidance** | GPT states acceptance criteria per issue | Claude had concrete targets instead of guessing what "resolved" means. |
| **max_turns=2** | Thinking needs 2 turns (think + respond), no more | Tight text-only responses. No tool-use sprawl that inflated Experiment 5 to $3.83. |

### Convergence Strategy for v1 (Final)

Based on all seven experiments, the recommended v1 default:

| Component | Setting | Why |
|-----------|---------|-----|
| **Planner model** | `claude-opus-4-6` | Opus resolves issues faster than Sonnet (fewer rounds = lower total cost) |
| **Planner effort** | `medium` | High effort + max_turns=10 caused $3.83 blowout; medium is sufficient |
| **Planner thinking** | `adaptive` | Enables deeper reasoning; combined with max_turns=2 stays tight |
| **max_turns** | `2` | Enough for think + respond; prevents tool-use cost creep |
| **Reviewer model** | `gpt-5.4` | Consistent, thorough reviewer |
| **Reviewer reasoning** | `high` | More structured, stable reviews |
| **Resolution guidance** | ON | Acceptance criteria per issue |
| **Keep/trim** | ON | Preserve good content, flag bloat |
| **Validate feedback** | ON | Claude filters invalid/out-of-scope feedback |
| **Severity filter** | `critical,major` | Ignore minor noise |
| **Constrained prompt** | ON | Size + scope limits on plan output |
| **Review history** | ON | GPT sees previous plan + previous review per round; prevents re-raising resolved issues |
| **Hard cap** | 5-6 standard, 20 complex | Safety net; standard converges at R5, complex may need 10-20 |
| **Human fallback** | If criticals persist at cap | Last resort |

### Cross-Feature Validation

The winning config was tested on a second feature domain (webhook receiver with signature validation, event queue, retry logic) to prevent overfitting. Results:

| Feature | Complexity | Config | Rounds | GPT GO? | Cost | Plan Quality |
|---------|-----------|--------|--------|---------|------|-------------|
| Registration | Standard | Winning config | R5 | YES | $0.87 | Implementation-ready |
| Webhook | High | Same, no history | 10 (capped) | No | $2.84 | Excellent but oscillating |
| **Webhook** | **High** | **Same + review history** | **R4** | **YES** | **$0.62** | **Implementation-ready** |

**Key findings:**
- Config is **not overfitted** — works across domains
- Standard features converge to GPT GO in 5 rounds
- Complex features reach zero criticals in 4-5 rounds but GPT never says GO (majors persist)
- **Zero-critical threshold is more reliable than waiting for GPT GO** — catches both features in a similar window
- Deep review analysis: **44/46 issues were warranted** — GPT reviews are thorough and valid, not nitpicking
- Complex features need a **pre-review domain checklist** — 50% of webhook issues could have been caught before round 1
- **Review history is the single biggest improvement** — webhook feature converged in 4 rounds ($0.62) with history vs never in 10 rounds ($2.84) without it

### Feature Complexity Detection

Flag a feature as "complex" if it involves any of:
- Concurrent access / locking
- Retry / backoff / dead-letter queues
- Idempotency / deduplication
- Cryptographic operations (signatures, tokens)
- State machines with transitions
- Time-dependent behavior (expiry, scheduling)

### Complexity-Aware Strategy

| Feature Type | Threshold | Cap | Pre-Review | Expected |
|-------------|-----------|-----|------------|----------|
| **Standard** (CRUD, validation, endpoints) | Zero criticals | 5-6 rounds | None | Converges R3-5, ~$0.50-0.90 |
| **Complex** (concurrency, retry, security) | Zero criticals × 2 consecutive | up to 20 rounds | Domain checklist | Progressive improvement, high-quality plan |

### Pre-Review Domain Checklist (for complex features)

Before round 1, Claude answers domain-specific questions to catch structural issues early:
1. **Dedup key definition** — How are duplicates identified? Collision risk?
2. **Concurrency model** — Which database? Locking strategy? Contention behavior?
3. **Idempotency contract** — At-least-once or exactly-once? Who is responsible?
4. **Security defaults** — Fail-open or fail-closed? Environment restrictions?
5. **Time control** — How are time-dependent features tested? Injectable clock?

### Review History (Context Continuity)

Without review history, GPT reviews each plan in isolation — no memory of what it flagged before or why the plan changed. This causes:
- **Oscillating criticals** — GPT re-raises resolved issues in different framing
- **No credit for resolved work** — Claude defers something with good reasoning, GPT flags it again next round
- **Wasted rounds** — both models spend tokens re-discovering what was already discussed

With `--review-history` enabled, each review round includes the previous plan and previous review as context. GPT is instructed to:
1. Check whether previously raised issues were adequately resolved
2. Flag only genuinely NEW issues introduced by the revision
3. Not re-raise issues that were validly deferred or resolved

This addresses the oscillation problem at the source — GPT can track progress across rounds instead of reviewing from scratch each time. Experiment 10 (pending) tests this on the webhook feature with a 20-round cap.

### Design Philosophy: Plan Quality Over Speed

The planning phase is an investment. A thorough plan that costs $2-5 and takes 30-60 minutes pays for itself by preventing implementation rework. Flawed plans create backlog work downstream:
- Missing error handling → post-launch bug fixes
- Underspecified concurrency → race conditions discovered in staging
- No migration strategy → deployment blocked at release time

planner-auto should optimize for **progressive improvement** — each round makes the plan strictly better — not for minimizing rounds. The process should never go backwards (re-raising resolved issues, adding scope that was already deferred).

The review history feature ensures this progression is visible and maintained across rounds.

### Cost Projection (Updated)

| Configuration | Feature | Rounds | Cost | Time |
|---------------|---------|--------|------|------|
| No tuning (Sonnet baseline) | Standard | 6+ (never) | $0.80+ | 13+ min |
| Sonnet + guidance + 3r cap | Standard | 3 | ~$0.39 | ~6 min |
| **v1 default (Opus + all features)** | **Standard** | **5 (converges)** | **~$0.87** | **~13 min** |
| v1 default + zero-critical stop | Standard | 3-5 | ~$0.50-0.87 | ~6-13 min |
| v1 default + zero-critical stop | Complex | 4-8 | ~$0.75-2.00 | ~10-25 min |
| v1 default + 20r cap + history | Complex | 10-20 | ~$2-5 | ~30-60 min |

### Note on Final Output Quality

The converged plan (Experiment 7, registration) is 10 KB, 1,346 words, 5 milestones — well within the 3,000-word constraint. GPT's GO review praised the architectural refactor, request parsing sequence, IntegrityError rollback handling, input normalization strategy, and rate limiting scope tradeoff.

The non-converged plan (Experiment 9, webhook at R10) still reached excellent quality: fail-closed security, FOR UPDATE SKIP LOCKED concurrency, terminal dead-letter, injected clock for testing. The deep analysis confirmed 44/46 GPT issues were warranted — the process was working, it just needed more rounds and context continuity to converge.

**The convergence problem is solved.** With review history enabled, both standard and complex features converge within 4-5 rounds. Review history was the single biggest improvement — it turned a non-converging 10-round run ($2.84) into a 4-round convergence ($0.62) by giving GPT context continuity across rounds.

---

## Pre-Implementation POCs (Revised)

Standalone scripts to validate technical unknowns before committing to full implementation. Each POC tests one assumption in isolation. Results feed directly into Plan 1 and Plan 2 implementation decisions.

**POC location:** `scripts/poc/planner-auto/`

### POC Scripts

#### Reviewer Invocation (compare all three adapters)

| POC | Script | What It Proves | Blocks |
|-----|--------|---------------|--------|
| 1a | `poc_reviewer_direct_api.py` | Call GPT-5.4 via OpenAI SDK, pass plan text as prompt, capture structured response. Measure latency, token cost, response consistency | Plan 2 |
| 1b | `poc_reviewer_codex_mcp.py` | Set up Codex MCP, invoke GPT from within Claude agent loop, capture response. Measure latency, test if GPT can read repo files through MCP tools | Plan 2 |
| 1c | `poc_reviewer_opencode_http.py` | Start `opencode serve`, create session via HTTP API, send review prompt, capture response. Measure latency, test session lifecycle | Plan 2 |
| 1d | `poc_reviewer_comparison.py` | Run the same plan through all three adapters, compare: latency, response quality, structured output reliability, cost. Generates a comparison report | Plan 2 |

#### Response Parsing

| POC | Script | What It Proves | Blocks |
|-----|--------|---------------|--------|
| 2a | `poc_parse_go_nogo.py` | Feed 10+ real and synthetic reviewer responses through the parser. Test GO, NO_GO, malformed, GO-with-notes, timeout edge cases. Validate `ReviewerResponse` schema extraction | Plan 2 |
| 2b | `poc_structured_prompt.py` | Test different prompt templates that instruct the reviewer to output structured format. Compare free-form vs JSON-instructed vs XML-tagged output reliability | Plan 2 |

#### SQLite Session Engine

| POC | Script | What It Proves | Blocks |
|-----|--------|---------------|--------|
| 3a | `poc_session_db.py` | Create session, append messages, store plan drafts, store reviews, query by session. Validates the DB schema (sessions, messages, context_entries, plan_drafts, reviews, blockers) | Plan 1 |
| 3b | `poc_artifact_export.py` | Given a populated DB, export `chat.csv`, `context-summary.md`, numbered `a-NN-plan.md` / `a-NN-review.md` files. Validates the export-from-DB pattern | Plan 1 |

#### Claude Agent SDK (Planner Side)

| POC | Script | What It Proves | Blocks |
|-----|--------|---------------|--------|
| 4a | `poc_planner_headless.py` | Run Claude via Agent SDK in headless mode with a system prompt. Feed it context files + a feature description. Confirm it produces a milestone plan following `CLAUDE_orch_v2.md` template | Plan 1 |
| 4b | `poc_context_synthesis.py` | Load files into `context_entries`, simulate conversation in `messages`, run on-demand context synthesis. Validate synthesized output is useful for plan generation | Plan 1 |

#### Failure Path and Session Recovery

| POC | Script | What It Proves | Blocks |
|-----|--------|---------------|--------|
| 5a | `poc_failure_paths.py` | Simulate reviewer timeout, malformed output, and parse failure. Verify session enters blocked/paused state correctly and resumes cleanly after human intervention. Validates contract edge cases against session model | Plan 1 + Plan 2 |

#### End-to-End Mini Loop

| POC | Script | What It Proves | Blocks |
|-----|--------|---------------|--------|
| 5b | `poc_review_loop_e2e.py` | Hardcoded plan → reviewer (Direct API) → parse response → if NO_GO, feed issues to Claude → revised plan → reviewer again. Run 2-3 rounds. Proves the full review loop before building the real engine | Plan 1 + Plan 2 |

### Execution Order

```
Phase A (parallel, no dependencies):
  1a  Direct API reviewer
  2a  Response parsing
  3a  SQLite session DB

Phase B (depends on Phase A):
  2b  Structured prompt testing    ← refine based on 2a results
  3b  Artifact export              ← depends on 3a schema
  4a  Planner headless

Phase C (depends on Phase A):
  1b  Codex MCP reviewer           ← compare against 1a
  1c  OpenCode HTTP reviewer       ← compare against 1a
  4b  Context synthesis            ← depends on 3a
  5a  Failure paths                ← depends on 2a + 3a

Phase D (depends on all above):
  1d  Reviewer comparison report   ← needs 1a, 1b, 1c
  5b  End-to-end mini loop         ← needs 4a (planner headless) + 1a + 2a + 3a
```

**Phase A can start immediately.** Total: 13 scripts, 4 phases.

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
| Cross-model integration | OpenCode subprocess | Direct API (ship first) → Codex MCP (if tool access needed) → OpenCode HTTP (alternative) | Research: subprocess has known bugs, Direct API fastest to prove loop, Codex MCP for full capability |
| Home directory | `~/.orchestrator-auto/` | `~/.planner-auto/` | Avoid collision with orchestrator-auto |
| Artifact export timing | Not specified | Explicit table per event | Senior dev: audit model clarity |
| Observability | Not specified | Headless default, `--verbose`, `--tui`, `--debug` flags, session-scoped log files | Gap: no logging or debug story in v1.0 |
| DB schema | 5 tables | 6 tables (added `blockers`) | POC 5a: pause/resume lifecycle requires persistent blocker records with source, question, answer, resolution status |
| Convergence strategy | Not addressed | 6-factor combination: constrained prompt, validate feedback, filter severity, keep/trim, resolution guidance, max_turns=2 | POC 5b: 7 experiments, convergence achieved at round 5 ($0.87, 10 KB plan). Solved. |
| Planner prompt | Unconstrained | Max 8 tasks/milestone, 1-2 sentences, under 3000 words, scope-locked | POC 5b: unconstrained prompt caused 7.5x plan bloat and scope creep (registration → JWT+login+auth) |
| Reviewer schema | verdict + issues + summary | Added resolution_guidance, target_section, keep[], trim[] | Senior dev suggestion + POC 5b: guidance gives Claude concrete targets; keep/trim prevents bloat |
| Feedback validation | Not addressed | Claude ACCEPT/DEFER/REJECT per issue | POC 5b: mirrors manual workflow where user assesses feedback validity before fixing |
| Review history | Not addressed | GPT sees previous plan + previous review per round | POC 5b Exp 8-9: oscillating criticals caused by GPT reviewing in isolation; history provides continuity |
| Design philosophy | Minimize rounds | Optimize for progressive plan quality; cost/time is acceptable if plan improves each round | Flawed plans create backlog work downstream; investment in planning prevents rework |
