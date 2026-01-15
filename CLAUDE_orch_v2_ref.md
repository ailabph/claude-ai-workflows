# Claude Orchestrator v2 - Quick Reference

Supplementary reference for `CLAUDE_orch_v2.md`.

---

## CLI Commands Cheatsheet

### Starting Workflows

```bash
# Basic start (interactive discovery)
orchestrator start -f "Feature description"

# Skip discovery, use existing plan
orchestrator start --plan docs/plan.md

# Cost-optimized (Sonnet planner, Haiku executor)
orchestrator start -f "Feature" -pm sonnet -em haiku

# With auto-commit
orchestrator start -f "Feature" --auto-commit --smart-commit

# With Telegram notifications
orchestrator start -f "Feature" --telegram

# Queue mode
orchestrator start --queue plan1.md plan2.md plan3.md

# Watch directory for plans
orchestrator watch ./plans/ --auto-commit
```

### Session Management

```bash
# List sessions (current project)
orchestrator list

# List all projects
orchestrator list --all-projects

# Filter by status
orchestrator list -s active
orchestrator list -s paused
orchestrator list -s completed
orchestrator list -s failed

# Check session details
orchestrator status <session-id>

# Resume paused session
orchestrator resume <session-id>

# Force resume orphaned session
orchestrator resume <session-id> --force

# Reset orphaned session
orchestrator reset <session-id>

# Force-complete stuck session
orchestrator complete <session-id>
orchestrator complete <session-id> --auto-commit
```

### Blocker Handling

```bash
# Respond to blocker
orchestrator respond <session-id> "Your answer"

# Resume after responding
orchestrator resume <session-id>
```

### Telegram

```bash
# Test configuration
orchestrator telegram test

# Verify two-way communication
orchestrator telegram ping

# Listen for blocker replies
orchestrator telegram listen
```

### Utilities

```bash
# Health check
orchestrator check
orchestrator check -v

# Convert plan to orchestrator format
orchestrator convert plan.md --validate-only
orchestrator convert plan.md -o converted.md
orchestrator convert plan.md --in-place

# Export session to markdown
orchestrator export <session-id> -o report.md

# Direct chat (no orchestration)
orchestrator chat
orchestrator chat -m opus --no-tools
```

---

## Workflow State Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ORCHESTRATOR STATE MACHINE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│    ┌──────────┐    /ready     ┌──────────┐    [PLAN_READY]   ┌──────────┐  │
│    │DISCOVERY │──────────────►│ PLANNING │──────────────────►│EXECUTION │  │
│    └────┬─────┘               └────┬─────┘                   └────┬─────┘  │
│         │                          │                               │        │
│         │ [HUMAN_INPUT_NEEDED]     │ [HUMAN_INPUT_NEEDED]         │        │
│         │                          │                               │        │
│         ▼                          ▼                               │        │
│    ┌──────────┐              ┌──────────┐                         │        │
│    │  PAUSED  │◄─────────────│  PAUSED  │◄────────────────────────┤        │
│    └────┬─────┘              └────┬─────┘   [BLOCKED]             │        │
│         │                          │                               │        │
│         │ respond                  │ respond                       │        │
│         │                          │                               ▼        │
│         ▼                          ▼                         ┌──────────┐  │
│    (back to                  (back to                        │  REVIEW  │  │
│     discovery)                planning)                      └────┬─────┘  │
│                                                                    │        │
│                                    ┌───────────────────────────────┤        │
│                                    │                               │        │
│                     [CHANGES_REQUESTED]              [MILESTONE_APPROVED]   │
│                                    │                               │        │
│                                    ▼                               ▼        │
│                              ┌──────────┐                   ┌──────────┐   │
│                              │EXECUTION │                   │ More MS? │   │
│                              │ (retry)  │                   └────┬─────┘   │
│                              └──────────┘                    yes/│\no      │
│                                                                  │  │      │
│                                                                  ▼  ▼      │
│                                                          (loop) ┌──────┐   │
│                                                                 │DONE  │   │
│                                                                 └──────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Response Tags Reference

### Planner Output Tags

```markdown
# Plan ready (transitions to execution)
[PLAN_READY]
Plan saved to: docs/feature/DOC_feature_plan.md

# Approve milestone (advance or complete)
[MILESTONE_APPROVED]
Milestone 2 approved. Proceed to Milestone 3.

# Request changes (send back to executor)
[CHANGES_REQUESTED]
- Fix the validation logic in UserSerializer
- Add test for edge case with empty input

# Need human input (pause workflow)
[HUMAN_INPUT_NEEDED]
Which database should we use?
1. PostgreSQL
2. MySQL
3. SQLite
```

### Executor Output Tags

```markdown
# Report milestone completion
[PROGRESS_REPORT]

## Milestone 1: Serializers - COMPLETED

### Files Created/Modified:
- app/serializers.py (modified)
- tests/test_serializers.py (created)

### Test Results:
12 tests passed, 0 failed
Coverage: 94%

### Ready for Review: YES

# Need clarification from planner
[CLARIFICATION_NEEDED]
The plan mentions "standard pagination" but the codebase uses both
cursor and offset pagination. Which should I use?

# Blocked by external dependency
[BLOCKED]
Cannot proceed: Waiting for database credentials
```

---

## Plan Document Templates

### Minimal Valid Plan

```markdown
# Feature Name - Implementation Plan

## Milestone 1: Setup
- Create project structure
- Add base configuration

## Milestone 2: Core Logic
- Implement main functionality
- Add error handling

## Milestone 3: Testing
- Write unit tests
- Integration tests
```

### Full API Plan

```markdown
# [Feature] API - Implementation Plan

## Overview
Brief description of the endpoint and its purpose.

## Endpoint Specification
| Property | Value |
|----------|-------|
| URL | `GET /api/v1/feature/` |
| Auth | JWT required |
| Permission | IsAuthenticated |

## Milestone 1: Serializers
### Tasks
- [ ] Create FeatureQuerySerializer
- [ ] Create FeatureResponseSerializer
- [ ] Add validation rules
- [ ] Write serializer tests

### Deliverables
- [ ] `app/serializers.py` - serializers added
- [ ] `tests/test_serializers.py` - tests created
- [ ] All tests passing

## Milestone 2: Service Layer
### Tasks
- [ ] Create FeatureService class
- [ ] Implement get_feature() method
- [ ] Add caching if needed
- [ ] Write service tests

### Deliverables
- [ ] `app/services/feature.py` - service created
- [ ] `tests/test_feature_service.py` - tests created
- [ ] 90%+ coverage

## Milestone 3: View and Routes
### Tasks
- [ ] Create FeatureView (APIView or ViewSet)
- [ ] Add URL pattern
- [ ] Configure permissions
- [ ] Write integration tests

### Deliverables
- [ ] `app/views.py` - view added
- [ ] `app/urls.py` - route added
- [ ] `tests/test_feature_view.py` - integration tests
- [ ] All tests passing

## Milestone 4: Validation
### Tasks
- [ ] Run full test suite
- [ ] Generate coverage report
- [ ] Update API documentation

### Deliverables
- [ ] `pytest` passing
- [ ] Coverage ≥ 85%
- [ ] OpenAPI schema updated
```

### Full Frontend Plan

```markdown
# [Feature] UI - Implementation Plan

## Overview
Brief description of the component/page and user story.

## UI Mockup
```
┌─────────────────────────────────────────────────────────────┐
│  Feature Title                                     [Action] │
├─────────────────────────────────────────────────────────────┤
│  [Filter ▼]  [Search...]                          [Reset]  │
├─────────────────────────────────────────────────────────────┤
│  Column 1   │ Column 2   │ Status      │ Actions           │
│─────────────┼────────────┼─────────────┼───────────────────│
│  Data       │ Data       │ ✓ Active    │ [View] [Edit]     │
├─────────────────────────────────────────────────────────────┤
│  ◀ Prev    Page 1 of 10    Next ▶                          │
└─────────────────────────────────────────────────────────────┘
```

## Milestone 1: Types and Structure
### Tasks
- [ ] Define TypeScript interfaces
- [ ] Create component directory structure
- [ ] Build skeleton components

### Deliverables
- [ ] `types/feature.ts` - interfaces defined
- [ ] `components/Feature/` - structure created
- [ ] Components rendering without errors

## Milestone 2: Data Layer
### Tasks
- [ ] Create API service methods
- [ ] Implement React Query hooks
- [ ] Handle loading/error states

### Deliverables
- [ ] `services/featureService.ts` - API methods
- [ ] `hooks/useFeature.ts` - React Query hook
- [ ] Loading spinners and error boundaries working

## Milestone 3: UI Implementation
### Tasks
- [ ] Build table/list component
- [ ] Implement filters and search
- [ ] Add pagination
- [ ] Style according to design system

### Deliverables
- [ ] FeatureTable component complete
- [ ] FeatureFilters component complete
- [ ] Matches design mockup
- [ ] Responsive layout

## Milestone 4: Testing and Polish
### Tasks
- [ ] Write component tests
- [ ] Test user interactions
- [ ] Verify accessibility
- [ ] Add loading states and animations

### Deliverables
- [ ] 80%+ test coverage
- [ ] All interactions tested
- [ ] No a11y violations
- [ ] Smooth UX
```

---

## Configuration Reference

### Config File Structure

```yaml
# ~/.claude_orchestrator/config.yaml

# Model selection
models:
  planner: opus      # opus | sonnet | haiku
  executor: sonnet   # opus | sonnet | haiku

# Auto-commit settings
auto_commit:
  smart: true        # AI-generated commit messages
  model: haiku       # Model for commit messages

# Telegram notifications
telegram:
  enabled: true
  bot_token: "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
  chat_id: "YOUR_CHAT_ID"
  stuck_sessions:
    enabled: true
    inactive_minutes: 20
```

### Environment Variables

```bash
# Authentication (choose one)
export ANTHROPIC_API_KEY="sk-ant-api03-..."
export CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat01-..."

# Telegram
export ORCHESTRATOR_TELEGRAM_BOT_TOKEN="..."
export ORCHESTRATOR_TELEGRAM_CHAT_ID="..."
export ORCHESTRATOR_TELEGRAM_ENABLED="true"

# Smart commit
export ORCHESTRATOR_SMART_COMMIT="true"
export ORCHESTRATOR_AUTO_COMMIT_MODEL="haiku"
```

### Priority Order

```
CLI flags
    ▼
Environment variables
    ▼
Repo config (<repo>/.claude_orchestrator/config.yaml)
    ▼
Global config (~/.claude_orchestrator/config.yaml)
    ▼
Defaults
```

---

## Milestone Patterns by Project Type

| Project Type | M1 | M2 | M3 | M4 |
|--------------|----|----|----|----|
| **API Endpoint** | Serializers + tests | Service + tests | View + routes | Validation |
| **Frontend Feature** | Types + structure | Data layer | UI implementation | Testing |
| **Bug Fix** | Failing test | Fix implementation | Regression tests | Cleanup |
| **Refactoring** | Identify scope | Extract/restructure | Update tests | Verify behavior |
| **Data Pipeline** | Schema + models | ETL logic | Orchestration | Monitoring |

---

## Task Recipes

These are copy-pasteable “starter prompts” designed to produce plans that work well with the `orchestrator` CLI (parseable milestones, clear deliverables, and gated review).

### Recipe: Planner Session Prompt (Plan-First Workflow)

**When:** You prefer to do discovery/planning in a separate chat session, then run `orchestrator start --plan <path>` for execution.

Copy/paste this as a single message into your planning session:

```text
Read @CLAUDE_orch_v2.md (and optionally @CLAUDE_orch_v2_ref.md). You are the PLANNER for a workflow that will be executed by the `orchestrator` CLI.

Context:
- Create the plan based on what we discussed earlier in this chat (use the conversation context above as the source of requirements/constraints/links).
- If any critical detail is missing, do NOT stop to ask questions mid-plan; instead capture it under `## Open Questions` with a recommended default.
- Goal: produce a single Markdown implementation plan that I will feed into `orchestrator start --plan <path>`. 

Hard requirements (must follow exactly):
1) The plan MUST be parseable by the `orchestrator` CLI:
   - Use milestone headers exactly like: `## Milestone 1: <Name>` (or `### Milestone 1: <Name>`).
   - Milestones must be sequential starting at 1.
2) Use 3–6 milestones. Each milestone must be independently executable and reviewable.
3) For EACH milestone include these subsections (use these headings):
   - `### Goal`
   - `### Tasks` (checklist format `- [ ]`)
   - `### Deliverables` (checklist format; include file paths when possible)
   - `### Validation` (exact commands to run, e.g. `pytest ...`, `npm test`, `make lint`, etc.)
   - `### Risks / Notes` (short; include likely pitfalls and rollback notes if relevant)
4) The plan must be specific to the existing codebase conventions:
   - Mention the exact directories/files/modules likely to change (best guess is fine).
   - Avoid vague tasks like “implement feature”; instead use concrete actions and outputs.
5) Include any required user decisions as explicit questions under an `## Open Questions` section.
   - If there are open questions, propose a default recommendation.
6) Do NOT implement anything. Do NOT run commands. Do NOT write code. Planning only.

Output instructions:
- First line: propose a plan file path I should save this as, e.g. `docs/plans/PLAN_<short_name>.md`.
- Then output the full plan Markdown content.
- After you finish outputting the plan Markdown, write exactly: `STOP` on its own line and stop responding.

Now, create the milestone-based plan.
```

### Recipe: Add a New API Endpoint

**When:** You need a new REST/JSON endpoint or to extend an existing one.

**Run:**

```bash
orchestrator start -f "Create a new API endpoint for <resource>. Requirements: <authz/authn>, request/response shape, error cases, performance constraints. Include tests and update docs."
```

**Recommended milestones:**
- M1: Request/response schema + validation + unit tests
- M2: Service/business logic + unit tests
- M3: Route/controller + integration tests
- M4: Validation (full test run) + docs update

**Planner guidance:** Ask for exact response codes, auth rules, pagination/filtering, and whether the endpoint is additive vs breaking.

### Recipe: Figma → Implement UI (New Page / Feature)

**When:** You have a Figma design and want production UI implementation.

**Run (discovery-driven):**

```bash
orchestrator start -f "Implement the <page/feature> UI from Figma. Source: <Figma URL>. Match layout, spacing, typography, states (loading/empty/error), and responsive behavior. Include accessibility and tests."
```

**If using MCP Figma tools:**
- Ensure `.mcp.json` includes `figma` and `orchestrator start` uses `--mcp-config` if not auto-discovered.

**Recommended milestones:**
- M1: Design tokens + component inventory (from Figma) + scaffolding
- M2: Core components + layout (desktop) + basic states
- M3: Responsive + a11y + empty/error/loading states
- M4: Tests + visual QA checklist + cleanup

### Recipe: Theme Refactor (Existing Site → New Theme from Figma)

**When:** You are updating an existing UI to match a new Figma theme (colors/typography/components) without rewriting the whole app.

**Run:**

```bash
orchestrator start -f "Refactor the existing UI to match the new Figma theme. Source: <Figma URL>. Keep behavior the same, change styling/components to match design tokens. Minimize churn; update tests as needed; verify key pages visually."
```

**Recommended milestones:**
- M1: Add/adjust design tokens (CSS vars/Tailwind/theme provider) + migration strategy
- M2: Refactor shared primitives (buttons/inputs/typography) + update snapshots/tests
- M3: Refactor key pages/flows + fix regressions
- M4: Visual QA pass + performance/a11y smoke checks

### Recipe: Add E2E Coverage via Playwright MCP

**When:** You want to validate MCP Playwright wiring or run a quick end-to-end interaction on a local site.

**Suggested workflow:**

```bash
# Terminal 1: run the committed fixture site
cd orchestrator-auto/fixtures/playwright-test-site
npm ci
npm run dev -- --port <PORT>

# Terminal 2: run the verification
orchestrator test-playwright both --test-url http://localhost:<PORT>/
```

**What “pass” means:** screenshots exist and are non-empty under `.orchestrator_artifacts/playwright-test/<timestamp>/`.

### Recipe: Large Refactor (Behavior-Preserving)

**When:** You need to reorganize code, rename modules, reduce duplication, or improve architecture without changing outward behavior.

**Run:**

```bash
orchestrator start -f "Refactor <area> to improve maintainability without changing behavior. Constraints: keep public APIs stable, keep tests green, minimize diff churn. Add missing tests if coverage is weak."
```

**Recommended milestones:**
- M1: Map current behavior + add characterization tests (if needed)
- M2: Perform refactor in small steps (core module extraction)
- M3: Update callers + remove dead code
- M4: Run full suite + cleanup + docs

### Recipe: Bug Fix (Known Repro)

**When:** You have a bug report with reproduction steps or a failing test.

**Run:**

```bash
orchestrator start -f "Fix bug: <description>. Repro: <steps or failing test>. Expected vs actual: <details>. Add regression test; ensure no new failures."
```

**Recommended milestones:**
- M1: Reproduce (or write failing test) + identify root cause
- M2: Implement fix + unit tests
- M3: Integration/regression coverage + validation

---

## Troubleshooting Quick Reference

| Symptom | Diagnosis | Solution |
|---------|-----------|----------|
| "Session not found" | Invalid or old session ID | `orchestrator list` to find valid IDs |
| "Database locked" | Multiple orchestrator processes | Close other instances |
| "Orphaned session" | Previous run crashed | `orchestrator reset <id>` then `resume --force` |
| Stuck at same milestone | Milestone count mismatch | `orchestrator complete <id>` |
| No response from agent | API timeout or auth issue | `orchestrator check` to diagnose |
| Blocker not clearing | Response not delivered | Check logs, try `respond` again |
| Queue not advancing | Previous item paused | `orchestrator status <id>`, resolve blocker |

### Debug Commands

```bash
# Full stack trace
orchestrator start -f "Feature" --debug

# Health check
orchestrator check -v

# View error logs
ls ~/.claude_orchestrator/logs/
cat ~/.claude_orchestrator/logs/error_<session_id>_*.log

# Session details
orchestrator status <session-id>

# Export full history
orchestrator export <session-id> -o debug.md
```

---

## ASCII UI Components (for Plans)

### Data Table

```
┌─────────────────────────────────────────────────────────────────┐
│  Title                                                 [Action] │
├─────────────────────────────────────────────────────────────────┤
│  [Filter ▼]  [Filter ▼]  [Search...]                   [Reset] │
├─────────────────────────────────────────────────────────────────┤
│  Column 1   │ Column 2 │ Column 3  │ Status    │ Actions       │
│─────────────┼──────────┼───────────┼───────────┼───────────────│
│  Data       │ Data     │ Data      │ ✓ Done    │ [View] [Edit] │
│  Data       │ Data     │ Data      │ ⏳ Pending │ [View] [Edit] │
├─────────────────────────────────────────────────────────────────┤
│  ◀ Prev    Page 1 of 10    Next ▶          Showing 1-20 of 156 │
└─────────────────────────────────────────────────────────────────┘
```

### Form

```
┌─────────────────────────────────────────────────────────────────┐
│  Create New Item                                            [X] │
├─────────────────────────────────────────────────────────────────┤
│  Name *                                                         │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Text input                                                │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Category *                      Amount *                       │
│  ┌─────────────────────┐        ┌─────────────────┐            │
│  │ Option 1        ▼   │        │ 0.00            │            │
│  └─────────────────────┘        └─────────────────┘            │
│                                                                 │
│                                    [Cancel]  [Save]             │
└─────────────────────────────────────────────────────────────────┘
```

### Stats Cards

```
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Total Users │ │    Revenue   │ │   Pending    │ │    Active    │
│    12,456    │ │    $1.2M     │ │      89      │ │    1,234     │
│   ▲ 12.5%    │ │   ▲ 8.3%     │ │   ▼ 5.2%     │ │   ▲ 15.1%    │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

### Status Indicators

```
Badges:    ✓ Success   ⏳ Pending   ✗ Failed   ○ Draft   ● Active

Progress:  [████████░░░░░░░░░░░░] 40%

Loading:   ◐ Loading...   ⟳ Refreshing...

Alerts:
┌─ ⚠ Warning ──────────────────────────────────────────────────┐
│  This action cannot be undone.                                │
└───────────────────────────────────────────────────────────────┘
```

---

## Related Files

| File | Purpose |
|------|---------|
| `CLAUDE_orch_v2.md` | Full v2 framework documentation |
| `orchestrator-auto/README.md` | Complete CLI documentation |
| `CLAUDE_orchestrator.md` | Manual workflow (v1) |
| `CLAUDE_orchestrator_ref.md` | Manual workflow reference |
