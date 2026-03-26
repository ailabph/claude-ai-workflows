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

## Actual Results

- 12/12 API calls parsed successfully (all 4 strategies x 3 runs)
- All strategies achieved 3/3 parse rate and 3/3 NO_GO verdict consistency
- xml_tagged: fastest (8.7s avg) and cheapest (1,007 tokens avg), 6.7 issues avg
- json_instructed: solid middle ground (12.3s, 1,232 tokens, 8.0 issues)
- few_shot: most thorough (14.5s, 1,261 tokens, 9.0 issues)
- free_form: noisy — parser extracted ~118 "issues" from bullet points (not real issues)
- Fixed recommendation logic to penalize inflated issue counts (>20)
- Key finding: all structured strategies work equally well for parsing; choice depends on latency vs thoroughness tradeoff
