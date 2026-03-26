#!/usr/bin/env python3
"""POC 2b: Structured Prompt Testing

Compare prompt strategies for structured reviewer output.

Steps:
  1. Load sample plan
  2. Define prompt variants:
     a. Free-form: "Review this plan. Is it go or no-go?"
     b. JSON-instructed: "Return your review as JSON with fields:
        verdict, issues, summary"
     c. XML-tagged: "Wrap your verdict in <verdict> tags, issues in
        <issues> tags"
     d. Few-shot: Include an example GO and NO_GO response in the prompt
  3. For each variant, call GPT-5.4 three times
  4. Parse each response using poc_parse_go_nogo parser
  5. Record: parse success/fail, latency, token usage, response quality
  6. Print comparison table:
     - Strategy | Parse Success (N/3) | Avg Latency | Avg Tokens | Notes

Usage:
  export OPENAI_API_KEY="your-key"
  python scripts/poc/planner-auto/poc_structured_prompt.py
  python scripts/poc/planner-auto/poc_structured_prompt.py --plan path/to/plan.md
"""

# TODO: implement
