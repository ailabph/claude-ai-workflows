# Planner-Auto — Open Issues & Bugs

Tracked issues discovered during development, review, and stress testing.

---

## Critical / Blocking

_(none currently)_

---

## High

_(none currently — H1, H2, H3 resolved by direct API backend)_

---

## Medium

### M2: Stress testing proposal uses fake file paths
**Found:** Stress test (2026-03-28)
**Symptom:** `proposal-stress-testing.md` references `src/app.py` which doesn't exist in this repo.
**Status:** Partially mitigated — real stress test ran successfully with `planner-auto/planner_auto/cli.py`. Proposal doc still has fake paths.
**Fix needed:** Update proposal to use real repo paths.

---

## Low

### L1: anyio version compatibility
**Found:** Stress test tracebacks reference `anyio._backends._asyncio.py:461`
**Note:** The anyio cancel scope issue may be version-specific. Current `anyio` version may conflict with `claude-agent-sdk` expectations. Worth checking if upgrading/pinning anyio resolves the tracebacks.

---

## Resolved

| ID | Issue | Fixed In | How |
|----|-------|----------|-----|
| — | Round numbering starts at 1 on resume | v0.2.0 | Engine queries max existing round |
| — | Disposition indexing mismatch | v0.2.0 | Validate before filter |
| — | CLI config not wired (prompt_mode, effort) | v0.2.0 | Defaults from POC config |
| — | Review metadata all None | v0.2.0 | Adapter populates, engine passes through |
| — | Export naming wrong (plan-final.md) | v0.2.0 | Numbered a-NN-plan-final.md |
| — | Duplicate CLI summary line | v0.3.0 | Engine owns final output |
| — | check --probe wrong signature | v0.3.0 | Correct query_claude args |
| — | Fresh DB misclassified | v0.3.0 | try/except around schema check |
| — | add-context missing observability | v0.3.0 | --verbose + setup_session_logging |
| — | inspect dump not pure JSON | v0.3.0 | Warning to stderr, JSON to stdout |
| — | Atomic persistence (auto-commit) | v0.1.2 | Callers manage transactions |
| — | Timeout not enforced | v0.1.2 | asyncio.wait_for wrapping |
| H1 | Opus + thinking + SDK subprocess empty results | v0.4.0 | Direct API backend bypasses SDK subprocess entirely |
| H2 | Rate limit from SDK subprocess (not API) | v0.4.0 | Direct API backend uses `anthropic` package, no CLI subprocess |
| H3 | anyio cancel scope tracebacks | v0.4.0 | Direct API backend has no subprocess = no anyio |
| M1 | Multiple Claude session conflicts | v0.4.0 | Direct API backend doesn't spawn subprocess |
