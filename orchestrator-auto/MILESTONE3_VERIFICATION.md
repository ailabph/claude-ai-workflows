# Milestone 3: CLI `start --queue` - Implementation Verification

## ✅ Completed Tasks

### 1. Updated `orchestrator start` Command Signature
**Location:** `orchestrator_auto/cli.py` lines 344-413

#### Changes Made:
- ✅ Made `--feature/-f` conditionally required (not required when `--queue` or `--plan` is provided)
- ✅ Added `--queue` flag for queue mode
- ✅ Added `--queue-reset` flag to overwrite existing queue
- ✅ Added variadic `queue_plans` argument: `@click.argument('queue_plans', nargs=-1, type=click.Path(exists=True))`
- ✅ Maintains backwards compatibility for non-queue mode

#### Signature:
```python
@cli.command()
@click.option('--feature', '-f', required=False, ...)
@click.option('--db-path', '-d', ...)
@click.option('--plan', '-p', type=click.Path(exists=True), ...)
@click.option('--queue', is_flag=True, ...)
@click.option('--queue-reset', is_flag=True, ...)
@click.argument('queue_plans', nargs=-1, type=click.Path(exists=True))
...
def start(...)
```

### 2. Input Validation
**Location:** `orchestrator_auto/cli.py` lines 378-386

#### Validation Rules Implemented:
- ✅ `--queue` and `--plan` are mutually exclusive
- ✅ `--feature` is required unless `--queue` or `--plan` is provided
- ✅ Error messages guide users to correct usage

### 3. Queue Mode Handler
**Location:** `orchestrator_auto/cli.py` lines 183-312

Implemented `_handle_queue_mode()` function with complete logic:

#### Resume Existing Queue (no plans provided):
- ✅ `--queue` with no `queue_plans` → resume existing queue
- ✅ Error if no active queue exists
- ✅ Display existing queue status

#### Create New Queue (plans provided):
- ✅ Validate all plan files upfront using `parse_plan_file()`
- ✅ Show validation results (✓/✗ per plan)
- ✅ Exit if any validation fails

#### Queue Matching Logic:
- ✅ If no active queue: create new queue items
- ✅ If active queue exists:
  - ✅ Normalize paths (absolute paths) for comparison
  - ✅ If plans match exactly: treat as resume
  - ✅ If mismatch without `--queue-reset`: error with instructions
  - ✅ If mismatch with `--queue-reset`: clear and recreate

### 4. Queue Creation
**Location:** `orchestrator_auto/cli.py` lines 274-300

- ✅ Determine project identity using `get_project_identity()`
- ✅ Extract feature description from each plan using `extract_feature_from_plan()`
- ✅ Create queue items in database with:
  - project_id (from `get_project_identity`)
  - plan_path (normalized absolute path)
  - feature_description (from extraction)
  - position (0-based index)
- ✅ Store in order provided by user

### 5. Queue Status Display
**Location:** `orchestrator_auto/cli.py` lines 315-334

Implemented `_display_queue_status()` function:

```
Queue: 3 plans
  1. [PENDING] plan1.md - "User Authentication"
  2. [PENDING] plan2.md - "API Rate Limiting"
  3. [PENDING] plan3.md - "Database Migration Tools"
```

Features:
- ✅ Shows position number (1-based for display)
- ✅ Color-coded status ([PENDING], [RUNNING], [COMPLETED], etc.)
- ✅ Plan filename (not full path for readability)
- ✅ Extracted feature description in quotes

### 6. Backwards Compatibility
**Location:** `orchestrator_auto/cli.py` lines 400-472

- ✅ Non-queue mode continues to work exactly as before
- ✅ All existing options preserved
- ✅ Original workflow logic unchanged

### 7. New Imports Added
**Location:** `orchestrator_auto/cli.py` lines 14-28

```python
from .parser import extract_feature_from_plan, parse_plan_file
from .config import get_project_identity
```

## Usage Examples

### Create Queue
```bash
orchestrator start --queue plan1.md plan2.md plan3.md
```

### Resume Existing Queue
```bash
orchestrator start --queue
```

### Reset and Recreate Queue
```bash
orchestrator start --queue --queue-reset plan1.md plan2.md
```

### Original Non-Queue Mode (unchanged)
```bash
orchestrator start -f "Add authentication"
orchestrator start --plan docs/plan.md -f "Auth feature"
```

## Deliverables Checklist

- [x] `orchestrator start --queue ...` accepted
- [x] Backwards compatible non-queue start behavior
- [x] Upfront validation of all plans
- [x] Persisted queue items in database
- [x] Queue creation UX output
- [x] Queue matching logic (resume if same plans)
- [x] `--queue-reset` flag for overwriting
- [x] Project scoping using `get_project_identity()`
- [x] Feature extraction from plans
- [x] Error handling with helpful messages

## Test Files Created

- `test_plans/plan1.md` - "User Authentication" (Implementation Plan format)
- `test_plans/plan2.md` - "API Rate Limiting" (Feature format)
- `test_plans/plan3.md` - "Database Migration Tools" (YAML frontmatter)

## Implementation Notes

### Queue Runner Note
The `_handle_queue_mode()` function currently creates and validates the queue, then displays:
```
⚠ Queue runner not yet implemented (Milestone 4)
For now, queue has been created and persisted to database.
```

This is intentional - the actual queue runner loop will be implemented in Milestone 4.

### Path Normalization
All paths are normalized to absolute paths using `Path.resolve()` before:
- Storing in database
- Comparing for queue matching

This ensures that `docs/plan.md` and `./docs/plan.md` are recognized as the same file.

### Feature Extraction Integration
Successfully integrated Milestone 2's `extract_feature_from_plan()`:
- YAML frontmatter: `feature: <description>`
- `# Feature:` header
- `# Implementation Plan:` header
- Plain `# Title`
- Filename fallback

All work correctly in queue creation flow.

### Error Messages
All error conditions provide clear, actionable messages:
- "No active queue found" → tells user how to create one
- "Active queue exists with different plans" → shows diff and suggests `--queue-reset`
- Validation failures → shows which plans failed and why

## Files Modified

1. `orchestrator_auto/cli.py` - Added queue mode handling
2. `test_plans/plan1.md` - Created test plan
3. `test_plans/plan2.md` - Created test plan
4. `test_plans/plan3.md` - Created test plan

## Summary

Milestone 3 is **COMPLETE** with all deliverables implemented:
- ✅ CLI accepts `--queue` mode
- ✅ Full input validation and error handling
- ✅ Queue creation with feature extraction
- ✅ Queue matching and resume logic
- ✅ UX output for queue status
- ✅ Backwards compatible with existing behavior
- ✅ Ready for Milestone 4 (Queue Runner implementation)
