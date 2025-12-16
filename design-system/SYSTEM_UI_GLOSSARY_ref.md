# SYSTEM_UI_GLOSSARY_ref

> Companion doc for `SYSTEM_UI_GLOSSARY.md`.
> **Purpose:** How to use the glossary in agent sessions + how to maintain it without drift.

---

## 1) How to Use (Recommended Session Preamble)

Paste this at the start of an agent task:

```
Use docs/design-system/SYSTEM_UI_GLOSSARY.md as your primary "where to look first" map.
- Start by identifying the most likely screens/routes/services/providers/components.
- Then run small targeted searches to confirm there are no duplicates.
- Prefer components/common patterns unless impossible.
- If you must introduce a custom UI pattern, document it (see Exceptions section).
```

### Example Task Prompts (Coinsher)

- “Update the P2P merchant dashboard to include <X>.”

  - Start: `app/(auth)/(developer)/p2p/merchant-dashboard.tsx`
  - Verify entry points: `app/(auth)/settings.tsx`, `components/p2p/P2pManageButtons.tsx`
  - Verify data/service: `services/merchantP2PService.ts`, `types/p2p.*`

- “Add a confirmation modal to <screen>.”

  - Default: use `components/common/Dialog.tsx` (see `docs/design-system/COMPONENT_PATTERNS.md` “Dialogs”).

- “Add a new settings row / toggle.”
  - Start: `app/(auth)/settings.tsx`
  - Theme: use `useColorScheme()` and deterministic handlers (`onCheckedChange={(v) => void setTheme(v)}` style).

---

## 2) Kickstarter Prompts (Copy/Paste)

Use these at the start of a new agent session to reduce exploratory work.

### A) Default UI Task

```
Read docs/design-system/SYSTEM_UI_GLOSSARY.md and follow it as your primary “where to look first” map.
Then implement: <describe UI change>.
Constraints:
- Prefer existing shared components (components/common/*).
- Use semantic tokens + dark: variants for all color classes.
- Use targeted searches only to confirm duplicates (no broad repo scanning).
Output:
- List the exact files you will modify before editing.
```

### B) Shared Component Change (Blast Radius)

```
Read docs/design-system/SYSTEM_UI_GLOSSARY.md.
Task: change shared UI behavior in <components/common/X>.
Before editing:
- Identify blast radius (which screens/features rely on it) using targeted searches.
- List the high-risk behavior changes.
After editing:
- Provide a short verification checklist of screens/flows to sanity-check.
```

### C) Add or Modify a Modal

```
Read:
- docs/design-system/SYSTEM_UI_GLOSSARY.md
- docs/design-system/COMPONENT_PATTERNS.md (Dialogs)
Task: add a modal to <screen>.
Rules:
- Default to components/common/Dialog.tsx.
- Only introduce a custom modal if platform/client constraints require it.
- If custom is required, document the exception in docs/design-system/SYSTEM_UI_GLOSSARY.md (Exceptions).
```

### D) Add a New Screen / Route

```
Read docs/design-system/SYSTEM_UI_GLOSSARY.md.
Task: add a new screen for <feature>.
Rules:
- Place it under the correct app/ route group.
- Use existing layouts/providers.
- Add it to SYSTEM_UI_GLOSSARY.md Fast Map under the correct feature.
- Add any new shared UI components to the Shared UI Registry section.
```

### E) “Update P2P Merchant Dashboard …” (Coinsher-specific)

```
Read docs/design-system/SYSTEM_UI_GLOSSARY.md.
Task: update the P2P merchant dashboard to include <X>.
Start here:
- app/(auth)/(developer)/p2p/merchant-dashboard.tsx
Also check:
- app/(auth)/settings.tsx (entry point)
- components/p2p/P2pManageButtons.tsx (entry point)
- services/merchantP2PService.ts (data)
Then:
- Run a targeted search to confirm there is no duplicate dashboard screen.
```

---

## 3) Doc Maintenance Prompt (End-of-Session)

Use this at the end of a long coding session (e.g., 3–4 hours) to prevent drift.

```
You just completed a long UI coding session.
Task: update docs/design-system/SYSTEM_UI_GLOSSARY.md so future work requires less exploratory searching.

Input:
- Provide a bullet list of the key files changed/added in this session.
- Provide a 1–2 sentence summary of what was implemented.

Update rules:
1) If new screens/routes were added or moved, update the correct Feature entry under “Fast Map — Feature → Files”.
2) If new providers/services/types were introduced or became the primary entrypoint, add them under that Feature.
3) If you edited/added a shared UI component (components/common/*), update “Shared UI Registry (Blast Radius)” with:
   - the component path
   - what changed
   - one targeted search query to find usages
4) If a custom modal/pattern was introduced, add an entry under “Exceptions (Allowlist)” with the reason and the standard it replaces.
5) If you discovered a new gotcha (doc vs code mismatch), add it under “Known Gotchas”.

Keep the glossary token-efficient:
- Prefer editing/adding 3–10 lines.
- Do not add long explanations.
- Prefer pointers and 1–2 targeted searches over listing every usage site.

Output:
- List exactly what you added/changed in SYSTEM_UI_GLOSSARY.md.
```

---

## 4) Maintenance Rules (Prevent Drift)

### When you MUST update `SYSTEM_UI_GLOSSARY.md`

- New top-level feature or major flow is introduced.
- New shared UI component is added under `components/common/`.
- A screen is moved/renamed (route path changes).
- A new canonical pattern is adopted (modal, screen wrapper, theming approach).

### How to update (minimal, token-efficient)

- Add/adjust a single entry under **Fast Map — Feature → Files**.
- If shared component: add it under **Shared UI Registry (Blast Radius)**.
- If it affects styling/theming: link to the relevant section in `STYLE_GUIDE.md` and add a short note under **Gotchas** if needed.

---

## 5) Documenting Exceptions (When Custom UI is Acceptable)

Custom UI patterns are acceptable only when:

- platform constraints require it (native picker, WebView constraints, etc.)
- a shared component cannot meet requirements without unacceptable complexity

When you add an exception:

1. Add a short row under `SYSTEM_UI_GLOSSARY.md` → **Exceptions (Allowlist)**.
2. Include: file path, reason, and what standard pattern it deviates from.
3. Prefer to also add a short note in `PAGE_AUDIT.md` if it relates to design tokens.

---

## 6) Lightweight Drift Checks (Before Finalizing a PR)

- New screen added? Ensure it’s indexed in **Fast Map**.
- Shared component changed? Ensure blast-radius section is accurate.
- New modal pattern? Confirm it uses `Dialog` or document why not.
- Any new colors introduced? Confirm semantic tokens + `dark:` coverage.

---

## 7) Framework-Agnostic Bootstrapping (Template Workflow)

This repo includes templates intended for other UI frameworks.

### Goal

Given a new repo (React/Vite/Next.js/etc.), generate:

- `SYSTEM_UI_GLOSSARY.md` (instance)
- `SYSTEM_UI_GLOSSARY_ref.md` (instance)

### Prompt to Generate a New Glossary From Templates

Use a prompt like:

```
You are setting up a UI glossary.
1) Read docs/design-system/template/SYSTEM_UI_GLOSSARY_template.md and fill it in for this repo.
2) Read docs/design-system/template/SYSTEM_UI_GLOSSARY_ref_template.md and fill it in for this repo.
3) Keep it token-efficient: prefer tables + short rules.
4) Do not list every file; instead list primary entrypoints + suggested targeted searches.
5) Mark DEV/ADMIN UI separately.
6) Add 3-5 canonical recipes matching this repo’s UI stack (routing, modals, theming).
```

---

## 8) Known Repo-Specific Notes (Coinsher)

- `components/common/Themed.tsx` behavior may not match intended `lightColor/darkColor` semantics. Prefer explicit Tailwind background classes until this is corrected.
- Expo Router route groups: `(public)`, `(auth)`, `(common)`, `(developer)`.
- Route groups do not appear in URL paths (e.g., `(auth)/(developer)/p2p/merchant-dashboard.tsx` → `/p2p/merchant-dashboard`).
