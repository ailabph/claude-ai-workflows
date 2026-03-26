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
