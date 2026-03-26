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
