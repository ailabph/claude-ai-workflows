# Claude Orchestrator - Quick Reference & UI Patterns

Supplementary reference for `CLAUDE_orchestrator.md`.

---

## Workflow Diagram

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Create    │────▶│   Execute   │────▶│   Review    │────▶│   Approve   │
│    Plan     │     │  Milestone  │     │   Report    │     │  or Reject  │
└─────────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                           ▲                                       │
                           └───────────────────────────────────────┘
                                    (repeat until complete)
```

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
- Review quickly - don't leave agent waiting
- Be specific: "Fix X" not "This doesn't look right"
- Minor issues can be noted without blocking

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Agent continues without stopping | Add **STOP** in bold, repeat instruction |
| Progress report missing details | Specify exact format in milestone |
| Agent deviates from plan | Reference specific section of plan doc |
| Tests not comprehensive | List specific test cases in milestone |

---

## Related Files

| File | Purpose |
|------|---------|
| `CLAUDE_orchestrator.md` | Full framework + templates |
| `docs/implementation-plans/` | Real implementation plans |
