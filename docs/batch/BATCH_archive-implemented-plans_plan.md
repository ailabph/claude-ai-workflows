# Batch Task: Archive Implemented Plan Files

## 1. Task Definition

### Objective
Find all `*_plan*.md` files in the repository, assess implementation status, and archive implemented plans by moving them to an `archive/` subfolder in their respective directories.

### Processing Rules
For each plan file:
1. Read the plan content to understand what it describes
2. Check the codebase for evidence of implementation (files exist, features present)
3. If IMPLEMENTED: create `archive/` subfolder in same directory and move file there
4. If NOT IMPLEMENTED: leave in place (no action)

### Skip Conditions
Skip plan file if:
- Plan is NOT implemented (feature/code doesn't exist in codebase)
- Plan file is this batch plan document itself

### Acceptance Criteria
Plan is considered IMPLEMENTED when:
- [ ] Core modules/files described in plan exist
- [ ] Key functions/features described are present in codebase
- [ ] CLI commands (if applicable) are functional

---

## 2. Enumerated Items

| # | Plan File | Location | Implementation Status | Action |
|---|-----------|----------|----------------------|--------|
| 1 | DOC_orchestrator_auto_plan.md | docs/orchestrator-auto/ | **IMPLEMENTED** | Archive |
| 2 | FEATURE_import_existing_plan.md | orchestrator-auto/docs/ | **IMPLEMENTED** | Archive |
| 3 | DOC_wheel_game_plan.md | / (root) | **NOT IMPLEMENTED** | Skip |
| 4 | DOC_telegram_ping_pong_plan.md | docs/orchestrator-auto/ | **NOT IMPLEMENTED** | Skip |
| 5 | DOC_direct_chat_plan.md | docs/direct-chat/ | **IMPLEMENTED** | Archive |
| 6 | DOC_auth_source_detection_plan.md | docs/orchestrator-auto/ | **IMPLEMENTED** | Archive |

**Total Plans Found:** 6
**Implemented (to archive):** 4
**Not Implemented (skip):** 2

---

## 3. Assessment Evidence

### 3.1 DOC_orchestrator_auto_plan.md - IMPLEMENTED

**Evidence:**
- Package structure exists: `orchestrator-auto/orchestrator_auto/`
- All planned modules present: `cli.py`, `engine.py`, `agents.py`, `state.py`, `parser.py`, `db.py`, `recovery.py`, `prompts.py`
- SQLite database implementation exists
- CLI commands functional (`orchestrator start`, `resume`, `list`, etc.)

**Verdict:** Archive to `docs/orchestrator-auto/archive/`

---

### 3.2 FEATURE_import_existing_plan.md - IMPLEMENTED

**Evidence:**
- `--plan` flag present in `cli.py`
- `--plan` documented in `README.md`
- `parse_plan_file()` function exists in `parser.py`

**Verdict:** Archive to `orchestrator-auto/docs/archive/`

---

### 3.3 DOC_wheel_game_plan.md - NOT IMPLEMENTED

**Evidence:**
- Plan describes Django backend (`backend/apps/lucky_draw/`) - not in this repo
- Plan describes frontend components - not in this repo
- This appears to be a plan for a different project

**Verdict:** Skip (leave in place)

---

### 3.4 DOC_telegram_ping_pong_plan.md - NOT IMPLEMENTED

**Evidence:**
- No `def ping` command found in `telegram.py` or `cli.py`
- No `send_ping()` or `wait_for_pong()` methods exist
- Feature described in plan not present

**Verdict:** Skip (leave in place)

---

### 3.5 DOC_direct_chat_plan.md - IMPLEMENTED

**Evidence:**
- `chat.py` module exists
- `chat` command present in `cli.py`
- `ChatSession` class implemented
- `create_chat_agent()` factory exists in `agents.py`

**Verdict:** Archive to `docs/direct-chat/archive/`

---

### 3.6 DOC_auth_source_detection_plan.md - IMPLEMENTED

**Evidence:**
- `auth.py` module exists with `detect_auth()` function
- `AuthSource` enum, `AuthInfo` dataclass present
- `auth_source` columns in database schema
- Auth display integrated in CLI

**Verdict:** Archive to `docs/orchestrator-auto/archive/`

---

## 4. Grouping Strategy

**Batched by directory**: Group plans by their parent directory to minimize archive folder creation operations.

| Milestone | Directory | Plans to Archive |
|-----------|-----------|------------------|
| M1 | docs/orchestrator-auto/ | DOC_orchestrator_auto_plan.md, DOC_auth_source_detection_plan.md |
| M2 | orchestrator-auto/docs/ | FEATURE_import_existing_plan.md |
| M3 | docs/direct-chat/ | DOC_direct_chat_plan.md |

---

## 5. Milestones

### Milestone 1: Archive docs/orchestrator-auto/ plans
- **Directory:** `docs/orchestrator-auto/`
- **Items:**
  - `DOC_orchestrator_auto_plan.md`
  - `DOC_auth_source_detection_plan.md`
- **Action:**
  1. Create `docs/orchestrator-auto/archive/` directory
  2. Move both plan files to archive
- **Acceptance:** Files exist in archive, not in original location

---

### Milestone 2: Archive orchestrator-auto/docs/ plan
- **Directory:** `orchestrator-auto/docs/`
- **Items:**
  - `FEATURE_import_existing_plan.md`
- **Action:**
  1. Create `orchestrator-auto/docs/archive/` directory
  2. Move plan file to archive
- **Acceptance:** File exists in archive, not in original location

---

### Milestone 3: Archive docs/direct-chat/ plan
- **Directory:** `docs/direct-chat/`
- **Items:**
  - `DOC_direct_chat_plan.md`
- **Action:**
  1. Create `docs/direct-chat/archive/` directory
  2. Move plan file to archive
- **Acceptance:** File exists in archive, not in original location

---

## 6. Progress Tracking

| Milestone | Item | Status | Notes |
|-----------|------|--------|-------|
| M1 | DOC_orchestrator_auto_plan.md | Pending | |
| M1 | DOC_auth_source_detection_plan.md | Pending | |
| M2 | FEATURE_import_existing_plan.md | Pending | |
| M3 | DOC_direct_chat_plan.md | Pending | |

Status legend: Pending | In Progress | Complete | Skipped

---

## 7. Recovery Checkpoint

| Field | Value |
|-------|-------|
| **Last Updated** | - |
| **Current Milestone** | 1 |
| **Completed** | 0 |
| **Skipped** | 2 (DOC_wheel_game_plan.md, DOC_telegram_ping_pong_plan.md) |
| **Failed** | 0 |

---

## 8. Executor Prompt (Milestone 1)

```
You are the EXECUTOR for a batch task.

## Current Milestone: 1 of 3

### Items to Process:
- **File 1:** docs/orchestrator-auto/DOC_orchestrator_auto_plan.md
- **File 2:** docs/orchestrator-auto/DOC_auth_source_detection_plan.md

### Processing Rules:
1. Create archive directory: `docs/orchestrator-auto/archive/`
2. Move DOC_orchestrator_auto_plan.md to archive/
3. Move DOC_auth_source_detection_plan.md to archive/
4. Verify files exist in new location
5. Verify files removed from original location

### Acceptance Criteria:
- [ ] Archive directory exists
- [ ] Both files moved successfully
- [ ] No broken references

Process these items. Generate [PROGRESS_REPORT] when done. STOP and wait for approval.
```

[PLAN_READY]
