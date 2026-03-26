# Planner-Auto POC Status

Tracking sheet for all POC scripts and convergence experiments. Updated as each POC is implemented and validated.

---

## Phase A (no dependencies)

| POC | Script | Status | Result | Notes |
|-----|--------|--------|--------|-------|
| 2a | `poc_parse_go_nogo.py` | Done | 14/14 passed | JSON, XML, free-form fallback chain. Markdown-fenced JSON covered. Simplified GO regex after review. |
| 3a | `poc_session_db.py` | Done | 13/13 passed | 5 tables, full lifecycle (setup→complete), WAL + foreign keys enabled, file-based DB inspectable with sqlite3 CLI. |
| 1a | `poc_reviewer_direct_api.py` | Done | 3/3 consistent | GPT-5.4 returns NO_GO with 7-8 issues, all parseable. Avg latency 14.1s, avg cost $0.007/review. Verdict 100% consistent across runs. |

## Phase B (depends on Phase A)

| POC | Script | Status | Result | Notes |
|-----|--------|--------|--------|-------|
| 2b | `poc_structured_prompt.py` | Done | 12/12 parsed | All 4 strategies 3/3 parseable. xml_tagged fastest (8.7s, 1007 tok). few_shot most thorough (9.0 issues). free_form noisy (118 issues from bullet extraction). json_instructed solid middle ground. |
| 3b | `poc_artifact_export.py` | Done | 14/14 passed | 7 files exported (chat.csv, context-summary.md, 2 plans, 2 reviews, final plan). Naming convention correct. Idempotent re-export verified. |
| 4a | `poc_planner_headless.py` | Done | 23/23 passed | Claude Sonnet 4.6 via Agent SDK query(). 5 milestones with tasks+deliverables. 25.7s, $0.029. Required SDK upgrade 0.1.47→0.1.50. |

## Phase C (depends on Phase A)

| POC | Script | Status | Result | Notes |
|-----|--------|--------|--------|-------|
| 1b | `poc_reviewer_codex_mcp.py` | Done | 1/1 parsed | GPT via Codex MCP: NO_GO, 5 issues, 30.9s, $0.035. 2.2x slower than Direct API, 5x more expensive. Requires `codex login` for auth (env passthrough unreliable). |
| 1c | `poc_reviewer_opencode_http.py` | Done | 1/1 parsed | GPT-5.4 via OpenCode HTTP: NO_GO, 6 issues, 13.8s, $0.039. Latency matches Direct API but 5.6x costlier (OpenCode injects 10K+ system tokens). Requires `opencode serve` running separately. |
| 4b | `poc_context_synthesis.py` | Done | 11/11 passed | Haiku synthesizes 292 words from 15 msgs + 6 entries in 8.3s, $0.019. All decisions captured, noise filtered. Directly usable as planner input. |
| 5a | `poc_failure_paths.py` | Done | 18/18 passed | 5 scenarios: timeout, malformed, partial_json, network_error, success. Retry-once + pause + blocker + resume lifecycle validated. Blockers table added. |

## Phase D (depends on all above)

| POC | Script | Status | Result | Notes |
|-----|--------|--------|--------|-------|
| 1d | `poc_reviewer_comparison.py` | Done | 2/3 adapters passed | Direct API: fastest ($0.007, 11.7s, 7 issues). OpenCode HTTP: works but 5.7x costlier. Codex MCP: failed (subprocess flaky). Recommendation: Direct API. |
| 5b | `poc_review_loop_e2e.py` | Done | 5/5 DB checks | Full loop works. Multiple convergence experiments run (see below). |

---

## All 13 POCs Complete

| Phase | Total | Done | Pending |
|-------|-------|------|---------|
| A | 3 | 3 | 0 |
| B | 3 | 3 | 0 |
| C | 4 | 4 | 0 |
| D | 2 | 2 | 0 |
| **Total** | **13** | **13** | **0** |

---

## Convergence Experiments (POC 5b)

All experiments use the same feature: "Add user registration with email validation, password hashing, and rate limiting"

### Experiment 1: Sonnet Baseline (no intervention)

| Config | Value |
|--------|-------|
| Planner | claude-sonnet-4-6 (default effort, no thinking) |
| Reviewer | gpt-5.4 (temperature=0.3) |
| Flags | None |

| Rounds | Issues | Cost | Time |
|--------|--------|------|------|
| 3 | 6→8→7 (oscillating) | $0.261 | 254s |
| 6 | 9→8→6→9→6→6 (oscillating) | $0.785 | 793s |

**Result:** Never converges. Issue count oscillates 6-9 per round.

### Experiment 2: Self-Review (check → repair → wrap-up after each revision)

| Config | Value |
|--------|-------|
| Planner | claude-sonnet-4-6 |
| Reviewer | gpt-5.4 (temperature=0.3) |
| Flags | `--self-review` |

| Rounds | Issues | Cost | Time | Plan Size |
|--------|--------|------|------|-----------|
| 3 | 7→6→7 | $0.790 | 700s | 10.9 KB (29% smaller than baseline) |

**Result:** 3x cost, no issue improvement. Wrap-up pass reduces bloat. Full self-review not justified.

### Experiment 3: Resolution Guidance (GPT provides acceptance criteria)

| Config | Value |
|--------|-------|
| Planner | claude-sonnet-4-6 |
| Reviewer | gpt-5.4 (temperature=0.3) |
| Flags | `--resolution-guidance` |

| Rounds | Issues | Cost | Time |
|--------|--------|------|------|
| 3 | 8→5→5 (declining) | $0.305 | 311s |
| 6 | 7→7→6→6→7→5 (marginal) | $0.833 | 897s |

**Result:** Best 3-round trajectory. +17% cost. Over 6 rounds, marginal improvement.

### Experiment 4: Opus + High Effort + Thinking + Guidance (max_turns=1)

| Config | Value |
|--------|-------|
| Planner | claude-opus-4-6 (effort=high, thinking=adaptive) |
| Reviewer | gpt-5.4 (reasoning_effort=high) |
| Flags | `--resolution-guidance --planner-effort high --planner-thinking --reviewer-reasoning high` |
| Note | max_turns=1 (originally a bug — Opus couldn't use tools, gave text-only responses) |

| Rounds | Issues | Cost | Time |
|--------|--------|------|------|
| 8 | 4→1→1→1→4→1→4→5 | $1.148 | 595s |

**Result:** Best issue trajectory — reaches 1 issue by round 2. Oscillates but stays low. The constrained max_turns=1 produced tighter, more focused revisions.

### Experiment 5: Opus + High + Thinking + Validate + Filter (max_turns=10, fixed)

| Config | Value |
|--------|-------|
| Planner | claude-opus-4-6 (effort=high, thinking=adaptive) |
| Reviewer | gpt-5.4 (reasoning_effort=high) |
| Flags | `--resolution-guidance --validate-feedback --filter-severity critical,major --planner-effort high --planner-thinking --reviewer-reasoning high` |
| Note | max_turns=10 (Opus used tools extensively — Read, Write, explore codebase) |

| Rounds | Issues | Cost | Time |
|--------|--------|------|------|
| 10 | 5→4→4→4→4→5→4→5→4→3 | $3.834 | 2959s (49 min) |

**Result:** 3.3x more expensive than Experiment 4. Opus used tools extensively (avg 100s review, 182s revision). Issue count stabilized at 3-5 but never reached the 1-issue low from Experiment 4.

### Experiment 4 vs 5: Quality Comparison

| Metric | Exp 4 (max_turns=1) | Exp 5 (max_turns=10) |
|--------|---------------------|----------------------|
| Final plan size | 30 KB (89 lines) | 29 KB (135 lines) |
| Tasks in plan | 61 | 93 |
| Milestones | 5 | 5 |
| Scope | Expanded (JWT, login, auth, protected routes) | Focused (registration + validation + rate limiting) |
| Over-engineering | High (sentinel hashes, MIGRATIONS.md, mask_ip) | Moderate (ProxyFix, CREATE_TABLES guardrail) |
| Implementability | 2-3 days | 1-2 days |
| Cost | $1.15 | $3.83 |

**Key insight:** max_turns=1 forces Claude to give text-only responses without tool use. This produces plans that are deeper in specification but prone to scope creep. max_turns=10 lets Claude explore the codebase, producing more disciplined plans, but at 3.3x the cost. The "bug" (max_turns=1) was producing better convergence behavior.

---

## Features Added to POC 5b (E2E Loop)

The e2e loop script now supports many experimental flags:

| Flag | What It Does |
|------|-------------|
| `--self-review` | Bounded self-check → repair → wrap-up after each revision |
| `--resolution-guidance` | GPT provides `resolution_guidance` + `target_section` per issue |
| `--validate-feedback` | Claude assesses each issue's validity before fixing (accept/defer/reject) |
| `--filter-severity critical,major` | Only pass critical+major issues to Claude; filter export too |
| `--keep-trim` | GPT includes "what to keep" and "what to trim" sections |
| `--planner-effort low/medium/high/max` | Claude effort level |
| `--planner-thinking` | Enable Claude adaptive thinking |
| `--reviewer-reasoning low/medium/high` | GPT reasoning effort (drops temperature when active) |

### Schema Extensions (POC 2a parser)

| Field | Added To | Purpose |
|-------|----------|---------|
| `resolution_guidance` | `ReviewIssue` | 1-3 sentences: what must change for the issue to be resolved |
| `target_section` | `ReviewIssue` | Which milestone/section the issue applies to |
| `keep` | `ReviewerResponse` | List of plan elements to preserve during revision |
| `trim` | `ReviewerResponse` | List of plan elements to simplify or remove |

### Prompt Changes

| Component | Change |
|-----------|--------|
| Planner system prompt | Added scope constraints (only implement what's requested), size limits (max 8 tasks/milestone, 1-2 sentences per task, under 3000 words), template from CLAUDE_orch_v2.md |
| Reviewer prompt (guidance) | `SYSTEM_PROMPT_WITH_GUIDANCE` — requests resolution_guidance + target_section |
| Reviewer prompt (keep/trim) | `SYSTEM_PROMPT_WITH_KEEP_TRIM` — requests keep/trim lists in addition to guidance |
| Revision prompt (validate) | Claude assesses each issue as ACCEPT/DEFER/REJECT before fixing |
| Revision prompt (keep/trim) | Includes "What to Keep" and "What to Trim" sections from reviewer |

### Other Fixes

- `run_review()` now accepts optional `system_prompt` override and `reasoning_effort`
- Review export now filters by severity (no more `[minor]` in filtered exports)
- Review export includes resolution_guidance, target_section, keep/trim sections
- `max_turns=1` default (was 10, then 5, settled on 1 for tighter plans)
- Blockers table added to schema (validated by POC 5a)

---

### Experiment 6: Opus medium + keep-trim (max_turns=5, old prompt)

| Config | Value |
|--------|-------|
| Planner | claude-opus-4-6 (effort=medium, thinking=adaptive, max_turns=5) |
| Reviewer | gpt-5.4 (reasoning_effort=high) |
| Flags | `--keep-trim --validate-feedback --resolution-guidance --filter-severity critical,major` |
| Prompt | Old planner prompt (no size/scope constraints) |

| Rounds | Issues | Cost | Time |
|--------|--------|------|------|
| 6 | 5→6→4→4→4→4 | $1.67 | 1286s (21 min) |

**Result:** Did not converge. max_turns=5 made Opus use tools, increasing cost 2.4x vs constrained runs. Stuck at 4 issues.

### Experiment 7: CONVERGED — Constrained Prompt (max_turns=2)

**First successful convergence across all experiments.**

| Config | Value |
|--------|-------|
| Planner | claude-opus-4-6 (effort=medium, thinking=adaptive, max_turns=2) |
| Reviewer | gpt-5.4 (reasoning_effort=high) |
| Flags | `--keep-trim --validate-feedback --resolution-guidance --filter-severity critical,major` |
| Prompt | **Constrained planner prompt** (max 8 tasks/milestone, 1-2 sentences, under 3000 words, stay on scope) |

| Rounds | Issues | Cost | Time | Plan Size |
|--------|--------|------|------|-----------|
| 5 | **5→4→4→4→GO** | **$0.87** | **791s (13 min)** | 10 KB (1,346 words) |

**Result: CONVERGED at round 5.** GPT said GO with 3 minor notes. Plan grew 2x (5→10 KB) vs 7.5x in baseline.

**Winning configuration (6 factors combined):**
1. Constrained planner prompt (size + scope limits)
2. Validate feedback (ACCEPT/DEFER/REJECT)
3. Filter severity (critical + major only)
4. Keep/trim (preserve good content, remove bloat)
5. Resolution guidance (acceptance criteria per issue)
6. max_turns=2 (tight responses, no tool sprawl)
