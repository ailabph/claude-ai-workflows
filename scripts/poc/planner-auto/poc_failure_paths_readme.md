# POC 5a: Failure Paths and Session Recovery

## Purpose

Validate that the session model correctly handles reviewer failures — timeout, malformed output, parse failure — by entering a blocked/paused state and resuming cleanly after intervention.

## What This Tests

- Reviewer timeout simulation → session enters paused state
- Malformed reviewer output → parsed as NO_GO with parse-failure issue
- Retry-once behavior before pausing
- Session pause/resume lifecycle in SQLite
- Human intervention simulation (inject answer to blocker)
- Session resumes and continues review loop after intervention

## Input

A pre-populated DB with a session in review phase. Simulated reviewer responses (no actual API calls) covering failure scenarios.

## Ideal Result

- Timeout: session pauses, blocker created, resume works
- Malformed output: treated as NO_GO, planner gets a parse-failure issue
- Retry-once: first failure retries, second failure pauses
- Resume: session continues from where it paused
- All state transitions logged correctly in DB
- No crashes or orphaned state

## Dependencies

- `sqlite3` (stdlib)
- POC 3a DB schema
- POC 2a parser (for malformed output handling)

## Actual Results

- 18/18 tests passed across 5 scenarios (timeout, malformed, partial_json, network_error, success)
- All 4 failure scenarios: retry-once behavior confirmed (2 attempts), then session pauses and blocker created
- All 4 failure scenarios: resume works — blocker resolved, session back to active
- Malformed output correctly parsed as NO_GO with single critical "could not be parsed" issue
- Success scenario: single attempt, no blocker, session stays active
- Extended POC 3a schema with `blockers` table (id, session_id, source, question, answer, status, created_at, resolved_at)
- Each scenario runs in its own isolated session — no state leakage between tests
- No API calls — all reviewer responses simulated, pure Python
- Key finding: the retry-once + pause + blocker + resume lifecycle works cleanly with the proposed SQLite schema
