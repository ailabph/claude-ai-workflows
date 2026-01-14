# MCP Playwright Test Site (Next.js) Plan

**Date:** 2026-01-14
**Purpose:** Create a deterministic local Next.js website specifically for validating Playwright MCP tool passing via `orchestrator test-playwright ...`.
**Location:** `orchestrator-auto/fixtures/playwright-test-site/`

This fixture is committed to the repo for local runs only (not deployed).

---

## Objective

Build a small Next.js app (as a fixture within the orchestrator-auto package) that reliably:

- Provides stable UI selectors (`data-testid`) for navigation and form input.
- Emits deliberate **console warnings/errors** that should be capturable via Playwright MCP.
- Generates both a **successful** and a **failing** **network request** that should be capturable via Playwright MCP.

This site is intentionally minimal to reduce flakiness.

---

## Non-Goals

- Production-ready UI.
- Authentication.
- Complex routing/state.
- Visual styling.

---

## Tech Stack

- Next.js (App Router)
- TypeScript
- No external UI libraries required

---

## Prerequisites

- Node.js `>=20`
- npm (use `npm ci` with committed lockfile)

---

## Project Setup

### 1) Scaffold

```bash
# From repository root
cd orchestrator-auto/fixtures
npx create-next-app@latest playwright-test-site --ts --eslint --app
```

### 2) Run locally

Pick any available port (examples: `3000`, `3001`, `3100`).

```bash
# From repository root
cd orchestrator-auto/fixtures/playwright-test-site
npm ci
npm run dev -- --port <PORT>
```

Expected base URL for orchestrator:

- `http://localhost:<PORT>/`

### 3) Directory structure

```
orchestrator-auto/
├── fixtures/
│   └── playwright-test-site/    ← This fixture
│       ├── app/
│       │   ├── page.tsx         # Home page
│       │   ├── form/
│       │   │   └── page.tsx     # Form page
│       │   └── api/
│       │       ├── ping/
│       │       │   └── route.ts # 200 endpoint
│       │       └── fail/
│       │           └── route.ts # 500 endpoint
│       ├── package.json
│       └── README.md
└── docs/
    └── plans/
        └── PLAN_mcp_playwright_test_site_nextjs.md  ← This plan
```

---

## Deterministic Selectors

Use these required selectors:

- Home → Form link/button: `data-testid="nav-form"`
- Username input: `data-testid="username"`

Optional (if you want an explicit manual trigger too):

- Trigger errors button: `data-testid="trigger-errors"`

---

## Required Routes + Behaviors

### 1) Home page: `/`

**File:** `app/page.tsx`

Requirements:

- Render a link to `/form` with `data-testid="nav-form"`.
- On mount, emit:
  - `console.warn("[mcp-test] warn from home")`
  - `console.error("[mcp-test] error from home")`
- On mount, trigger both:
  - `fetch("/api/ping")` (expected `200`)
  - `fetch("/api/fail")` (expected `500`)

Notes:

- Prefix logs with `[mcp-test]` so the MCP console capture is unambiguous.
- The two network calls give you deterministic data for MCP network inspection.

### 2) Form page: `/form`

**File:** `app/form/page.tsx`

Requirements:

- Render a username input with `data-testid="username"`.
- The input must be visible without scrolling.

Optional:

- Render additional form controls if you want to expand the orchestrator test later.

### 3) API ping endpoint: `/api/ping`

**File:** `app/api/ping/route.ts`

Requirements:

- Respond `200` JSON:

```json
{ "ok": true, "source": "ping" }
```

### 4) API fail endpoint: `/api/fail`

**File:** `app/api/fail/route.ts`

Requirements:

- Respond `500` JSON:

```json
{ "ok": false, "source": "fail" }
```

---

## Smoke Checklist (manual)

After starting the dev server:

1. Open `http://localhost:<PORT>/` in a browser.
2. Confirm DevTools console shows:
   - `[mcp-test] warn from home`
   - `[mcp-test] error from home`
3. Confirm Network tab shows requests:
   - `/api/ping` status `200`
   - `/api/fail` status `500`
4. Click “Go to form” and confirm `/form` loads.
5. Confirm username input exists (`data-testid="username"`).

---

## Orchestrator Verification

Start the test site, then run the verification command:

```bash
# Terminal 1: Start the test site
cd orchestrator-auto/fixtures/playwright-test-site
npm run dev -- --port <PORT>

# Terminal 2: Run orchestrator verification
orchestrator test-playwright planner --test-url http://localhost:<PORT>/
orchestrator test-playwright executor --test-url http://localhost:<PORT>/
orchestrator test-playwright both --test-url http://localhost:<PORT>/
```

Expected MCP captures:

- Console messages include the `[mcp-test]` warn/error.
- Network requests include both `/api/ping` (200) and `/api/fail` (500).
- A screenshot artifact is created by the test runner.

---

## Optional Hardening (if needed)

- Add `robots.txt` and disable caching if you see stale behavior.
- Add a dedicated page `/signals` that triggers signals only on click if you want to test interactive signal capture.
- Add `data-testid` attributes to all relevant elements to avoid brittle prompts.
