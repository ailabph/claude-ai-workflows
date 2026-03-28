# Planner-Auto Progress Tracker

## Project Status: v0.4.0 — Plan 1 + Plan 2 + Observability + Direct API Backend

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

### Plan 2: Reviewer Adapter — COMPLETE

| Module | Lines | Status |
|--------|-------|--------|
| `reviewer/contract.py` | 163 | Implemented + reviewed (ReviewerContract, ReviewerResponse, ReviewIssue) |
| `reviewer/parser.py` | 372 | Implemented + reviewed (JSON/XML/free-form fallback) |
| `reviewer/prompts.py` | 171 | Implemented (3 prompt variants: basic, guidance, keep_trim) |
| `reviewer/direct_api.py` | 237 | Implemented + reviewed (GPT-5.4, retry, cost tracking, raw_text) |
| `loop/engine.py` | 425 | Implemented + reviewed (round resume, total_cost, metadata) |
| `loop/feedback.py` | 217 | Implemented + reviewed (ACCEPT/DEFER/REJECT, full-list indexing) |
| `loop/history.py` | 196 | Implemented (cumulative deferred context across all rounds) |
| `loop/convergence.py` | 126 | Implemented (complexity detection, caps, fast mode) |
| `git_utils.py` | 50 | Implemented (repo root discovery + --repo-root override) |
| `export.py` (extended) | 193 | Implemented + reviewed (a-NN artifacts, keep/trim, fast headers) |
| `db.py` (extended) | 303 | Implemented + reviewed (schema v2 migration, dispositions) |
| `cli.py` (extended) | 243 | Implemented + reviewed (review command, fast/config wiring) |
| **Tests** | **3,200+** | **283 passing** |

**Review rounds:**
- Round 1: 5 issues (resume bug, disposition indexing, CLI config, metadata, export naming) → all fixed
- Round 2: 3 issues (cost/raw_text incomplete, round lookup, fast headers) → all fixed

### Observability & Debug (v0.3.0) — COMPLETE

| Module | Status |
|--------|--------|
| `logging.py` | Rewritten — shared root logger + SessionFilter |
| `inspect.py` | New — 6 DB inspection commands |
| `cli.py` (check) | New — environment validation, --probe for API |
| `loop/engine.py` (output tiers) | Updated — quiet/verbose/debug |
| All modules (structured logging) | Updated — 49+ log calls at key decisions |
| All commands (--verbose/--debug) | Updated — per-command flags + session logging |
| **Tests** | **368 passing** (was 283) |

**Review rounds:**
- Round 1: 7 issues (probe signature, fresh DB, output tiers, add-context, tracebacks, dump JSON, claude_agent_sdk check) → all fixed
- Round 2: 1 issue (duplicate CLI summary line violating quiet contract) → fixed
- Round 3: 4 medium issues (add-context log, inspect --round flags, dump --output, status wiring) → fixed

---

### Direct API Backend (v0.4.0) — COMPLETE

Replaced Claude CLI subprocess with direct Anthropic API calls as default backend. Resolves the #1 production blocker (unusable alongside active Claude Code sessions).

| Change | Detail |
|--------|--------|
| `sdk_wrapper.py` | Dual backend: `_execute_direct()` (anthropic pkg) + `_execute_sdk()` (CLI subprocess) |
| Auth-aware default | `ANTHROPIC_API_KEY` → direct, OAuth only → sdk |
| `.env` auto-load | `python-dotenv` loads API keys at CLI startup |
| Error contract | Anthropic exceptions mapped to existing SDKError hierarchy |
| `--claude-backend` | On `start` command, persisted in session config |
| Issues resolved | H1 (empty results), H2 (rate limit), H3 (anyio noise), M1 (session conflicts) |
| **Tests** | **401 passing** (was 368) |

**Stress test results:**
- Confirmed direct API works alongside active Claude Code session
- `discuss` + `--done` succeeded where SDK backend was rate-limited
- First full end-to-end success: start → add-context → discuss → generate → review → complete
- Session `765ac72b` (stress-test-3): 4-milestone plan for "--json flag on status command"
- Review loop: **converged in 3 rounds, $0.12, GPT said GO**
- Issue trend: 2→1→GO (strictly declining, review history working)
- 7 artifacts exported, .kafra handoff successful
- Observability: verbose output showed round metrics, dispositions, draft size, history context

### First Successful End-to-End Stress Test (2026-03-28)

```
planner-auto start --project stress-test-3          → direct backend, repo root detected
planner-auto add-context 765ac72b --file cli.py     → 44K chars stored, absolute path
planner-auto add-context 765ac72b --note "..."      → note stored
planner-auto discuss 765ac72b "..." --done          → Claude asked questions, phase → PLANNING
planner-auto generate 765ac72b                      → 4-milestone plan, format validated
planner-auto review 765ac72b --verbose              → 3 rounds, GO, $0.12
  Round 1: NO_GO (2 issues, both ACCEPT) → revised
  Round 2: NO_GO (1 issue, ACCEPT) → revised
  Round 3: GO (0 issues)
  Final plan: .kafra/a-01-plans/stress-test-3.md
```

---

## Key Documents

| Document | Location | Purpose |
|----------|----------|---------|
| v1.0 proposal | `docs/plans/planner-auto-proposal-v1.md` | Original idea + manual workflow |
| v1.1 proposal | `docs/plans/planner-auto-proposal-v1.1.md` | Final architecture + convergence strategy |
| Research | `docs/plans/planner-auto-proposal-v1-research.md` | Kagi research findings |
| Plan 1 plan | `docs/planner-auto/plans/plan-phase1.1.md` | Implementation plan (dogfooded) |
| Plan 2 plan | `docs/planner-auto/plans/plan-phase2.1.md` | Implementation plan (manual, reviewed) |
| Observability plan | `docs/planner-auto/plans/plan-observability.md` | Logging, inspect, check, output tiers |
| Stress testing | `docs/planner-auto/plans/proposal-stress-testing.md` | 3-level testing strategy |
| Direct API proposal | `docs/planner-auto/plans/proposal-direct-api-fallback.md` | Direct Anthropic API backend (v5) |
| Direct API plan | `docs/planner-auto/plans/plan-direct-api-fallback.md` | Implementation plan (3 milestones) |
| Brew installer | `docs/planner-auto/plans/brew-installer-plan.md` | Homebrew formula plan |
| POC status | `scripts/poc/planner-auto/POC_STATUS.md` | Full experiment log |
| POC 5b readme | `scripts/poc/planner-auto/poc_review_loop_e2e_readme.md` | 11 experiment analysis |
| AGENTS.md | `planner-auto/AGENTS.md` | Developer context |
| CHANGELOG.md | `planner-auto/CHANGELOG.md` | Version history |
| Debugger agent | `claude/agents/planner-auto-debugger.md` | Debugging agent definition |

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
