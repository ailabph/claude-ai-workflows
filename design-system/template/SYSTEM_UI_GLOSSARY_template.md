# SYSTEM_UI_GLOSSARY (TEMPLATE)

> **Purpose:** Token-efficient “where to look first” map for AI agents working on UI.
> **This file is a template.** Copy it to `docs/design-system/SYSTEM_UI_GLOSSARY.md` and fill in repo-specific details.

---

## 0) Agent Contract (Defaults)

- Use this glossary to reduce exploratory searching.
- Verify with targeted searches (to catch duplicates).
- Prefer shared components and standard patterns.
- If a task requires a new pattern, document it in **Exceptions** and update the reference docs.

---

## 1) Framework Bindings (Fill In)

| Concept         | This Repo Uses                                        | Notes                     |
| --------------- | ----------------------------------------------------- | ------------------------- |
| Routing         | <Expo Router / Next App Router / React Router / etc.> | <file-based? code-based?> |
| Layout wrappers | <where?>                                              | <providers, app root>     |
| Modal system    | <Dialog/Sheet/etc.>                                   | <default vs custom>       |
| Data fetching   | <React Query / SWR / Redux>                           | <where configured>        |
| Styling         | <Tailwind / CSS Modules / Styled Components>          | <tokens location>         |

---

## 2) Fast Map — Feature → Files

> For each feature: list primary entrypoints and where data/UI live.

### <FEATURE NAME> (PRODUCTION)

- **Primary routes/screens:**
  - `<path>`
- **Entry points/navigation from:**
  - `<path>`
- **Data layer:**
  - Providers/hooks: `<path>`
  - Services/clients: `<path>`
  - Types/schemas: `<path>`
- **Shared UI used:**
  - `<path>`
- **Targeted searches (optional):**
  - `rg "<pattern>" -n`

### <FEATURE NAME> (DEV/ADMIN)

- Same structure, explicitly labeled.

---

## 3) Shared UI Registry (Blast Radius)

> List the shared components most likely to cause cascading UI changes.

| Component | Path   | Used For | Risk | How to Find Usages |
| --------- | ------ | -------- | ---- | ------------------ |
| <Dialog>  | <path> | <modals> | High | `rg "<Dialog" -n`  |

---

## 4) Canonical Recipes

Keep recipes short and copy/paste-friendly.

- **Add new screen/page** (routing + layout wrapper)
- **Add modal** (default modal component)
- **Edit shared component safely** (blast-radius checklist)
- **Theming/styling rules** (tokens, dark mode)

---

## 5) Known Gotchas

- List mismatches between docs and reality.
- List route aliases.
- List legacy patterns to avoid.

---

## 6) Exceptions (Allowlist)

| File/Area | Exception       | Reason | Replacement/Standard |
| --------- | --------------- | ------ | -------------------- |
| <path>    | <what deviates> | <why>  | <standard pattern>   |
