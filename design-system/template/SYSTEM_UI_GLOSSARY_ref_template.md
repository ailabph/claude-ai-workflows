# SYSTEM_UI_GLOSSARY_ref (TEMPLATE)

> Companion template for `SYSTEM_UI_GLOSSARY.md`.
> Copy to `docs/design-system/SYSTEM_UI_GLOSSARY_ref.md` and fill in repo-specific prompts and drift checks.

---

## 1) How to Use (Session Preamble)

```
Use docs/design-system/SYSTEM_UI_GLOSSARY.md as your primary "where to look first" map.
- Identify likely routes/screens/services/components from the glossary.
- Confirm with small targeted searches.
- Prefer shared components.
- Document custom patterns/exceptions.
```

---

## 2) Kickstarter Prompts (Copy/Paste)

### A) Default UI Task

```
Read docs/design-system/SYSTEM_UI_GLOSSARY.md and follow it as your primary “where to look first” map.
Then implement: <describe UI change>.
Constraints:
- Prefer existing shared components.
- Use tokenized theming + dark mode rules.
- Use targeted searches only to confirm duplicates.
Output:
- List the exact files you will modify before editing.
```

### B) Shared Component Change (Blast Radius)

```
Read docs/design-system/SYSTEM_UI_GLOSSARY.md.
Task: change shared UI behavior in <shared component>.
Before editing:
- Identify blast radius using targeted searches.
After editing:
- Provide a short verification checklist.
```

### C) Add or Modify a Modal

```
Read docs/design-system/SYSTEM_UI_GLOSSARY.md.
Task: add a modal to <screen>.
Rules:
- Default to the repo’s standard modal component/pattern.
- Only introduce a custom modal if platform/client constraints require it.
- If custom is required, document the exception.
```

### D) Add a New Screen / Route

```
Read docs/design-system/SYSTEM_UI_GLOSSARY.md.
Task: add a new screen/page for <feature>.
Rules:
- Place it under the correct route group.
- Use existing layouts/providers.
- Add it to SYSTEM_UI_GLOSSARY.md Fast Map.
```

---

## 3) Doc Maintenance Prompt (End-of-Session)

```
You just completed a long UI coding session.
Task: update docs/design-system/SYSTEM_UI_GLOSSARY.md so future work requires less exploratory searching.

Input:
- Provide key files changed/added.
- Provide a short summary of what was implemented.

Update rules:
- Update “Fast Map — Feature → Files” if screens/routes/providers/services changed.
- Update “Shared UI Registry (Blast Radius)” if shared components changed.
- Add to “Exceptions (Allowlist)” if a non-standard UI pattern was required.
- Add to “Known Gotchas” for doc-vs-code mismatches.

Keep it token-efficient: small edits, pointers, and 1–2 targeted searches.
Output: list exactly what changed in SYSTEM_UI_GLOSSARY.md.
```

---

## 4) Example Prompts

- “Update <feature> to include <X>.”

  - Start: <primary screen path>
  - Check: <entry points>
  - Data: <services/types/providers>

- “Add a new modal to <screen>.”
  - Default: <modal component path>

---

## 5) Maintenance Rules

Update the glossary when:

- new route/screen added or renamed
- new shared UI component is introduced
- new canonical pattern becomes standard
- new exception is introduced

---

## 6) Drift Checks (Pre-PR)

- New route? Added to Fast Map.
- Shared component changed? Blast radius reviewed.
- New modal pattern? Uses default or documented exception.
- Theming changes? Token + dark-mode rules followed.

---

## 7) Bootstrapping Prompt (Generate from Templates)

```
1) Read docs/design-system/template/SYSTEM_UI_GLOSSARY_template.md and fill it for this repo.
2) Read docs/design-system/template/SYSTEM_UI_GLOSSARY_ref_template.md and fill it for this repo.
3) Keep token-efficient: tables + short rules.
4) Prefer pointers + targeted searches over listing every file.
5) Mark DEV/ADMIN separately.
```
