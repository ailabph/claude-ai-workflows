# Claude Orchestrator: Batch Task Execution Framework

## Overview

A **batch-oriented workflow** for AI agents executing repetitive, time-consuming tasks. Designed for work that involves processing many similar items (files, endpoints, modules, records) where each item requires ~30 minutes of human effort.

**Key Difference from Standard Orchestrator:** Instead of 3-5 large milestones for a feature, this framework creates **one milestone per item** to process. Milestones function as todo items.

**Architecture**: Same two-agent model (Planner + Executor) with full orchestrator-auto compatibility.

---

## When to Use This Framework

| Use This Framework | Use Standard Orchestrator |
|--------------------|---------------------------|
| Processing many similar items | Building new features |
| Each item takes ~30 min | Each milestone takes 2-4 hours |
| Repetitive/mechanical work | Creative/architectural work |
| 10-50+ milestones typical | 3-5 milestones typical |
| Enumerable scope upfront | Scope emerges during work |

### Example Tasks

| Task | Items to Enumerate | Milestone Per |
|------|-------------------|---------------|
| Archive stale MD files | All `.md` files in repo | Folder or file group |
| Document API endpoints | All endpoints from OpenAPI/URL | Single endpoint |
| Migrate config files | All config files matching pattern | Single file |
| Update import statements | All files with old import | Single file |
| Audit security headers | All routes in application | Route group |
| Translate documentation | All docs in source language | Single document |
| Review PR comments | All open PRs with comments | Single PR |
| Migrate database records | All records matching criteria | Batch of N records |

---

## Core Principles

| Principle | Description |
|-----------|-------------|
| **Enumerate First** | Discovery phase identifies ALL items before planning |
| **One Item = One Milestone** | Each processable item becomes a milestone |
| **30-Minute Rule** | Each milestone ≈ 30 min of equivalent human work |
| **Batch When Needed** | Group tiny items (< 5 min each) into logical batches |
| **Progress Visibility** | Clear tracking: "Milestone 7/23 complete" |

---

## Phase Mapping to orchestrator-auto

This framework maps to orchestrator-auto's phases as follows:

| Batch Framework | orchestrator-auto Phase | What Happens |
|-----------------|------------------------|--------------|
| Discovery | **DISCOVERY** | Understand task, define processing rules |
| Enumeration | **DISCOVERY** (continued) | Find all items, count total |
| Planning | **PLANNING** | Create plan doc, define milestones |
| Execution | **EXECUTION** | Process each milestone with approval |
| Complete | **COMPLETED** | All milestones done |
| Blocked | **PAUSED** | Waiting for human input |

> **Note:** Enumeration is conceptually separate but happens within the DISCOVERY phase. The CLI will show `DISCOVERY` status during both discovery and enumeration.

---

## Workflow Phases

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BATCH TASK WORKFLOW                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  DISCOVERY PHASE              PLANNING PHASE        EXECUTION PHASE          │
│  ────────────────             ──────────────        ───────────────          │
│                                                                              │
│  1. Understand task           3. Create milestone   4. Process each          │
│     scope and criteria           for each item         milestone with        │
│                                  or logical batch      approval gate         │
│  2. Enumerate ALL items                                                      │
│     (files, endpoints,        Output:               Output:                  │
│     records, etc.)            - Plan doc with       - Completed items        │
│                                 N milestones        - Progress reports       │
│  Output:                      - [PLAN_READY] tag                             │
│  - Item list with paths                                                      │
│  - Processing rules                                                          │
│  - Skip conditions                                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Two-Agent Architecture

```
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│  PLANNER (Opus)                     │     │  EXECUTOR (Sonnet/Haiku)            │
├─────────────────────────────────────┤     ├─────────────────────────────────────┤
│  • Enumerates all items             │     │  • Processes ONE milestone          │
│  • Groups items into milestones     │────▶│  • Follows processing rules         │
│  • Defines acceptance criteria      │◀────│  • Reports status in [PROGRESS_     │
│  • Validates completion             │     │    REPORT] (done/skipped/failed)    │
│  • Tracks overall progress          │     │  • STOPS after each milestone       │
└─────────────────────────────────────┘     └─────────────────────────────────────┘
```

### Planner Responsibilities

1. **Discovery Phase**
   - Understand task requirements
   - Define processing rules (what to do with each item)
   - Define skip conditions (when to skip an item)
   - Define acceptance criteria (how to verify completion)

2. **Enumeration (within Discovery)**
   - Find ALL items matching criteria
   - Record item identifiers (paths, URLs, IDs)
   - Determine grouping strategy (one-per-milestone vs batched)
   - Calculate total milestone count

3. **Planning Phase**
   - Create plan document at canonical path
   - Define milestone for each item/batch
   - Emit `[PLAN_READY]` tag on its own line

4. **Review Phase**
   - Validate each milestone completion
   - Track progress (X of N complete)
   - Handle edge cases (skipped items, failures)
   - Emit `[MILESTONE_APPROVED]` or `[CHANGES_REQUESTED]`

### Executor Responsibilities

1. Process exactly ONE milestone
2. Follow the processing rules defined by planner
3. Report outcome in `[PROGRESS_REPORT]` with status field: COMPLETED / SKIPPED / FAILED
4. **STOP** and wait for approval
5. Never proceed to next milestone without explicit approval

### Context Management for Large Batches

For 10+ milestones, context management is critical:

| Milestone Count | Recommendation |
|-----------------|----------------|
| 1-10 | Same executor session is fine |
| 11-25 | New executor session every 5-10 milestones |
| 26-50 | New executor session every 3-5 milestones |
| 50+ | New executor session every milestone |

**Signs you need a fresh executor session:**
- Response quality declining
- Executor forgetting processing rules
- Context compression occurred (`/compact`)
- Executor conflating different items

**With orchestrator-auto:** The tool manages sessions automatically. For manual workflow, start a new Claude session and re-send the executor prompt.

---

## Response Tags (orchestrator-auto Compatible)

**IMPORTANT:** Only use these exact tags. The orchestrator-auto parser expects this specific vocabulary.

### Planner Tags

| Tag | When Used |
|-----|-----------|
| `[PLAN_READY]` | Enumeration complete, all milestones defined |
| `[MILESTONE_APPROVED]` | Item processed correctly, proceed to next |
| `[CHANGES_REQUESTED]` | Item needs reprocessing |
| `[HUMAN_INPUT_NEEDED]` | Blocker requiring human decision |

### Executor Tags

| Tag | When Used |
|-----|-----------|
| `[PROGRESS_REPORT]` | Milestone completion report (includes status: COMPLETED/SKIPPED/FAILED) |
| `[CLARIFICATION_NEEDED]` | Need planner clarification on processing rules |
| `[BLOCKED]` | External dependency or issue requiring human input |

### Representing Item Status

Skipped and failed items are represented as **status fields inside `[PROGRESS_REPORT]`**, not as separate tags:

```markdown
[PROGRESS_REPORT]
## Milestone 5: config/legacy.yaml - SKIPPED

**Status:** SKIPPED
**Reason:** File matches skip condition - contains 'DO NOT MIGRATE' comment

### Progress: 5 of 20 (25%) - 4 completed, 1 skipped
### Ready for Review: YES
[/PROGRESS_REPORT]
```

```markdown
[PROGRESS_REPORT]
## Milestone 8: services/auth/config.yaml - FAILED

**Status:** FAILED
**Error:** ValidationError - Field 'oauth_providers' has invalid format

### Progress: 8 of 20 (40%) - 6 completed, 1 skipped, 1 failed
### Ready for Review: YES
[/PROGRESS_REPORT]
```

When a failure requires human intervention, executor emits `[BLOCKED]`:

```markdown
[BLOCKED] Cannot proceed: Data format incompatible with automated migration

## Milestone 8: services/auth/config.yaml

**Details:** Field 'oauth_providers' is a string, expected array of objects
**Question:** Should I skip this file, or do you want to manually fix the format first?

### Progress: 8 of 20 (40%) - 6 completed, 1 skipped, 1 blocked
```

> **IMPORTANT:** The `[BLOCKED]` tag MUST be followed by `Cannot proceed:` on the same line for the parser to detect it.

---

## Plan Document Template

**Canonical path:** `docs/batch/BATCH_[task-name]_plan.md`

Examples:
- `docs/batch/BATCH_archive-stale-docs_plan.md`
- `docs/batch/BATCH_document-api-endpoints_plan.md`
- `docs/batch/BATCH_migrate-configs_plan.md`

### Planner Output Format (for orchestrator-auto)

When using `orchestrator start -f "..."` (planner generates the plan), the planner MUST wrap its output like this:

```markdown
[PLAN_READY]
Path: docs/batch/BATCH_[task-name]_plan.md
Milestones: [N] total

[PLAN_CONTENT]
# Batch Task: [Task Name]
... full plan content ...
[/PLAN_CONTENT]

Summary: [brief summary of the approach]
```

The orchestrator will save the plan file automatically. Do NOT use the Write tool for the plan document.

### Plan Content Structure

```markdown
# Batch Task: [Task Name]

## 1. Task Definition

### Objective
[One sentence: what are we processing and why]

### Processing Rules
For each item:
1. [Action 1]
2. [Action 2]
3. [Verification step]

### Skip Conditions
Skip item if:
- [Condition 1]
- [Condition 2]

### Acceptance Criteria
Item is complete when:
- [ ] [Criterion 1]
- [ ] [Criterion 2]

## 2. Enumerated Items

| # | Item Identifier | Path/URL | Notes |
|---|-----------------|----------|-------|
| 1 | [name] | [path] | |
| 2 | [name] | [path] | |
| ... | ... | ... | |

**Total Items:** [N]
**Estimated Time:** [N × 30 min = X hours]

## 3. Grouping Strategy

[One of:]
- **One-per-milestone**: Each item is its own milestone (recommended for items > 10 min)
- **Batched**: Items grouped by [criterion] (~5-10 items per milestone)

## 4. Milestones

### Milestone 1: [Item/Batch Name]
- **Items:** [item identifier(s)]
- **Path(s):** [file paths or URLs]
- **Action:** [specific action for this item]
- **Acceptance:** [how to verify this specific item]

### Milestone 2: [Item/Batch Name]
...

[Repeat for all milestones]

## 5. Progress Tracking

| Milestone | Item | Status | Notes |
|-----------|------|--------|-------|
| M1 | [item] | ⏳ Pending | |
| M2 | [item] | ⏳ Pending | |
| ... | ... | ... | |

Status legend: ⏳ Pending | 🔄 In Progress | ✅ Complete | ⏭️ Skipped | ❌ Failed

## 6. Recovery Checkpoint

Last updated: [timestamp]
Current milestone: [N]
Completed: [X] | Skipped: [Y] | Failed: [Z]

[PLAN_READY]
```

> **Tag placement:** The `[PLAN_READY]` tag MUST appear on its own line at the end of the plan output.

---

## Progress Report Template

```markdown
[PROGRESS_REPORT]
## Milestone [N]: [Item Name] - [STATUS]

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
- [ ] [Criterion 1]: [PASS/FAIL]
- [ ] [Criterion 2]: [PASS/FAIL]

### Files Modified:
- [path] (created|modified|deleted|unchanged)

### Progress: [N] of [Total] ([percentage]%)
- Completed: [X]
- Skipped: [Y]
- Failed: [Z]

### Ready for Review: YES
[/PROGRESS_REPORT]
```

> **Tag placement:**
> - `[PROGRESS_REPORT]` MUST appear on its own line at the very beginning
> - `[/PROGRESS_REPORT]` MUST appear on its own line at the very end
> - Milestone header format: `## Milestone N:` (NOT `## Milestone N/Total:`)

---

## Recovery and State Tracking

For batch tasks with many milestones, recovery is critical. Track state explicitly.

### State Tracking Table

Maintain this in the plan document and update after each milestone:

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

### Recovery After Crash/Interruption

If a session crashes or context is lost:

1. **Read the plan document** at `docs/batch/BATCH_[task]_plan.md`
2. **Check the Recovery State table** for current milestone
3. **Resume from current milestone** (not from the beginning)

**Recovery prompt for Planner:**
```
Read CLAUDE_orchestrator_batch.md. You are the PLANNER recovering a batch task.

Plan document: docs/batch/BATCH_[task]_plan.md

Check the Recovery State section and continue from where we left off.
Generate the executor prompt for the next pending milestone.
```

### Re-enumeration Checkpoints

For long-running batch tasks (50+ milestones or multi-day execution):

- **Re-enumerate at 50% completion** to catch:
  - New items added since enumeration
  - Items deleted/moved since enumeration
  - Scope drift

- **Re-enumerate after any failure** that might indicate systemic issues

**Re-enumeration prompt:**
```
Pause execution. Re-enumerate items to check for:
1. New items matching criteria that weren't in original list
2. Items that no longer exist (deleted/moved)
3. Any scope drift

Compare with original enumeration and report differences.
```

---

## Managing Approval Overhead

For 10-50+ milestones, approval overhead becomes significant. Strategies to manage:

### Batch Approvals

When items are formulaic and low-risk, approve in batches:

```
[MILESTONE_APPROVED] Milestone 12 approved. Batch approved: milestones 7-12 all followed the expected pattern.

Continue with Milestone 13: [Item Name]
```

> **Parser requirement:** The `[MILESTONE_APPROVED]` tag must be followed by "Milestone N approved" (singular, with highest milestone number) for the parser to extract the milestone number. Additional batch context can follow.

**Use batch approvals when:**
- Items are highly similar
- Processing is mechanical (no judgment calls)
- Previous items in batch all succeeded
- Risk of error is low

**Don't batch approve when:**
- Items have different characteristics
- Any item in batch was skipped or failed
- Processing involves destructive operations
- Items require individual verification

### Approval Thresholds

| Risk Level | Approval Strategy |
|------------|-------------------|
| **Low** (docs, formatting) | Batch approve 5-10 at a time |
| **Medium** (config, code) | Batch approve 2-3, or individual |
| **High** (data, security) | Individual approval required |

### Progressive Trust

Start with individual approvals, then batch as patterns emerge:

1. **Milestones 1-3:** Individual approval (establish pattern)
2. **Milestones 4-10:** Batch approve 2-3 if consistent
3. **Milestones 11+:** Batch approve 5+ if highly consistent

---

## Git Commits for Batch Tasks

### Auto-commit Behavior

**Important:** orchestrator-auto's `--auto-commit` commits **per session completion**, not per milestone.

| Mode | Commit Timing |
|------|---------------|
| Single session | Commits when session completes (all milestones done) |
| Queue mode | Commits after each plan/session completes |

### Manual Commits for Rollback Points

If you need per-milestone rollback points, commit manually after approvals:

```bash
# After approving milestone 5
git add -A
git commit -m "batch(archive-docs): complete M5 - docs/api/ archived"
```

### Recommended Commit Strategy

| Milestone Count | Strategy |
|-----------------|----------|
| 1-10 | Auto-commit at end is fine |
| 11-25 | Manual commit every 5 milestones |
| 26-50 | Manual commit every 3 milestones |
| 50+ | Manual commit every milestone |

**Commit message format:**
```
batch([task]): complete M[N] - [brief description]

Processed: [X] | Skipped: [Y] | Failed: [Z]
```

---

## Example Workflows

### Example 1: Archive Stale Markdown Files

**Task:** Find and archive markdown files not updated in 6+ months

**Plan document:** `docs/batch/BATCH_archive-stale-docs_plan.md`

```markdown
# Batch Task: Archive Stale Documentation

## 1. Task Definition

### Objective
Move markdown files not updated in 6+ months to archive/ folder.

### Processing Rules
For each stale .md file:
1. Check last modified date via git log
2. If > 6 months old, move to `archive/[original-path]/`
3. Update any internal links pointing to archived file
4. Verify no broken links introduced

### Skip Conditions
Skip item if:
- File is in `archive/` already
- File is `README.md`, `CHANGELOG.md`, or `CONTRIBUTING.md`
- File was modified in last 6 months
- File is referenced by non-archived files (would break links)

### Acceptance Criteria
Item is complete when:
- [ ] File moved to archive/
- [ ] Internal links updated
- [ ] No broken link errors

## 2. Enumerated Items (grouped by folder)

| # | Folder | Stale Files | Est. Time |
|---|--------|-------------|-----------|
| 1 | docs/api/ | 6 files | 30 min |
| 2 | docs/guides/ | 8 files | 30 min |
| 3 | docs/internal/ | 4 files | 20 min |
| 4 | specs/ | 3 files | 15 min |

**Total:** 4 milestones, 21 files, ~2 hours

## 3. Grouping Strategy
**Batched**: Grouped by folder (each folder ~30 min)

## 4. Milestones

### Milestone 1: docs/api/
- **Items:** auth.md, users.md, payments.md, orders.md, webhooks.md, legacy-v1.md
- **Action:** Archive all 6 files, update links in docs/guides/

### Milestone 2: docs/guides/
...

## 5. Recovery State

| Field | Value |
|-------|-------|
| **Last Updated** | - |
| **Current Milestone** | 1 |
| **Completed** | 0 |
| **Skipped** | 0 |
| **Failed** | 0 |

[PLAN_READY]
```

**Milestone 1 Report:**
```markdown
[PROGRESS_REPORT]
## Milestone 1: docs/api/ - COMPLETED

**Status:** COMPLETED

### Items Processed: 6 files
- `docs/api/auth.md` → archived (last modified: 2024-03-15)
- `docs/api/users.md` → archived (last modified: 2024-02-20)
- `docs/api/payments.md` → archived (last modified: 2024-04-01)
- `docs/api/orders.md` → archived (last modified: 2024-01-10)
- `docs/api/webhooks.md` → archived (last modified: 2024-05-22)
- `docs/api/legacy-v1.md` → archived (last modified: 2023-11-30)

### Files Modified:
- archive/docs/api/auth.md (created)
- archive/docs/api/users.md (created)
- archive/docs/api/payments.md (created)
- archive/docs/api/orders.md (created)
- archive/docs/api/webhooks.md (created)
- archive/docs/api/legacy-v1.md (created)
- docs/guides/quickstart.md (modified - updated 3 links)
- docs/guides/authentication.md (modified - updated 1 link)

### Verification:
- [x] All 6 files moved to archive/
- [x] Internal links updated (4 links in 2 files)
- [x] No broken link errors (ran link checker)

### Progress: 1 of 4 (25%)
- Completed: 1
- Skipped: 0
- Failed: 0

### Ready for Review: YES
[/PROGRESS_REPORT]
```

---

### Example 2: Document API Endpoints

**Task:** Create documentation for all endpoints from OpenAPI spec

**Plan document:** `docs/batch/BATCH_document-api-endpoints_plan.md`

```markdown
# Batch Task: Document API Endpoints

## 1. Task Definition

### Objective
Generate markdown documentation for each API endpoint from OpenAPI spec.

### Processing Rules
For each endpoint:
1. Extract endpoint details from OpenAPI spec
2. Create markdown doc at `docs/api/[tag]/[operation-id].md`
3. Include: method, path, description, parameters, request body, responses
4. Add authentication requirements
5. Include example request/response

### Skip Conditions
Skip endpoint if:
- Documentation file already exists and is newer than spec
- Endpoint is marked deprecated AND has replacement documented

### Acceptance Criteria
Endpoint doc is complete when:
- [ ] All parameters documented
- [ ] Request/response examples included
- [ ] Authentication noted
- [ ] Linked from API index

## 2. Enumerated Endpoints

| # | Method | Path | Tag | Operation ID |
|---|--------|------|-----|--------------|
| 1 | GET | /api/v1/users | Users | listUsers |
| 2 | POST | /api/v1/users | Users | createUser |
| 3 | GET | /api/v1/users/{id} | Users | getUser |
| 4 | PUT | /api/v1/users/{id} | Users | updateUser |
| 5 | DELETE | /api/v1/users/{id} | Users | deleteUser |
| 6 | GET | /api/v1/orders | Orders | listOrders |
| ... | ... | ... | ... | ... |

**Total:** 23 endpoints, 23 milestones, ~12 hours

## 3. Grouping Strategy
**One-per-milestone**: Each endpoint is complex enough for individual milestone

[PLAN_READY]
```

---

### Example 3: Migrate Database Records

**Task:** Migrate user records from legacy format to new schema

**Plan document:** `docs/batch/BATCH_migrate-user-records_plan.md`

```markdown
# Batch Task: Migrate User Records

## 1. Task Definition

### Objective
Migrate 50,000 user records from legacy schema (v1) to new schema (v2).

### Processing Rules
For each batch of 1,000 records:
1. Query legacy table using cursor: `WHERE id > [last_processed_id] ORDER BY id LIMIT 1000`
2. Transform each record to new schema
3. Validate transformed data
4. Insert into new table (idempotent - use upsert)
5. Verify record count matches
6. Update checkpoint cursor to max(id) in batch

> **Note:** Use cursor-based pagination (`WHERE id > X`), not OFFSET. OFFSET becomes slow at scale and can skip/duplicate rows if data changes during migration.

### Skip Conditions
Skip record if:
- Record already exists in new table with same updated_at timestamp
- Record is marked as deleted in legacy table

### Acceptance Criteria
Batch is complete when:
- [ ] All valid records transformed
- [ ] Validation passed (no schema errors)
- [ ] Upsert completed
- [ ] Record counts match
- [ ] Checkpoint updated

### Idempotency
- Uses upsert (INSERT ON CONFLICT UPDATE)
- Safe to re-run any batch
- Checkpoint allows resume from any point

### Rollback Plan
- New table can be truncated to restart
- Legacy table is read-only (not modified)
- Each batch is atomic (transaction)

## 2. Enumerated Batches

| # | Batch | ID Range | Record Count |
|---|-------|----------|--------------|
| 1 | Batch 1 | 1-1000 | 1,000 |
| 2 | Batch 2 | 1001-2000 | 1,000 |
| 3 | Batch 3 | 2001-3000 | 1,000 |
| ... | ... | ... | ... |
| 50 | Batch 50 | 49001-50000 | 1,000 |

**Total:** 50 batches, 50,000 records, ~25 hours

## 3. Grouping Strategy
**Batched**: 1,000 records per milestone (~30 min each)

## 4. Checkpointing

```sql
-- Checkpoint table
CREATE TABLE migration_checkpoint (
  task_name VARCHAR PRIMARY KEY,
  last_processed_id BIGINT,
  processed_count INT,
  skipped_count INT,
  failed_count INT,
  updated_at TIMESTAMP
);
```

After each batch:
```sql
UPDATE migration_checkpoint
SET last_processed_id = [max_id_in_batch],
    processed_count = processed_count + [batch_count],
    updated_at = NOW()
WHERE task_name = 'user_migration_v1_to_v2';
```

## 5. Dry Run Mode

First milestone should be dry-run:
- Process Batch 1 with `DRY_RUN=true`
- Log transformations without committing
- Verify output format
- Get explicit approval before live run

## 6. Sampling Verification

After every 10 batches, verify sample:
- Random sample 10 records from migrated data
- Compare with legacy source
- Report any discrepancies

## 7. Recovery State

| Field | Value |
|-------|-------|
| **Checkpoint Table** | migration_checkpoint |
| **Last Processed ID** | 0 |
| **Processed** | 0 |
| **Skipped** | 0 |
| **Failed** | 0 |

[PLAN_READY]
```

**Milestone 1 Report (Dry Run):**
```markdown
[PROGRESS_REPORT]
## Milestone 1: Batch 1 (Dry Run) - COMPLETED

**Status:** COMPLETED

### Batch Details:
- **ID Range:** 1-1000
- **Mode:** DRY_RUN (no commits)

### Results:
- Records processed: 1,000
- Transformations successful: 987
- Skipped (already migrated): 8
- Skipped (deleted in legacy): 5
- Validation errors: 0

### Sample Transformations:
```json
// Record ID: 1
// Legacy:
{"user_id": 1, "name": "John Doe", "email_addr": "john@example.com", "created": "2020-01-15"}

// Transformed:
{"id": 1, "full_name": "John Doe", "email": "john@example.com", "created_at": "2020-01-15T00:00:00Z", "schema_version": 2}
```

### Verification:
- [x] All 1,000 records processed
- [x] Schema validation passed
- [x] No data truncation
- [x] Timestamps converted correctly

### Progress: 1 of 50 (2%)
- Completed: 1 (dry run)
- Skipped: 0
- Failed: 0

### Next Steps:
Awaiting approval to proceed with live migration (Batch 1 with commits, then continue).

### Ready for Review: YES
[/PROGRESS_REPORT]
```

---

## Batching Strategy

### When to Batch Items

| Item Processing Time | Strategy |
|---------------------|----------|
| < 5 minutes each | Batch 5-10 items per milestone |
| 5-15 minutes each | Batch 2-3 items per milestone |
| 15-30 minutes each | One item per milestone |
| > 30 minutes each | Split item into sub-tasks |

### Batching by Logical Groups

Group items that share:
- Same folder/directory
- Same file type
- Same processing rules
- Related functionality

**Example:** Instead of 50 milestones for 50 files, create 8 milestones by folder:
```
Milestone 1: src/components/*.tsx (12 files)
Milestone 2: src/hooks/*.ts (8 files)
Milestone 3: src/services/*.ts (6 files)
...
```

---

## Integration with orchestrator-auto

This framework is fully compatible with orchestrator-auto:

```bash
# Start batch task
orchestrator start -f "Archive stale markdown files in docs/"

# With existing plan
orchestrator start --plan docs/batch/BATCH_archive-stale-docs_plan.md

# Queue multiple batch plans
orchestrator start --queue batch-plan1.md batch-plan2.md

# Resume after reviewing milestone
orchestrator resume <session-id>

# Respond to blocker
orchestrator respond <session-id> "Skip this file, it's referenced externally"
```

### Recommended Settings for Batch Tasks

| Setting | Recommendation | Reason |
|---------|---------------|--------|
| Planner model | `sonnet` | Enumeration needs thoroughness but not creativity |
| Executor model | `haiku` | Repetitive tasks, cost efficiency |
| Auto-commit | Use for small batches | Commits at session end, not per milestone |
| Telegram | Enable | Get notified on blockers in long-running tasks |

```bash
# Cost-optimized batch processing
orchestrator start -f "Document all 50 API endpoints" -pm sonnet -em haiku --telegram
```

### For Per-Milestone Commits

If you need rollback points per milestone, don't rely on `--auto-commit`. Instead:

1. Run without `--auto-commit`
2. After each milestone approval, manually commit:
   ```bash
   git add -A && git commit -m "batch(task): complete M[N]"
   ```
3. Or use a post-approval hook if available

---

## Kickstart Prompts

### Start Batch Task (Planner)

```
Read CLAUDE_orchestrator_batch.md. You are the PLANNER for a batch task.

Task: [DESCRIBE THE REPETITIVE TASK]

1. DISCOVERY: Understand what needs to be processed, define rules
2. ENUMERATION: Find ALL items (files, endpoints, records, etc.)
3. PLANNING: Create plan doc at docs/batch/BATCH_[task-name]_plan.md
   - One milestone per item (or logical batch of ~30 min)
   - Include Recovery State section
   - End with [PLAN_READY] tag on its own line

Processing scope: [FOLDER/URL/DATABASE/etc.]

After creating the plan, show me:
- Total item count
- Grouping strategy
- Estimated time
- The executor prompt for Milestone 1
```

### Continue After Approval (Planner)

```
Milestone [N] approved.

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

> **Note:** Use the highest milestone number after "Milestone" for parser compatibility.

### Executor Prompt Template

```
Read CLAUDE_orchestrator_batch.md. You are the EXECUTOR.

## Current Milestone: [N] of [Total]

### Item to Process:
- **Identifier:** [name]
- **Path/URL:** [location]

### Processing Rules:
[Copy from plan]

### Skip Conditions:
[Copy from plan]

### Acceptance Criteria:
[Copy from plan]

Process this item. Your response MUST:
1. Start with [PROGRESS_REPORT] on its own line
2. Use header format: ## Milestone N: [Name] - [STATUS]
3. End with [/PROGRESS_REPORT] on its own line

Include status (COMPLETED/SKIPPED/FAILED) and progress counts.
STOP and wait for approval.
```

### Recovery Prompt (Planner)

```
Read CLAUDE_orchestrator_batch.md. You are the PLANNER recovering a batch task.

Plan document: docs/batch/BATCH_[task-name]_plan.md

1. Read the plan and Recovery State section
2. Identify the current milestone and progress
3. Generate the executor prompt to continue from where we left off

If more than 50% complete, consider re-enumeration to check for scope drift.
```

---

## Summary Checklist

Before starting a batch task:

- [ ] Task involves processing multiple similar items
- [ ] Each item takes ~30 min (or can be batched to ~30 min)
- [ ] Items can be enumerated upfront
- [ ] Processing rules are consistent across items
- [ ] Skip conditions are defined
- [ ] Acceptance criteria are clear
- [ ] Plan stored at `docs/batch/BATCH_[task]_plan.md`

During execution:

- [ ] Planner enumerated ALL items before `[PLAN_READY]`
- [ ] Planner wrapped plan in `[PLAN_CONTENT]...[/PLAN_CONTENT]` (for orchestrator-auto)
- [ ] Each milestone has clear item identifier
- [ ] Executor report starts with `[PROGRESS_REPORT]` and ends with `[/PROGRESS_REPORT]`
- [ ] Milestone header uses `## Milestone N:` format (not N/Total)
- [ ] Status field indicates COMPLETED/SKIPPED/FAILED
- [ ] `[BLOCKED]` uses `Cannot proceed:` format
- [ ] Progress tracked: N of Total with counts
- [ ] Recovery State updated after each milestone
- [ ] Re-enumerate at 50% for long tasks

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-01 | Initial batch task framework |
| 1.1 | 2025-01 | Fixed orchestrator-auto compatibility: removed custom tags, added explicit tag placement, fixed auto-commit docs, added recovery/state tracking, added data migration example, added batch approvals guidance, added phase mapping |
| 1.2 | 2025-01 | Parser compatibility fixes: added `[/PROGRESS_REPORT]` closing tag, fixed `[BLOCKED]` format to use `Cannot proceed:`, changed milestone header from `N/Total` to `N`, added `[PLAN_CONTENT]` wrapper requirement, fixed OFFSET to cursor-based pagination in data migration example, fixed batch approval to use singular "Milestone N approved" format |
