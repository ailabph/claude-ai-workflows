# Frontend Visual QA Workflow - Reference Guide

This document contains detailed checklists, templates, and reference material for `CLAUDE_frontend_visual_qa_workflow.md`.

---

## Table of Contents

1. [Codebase Inspection Checklist](#codebase-inspection-checklist)
2. [Context File Template](#context-file-template)
3. [Session Plan Template](#session-plan-template)
4. [Visual Comparison Templates](#visual-comparison-templates)
5. [MCP Command Reference](#mcp-command-reference)
6. [Framework-Specific Guides](#framework-specific-guides)
7. [Figma Token Extraction Guide](#figma-token-extraction-guide)
8. [Viewport Reference](#viewport-reference)
9. [Common Issues & Solutions](#common-issues--solutions)
10. [Prompt Templates](#prompt-templates)

---

## Codebase Inspection Checklist

### Initial Exploration (First Session)

```markdown
## Codebase Inspection Checklist

### 1. Package & Framework Detection
- [ ] Read `package.json` for framework (react, next, vue, svelte)
- [ ] Identify CSS framework (tailwindcss, styled-components, emotion)
- [ ] Check for UI library (shadcn, radix, chakra, mui)
- [ ] Note testing framework (jest, vitest, playwright)
- [ ] Check build tool (vite, webpack, turbopack)

### 2. Configuration Files
- [ ] `tailwind.config.js` / `tailwind.config.ts` - theme tokens
- [ ] `postcss.config.js` - CSS processing
- [ ] `tsconfig.json` - path aliases (@/, ~/)
- [ ] `.env*` files - environment setup (don't read secrets)
- [ ] `next.config.js` / `vite.config.ts` - framework config

### 3. Directory Structure
- [ ] `src/` or root-level organization
- [ ] `components/` location and structure
- [ ] `app/` or `pages/` for routing
- [ ] `styles/` or `css/` for global styles
- [ ] `lib/` or `utils/` for utilities
- [ ] `services/` or `api/` for data layer

### 4. Styling Patterns
- [ ] Global styles location (`globals.css`, `index.css`)
- [ ] CSS variable definitions (`:root`)
- [ ] Tailwind `@layer` usage
- [ ] Component-specific style patterns
- [ ] Dark mode implementation (if any)

### 5. Component Patterns
- [ ] UI primitives location (`components/ui/`)
- [ ] Shared components vs page-specific
- [ ] Prop patterns (variants, sizes, colors)
- [ ] Composition patterns (children, slots)
- [ ] Export patterns (named vs default)

### 6. Routing Structure
- [ ] Router type (Next.js App/Pages, React Router, etc.)
- [ ] Layout components
- [ ] Protected routes / auth guards
- [ ] Dynamic routes pattern

### 7. State & Data
- [ ] State management (zustand, redux, context)
- [ ] Data fetching (react-query, swr, fetch)
- [ ] Form handling (react-hook-form, formik)
```

### Quick Inspection (Subsequent Sessions)

```markdown
## Quick Inspection Checklist

- [ ] Verify `CLAUDE_frontend_context.md` exists and is recent
- [ ] Check for new components since last session
- [ ] Verify target page/component exists
- [ ] Confirm dev server URL and port
- [ ] Check git status for uncommitted changes
```

---

## Context File Template

### Full Template: `CLAUDE_frontend_context.md`

```markdown
# Frontend Context

## Last Updated
[Date] - [Brief note on what changed]

## Project Overview
- **Name**: [Project name]
- **Framework**: [React 18, Next.js 14, Vue 3, etc.]
- **Language**: [TypeScript / JavaScript]
- **Package Manager**: [npm / yarn / pnpm]

## 1. Styling Framework

### Core Setup
- **CSS Framework**: [Tailwind CSS v3.4]
- **UI Library**: [Shadcn/ui, Radix, none]
- **Design System**: [Custom / External]

### Configuration Files
| File | Purpose |
|------|---------|
| `tailwind.config.js` | Theme tokens, plugins |
| `globals.css` | Base styles, CSS variables |
| `components.json` | Shadcn configuration |

### Theme Tokens
```javascript
// From tailwind.config.js
colors: {
  primary: '#EB5017',
  secondary: '#1A1A1A',
  background: '#FFFFFF',
  surface: '#F5F5F5',
  // ...
}

spacing: {
  // Custom spacing if any
}

fontSize: {
  // Custom sizes if any
}
```

### Key Style Patterns
| Pattern | Convention | Example |
|---------|------------|---------|
| Colors | Semantic names | `bg-primary`, `text-secondary` |
| Spacing | Tailwind scale | `p-4`, `gap-6`, `space-y-4` |
| Typography | Size + weight | `text-sm font-medium` |
| Responsive | Mobile-first | `md:grid-cols-2` |
| Dark mode | Class strategy | `dark:bg-gray-900` |

### Custom Utilities
```css
/* List any custom Tailwind classes */
@layer utilities {
  .text-gradient { /* ... */ }
}
```

## 2. Routing

### Setup
- **Router**: [Next.js App Router / React Router v6]
- **Structure**: [File-based / Config-based]
- **Base Path**: [/ or /app]

### Route Map
| Route | File | Layout | Auth |
|-------|------|--------|------|
| `/` | `app/page.tsx` | Root | Public |
| `/dashboard` | `app/dashboard/page.tsx` | Dashboard | Protected |
| `/dashboard/settings` | `app/dashboard/settings/page.tsx` | Dashboard | Protected |
| `/auth/login` | `app/auth/login/page.tsx` | Auth | Public |

### Layout Hierarchy
```
app/
├── layout.tsx (root - providers, fonts)
├── page.tsx (landing)
├── dashboard/
│   ├── layout.tsx (sidebar, header)
│   ├── page.tsx (dashboard home)
│   └── settings/
│       └── page.tsx
└── auth/
    ├── layout.tsx (centered card)
    └── login/
        └── page.tsx
```

## 3. Shared Components

### Location
`src/components/` or `components/`

### UI Primitives (`components/ui/`)
| Component | File | Variants | Notes |
|-----------|------|----------|-------|
| Button | `button.tsx` | default, outline, ghost, link | From Shadcn |
| Card | `card.tsx` | - | CardHeader, CardContent, CardFooter |
| Input | `input.tsx` | - | Controlled wrapper |
| Dialog | `dialog.tsx` | - | Radix-based modal |
| Select | `select.tsx` | - | Custom dropdown |

### Composite Components (`components/`)
| Component | File | Purpose |
|-----------|------|---------|
| Navbar | `navbar.tsx` | Top navigation |
| Sidebar | `sidebar.tsx` | Dashboard side nav |
| DataTable | `data-table.tsx` | Sortable table |
| FormField | `form-field.tsx` | Label + input + error |

### Component Patterns
```tsx
// Variant pattern (example)
interface ButtonProps {
  variant?: 'default' | 'outline' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  children: React.ReactNode;
}

// Composition pattern
<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
  </CardHeader>
  <CardContent>Content</CardContent>
</Card>
```

## 4. Page-Specific Components

| Page | Components | Location |
|------|------------|----------|
| Dashboard | `DashboardHeader`, `StatsGrid`, `RecentActivity` | `components/dashboard/` |
| Settings | `SettingsForm`, `ProfileCard`, `NotificationPrefs` | `components/settings/` |
| Auth | `LoginForm`, `RegisterForm`, `SocialButtons` | `components/auth/` |

## 5. Service Layer

### Location
`src/services/` or `lib/`

### Services
| Service | File | Purpose |
|---------|------|---------|
| API Client | `api.ts` | Axios/fetch wrapper |
| Auth | `auth.ts` | Login, logout, session |
| User | `user.ts` | User CRUD operations |

### Data Fetching Pattern
```tsx
// React Query pattern
const { data, isLoading } = useQuery({
  queryKey: ['users'],
  queryFn: () => userService.getAll(),
});

// Or SWR pattern
const { data, error } = useSWR('/api/users', fetcher);
```

## 6. State Management

| Type | Solution | Location |
|------|----------|----------|
| Global | [Zustand / Redux / Context] | `stores/` or `context/` |
| Server | [React Query / SWR] | Via hooks |
| Form | [React Hook Form] | Per-form |
| URL | [nuqs / searchParams] | Query strings |

## 7. Conventions

### File Naming
| Type | Convention | Example |
|------|------------|---------|
| Components | PascalCase | `UserCard.tsx` |
| Hooks | camelCase | `useAuth.ts` |
| Utils | camelCase | `formatDate.ts` |
| Types | PascalCase | `User.ts` or `types.ts` |

### Import Aliases
```json
// tsconfig.json paths
{
  "@/*": ["./src/*"],
  "@/components/*": ["./src/components/*"],
  "@/lib/*": ["./src/lib/*"]
}
```

### Export Patterns
- Components: Named exports preferred
- Utils: Named exports
- Types: Named exports
- Pages: Default export (Next.js)

## 8. Known Issues / Tech Debt

| Issue | Location | Priority | Notes |
|-------|----------|----------|-------|
| Inconsistent button styles | Various | Medium | Some use old pattern |
| Missing loading states | DataTable | Low | Add skeletons |
| Hardcoded colors | Header | High | Should use tokens |

## 9. Dev Environment

### Commands
| Command | Purpose |
|---------|---------|
| `npm run dev` | Start dev server (port 3000) |
| `npm run build` | Production build |
| `npm run lint` | ESLint check |
| `npm run type-check` | TypeScript check |

### URLs
- **Local**: `http://localhost:3000`
- **API**: `http://localhost:3001` or same origin
```

---

## Session Plan Template

### Full Template: `CLAUDE_session_plan.md`

```markdown
# Session Plan: [Feature/Page Name]

## Created
[YYYY-MM-DD HH:MM] - [Brief description]

## Objective
[1-2 sentences describing what we're implementing]

## MCP Resources

### Figma
| Resource | Value |
|----------|-------|
| File URL | `https://figma.com/design/[FILE_KEY]/[name]` |
| File Key | `[FILE_KEY]` |
| Target Node | `[NODE_ID]` (e.g., `1-9366`) |
| Mobile Node | `[NODE_ID]` (if different) |
| Tablet Node | `[NODE_ID]` (if different) |

### Local App
| Resource | Value |
|----------|-------|
| Dev Server | `http://localhost:3000` |
| Target Route | `/dashboard` |
| Auth Required | Yes / No |

## Design Specs

Extracted from Figma - persisted here for context recovery:

### Colors
| Token | Hex | Usage |
|-------|-----|-------|
| Primary | `#EB5017` | Buttons, links, accents |
| Secondary | `#1A1A1A` | Headings, primary text |
| Background | `#FFFFFF` | Page background |
| Surface | `#F5F5F5` | Card backgrounds |
| Border | `#E5E5E5` | Dividers, card borders |
| Error | `#DC2626` | Error states |
| Success | `#16A34A` | Success states |

### Spacing
| Element | Value | Tailwind |
|---------|-------|----------|
| Page padding | 24px | `p-6` |
| Card padding | 16px | `p-4` |
| Section gap | 24px | `gap-6` |
| Item gap | 12px | `gap-3` |
| Button padding | 12px 24px | `px-6 py-3` |

### Typography
| Element | Size | Weight | Line Height | Tailwind |
|---------|------|--------|-------------|----------|
| H1 | 32px | 700 | 40px | `text-3xl font-bold` |
| H2 | 24px | 600 | 32px | `text-2xl font-semibold` |
| H3 | 20px | 600 | 28px | `text-xl font-semibold` |
| Body | 16px | 400 | 24px | `text-base` |
| Small | 14px | 400 | 20px | `text-sm` |
| Caption | 12px | 500 | 16px | `text-xs font-medium` |

### Border Radius
| Element | Value | Tailwind |
|---------|-------|----------|
| Cards | 12px | `rounded-xl` |
| Buttons | 8px | `rounded-lg` |
| Inputs | 6px | `rounded-md` |
| Avatars | 50% | `rounded-full` |

### Shadows
| Element | Value | Tailwind |
|---------|-------|----------|
| Card | `0 1px 3px rgba(0,0,0,0.1)` | `shadow-sm` |
| Dropdown | `0 4px 6px rgba(0,0,0,0.1)` | `shadow-md` |
| Modal | `0 10px 25px rgba(0,0,0,0.15)` | `shadow-xl` |

## Target Files

| File | Action | Status |
|------|--------|--------|
| `src/app/dashboard/page.tsx` | Modify | Pending |
| `src/components/dashboard/StatsCard.tsx` | Modify | Pending |
| `src/components/ui/Card.tsx` | Modify | Pending |
| `src/components/dashboard/RecentActivity.tsx` | Create | Pending |

## Discrepancies to Fix

### High Priority
- [ ] Header height: 80px → 64px
- [ ] Primary button color: #EF4444 → #EB5017
- [ ] Card shadow missing

### Medium Priority
- [ ] Card padding: 24px → 16px
- [ ] Section gap: 16px → 24px
- [ ] Body font size: 14px → 16px

### Low Priority
- [ ] Border radius on inputs: 4px → 6px
- [ ] Caption font weight: 400 → 500

## Decisions Made

Clarifications and choices made during the session:

1. **[Topic]**: [Decision and rationale]
2. **[Topic]**: [Decision and rationale]

## Verification Checklist

### Visual Match
- [ ] Desktop (1280px) matches Figma
- [ ] Tablet (768px) matches Figma
- [ ] Mobile (375px) matches Figma

### Functionality
- [ ] No console errors
- [ ] No TypeScript errors
- [ ] Build passes
- [ ] Interactions work (hover, click, focus)

### Quality
- [ ] Responsive transitions smooth
- [ ] Loading states present
- [ ] Error states handled

## Git Checkpoints

| Checkpoint | Commit | Description | Rollback |
|------------|--------|-------------|----------|
| Baseline | `abc1234` | Before starting | `git reset --hard abc1234` |
| Phase 1 | - | - | - |
| Phase 2 | - | - | - |
| Final | - | - | - |

**Latest stable**: `abc1234`

## Progress Log

| Time | Update |
|------|--------|
| [HH:MM] | Session started, Figma specs fetched |
| [HH:MM] | Baseline captured, discrepancies identified |
| | |

## Screenshots Captured

| Type | Viewport | Description | Timestamp |
|------|----------|-------------|-----------|
| Figma | Desktop | Main design | [HH:MM] |
| Figma | Mobile | Mobile design | [HH:MM] |
| Live | 1280px | Baseline state | [HH:MM] |
| Live | 1280px | After fix 1 | [HH:MM] |

## Notes

[Any blockers, questions, or context for future reference]

---

## Recovery Prompt

**Copy and paste this into a new session if this session crashes:**

> Continue frontend visual QA session for [Feature Name].
>
> Read these files first:
> - `CLAUDE_frontend_visual_qa_workflow.md`
> - `CLAUDE_session_plan.md`
> - `CLAUDE_frontend_context.md`
>
> MCP Resources:
> - Figma file: [FILE_URL]
> - Figma node: [NODE_ID]
> - Local URL: http://localhost:3000/[route]
>
> Current status:
> - Last completed: [Task description]
> - Next task: [Task description]
> - Last checkpoint: `[commit-hash]`
> - Blocking issues: [None / description]
>
> Design specs are persisted in session plan. Continue implementation.

**Last updated**: [Timestamp or step description]
```

---

## Visual Comparison Templates

### Initial Comparison Report

```markdown
## Visual Comparison: [Page/Component Name]

### Sources
| Source | Reference |
|--------|-----------|
| Figma | Node `[node-id]` from file `[file-key]` |
| Live | `[URL]` at viewport `[width]x[height]` |
| Captured | [timestamp] |

### Overall Assessment
- **Match Level**: [X]% (rough estimate)
- **Discrepancies Found**: [N]
- **Complexity**: [Lightweight / Standard]

### Discrepancy Analysis

| # | Element | Location | Figma Spec | Current | Delta | Priority | Fix |
|---|---------|----------|------------|---------|-------|----------|-----|
| 1 | Header height | `Header.tsx` | 64px | 80px | +16px | High | `h-20` → `h-16` |
| 2 | Card padding | `Card.tsx` | 16px | 24px | +8px | Medium | `p-6` → `p-4` |
| 3 | Button color | `Button.tsx` | #EB5017 | #EF4444 | Different | High | Update theme |
| 4 | Body font | Global | 16px | 14px | -2px | Medium | `text-sm` → `text-base` |
| 5 | Gap | Page | 24px | 16px | -8px | Low | `gap-4` → `gap-6` |

### Console Status
- **Errors**: [0]
- **Warnings**: [N] ([new/pre-existing])

### Recommended Approach
1. [First fix - highest impact]
2. [Second fix]
3. [...]

### Files to Modify
| File | Changes |
|------|---------|
| `[file]` | [changes] |

Shall I proceed with these fixes?
```

### Verification Report (After Changes)

```markdown
## Verification Report: [Change Description]

### Change Applied
- **File**: `[file path]`
- **Change**: [description]
- **Code**: `[old]` → `[new]`

### Before/After Comparison

| Element | Figma | Before | After | Status |
|---------|-------|--------|-------|--------|
| [element] | [spec] | [was] | [now] | MATCH / MISMATCH |

### Visual Confirmation
- Screenshot captured at [timestamp]
- [Description of visual result]

### Remaining Discrepancies
- [ ] [remaining item 1]
- [ ] [remaining item 2]

### Next Action
[Proceeding to next fix / Done / Need human input]
```

### Multi-Viewport Report

```markdown
## Viewport Verification: [Page Name]

### Test Matrix

| Viewport | Width | Height | Figma Node | Status | Issues |
|----------|-------|--------|------------|--------|--------|
| Mobile | 375px | 812px | `[node]` | PASS/FAIL | [notes] |
| Tablet | 768px | 1024px | `[node]` | PASS/FAIL | [notes] |
| Desktop | 1280px | 800px | `[node]` | PASS/FAIL | [notes] |
| Wide | 1440px | 900px | `[node]` | PASS/FAIL | [notes] |

### Issues Found

#### [Viewport] - [Issue Title]
- **Element**: [element name]
- **Expected**: [from Figma]
- **Actual**: [observed]
- **Fix**: [proposed solution]

### Overall Status
- **Passing**: [X]/[Y] viewports
- **Action Required**: [Yes/No]
```

### Human Checkpoint Request

```markdown
## Checkpoint Request: [Milestone Name]

### Summary
Completed [X] changes to match Figma design for [page/component].

### Visual Status
| Viewport | Before | After | Figma Match |
|----------|--------|-------|-------------|
| Desktop | [captured] | [captured] | YES |
| Mobile | [captured] | [captured] | YES |

### Changes Made
| # | File | Change | Impact |
|---|------|--------|--------|
| 1 | `[file]` | [change] | [impact] |
| 2 | `[file]` | [change] | [impact] |

### Validation Results
- Console errors: 0
- Build status: PASS
- TypeScript: PASS

### Questions/Ambiguities
[None, or list items needing decision]

---

**Awaiting your approval to:**
- [ ] Create git checkpoint
- [ ] Proceed to [next task]

Please confirm or provide feedback.
```

---

## MCP Command Reference

### Figma MCP

#### Get File Info
```
Purpose: Retrieve file metadata and structure
Use when: Starting a new file, need to find node IDs

Returns: File name, pages, components, styles
```

#### Get Node Info
```
Purpose: Get detailed info about a specific node
Use when: Need exact specs for a component/frame
Parameters: file_key, node_id

Returns: Node properties (size, position, styles, children)
```

#### Export Node as Image
```
Purpose: Get screenshot of a Figma node
Use when: Need visual reference for comparison
Parameters: file_key, node_id, format (png/jpg/svg), scale (1-4)

Returns: Image data or URL
```

#### Get File Styles
```
Purpose: Get all defined styles in a file
Use when: Doing design token audit

Returns: Color styles, text styles, effect styles
```

#### Get File Components
```
Purpose: List all components in a file
Use when: Need to find specific component variants

Returns: Component names, IDs, descriptions
```

### Chrome MCP

#### Navigate
```
Purpose: Go to a URL
Use when: Opening target page
Parameters: url

Returns: Navigation result, page title
```

#### Screenshot
```
Purpose: Capture current viewport
Use when: Need visual state for comparison
Parameters: (optional) full_page, selector

Returns: Image data (base64 or file path)
```

#### Set Viewport
```
Purpose: Resize browser viewport
Use when: Testing responsive breakpoints
Parameters: width, height

Returns: Confirmation
```

#### Get Console Logs
```
Purpose: Retrieve browser console output
Use when: Checking for errors after changes
Parameters: (optional) level filter

Returns: Array of console messages with levels
```

#### Wait for Selector
```
Purpose: Wait until element exists
Use when: Page has async content
Parameters: selector, timeout

Returns: Element found confirmation
```

#### Click
```
Purpose: Click an element
Use when: Testing interactions, navigating
Parameters: selector

Returns: Click result
```

#### Type
```
Purpose: Enter text into input
Use when: Testing form inputs
Parameters: selector, text

Returns: Type result
```

#### Evaluate
```
Purpose: Run JavaScript in page context
Use when: Need computed styles, DOM info
Parameters: script

Returns: Script result
```

---

## Framework-Specific Guides

### Next.js + Tailwind + Shadcn

#### Key Files
| File | Purpose |
|------|---------|
| `tailwind.config.ts` | Theme tokens, content paths |
| `globals.css` | CSS variables, base styles |
| `components.json` | Shadcn configuration |
| `lib/utils.ts` | `cn()` utility for class merging |

#### Style Pattern
```tsx
import { cn } from '@/lib/utils';

export function Card({ className, ...props }) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-card p-4 shadow-sm",
        className
      )}
      {...props}
    />
  );
}
```

#### CSS Variables (common setup)
```css
:root {
  --background: 0 0% 100%;
  --foreground: 0 0% 3.9%;
  --card: 0 0% 100%;
  --card-foreground: 0 0% 3.9%;
  --primary: 24 95% 50%;
  --primary-foreground: 0 0% 98%;
  /* ... */
}
```

### React + CSS Modules

#### Key Files
| File | Purpose |
|------|---------|
| `*.module.css` | Component styles |
| `styles/variables.css` | CSS variables |
| `styles/global.css` | Global styles |

#### Style Pattern
```tsx
import styles from './Card.module.css';

export function Card({ className }) {
  return (
    <div className={`${styles.card} ${className}`}>
      {/* ... */}
    </div>
  );
}
```

### Vue + Tailwind

#### Key Files
| File | Purpose |
|------|---------|
| `tailwind.config.js` | Theme configuration |
| `assets/main.css` | Global styles |
| `*.vue` | Single-file components |

#### Style Pattern
```vue
<template>
  <div :class="['rounded-xl', 'p-4', customClass]">
    <slot />
  </div>
</template>

<script setup>
defineProps({
  customClass: String
});
</script>
```

### Styled Components

#### Key Files
| File | Purpose |
|------|---------|
| `theme.ts` | Theme object |
| `GlobalStyle.ts` | Global styles |
| `*.styles.ts` | Component styles |

#### Style Pattern
```tsx
import styled from 'styled-components';

export const Card = styled.div`
  border-radius: ${({ theme }) => theme.radii.xl};
  padding: ${({ theme }) => theme.space[4]};
  background: ${({ theme }) => theme.colors.card};
`;
```

---

## Figma Token Extraction Guide

### Color Extraction

When extracting colors from Figma:

1. **Get fill colors**
   - Look for `fills` array in node properties
   - Extract `color` object (r, g, b values are 0-1 scale)
   - Convert: `hex = #${Math.round(r*255).toString(16)}...`

2. **Map to theme tokens**
   ```
   Figma Color Name → Theme Token
   Primary/500      → primary
   Neutral/900      → foreground
   Neutral/50       → background
   ```

### Spacing Extraction

1. **Padding/margins**
   - Look for `paddingTop`, `paddingRight`, etc.
   - Or `padding` for uniform padding

2. **Gap (auto-layout)**
   - Look for `itemSpacing` property
   - This is the gap between children

3. **Map to Tailwind**
   ```
   8px  → 2  (p-2, gap-2)
   12px → 3  (p-3, gap-3)
   16px → 4  (p-4, gap-4)
   24px → 6  (p-6, gap-6)
   32px → 8  (p-8, gap-8)
   ```

### Typography Extraction

1. **Font properties**
   - `fontSize` - size in pixels
   - `fontWeight` - numeric weight
   - `lineHeightPx` - line height in pixels
   - `fontFamily` - font name
   - `letterSpacing` - tracking

2. **Map to Tailwind**
   ```
   12px → text-xs
   14px → text-sm
   16px → text-base
   18px → text-lg
   20px → text-xl
   24px → text-2xl

   400 → font-normal
   500 → font-medium
   600 → font-semibold
   700 → font-bold
   ```

### Border Radius Extraction

1. **Uniform radius**
   - `cornerRadius` property

2. **Individual corners**
   - `topLeftRadius`, `topRightRadius`, etc.

3. **Map to Tailwind**
   ```
   0px  → rounded-none
   4px  → rounded
   6px  → rounded-md
   8px  → rounded-lg
   12px → rounded-xl
   16px → rounded-2xl
   50%  → rounded-full
   ```

### Shadow Extraction

1. **Effect properties**
   - Look for `effects` array
   - Type: `DROP_SHADOW` or `INNER_SHADOW`
   - Properties: `offset`, `radius`, `spread`, `color`

2. **Map to Tailwind** (approximate)
   ```
   blur 3px  → shadow-sm
   blur 6px  → shadow
   blur 15px → shadow-md
   blur 25px → shadow-lg
   blur 50px → shadow-xl
   ```

---

## Viewport Reference

### Standard Breakpoints

| Name | Width | Tailwind | Use Case |
|------|-------|----------|----------|
| Mobile S | 320px | - | Small phones |
| Mobile M | 375px | - | iPhone SE, standard mobile |
| Mobile L | 425px | - | Large phones |
| Tablet | 768px | `md:` | iPad portrait, tablets |
| Laptop | 1024px | `lg:` | Small laptops, iPad landscape |
| Desktop | 1280px | `xl:` | Standard desktop |
| Wide | 1440px | `2xl:` | Large monitors |

### Figma Frame Sizes (Common)

| Device | Frame Size |
|--------|------------|
| iPhone 14 | 390 x 844 |
| iPhone 14 Pro Max | 430 x 932 |
| iPhone SE | 375 x 667 |
| iPad | 768 x 1024 |
| iPad Pro 11" | 834 x 1194 |
| Desktop | 1440 x 900 |
| MacBook Pro 14" | 1512 x 982 |

### Chrome MCP Viewport Settings

```
// Common viewports for testing
Mobile:  { width: 375, height: 812 }   // iPhone X-style
Tablet:  { width: 768, height: 1024 }  // iPad portrait
Desktop: { width: 1280, height: 800 }  // Standard desktop
Wide:    { width: 1440, height: 900 }  // Large desktop
```

---

## Common Issues & Solutions

### Visual Discrepancies

| Issue | Cause | Solution |
|-------|-------|----------|
| Colors slightly off | Tailwind palette vs custom | Use exact hex in config |
| Spacing inconsistent | Mixed units | Standardize on Tailwind scale |
| Font rendering different | System fonts | Ensure font loaded correctly |
| Shadows don't match | Browser rendering | Use closest Tailwind class |
| Border radius off | Inconsistent use | Standardize radius tokens |

### MCP Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Figma export fails | Invalid node ID | Verify node-id format |
| Chrome can't navigate | Dev server not running | Start dev server first |
| Screenshot blank | Page not loaded | Add wait for element |
| Console errors | App crashed | Check terminal for errors |
| Viewport not changing | Browser state | Try full page refresh |

### Git Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Can't commit | Unstaged changes | `git add -A` first |
| Wrong files staged | Unrelated changes | `git reset` specific files |
| Need to rollback | Bad change | `git reset --hard [hash]` |
| Lost checkpoint hash | Session crashed | Check `git log` |

---

## Prompt Templates

### Starting a New Page Implementation

```
Read CLAUDE_frontend_visual_qa_workflow.md and follow the workflow.

Figma design: https://figma.com/design/ABC123/ProjectName?node-id=1-100
Local app: http://localhost:3000/dashboard

Implement this dashboard page to match the Figma design exactly.
Test on desktop (1280px) and mobile (375px).
```

### Visual QA Check

```
Read CLAUDE_frontend_visual_qa_workflow.md.

Figma: https://figma.com/design/ABC123/ProjectName?node-id=1-200
Local: http://localhost:3000/settings

The settings page doesn't look quite right.
Compare to Figma and fix any discrepancies you find.
```

### Multi-Screen Implementation

```
Read CLAUDE_frontend_visual_qa_workflow.md.

Figma file: https://figma.com/design/ABC123/ProjectName

Implement these screens in order:
1. Dashboard (node-id: 1-100) → /dashboard
2. Settings (node-id: 1-200) → /settings
3. Profile (node-id: 1-300) → /profile

Checkpoint after each screen. Test desktop and mobile.
```

### Design Token Audit

```
Read CLAUDE_frontend_visual_qa_workflow.md.

The colors seem off across the whole site.

Figma design system: https://figma.com/design/ABC123/DesignSystem?node-id=0-1

Compare Figma color tokens with our tailwind.config.js
and fix any mismatches.
```

### Resume After Crash

```
Continue frontend visual QA session for Dashboard Page.

Read these files first:
- CLAUDE_frontend_visual_qa_workflow.md
- CLAUDE_session_plan.md
- CLAUDE_frontend_context.md

MCP Resources:
- Figma: https://figma.com/design/ABC123/App?node-id=1-100
- Local: http://localhost:3000/dashboard

Current status:
- Last completed: Fixed header height and card padding
- Next task: Update button colors
- Last checkpoint: `def5678`
- Blocking issues: None

Continue from where we left off.
```

### Specific Component Fix

```
Read CLAUDE_frontend_visual_qa_workflow.md.

Figma: https://figma.com/design/ABC123/Components?node-id=5-50
Local: http://localhost:3000/dashboard

Focus only on the StatsCard component in the dashboard.
The shadow and border radius don't match Figma.
```
