# Planner-Auto Progress Tracker

## Project Status: Plan 1 Implemented + Reviewed

---

## Timeline

### Phase 0: Proposal & Research
- Documented manual planning workflow (v1.0 proposal)
- Senior dev review → architectural refinements (v1.1 proposal)
- Kagi research: OpenCode subprocess issues, ARIS prior art, Codex MCP
- v1.1 proposal: Session Core vs Reviewer Adapter architecture, SQLite canonical state, reviewer contract

### Phase 1: POC Scripts (13/13 complete)
- **Phase A:** Parser (14/14), Session DB (13/13), Direct API reviewer (3/3 consistent)
- **Phase B:** Structured prompts (12/12), Artifact export (14/14), Planner headless (23/23)
- **Phase C:** Codex MCP (1/1), OpenCode HTTP (1/1), Context synthesis (11/11), Failure paths (18/18)
- **Phase D:** Reviewer comparison (2/3 adapters), E2E review loop (5/5 DB checks)

### Phase 2: Convergence Experiments (11 experiments)

| # | Config | Feature | Result | Cost |
|---|--------|---------|--------|------|
| 1 | Sonnet baseline | Registration | No convergence | $0.26 |
| 2 | + self-review | Registration | No (3x cost) | $0.79 |
| 3 | + guidance | Registration | Declining trend | $0.31 |
| 4 | Opus + thinking | Registration | 4→1→1 issues | $1.15 |
| 5 | Opus max_turns=10 | Registration | $3.83 blowout | $3.83 |
| 6 | Opus old prompt | Registration | Stuck at 4 | $1.67 |
| **7** | **Constrained prompt** | **Registration** | **GO at R5** | **$0.87** |
| 8 | Same as 7 | Webhook | 0 criticals R4 | $1.26 |
| 9 | Same, 10 rounds | Webhook | Oscillating | $2.84 |
| **10** | **+ review history** | **Webhook** | **GO at R4** | **$0.62** |
| **11** | **+ review history** | **Registration** | **GO at R8 (deep)** | **$1.52** |

**Key discoveries:**
- Review history is the key convergence mechanism (-78% cost on complex features)
- Constrained planner prompt prevents scope creep and plan bloat
- Validate feedback (ACCEPT/DEFER/REJECT) stops Claude from blindly fixing everything
- GPT reviews are thorough: 44/46 issues warranted across deep analysis
- Standard features: 5-8 rounds. Complex features: 4-8 rounds with history.

### Phase 3: Plan 1 Implementation

**Dogfooded:** Used POC pipeline to generate the Plan 1 implementation plan itself.

**orchestrator-auto** implemented Plan 1 in a single commit: 3,570 lines, 12 source modules, 8 test files, 102 tests.

**Review round 1:** 6 issues found (3 high, 2 medium, 1 low) → all fixed, 102 tests passing.
- Atomic persistence (conn.commit() in individual CRUD → callers manage transactions)
- Timeout enforcement (asyncio.wait_for wrapping SDK calls)
- PLANNING→COMPLETE path (Plan 1 skips REVIEW)
- complete checks PAUSED status
- One-shot discuss --done flag
- Build artifacts removed from git

**Review round 2:** 4 follow-up issues found (1 high, 2 medium, 1 low) → all fixed, 103 tests passing.
- discuss --done only advances on success
- check_command("complete") enforces phase rules (not just blockers)
- Timeout retries independent of rate-limit counter
- SDK logging includes token counts

---

## Current State

### Plan 1: Session Core — COMPLETE

| Module | Lines | Status |
|--------|-------|--------|
| `cli.py` | 471 | Implemented + reviewed |
| `db.py` | 456 | Implemented + reviewed (atomic transactions) |
| `agents.py` | 213 | Implemented + reviewed |
| `sdk_wrapper.py` | 192 | Implemented + reviewed (timeout + token logging) |
| `session.py` | 174 | Implemented + reviewed (phase enforcement) |
| `export.py` | 126 | Implemented + reviewed |
| `validation.py` | 92 | Implemented + reviewed |
| `errors.py` | 67 | Implemented |
| `prompts.py` | 57 | Implemented |
| `logging.py` | 54 | Implemented |
| `state.py` | 49 | Implemented + reviewed (PLANNING→COMPLETE) |
| **Tests** | **1,616** | **103 passing** |

### Plan 2: Reviewer Adapter — NOT STARTED

Scope: GPT reviewer integration, review-fix loop, review history, feedback validation, keep/trim, convergence logic, severity filtering, complexity detection, fast mode, .kafra handoff.

All mechanisms proven in POC 5b experiments. Implementation plan not yet generated.

---

## Key Documents

| Document | Location | Purpose |
|----------|----------|---------|
| v1.0 proposal | `docs/plans/planner-auto-proposal-v1.md` | Original idea + manual workflow |
| v1.1 proposal | `docs/plans/planner-auto-proposal-v1.1.md` | Final architecture + convergence strategy |
| Research | `docs/plans/planner-auto-proposal-v1-research.md` | Kagi research findings |
| Plan 1 plan | `docs/planner-auto/plans/plan-phase1.1.md` | Implementation plan (dogfooded) |
| POC status | `scripts/poc/planner-auto/POC_STATUS.md` | Full experiment log |
| POC 5b readme | `scripts/poc/planner-auto/poc_review_loop_e2e_readme.md` | 11 experiment analysis |

## Final v1 Configuration (Proven)

| Setting | Value |
|---------|-------|
| Planner | claude-opus-4-6, effort=medium, thinking=adaptive, max_turns=10 |
| Reviewer | gpt-5.4, reasoning_effort=high |
| Resolution guidance | ON |
| Keep/trim | ON |
| Validate feedback | ON (ACCEPT/DEFER/REJECT) |
| Filter severity | critical,major |
| Review history | ON (default) |
| Constrained prompt | ON |
| Cap | Standard: 8, Complex: 12, Emergency: 20 |
