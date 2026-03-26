# POC 5b: End-to-End Review Loop

## Purpose

Prove the full review loop works end-to-end: plan → reviewer → parse → if NO_GO, feed issues to Claude → revised plan → reviewer again. Run 2-3 rounds with real API calls.

## What This Tests

- Full integration of all components: plan generation, reviewer invocation, response parsing, plan revision
- Claude can meaningfully revise a plan based on structured reviewer feedback
- The loop converges (reviewer eventually says GO, not infinite NO_GO)
- Artifact export at each step matches expected numbering
- DB state is consistent throughout the loop

## Input

- A feature description for Claude to generate the initial plan
- Real API calls to both Claude (planner) and GPT (reviewer via Direct API)

## Ideal Result

- Round 1: Claude generates plan → GPT reviews → NO_GO with issues
- Round 2: Claude revises plan based on issues → GPT reviews → GO (or fewer issues)
- Round 3 (if needed): Final revision → GO
- Session folder contains correctly numbered artifacts:
  `a-01-plan.md`, `a-02-review.md`, `a-03-plan.md`, `a-04-review.md`, ...
- DB reflects full history
- Total cost and time printed

## Dependencies

- `claude-agent-sdk` or `anthropic` SDK
- `openai` SDK
- `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` env vars
- POC 2a parser, POC 3a DB schema, POC 3b artifact export
- POC 4a planner headless (for representative Claude responses)

## Actual Results

- Full loop works end-to-end: plan → review → revise → review (real API calls to both Claude and GPT)
- DB consistency verified: 5/5 checks passed (session, drafts, reviews, messages, draft numbering)
- Artifact numbering correct: a-01-plan.md, a-02-review.md, ..., a-07-plan.md
- **Did not converge in 3 rounds** — GPT keeps finding new issues each round (7 → 6 → 7 issues)
- Each revision addresses prior issues but GPT surfaces new concerns at similar depth
- Total cost for 3 rounds: $0.260 (Claude: $0.231 for plan+revisions, GPT: $0.029 for reviews)
- Total wall clock: 257.3s (~4.3 minutes) for 3 rounds
- Revision latency grows per round (49s → 61s → 80s) as plan grows from incorporating feedback

**Key findings for planner-auto design:**
- The review loop mechanism works — all components integrate cleanly
- Convergence tuning needed: either relax reviewer threshold, cap severity levels, or add a "good enough" heuristic (e.g., no critical issues = GO)
- Claude revisions are substantive — each draft genuinely addresses the prior issues
- Cost scales linearly per round (~$0.09/round), so capping at 3-5 rounds is important
- Revision prompts may need to tell Claude to be more concise to avoid plan bloat
