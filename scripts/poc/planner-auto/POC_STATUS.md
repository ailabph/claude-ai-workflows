# Planner-Auto POC Status

Tracking sheet for all POC scripts. Updated as each POC is implemented and validated.

---

## Phase A (no dependencies)

| POC | Script | Status | Result | Notes |
|-----|--------|--------|--------|-------|
| 2a | `poc_parse_go_nogo.py` | Done | 14/14 passed | JSON, XML, free-form fallback chain. Markdown-fenced JSON covered. Simplified GO regex after review. |
| 3a | `poc_session_db.py` | Done | 13/13 passed | 5 tables, full lifecycle (setup→complete), WAL + foreign keys enabled, file-based DB inspectable with sqlite3 CLI. |
| 1a | `poc_reviewer_direct_api.py` | Pending | — | — |

## Phase B (depends on Phase A)

| POC | Script | Status | Result | Notes |
|-----|--------|--------|--------|-------|
| 2b | `poc_structured_prompt.py` | Pending | — | Depends on 2a parser |
| 3b | `poc_artifact_export.py` | Pending | — | Depends on 3a schema |
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
| A | 3 | 2 | 1 |
| B | 3 | 0 | 3 |
| C | 4 | 0 | 4 |
| D | 2 | 0 | 2 |
| **Total** | **13** | **2** | **11** |
