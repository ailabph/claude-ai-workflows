# [PROJECT_NAME] Color Tokens Reference

> Complete reference of all semantic color tokens with their light and dark mode values.

## Table of Contents

- [Background Colors](#background-colors)
- [Text Colors](#text-colors)
- [Border Colors](#border-colors)
- [Card Gradients](#card-gradients)
- [Brand Colors](#brand-colors)
- [Status Colors](#status-colors)
- [Navigation Colors](#navigation-colors)
- [Asset Colors](#asset-colors)
- [Logo Colors](#logo-colors)
- [Framework Secondary Colors](#framework-secondary-colors)

---

## Background Colors

### Tailwind Classes: `bg-surface-*`

| Token | Tailwind Class | Light Mode | Dark Mode |
|-------|----------------|------------|-----------|
| `--bg-primary` | `bg-surface-primary` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--bg-secondary` | `bg-surface-secondary` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--bg-card` | `bg-surface-card` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--bg-card-solid` | `bg-surface-card-solid` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--bg-header` | `bg-surface-header` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--bg-navbar` | `bg-surface-navbar` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--bg-dropdown` | `bg-surface-dropdown` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--bg-hover` | `bg-surface-hover` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--bg-toast` | `bg-surface-toast` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--bg-action-button` | `bg-surface-action-button` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |

### Usage Examples

```tsx
// Page background
<main className="bg-surface-primary">

// Card with solid background
<div className="bg-surface-card-solid rounded-xl p-6">

// Card with semi-transparent background
<div className="bg-surface-card rounded-xl p-6">

// Hover state
<button className="hover:bg-surface-hover">
```

---

## Text Colors

### Tailwind Classes: `text-content-*`

| Token | Tailwind Class | Light Mode | Dark Mode |
|-------|----------------|------------|-----------|
| `--text-primary` | `text-content-primary` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--text-secondary` | `text-content-secondary` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--text-muted` | `text-content-muted` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--text-on-primary` | `text-content-on-primary` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |

### Usage Examples

```tsx
// Primary headings
<h1 className="text-content-primary">Title</h1>

// Secondary text / descriptions
<p className="text-content-secondary">Description text</p>

// Very muted text
<span className="text-content-muted">Hint text</span>
```

---

## Border Colors

### Tailwind Classes: `border-stroke-*`

| Token | Tailwind Class | Light Mode | Dark Mode |
|-------|----------------|------------|-----------|
| `--border-default` | `border-stroke` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--border-light` | `border-stroke-light` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--border-header` | `border-stroke-header` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--border-accent` | `border-stroke-accent` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--border-subtle` | `border-stroke-subtle` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |

### Usage Examples

```tsx
// Default card border
<div className="border border-stroke rounded-xl">

// Table row borders (lighter)
<tr className="border-b border-stroke-light">

// Accent border (brand tint)
<div className="border border-stroke-accent">
```

---

## Card Gradients

### CSS Variables (use with inline styles)

| Token | Light Mode | Dark Mode |
|-------|------------|-----------|
| `--card-gradient-start` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--card-gradient-mid` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--card-gradient-end` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--card-inner-highlight` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--card-stat-bg` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--card-stat-border` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--card-shadow` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--card-border-radius` | `[VALUE]` | `[VALUE]` |

### Usage Examples

```tsx
// Dashboard-style card with gradient
const cardStyle = {
  background: "linear-gradient(135deg, var(--card-gradient-start) 0%, var(--card-gradient-mid) 50%, var(--card-gradient-end) 100%)",
  boxShadow: "var(--card-shadow)",
  border: "1px solid var(--border-default)",
  borderRadius: "var(--card-border-radius)"
};

<div style={cardStyle} className="p-6">
  Card content
</div>
```

---

## Brand Colors

### Tailwind Classes: `text-primary`, `bg-primary`, `text-brand-*`, `bg-brand-*`

| Token | Tailwind Class | Value | Notes |
|-------|----------------|-------|-------|
| `--primary` | `text-primary` / `bg-primary` | `[VALUE]` | Main brand color |
| `--primary-dark` | `text-brand-dark` / `bg-brand-dark` | `[VALUE]` | Darker variant |
| `--primary-glow` | `bg-brand-glow` | `[VALUE]` | Glow effect |
| `--primary-underline` | - | `[VALUE]` | Underline accent |
| `--primary-gradient-start` | - | `[VALUE]` | Gradient start |
| `--primary-gradient-end` | - | `[VALUE]` | Gradient end |

### Usage Examples

```tsx
// Brand text
<span className="text-primary">Highlighted text</span>

// Primary button with gradient
<button
  style={{
    background: "linear-gradient(to right, var(--primary-gradient-start), var(--primary-gradient-end))"
  }}
>
  Submit
</button>

// Light brand background
<div className="bg-primary/10">
```

---

## Status Colors

### Tailwind Classes: `text-status-*`, `bg-status-*`

| Token | Tailwind Class | Value | Use Case |
|-------|----------------|-------|----------|
| `--success` | `text-status-success` / `bg-status-success` | `[VALUE]` | Success messages, positive values |
| `--success-light` | `bg-status-success-light` | `[VALUE]` | Success backgrounds |
| `--error` | `text-status-error` / `bg-status-error` | `[VALUE]` | Error messages, negative values |
| `--error-light` | `bg-status-error-light` | `[VALUE]` | Error backgrounds |
| `--warning` | `text-status-warning` / `bg-status-warning` | `[VALUE]` | Warning messages |
| `--info` | `text-status-info` / `bg-status-info` | `[VALUE]` | Info messages |

### Usage Examples

```tsx
// Success text
<span className="text-status-success">+$1,234.56</span>

// Success badge
<span className="bg-status-success-light text-status-success px-2 py-1 rounded-full">
  Completed
</span>

// Error message
<p className="text-status-error">Transaction failed</p>

// Info icon
<LuClock className="text-status-info" />
```

---

## Navigation Colors

### Tailwind Classes: `text-nav-*`

| Token | Tailwind Class | Light Mode | Dark Mode |
|-------|----------------|------------|-----------|
| `--nav-icon-active` | `text-nav-active` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--nav-icon-inactive` | `text-nav-inactive` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |

### Usage Examples

```tsx
<NavItem className={isActive ? "text-nav-active" : "text-nav-inactive"}>
```

---

## Asset Colors

### Tailwind Classes: `text-asset-*`, `bg-asset-*`

| Token | Tailwind Class | Value |
|-------|----------------|-------|
| `--asset-[NAME]` | `text-asset-[NAME]` / `bg-asset-[NAME]` | `[VALUE]` |
| `--asset-default` | `text-asset` / `bg-asset` | `[VALUE]` |

### Usage Examples

```tsx
// Asset color indicator
<div
  className="w-3 h-3 rounded-full"
  style={{ backgroundColor: `var(--asset-${symbol.toLowerCase()})` }}
/>

// Or using Tailwind (when asset is known)
<span className="text-asset-[NAME]">[NAME]</span>
```

---

## Logo Colors

### Tailwind Classes: `text-logo-*`, `bg-logo-*`

| Token | Tailwind Class | Light Mode | Dark Mode |
|-------|----------------|------------|-----------|
| `--logo-primary` | `text-logo-primary` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--logo-secondary` | `text-logo-secondary` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |
| `--logo-bg` | `bg-logo-bg` | `[LIGHT_VALUE]` | `[DARK_VALUE]` |

---

## Framework Secondary Colors

### Tailwind Classes: `text-secondary-*`

These are defined in the UI framework theme plugin:

| Token | Light Mode | Dark Mode | Use Case |
|-------|------------|-----------|----------|
| `secondary-300` | `[LIGHT_VALUE]` | `[DARK_VALUE]` | Light secondary |
| `secondary-500` | `[LIGHT_VALUE]` | `[DARK_VALUE]` | Default secondary |
| `secondary-600` | `[LIGHT_VALUE]` | `[DARK_VALUE]` | Darker secondary |

> **Warning**: Framework secondary colors may render unexpectedly in dark mode. For reliable secondary text color in both modes, **use `text-content-secondary` instead**.

### Usage Examples

```tsx
// RECOMMENDED: Use text-content-secondary for secondary text
<p className="text-content-secondary">Description text</p>

// Table header text
<th className="text-content-secondary text-sm font-medium">Column</th>

// AVOID: text-secondary-500 may appear incorrectly in dark mode
// <p className="text-secondary-500">Description text</p>
```

---

## Migration Cheatsheet

| Hardcoded Value | Replace With |
|-----------------|--------------|
| `[HEX_VALUE]` | `[SEMANTIC_TOKEN]` |
| `rgba(...)` | `[SEMANTIC_TOKEN]` |
| `text-white` (in dark theme) | `text-content-primary` |
| `text-green-500` | `text-status-success` |
| `bg-green-500/10` | `bg-status-success-light` |
| `text-red-500` | `text-status-error` |
| `bg-red-500/10` | `bg-status-error-light` |
