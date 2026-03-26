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
| 4a | `poc_planner_headless.py` | Pending | — | — |

## Phase C (depends on Phase A)

| POC | Script | Status | Result | Notes |
|-----|--------|--------|--------|-------|
| 1b | `poc_reviewer_codex_mcp.py` | Pending | — | Compare against 1a |
| 1c | `poc_reviewer_opencode_http.py` | Pending | — | Compare against 1a |
| 4b | `poc_context_synthesis.py` | Pending | — | Depends on 3a |
| 5a | `poc_failure_paths.py` | Pending | — | Depends on 2a + 3a |

## Phase D (depends on all above)

| POC | Script | Status | Result | Notes |
|-----|--------|--------|--------|-------|
| 1d | `poc_reviewer_comparison.py` | Pending | — | Needs 1a, 1b, 1c |
| 5b | `poc_review_loop_e2e.py` | Pending | — | Needs 4a + 1a + 2a + 3a |

---

## Summary

| Phase | Total | Done | Pending |
|-------|-------|------|---------|
| A | 3 | 3 | 0 |
| B | 3 | 2 | 1 |
| C | 4 | 0 | 4 |
| D | 2 | 0 | 2 |
| **Total** | **13** | **5** | **8** |
