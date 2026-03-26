# POC 3a: SQLite Session Database

## Purpose

Validate the SQLite schema proposed in v1.1 — create sessions, append messages, store plan drafts and reviews, query by session. Proves the DB-as-canonical-state pattern works before building the real session engine.

## What This Tests

- Schema creation (sessions, messages, context_entries, plan_drafts, reviews)
- Session lifecycle: create, update phase, update status, mark complete
- Append-only message logging with timestamps and roles
- Context entry storage (file paths, entity summaries)
- Plan draft versioning (draft_number increments per session)
- Review storage with parsed verdict and issue counts
- Query patterns: get session, get messages by session, get latest plan draft, get all reviews
- Concurrent access safety (WAL mode)

## Input

Simulated session data — no API calls, no agents. Pure DB operations with hardcoded test data.

## Ideal Result

- All tables created without errors
- Full session lifecycle exercised: setup → context → discussion → planning → review → complete
- Draft versioning works (draft 1, 2, 3 within same session)
- Review storage captures verdict + issues correctly
- Queries return expected data
- DB file is inspectable with `sqlite3` CLI after run
- Print summary of all operations and row counts

## Dependencies

- `sqlite3` (stdlib)
