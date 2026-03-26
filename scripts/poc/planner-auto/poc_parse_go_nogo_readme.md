# POC 2a: Go/No-Go Response Parsing

## Purpose

Validate that reviewer responses (from any adapter) can be reliably parsed into the `ReviewerResponse` schema, including edge cases like malformed output, GO-with-notes, and ambiguous verdicts.

## What This Tests

- Parser correctness against 10+ synthetic reviewer responses
- Edge case handling: malformed, missing verdict, GO with non-blocking notes, mixed signals
- Schema extraction reliability: verdict, issues list with severity, summary
- Parser fallback behavior when structured format is absent (keyword matching)

## Input

A set of hardcoded test responses covering:
- Clean GO response
- Clean NO_GO with structured issues
- GO with non-blocking notes
- NO_GO with only minor issues
- Malformed output (no clear verdict)
- Empty response
- Partial JSON (truncated)
- Free-form text with embedded verdict keywords
- Multiple verdicts in one response (conflicting)
- Response in unexpected language or format

## Ideal Result

- All test cases pass with expected parsed output
- Malformed/ambiguous responses default to NO_GO with a parse-failure issue
- GO-with-notes extracts notes but returns GO verdict
- Parser never crashes — always returns a valid `ReviewerResponse`
- Print pass/fail summary table

## Dependencies

- None (pure Python, no API calls)
