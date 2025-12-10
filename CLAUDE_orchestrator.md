# Claude Orchestrator: Milestone-Based Task Execution Framework (v2)

## Overview

A **gated milestone workflow** for AI agents executing complex multi-step tasks. Ensures human oversight at critical checkpoints for review, validation, and course correction.

---

## Core Principles

| Principle | Description |
|-----------|-------------|
| **Milestone-Based** | Tasks divided into 3-5 discrete milestones with clear deliverables |
| **Gated Approval** | No milestone proceeds without explicit human approval |
| **Structured Reports** | Standardized format: files changed, test results, issues |

---

## Quick Start

### Step 1: Create Implementation Plan
```
docs/{feature}/DOC_{feature_name}_plan.md
```
Include: endpoint spec, file organization, code patterns, testing requirements, security considerations.

### Step 2: Define Milestones (3-5)

| Project Type | Milestone Pattern |
|--------------|-------------------|
| **API Endpoints** | Schemas → Service Logic → Controller + Routes → Validation |
| **New Features** | Models → Services → API/UI → Tests + Integration |
| **Bug Fixes** | Failing Test → Fix → Verify + Regression |
| **Frontend** | Components + Types → Logic → Styling → Tests + Storybook |
| **Data Pipeline** | Schema → ETL Logic → Orchestration → Monitoring + Tests |
| **Infrastructure** | Config → Resources → Network + Security → Validation |

### Step 3: Execute + Review Loop
1. Give prompt to Claude → 2. Agent executes milestone, stops, reports → 3. Review and approve/reject → 4. Repeat

---

## Two-Agent Workflow

This framework is designed for a **two-agent architecture** to optimize context usage and model costs.

### Architecture

```
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│  PLANNER/REVIEWER                   │     │  EXECUTOR                           │
│  (Opus - expensive, strategic)      │     │  (Sonnet/Haiku - cost-effective)    │
├─────────────────────────────────────┤     ├─────────────────────────────────────┤
│  • Reviews framework docs           │     │  • Receives orchestrator prompt     │
│  • Researches project codebase      │     │  • Executes ONE milestone only      │
│  • Creates implementation plan      │     │  • Generates progress report        │
│  • Writes orchestrator prompt       │────▶│  • STOPS and waits for approval     │
│  • Validates milestone reports      │◀────│                                     │
│  • Approves/rejects milestones      │     │  (fresh context each milestone)     │
│  • Stays grounded (minimal context) │     │                                     │
└─────────────────────────────────────┘     └─────────────────────────────────────┘
```

### Benefits

| Benefit | Description |
|---------|-------------|
| **Context efficiency** | Planner stays lean, doesn't accumulate execution details |
| **Model optimization** | Expensive model for planning, cheaper for execution |
| **Fresh executor** | Each milestone starts clean, no accumulated confusion |
| **Grounded reviewer** | Planner validates objectively without being "in the weeds" |

### Planner/Reviewer Responsibilities

1. **Research phase**
   - Review framework documentation
   - Explore project codebase
   - Identify patterns and existing conventions
   - Ask clarifying questions

2. **Planning phase**
   - Create implementation plan (`DOC_{feature}_plan.md`)
   - Define milestones with clear deliverables
   - Write orchestrator prompt for executor

3. **Review phase**
   - Validate executor's progress report
   - Check files created/modified match expectations
   - Verify tests pass and coverage meets targets
   - Approve, request changes, or abort

### Executor Responsibilities

1. Receive orchestrator prompt with plan reference
2. Execute **ONE milestone only**
3. Generate progress report in specified format
4. **STOP** and wait for approval
5. Never proceed to next milestone without explicit approval

### Handoff Format (Planner → Executor)

The planner creates this prompt to send to a fresh executor session:

```markdown
## Agent Task: [Feature Name]

### Plan Document
Read and follow: `docs/[path]/DOC_[feature]_plan.md`

### Workflow Instructions
This task has **[N] milestones**. After completing each:
1. **STOP** and generate a progress report
2. **WAIT** for approval before proceeding
3. **DO NOT** continue without explicit approval

### Current Milestone: [N]
[Copy milestone details from plan]

### Progress Report Format
```
## Milestone [N]: [Name] - COMPLETED

### Files Created/Modified:
- path/to/file (created|modified)

### Test Results:
[paste output]

### Notes/Issues:
[blockers, deviations, questions]

### Ready for Review: YES
```

**Begin Milestone [N]. Stop and report when complete.**
```

### Report Validation Checklist (Reviewer)

When executor submits a progress report, planner validates:

| Check | Question |
|-------|----------|
| **Completeness** | All deliverables in milestone checklist addressed? |
| **Files** | Expected files created/modified in correct locations? |
| **Patterns** | Code follows existing project conventions? |
| **Tests** | Tests written and passing? |
| **Coverage** | Coverage meets target (if specified)? |
| **Issues** | Any blockers or deviations that need discussion? |

### Milestone Continuation Prompt

After approving a milestone, planner sends to **same or new** executor:

```
Milestone [N] approved.

Continue with Milestone [N+1]:
[Copy next milestone details from plan]

Stop and report when complete.
```

### Session Management

| Scenario | Recommendation |
|----------|----------------|
| Small milestones | Same executor session, continue with approval |
| Large milestones | New executor session to reset context |
| Context getting long | Start fresh executor session |
| Executor confused | Start fresh executor session with clearer prompt |

---

## Plan Document Templates

### Backend API Plan Template

```markdown
# [Feature Name] API - Implementation Plan

## 1. Overview
[What endpoint(s) and why - 2-3 sentences]

## 2. Endpoint Specification

### 2.1 Endpoint Details
| Property | Value |
|----------|-------|
| **URL** | `[METHOD] /api/v1/[path]/` |
| **View** | `[app].views.[ViewName]` |
| **Permission** | `[PermissionClass]` |
| **Service** | `[app].services.[method]` |

### 2.2 Path Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | UUID | Yes | Resource ID |

### 2.3 Query Parameters
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `page` | int | No | 1 | Page number |
| `page_size` | int | No | 20 | Items per page |

### 2.4 Request Body (if POST/PUT/PATCH)
```json
{
  "field": "type"
}
```

### 2.5 Response Schema
```json
{
  "count": 0,
  "results": []
}
```

### 2.6 Error Responses
| Status | Condition | Response |
|--------|-----------|----------|
| 400 | Invalid params | `{"field": ["error"]}` |
| 401 | Not authenticated | `{"detail": "..."}` |
| 403 | Not authorized | `{"detail": "..."}` |
| 404 | Not found | `{"detail": "..."}` |

## 3. Architecture

### 3.1 File Structure
```
[app]/
├── views.py           # Add [ViewName]
├── serializers.py     # Add query/response serializers
├── urls.py            # Add URL pattern
├── services/
│   └── [service].py   # Add [method]
└── tests/
    ├── test_[feature]_view.py
    └── test_[feature]_service.py
```

### 3.2 Patterns to Follow
- View: `[app]/views.py::[ExistingView]`
- Service: `[app]/services/[file].py::[method]`
- Serializer: `[app]/serializers.py::[Serializer]`

## 4. Implementation Details

### 4.1 Query Serializer
```python
class [Feature]QuerySerializer(serializers.Serializer):
    # fields...
```

### 4.2 Service Method
```python
@staticmethod
def [method_name](params) -> dict:
    """Docstring"""
    pass
```

## 5. Testing Strategy

### 5.1 Unit Tests (Service)
- test_[scenario_1]
- test_[scenario_2]
- test_edge_case

### 5.2 Integration Tests (View)
- test_unauthenticated_returns_401
- test_unauthorized_returns_403
- test_valid_request_returns_200

### 5.3 Coverage Targets
| Component | Target |
|-----------|--------|
| Serializers | 95% |
| Service | 90% |
| View | 85% |

## 6. Security
- [ ] Auth: JWT required
- [ ] Authorization: [Permission class]
- [ ] Input validation: All params via serializer
- [ ] Data protection: [considerations]

## 7. Anti-Patterns
### Don't: [Bad pattern]
```python
# BAD
```
### Do: [Good pattern]
```python
# GOOD
```
```

---

### Frontend Feature Plan Template

```markdown
# [Feature Name] - Implementation Plan

## 1. Overview
[What component/page and why - 2-3 sentences]

## 2. Feature Specification

### 2.1 Component Details
| Property | Value |
|----------|-------|
| **Component** | `[ComponentName]` |
| **Route** | `/path/to/page` |
| **State** | React Query + URL params |
| **API** | `[METHOD] /api/v1/[endpoint]/` |

### 2.2 User Stories
- As a [user], I can [action] so that [benefit]
- As a [user], I can [action] so that [benefit]

### 2.3 UI Mockup
```
┌─────────────────────────────────────────────────────────────────┐
│  Page Title                                            [Action] │
├─────────────────────────────────────────────────────────────────┤
│  [Filter ▼]  [Filter ▼]  [Date Range]              [Reset]     │
├─────────────────────────────────────────────────────────────────┤
│  Column 1   │ Column 2 │ Status    │ Actions                   │
│─────────────┼──────────┼───────────┼───────────────────────────│
│  Data       │ Data     │ ✓ Done    │ [View]                    │
├─────────────────────────────────────────────────────────────────┤
│  ◀ Prev    Page 1 of 10    Next ▶                              │
└─────────────────────────────────────────────────────────────────┘
```

## 3. Architecture

### 3.1 File Structure
```
src/components/[feature]/
├── [Feature]Content.tsx        # Main container
├── [Feature]DataTable.tsx      # Table component
├── [Feature]Filters.tsx        # Filter controls
├── [Feature]DetailDrawer.tsx   # Detail view
├── columns.tsx                 # Table columns
├── index.ts                    # Exports
└── __tests__/
    └── [Feature].test.tsx
```

### 3.2 Patterns to Follow
- Component: `src/components/[existing]/`
- Hook: `src/hooks/use[Existing].ts`
- Service: `src/services/[existing]Service.ts`

## 4. Implementation Details

### 4.1 Types
```typescript
export interface [Feature] {
  id: string;
  // fields...
}

export interface [Feature]Filters {
  // filter fields...
}
```

### 4.2 Service Method
```typescript
async get[Feature](params: Params): Promise<Response> {
  // implementation
}
```

### 4.3 Hook
```typescript
export const [FEATURE]_QUERY_KEY = '[feature]';

export function use[Feature](params: Params) {
  return useQuery({
    queryKey: [[FEATURE]_QUERY_KEY, params],
    queryFn: () => service.get[Feature](params),
  });
}
```

### 4.4 Main Component Structure
```tsx
export function [Feature]Content() {
  const { data, isLoading } = use[Feature](params);

  return (
    // JSX structure
  );
}
```

## 5. Testing Strategy

### 5.1 Unit Tests
- renders loading state
- renders data correctly
- handles empty state
- filter changes update query

### 5.2 Integration Tests
- fetches data on mount
- pagination works
- filters apply correctly

### 5.3 Coverage Targets
| Component | Target |
|-----------|--------|
| Hooks | 90% |
| Components | 80% |

## 6. Accessibility
- [ ] Keyboard navigation
- [ ] ARIA labels on table
- [ ] Screen reader announcements
- [ ] Focus management in modals

## 7. Anti-Patterns
### Don't: [Bad pattern]
```tsx
// BAD
```
### Do: [Good pattern]
```tsx
// GOOD
```
```

---

## Orchestrator Prompt Template

```markdown
## Agent Task: [Task Title]

### Objective
[One-sentence description]

### Context
[2-3 sentences: why needed, what it connects to]

### Workflow Instructions
This task has **[N] milestones**. After each:
1. **STOP** and generate a progress report
2. **WAIT** for approval
3. **DO NOT** proceed until explicitly approved

---

## Milestone [N]: [Name]

### Prerequisites
- [Previous milestone approved, if applicable]

### Tasks
1. [Task]
2. [Task]

### Key References
- [File/pattern to follow]

### Deliverables
- [ ] [Deliverable]
- [ ] Tests passing

**⛔ STOP - Generate progress report, wait for approval**

---

[Repeat milestone block for each milestone]

---

## Quick Reference

| Resource | Path |
|----------|------|
| Implementation Plan | `docs/path/to/plan.md` |
| Pattern to Follow | `path/to/example.py` |
```

---

## Progress Report Template

Use this format after completing each milestone:

```
## Milestone [N]: [Name] - COMPLETED

### Files Created/Modified:
- path/to/file (created|modified)

### Test Results:
[paste output]

### Notes/Issues:
[blockers, deviations, questions]

### Ready for Review: YES
```

For final milestone, add:
```
### Coverage Report:
[paste summary]

### TASK COMPLETE - Ready for Final Review
```

---

## Review Commands

| Action | Command |
|--------|---------|
| **Approve** | `Milestone [N] approved. Proceed to Milestone [N+1].` |
| **Changes needed** | `Milestone [N] needs changes: [issues]. Fix and regenerate report.` |
| **Approve with notes** | `Milestone [N] approved with notes: [observations]. Proceed.` |
| **Abort** | `ABORT: [Reason]. Do not proceed.` |

---

## Kickstart Options

### Option A: Reference Directly
```
Read CLAUDE_orchestrator_planner_executor_v2.md and implement [FEATURE]
using milestone workflow. Plan at docs/[path]/DOC_[feature]_plan.md.
Execute Milestone 1 only, then stop and report.
```

### Option B: Minimal Context
```
Implement using milestone-based workflow with approval gates.

RULES:
1. Execute ONE milestone at a time
2. STOP and generate progress report after each
3. WAIT for approval before proceeding

PLAN: [path or content]

MILESTONES:
1. [name + tasks]
2. [name + tasks]
3. [name + tasks]
4. Final validation

Begin Milestone 1. Stop and report when complete.
```

---

## Example: API Endpoint (Condensed)

```markdown
## Agent Task: User Activity Log Endpoint

### Objective
Create `GET /api/v1/admin/users/{user_id}/activity-log/`

### Context
Admins need to audit user actions. Follows existing admin module patterns.

### Milestones (4)

**M1: Serializers** → QuerySerializer, ItemSerializer, ResponseSerializer + tests
**M2: Service** → `get_user_activity_log()` in AdminService + pagination + tests
**M3: View + URL** → UserActivityLogView + Swagger + route + integration tests
**M4: Validation** → Full test suite, 85%+ coverage, docs updated
```

---

## Best Practices

| DO | DON'T |
|----|-------|
| Keep milestones small (2-4 hours) | Create external dependencies |
| Include tests in every milestone | Skip planning phase |
| Provide clear file paths/patterns | Allow multiple milestones without review |
| Specify exact report format | Mix unrelated tasks in one milestone |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-12 | Initial framework |
| 2.0 | 2025-12 | Optimized: consolidated templates, table formats, condensed example |
| 2.1 | 2025-12 | Added two-agent workflow, plan templates (backend/frontend), handoff formats |