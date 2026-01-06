# Claude Orchestrator Batch - Quick Reference & Prompt Templates

Supplementary reference for `CLAUDE_orchestrator_batch.md`.

---

## Batch Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BATCH TASK WORKFLOW                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  PLANNER (Opus/Sonnet)                    EXECUTOR (Sonnet/Haiku)            │
│  ────────────────────                     ───────────────────────            │
│                                                                              │
│  ┌─────────────────────┐                                                     │
│  │ 1. DISCOVERY        │                                                     │
│  │    - Understand task│                                                     │
│  │    - Define rules   │                                                     │
│  └──────────┬──────────┘                                                     │
│             │                                                                │
│             ▼                                                                │
│  ┌─────────────────────┐                                                     │
│  │ 2. ENUMERATION      │                                                     │
│  │    - Find ALL items │                                                     │
│  │    - Count: N total │                                                     │
│  └──────────┬──────────┘                                                     │
│             │                                                                │
│             ▼                                                                │
│  ┌─────────────────────┐                                                     │
│  │ 3. PLANNING         │                                                     │
│  │    - 1 milestone    │                                                     │
│  │      per item       │                                                     │
│  │    - [PLAN_READY]   │                                                     │
│  └──────────┬──────────┘                                                     │
│             │                                                                │
│             ▼                                                                │
│  ┌─────────────────────┐    prompt M1     ┌─────────────────────┐           │
│  │ 4. Generate         │ ────────────────▶│ 5. Execute          │           │
│  │    Executor Prompt  │                  │    Milestone 1      │           │
│  └─────────────────────┘                  └──────────┬──────────┘           │
│                                                      │                       │
│                                                      ▼                       │
│  ┌─────────────────────┐    [PROGRESS_    ┌─────────────────────┐           │
│  │ 6. Review Report    │◀───REPORT]───────│ 6. STOP + Report    │           │
│  │    (1 of N)         │                  │    [/PROGRESS_      │           │
│  └──────────┬──────────┘                  │     REPORT]         │           │
│             │                             └─────────────────────┘           │
│             ▼                                                                │
│  ┌─────────────────────┐                                                     │
│  │ 7. [MILESTONE_      │──── approved ────┐                                 │
│  │    APPROVED]        │                  │                                 │
│  └─────────────────────┘                  ▼                                 │
│             │                  ┌─────────────────────┐                      │
│             │   prompt M2      │ 8. Execute          │                      │
│             └─────────────────▶│    Milestone 2      │                      │
│                                └─────────────────────┘                      │
│                                                                              │
│  [Repeat for all N milestones]                                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Kickstart Prompts (Copy-Paste)

### Start Batch Task (Planner)

```
Read CLAUDE_orchestrator_batch.md. You are the PLANNER for a batch task.

Task: [DESCRIBE THE REPETITIVE TASK]

1. DISCOVERY: Understand what needs to be processed, define rules
2. ENUMERATION: Find ALL items (files, endpoints, records, etc.)
3. PLANNING: Create plan doc at docs/batch/BATCH_[task-name]_plan.md

Your output MUST include:
[PLAN_READY]
Path: docs/batch/BATCH_[task-name]_plan.md
Milestones: [N] total

[PLAN_CONTENT]
# Batch Task: [Task Name]
... full plan content ...
[/PLAN_CONTENT]

Processing scope: [FOLDER/URL/DATABASE/etc.]

After creating the plan, show me:
- Total item count
- Grouping strategy
- Estimated time
- The executor prompt for Milestone 1
```

### Start Executor (Milestone 1)

```
Read CLAUDE_orchestrator_batch.md. You are the EXECUTOR.

## Current Milestone: 1 of [Total]

### Item to Process:
- **Identifier:** [name]
- **Path/URL:** [location]

### Processing Rules:
[Copy from plan]

### Skip Conditions:
[Copy from plan]

### Acceptance Criteria:
[Copy from plan]

Your response MUST:
1. Start with [PROGRESS_REPORT] on its own line
2. Use header: ## Milestone 1: [Name] - [STATUS]
3. End with [/PROGRESS_REPORT] on its own line

STOP and wait for approval after completing this milestone.
```

### Approve & Continue (Planner)

```
[MILESTONE_APPROVED] Milestone [N] approved.

Update the Recovery State in the plan document:
- Current milestone: [N+1]
- Completed: [X]
- Skipped: [Y]
- Failed: [Z]

Generate the executor prompt for Milestone [N+1]: [Item Name]
```

### Batch Approval (Planner)

```
[MILESTONE_APPROVED] Milestone [M] approved. Batch approved: milestones [N]-[M] all followed expected pattern.

Update the Recovery State in the plan document.
Generate the executor prompt for Milestone [M+1]: [Item Name]
```

### Request Changes (Planner)

```
[CHANGES_REQUESTED] Milestone [N] needs changes:
- [Issue 1]
- [Issue 2]

Fix these issues and regenerate your progress report.
```

### Continue After Approval (Executor)

```
Milestone [N] approved. Continue with Milestone [N+1]:

## Current Milestone: [N+1] of [Total]

### Item to Process:
- **Identifier:** [name]
- **Path/URL:** [location]

[Copy processing rules, skip conditions, acceptance criteria from plan]

Process this item. Use [PROGRESS_REPORT]...[/PROGRESS_REPORT] format.
STOP and wait for approval.
```

---

## Recovery Prompts (Copy-Paste)

### Recover Planner Session

```
Read CLAUDE_orchestrator_batch.md. You are the PLANNER recovering a batch task.

Plan document: docs/batch/BATCH_[task-name]_plan.md

1. Read the plan and Recovery State section
2. Identify the current milestone and progress
3. Generate the executor prompt to continue from where we left off

Current status:
- Milestones completed: [list]
- Milestones skipped: [list]
- Current milestone: [N]
- Blocking issues: [None / description]

If more than 50% complete, consider re-enumeration to check for scope drift.
```

### Recover Executor Session (Same Session)

```
Context was compressed. Re-read:
- CLAUDE_orchestrator_batch.md
- The plan document at docs/batch/BATCH_[task]_plan.md

Continue Milestone [N] from where we left off.
Last completed: [file/task]

Remember: Use [PROGRESS_REPORT]...[/PROGRESS_REPORT] format.
```

### Recover Executor Session (New Session)

```
Read CLAUDE_orchestrator_batch.md. You are the EXECUTOR.

Milestone [N] is IN PROGRESS. Previous executor crashed.

Plan document: docs/batch/BATCH_[task]_plan.md

### Item to Process:
- **Identifier:** [name]
- **Path/URL:** [location]

Completed so far:
- [task1] done
- [file1] created

Remaining:
- [task2]
- [task3]

Continue from where the previous executor left off.
Use [PROGRESS_REPORT]...[/PROGRESS_REPORT] format.
STOP and report when milestone is complete.
```

### Re-enumeration Check (Planner)

```
Pause execution. We're at 50% completion - time to check for scope drift.

Re-enumerate items to check for:
1. New items matching criteria that weren't in original list
2. Items that no longer exist (deleted/moved)
3. Any scope drift

Compare with original enumeration in the plan document and report differences.
If items changed, update the plan and adjust remaining milestones.
```

---

## Progress Report Template (Executor)

```markdown
[PROGRESS_REPORT]
## Milestone [N]: [Item Name] - [COMPLETED|SKIPPED|FAILED]

**Status:** [COMPLETED | SKIPPED | FAILED]

### Item Processed:
- **Identifier:** [name/id]
- **Path/URL:** [location]

### Action Taken:
[What was done - or why skipped/failed]

### If Skipped - Reason:
[Which skip condition matched]

### If Failed - Error:
[Error details]

### Verification:
- [x] [Criterion 1]: PASS
- [x] [Criterion 2]: PASS

### Files Modified:
- [path] (created|modified|deleted)

### Progress: [N] of [Total] ([percentage]%)
- Completed: [X]
- Skipped: [Y]
- Failed: [Z]

### Ready for Review: YES
[/PROGRESS_REPORT]
```

### Blocked Report (Executor)

```markdown
[BLOCKED] Cannot proceed: [Short reason - this line is parsed!]

## Milestone [N]: [Item Name]

**Details:** [Full explanation of the blocker]
**Question:** [What decision/input do you need?]

### Progress: [N] of [Total] - [X] completed, [Y] skipped, 1 blocked
```

---

## Session State Template (Planner)

Track progress in the plan document:

```markdown
## Recovery State

| Field | Value |
|-------|-------|
| **Last Updated** | 2025-01-06 14:30 UTC |
| **Current Milestone** | 12 |
| **Total Milestones** | 35 |
| **Completed** | 10 |
| **Skipped** | 1 |
| **Failed** | 0 |
| **Blocked** | 0 |
| **Remaining** | 24 |

### Completed Items
| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | users.md | ✅ | Archived |
| 2 | auth.md | ✅ | Archived |
| 3 | legacy.md | ⏭️ | Skip: DO NOT MIGRATE |
| ... | ... | ... | ... |
```

---

## Review Commands

| Action | Command |
|--------|---------|
| **Approve** | `[MILESTONE_APPROVED] Milestone N approved. Generate prompt for M[N+1].` |
| **Batch approve** | `[MILESTONE_APPROVED] Milestone M approved. Batch: M[N]-M[M] all good. Generate prompt for M[M+1].` |
| **Changes needed** | `[CHANGES_REQUESTED] Milestone N needs changes: [issues]. Fix and re-report.` |
| **Blocked response** | `Blocker resolved: [answer]. Continue with Milestone N.` |
| **Abort** | `ABORT: [Reason]. Do not proceed.` |

---

## Parser-Compatible Formats

These formats are required for orchestrator-auto compatibility:

### Progress Report
```
[PROGRESS_REPORT]
## Milestone N: [Name] - [STATUS]
...content...
[/PROGRESS_REPORT]
```
- Opening AND closing tags required
- Milestone header: `## Milestone N:` (NOT `N/Total`)

### Blocked
```
[BLOCKED] Cannot proceed: [reason on same line]
```
- `Cannot proceed:` must be on same line as tag

### Plan Ready (Planner Output)
```
[PLAN_READY]
Path: docs/batch/BATCH_[name]_plan.md
Milestones: N total

[PLAN_CONTENT]
...full plan markdown...
[/PLAN_CONTENT]
```

### Milestone Approved
```
[MILESTONE_APPROVED] Milestone N approved.
```
- Must include "Milestone N approved" (singular, with number)

---

## Batching Strategies

### When to Batch Items into Single Milestone

| Item Processing Time | Strategy |
|---------------------|----------|
| < 5 minutes each | Batch 5-10 items per milestone |
| 5-15 minutes each | Batch 2-3 items per milestone |
| 15-30 minutes each | One item per milestone |
| > 30 minutes each | Split item into sub-tasks |

### Approval Batching by Risk Level

| Risk Level | Approval Strategy |
|------------|-------------------|
| **Low** (docs, formatting) | Batch approve 5-10 at a time |
| **Medium** (config, code) | Batch approve 2-3, or individual |
| **High** (data, security) | Individual approval required |

### Progressive Trust Pattern

1. **Milestones 1-3:** Individual approval (establish pattern)
2. **Milestones 4-10:** Batch approve 2-3 if consistent
3. **Milestones 11+:** Batch approve 5+ if highly consistent

---

## Git Checkpoint Quick Reference

### Commit Strategy by Milestone Count

| Milestone Count | Strategy |
|-----------------|----------|
| 1-10 | Auto-commit at end is fine |
| 11-25 | Manual commit every 5 milestones |
| 26-50 | Manual commit every 3 milestones |
| 50+ | Manual commit every milestone |

### Commit After Milestone Approval

```bash
git add -A
git commit -m "batch([task]): complete M[N] - [description]

Processed: [X] | Skipped: [Y] | Failed: [Z]"
```

### Rollback Commands

```bash
# View recent commits
git log --oneline -10

# Rollback to specific commit (discard changes)
git reset --hard [commit-hash]

# Rollback but keep changes as unstaged
git reset --soft [commit-hash]
```

---

## Context Management

### When to Start Fresh Executor Session

| Milestone Count | Recommendation |
|-----------------|----------------|
| 1-10 | Same session is fine |
| 11-25 | New session every 5-10 milestones |
| 26-50 | New session every 3-5 milestones |
| 50+ | New session every milestone |

### Signs You Need Fresh Executor

- Response quality declining
- Executor forgetting processing rules
- Context compression occurred (`/compact`)
- Executor conflating different items

---

## Example Task Types

| Task | Items | Milestone Per | Est. Time Each |
|------|-------|---------------|----------------|
| Archive stale docs | MD files by folder | Folder | 30 min |
| Document API endpoints | OpenAPI endpoints | Single endpoint | 30 min |
| Migrate configs | Config files | Single file | 20 min |
| Update imports | Files with old import | Single file | 15 min |
| Audit security | Routes | Route group | 30 min |
| Translate docs | Doc files | Single doc | 45 min |
| Migrate records | DB records | Batch of 1000 | 30 min |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Parser not detecting progress report | Check for `[/PROGRESS_REPORT]` closing tag |
| Parser not detecting blocked | Ensure `Cannot proceed:` is on same line as `[BLOCKED]` |
| Milestone number not extracted | Use `## Milestone N:` not `## Milestone N/Total:` |
| Plan not saved | Wrap plan in `[PLAN_CONTENT]...[/PLAN_CONTENT]` |
| Executor continues without stopping | Add **⛔ STOP** in bold, emphasize "wait for approval" |
| Lost track of progress | Check Recovery State in plan document |
| Context compressed | Use recovery prompts |
| Items changed mid-execution | Re-enumerate at 50% completion |
| Approval overhead too high | Use batch approvals for low-risk items |
| Data migration slow | Use cursor-based pagination, not OFFSET |

---

## orchestrator-auto CLI Commands

```bash
# Start batch task
orchestrator start -f "Archive stale markdown files in docs/"

# Start with existing plan (skip discovery/planning)
orchestrator start --plan docs/batch/BATCH_archive-stale-docs_plan.md

# Cost-optimized batch processing
orchestrator start -f "Document 50 API endpoints" -pm sonnet -em haiku --telegram

# Queue multiple batch plans
orchestrator start --queue batch-plan1.md batch-plan2.md

# Resume after reviewing milestone
orchestrator resume <session-id>

# Respond to blocker
orchestrator respond <session-id> "Skip this file, it's referenced externally"

# Check session status
orchestrator status <session-id>

# Export session history
orchestrator export <session-id> -o report.md
```

---

## Related Files

| File | Purpose |
|------|---------|
| `CLAUDE_orchestrator_batch.md` | Full batch framework + templates |
| `CLAUDE_orchestrator.md` | Standard orchestrator (3-5 large milestones) |
| `CLAUDE_orchestrator_ref.md` | Standard orchestrator quick reference |
| `docs/batch/BATCH_[task]_plan.md` | Batch task plan documents |
