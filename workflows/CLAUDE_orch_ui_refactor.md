# Claude Orchestrator: UI Page Refactoring Workflow

## Overview

A **queue-based workflow** for refactoring multiple UI pages systematically. Each page is an independent plan, processed sequentially with fresh context, auto-commit per page, and fail-forward resilience.

**Best For:**
- Design system migrations
- Component library upgrades
- Styling framework changes (CSS → Tailwind, etc.)
- Accessibility remediation
- Performance optimization across pages

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        UI REFACTORING QUEUE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   refactor-plans/                      orchestrator-auto                     │
│   ├── 01-dashboard.md    ───┐                                               │
│   ├── 02-settings.md        │         ┌─────────────────┐                   │
│   ├── 03-profile.md         ├────────►│  Queue Engine   │                   │
│   ├── 04-checkout.md        │         └────────┬────────┘                   │
│   └── ...                ───┘                  │                             │
│                                                ▼                             │
│                                    ┌───────────────────────┐                │
│                                    │ Process One at a Time │                │
│                                    └───────────┬───────────┘                │
│                                                │                             │
│          ┌─────────────────────────────────────┼─────────────────────┐      │
│          ▼                                     ▼                     ▼      │
│   ┌─────────────┐                      ┌─────────────┐       ┌──────────┐  │
│   │  Planner    │◄────────────────────►│  Executor   │──────►│ git      │  │
│   │  (review)   │                      │  (refactor) │       │ commit   │  │
│   └─────────────┘                      └─────────────┘       └──────────┘  │
│                                                                              │
│   On completion: 01-dashboard.md → 01-dashboard_done.md                     │
│   On failure:    02-settings.md  → 02-settings_failed.md                    │
│   Queue continues to next...                                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Create Plans Directory

```bash
mkdir refactor-plans
```

### 2. Generate Plan Files

Create one plan per page (see templates below):

```
refactor-plans/
├── 01-dashboard.md
├── 02-settings.md
├── 03-profile.md
├── 04-users-list.md
├── 05-user-detail.md
├── 06-products.md
├── 07-orders.md
├── 08-checkout.md
├── 09-payment.md
├── 10-confirmation.md
└── ... (as many as needed)
```

### 3. Run Queue

```bash
# Start queue with auto-commit
orchestrator start --queue refactor-plans/*.md --auto-commit

# With Telegram notifications (for long-running queues)
orchestrator start --queue refactor-plans/*.md --auto-commit --telegram

# Cost-optimized models
orchestrator start --queue refactor-plans/*.md --auto-commit -pm sonnet -em haiku
```

### 4. Monitor Progress

```bash
# Check queue status
orchestrator list

# Output shows queue position:
# a1b2c3d4  Dashboard Page     COMPLETED  Queue: #1 [DONE]
# b2c3d4e5  Settings Page      EXECUTION  Queue: #2 [RUNNING]
# c3d4e5f6  Profile Page       PENDING    Queue: #3 [PENDING]
```

### 5. Handle Blockers

If a page hits a blocker:

```bash
# Check what's blocking
orchestrator status <session-id>

# Respond and continue
orchestrator respond <session-id> "Skip the legacy DatePicker, use native input"
orchestrator resume <session-id>
```

---

## Plan Templates

### Standard Page Refactor (2 Milestones)

```markdown
# Refactor: [Page Name] Page

## Overview
Refactor [Page Name] page to [design system / new patterns].

## Current State
- Location: `src/pages/[PageName]/` or `src/components/[PageName]/`
- Key components: [list main components]
- Known issues: [any specific problems to address]

## Target State
- Use [DesignSystem] components
- Follow [pattern] for state management
- Meet accessibility standards (WCAG 2.1 AA)

## Milestone 1: Component Migration
### Tasks
- [ ] Replace legacy components with design system equivalents
- [ ] Update imports and dependencies
- [ ] Fix TypeScript errors
- [ ] Maintain existing functionality

### Component Mapping
| Legacy | New |
|--------|-----|
| `<LegacyButton>` | `<Button>` |
| `<LegacyInput>` | `<TextField>` |
| `<LegacyModal>` | `<Dialog>` |

### Deliverables
- [ ] All components migrated
- [ ] No TypeScript errors
- [ ] Page renders correctly

## Milestone 2: Testing & Polish
### Tasks
- [ ] Update existing tests for new components
- [ ] Add missing test coverage
- [ ] Verify responsive behavior
- [ ] Check accessibility (keyboard nav, ARIA)

### Deliverables
- [ ] All tests passing
- [ ] No console errors/warnings
- [ ] Responsive at all breakpoints
- [ ] No accessibility violations
```

### Complex Page Refactor (3 Milestones)

```markdown
# Refactor: [Page Name] Page

## Overview
Refactor [Page Name] page - complex page with multiple sections.

## Current State
- Location: `src/pages/[PageName]/`
- Sections: [Header, Filters, DataTable, DetailPanel, etc.]
- State: [Redux/Context/local state]
- API calls: [list endpoints used]

## Target State
- Design system components throughout
- React Query for data fetching
- URL-synced filters
- Improved performance

## Milestone 1: Structure & Data Layer
### Tasks
- [ ] Refactor component structure
- [ ] Migrate to React Query hooks
- [ ] Update TypeScript interfaces
- [ ] Remove legacy state management

### Deliverables
- [ ] Clean component hierarchy
- [ ] Data fetching via React Query
- [ ] Types updated
- [ ] No legacy state patterns

## Milestone 2: UI Components
### Tasks
- [ ] Replace all legacy components
- [ ] Implement new filter components
- [ ] Update table/list components
- [ ] Add loading/error states

### Component Mapping
| Section | Legacy | New |
|---------|--------|-----|
| Header | `<PageHeader>` | `<Header>` |
| Filters | `<LegacyFilters>` | `<FilterBar>` |
| Table | `<DataTable>` | `<Table>` |
| Detail | `<SidePanel>` | `<Drawer>` |

### Deliverables
- [ ] All UI components migrated
- [ ] Consistent styling
- [ ] Loading states implemented
- [ ] Error boundaries in place

## Milestone 3: Testing & Optimization
### Tasks
- [ ] Write/update component tests
- [ ] Add integration tests
- [ ] Performance optimization (memoization, virtualization)
- [ ] Accessibility audit

### Deliverables
- [ ] 80%+ test coverage
- [ ] No performance regressions
- [ ] Lighthouse accessibility score ≥ 90
- [ ] All interactions keyboard-accessible
```

### Minimal Page Refactor (1 Milestone)

For simple pages with minimal changes:

```markdown
# Refactor: [Page Name] Page

## Overview
Simple refactor of [Page Name] page - replace legacy components.

## Milestone 1: Migration & Testing
### Tasks
- [ ] Replace `<LegacyX>` with `<NewX>` components
- [ ] Update imports
- [ ] Fix any TypeScript errors
- [ ] Update tests
- [ ] Visual verification

### Deliverables
- [ ] Components migrated
- [ ] Tests passing
- [ ] No console errors
```

---

## Naming Conventions

### Plan Files

Use numbered prefixes for ordering:

```
refactor-plans/
├── 01-dashboard.md       # Processed first
├── 02-settings.md        # Processed second
├── 03-profile.md
...
```

Or group by feature area:

```
refactor-plans/
├── admin-01-users.md
├── admin-02-roles.md
├── admin-03-settings.md
├── shop-01-products.md
├── shop-02-cart.md
├── shop-03-checkout.md
...
```

### Completed Files

Queue automatically renames on completion:

| Original | Outcome | Renamed To |
|----------|---------|------------|
| `01-dashboard.md` | Success | `01-dashboard_done.md` |
| `02-settings.md` | Failed | `02-settings_failed.md` |
| `03-profile.md` | Paused | `03-profile_paused.md` |

---

## Workflow Patterns

### Pattern 1: Full Queue Upfront

Create all plans first, then run:

```bash
# Create all plans
for page in dashboard settings profile checkout; do
  cp template.md "refactor-plans/${page}.md"
  # Edit each plan with page-specific details
done

# Run entire queue
orchestrator start --queue refactor-plans/*.md --auto-commit
```

### Pattern 2: Watch Mode (Continuous)

Add plans as you go:

```bash
# Terminal 1: Start watcher
orchestrator watch ./refactor-plans/ --auto-commit

# Terminal 2: Add plans when ready
cp template.md refactor-plans/new-page.md
# Watcher picks it up automatically
```

### Pattern 3: Batched Execution

Run in batches (e.g., by feature area):

```bash
# Day 1: Admin pages
orchestrator start --queue refactor-plans/admin-*.md --auto-commit

# Day 2: Shop pages
orchestrator start --queue refactor-plans/shop-*.md --auto-commit

# Day 3: User pages
orchestrator start --queue refactor-plans/user-*.md --auto-commit
```

### Pattern 4: Priority-Based

Handle critical pages first:

```bash
# High priority (blocking release)
orchestrator start --queue \
  refactor-plans/01-checkout.md \
  refactor-plans/02-payment.md \
  --auto-commit

# Then remaining pages
orchestrator start --queue refactor-plans/*.md --auto-commit
```

---

## Handling Common Scenarios

### Shared Components

If multiple pages use the same legacy component:

**Option A: Refactor shared component first**
```
refactor-plans/
├── 00-shared-datatable.md    # Refactor shared component first
├── 01-dashboard.md            # Then pages that use it
├── 02-orders.md
...
```

**Option B: Include in first page, reference in others**
```markdown
# In 01-dashboard.md
## Milestone 1: Shared Components
- [ ] Create new `<DataTable>` component
- [ ] Export from shared components

# In 02-orders.md
## Overview
Uses shared `<DataTable>` from dashboard refactor.
```

### Pages with Shared State

If pages share Redux/Context state:

```markdown
# In plan
## Notes
This page shares state with [OtherPage].
Changes to state shape must be backward-compatible until OtherPage is refactored.
```

### Dependent Pages

If Page B depends on Page A's components:

```
refactor-plans/
├── 01-page-a.md              # Must complete first
├── 02-page-b-depends-a.md    # Uses components from A
```

Queue processes in order, so B won't start until A completes.

---

## Git Strategy

### Commit Per Page (Recommended)

```bash
orchestrator start --queue refactor-plans/*.md --auto-commit --smart-commit
```

Produces commits like:
```
refactor(dashboard): migrate to design system components
refactor(settings): migrate to design system components
refactor(profile): migrate to design system components
```

### Squash Before PR

If you want a single commit for the PR:

```bash
# After queue completes
git rebase -i HEAD~20  # Squash all refactor commits
```

### Branch Strategy

```bash
# Create feature branch
git checkout -b refactor/design-system-migration

# Run queue
orchestrator start --queue refactor-plans/*.md --auto-commit

# Push and create PR
git push -u origin refactor/design-system-migration
```

---

## Telegram Integration

For long-running queues, enable Telegram notifications:

```bash
orchestrator start --queue refactor-plans/*.md --auto-commit --telegram
```

**Notifications you'll receive:**
- Queue started (X items)
- Each page completed
- Blockers (with reply capability)
- Queue completed summary
- Failures

**Reply to blockers directly from Telegram:**
```bash
# In another terminal, start listener
orchestrator telegram listen
```

---

## Recovery Scenarios

### Queue Interrupted (Crash/Restart)

```bash
# Resume existing queue
orchestrator start --queue
```

Queue continues from next pending item.

### Page Failed

Queue continues automatically. Review failed pages later:

```bash
# List failed sessions
orchestrator list -s failed

# Check what went wrong
orchestrator status <session-id>
orchestrator export <session-id> -o failed-page-report.md

# Fix manually or re-queue
mv refactor-plans/05-orders_failed.md refactor-plans/05-orders.md
orchestrator start --queue refactor-plans/05-orders.md --auto-commit
```

### Page Paused on Blocker

```bash
# Check blocker
orchestrator status <session-id>

# Respond
orchestrator respond <session-id> "Use the new DatePicker from @/components/ui"

# Resume (queue continues automatically after)
orchestrator resume <session-id>
```

---

## Best Practices

### Plan Creation

| DO | DON'T |
|----|-------|
| Include component mapping table | Leave mappings ambiguous |
| Specify file locations | Assume executor knows paths |
| Note shared state dependencies | Ignore cross-page impacts |
| Keep milestones focused (1-2) | Create 5+ milestones per page |

### Queue Management

| DO | DON'T |
|----|-------|
| Number files for ordering | Rely on alphabetical sorting |
| Use `--auto-commit` for clean history | Accumulate uncommitted changes |
| Enable `--telegram` for long queues | Check manually every hour |
| Review `_failed.md` files | Ignore failures |

### Testing

| DO | DON'T |
|----|-------|
| Include test updates in each plan | Leave testing to "later" |
| Verify visual rendering | Only check TypeScript compiles |
| Test responsive behavior | Only test desktop |
| Run accessibility checks | Skip a11y |

---

## Metrics & Tracking

### Progress Tracking

```bash
# Count completed
ls refactor-plans/*_done.md | wc -l

# Count remaining
ls refactor-plans/*.md | grep -v '_done\|_failed\|_paused' | wc -l

# Quick summary
echo "Done: $(ls refactor-plans/*_done.md 2>/dev/null | wc -l)"
echo "Failed: $(ls refactor-plans/*_failed.md 2>/dev/null | wc -l)"
echo "Remaining: $(ls refactor-plans/*.md 2>/dev/null | grep -v '_done\|_failed\|_paused' | wc -l)"
```

### Time Estimation

Rough estimates per page complexity:

| Complexity | Milestones | Estimated Time |
|------------|------------|----------------|
| Simple | 1 | 10-15 min |
| Standard | 2 | 20-30 min |
| Complex | 3 | 40-60 min |

For 20 standard pages: ~8-10 hours total queue time.

---

## Related

- [CLAUDE_orch_ui_refactor_ref.md](CLAUDE_orch_ui_refactor_ref.md) - Quick reference
- [CLAUDE_orch_v2.md](CLAUDE_orch_v2.md) - Full orchestrator v2 documentation
- [orchestrator-auto README](orchestrator-auto/README.md) - CLI documentation
