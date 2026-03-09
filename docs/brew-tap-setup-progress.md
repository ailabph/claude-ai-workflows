# Homebrew Tap Setup — Live Progress

> **⚠️ SUPERSEDED** — This document recorded the one-time manual tap setup (v1.9.0).
> Formula updates are now automated via `.github/workflows/release.yml`.
> For the current release process, see [`docs/RELEASE.md`](RELEASE.md).

**Tap:** `ailabph/orchestrator-auto`
**Repo:** https://github.com/ailabph/homebrew-orchestrator-auto
**PyPI:** https://pypi.org/project/orchestrator-auto/1.9.0/
**Started:** 2026-03-09

---

## Steps

| # | Step | Status |
|---|------|--------|
| 1 | Initialize tap locally | ✅ Done |
| 2 | Generate resource stanzas (poet) | ✅ Done |
| 3 | Write formula | ✅ Done |
| 4 | Audit + test locally | ✅ Done (`brew style` clean; `brew audit --strict` blocked by macOS 26 CLT issue — system, not formula) |
| 5 | Push to GitHub | ✅ Done |

---

## Step 1 — Initialize tap locally

**Command:** `brew tap-new ailabph/orchestrator-auto`
**Result:** ✅ Created at `/opt/homebrew/Library/Taps/ailabph/homebrew-orchestrator-auto`

---

## Step 2 — Generate resource stanzas

**Method:** `homebrew-pypi-poet` in fresh venv with `orchestrator-auto[tui]==1.9.0`
**Result:** ✅ All deps captured. TUI packages (textual 8.0.2, rich, markdown-it-py, etc.) fetched separately via PyPI JSON API + `pip download` since poet skipped them.

---

## Step 3 — Write formula

**File:** `Formula/orchestrator-auto.rb`
**Result:** ✅ Written with:
- `depends_on "python@3.13"`
- 45 resource blocks (core + TUI deps)
- `virtualenv_install_with_resources` install block
- `brew test` block: `orchestrator --version`

---

## Step 4 — Audit + style check

**Result:** ✅ `brew style` — 1 file inspected, no offenses
**Note:** `brew audit --strict` blocked by macOS 26 CLT incompatibility (system issue, not formula)

---

## Step 5 — Push to GitHub

**Remote:** https://github.com/ailabph/homebrew-orchestrator-auto
**Commit:** `cca71d0` — add orchestrator-auto formula v1.9.0
**Result:** ✅ Pushed to `main`

---

## Install Command

```bash
brew tap ailabph/orchestrator-auto
brew install orchestrator-auto
```

Or one-liner:
```bash
brew install ailabph/orchestrator-auto/orchestrator-auto
```
