# Changelog

All notable changes to planner-auto will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-03-28

### Added

- **Observability & Debug system** — Shared root logger with `SessionFilter` for session-id context injection. All modules use `logging.getLogger(__name__)` as children of the `planner_auto` root logger. Session log files at `~/.planner-auto/logs/<session-id>.log` capture all module activity.
- **`inspect` CLI subgroup** — 6 commands for debugging sessions from the terminal: `reviews`, `dispositions`, `config`, `history` (reconstructed from DB), `raw-response`, `dump` (pure JSON with `--output` option). Security warning on sensitive output.
- **`check` command** — Environment validation: API keys, SDK imports, DB writability, schema version. Safe by default (no API calls); `--probe` for live API round-trips.
- **Three-tier review loop output** — `quiet` (one line per round, headless-safe), `verbose` (full metrics, dispositions, keep/trim), `debug` (raw GPT response, history context, revision prompt with security warnings). Engine owns all output; CLI does not duplicate.
- **`--verbose` and `--debug` flags on all session-aware commands** — `start`, `discuss`, `generate`, `review`, `export`, `complete`, `resume`, `add-context`, `status`.
- **Structured logging** — 49+ log calls across all modules at key decision points: phase transitions, SDK calls, review rounds, dispositions, convergence detection, artifact export.
- **Error diagnostics** — `--debug` prints full stack traces on all commands. Without `--debug`, one-line error messages only.
- **`planner-auto-debugger` agent** — Claude Code agent definition with codebase map, debugging toolkit (CLI + SQL + log queries), 6 common failure patterns with diagnosis steps.
- **`AGENTS.md`** — Developer context file: architecture, design rules, what-NOT-to-do, common development tasks.

---

## [0.2.0] - 2026-03-28

### Added

- **GPT-5.4 review loop** — `planner-auto review <session-id>` runs automated multi-round plan review via OpenAI Direct API. GPT reviews → Claude revises → repeat until convergence.
- **`ReviewerContract` interface** — Abstract base class with `ReviewerResponse` and `ReviewIssue` dataclasses. Supports verdict (GO/NO_GO), issues with severity/description/rationale/resolution_guidance/target_section, keep/trim lists, and metadata (model, cost, tokens, raw_text).
- **Response parser** — Three-stage fallback: JSON (including markdown-fenced) → XML tagged → free-form keyword matching. On parse failure returns NO_GO with "could not be parsed" critical issue.
- **`DirectAPIAdapter`** — GPT-5.4 via OpenAI SDK with configurable `reasoning_effort` and `prompt_mode` (basic/guidance/keep_trim). Retry logic: rate limit 3x with 2/4/8s backoff, timeout 1 retry. Cost calculated from token counts.
- **Review-fix loop engine** — `ReviewLoopEngine` orchestrates rounds with stop policy: GO → complete, cap+no-criticals → complete, cap+criticals → pause with blocker.
- **Feedback validation** — Claude assesses each issue as ACCEPT/DEFER/REJECT. Dispositions stored in `review_dispositions` table per issue per round. Only ACCEPT issues passed to revision prompt.
- **Review history** — GPT sees previous plan + previous review + cumulative DEFER decisions from ALL prior rounds. Prevents re-raising deferred issues across long loops.
- **Severity filtering** — Only critical + major issues reach Claude. Minor issues stored in DB but not acted on.
- **Keep/trim sections** — GPT tells Claude what to preserve and what to simplify in each review.
- **Complexity detection** — Auto-detects complex features from first user message and plan content keywords (concurrency, retry, idempotency, signatures, state machines, etc.). Complexity-aware caps: standard=8, complex=12.
- **Fast mode** — `--fast` flag: history OFF, validate OFF, keep_trim OFF, basic prompt, cap=4. Sessions tagged `"mode": "fast"` in config. Artifacts get `[FAST MODE]` header.
- **Round resume** — After cap-hit pause, `review` continues from next round number (not round 1). `UNIQUE(session_id, round_number)` prevents collisions.
- **Schema migration (v1 → v2)** — `schema_version` table tracks version. Reviews table rebuilt with new columns: `round_number`, `issues_json`, `summary`, `raw_response`, `reviewer_model`, `cost`, `input_tokens`, `output_tokens`. Legacy rows preserved with `round_number=NULL`.
- **`review_dispositions` table** — Per-issue ACCEPT/DEFER/REJECT with rationale per round.
- **Repo root discovery** — `git rev-parse --show-toplevel` at session start, `--repo-root` override on `start` and `review` commands, fallback re-discovery at review/complete time.
- **`.kafra` handoff** — Final plan copied to `<repo>/.kafra/a-01-plans/<project>.md` on completion. Skips with warning if no repo root.
- **Interleaved artifact export** — `a-01-plan.md`, `a-02-review.md`, `a-03-plan.md`, etc. Reviews include verdict, issues, resolution guidance, keep/trim. Final plan as `a-{N}-plan-final.md`.
- **Extended `sdk_wrapper.py`** — `query_claude()` accepts `effort`, `thinking`, `max_turns` params. Unlimited turns with thinking mode. `ThinkingConfigAdaptive` support.
- **Absolute context file paths** — Files stored with full absolute paths in `context_entries` for unambiguous repo root inference.
- **Extended `session_config`** — Captures reviewer settings: model, reasoning_effort, prompt_mode, review_history, validate_feedback, filter_severity, keep_trim, fast_mode, complexity, max_rounds, repo_root.

### Changed

- **`state.py`** — Added `"review"` to PLANNING and REVIEW allowed commands. PLANNING→REVIEW transition via `review` command.
- **`export.py`** — Extended with `export_review_artifacts()` and `kafra_handoff()`.
- **`errors.py`** — Added `ReviewerAuthError`, `ReviewerRateLimitError`, `ReviewerTimeoutError`.
- **`pyproject.toml`** — Added `openai>=2.0` dependency.

---

## [0.1.2] - 2026-03-28

### Fixed

- **Atomic persistence** — Removed auto-commit from all CRUD functions. Added `transaction()` context manager. `discuss()` and `generate_plan()` commit atomically. Callers manage transaction boundaries.
- **Timeout enforcement** — `sdk_wrapper.py` wraps SDK call in `asyncio.wait_for()`. Hung calls raise `SDKTimeoutError` instead of blocking forever.
- **PLANNING→COMPLETE path** — Added direct transition for Plan 1 (REVIEW phase is Plan 2). Added `"complete"` to PLANNING and REVIEW allowed commands.
- **`complete` checks PAUSED status** — Added `SessionManager.check_command()` call. Also enforces phase rules (not just blockers).
- **One-shot discuss `--done` flag** — Advances to PLANNING after message. Only advances on success (not on SDK failure).
- **Timeout retries independent** — Separate `timeout_retries_used` counter, not coupled to rate-limit loop.
- **SDK logging includes token count** — `_execute_query()` returns `(text, usage_info)` tuple. Logger prints input+output tokens.
- **Build artifacts removed** — `.gitignore` added. `.egg-info/` and `__pycache__/` untracked.

---

## [0.1.1] - 2026-03-27

### Added

- **POC validation complete** — 13 POC scripts across 4 phases, all passing. Validated: parser (14/14), session DB (13/13), Direct API reviewer (3/3), structured prompts (12/12), artifact export (14/14), planner headless (23/23), Codex MCP (1/1), OpenCode HTTP (1/1), context synthesis (11/11), failure paths (18/18), reviewer comparison (2/3), end-to-end loop (5/5 DB checks).
- **11 convergence experiments** — Discovered review history as the key convergence mechanism. Registration: GO at R5 ($0.87). Webhook: GO at R4 with history ($0.62), never converged without. Full experiment data in `scripts/poc/planner-auto/POC_STATUS.md`.

---

## [0.1.0] - 2026-03-27

### Added

- **Initial release — Session Core (Plan 1)**
- **CLI commands** — `start`, `add-context` (file + note), `discuss` (single + interactive), `generate`, `list`, `status`, `resume`, `export`, `complete`.
- **SQLite persistence** — 7 tables: `sessions`, `messages`, `context_entries`, `plan_drafts`, `reviews`, `blockers`, `session_config`. WAL mode, foreign keys.
- **Session lifecycle** — SETUP → CONTEXT → DISCUSSION → PLANNING → COMPLETE. Phase-gated commands via `SessionManager`.
- **Context loading** — UTF-8 file validation, 500KB limit, UPSERT on duplicate, note support.
- **Context synthesis** — On-demand synthesis via Claude Haiku before plan generation.
- **Plan generation** — Claude Sonnet/Opus via Agent SDK. Constrained planner prompt (max 8 tasks/milestone, under 3000 words, scope-locked).
- **Plan validation** — Milestone header format, sequential numbering, tasks/deliverables sections.
- **Artifact export** — `chat.csv`, `context-summary.md`, `plan-draft-N.md`. Idempotent re-export.
- **Blocker lifecycle** — Pause/resume with source, question, answer tracking.
- **Config versioning** — `session_config` table captures model, prompt hashes at session start.
- **Session-scoped logging** — Log files at `~/.planner-auto/logs/<session-id>.log`.
- **103 tests** — Full coverage of DB, CLI, session, agents, SDK wrapper, export, validation.
