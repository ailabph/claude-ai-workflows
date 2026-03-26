# POC 3b: Artifact Export from DB

## Purpose

Validate that all audit artifacts (chat.csv, context-summary.md, numbered plan/review files) can be reliably generated from the SQLite database. Proves the "DB is canonical, files are exports" pattern.

## What This Tests

- Export `chat.csv` from messages table (timestamp, role, message columns)
- Export `context-summary.md` synthesized from context_entries table
- Export numbered `a-01-plan.md`, `a-02-review.md`, etc. from plan_drafts and reviews tables
- Export `a-<N>-plan-final.md` for the approved plan
- File naming convention correctness
- Idempotency (exporting twice produces identical files)

## Input

A pre-populated SQLite DB (reuses POC 3a schema and test data).

## Ideal Result

- All artifact files written to a session directory
- Files are human-readable and match expected format
- chat.csv is valid CSV, importable into any spreadsheet tool
- Numbered files appear in correct order
- Re-export produces identical output (idempotent)

## Dependencies

- `sqlite3` (stdlib), `csv` (stdlib)
- POC 3a DB schema
