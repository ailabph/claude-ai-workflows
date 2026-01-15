# UI Page Refactoring - Quick Reference

Quick reference for `CLAUDE_orch_ui_refactor.md`.

---

## Commands Cheatsheet

```bash
# Start queue
orchestrator start --queue refactor-plans/*.md --auto-commit

# With Telegram
orchestrator start --queue refactor-plans/*.md --auto-commit --telegram

# Cost-optimized
orchestrator start --queue refactor-plans/*.md --auto-commit -pm sonnet -em haiku

# Resume interrupted queue
orchestrator start --queue

# Watch mode (continuous)
orchestrator watch ./refactor-plans/ --auto-commit

# Check progress
orchestrator list

# Handle blocker
orchestrator status <session-id>
orchestrator respond <session-id> "answer"
orchestrator resume <session-id>

# Re-queue failed page
mv refactor-plans/page_failed.md refactor-plans/page.md
orchestrator start --queue refactor-plans/page.md --auto-commit
```

---

## Plan Templates

### Copy-Paste: Standard (2 Milestones)

```markdown
# Refactor: [PAGE_NAME] Page

## Overview
Refactor [PAGE_NAME] page to [DESIGN_SYSTEM] design system.

## Current State
- Location: `src/pages/[PAGE_NAME]/`
- Components: [LIST_COMPONENTS]

## Target State
- [DESIGN_SYSTEM] components
- TypeScript strict mode
- WCAG 2.1 AA accessible

## Milestone 1: Component Migration
### Tasks
- [ ] Replace legacy components with design system equivalents
- [ ] Update imports
- [ ] Fix TypeScript errors
- [ ] Maintain functionality

### Component Mapping
| Legacy | New |
|--------|-----|
| `<OldButton>` | `<Button>` |
| `<OldInput>` | `<TextField>` |
| `<OldSelect>` | `<Select>` |
| `<OldModal>` | `<Dialog>` |
| `<OldTable>` | `<DataTable>` |

### Deliverables
- [ ] All components migrated
- [ ] No TypeScript errors
- [ ] Page renders correctly

## Milestone 2: Testing & Polish
### Tasks
- [ ] Update component tests
- [ ] Verify responsive behavior
- [ ] Check keyboard navigation
- [ ] Verify screen reader compatibility

### Deliverables
- [ ] Tests passing
- [ ] No console errors
- [ ] Responsive at all breakpoints
```

### Copy-Paste: Simple (1 Milestone)

```markdown
# Refactor: [PAGE_NAME] Page

## Overview
Simple refactor of [PAGE_NAME] - replace legacy components.

## Milestone 1: Migration
### Tasks
- [ ] Replace legacy components
- [ ] Update imports
- [ ] Fix TypeScript errors
- [ ] Update tests
- [ ] Visual verification

### Deliverables
- [ ] Components migrated
- [ ] Tests passing
- [ ] No console errors
```

### Copy-Paste: Complex (3 Milestones)

```markdown
# Refactor: [PAGE_NAME] Page

## Overview
Complex refactor of [PAGE_NAME] with data layer changes.

## Current State
- Location: `src/pages/[PAGE_NAME]/`
- State: Redux / Context
- API: [LIST_ENDPOINTS]

## Milestone 1: Data Layer
### Tasks
- [ ] Migrate to React Query
- [ ] Update TypeScript interfaces
- [ ] Remove legacy state

### Deliverables
- [ ] React Query hooks created
- [ ] Types updated
- [ ] No legacy state

## Milestone 2: UI Components
### Tasks
- [ ] Replace all legacy components
- [ ] Implement loading/error states
- [ ] Update styling

### Deliverables
- [ ] All components migrated
- [ ] Loading states working
- [ ] Consistent styling

## Milestone 3: Testing
### Tasks
- [ ] Component tests
- [ ] Integration tests
- [ ] Accessibility audit

### Deliverables
- [ ] 80%+ coverage
- [ ] Accessibility score ≥ 90
```

---

## Component Mapping Tables

### General UI

| Legacy | Shadcn/ui | MUI | Chakra |
|--------|-----------|-----|--------|
| `<LegacyButton>` | `<Button>` | `<Button>` | `<Button>` |
| `<LegacyInput>` | `<Input>` | `<TextField>` | `<Input>` |
| `<LegacySelect>` | `<Select>` | `<Select>` | `<Select>` |
| `<LegacyCheckbox>` | `<Checkbox>` | `<Checkbox>` | `<Checkbox>` |
| `<LegacyRadio>` | `<RadioGroup>` | `<RadioGroup>` | `<RadioGroup>` |
| `<LegacySwitch>` | `<Switch>` | `<Switch>` | `<Switch>` |

### Layout

| Legacy | Shadcn/ui | MUI | Chakra |
|--------|-----------|-----|--------|
| `<LegacyModal>` | `<Dialog>` | `<Modal>` | `<Modal>` |
| `<LegacyDrawer>` | `<Sheet>` | `<Drawer>` | `<Drawer>` |
| `<LegacyTabs>` | `<Tabs>` | `<Tabs>` | `<Tabs>` |
| `<LegacyCard>` | `<Card>` | `<Card>` | `<Box>` |
| `<LegacyAccordion>` | `<Accordion>` | `<Accordion>` | `<Accordion>` |

### Data Display

| Legacy | Shadcn/ui | MUI | Chakra |
|--------|-----------|-----|--------|
| `<LegacyTable>` | `<Table>` | `<DataGrid>` | `<Table>` |
| `<LegacyBadge>` | `<Badge>` | `<Chip>` | `<Badge>` |
| `<LegacyTooltip>` | `<Tooltip>` | `<Tooltip>` | `<Tooltip>` |
| `<LegacyAvatar>` | `<Avatar>` | `<Avatar>` | `<Avatar>` |

### Feedback

| Legacy | Shadcn/ui | MUI | Chakra |
|--------|-----------|-----|--------|
| `<LegacyAlert>` | `<Alert>` | `<Alert>` | `<Alert>` |
| `<LegacyToast>` | `<Toast>` | `<Snackbar>` | `<useToast>` |
| `<LegacySpinner>` | `<Spinner>` | `<CircularProgress>` | `<Spinner>` |
| `<LegacySkeleton>` | `<Skeleton>` | `<Skeleton>` | `<Skeleton>` |

---

## File Naming

### Plan Files

```
refactor-plans/
├── 01-dashboard.md          # Numbered for order
├── 02-settings.md
├── 03-profile.md
├── admin-users.md           # Or grouped by area
├── admin-roles.md
├── shop-products.md
```

### Terminal States

| State | Suffix | Example |
|-------|--------|---------|
| Completed | `_done.md` | `01-dashboard_done.md` |
| Failed | `_failed.md` | `02-settings_failed.md` |
| Paused | `_paused.md` | `03-profile_paused.md` |

---

## Progress Tracking

### Quick Status

```bash
# Count by status
echo "✓ Done: $(ls refactor-plans/*_done.md 2>/dev/null | wc -l | tr -d ' ')"
echo "✗ Failed: $(ls refactor-plans/*_failed.md 2>/dev/null | wc -l | tr -d ' ')"
echo "⏳ Pending: $(ls refactor-plans/*.md 2>/dev/null | grep -v '_done\|_failed\|_paused' | wc -l | tr -d ' ')"
```

### Visual Progress

```bash
# Simple progress bar
total=$(ls refactor-plans/*.md 2>/dev/null | wc -l | tr -d ' ')
done=$(ls refactor-plans/*_done.md 2>/dev/null | wc -l | tr -d ' ')
echo "Progress: $done/$total pages"
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Queue stuck | `orchestrator list` → find active session → `orchestrator status <id>` |
| Page failed | Check `orchestrator status <id>` → fix issue → re-queue |
| Blocker waiting | `orchestrator respond <id> "answer"` → `orchestrator resume <id>` |
| All pages failing | Check shared dependency → fix → re-queue all |
| Executor confused | Plans too vague → add more detail to component mapping |

---

## Batch Generation Script

Generate multiple plan files from a template:

```bash
#!/bin/bash
# generate-plans.sh

PAGES=(
  "dashboard"
  "settings"
  "profile"
  "users-list"
  "user-detail"
  "products"
  "orders"
  "checkout"
)

TEMPLATE='# Refactor: PAGE_NAME Page

## Overview
Refactor PAGE_NAME page to new design system.

## Milestone 1: Component Migration
### Tasks
- [ ] Replace legacy components
- [ ] Update imports
- [ ] Fix TypeScript errors

### Deliverables
- [ ] Components migrated
- [ ] No errors

## Milestone 2: Testing
### Tasks
- [ ] Update tests
- [ ] Verify responsive
- [ ] Check accessibility

### Deliverables
- [ ] Tests passing
- [ ] No console errors'

mkdir -p refactor-plans

i=1
for page in "${PAGES[@]}"; do
  filename=$(printf "refactor-plans/%02d-%s.md" $i "$page")
  page_title=$(echo "$page" | sed 's/-/ /g' | sed 's/\b\(.\)/\u\1/g')
  echo "$TEMPLATE" | sed "s/PAGE_NAME/$page_title/g" > "$filename"
  echo "Created: $filename"
  ((i++))
done
```

Usage:
```bash
chmod +x generate-plans.sh
./generate-plans.sh
# Edit each plan to add page-specific details
```

---

## Time Estimates

| Page Complexity | Milestones | Est. Time | Token Usage |
|-----------------|------------|-----------|-------------|
| Simple (few components) | 1 | 10-15 min | ~50K |
| Standard (typical page) | 2 | 20-30 min | ~100K |
| Complex (data + UI) | 3 | 40-60 min | ~200K |

### Queue Estimates

| Pages | Complexity | Total Time |
|-------|------------|------------|
| 10 | Simple | 2-3 hours |
| 10 | Standard | 4-5 hours |
| 20 | Standard | 8-10 hours |
| 20 | Mixed | 10-12 hours |

---

## Git Commands

```bash
# Create branch
git checkout -b refactor/design-system

# Run queue
orchestrator start --queue refactor-plans/*.md --auto-commit

# After completion - view commits
git log --oneline -20

# Squash if desired
git rebase -i HEAD~20

# Push
git push -u origin refactor/design-system
```

---

## Telegram Setup (for Long Queues)

```yaml
# ~/.claude_orchestrator/config.yaml
telegram:
  enabled: true
  bot_token: "YOUR_BOT_TOKEN"
  chat_id: "YOUR_CHAT_ID"
```

```bash
# Test setup
orchestrator telegram test

# Start queue with notifications
orchestrator start --queue refactor-plans/*.md --auto-commit --telegram

# (Optional) Listen for blocker replies
orchestrator telegram listen
```

---

## Related

| File | Purpose |
|------|---------|
| `CLAUDE_orch_ui_refactor.md` | Full workflow documentation |
| `CLAUDE_orch_v2.md` | General orchestrator v2 docs |
| `CLAUDE_orch_v2_ref.md` | General orchestrator reference |
