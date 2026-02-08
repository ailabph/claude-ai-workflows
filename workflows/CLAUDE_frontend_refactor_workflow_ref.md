# Frontend Refactor Workflow - Human Reference

Quick reference for setting up and using `CLAUDE_frontend_refactor_workflow.md`.

---

## Quick Setup

### 1. Permissions (Reduce Prompts)

Create `.claude/settings.json` in your project:

```json
{
  "permissions": {
    "allow": [
      "Bash(npm run build)",
      "Bash(npm run dev)",
      "Bash(npm run start)",
      "Bash(npm run lint)",
      "Bash(npm run test)",
      "Bash(npx playwright screenshot:*)",
      "Bash(ls:*)",
      "Bash(git status)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(git add:*)",
      "Bash(git commit:*)",
      "Bash(git branch)",
      "Bash(mkdir:*)",
      "Read",
      "Glob",
      "Grep"
    ],
    "deny": [
      "Bash(rm -rf:*)",
      "Bash(git push:*)",
      "Bash(git reset --hard:*)"
    ]
  }
}
```

**What this allows without prompts:**
| Category | Commands |
|----------|----------|
| Build/Dev | `npm run build`, `npm run dev`, `npm run lint`, `npm run test` |
| Screenshots | `npx playwright screenshot ...` |
| File exploration | `ls`, all Read/Glob/Grep tools |
| Git (read + commit) | `git status`, `git diff`, `git log`, `git add`, `git commit` |
| Directory creation | `mkdir -p screenshots/...` |

**Still requires approval:**
- `git push` (explicit approval)
- `rm -rf` (destructive)
- `git reset --hard` (destructive rollback)

### 2. Slash Command (Optional)

Create `.claude/commands/frontend-refactor.md`:

```markdown
Read CLAUDE_frontend_refactor_workflow.md and follow the workflow.

Starting point: $ARGUMENTS
```

Then kickstart with:
```
/frontend-refactor src/pages/Dashboard.tsx
```

---

## Kickstart Prompts

### New Session
```
Read CLAUDE_frontend_refactor_workflow.md and follow the workflow.

[paste screenshot]

I want to [describe task]
```

### With Existing Context
```
Read CLAUDE_frontend_refactor_workflow.md and CLAUDE_frontend_context.md.

[paste screenshot]

Task: [describe task]
```

### Resume Crashed Session
```
[paste recovery prompt from CLAUDE_session_plan.md]
```

### After Context Compression
```
Context seems compressed. Re-read the workflow:
- CLAUDE_frontend_refactor_workflow.md
- CLAUDE_session_plan.md (if exists)
- CLAUDE_frontend_context.md (if exists)

Continue from where we left off.
```

### Visual Comparison
```
Read CLAUDE_frontend_refactor_workflow.md.

Check [page]. Design [image-1], current [image-2].
Identify differences and fix.
```

### With Figma Link
```
Read CLAUDE_frontend_refactor_workflow.md.

Check [page]. Current [image-1], Figma [image-2].
Figma link for specs: [url]

Identify differences and fix.
```

### Site-Wide Token Audit
```
Read CLAUDE_frontend_refactor_workflow.md.

Colors seem off site-wide.
Check Figma via MCP: [url]

Compare with theme config and fix.
```

---

## Files Overview

| File | Purpose | Lifecycle |
|------|---------|-----------|
| `CLAUDE_frontend_refactor_workflow.md` | Main workflow instructions | Permanent (don't modify) |
| `CLAUDE_frontend_context.md` | Codebase architecture knowledge | Persists across sessions |
| `CLAUDE_session_plan.md` | Task-specific state + recovery | Temporary (per task) |

### Context File Location
- Project root: `./CLAUDE_frontend_context.md`
- Or docs folder: `./docs/CLAUDE_frontend_context.md`

### Session Plan Location
- Project root: `./CLAUDE_session_plan.md`
- Or with date: `./docs/sessions/PLAN_{feature}_{date}.md`

---

## Task Complexity Modes

### Lightweight Mode
**When:** Single file, <15 min, simple/unambiguous

**Examples:**
- Change button color
- Fix padding
- Hide element on mobile
- Fix typo

**Flow:** Task → Implement → Report → Done

**No session plan, no git checkpoints.**

### Standard Mode
**When:** Multi-file, design specs, multiple iterations expected

**Examples:**
- Match page to Figma design
- Rebuild navigation
- Update all cards to new design system
- New component from scratch

**Flow:** Task → Clarify → Plan → Baseline commit → Implement → Approve → Checkpoint → Repeat

**Creates session plan, git checkpoints after each approval.**

---

## Git Checkpoint Commands

```bash
# View recent checkpoints
git log --oneline -10

# Rollback to specific checkpoint (destructive)
git reset --hard <commit-hash>

# Rollback but keep changes unstaged
git reset --soft <commit-hash>

# View what changed since checkpoint
git diff <commit-hash>
```

---

## Signs of Context Compression

Watch for these behaviors - means agent lost workflow context:

- Stops using structured comparison tables
- Forgets to update session plan
- Doesn't mention git checkpoints
- Responses become generic
- Skips validation steps

**Recovery:** Use the "After Context Compression" prompt above.

---

## Human Review Workflow

### After Agent Reports Changes

1. **Take screenshot** of updated UI
2. **Compare** to design/expectation
3. **Respond:**
   - "Looks good!" → Agent checkpoints and continues
   - "The X is off, see screenshot" → Agent adjusts

### Approval Language

| Intent | Say |
|--------|-----|
| Approve, continue | "Looks good, next task" |
| Approve, done | "Perfect, we're done" |
| Needs fix | "The spacing is wrong, see screenshot" |
| Rollback | "This broke something, rollback to last checkpoint" |
| Abort | "Stop, let's take a different approach" |

---

## When to Provide What

| Scenario | Provide |
|----------|---------|
| Start any task | Screenshot of current state |
| Design match | Design image + current screenshot |
| Precise specs needed | Figma URL (for MCP fetch) |
| Theme consistency | Path to theme files |
| After changes | Updated screenshot |
| Error occurred | Screenshot + console error text |
| Interaction bug | Text description (smooth/laggy/choppy) |

---

## Directory Setup (Optional)

For visual QA workflows:

```bash
mkdir -p screenshots/figma screenshots/browser
```

---

## Troubleshooting

### Agent not following workflow
Re-read prompt: "Read CLAUDE_frontend_refactor_workflow.md and follow it."

### Agent lost context mid-session
Use compression recovery prompt.

### Wrong mode (lightweight vs standard)
Explicitly state: "Use standard mode for this" or "This is lightweight, just do it."

### Too many permission prompts
Check `.claude/settings.json` is in project root and formatted correctly.

### Rollback needed
Use git checkpoint from session plan: `git reset --hard <hash>`

---

## Token/Cost Estimation

The workflow file is ~41K characters (~10K tokens).

- First message (loading workflow): ~10K tokens
- Subsequent messages: Much smaller (conversation context)
- With context compression: Workflow re-read adds ~10K tokens

**Tip:** For many small tasks, keep session alive rather than starting fresh each time.

---

## Not a Sub-Agent

This workflow is interactive (human-in-the-loop), so it's **not suitable** for autonomous sub-agent conversion. The slash command approach above provides the "one command kickstart" without fighting the interactive nature.

---

## Framework Adaptations (Detailed)

### React + Tailwind (Default)

**Inspection Focus:**
- `tailwind.config.js` for theme/colors
- `globals.css` for base styles
- Component `className` patterns
- Responsive prefixes (`sm:`, `md:`, `lg:`)

### Vue + Tailwind

**Inspection Focus:**
- `tailwind.config.js`
- `<style>` blocks in SFCs
- Scoped vs global styles
- Composition API patterns

### React + CSS Modules

**Inspection Focus:**
- `*.module.css` files
- `className={styles.xxx}` patterns
- CSS variable usage
- Global vs scoped styles

### React + Styled Components

**Inspection Focus:**
- `styled.xxx`` patterns
- Theme provider setup
- Prop-based styling
- CSS-in-JS conventions

### Svelte

**Inspection Focus:**
- `<style>` blocks
- `:global()` usage
- CSS custom properties
- Component composition

---

## Example Session

### Session Start

**Human**:
> Here's our settings page (screenshot attached). I want to refactor this - it's using old inline styles and the layout is inconsistent with our other pages.

**Agent**:
> I don't see a `CLAUDE_frontend_context.md` file in this project. Let me inspect the codebase to understand the frontend architecture before we begin.
>
> [Proceeds with inspection...]
>
> I've created `CLAUDE_frontend_context.md`. Here's what I found:
> - **Framework**: Next.js 14 with App Router
> - **Styling**: Tailwind CSS + Shadcn UI components
> - **Target page**: `app/(dashboard)/settings/page.tsx`
> - **Issue identified**: This page uses inline `style={{}}` props while rest of app uses Tailwind
>
> Ready for your refactoring task. What specifically would you like to change?

### Task Iteration

**Human**:
> Convert all inline styles to Tailwind and make the layout match our dashboard page - with the sidebar pattern.

**Agent**:
> Before I proceed, a few questions:
> 1. The dashboard uses a 240px fixed sidebar. Should settings match this exactly?
> 2. I see the current page has a max-width of 800px. Should I keep this constraint?
> 3. There's a custom background color `#f5f5f5` - should I map this to `bg-gray-100` or add it to your Tailwind config?

**Human**:
> 1. Yes, match dashboard exactly
> 2. Keep the max-width
> 3. Map to bg-gray-100

**Agent**:
> [Implements changes...]
>
> ## Changes Made
> ### Files Modified:
> - `app/(dashboard)/settings/page.tsx` - Converted to Tailwind, added sidebar layout
> - `app/(dashboard)/settings/layout.tsx` - Created to wrap with dashboard shell
>
> ### Key Changes:
> 1. Replaced all `style={{}}` with Tailwind classes
> 2. Added `DashboardShell` wrapper for consistent sidebar
> 3. Applied `max-w-3xl` to content area
> 4. Converted `#f5f5f5` to `bg-gray-100`
>
> **Ready for your review. Please share an updated screenshot.**

**Human**:
> (shares screenshot) The sidebar is there but the content padding looks off compared to dashboard.

**Agent**:
> I see the issue. Looking at your screenshot, the content area has less left padding than the dashboard. Let me check...
>
> Found it: Dashboard uses `pl-8` but I applied `pl-6`. Updating now.
>
> [Makes fix...]
>
> Changed `pl-6` to `pl-8` in the content wrapper. Please refresh and share another screenshot.

### Session End

**Human**:
> Perfect, that matches now. We're done for today.

**Agent**:
> Great! I've updated `CLAUDE_frontend_context.md` with:
> - Added: Settings page now uses DashboardShell layout
> - Removed: Note about inline styles in settings (now converted)
> - Pattern: All dashboard pages should use `pl-8` content padding
>
> Session complete. Ready for next time!

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-12 | Initial frontend refactor workflow |
| 1.1 | 2024-12 | Added: Design Reference (Figma MCP, theme files, inline specs), Interaction & Behavior Feedback, Error Communication, Component Isolation strategies |
| 1.2 | 2024-12 | Added: Session Plan File for persisting task details across context compression |
| 1.3 | 2024-12 | Added: Recovery Prompt in session plan - auto-updated copy-paste prompt for session crash recovery |
| 2.0 | 2024-12 | Major update: Added Quick Reference, Task Complexity Tiers (lightweight vs standard mode), Files Modified tracking, Pre-Completion Validation checklist, enhanced completion phase with validation steps |
| 2.1 | 2024-12 | Added: Git Checkpoint Strategy - commit after approval, baseline commits, rollback commands, checkpoint tracking in session plan |
| 2.2 | 2024-12 | Added: "How to Start a Session" with kickstart prompts for new session, existing context, and crash recovery |
| 2.3 | 2024-12 | Added: Visual Comparison section - structured format for comparing design image vs implementation screenshot, includes combining with theme files |
| 2.4 | 2024-12 | Added: Design Token Audit section - for site-wide issues comparing Figma tokens vs theme config (always Standard mode) |
| 2.5 | 2024-12 | Added: Combine with Figma MCP for Precise Specs - using images for visual diff + MCP link for exact measurements |
| 2.6 | 2024-12 | Added: Option 4 "After Context Compression" - signs of compression and recovery prompt |
| 2.7 | 2024-12 | Added: Cheat Sheet at top of document - all copy-paste prompts in one place for quick access |
| 3.0 | 2024-12 | Converted ASCII diagrams to Mermaid, simplified verbose boxes to markdown |
| 3.1 | 2024-12 | Moved Example Session, Framework Adaptations details, and Version History to reference file |
