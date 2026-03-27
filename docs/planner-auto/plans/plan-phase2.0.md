# Planner-Auto Reviewer Adapter (Plan 2) - Implementation Plan

## Overview
Add the GPT-5.4 review loop to the existing planner-auto CLI (Plan 1). GPT reviews each plan draft, Claude revises based on validated feedback, and the loop repeats until GPT says GO or a complexity-aware cap is reached. Review history gives GPT context continuity across rounds. The final approved plan is exported and copied to `.kafra/a-01-plans/` for orchestrator-auto.

## Milestone 1: ReviewerContract Interface and Response Parser

Define the reviewer contract, implement the response parser with JSON/XML/free-form fallback, and add the `openai` dependency.

### Tasks
- [ ] Add `openai>=2.0` to `pyproject.toml` dependencies.
- [ ] Create `planner_auto/reviewer/__init__.py` and `planner_auto/reviewer/contract.py` with `ReviewerContract` abstract base class: `async review(plan_text: str, previous_context: str | None) -> ReviewerResponse`. Define `ReviewerResponse` dataclass: `verdict` (GO/NO_GO), `issues` (list of `ReviewIssue`), `summary`, `keep` (list[str]), `trim` (list[str]). Define `ReviewIssue` dataclass: `severity` (critical/major/minor), `description`, `rationale`, `resolution_guidance`, `target_section`.
- [ ] Create `planner_auto/reviewer/parser.py` with `parse_reviewer_response(raw_text: str) -> ReviewerResponse`. Three-stage fallback: JSON (including markdown-fenced) → XML tagged → free-form keyword matching. On parse failure return NO_GO with a single critical "could not be parsed" issue. Port logic from `scripts/poc/planner-auto/poc_parse_go_nogo.py`.
- [ ] Create `planner_auto/reviewer/prompts.py` with three prompt constants: `REVIEWER_SYSTEM_PROMPT` (basic), `REVIEWER_SYSTEM_PROMPT_WITH_GUIDANCE` (adds resolution_guidance + target_section), `REVIEWER_SYSTEM_PROMPT_WITH_KEEP_TRIM` (adds keep/trim sections). Include `USER_PROMPT_TEMPLATE` with `{plan_text}` placeholder.
- [ ] Create `tests/test_parser.py` with 14+ test cases: clean GO/NO_GO JSON, GO with notes, NO_GO minor only, XML tagged, free-form GO/NO_GO, malformed/empty/partial, conflicting signals, markdown-fenced JSON, unicode, keep/trim extraction. Port from POC 2a.
- [ ] Create `tests/test_contract.py` verifying `ReviewerResponse` and `ReviewIssue` dataclass construction, serialization to JSON, and default values for optional fields.

### Deliverables
- [ ] `planner_auto/reviewer/contract.py` with `ReviewerContract` ABC, `ReviewerResponse`, `ReviewIssue`
- [ ] `planner_auto/reviewer/parser.py` with three-stage parse fallback
- [ ] `planner_auto/reviewer/prompts.py` with three prompt variants
- [ ] `pytest tests/test_parser.py tests/test_contract.py` passes with 16+ tests

## Milestone 2: Direct API Reviewer Adapter

Implement the GPT-5.4 reviewer via OpenAI SDK with configurable reasoning effort and system prompt selection.

### Tasks
- [ ] Create `planner_auto/reviewer/direct_api.py` with `DirectAPIAdapter(ReviewerContract)`. Constructor accepts `model` (default "gpt-5.4"), `reasoning_effort` (default "high"), `prompt_mode` ("basic", "guidance", "keep_trim"). Method `async review(plan_text, previous_context)`: builds messages list, calls `openai.AsyncOpenAI().chat.completions.create()`, parses response via `parse_reviewer_response()`, returns `ReviewerResponse`. When `reasoning_effort` is set, omit `temperature` (OpenAI requirement). When `previous_context` is provided, prepend to user prompt with instructions to focus on new issues.
- [ ] Add error handling: `openai.AuthenticationError` → `ReviewerAuthError`, `openai.RateLimitError` → retry 3x with 2/4/8s backoff, timeout → retry once after 2s. All custom errors in `planner_auto/errors.py`.
- [ ] Log every review call: model, latency, token usage (input + output), verdict, issue count.
- [ ] Create `tests/test_direct_api.py` with mocked OpenAI client: successful GO review, successful NO_GO review, auth error propagation, rate limit with retry exhaustion, timeout with retry, parse failure on malformed response, previous_context inclusion in prompt, reasoning_effort disables temperature. 10+ tests.

### Deliverables
- [ ] `planner_auto/reviewer/direct_api.py` with `DirectAPIAdapter` implementing `ReviewerContract`
- [ ] Reviewer errors added to `planner_auto/errors.py`
- [ ] `pytest tests/test_direct_api.py` passes with 10+ mocked tests

## Milestone 3: Review-Fix Loop Engine

Implement the core loop that orchestrates GPT review → Claude revision → repeat, with feedback validation, severity filtering, and review history.

### Tasks
- [ ] Create `planner_auto/loop/__init__.py` and `planner_auto/loop/engine.py` with `ReviewLoopEngine` class. Constructor accepts `conn`, `session_id`, `reviewer` (ReviewerContract), `planner_model`, `config` (dict of flags). Method `async run(current_plan: str, max_rounds: int) -> LoopResult`. `LoopResult` dataclass: `converged` (bool), `rounds` (int), `final_plan` (str), `final_draft_number` (int), `total_cost` (float), `round_details` (list).
- [ ] Each round: call `reviewer.review()` → parse → store review in DB via `add_review()` → export `a-{2*N:02d}-review.md` → check verdict → if GO, break → if NO_GO, build revision prompt → call Claude via `sdk_wrapper.query_claude()` → store draft via `add_plan_draft()` → export `a-{2*round:02d+1}-plan.md`.
- [ ] Create `planner_auto/loop/feedback.py` with `validate_feedback(plan_text: str, review: ReviewerResponse, planner_model: str) -> ReviewerResponse`. Calls Claude with a prompt that assesses each issue as ACCEPT/DEFER/REJECT. Returns a filtered `ReviewerResponse` with only accepted issues. Only active when `validate_feedback=True` in config.
- [ ] Create `planner_auto/loop/history.py` with `build_review_context(previous_plan: str, previous_review_raw: str) -> str`. Formats previous plan (capped at 5000 chars) and previous review (capped at 3000 chars) with instructions: "focus on whether issues were resolved, flag only NEW issues, don't re-raise deferred items."
- [ ] Severity filtering in the loop: before passing issues to Claude, filter by configured severity levels (default: critical + major). Minor issues are stored in DB but not sent to revision prompt.
- [ ] Revision prompt construction: include current plan, filtered issues with resolution_guidance (if enabled), keep/trim sections (if enabled), and validate feedback instructions (if enabled). Explicitly instruct Claude: "Do not add scope beyond what's needed."
- [ ] Create `tests/test_engine.py` with mocked reviewer and SDK: loop converges on GO at round 2, loop hits cap and stops, severity filter removes minor issues, review history passes previous context, round details tracked correctly, artifacts exported per round. 10+ tests.

### Deliverables
- [ ] `planner_auto/loop/engine.py` with `ReviewLoopEngine` and `LoopResult`
- [ ] `planner_auto/loop/feedback.py` with `validate_feedback()`
- [ ] `planner_auto/loop/history.py` with `build_review_context()`
- [ ] `pytest tests/test_engine.py` passes with 10+ tests

## Milestone 4: Convergence, Complexity Detection, and Fast Mode

Implement complexity-aware caps, fast mode, and cap-hit blocker behavior.

### Tasks
- [ ] Create `planner_auto/loop/convergence.py` with `detect_complexity(feature_description: str) -> str` returning "standard" or "complex". Scans for keywords: concurrent, lock, retry, backoff, queue, dead-letter, idempotent, dedup, signature, hmac, token, encrypt, state machine, transition, schedule, cron, expir. Log detected level and matching keywords. Add `get_max_rounds(complexity: str, fast: bool) -> int`: standard=8, complex=12, fast=4.
- [ ] Add `--complexity` flag to allow manual override ("standard", "complex").
- [ ] Cap-hit behavior: when max rounds exhausted and criticals remain, create a blocker via `SessionManager.pause_with_blocker()` with source="review_cap" and question listing remaining critical issues. Session enters PAUSED. User resolves via `planner-auto resume`.
- [ ] Cap-hit without criticals: treat as converged (accept plan as implementation-ready). Mark session COMPLETE.
- [ ] Fast mode config: `--fast` flag sets `review_history=False`, `validate_feedback=False`, `keep_trim=False`, `max_rounds=4`. Fast-mode sessions have `config_json` tagged with `"mode": "fast"`. Export artifacts include a `[FAST MODE]` header note.
- [ ] Create `tests/test_convergence.py`: complexity detection for standard feature, complex feature, manual override, round caps, cap-hit with criticals creates blocker, cap-hit without criticals completes, fast mode config. 8+ tests.

### Deliverables
- [ ] `planner_auto/loop/convergence.py` with `detect_complexity()` and `get_max_rounds()`
- [ ] Cap-hit blocker behavior tested end-to-end
- [ ] Fast mode flag wired through config
- [ ] `pytest tests/test_convergence.py` passes with 8+ tests

## Milestone 5: CLI Integration, Artifact Export, and .kafra Handoff

Wire the review loop into the CLI, extend artifact export for review rounds, and implement .kafra pipeline handoff.

### Tasks
- [ ] Add `review` subcommand to `planner_auto/cli.py`: `planner-auto review <session-id>`. Validates session is in PLANNING or REVIEW phase. Creates `DirectAPIAdapter` with configured model/reasoning/prompt mode. Creates `ReviewLoopEngine` with all flags. Runs the loop. On convergence: advances phase to COMPLETE, exports final plan. On cap-hit: behavior depends on criticals (blocker or complete). Flags: `--fast`, `--max-rounds`, `--no-review-history`, `--reviewer-model`, `--reviewer-reasoning`.
- [ ] Extend `planner_auto/export.py` with `export_review_artifacts(session_id, conn, output_dir)`: exports interleaved plan/review files using the `a-{NN}-plan.md` / `a-{NN}-review.md` naming convention. Review files include verdict, summary, issues with resolution_guidance, keep/trim sections. Final plan exported as `a-{N}-plan-final.md`.
- [ ] Implement `.kafra` handoff: on session completion, copy `a-{N}-plan-final.md` to `<repo>/.kafra/a-01-plans/<project-name>.md`. Create `.kafra/a-01-plans/` directory if it doesn't exist. Skip if not in a git repo.
- [ ] Extend `session_config` to capture reviewer settings: `reviewer_model`, `reasoning_effort`, `prompt_mode`, `review_history`, `validate_feedback`, `filter_severity`, `keep_trim`, `fast_mode`, `complexity`, `max_rounds`.
- [ ] Update `state.py`: add `"review"` to PLANNING's allowed commands. Ensure REVIEW→COMPLETE and REVIEW→PLANNING transitions work.
- [ ] Create `tests/test_review_cli.py` using Click's `CliRunner`: `review` command on session in PLANNING phase, `review` rejects session in SETUP, `--fast` flag sets config correctly, convergence triggers COMPLETE, cap-hit with criticals creates blocker. Create `tests/test_review_export.py`: interleaved plan/review file naming, final plan export, .kafra copy. 10+ tests total.
- [ ] Run full test suite `pytest tests/` to confirm all Plan 1 + Plan 2 tests pass together.

### Deliverables
- [ ] `planner-auto review <id>` runs the full review loop with configurable flags
- [ ] Review artifacts exported with correct interleaved naming
- [ ] Final plan copied to `.kafra/a-01-plans/` on completion
- [ ] Config snapshot includes all reviewer settings
- [ ] `pytest tests/` passes with all tests green (Plan 1 + Plan 2)
