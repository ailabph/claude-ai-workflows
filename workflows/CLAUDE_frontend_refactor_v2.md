## Feature Request: Refactor [Page Name] to V2 Design

### References
- Workflow framework: `CLAUDE_orchestrator.md`
- Design system: `docs/design-system/SYSTEM_UI_GLOSSARY.md`

### Artifacts

**Page Route**: <pasted-page-url>

**Current State**:
| View | Screenshot |
|------|------------|
| Main page | <paste-screenshot-current-1> |
| Modal/Drawer (if any) | <paste-screenshot-current-2> |

**Target Design**:
| View | Screenshot | Figma Dev Link |
|------|------------|----------------|
| Main page | <paste-screenshot-target-1> | <figma-url-1> |
| Modal/Drawer | <paste-screenshot-target-2> | <figma-url-2> |
| [Additional state] | <paste-screenshot-target-N> | <figma-url-N> |

> Add rows as needed for each distinct view, modal, drawer, or state that has its own Figma frame.

---

## Phase 1: Research

### 1.1 Figma Analysis
Use Figma MCP (read-only commands only) on **each Figma dev link**:
- `get_file` - component structure
- `get_file_styles` - design tokens used
- `get_file_components` - reusable components
- `get_node` - specific element properties

For each view/modal, document:
- Color tokens, typography, spacing
- Component variants and states
- Responsive breakpoints if specified
- Assets needing export
- Relationship between views (e.g., which button triggers which modal)

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
      B -->|Yes| C[Render Main View]
      B -->|No| D[Redirect Login]
      C --> E[User clicks action]
      E --> F[Open Modal]
      F --> G[Submit/Cancel]
      G --> C
  ```

  Identify what MUST be preserved:
  - Route path and params
  - API contracts
  - Core functionality
  - Navigation targets
  - Modal/drawer trigger logic

  ---
  Phase 2: Planning

  2.1 Layout Design

  Create ASCII layout for each target view:

  Main Page
  ┌─────────────────────────────────────────────────────┐
  │ Header (shared)                                     │
  ├─────────────────────────────────────────────────────┤
  │ PageHeader: Title + Actions                         │
  ├──────────────────────┬──────────────────────────────┤
  │ Sidebar/Filters      │ Main Content Area            │
  │                      │ ┌────────────────────────┐   │
  │                      │ │ Component A            │   │
  │                      │ └────────────────────────┘   │
  └──────────────────────┴──────────────────────────────┘

  Modal/Drawer (if applicable)
  ┌─────────────────────────────────────┐
  │ Modal Header              [X]       │
  ├─────────────────────────────────────┤
  │ Form Field 1                        │
  │ Form Field 2                        │
  │ ...                                 │
  ├─────────────────────────────────────┤
  │              [Cancel] [Submit]      │
  └─────────────────────────────────────┘

  2.2 Component Inventory

  | Component   | Status | Location      | View  | Notes           |
  |-------------|--------|---------------|-------|-----------------|
  | PageHeader  | Modify | page-specific | Main  | Add new actions |
  | DataTable   | Reuse  | shared        | Main  | Update columns  |
  | FilterPanel | Create | page-specific | Main  | New component   |
  | DetailModal | Modify | page-specific | Modal | New layout      |
  | ModalForm   | Create | page-specific | Modal | New form fields |

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
  3. Create empty component shells with proper exports (including modal components)
  4. Verify route still loads (even if unstyled)

  Deliverables:
  - src/app/(group)/[page]/page.tsx - updated structure
  - src/app/(group)/[page]/components/index.ts - exports
  - src/types/[page].ts - type definitions (if needed)
  - Modal/drawer component shells created
  - Page renders without runtime errors
  - yarn build passes

  ⛔ STOP - Generate progress report, wait for approval

  ---
  Milestone 2: Layout + Core Components

  Objective: Implement page layout and primary components matching Figma structure

  Tasks:
  1. Implement main page layout grid (Tailwind flex/grid) per Figma specs
  2. Build core components with NextUI primitives:
    - Cards, Buttons, Inputs per design system glossary
    - Tables with correct column structure from Figma
    - Navigation elements
  3. Wire up existing data (no API changes)
  4. Implement responsive breakpoints (sm:, md:, lg:) based on Figma

  Deliverables:
  - Main page layout structure matches Figma component hierarchy
  - Core components render with real data
  - Responsive classes applied per design specs
  - No TypeScript errors
  - yarn build passes

  ⛔ STOP - Generate progress report, wait for approval

  ---
  Milestone 3: Styling + Design Tokens

  Objective: Apply design system tokens to match Figma design for all views

  Tasks:
  1. Apply color tokens from design system glossary
  2. Typography: font sizes, weights, line heights from Figma
  3. Spacing: margins, paddings, gaps per Figma node properties
  4. Shadows, borders, rounded corners per Figma styles
  5. NextUI component variants (color, variant, size)
  6. Hover/focus states based on Figma component variants
  7. Style modal/drawer components per their respective Figma frames

  Deliverables:
  - Colors match design system glossary mapping
  - Typography matches Figma text styles
  - Spacing matches Figma auto-layout/spacing values
  - Component variants applied correctly
  - Modal/drawer styling matches respective Figma designs
  - yarn build passes

  ⛔ STOP - Generate progress report, wait for approval

  ---
  Milestone 4: Interactions + Modals

  Objective: Implement all interactive behaviors across all views

  Tasks:
  1. Modal/drawer open/close logic with correct triggers
  2. Form validation and submission (preserve existing logic)
  3. Loading states (skeletons, spinners)
  4. Error states and empty states
  5. Toast notifications if applicable
  6. Transitions/animations (NextUI defaults or per Figma)
  7. Inter-view navigation (main page ↔ modal flows)

  Deliverables:
  - All modals/drawers open from correct triggers
  - Forms validate and submit correctly
  - Loading states implemented
  - Error handling preserved/improved
  - Keyboard navigation (Escape closes modals, Tab order)
  - View transitions work correctly
  - yarn build passes

  ⛔ STOP - Generate progress report, wait for approval

  ---
  Milestone 5: Integration + Cleanup

  Objective: Final integration and code quality

  Tasks:
  1. Verify full user flow works end-to-end (all views, all modals)
  2. Remove unused imports/components from refactor
  3. Remove console.logs and debug code
  4. Ensure no TypeScript warnings
  5. Update mermaid diagram if flow changed
  6. Document any deviations from Figma in progress report

  Deliverables:
  - User flow preserved (per mermaid diagram)
  - All views match their respective Figma targets
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
  4. Figma reference links (table mapping views to URLs)
  5. Design token mapping table
  6. Component inventory table

  After plan creation, output: [PLAN_READY]
