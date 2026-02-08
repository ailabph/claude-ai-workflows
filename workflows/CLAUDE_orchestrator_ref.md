# Claude Orchestrator - Quick Reference & UI Patterns

Supplementary reference for `CLAUDE_orchestrator.md`.

---

## Two-Agent Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TWO-SESSION ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SESSION 1: REVIEWER (Opus)             SESSION 2: EXECUTOR (Sonnet)         │
│  ──────────────────────────             ────────────────────────────         │
│                                                                              │
│  ┌─────────────────────┐                                                     │
│  │ 1. Create Plan      │                                                     │
│  │    DOC_feature.md   │                                                     │
│  └──────────┬──────────┘                                                     │
│             │                                                                │
│             ▼                                                                │
│  ┌─────────────────────┐    copy prompt    ┌─────────────────────┐          │
│  │ 2. Generate         │ ─────────────────▶│ 3. Execute          │          │
│  │    Executor Prompt  │                   │    Milestone 1      │          │
│  └─────────────────────┘                   └──────────┬──────────┘          │
│                                                       │                      │
│                                                       ▼                      │
│  ┌─────────────────────┐    copy report    ┌─────────────────────┐          │
│  │ 4. Review           │ ◀─────────────────│ 4. STOP + Report    │          │
│  │    Progress Report  │                   │    Progress         │          │
│  └──────────┬──────────┘                   └─────────────────────┘          │
│             │                                                                │
│             ▼                                                                │
│  ┌─────────────────────┐                                                     │
│  │ 5. Approve/Reject   │──── if approved ────┐                              │
│  └─────────────────────┘                     │                              │
│             │                                ▼                              │
│             │                   ┌─────────────────────┐                     │
│             │   copy prompt     │ 6. Continue         │                     │
│             └──────────────────▶│    Milestone N+1    │                     │
│                                 └─────────────────────┘                     │
│                                                                              │
│  [Repeat until all milestones complete]                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Kickstart Prompts (Copy-Paste)

### Start Reviewer Session
```
Read CLAUDE_orchestrator.md. You are the REVIEWER agent.

Create an implementation plan for: [FEATURE DESCRIPTION]

1. Research the codebase to understand existing patterns
2. Create plan at: docs/[feature]/DOC_[feature]_plan.md
3. Define 3-5 milestones with clear deliverables
4. Generate the executor prompt for Milestone 1

After creating the plan, show me the prompt to send to the executor agent.
```

### Start Executor Session
```
Read CLAUDE_orchestrator.md. You are the EXECUTOR agent.

[PASTE PROMPT FROM REVIEWER AGENT]
```

### Reviewer: Approve & Continue
```
Milestone [N] approved.

Generate the prompt for the executor to continue with Milestone [N+1].
```

### Reviewer: Request Changes
```
Milestone [N] needs changes:
- [Issue 1]
- [Issue 2]

Generate a prompt for the executor to fix these issues.
```

### Executor: Continue
```
Milestone [N] approved. Continue with Milestone [N+1]:

[PASTE NEXT MILESTONE DETAILS FROM REVIEWER]
```

---

## Recovery Prompts (Copy-Paste)

### Recover Reviewer Session
```
Read CLAUDE_orchestrator.md. You are the REVIEWER agent.

Recovering session for: [FEATURE NAME]

Plan document: docs/[feature]/DOC_[feature]_plan.md

Current status:
- Milestones approved: [1, 2, ...]
- Current milestone: [N] (executor working / awaiting review)
- Blocking issues: [None / description]

[If executor submitted report, paste it here]

Continue reviewing from where we left off.
```

### Recover Executor Session (Same Session)
```
Context was compressed. Re-read:
- CLAUDE_orchestrator.md
- The plan document

Continue Milestone [N] from where we left off.
Last completed: [file/task]
```

### Recover Executor Session (New Session)
```
Read CLAUDE_orchestrator.md. You are the EXECUTOR agent.

Milestone [N] is IN PROGRESS. Previous executor crashed.

Plan document: [path]

Completed so far:
- [file1] created
- [task1] done

Remaining:
- [task2]
- [task3]

Continue from where the previous executor left off.
Stop and report when milestone is complete.
```

---

## Session State Template

Reviewer should track progress:

```markdown
## Session State: [Feature Name]

**Plan**: docs/[feature]/DOC_[feature]_plan.md

| Milestone | Status | Commit | Notes |
|-----------|--------|--------|-------|
| M1 | ✅ Approved | `abc123` | Serializers + tests |
| M2 | ✅ Approved | `def456` | Service layer |
| M3 | 🔄 In Progress | - | View + routes |
| M4 | ⏳ Pending | - | Final validation |

**Current**: Executor working on M3
**Blocking**: None
**Last Update**: [timestamp]
```

---

## Git Checkpoint Quick Reference

### Commit After Milestone Approval
```bash
git add -A
git commit -m "feat([feature]): complete M[N] - [description]"
```

### Commit Message Formats
| Event | Format |
|-------|--------|
| Milestone complete | `feat([feature]): complete M[N] - [description]` |
| Work in progress | `wip([feature]): M[N] in progress - [status]` |
| Checkpoint | `chore([feature]): checkpoint before [risky thing]` |

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

## Context Retention Quick Reference

### Critical Info by Agent

| Agent | Must Remember |
|-------|---------------|
| **Reviewer** | Plan doc path, current milestone #, approved milestones |
| **Executor** | Plan doc path, current milestone #, deliverables, test requirements |

### Re-read Triggers

**Reviewer** - Re-read if you:
- Forgot which milestones are approved
- Lost track of the plan document
- Can't remember executor prompt format

**Executor** - Re-read if you:
- Forgot progress report format
- Don't remember to STOP after milestone
- Lost track of deliverables

### Compression Recovery
```
"Context was compressed. Let me re-read the workflow and plan to continue properly."
```

---

## Progress Report Template

```markdown
## Milestone [N]: [Name] - COMPLETED

### Files Created/Modified:
- path/to/file.py (created)
- path/to/other.py (modified)

### Test Results:
```
[paste test output]
```

### Git Checkpoint:
```
[commit hash] - [commit message]
```

### Notes/Issues:
[Any blockers, deviations, or questions]

### Ready for Review: YES
```

### Final Milestone Addition
```markdown
### Coverage Report:
[paste coverage summary]

### TASK COMPLETE - Ready for Final Review
```

---

## Review Commands

| Action | Command |
|--------|---------|
| **Approve** | `Milestone [N] approved. Generate prompt for M[N+1].` |
| **Changes needed** | `Milestone [N] needs changes: [issues]. Generate fix prompt.` |
| **Approve with notes** | `Milestone [N] approved with notes: [observations]. Generate prompt for M[N+1].` |
| **Abort** | `ABORT: [Reason]. Do not proceed.` |

---

## ASCII UI Templates

Use these patterns in plan documents to communicate UI layout.

### Data Table with Filters

```
┌─────────────────────────────────────────────────────────────────┐
│  Page Title                                            [Action] │
├─────────────────────────────────────────────────────────────────┤
│  [Filter ▼]  [Filter ▼]  [Date Range]  [Search...]     [Reset] │
├─────────────────────────────────────────────────────────────────┤
│  Column 1   │ Column 2 │ Column 3  │ Status    │ Actions       │
│─────────────┼──────────┼───────────┼───────────┼───────────────│
│  Data       │ Data     │ Data      │ ✓ Done    │ [View] [Edit] │
│  Data       │ Data     │ Data      │ ⏳ Pending │ [View] [Edit] │
│  Data       │ Data     │ Data      │ ✗ Failed  │ [View] [Edit] │
├─────────────────────────────────────────────────────────────────┤
│  ◀ Prev    Page 1 of 10    Next ▶          Showing 1-20 of 156 │
└─────────────────────────────────────────────────────────────────┘
```

### Stats Dashboard

```
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Total Users │ │    Revenue   │ │  Pending Txs │ │ Active Today │
│    12,456    │ │   $1.2M      │ │      89      │ │    1,234     │
│   ▲ 12.5%    │ │   ▲ 8.3%     │ │   ▼ 5.2%     │ │   ▲ 15.1%    │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘

┌─────────────────────────────────┐ ┌─────────────────────────────┐
│  Chart: Volume Over Time        │ │  Chart: Distribution        │
│  ▁▂▃▅▆▇█▇▆▅▃▂▁▂▃▅▆▇█▇▆▅        │ │      ████ 45% Deposits      │
│  Jan  Feb  Mar  Apr  May  Jun   │ │      ███  30% Withdrawals   │
│                                 │ │      ██   20% Trades        │
│                                 │ │      █     5% Swaps         │
└─────────────────────────────────┘ └─────────────────────────────┘
```

### Form Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Create New [Entity]                                        [X] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Label *                                                        │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Input field                                               │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Select Option *                          Amount *              │
│  ┌─────────────────────────┐              ┌─────────────────┐   │
│  │ Option 1            ▼   │              │ 0.00            │   │
│  └─────────────────────────┘              └─────────────────┘   │
│                                                                 │
│  Description                                                    │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                                                           │  │
│  │ Textarea                                                  │  │
│  │                                                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│                                    [Cancel]  [Submit Button]    │
└─────────────────────────────────────────────────────────────────┘
```

### Detail Drawer/Modal

```
┌─────────────────────────────────────────────────────────────────┐
│  Transaction Details                                        [X] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Status: ✓ Completed                                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ID              abc-123-def-456                                │
│  Type            Deposit                                        │
│  Amount          100.00 USDT                                    │
│  Created         2024-01-15 10:30:00                            │
│  Completed       2024-01-15 10:35:00                            │
│  ─────────────────────────────────────────────────────────────  │
│  Network         TRC20                                          │
│  TX Hash         0x1234...5678                                  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Timeline                                               │    │
│  │  ● Created    10:30:00                                  │    │
│  │  ● Confirmed  10:32:00                                  │    │
│  │  ● Completed  10:35:00                                  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│                              [Close]  [Download]  [Take Action] │
└─────────────────────────────────────────────────────────────────┘
```

### Tabs Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                         │
│  │ Tab One  │ │ Tab Two  │ │ Tab Three│                         │
│  └──────────┘ └──────────┘ └──────────┘─────────────────────────│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                                                             ││
│  │  Tab Content Area                                           ││
│  │                                                             ││
│  │  - Item 1                                                   ││
│  │  - Item 2                                                   ││
│  │  - Item 3                                                   ││
│  │                                                             ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Empty State

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│                         ┌───────────┐                           │
│                         │    📭     │                           │
│                         └───────────┘                           │
│                                                                 │
│                      No transactions yet                        │
│                                                                 │
│            Your transactions will appear here once              │
│                   you make your first deposit.                  │
│                                                                 │
│                      [Make a Deposit]                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Status Indicators

```
Status Badges:     ✓ Success   ⏳ Pending   ✗ Failed   ○ Draft   ● Active

Progress:          [████████░░░░░░░░░░░░] 40%

Loading:           ◐ Loading...   ⟳ Refreshing...

Alerts:
┌─ ⚠ Warning ──────────────────────────────────────────────────┐
│  This action cannot be undone.                               │
└──────────────────────────────────────────────────────────────┘

┌─ ✓ Success ──────────────────────────────────────────────────┐
│  Transaction completed successfully.                          │
└──────────────────────────────────────────────────────────────┘

┌─ ✗ Error ────────────────────────────────────────────────────┐
│  Failed to process. Please try again.              [Retry]   │
└──────────────────────────────────────────────────────────────┘
```

---

## Milestone Patterns by Project Type

| Project Type | M1 | M2 | M3 | M4 |
|--------------|----|----|----|----|
| **API Endpoint** | Serializers + tests | Service + tests | View + routes + integration | Validation + docs |
| **Frontend Feature** | Types + components | Logic + hooks | Styling + responsive | Tests + storybook |
| **Bug Fix** | Failing test | Fix implementation | Verify + regression | Cleanup + docs |
| **Data Pipeline** | Schema + models | ETL logic | Orchestration | Monitoring + tests |
| **Infrastructure** | Config + resources | Network + security | Deployment | Validation + docs |

---

## Tips & Best Practices

### Plan Documents
- Include actual code examples, not just descriptions
- Reference existing files that demonstrate conventions
- Show anti-patterns (what NOT to do)
- List specific test scenarios

### Orchestrator Prompts
- Keep milestones focused (1-3 hours each)
- Include deliverable checklists
- Reference the plan document - don't duplicate

### Reviews
- Review quickly - don't leave executor waiting
- Be specific: "Fix X" not "This doesn't look right"
- Minor issues can be noted without blocking

### Session Management
- Reviewer stays in same session (maintains state)
- Executor can continue or start fresh per milestone
- If executor context gets long, start new session

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Agent continues without stopping | Add **⛔ STOP** in bold, repeat instruction |
| Progress report missing details | Specify exact format in milestone |
| Agent deviates from plan | Reference specific section of plan doc |
| Tests not comprehensive | List specific test cases in milestone |
| Executor confused after many milestones | Start fresh executor session |
| Lost track of progress | Use session state template |
| Context compressed | Use recovery prompts |
| Reviewer forgot approvals | Check git log for milestone commits |

---

## Related Files

| File | Purpose |
|------|---------|
| `CLAUDE_orchestrator.md` | Full framework + templates |
| `docs/[feature]/DOC_[feature]_plan.md` | Implementation plans |
| `CLAUDE_frontend_refactor_workflow.md` | Frontend-specific workflow |
| `CLAUDE_frontend_visual_qa_workflow.md` | Visual QA with MCP |
