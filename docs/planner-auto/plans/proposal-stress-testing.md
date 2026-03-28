# Planner-Auto Stress Testing Proposal

## Purpose

Validate planner-auto end-to-end before the first real user session. Unit tests (283 passing) verify individual functions; stress tests verify the full CLI flow, real API integration, edge cases, and failure recovery as a user would experience them.

---

## Three Testing Levels

### Level 1: Local End-to-End (No API Calls)

Test the full CLI flow against a real SQLite DB to verify session lifecycle, phase transitions, DB state consistency, artifact export, and log files. No API calls — uses the existing mocked test infrastructure or manual CLI walkthrough.

**What it validates:**
- Session created with correct initial state
- Context files stored with absolute paths
- Phase transitions enforced (SETUP→CONTEXT→DISCUSSION→PLANNING→COMPLETE)
- Plan drafts versioned correctly (draft_number increments)
- Artifact export produces correct files with correct names
- Blocker pause/resume lifecycle works
- Schema migration (v1 → v2) preserves data
- Config snapshot captured at session start

**Manual walkthrough:**
```bash
planner-auto start --project stress-test-1
planner-auto add-context <id> --file src/app.py
planner-auto add-context <id> --file src/models.py
planner-auto add-context <id> --note "PostgreSQL, deployed on AWS ECS"
planner-auto discuss <id> "Add user registration with email validation" --done
planner-auto generate <id>
planner-auto status <id>
planner-auto export <id>
planner-auto complete <id>

# Verify
sqlite3 ~/.planner-auto/planner.db "SELECT id, phase, status FROM sessions"
ls ~/.planner-auto/sessions/<id>/
cat ~/.planner-auto/logs/<id>.log
```

### Level 2: Live API Smoke Tests (Real Claude + GPT)

Test against real APIs with real feature descriptions. Costs ~$1-3 per run depending on round count.

**Simple feature (should converge in 3-5 rounds):**
```bash
planner-auto start --project smoke-simple
planner-auto add-context <id> --file planner-auto/planner_auto/cli.py
planner-auto discuss <id> "Add a --json flag to the status command that outputs JSON instead of formatted text" --done
planner-auto generate <id>
planner-auto review <id> --verbose
planner-auto inspect reviews <id>
planner-auto inspect config <id>
planner-auto export <id>
```

**Verify:**
- Review loop converges (GO or cap with zero criticals)
- Artifacts exported with correct interleaved naming (a-01-plan.md, a-02-review.md, ...)
- Review metadata persisted (model, cost, tokens per round)
- Dispositions stored (ACCEPT/DEFER/REJECT per issue)
- Session log file captures all module activity
- Total cost accumulated correctly

**Complex feature (tests convergence strategy):**
```bash
planner-auto start --project smoke-complex
planner-auto add-context <id> --file planner-auto/planner_auto/loop/engine.py
planner-auto discuss <id> "Add WebSocket support for real-time review loop progress streaming to a browser dashboard" --done
planner-auto generate <id>
planner-auto review <id> --verbose
```

**Verify:**
- Complexity detected as "complex" (WebSocket, streaming, real-time)
- Higher cap applied (12 instead of 8)
- Review history includes cumulative deferred context
- Cost tracked across all rounds

### Level 3: Edge Cases and Failure Paths

| Test | What It Stresses | How to Run | Expected Behavior |
|------|-----------------|-----------|-------------------|
| **Resume after cap-hit** | Round numbering, blocker lifecycle | Run `review --max-rounds 2`, let it pause, then `resume` + `review` again | Rounds continue from 3, not 1. Blocker resolved. |
| **Large context** | SDK subprocess limits, prompt size | Add 10+ files (400KB total), generate, review | Plan generated (may be slow). No crash. |
| **Fast mode** | Config wiring, artifact headers | `review --fast` | Artifacts have `[FAST MODE]` header. Cap at 4 rounds. No history/validation. |
| **Invalid API key** | Error handling | Unset `OPENAI_API_KEY`, run `review` | Clean error message, no traceback (unless --debug). Session stays REVIEW. |
| **Invalid Claude key** | Error handling | Unset `ANTHROPIC_API_KEY`, run `generate` | Clean error message. Session stays PLANNING. |
| **Concurrent sessions** | DB locking, log isolation | Start 2 sessions, review both simultaneously | Each gets own log file. DB not locked. No cross-talk. |
| **Empty/vague feature** | Plan validation, convergence | `discuss <id> "Fix bugs" --done`, generate, review | Plan may be thin. Validation warns. Review may not converge. |
| **Kill mid-review** | Session recovery, DB consistency | Ctrl+C during round 3 of review | Session stays REVIEW (not corrupted). `review` can resume from round 4. |
| **Schema migration** | DB upgrade path | Copy a Plan 1 DB, run `review` against it | Schema migrated v1→v2. Existing data preserved. Reviews table rebuilt. |
| **20+ rounds** | Cost accumulation, plan bloat | `review --max-rounds 20` on complex feature | Cost accumulates correctly. Plan size tracked. Cap-hit creates blocker. |
| **No git repo** | .kafra handoff | Run from `/tmp` | Handoff skips with warning. Session still completes normally. |
| **Duplicate context** | UPSERT behavior | Add same file twice | Second add replaces content (UPSERT). No duplicate in DB. |
| **--repo-root override** | Handoff targeting | `review --repo-root /path/to/other/repo` | Final plan copied to specified repo's `.kafra/a-01-plans/`. |
| **Debug output** | Traceback printing, sensitive data | `review --debug` | Full tracebacks on error. Raw GPT responses in output. Security warning printed. |

---

## Automated Smoke Test Script

A script that runs the core happy paths automatically. Requires API keys set.

```bash
#!/bin/bash
# scripts/smoke_test_planner.sh
# Run: ./scripts/smoke_test_planner.sh
# Requires: ANTHROPIC_API_KEY and OPENAI_API_KEY set
set -euo pipefail

echo "=== Planner-Auto Smoke Test ==="
echo ""

# 1. Simple session lifecycle (no review)
echo "--- Test 1: Simple lifecycle ---"
SID=$(planner-auto start --project smoke-lifecycle 2>&1 | grep "Session created:" | awk '{print $3}')
echo "Session: $SID"
planner-auto add-context $SID --note "Simple test project"
planner-auto discuss $SID "Add a health check endpoint that returns JSON status" --done
planner-auto generate $SID
planner-auto status $SID
planner-auto complete $SID
echo "PASS: Simple lifecycle"
echo ""

# 2. Review loop with 2-round cap
echo "--- Test 2: Review loop (cap=2) ---"
SID=$(planner-auto start --project smoke-review 2>&1 | grep "Session created:" | awk '{print $3}')
echo "Session: $SID"
planner-auto add-context $SID --note "Flask app with SQLAlchemy"
planner-auto discuss $SID "Add input validation to the user registration endpoint" --done
planner-auto generate $SID
planner-auto review $SID --max-rounds 2
planner-auto status $SID
echo "PASS: Review loop"
echo ""

# 3. Fast mode
echo "--- Test 3: Fast mode ---"
SID=$(planner-auto start --project smoke-fast 2>&1 | grep "Session created:" | awk '{print $3}')
echo "Session: $SID"
planner-auto add-context $SID --note "Express.js REST API"
planner-auto discuss $SID "Add a --json flag to the list command" --done
planner-auto generate $SID
planner-auto review $SID --fast
planner-auto status $SID
echo "PASS: Fast mode"
echo ""

# 4. No git repo (handoff skip)
echo "--- Test 4: No git repo ---"
TMPDIR=$(mktemp -d)
pushd $TMPDIR > /dev/null
SID=$(planner-auto start --project smoke-no-git 2>&1 | grep "Session created:" | awk '{print $3}')
echo "Session: $SID (from $TMPDIR)"
planner-auto discuss $SID "Add logging" --done
planner-auto generate $SID
planner-auto complete $SID
popd > /dev/null
rm -rf $TMPDIR
echo "PASS: No git repo"
echo ""

# 5. Environment check
echo "--- Test 5: Health check ---"
planner-auto check
echo "PASS: Health check"
echo ""

echo "=== All smoke tests passed ==="
```

---

## When to Run

| Trigger | Which Tests |
|---------|-------------|
| After implementing a milestone | Level 1 (local walkthrough) |
| After completing Plan 2 or Observability plan | Level 2 (live API smoke) |
| Before first real user session | Level 2 + Level 3 edge cases |
| After SDK upgrade or dependency change | Level 2 + "Kill mid-review" + "Large context" |
| Before Homebrew publishing | Full Level 1 + 2 + 3 |

---

## Success Criteria

| Criteria | Threshold |
|----------|-----------|
| Simple lifecycle completes | start → add-context → discuss → generate → complete with no errors |
| Review loop converges | GO or cap-hit within expected rounds (3-5 simple, 4-8 complex) |
| Resume after pause works | Rounds continue from correct number, blocker resolved |
| Cost tracking accurate | total_cost > 0, matches sum of per-round costs |
| Artifacts correct | Interleaved naming, final plan exists, .kafra copy (when in git repo) |
| Error messages actionable | Missing API key → clear message with env var name |
| No data corruption | DB state consistent after Ctrl+C, concurrent sessions, schema migration |
| Logs capture full session | Session log file contains entries from all modules with session_id |

---

## Dependencies

- `planner-auto` installed with `pip install -e ".[dev]"`
- `ANTHROPIC_API_KEY` set (for Claude)
- `OPENAI_API_KEY` set (for GPT reviewer)
- Level 2 and 3 tests cost real money (~$1-5 per full run)
- Observability plan should be implemented first so smoke tests can verify logging
