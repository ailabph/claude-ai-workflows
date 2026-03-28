# Planner-Auto Reviewer Adapter (Plan 2) - Implementation Plan v2.1

## Overview

Add the GPT-5.4 review loop to the existing planner-auto CLI (Plan 1). GPT reviews each plan draft, Claude revises based on validated feedback, and the loop repeats. Review history (including ACCEPT/DEFER/REJECT dispositions from prior rounds) gives GPT context continuity.

### Stop Policy (Deterministic)

The loop stops when ANY of these conditions is met, checked in order:

1. **GPT says GO** → session COMPLETE, export final plan
2. **Cap reached, zero criticals remaining** → session COMPLETE, export final plan (treated as implementation-ready)
3. **Cap reached, criticals remaining** → session PAUSED, blocker created listing remaining criticals, user must intervene via `planner-auto resume`

Round caps are complexity-aware:
- Standard features: 8 rounds
- Complex features: 12 rounds
- Fast mode: 4 rounds
- Emergency ceiling: 20 rounds (manual override only via `--max-rounds`)

### .kafra Handoff Contract

On session COMPLETE, the final plan is copied to `<repo>/.kafra/a-01-plans/<project>.md`. Repo root is discovered at session start via `git rev-parse --show-toplevel` and stored in `session_config.config_json["repo_root"]`. If not in a git repo, repo_root is null and .kafra handoff is skipped with a warning.

## Milestone 1: Schema Migration, SDK Wrapper Extension, and Repo Root Discovery

Extend the existing DB schema and SDK wrapper to support Plan 2's requirements before building reviewer modules.

### Tasks
- [ ] Extend `reviews` table in `planner_auto/db.py` `init_schema()`: add columns `round_number INTEGER NOT NULL`, `issues_json TEXT` (JSON array of issues with severity/description/rationale/guidance/target), `summary TEXT`, `raw_response TEXT`, `reviewer_model TEXT`, `cost REAL`, `input_tokens INTEGER`, `output_tokens INTEGER`. Keep existing `verdict` and `content` columns for backward compatibility. Add `UNIQUE(session_id, round_number)`.
- [ ] Create `review_dispositions` table: `id INTEGER PK AUTOINCREMENT`, `review_id INTEGER REFERENCES reviews(id)`, `issue_index INTEGER NOT NULL`, `disposition TEXT NOT NULL CHECK(disposition IN ('ACCEPT','DEFER','REJECT'))`, `rationale TEXT`, `created_at TEXT DEFAULT CURRENT_TIMESTAMP`. This persists Claude's ACCEPT/DEFER/REJECT decisions per issue per round.
- [ ] Add CRUD functions: `add_review_v2(conn, session_id, round_number, verdict, issues_json, summary, raw_response, reviewer_model, cost, input_tokens, output_tokens, draft_id)`, `add_disposition(conn, review_id, issue_index, disposition, rationale)`, `get_dispositions(conn, review_id) -> list[dict]`, `get_review_by_round(conn, session_id, round_number) -> dict | None`.
- [ ] Extend `query_claude()` in `planner_auto/sdk_wrapper.py` to accept optional `effort`, `thinking`, and `max_turns` parameters. When `thinking=True`, set `ThinkingConfigAdaptive(type="adaptive")` on options. When `max_turns` is provided, override the default `max_turns=1`. When `effort` is provided, set `opts.effort`. Import `ThinkingConfigAdaptive` from `claude_agent_sdk.types`.
- [ ] Add `discover_repo_root() -> str | None` to `planner_auto/cli.py` (or a new `planner_auto/git_utils.py`): runs `git rev-parse --show-toplevel` via `subprocess.run`, returns path or None if not in a git repo. Call this in the `start` command and store in `session_config.config_json["repo_root"]`.
- [ ] Create `tests/test_db_v2.py`: test new review columns round-trip, review_dispositions CRUD, unique constraint on (session_id, round_number), backward compatibility (old-style add_review still works). Create `tests/test_sdk_wrapper_v2.py`: test effort/thinking/max_turns passed to SDK options (mocked). Test `discover_repo_root` with and without git. 10+ tests total.

### Deliverables
- [ ] `reviews` table extended with round_number, issues_json, summary, raw_response, reviewer_model, cost, tokens
- [ ] `review_dispositions` table created with ACCEPT/DEFER/REJECT per issue
- [ ] `query_claude()` accepts effort, thinking, max_turns parameters
- [ ] Repo root discovered and stored at session start
- [ ] `pytest tests/test_db_v2.py tests/test_sdk_wrapper_v2.py` passes with 10+ tests

## Milestone 2: ReviewerContract Interface and Response Parser

Define the reviewer contract, implement the response parser with JSON/XML/free-form fallback, and add the `openai` dependency.

### Tasks
- [ ] Add `openai>=2.0` to `pyproject.toml` dependencies.
- [ ] Create `planner_auto/reviewer/__init__.py` and `planner_auto/reviewer/contract.py` with `ReviewerContract` abstract base class: `async review(plan_text: str, previous_context: str | None) -> ReviewerResponse`. Define `ReviewerResponse` dataclass: `verdict` (GO/NO_GO enum), `issues` (list of `ReviewIssue`), `summary` (str), `keep` (list[str]), `trim` (list[str]). Define `ReviewIssue` dataclass: `severity` (CRITICAL/MAJOR/MINOR enum), `description` (str), `rationale` (str), `resolution_guidance` (str, default ""), `target_section` (str, default "").
- [ ] Create `planner_auto/reviewer/parser.py` with `parse_reviewer_response(raw_text: str) -> ReviewerResponse`. Three-stage fallback: JSON (including markdown-fenced) → XML tagged → free-form keyword matching. On parse failure return NO_GO with a single critical "could not be parsed" issue. Port logic from `scripts/poc/planner-auto/poc_parse_go_nogo.py`.
- [ ] Create `planner_auto/reviewer/prompts.py` with three system prompt constants: `REVIEWER_SYSTEM_PROMPT` (basic: verdict + issues + summary), `REVIEWER_SYSTEM_PROMPT_WITH_GUIDANCE` (adds resolution_guidance + target_section per issue), `REVIEWER_SYSTEM_PROMPT_WITH_KEEP_TRIM` (adds keep[] and trim[] lists). Include `USER_PROMPT_TEMPLATE` with `{plan_text}` placeholder.
- [ ] Create `tests/test_parser.py` with 14+ test cases ported from POC 2a. Create `tests/test_contract.py` verifying dataclass construction, JSON serialization, enum values, and default fields.

### Deliverables
- [ ] `planner_auto/reviewer/contract.py` with `ReviewerContract` ABC, `ReviewerResponse`, `ReviewIssue`
- [ ] `planner_auto/reviewer/parser.py` with three-stage parse fallback
- [ ] `planner_auto/reviewer/prompts.py` with three prompt variants
- [ ] `pytest tests/test_parser.py tests/test_contract.py` passes with 16+ tests

## Milestone 3: Direct API Reviewer Adapter

Implement the GPT-5.4 reviewer via OpenAI SDK with configurable reasoning effort and system prompt selection.

### Tasks
- [ ] Create `planner_auto/reviewer/direct_api.py` with `DirectAPIAdapter(ReviewerContract)`. Constructor accepts `model` (default "gpt-5.4"), `reasoning_effort` (default "high"), `prompt_mode` ("basic", "guidance", "keep_trim"). Method `async review(plan_text, previous_context)`: builds messages, calls `openai.AsyncOpenAI().chat.completions.create()`, parses via `parse_reviewer_response()`, returns `ReviewerResponse`. When `reasoning_effort` is set, omit `temperature` (OpenAI requires default temp with reasoning). When `previous_context` is provided, prepend to user prompt with instructions to focus on new issues and not re-raise deferred items.
- [ ] Add error handling: `openai.AuthenticationError` → `ReviewerAuthError`, `openai.RateLimitError` → retry 3x with 2/4/8s backoff, timeout → retry once after 2s. Custom errors in `planner_auto/errors.py`.
- [ ] Log every review call: model, latency, input_tokens, output_tokens, verdict, issue count.
- [ ] Create `tests/test_direct_api.py` with mocked OpenAI client: successful GO, successful NO_GO, auth error, rate limit exhaustion, timeout retry, parse failure, previous_context in prompt, reasoning_effort disables temperature. 10+ tests.

### Deliverables
- [ ] `planner_auto/reviewer/direct_api.py` with `DirectAPIAdapter`
- [ ] Reviewer errors in `planner_auto/errors.py`
- [ ] `pytest tests/test_direct_api.py` passes with 10+ mocked tests

## Milestone 4: Review-Fix Loop Engine with Feedback Validation and History

Implement the core loop: GPT review → feedback validation → Claude revision → repeat, with review history built from stored dispositions.

### Tasks
- [ ] Create `planner_auto/loop/__init__.py` and `planner_auto/loop/engine.py` with `ReviewLoopEngine`. Constructor: `conn`, `session_id`, `reviewer` (ReviewerContract), `planner_model`, `config` (dict). Method `async run(current_plan: str, max_rounds: int) -> LoopResult`. `LoopResult`: `converged` (bool), `rounds` (int), `final_plan` (str), `final_draft_number` (int), `total_cost` (float), `round_details` (list), `stop_reason` ("go", "cap_no_criticals", "cap_with_criticals").
- [ ] Each round: (1) call `reviewer.review(plan, history_context)` → (2) store review in DB via `add_review_v2()` with all metadata → (3) export `a-{2*round_num:02d}-review.md` → (4) apply stop policy (GO → break; see Overview) → (5) filter issues by severity (default: critical+major, store all, pass only filtered to revision) → (6) if `validate_feedback` enabled, call `validate_feedback()` and store dispositions → (7) build revision prompt with filtered issues, keep/trim, resolution_guidance → (8) call Claude via `query_claude()` with effort/thinking/max_turns from config → (9) store draft via `add_plan_draft()` → (10) export `a-{2*round_num+1:02d}-plan.md`.
- [ ] Create `planner_auto/loop/feedback.py` with `async validate_feedback(plan_text, review, planner_model, conn, review_id) -> ReviewerResponse`. Calls Claude with prompt: "Assess each issue. For each, respond ACCEPT (fix it), DEFER (valid but out of scope), or REJECT (not valid)." Stores each disposition in `review_dispositions` table via `add_disposition()`. Returns a new `ReviewerResponse` containing only ACCEPT issues.
- [ ] Create `planner_auto/loop/history.py` with `build_review_context(conn, session_id, current_round) -> str | None`. For round > 1: queries previous review + previous dispositions from DB. Builds context including: previous plan (capped 5000 chars), previous review verdict + issues, disposition for each issue (ACCEPT/DEFER/REJECT with rationale). Instructions to GPT: "Issues marked DEFER were intentionally scoped out — do not re-raise. Issues marked ACCEPT were fixed — verify they're resolved. Focus on NEW issues only."
- [ ] Severity filtering: `filter_issues(issues, severity_levels) -> list[ReviewIssue]`. Default levels: `["critical", "major"]`. All issues stored in DB; only filtered subset passed to revision prompt.
- [ ] Revision prompt: include current plan, filtered issues (with resolution_guidance if present), keep/trim sections (if present), instruction "Do not add scope beyond what's needed to address accepted issues. Keep the plan concise."
- [ ] Create `tests/test_engine.py`: loop converges on GO at round 2, loop hits cap with no criticals (stop_reason="cap_no_criticals"), loop hits cap with criticals (stop_reason="cap_with_criticals"), severity filter excludes minor, validate_feedback stores dispositions, history context includes dispositions from previous round, round details tracked correctly. 12+ tests.

### Deliverables
- [ ] `planner_auto/loop/engine.py` with `ReviewLoopEngine` and `LoopResult`
- [ ] `planner_auto/loop/feedback.py` with `validate_feedback()` storing dispositions
- [ ] `planner_auto/loop/history.py` with `build_review_context()` using stored dispositions
- [ ] `pytest tests/test_engine.py` passes with 12+ tests

## Milestone 5: Convergence, Complexity Detection, Fast Mode, CLI, and .kafra Handoff

Wire everything into the CLI, implement complexity-aware caps, fast mode, artifact export, and .kafra pipeline handoff.

### Tasks
- [ ] Create `planner_auto/loop/convergence.py` with `detect_complexity(feature_description: str) -> str` returning "standard" or "complex". Keywords: concurrent, lock, retry, backoff, queue, dead-letter, idempotent, dedup, signature, hmac, token, encrypt, state machine, transition, schedule, cron, expir. Log level + matching keywords. `get_max_rounds(complexity, fast) -> int`: standard=8, complex=12, fast=4. Allow `--complexity` manual override and `--max-rounds` direct override.
- [ ] Fast mode: `--fast` flag sets `review_history=False`, `validate_feedback=False`, `keep_trim=False`, `max_rounds=4`, `prompt_mode="basic"`. Fast-mode sessions tagged in config_json as `"mode": "fast"`. Artifacts get `[FAST MODE]` header.
- [ ] Add `review` subcommand to `planner_auto/cli.py`: `planner-auto review <session-id>`. Validates phase is PLANNING or REVIEW (via `SessionManager.check_command`). Advances to REVIEW if in PLANNING. Creates `DirectAPIAdapter` and `ReviewLoopEngine`. Runs loop. On convergence: advance to COMPLETE, export, .kafra handoff. On cap-hit: depends on stop_reason. Flags: `--fast`, `--max-rounds`, `--no-review-history`, `--reviewer-model`, `--reviewer-reasoning`, `--complexity`.
- [ ] Extend `planner_auto/export.py` with `export_review_artifacts(session_id, conn, output_dir)`: query all plan_drafts and reviews ordered by round, export interleaved `a-{NN}-plan.md` / `a-{NN}-review.md`. Review files include: verdict, summary, issues (with severity, resolution_guidance, target_section), keep/trim sections. Final plan as `a-{N}-plan-final.md`.
- [ ] Implement .kafra handoff: read `repo_root` from `session_config.config_json`. If present, copy final plan to `{repo_root}/.kafra/a-01-plans/{project}.md`. Create directory if needed. If repo_root is null, log warning and skip.
- [ ] Extend session_config snapshot: add `reviewer_model`, `reasoning_effort`, `prompt_mode`, `review_history`, `validate_feedback`, `filter_severity`, `keep_trim`, `fast_mode`, `complexity`, `max_rounds`, `repo_root`.
- [ ] Update `state.py`: add `"review"` to PLANNING's `PHASE_ALLOWED_COMMANDS`. Verify REVIEW→COMPLETE and REVIEW→PLANNING transitions exist (REVIEW→PLANNING for re-generation after review feedback).
- [ ] Create `tests/test_convergence.py`: complexity detection standard/complex, manual override, round caps, fast mode config. Create `tests/test_review_cli.py`: review from PLANNING, reject from SETUP, --fast config, convergence → COMPLETE, cap-hit blocker. Create `tests/test_review_export.py`: interleaved naming, final plan, .kafra copy with and without repo root. 14+ tests total.
- [ ] Run full suite `pytest tests/` confirming all Plan 1 + Plan 2 tests pass together.

### Deliverables
- [ ] `planner-auto review <id>` runs the full review loop
- [ ] Complexity detection and fast mode working
- [ ] Review artifacts exported with correct interleaved naming
- [ ] Final plan copied to `.kafra/a-01-plans/` when repo root available
- [ ] Config snapshot captures all reviewer settings
- [ ] `pytest tests/` passes with all tests green
