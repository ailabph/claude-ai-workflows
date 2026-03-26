# POC 2b: Structured Prompt Testing

## Purpose

Compare different prompt strategies for getting the reviewer to return output that matches the `ReviewerResponse` schema. Determines which prompt format produces the most reliably parseable responses.

## What This Tests

- Free-form prompt (just ask for go/no-go) vs structured output instructions
- JSON-instructed prompt (ask reviewer to return JSON)
- XML-tagged prompt (ask reviewer to wrap output in tags like `<verdict>GO</verdict>`)
- Few-shot examples in the prompt
- Parsing success rate across prompt strategies

## Input

A single sample plan reviewed 3 times with each prompt strategy (total: 12+ API calls).

## Ideal Result

- Comparison table: prompt strategy vs parse success rate vs response quality
- One clear winner for structured output reliability
- Recommended prompt template to use in the real reviewer adapter

## Dependencies

- `openai` Python SDK
- `OPENAI_API_KEY` env var
- POC 2a parser (reuses `parse_reviewer_response`)
