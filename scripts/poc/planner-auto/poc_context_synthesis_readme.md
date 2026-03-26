# POC 4b: On-Demand Context Synthesis

## Purpose

Validate that useful context can be synthesized on-demand from the messages and context_entries tables, producing a summary that is good enough for the planner agent to generate a quality plan.

## What This Tests

- Querying messages + context_entries from DB
- Synthesizing a structured context summary (files, entities, decisions, requirements)
- Output quality: is the summary useful for plan generation?
- Comparison: plan generated with synthesis vs plan generated with raw context

## Input

A pre-populated DB with simulated conversation (10-15 messages) and context entries (5-8 files loaded).

## Ideal Result

- Synthesis produces a readable markdown summary under 2000 tokens
- Summary captures: files loaded, key entities, user requirements, decisions made
- Discards noise (greetings, clarification loops) and keeps signal
- Can be fed directly to the planner as context for plan generation

## Dependencies

- `sqlite3` (stdlib)
- `claude-agent-sdk` or `anthropic` SDK (for synthesis via Claude)
- POC 3a DB schema

## Actual Results

- 11/11 validation checks passed
- Claude Haiku 4.5 synthesized 292 words (well under 500 target) from 15 messages + 6 context entries
- Output is structured markdown with 5 clear sections: Files & Purpose, Key Entities, Requirements, Decisions Made, Open Questions
- All key decisions captured: username from email, bcrypt hashing, rate limiting (5/min/IP), JWT deferred, REST error codes
- All loaded files referenced with correct descriptions
- Greeting noise ("Hi, I need help", "Hello! I see you've loaded") successfully filtered out
- Duration: 8.3s, Cost: $0.019
- Output is directly usable as planner input — no further processing needed
- Haiku is sufficient quality for synthesis (no need for Sonnet/Opus)
