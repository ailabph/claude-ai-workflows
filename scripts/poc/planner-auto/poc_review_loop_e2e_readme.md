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

### Resolution Guidance Experiment (A/B comparison)

Tested the senior dev's follow-up suggestion: add `resolution_guidance` (1-3 sentences) and `target_section` fields to each reviewer issue, giving Claude concrete acceptance criteria.

**A/B Results (3 rounds each, same feature):**

| Metric | Baseline | Guidance | Delta |
|--------|----------|----------|-------|
| Issues R1/R2/R3 | 6/8/7 | 8/5/5 | Declining trend vs oscillating |
| Issue trend | Oscillating | **Declining** | Better convergence trajectory |
| Converged? | No | No | Same (3 rounds too few) |
| Total cost | $0.261 | $0.305 | +17% (modest increase) |
| Total time | 254s | 311s | +22% |
| GPT cost | $0.030 | $0.044 | +47% (longer responses with guidance) |
| Final plan size | 15.4 KB | 15.4 KB | Same |

**What resolution guidance does well:**
- **Issue count declines** (8→5→5) instead of oscillating (6→8→7) — GPT's feedback is more stable when it includes acceptance criteria
- GPT stops reframing the same architectural concern in different ways because the guidance makes "resolved" explicit
- Cost increase is modest (+17%) — mostly from GPT writing slightly longer responses

**What it doesn't solve (yet):**
- Still didn't converge in 3 rounds — likely needs 4-5 with a zero-critical threshold
- Plan size is identical — guidance doesn't reduce bloat (wrap-up pass still needed separately)

### Resolution Guidance — 6-Round Extended Test

Ran guidance variant at 6 rounds to see if the declining trend from the 3-round test holds.

**6-round comparison:**

| Metric | Baseline 6r | Guidance 6r | Delta |
|--------|------------|-------------|-------|
| Issue trend | 9→8→6→9→6→6 | 7→7→6→6→7→5 | Marginally better end state |
| Final issues | 6 | 5 | -1 |
| Converged? | No | No | Same |
| Total cost | $0.785 | $0.833 | +6% |
| Total time | 793s | 897s | +13% |
| Final plan size | 30 KB | 37 KB | Worse (guidance didn't help bloat) |
| Plan growth | 4→30 KB (7.5x) | 4→37 KB (9.7x) | Worse |

**Key finding:** Over 6 rounds, resolution guidance provides only marginal improvement. The 3-round declining trend (8→5→5) didn't sustain — at 6 rounds both variants stabilize around 5-6 issues. Plan bloat is actually worse with guidance because GPT's longer responses (with acceptance criteria) prompt Claude to add more detail.

**Conclusion across all experiments:** GPT will never say GO on its own for a complex feature plan. The loop produces better plans each round, but the reviewer always finds more to critique. The right strategy is controlling *when to stop*, not *how to make GPT say GO*.

### Final Recommendation for v1

Based on all three experiments (baseline, self-review, resolution guidance) across 3-round and 6-round runs:

1. **Zero-critical threshold** — stop when no critical issues remain after any round
2. **Hard cap at 3-5 rounds** — diminishing returns after round 3; cost grows linearly but quality plateaus
3. **Resolution guidance ON** — the 3-round improvement (8→5→5 vs 6→8→7) justifies the modest +17% cost; helps most in early rounds when plan has real gaps
4. **Single wrap-up pass per round** — needed for bloat control (neither guidance nor self-review addresses this)
5. **Human fallback** — if critical issues persist at cap, pause for human review

### Opus + High Effort + Thinking Experiment

Tested with upgraded model settings: Claude Opus 4.6 (effort=high, thinking=adaptive) as planner, GPT-5.4 (reasoning_effort=high) as reviewer, resolution guidance ON, 8-round cap.

**Results (8 rounds):**

| Round | Issues | Review Time | Revision Time | Round Cost |
|-------|--------|-------------|---------------|------------|
| 1 | 4 | 12.8s | 74.6s | $0.150 |
| 2 | **1** | 5.5s | 7.9s | $0.023 |
| 3 | **1** | 6.1s | 75.3s | $0.159 |
| 4 | **1** | 6.2s | 94.7s | $0.185 |
| 5 | 4 | 19.2s | 5.9s | $0.028 |
| 6 | **1** | 5.6s | 7.4s | $0.023 |
| 7 | 4 | 11.9s | 68.4s | $0.145 |
| 8 | 5 | 13.3s | 91.9s | $0.194 |

**Total: $1.15, 595s (10 min), still NO_GO after 8 rounds.**

**Cross-configuration comparison (3-round window):**

| Config | Issues R1/R2/R3 | Cost (3r) |
|--------|----------------|-----------|
| Sonnet baseline | 6/8/7 | $0.26 |
| Sonnet + guidance | 8/5/5 | $0.31 |
| **Opus + high + thinking + guidance** | **4/1/1** | ~$0.33 |

**Key findings:**
- **Opus gets to 1 issue by round 2** — dramatically better than Sonnet's 5-8
- Oscillation pattern (1→1→1→4→1→4→5): GPT periodically finds new angles, Opus resolves them quickly
- Cheap rounds ($0.02) = Opus makes small targeted fixes; expensive rounds ($0.19) = Opus rewrites sections
- **Still doesn't converge to GO** — confirms threshold-based stop is the right strategy regardless of model
- **With a zero-critical threshold, Opus likely converges by round 2-3** — 1 remaining issue is almost certainly major/minor
- Opus is ~4x more expensive per revision than Sonnet, but reaches "implementation-ready" quality much faster

**Cost projection for v1 default loop:**

| Config | Rounds to ~0 criticals | Est. Cost | Est. Time |
|--------|----------------------|-----------|-----------|
| Sonnet + guidance + 3r cap | 3 (may still have criticals) | ~$0.39 | ~6 min |
| Opus + guidance + 3r cap | 2-3 (likely 0 criticals by R2) | ~$0.45 | ~4 min |
| Opus + guidance + zero-critical stop | 2 (projected) | ~$0.20 | ~3 min |

**Recommendation update:** Opus + thinking + guidance is the strongest combination. For users with API budget, Opus at 2-3 rounds is cheaper AND faster than Sonnet at 5+ rounds because it resolves issues in fewer iterations.
