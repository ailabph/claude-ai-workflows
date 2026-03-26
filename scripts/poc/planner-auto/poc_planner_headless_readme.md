# POC 4a: Planner Headless (Claude Agent SDK)

## Purpose

Validate that Claude can be invoked via the Agent SDK in headless mode to generate a milestone plan from context files and a feature description, following the `CLAUDE_orch_v2.md` template.

## What This Tests

- Claude Agent SDK headless invocation (non-interactive)
- System prompt injection for plan format requirements
- Context file loading (pass file contents as part of the prompt)
- Output quality: does the plan follow `## Milestone N: Name` format?
- Latency and token usage for plan generation

## Input

- 2-3 sample source files (small, representative of a real project)
- A feature description string
- System prompt requiring CLAUDE_orch_v2.md milestone format

## Ideal Result

- Agent produces a plan with 3-5 milestones in the correct format
- Each milestone has tasks and deliverables
- Plan is parseable by orchestrator-auto's existing milestone parser
- Latency measured (target: under 60s)
- Token usage printed

## Dependencies

- `claude-agent-sdk` (or Claude CLI with `-p` flag)
- `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` env var
