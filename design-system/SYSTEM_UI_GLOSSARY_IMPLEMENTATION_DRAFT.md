# SYSTEM_UI_GLOSSARY — Executive Summary & Implementation Draft

> **Status:** Draft (session continuity doc)
> **Audience:** AI coding agents + maintainers
> **Primary Output Files (to be created next):**
>
> - `docs/design-system/SYSTEM_UI_GLOSSARY.md`
> - `docs/design-system/SYSTEM_UI_GLOSSARY_ref.md`
> - `docs/design-system/template/SYSTEM_UI_GLOSSARY_template.md`
> - `docs/design-system/template/SYSTEM_UI_GLOSSARY_ref_template.md`

## Executive Summary

This repo benefits from a token-efficient, agent-friendly “where to look first” map of the UI system.

The goal is to reduce exploratory searching and prevent duplicate / non-standard UI work by giving AI agents:

- A **feature → files index** (routes/screens, shared components, providers, services, types).
- A small set of **canonical patterns** (new screens, modals/dialogs, shared component edits, theming rules).
- **Blast-radius awareness** when touching shared components.
- **Documented exceptions** and **known gotchas** to prevent hallucinated fixes.

This is **not** intended to replace source-of-truth code or existing design docs; it is a curated set of pointers and recipes that accelerates work and reduces regressions.

## Scope

### In scope

- **User-facing production UI** patterns (primary focus).
- **Admin/dev-only UI patterns** (explicitly labeled “DEV/ADMIN”; may be lower rigor, but still mapped).
- **Framework-agnostic templates** so this system can be dropped into other repos (React/Vite/Next.js/etc.).

### Out of scope

- Full component documentation for every component.
- Enumerating every usage site (prefer searchable pointers + small targeted queries).
- Rewriting existing design-system docs; we link to them and align terminology.

## Existing Design-System Docs (to reference, not duplicate)

- `docs/design-system/STYLE_GUIDE.md`
- `docs/design-system/COLOR_TOKENS.md`
- `docs/design-system/COMPONENT_PATTERNS.md`
- `docs/design-system/PAGE_AUDIT.md`

## Implementation Plan

### 1) Add templates (framework-agnostic)

Create:

- `docs/design-system/template/SYSTEM_UI_GLOSSARY_template.md`
- `docs/design-system/template/SYSTEM_UI_GLOSSARY_ref_template.md`

Template design goals:

- Uses neutral terms: **Route Entry**, **Screen/Page**, **Layout Wrapper**, **Modal Pattern**, **Data Layer**, **Shared UI**, **Types**.
- Includes a short **Framework Bindings** section (e.g., Expo Router vs Next App Router).
- Minimizes tokens by preferring **tables + bullet rules**.

### 2) Create Coinsher instance glossary

Create `docs/design-system/SYSTEM_UI_GLOSSARY.md` using the template and filling it with Coinsher-specific pointers.

Planned sections:

1. **Contract (Agent Rules)**

   - “Use these patterns; if missing, ask.”
   - “Prefer existing shared components.”
   - “When touching shared components, do blast-radius checks.”

2. **Fast Map (Feature → Files Index)**

   - Top-level features (Auth, Navigation Tabs, Balances, P2P, Merchant, KYC, etc.)
   - Each feature entry lists:
     - **Primary screens/routes** (`app/...`)
     - **Entry points / navigation origins**
     - **Data providers/hooks** (`providers/...`)
     - **Services** (`services/...`)
     - **Types** (`types/...`)
     - **Shared UI** dependencies (selective)
     - **Notes/gotchas** (route aliases, dev-only, etc.)

3. **Canonical Recipes (authoritative defaults)**

   - Add new screen (where to place files, wrappers to use)
   - Add modal/dialog (default to `components/common/Dialog.tsx`; custom allowed only with documentation)
   - Edit existing shared component safely (blast-radius checklist)
   - Theming rules (Tailwind semantic tokens + `dark:`; `Colors` + `useColorScheme` for prop colors)

4. **Shared Component Registry (blast radius)**

   - `components/common/*` high-impact components: Dialog, Alert, Tabs, Input, Button, etc.
   - For each: purpose + “danger areas” + where it’s used (via pointers or common call sites)

5. **Known Gotchas / Exceptions**
   - Record any mismatches between doc and code behavior.
   - Example known gotcha already identified: `components/common/Themed.tsx` behavior may not match intended `lightColor/darkColor` semantics.

### 3) Create maintenance + usage doc

Create `docs/design-system/SYSTEM_UI_GLOSSARY_ref.md` (Coinsher-specific) based on the template.

Planned content:

- **How to use** (copy/paste blocks you can drop into a new agent session).
- **Example prompts** (e.g., “Update P2P merchant dashboard to include X”).
- **How to update without drift**:
  - When adding a new screen/feature/service/provider/component, update the matching glossary entry.
  - When deviating from canonical patterns (custom modal, custom theming), document the exception and rationale.
- **Drift checks** (lightweight):
  - Confirm new routes are in glossary.
  - Confirm new shared UI component added to registry.
  - Confirm new exceptions added to allowlist.

## Acceptance Criteria

- A fresh agent can answer “where do I implement X?” by reading only `SYSTEM_UI_GLOSSARY.md`.
- Adding a new task prompt (e.g., “update p2p merchant dashboard…”) leads directly to correct file(s) with minimal repo-wide searching.
- The glossary includes explicit “default patterns” and a clear rule for when custom solutions are acceptable.
- Templates are usable in other repos/frameworks with minimal edits.

## Notes / Risks

- Avoid documenting patterns that are contradicted by real implementation.
- Keep the glossary small; link to existing docs for details.
- Prefer pointers like “start here” + minimal search queries rather than listing hundreds of files.
