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

### Self-Review Experiment (A/B comparison)

Tested the senior dev's suggestion: add a bounded self-review after each revision (self-check → repair → wrap-up) before sending back to GPT.

**A/B Results (3 rounds each, same feature):**

| Metric | Baseline | Self-Review | Delta |
|--------|----------|-------------|-------|
| Issues R1/R2/R3 | 6/8/7 | 7/6/7 | No meaningful change |
| Converged? | No | No | Same |
| Total cost | $0.261 | $0.790 | 3x more expensive |
| Total time | 254s | 700s | 2.8x slower |
| Final plan size | 15.4 KB | 10.9 KB | 29% smaller |
| Plan growth | 4→15 KB (3.7x) | 4→11 KB (2.5x) | Less bloat |

**What self-review does well:**
- Wrap-up pass reduces plan bloat (29% smaller final plan)
- Self-check found problems every round — confirms Claude revisions consistently introduce new issues

**What self-review doesn't help:**
- GPT issue count unchanged (6-7 per round regardless)
- GPT finds *different* issues than what self-check catches — they're complementary critics, not redundant
- 3x cost increase not justified by the convergence benefit

**Recommendation:** Don't use full 3-step self-review per round. Instead, apply a standalone wrap-up/compression pass (1 Claude call) to control plan bloat, and invest the convergence budget in severity-based thresholds (GO if no criticals) rather than additional Claude calls.
