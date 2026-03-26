# POC 1a: Reviewer Direct API

## Purpose

Validate that GPT-5.4 can review a milestone plan via the OpenAI API and return a structured go/no-go response that conforms to the `ReviewerResponse` schema.

## What This Tests

- OpenAI SDK connectivity and authentication
- GPT-5.4 response quality when reviewing a plan document
- Structured output reliability (can we get consistent GO/NO_GO + issues?)
- Latency and token cost for a single review round

## Input

A sample milestone plan (hardcoded or loaded from file) following the `CLAUDE_orch_v2.md` template format.

## Ideal Result

- Script runs end-to-end without errors
- GPT returns a response that can be parsed into:
  ```
  verdict: GO | NO_GO
  issues: [{ severity, description, rationale }]
  summary: str
  ```
- Latency measured and printed (target: under 30s for a typical plan)
- Token usage and estimated cost printed
- Response is deterministic enough across 3 runs to be parseable every time

## Dependencies

- `openai` Python SDK
- `OPENAI_API_KEY` env var
