# Page Compliance Audit

> Tracks which pages follow the design system and which need updates.

## Status Legend

| Status | Meaning |
|--------|---------|
| ✅ Compliant | Page uses semantic tokens correctly |
| ⚠️ Partial | Some hardcoded colors remain |
| ❌ Needs Work | Many hardcoded colors, needs migration |
| 🔍 Not Audited | Page hasn't been reviewed yet |

---

## Private Pages ([TOTAL] total)

### [SECTION_NAME] ([COUNT])

| Page | Path | Status | Notes | Last Audited |
|------|------|--------|-------|--------------|
| [Page Name] | `/path` | 🔍 Not Audited | - | - |
| [Page Name] | `/path` | ✅ Compliant | [Notes about compliance] | [Month Year] |
| [Page Name] | `/path` | ⚠️ Partial | [Notes about issues] | [Month Year] |
| [Page Name] | `/path` | ❌ Needs Work | [Notes about issues] | [Month Year] |

### [SECTION_NAME] ([COUNT])

| Page | Path | Status | Notes | Last Audited |
|------|------|--------|-------|--------------|
| [Page Name] | `/path` | 🔍 Not Audited | - | - |

---

## Public Pages ([TOTAL] total)

### [SECTION_NAME] ([COUNT])

| Page | Path | Status | Notes | Last Audited |
|------|------|--------|-------|--------------|
| [Page Name] | `/path` | 🔍 Not Audited | - | - |

---

## Summary Statistics

| Status | Count | Percentage |
|--------|-------|------------|
| ✅ Compliant | [COUNT] | [PERCENT]% |
| ⚠️ Partial | [COUNT] | [PERCENT]% |
| ❌ Needs Work | [COUNT] | [PERCENT]% |
| 🔍 Not Audited | [COUNT] | [PERCENT]% |
| **Total** | **[TOTAL]** | **100%** |

---

## How to Audit a Page

1. **Open the page file** (e.g., `src/app/(private)/[page]/page.tsx`)

2. **Search for hardcoded colors:**
   ```bash
   # In the file, search for these patterns:
   #[0-9a-fA-F]{3,6}     # Hex colors
   rgba?\(               # rgba/rgb values
   text-white            # May need text-content-primary
   text-gray-            # May need semantic token
   bg-gray-              # May need semantic token
   text-green-           # Should be text-status-success
   text-red-             # Should be text-status-error
   ```

3. **Map hardcoded values** to semantic tokens using [COLOR_TOKENS.md](./COLOR_TOKENS.md)

4. **Update the page** with semantic tokens

5. **Test both themes** (light and dark mode)

6. **Update this audit** with new status

---

## Audit History

| Date | Page | Action | By |
|------|------|--------|-----|
| [Month Year] | `/path` | [Description of changes] | [Author] |

---

## Priority Queue

Pages recommended for next audit (based on user traffic and visibility):

1. `/[high-traffic-page]` - [Reason]
2. `/[high-traffic-page]` - [Reason]
3. `/[public-page]` - [Reason]

### Minor Fixes Needed

| File | Issue | Fix |
|------|-------|-----|
| `src/components/[file].tsx` | [Issue description] | [Recommended fix] |
