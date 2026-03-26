# Planner-Auto POC Status

Tracking sheet for all POC scripts. Updated as each POC is implemented and validated.

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
| 5b | `poc_review_loop_e2e.py` | Pending | — | Needs 4a + 1a + 2a + 3a |

---

## Summary

| Phase | Total | Done | Pending |
|-------|-------|------|---------|
| A | 3 | 3 | 0 |
| B | 3 | 3 | 0 |
| C | 4 | 4 | 0 |
| D | 2 | 1 | 1 |
| **Total** | **13** | **11** | **2** |
