# Component Patterns

> Reusable styling patterns extracted from compliant pages.

## Table of Contents

- [Cards](#cards)
- [Buttons](#buttons)
- [Form Inputs](#form-inputs)
- [Tables](#tables)
- [Status Badges](#status-badges)
- [Feature Cards](#feature-cards)
- [List Items](#list-items)
- [Headers](#headers)
- [Empty States](#empty-states)
- [Icons](#icons)
- [Dark Mode Assets](#dark-mode-assets)

---

## Cards

### Simple Card

Basic card with solid background:

```tsx
<div className="rounded-3xl border border-stroke bg-surface-card-solid p-6">
  <h3 className="text-lg font-semibold text-content-primary">Card Title</h3>
  <p className="text-content-secondary text-sm mt-1">Card description text</p>
  {/* Card content */}
</div>
```

### Gradient Card (Dashboard Style)

Premium card with gradient background and shadow:

```tsx
// Define the style object
const cardStyle = {
  background: "linear-gradient(135deg, var(--card-gradient-start) 0%, var(--card-gradient-mid) 50%, var(--card-gradient-end) 100%)",
  boxShadow: "var(--card-shadow)",
  border: "1px solid var(--border-default)",
  borderRadius: "24px"
};

// Usage
<div style={cardStyle} className="p-6 md:p-8 relative overflow-hidden">
  {/* Optional glow accent */}
  <div
    className="absolute top-0 right-0 w-64 h-64 opacity-20 pointer-events-none"
    style={{
      background: "radial-gradient(circle at top right, var(--primary-glow) 0%, transparent 70%)"
    }}
  />

  <div className="relative z-10">
    {/* Card content */}
  </div>
</div>
```

### Semi-transparent Card

For layered content:

```tsx
<div className="rounded-xl bg-surface-card border border-stroke-light p-4">
  {/* Card content */}
</div>
```

---

## Buttons

### Primary Button (Gradient)

Main CTA button with brand gradient:

```tsx
<Button
  variant="solid"
  color="primary"
  className="rounded-2xl font-bold h-14"
  style={{
    background: "linear-gradient(to right, var(--primary-gradient-start), var(--primary-gradient-end))"
  }}
  fullWidth
>
  Submit
</Button>
```

### Secondary Button

For secondary actions:

```tsx
<Button
  variant="faded"
  className="bg-surface-card-solid border-stroke text-content-primary rounded-xl h-10 px-5 text-sm font-medium hover:bg-surface-hover transition-colors"
>
  <LuIcon size={16} />
  <span>Button Text</span>
</Button>
```

### Mobile Button (Pill Style)

Compact button for mobile headers:

```tsx
<Button
  variant="faded"
  className="bg-surface-primary border-stroke text-content-primary rounded-full h-8 px-4 text-xs font-medium"
  size="sm"
>
  <LuPlus size={12} />
  <span>Add</span>
</Button>
```

### Action Button (Circle)

Circular action button (e.g., deposit, withdraw):

```tsx
<button className="flex flex-col items-center gap-2 group">
  <div
    className="w-14 h-14 rounded-full flex items-center justify-center shadow-lg transition-transform group-hover:scale-105"
    style={{
      background: "linear-gradient(135deg, var(--primary-gradient-start) 0%, var(--primary-gradient-end) 100%)"
    }}
  >
    <LuPlus size={24} className="text-white" />
  </div>
  <span className="text-xs font-medium text-content-secondary group-hover:text-content-primary transition-colors">
    Deposit
  </span>
</button>
```

### Ghost Action Button

Secondary circular action:

```tsx
<button className="flex flex-col items-center gap-2 group">
  <div className="w-14 h-14 rounded-full bg-surface-action-button hover:bg-surface-hover flex items-center justify-center transition-all group-hover:scale-105">
    <LuWallet size={20} className="text-content-secondary" />
  </div>
  <span className="text-xs font-medium text-content-secondary group-hover:text-content-primary transition-colors">
    Withdraw
  </span>
</button>
```

---

## Form Inputs

### Dropdown Trigger

Custom styled dropdown button:

```tsx
<div
  className="flex-shrink-0 w-[200px] rounded-xl py-3 cursor-pointer px-3 bg-surface-primary border border-stroke text-xs"
  onClick={onOpen}
>
  <div className="w-full flex justify-between items-center">
    {/* Left - Selected value */}
    <div className="flex items-center space-x-2">
      {selectedLogo && (
        <div className="w-6 h-6">
          <Image src={selectedLogo} alt={selectedValue} />
        </div>
      )}
      <p className="text-sm font-semibold text-content-primary">
        {selectedValue || "Select Option"}
      </p>
    </div>
    {/* Right - Chevron */}
    <span className="flex space-x-2 items-center font-normal text-content-secondary">
      <LuChevronDown size={16} />
    </span>
  </div>
</div>
```

### Input Card

Card containing form inputs (From/To pattern):

```tsx
<div className={cn(
  "relative w-full rounded-2xl border border-stroke bg-surface-card p-5 flex flex-col",
  hasError && "border-primary"
)}>
  <span className="text-content-secondary text-sm font-semibold mb-4">From</span>

  <div className="flex items-center justify-between gap-4">
    {/* Dropdown */}
    <DropdownTrigger />

    {/* Amount input */}
    <div className="flex-1 flex justify-end">
      <Input
        classNames={{
          input: "text-right text-2xl border-0 focus:ring-transparent",
          inputWrapper: "!border-0 shadow-none",
        }}
        placeholder="0"
        variant="bordered"
      />
    </div>
  </div>

  {/* Balance info */}
  <div className="flex flex-col gap-0.5 text-xs mt-3">
    <span className="text-content-secondary">
      Bal: <span className="text-content-primary font-medium">$0.00</span>
    </span>
    <span className="text-content-secondary">
      Max: <span className="text-status-success font-medium">100.00</span>
    </span>
  </div>
</div>
```

### Info Box

Subtle info display:

```tsx
<div className="flex items-center justify-between p-3 rounded-xl bg-surface-card border border-stroke">
  <span className="text-xs text-content-secondary">Label</span>
  <span className="text-sm text-content-primary font-medium">
    Value
  </span>
</div>
```

---

## Tables

### Standard Table

```tsx
<div className="overflow-x-auto">
  <table className="w-full">
    <thead>
      <tr className="border-b border-stroke">
        <th className="text-left py-3 px-4 text-content-secondary text-sm font-medium">Column</th>
        <th className="text-left py-3 px-4 text-content-secondary text-sm font-medium">Column</th>
        <th className="text-right py-3 px-4 text-content-secondary text-sm font-medium">Column</th>
      </tr>
    </thead>
    <tbody>
      {items.map((item, index) => (
        <tr
          key={index}
          className="border-b border-stroke-light hover:bg-surface-card transition-colors"
        >
          <td className="py-4 px-4 text-content-primary text-sm">{item.col1}</td>
          <td className="py-4 px-4 text-content-secondary text-sm">{item.col2}</td>
          <td className="py-4 px-4 text-right">
            <StatusBadge status={item.status} />
          </td>
        </tr>
      ))}
    </tbody>
  </table>
</div>
```

### Table with Icons

```tsx
<tr className="border-b border-stroke-light hover:bg-surface-card transition-colors">
  <td className="py-4 px-4">
    <div className="flex items-center gap-3">
      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
        <LuIcon size={14} className="text-primary" />
      </div>
      <span className="text-content-primary text-sm">{item.name}</span>
    </div>
  </td>
  {/* ... other columns */}
</tr>
```

---

## Status Badges

### Success Badge

```tsx
<span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-status-success-light text-status-success text-xs font-medium">
  <span className="w-1.5 h-1.5 rounded-full bg-status-success"></span>
  Completed
</span>
```

### Error Badge

```tsx
<span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-status-error-light text-status-error text-xs font-medium">
  <span className="w-1.5 h-1.5 rounded-full bg-status-error"></span>
  Failed
</span>
```

### Pending Badge

```tsx
<span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-surface-card text-content-secondary text-xs font-medium">
  <span className="w-1.5 h-1.5 rounded-full bg-content-secondary"></span>
  Pending
</span>
```

---

## Feature Cards

### Feature Item with Icon

For "Why use X?" sections:

```tsx
<div className="flex items-start gap-4">
  <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
    <LuZap className="text-primary" size={20} />
  </div>
  <div>
    <h4 className="text-content-primary font-medium mb-1">Feature Title</h4>
    <p className="text-content-secondary text-sm">Feature description text goes here</p>
  </div>
</div>
```

### Feature Item with Status Color

```tsx
// Success/Security themed
<div className="flex items-start gap-4">
  <div className="w-10 h-10 rounded-xl bg-status-success-light flex items-center justify-center flex-shrink-0">
    <LuShield className="text-status-success" size={20} />
  </div>
  <div>
    <h4 className="text-content-primary font-medium mb-1">Secure & Reliable</h4>
    <p className="text-content-secondary text-sm">Your data is protected</p>
  </div>
</div>

// Info themed
<div className="flex items-start gap-4">
  <div className="w-10 h-10 rounded-xl bg-status-info/10 flex items-center justify-center flex-shrink-0">
    <LuClock className="text-status-info" size={20} />
  </div>
  <div>
    <h4 className="text-content-primary font-medium mb-1">24/7 Available</h4>
    <p className="text-content-secondary text-sm">Access anytime, anywhere</p>
  </div>
</div>
```

---

## List Items

### Clickable List Item

For popular items, quick actions:

```tsx
<div className="flex items-center justify-between p-3 rounded-xl bg-surface-card border border-stroke-light hover:border-primary/50 cursor-pointer transition-all group">
  <div className="flex items-center gap-3">
    {/* Left content */}
    <div className="flex -space-x-2">
      <Image src={icon1} className="w-7 h-7 rounded-full border-2 border-surface-card-solid" />
      <Image src={icon2} className="w-7 h-7 rounded-full border-2 border-surface-card-solid" />
    </div>
    <span className="text-content-primary font-medium">Item Name</span>
  </div>
  {/* Right arrow */}
  <LuArrowRight className="text-content-secondary group-hover:text-primary transition-colors" size={18} />
</div>
```

---

## Headers

### Page Header (Desktop)

```tsx
<div className="hidden lg:flex items-center justify-between mb-8">
  <div>
    <h1 className="text-3xl font-bold text-content-primary">Page Title</h1>
    <p className="text-content-secondary mt-1">Page description or subtitle</p>
  </div>
  <div className="flex items-center gap-3">
    <Button variant="faded" className="...">Action 1</Button>
    <Button variant="faded" className="...">Action 2</Button>
  </div>
</div>
```

### Page Header (Mobile)

```tsx
<div className="flex lg:hidden items-center justify-between mb-4">
  <Link href={Routes.PREVIOUS} className="text-content-primary w-6">
    <LuMoveLeft size={21} />
  </Link>
  <div className="flex items-center gap-2">
    <Button variant="faded" className="rounded-full h-8 px-4 text-xs">
      Action
    </Button>
  </div>
</div>
```

### Section Header with Link

```tsx
<div className="flex items-center justify-between mb-6">
  <div className="flex items-center gap-3">
    <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
      <LuHistory className="text-primary" size={20} />
    </div>
    <div>
      <h3 className="text-lg font-semibold text-content-primary">Section Title</h3>
      <p className="text-content-secondary text-sm">Section subtitle</p>
    </div>
  </div>
  <Link href={Routes.PAGE} className="text-primary text-sm font-medium hover:underline flex items-center gap-1">
    View All <LuArrowRight size={14} />
  </Link>
</div>
```

---

## Empty States

### Empty Table/List

```tsx
<div className="text-center py-12">
  <div className="w-16 h-16 rounded-full bg-surface-card flex items-center justify-center mx-auto mb-4">
    <LuHistory className="text-content-secondary" size={28} />
  </div>
  <p className="text-content-primary text-lg font-medium mb-1">No items yet</p>
  <p className="text-content-secondary text-sm">
    Your items will appear here once you create them
  </p>
</div>
```

### Empty State with CTA

```tsx
<div className="flex flex-col items-center justify-center h-48 text-content-muted text-sm">
  <p>No items yet</p>
  <Link href={Routes.CREATE} className="text-primary mt-2 hover:underline">
    Create your first item
  </Link>
</div>
```

---

## Icons

### Icon with Background

```tsx
// Primary themed
<div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
  <LuIcon className="text-primary" size={20} />
</div>

// Success themed
<div className="w-10 h-10 rounded-xl bg-status-success-light flex items-center justify-center">
  <LuIcon className="text-status-success" size={20} />
</div>

// Circular version
<div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
  <LuIcon className="text-primary" size={14} />
</div>
```

### Custom SVG Icon Example

```tsx
const CustomIcon = ({ size = 20 }: { size?: number }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 20 20"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    {/* SVG paths */}
    <path d="..." stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

// Usage
<div className="rounded-full border border-stroke w-12 h-12 flex justify-center cursor-pointer items-center bg-surface-primary text-primary">
  <CustomIcon size={20} />
</div>
```

---

## Layout Patterns

### Two Column Layout (Desktop)

```tsx
<section className="grid lg:grid-cols-12 gap-6 lg:gap-8">
  {/* Main content - larger */}
  <div className="lg:col-span-7 xl:col-span-6">
    <div className="lg:rounded-3xl lg:border lg:border-stroke lg:bg-surface-card-solid lg:p-8">
      {/* Form or main content */}
    </div>
  </div>

  {/* Sidebar - smaller */}
  <div className="hidden lg:block lg:col-span-5 xl:col-span-6 space-y-6">
    {/* Side cards */}
  </div>
</section>
```

### Full Width Section Below Grid

```tsx
{/* Main grid */}
<section className="grid lg:grid-cols-12 gap-6">
  {/* ... */}
</section>

{/* Full width section below */}
<div className="hidden lg:block mt-8">
  <div className="rounded-3xl border border-stroke bg-surface-card-solid p-6">
    {/* Full width content like tables */}
  </div>
</div>
```

---

## Dark Mode Assets

### Conditional Logo Rendering

For logos that need different versions in light/dark mode:

```tsx
import LightModeLogo from "@/components/icons/logo";
import DarkModeLogo from "@/components/icons/logo-dark";

// Usage
<Link href={Routes.HOME}>
  {/* Light mode logo */}
  <div className="dark:hidden">
    <LightModeLogo className={"scale-90"} />
  </div>
  {/* Dark mode logo (white text) */}
  <div className="hidden dark:block">
    <DarkModeLogo className={"scale-90"} />
  </div>
</Link>
```

### Conditional Image Rendering

For images/badges that need light and dark versions:

```tsx
import Image from "next/image";

// Usage
<div className="hover:cursor-pointer">
  {/* Light mode - light background badge */}
  <div className="dark:hidden">
    <Image
      src={"/images/badge-light.svg"}
      alt="Badge"
      className="w-full"
      width={200}
      height={200}
    />
  </div>
  {/* Dark mode - dark background badge */}
  <div className="hidden dark:block">
    <Image
      src={"/images/badge-dark.svg"}
      alt="Badge"
      className="w-full"
      width={200}
      height={200}
    />
  </div>
</div>
```

### Icon Dark Mode Inversion

For icons with dark strokes that need to be visible on dark backgrounds, use the `icon-dark-mode-invert` utility class:

```tsx
// This class applies filter: invert(1) brightness(2) in dark mode
<Image
  src={"/images/icon.svg"}
  alt="Icon"
  width={50}
  height={50}
  className="w-8 h-8 sm:w-10 sm:h-10 icon-dark-mode-invert"
/>
```

> **When to use**: Use `icon-dark-mode-invert` when you have SVG icons with dark strokes/fills that become invisible on dark backgrounds. The filter inverts colors and increases brightness, making dark icons appear white.

> **When NOT to use**: Don't use this on colored icons or icons that already have proper dark mode support. The inversion will distort colors.
