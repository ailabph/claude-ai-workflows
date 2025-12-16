# [PROJECT_NAME] Design System Style Guide

> **Last Updated:** [Month Year]
> **Maintainers:** [Team Name]

## Overview

This document serves as the central reference for [PROJECT_NAME]'s design system. All UI development should follow these guidelines to ensure consistency across the application.

## Quick Reference

| Need | Use |
|------|-----|
| Primary text | `text-content-primary` |
| Secondary/muted text | `text-content-secondary` |
| Card backgrounds | `bg-surface-card` or `bg-surface-card-solid` |
| Page backgrounds | `bg-surface-primary` |
| Default borders | `border-stroke` |
| Success states | `text-status-success` / `bg-status-success-light` |
| Error states | `text-status-error` / `bg-status-error-light` |
| Brand/accent color | `text-primary` / `bg-primary` |

## File Structure

```
docs/design-system/
├── STYLE_GUIDE.md          # This file - main overview
├── COLOR_TOKENS.md         # Complete token reference with light/dark values
├── PAGE_AUDIT.md           # Per-page compliance tracking
└── COMPONENT_PATTERNS.md   # Reusable component styling patterns
```

## Source Files

| File | Purpose |
|------|---------|
| `tailwind.config.ts` | Tailwind theme extensions and semantic token definitions |
| `src/app/globals.css` | CSS custom properties for light/dark themes |
| `src/lib/utils.ts` | `cn()` utility for conditional class merging |

## Core Principles

### 1. Never Use Hardcoded Colors

```tsx
// BAD - hardcoded hex values
<p className="text-[#667185]">Text</p>
<div className="bg-[#09090b] border-[#1d1d20]">Card</div>

// GOOD - semantic tokens
<p className="text-content-secondary">Text</p>
<div className="bg-surface-primary border-stroke">Card</div>
```

### 2. Use Semantic Tokens Over Raw Values

Semantic tokens adapt to light/dark mode automatically:

```tsx
// These adapt to theme changes automatically
<h1 className="text-content-primary">Title</h1>        // Adapts to theme
<p className="text-content-secondary">Subtitle</p>     // Adapts to theme
<div className="bg-surface-card">Card</div>            // Adapts to theme
```

### 3. Use CSS Variables for Gradients and Complex Styles

For gradients or styles that can't be expressed with Tailwind classes:

```tsx
// Use inline styles with CSS variables
<button
  style={{
    background: "linear-gradient(to right, var(--primary-gradient-start), var(--primary-gradient-end))"
  }}
>
  Submit
</button>

// Card with gradient (dashboard pattern)
const cardStyle = {
  background: "linear-gradient(135deg, var(--card-gradient-start) 0%, var(--card-gradient-mid) 50%, var(--card-gradient-end) 100%)",
  boxShadow: "var(--card-shadow)",
  border: "1px solid var(--border-default)",
  borderRadius: "24px"
};
```

### 4. Use `cn()` for Conditional Classes

```tsx
import { cn } from "@/lib/utils";

<div className={cn(
  "rounded-xl border border-stroke",
  isActive && "border-primary",
  isDisabled && "opacity-50"
)}>
```

## Token Categories

### Background Tokens (`bg-surface-*`)

| Token | Use Case |
|-------|----------|
| `bg-surface-primary` | Page backgrounds |
| `bg-surface-secondary` | Section backgrounds |
| `bg-surface-card` | Card backgrounds (semi-transparent) |
| `bg-surface-card-solid` | Card backgrounds (solid) |
| `bg-surface-hover` | Hover states |
| `bg-surface-dropdown` | Dropdown menus |

### Text Tokens (`text-content-*`)

| Token | Use Case |
|-------|----------|
| `text-content-primary` | Primary headings, important text |
| `text-content-secondary` | Secondary text, descriptions |
| `text-content-muted` | Very subtle text, hints |

### Border Tokens (`border-stroke-*`)

| Token | Use Case |
|-------|----------|
| `border-stroke` | Default borders |
| `border-stroke-light` | Subtle borders (table rows) |
| `border-stroke-accent` | Accent borders |
| `border-stroke-subtle` | Very subtle borders |

### Status Tokens (`text-status-*` / `bg-status-*`)

| Token | Use Case |
|-------|----------|
| `text-status-success` | Success text (green) |
| `bg-status-success-light` | Success background |
| `text-status-error` | Error text (red) |
| `bg-status-error-light` | Error background |
| `text-status-info` | Info text (blue) |

### Brand Tokens

| Token | Use Case |
|-------|----------|
| `text-primary` | Brand-colored text |
| `bg-primary` | Brand-colored backgrounds |
| `bg-primary/10` | Light brand background |

## Common Patterns

### Cards

```tsx
// Simple card
<div className="rounded-3xl border border-stroke bg-surface-card-solid p-6">
  <h3 className="text-lg font-semibold text-content-primary">Title</h3>
  <p className="text-content-secondary text-sm">Description</p>
</div>

// Card with gradient (dashboard style)
<div style={cardStyle} className="p-6">
  Content
</div>
```

### Buttons

```tsx
// Primary button with gradient
<Button
  className="rounded-2xl font-bold h-14"
  style={{ background: "linear-gradient(to right, var(--primary-gradient-start), var(--primary-gradient-end))" }}
>
  Submit
</Button>

// Secondary button
<Button className="bg-surface-card-solid border-stroke text-content-primary hover:bg-surface-hover">
  Cancel
</Button>
```

### Form Inputs

```tsx
<div className="rounded-xl py-3 px-3 bg-surface-primary border border-stroke">
  <p className="text-content-primary">Selected value</p>
  <span className="text-content-secondary">Placeholder</span>
</div>
```

### Tables

```tsx
<table className="w-full">
  <thead>
    <tr className="border-b border-stroke">
      <th className="text-content-secondary text-sm font-medium">Header</th>
    </tr>
  </thead>
  <tbody>
    <tr className="border-b border-stroke-light hover:bg-surface-card">
      <td className="text-content-primary">Content</td>
    </tr>
  </tbody>
</table>
```

## Dark Mode Utilities

### Icon Inversion for Dark Mode

For icons with dark strokes that need to be visible on dark backgrounds:

```tsx
// Apply icon-dark-mode-invert class - applies filter: invert(1) brightness(2) in dark mode
<Image
  src={"/images/icon.svg"}
  alt="Icon"
  className="w-8 h-8 icon-dark-mode-invert"
/>
```

### Conditional Asset Rendering

For assets that need different versions in light/dark mode:

```tsx
// Pattern: Use dark:hidden and hidden dark:block
<div className="dark:hidden">
  <LightModeAsset />
</div>
<div className="hidden dark:block">
  <DarkModeAsset />
</div>
```

See [COMPONENT_PATTERNS.md](./COMPONENT_PATTERNS.md#dark-mode-assets) for complete examples.

## Related Documentation

- [COLOR_TOKENS.md](./COLOR_TOKENS.md) - Complete token reference with hex values
- [PAGE_AUDIT.md](./PAGE_AUDIT.md) - Page compliance tracking
- [COMPONENT_PATTERNS.md](./COMPONENT_PATTERNS.md) - Reusable component patterns

## Migration Guide

When converting a page to use semantic tokens:

1. **Search for hardcoded colors**: `#[0-9a-fA-F]{3,6}` or `rgba?(`
2. **Map to semantic tokens** using the tables in [COLOR_TOKENS.md](./COLOR_TOKENS.md)
3. **Test both themes** to ensure colors adapt correctly
4. **Update PAGE_AUDIT.md** with the page's new compliance status
