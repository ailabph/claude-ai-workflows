# Planner Auto: Automated Plan Generation Pipeline

## Problem

Before `orchestrator-auto` can execute, it needs a high-quality milestone plan. Today that plan is created manually through a multi-step, multi-agent review loop. This document captures the current manual workflow and the proposed automation design.

---

## Current Manual Workflow

### Step 1: Context Loading (Claude)

Open Claude. Add relevant files for context (source files, docs, existing tests, etc.). Ask the agent to confirm it understands the codebase context before proceeding.

**Input:** Project files
**Output:** Agent confirms understanding of codebase

### Step 2: Plan Generation (Claude)

Describe the new feature or issue. Ask Claude to create a comprehensive implementation plan and save it as an `.md` file following the orchestrator milestone format (`## Milestone N: Name`).

**Input:** Feature description or issue
**Output:** `docs/plans/<feature>.md` — milestone plan draft

### Step 3: Go/No-Go Review (OpenCode + GPT-5.4)

Open OpenCode, load GPT-5.4. Prompt:

```
Do go/no-go for implementation for plan <plan file path>
```

GPT reviews the plan for feasibility, gaps, ordering issues, missing edge cases, etc.

**Input:** Plan file path
**Output:** "Go" (proceed to orchestrator) or list of issues

### Step 4: Feedback Loop (Claude)

If GPT found issues, copy the issues back to Claude:

```
Assess if feedback is valid:

\```
<paste issues only>
\```

If valid, proceed to fix and update the plan.
```

Claude evaluates each issue, applies valid fixes, and updates the plan file.

**Input:** GPT feedback
**Output:** Updated plan file

### Step 5: Repeat Until "Go"

Repeat Steps 3-4 until GPT returns a "Go" for implementation.

**Output:** Finalized plan ready for `orchestrator-auto`

---

## Handoff to orchestrator-auto

Once the plan passes go/no-go:

```bash
orchestrator start --plan docs/plans/<feature>.md --auto-commit
```

---

## Pain Points (Why Automate)

| Pain Point | Detail |
|------------|--------|
| Manual copy-paste | Issues from GPT must be copied into Claude and back |
| Context switching | Three tools open (Claude, OpenCode, terminal) |
| No audit trail | Review rounds aren't tracked — only the final plan survives |
| Repetitive prompts | Same prompt patterns every time |
| Human bottleneck | Each round-trip requires manual intervention |

---

## Proposed Automation Design

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PLANNER-AUTO                                │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ PHASE 1: SESSION SETUP                                       │   │
│  │                                                              │   │
│  │  User runs: planner-auto                                     │   │
│  │       │                                                      │   │
│  │       ▼                                                      │   │
│  │  Create sessions/<session-id>/                               │   │
│  │       ├── chat.csv                                           │   │
│  │       └── context-tracker-live.md                            │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                             ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ PHASE 2: CONTEXT LOADING                                     │   │
│  │                                                              │   │
│  │  User adds files ──► Planner agent reads files               │   │
│  │                              │                               │   │
│  │                              ▼                               │   │
│  │                       "Do you understand?"                   │   │
│  │                              │                               │   │
│  │                     ┌────────┴────────┐                      │   │
│  │                     │ NO              │ YES                  │   │
│  │                     ▼                 ▼                      │   │
│  │               User clarifies    Updates context-             │   │
│  │               or adds more      tracker-live.md              │   │
│  │               files ─────┘                                   │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                             ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ PHASE 3: FEATURE DISCUSSION                                  │   │
│  │                                                              │   │
│  │  User describes feature/issue                                │   │
│  │       │                                                      │   │
│  │       ▼                                                      │   │
│  │  Planner agent ◄──► User (clarifying Q&A)                   │   │
│  │       │                                                      │   │
│  │       │  ┌─────────────────────────────────┐                 │   │
│  │       └──► Sub-agent (after EVERY response) │                │   │
│  │           │  • Appends to chat.csv          │                │   │
│  │           │  • Updates context-tracker-live  │                │   │
│  │           └─────────────────────────────────┘                │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                             ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ PHASE 4: PLAN GENERATION                                     │   │
│  │                                                              │   │
│  │  Agent fully understands ──► Creates milestone plan          │   │
│  │                               (CLAUDE_orch_v2.md template)   │   │
│  │                                      │                       │   │
│  │                                      ▼                       │   │
│  │                              Saves a-01-plan.md              │   │
│  └──────────────────────────────────────┬───────────────────────┘   │
│                                         ▼                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ PHASE 5-7: CROSS-MODEL REVIEW LOOP                           │   │
│  │                                                              │   │
│  │  ┌─────────────────────┐      ┌──────────────────────┐      │   │
│  │  │  REVIEWER            │      │  PLANNER AGENT        │      │   │
│  │  │  (OpenCode + GPT-5.4)│      │  (Claude)             │      │   │
│  │  └──────────┬──────────┘      └──────────┬───────────┘      │   │
│  │             │                             │                  │   │
│  │             ▼                             │                  │   │
│  │  Reads a-01-plan.md                       │                  │   │
│  │  "go/no-go for implementation?"           │                  │   │
│  │             │                             │                  │   │
│  │        ┌────┴────┐                        │                  │   │
│  │        │ GO      │ NO-GO                  │                  │   │
│  │        ▼         ▼                        │                  │   │
│  │    (skip to   Saves a-02-review.md        │                  │   │
│  │     Phase 8)     │                        │                  │   │
│  │                  └───────────────────────►│                  │   │
│  │                                           ▼                  │   │
│  │                                  Reads a-02-review.md        │   │
│  │                                  Assess validity             │   │
│  │                                  Apply valid feedback only   │   │
│  │                                           │                  │   │
│  │                                           ▼                  │   │
│  │                                  Saves a-03-plan.md          │   │
│  │                                           │                  │   │
│  │             ┌─────────────────────────────┘                  │   │
│  │             ▼                                                │   │
│  │  Reads a-03-plan.md ◄─── LOOP REPEATS:                      │   │
│  │  "go/no-go?"              a-04-review.md                     │   │
│  │       │                   a-05-plan.md                       │   │
│  │  ┌────┴────┐              a-06-review.md                     │   │
│  │  │ GO      │ NO-GO        ...                                │   │
│  │  ▼         └──► (continues)                                  │   │
│  │ (Phase 8)                                                    │   │
│  └──────────────────────────────────────────┬───────────────────┘   │
│                                             ▼                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ PHASE 8: FINALIZE                                            │   │
│  │                                                              │   │
│  │  Reviewer says "GO"                                          │   │
│  │       │                                                      │   │
│  │       ▼                                                      │   │
│  │  Last plan renamed to a-<N>-plan-final.md                    │   │
│  │       │                                                      │   │
│  │       ▼                                                      │   │
│  │  Copied to <repo>/.kafra/a-01-plans/                         │   │
│  │                                                              │   │
│  │  ✅ planner-auto job done                                    │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
~/.orchestrator-auto/
├── sessions/                    # Active planning sessions
│   └── <session-id>/
│       ├── chat.csv             # Full conversation log (timestamp, role, message)
│       ├── context-tracker-live.md  # Running summary of loaded context and understanding
│       ├── a-01-plan.md         # First plan draft
│       ├── a-02-review.md       # First reviewer feedback
│       ├── a-03-plan.md         # Revised plan after feedback
│       ├── a-04-review.md       # Second reviewer feedback
│       ├── ...                  # Continues until "go"
│       └── a-<N>-plan-final.md  # Final approved plan
├── skills/                      # Reusable prompt templates and instructions
├── agents/                      # Agent configurations (planner, reviewer, etc.)
├── plans/                       # Standalone plan storage
├── a-01-plans/                  # Pipeline stage: new plans awaiting review
├── a-02-ongoing/                # Pipeline stage: plans in active review loop
├── a-03-for-review/             # Pipeline stage: plans sent to reviewer
├── a-04-done/                   # Pipeline stage: approved plans ready for execution
└── a-05-archive/                # Pipeline stage: completed/historical plans
```

### Automated Flow

#### Phase 1: Session Setup

1. Create a new session: `~/.orchestrator-auto/sessions/<session-id>/`
2. Initialize `chat.csv` (columns: timestamp, role, message) and `context-tracker-live.md`

#### Phase 2: Context Loading

3. User runs `planner-auto` and adds files for context
4. Planner agent reads the files, confirms understanding
5. Agent updates `context-tracker-live.md` with initial context summary (files loaded, key entities, relationships)

#### Phase 3: Feature Discussion

6. User describes the feature or issue in conversation
7. Planner agent asks clarifying questions, builds understanding
8. **After every agent response**, a sub-agent updates:
   - `chat.csv` — appends the exchange
   - `context-tracker-live.md` — updates with new decisions, constraints, or requirements learned

#### Phase 4: Plan Generation

9. Once the agent fully understands the task, it generates a milestone plan
10. Plan follows the `CLAUDE_orch_v2.md` template format (`## Milestone N: Name`, tasks, deliverables)
11. Saved as `sessions/<session-id>/a-01-plan.md`

#### Phase 5: Cross-Model Review

12. `planner-auto` invokes OpenCode with GPT-5.4 (or configured reviewer model)
13. Reviewer prompt: `"Assess if plan is go/no-go for implementation, <plan-path>.md"`
14. Reviewer saves its response to `sessions/<session-id>/a-02-review.md`

#### Phase 6: Feedback Loop

15. Planner agent reads `a-02-review.md`
16. Assesses each piece of feedback — applies only what's valid, discards noise
17. Produces revised plan, saved as `a-03-plan.md`

#### Phase 7: Repeat Until "Go"

18. Steps 12-17 repeat. Files increment:

```
a-01-plan.md      # Draft 1
a-02-review.md    # Review 1
a-03-plan.md      # Draft 2 (revised)
a-04-review.md    # Review 2
a-05-plan.md      # Draft 3 (revised)
a-06-review.md    # Review 3 → "Go"
```

19. When reviewer returns "Go", the last plan is renamed to `a-<N>-plan-final.md`

#### Phase 8: Handoff (Future)

The finalized plan is ready for `orchestrator-auto`. In a future phase, `planner-auto` will automatically forward the plan to a watched folder:

```bash
orchestrator watch <folder-to-watch> --auto-commit
```

This closes the loop: `planner-auto` generates the plan, `orchestrator-auto` executes it.

---

## Session File Details

### chat.csv

Append-only conversation log. Every exchange is recorded for audit trail.

| Column | Description |
|--------|-------------|
| `timestamp` | ISO 8601 timestamp |
| `role` | `user`, `planner`, `reviewer`, `sub-agent` |
| `message` | Full message content |

### context-tracker-live.md

Living document updated by a sub-agent after every response. Tracks:

- Files loaded and their purpose
- Key entities, models, and relationships discovered
- User requirements and constraints
- Decisions made during conversation
- Open questions

### Plan Files (a-NN-plan.md / a-NN-review.md)

Numbered sequentially within a session. Odd-numbered files are plans, even-numbered are reviews (after the initial `a-01-plan.md`). The naming convention makes it easy to see how many review rounds occurred and trace the evolution of the plan.

---

## Pipeline Folders vs. Session Folders

The `sessions/` folder is the working directory for a single plan's lifecycle. The `a-01` through `a-05` pipeline folders belong to a broader pipeline that is **out of scope for planner-auto** — documented here for context only.

### Session Folders (planner-auto scope)

| Folder | Purpose |
|--------|---------|
| `sessions/<id>/` | All artifacts for a single planning session (conversation, context, plan drafts, reviews) |

planner-auto's responsibility ends when the final plan is produced. It copies the `a-<N>-plan-final.md` into `a-01-plans/` and its job is done.

### Pipeline Folders (broader .kafra pipeline — out of scope)

The `a-01` through `a-05` folders form a per-project pipeline that lives at `<repo>/.kafra/`. Folder prefixes are numbered for alphabetical `ls` ordering. Files move (not copy) between folders — the folder a file is in represents its current status.

```
planner-auto → a-01-plans/ → PM agent → a-02-ongoing/ → orchestrator watch → a-03-for-review/ → reviewer-fixer-auto → a-04-done/ → PM agent → a-05-archive/
```

| Stage | Folder | Agent | Action |
|-------|--------|-------|--------|
| Backlog | `a-01-plans/` | PM agent | Decides what to implement next |
| Implementation | `a-02-ongoing/` | `orchestrator watch` | Executes plan, commits code, renames file with `-done` suffix |
| Review | `a-03-for-review/` | `reviewer-fixer-auto` | Review ↔ fix loop until implementation is satisfactory |
| Done | `a-04-done/` | PM agent | Acknowledges completion |
| Archive | `a-05-archive/` | PM agent | Cold storage for historical plans |

### Tool Status

| Tool | Status | Pipeline Role |
|------|--------|---------------|
| `orchestrator-auto` | Built | Executes plans (implementation in `a-02-ongoing/`) |
| `planner-auto` | To be built | Generates reviewed plans (feeds `a-01-plans/`) |
| `reviewer-fixer-auto` | Not yet planned | Post-implementation review (processes `a-03-for-review/`) |
| PM agent | Not yet planned | Traffic controller across all pipeline stages |
