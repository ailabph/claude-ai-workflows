page route: , current screenshot: , target design: , figma: 
## Feature Request: Refactor [Page Name] to V2 Design

### References
- Workflow framework: `CLAUDE_orchestrator.md`
- Design system: `docs/design-system/SYSTEM_UI_GLOSSARY.md`

### Artifacts
- **Page route**: [already provided, see above]
- **Current screenshot**: [already provided, see above]
- **Target design**: [already provided, see above]
- **Figma (dev mode)**: [already provided, see above]

  ---

## Phase 1: Research

### 1.1 Figma Analysis
Use Figma MCP (read-only commands only):
- `get_file` - component structure
- `get_file_styles` - design tokens used
- `get_file_components` - reusable components
- `get_node` - specific element properties

Document:
- Color tokens, typography, spacing
- Component variants and states
- Responsive breakpoints if specified
- Assets needing export

### 1.2 Current Implementation Audit
Investigate the codebase to understand:

**Route Structure**
src/app/(route-group)/[page]/
├── page.tsx          ← main component
├── layout.tsx        ← if exists
├── loading.tsx       ← if exists
└── components/       ← page-specific components

**Component Hierarchy**
- Identify shared components from `src/components/`
- Identify page-specific components
- Map NextUI components in use (Button, Card, Table, Modal, etc.)
- Map custom components and their props

**Styling Approach**
- Tailwind utility classes
- NextUI theme customizations
- Any CSS modules or global styles

**Data Layer**
- API calls (fetch, axios, react-query)
- State management (useState, useContext, zustand, etc.)
- Props drilling vs context

**Interactions**
- Modals/drawers and their triggers
- Form handling
- Navigation patterns
- Loading/error states

### 1.3 User Flow Documentation
Create mermaid diagram of current user flow:
  ```mermaid
  flowchart TD
      A[Page Load] --> B{Auth Check}
      B -->|Yes| C[Render Dashboard]
      B -->|No| D[Redirect Login]
      C --> E[User Actions...]

  Identify what MUST be preserved:
  - Route path and params
  - API contracts
  - Core functionality
  - Navigation targets

  ---
  Phase 2: Planning

  2.1 Layout Design

  Create ASCII layout showing target component structure:
  ┌─────────────────────────────────────────────────────┐
  │ Header (shared)                                     │
  ├─────────────────────────────────────────────────────┤
  │ PageHeader: Title + Actions                         │
  ├──────────────────────┬──────────────────────────────┤
  │ Sidebar/Filters      │ Main Content Area            │
  │                      │ ┌────────────────────────┐   │
  │                      │ │ Component A            │   │
  │                      │ └────────────────────────┘   │
  │                      │ ┌────────────────────────┐   │
  │                      │ │ Component B            │   │
  │                      │ └────────────────────────┘   │
  └──────────────────────┴──────────────────────────────┘

  2.2 Component Inventory

  | Component   | Status | Location      | Notes           |
  |-------------|--------|---------------|-----------------|
  | PageHeader  | Modify | page-specific | Add new actions |
  | DataTable   | Reuse  | shared        | Update columns  |
  | FilterPanel | Create | page-specific | New component   |
  | DetailModal | Modify | page-specific | New layout      |

  2.3 Design Token Mapping

  | Figma Token    | Tailwind/NextUI  | Usage            |
  |----------------|------------------|------------------|
  | primary-600    | bg-primary       | CTA buttons      |
  | surface-card   | bg-content1      | Card backgrounds |
  | text-secondary | text-default-500 | Secondary text   |

  ---
  Milestones

  Milestone 1: Scaffolding + Types

  Objective: Set up component structure and TypeScript interfaces

  Tasks:
  1. Create/update page component file structure
  2. Define TypeScript interfaces for:
    - Component props
    - API response types (if changed)
    - Form data types (if applicable)
  3. Create empty component shells with proper exports
  4. Verify route still loads (even if unstyled)

  Deliverables:
  - src/app/(group)/[page]/page.tsx - updated structure
  - src/app/(group)/[page]/components/index.ts - exports
  - src/types/[page].ts - type definitions (if needed)
  - Page renders without runtime errors
  - yarn build passes

  ⛔ STOP - Generate progress report, wait for approval

  ---
  Milestone 2: Layout + Core Components

  Objective: Implement page layout and primary components matching Figma structure

  Tasks:
  1. Implement page layout grid (Tailwind flex/grid) per Figma specs
  2. Build core components with NextUI primitives:
    - Cards, Buttons, Inputs per design system glossary
    - Tables with correct column structure from Figma
    - Navigation elements
  3. Wire up existing data (no API changes)
  4. Implement responsive breakpoints (sm:, md:, lg:) based on Figma

  Deliverables:
  - Layout structure matches Figma component hierarchy
  - Core components render with real data
  - Responsive classes applied per design specs
  - No TypeScript errors
  - yarn build passes

  ⛔ STOP - Generate progress report, wait for approval

  ---
  Milestone 3: Styling + Design Tokens

  Objective: Apply design system tokens to match Figma design

  Tasks:
  1. Apply color tokens from design system glossary
  2. Typography: font sizes, weights, line heights from Figma
  3. Spacing: margins, paddings, gaps per Figma node properties
  4. Shadows, borders, rounded corners per Figma styles
  5. NextUI component variants (color, variant, size)
  6. Hover/focus states based on Figma component variants

  Deliverables:
  - Colors match design system glossary mapping
  - Typography matches Figma text styles
  - Spacing matches Figma auto-layout/spacing values
  - Component variants applied correctly
  - yarn build passes

  ⛔ STOP - Generate progress report, wait for approval

  ---
  Milestone 4: Interactions + Modals

  Objective: Implement all interactive behaviors

  Tasks:
  1. Modal/drawer open/close logic
  2. Form validation and submission (preserve existing logic)
  3. Loading states (skeletons, spinners)
  4. Error states and empty states
  5. Toast notifications if applicable
  6. Transitions/animations (NextUI defaults or per Figma)

  Deliverables:
  - All modals/drawers functional
  - Forms validate and submit correctly
  - Loading states implemented
  - Error handling preserved/improved
  - Keyboard navigation (Escape closes modals, Tab order)
  - yarn build passes

  ⛔ STOP - Generate progress report, wait for approval

  ---
  Milestone 5: Integration + Cleanup

  Objective: Final integration and code quality

  Tasks:
  1. Verify full user flow works end-to-end
  2. Remove unused imports/components from refactor
  3. Remove console.logs and debug code
  4. Ensure no TypeScript warnings
  5. Update mermaid diagram if flow changed
  6. Document any deviations from Figma in progress report

  Deliverables:
  - User flow preserved (per mermaid diagram)
  - No console errors/warnings
  - TypeScript strict mode passes
  - No unused code from old implementation
  - yarn build passes
  - Deviations documented (if any)

  ⛔ STOP - Generate final progress report

  ---
  Output

  Create plan document: docs/refactor/DOC_[page-name]_v2_plan.md

  Include:
  1. Research findings (1.1-1.3)
  2. Planning outputs (2.1-2.3)
  3. All 5 milestones with deliverables
  4. Figma reference links
  5. Design token mapping table
  6. Component inventory table

  After plan creation, output: [PLAN_READY]

  ---