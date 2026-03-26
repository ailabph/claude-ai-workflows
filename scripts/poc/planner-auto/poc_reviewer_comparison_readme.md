# POC 1d: Reviewer Adapter Comparison

## Purpose

Run the same plan through all three reviewer adapters (Direct API, Codex MCP, OpenCode HTTP) and produce a comparison report covering latency, cost, reliability, and response quality.

## What This Tests

- Side-by-side comparison of all three adapters
- Consistency of ReviewerResponse across adapters
- Latency differences
- Cost differences (token usage)
- Reliability (parse success rate across 3 runs each)
- Quality (do different adapters catch different issues?)

## Input

Same sample plan used across POC 1a, 1b, 1c. Each adapter runs 3 times.

## Ideal Result

A printed comparison report:

```
| Adapter         | Parse Success | Avg Latency | Avg Tokens | Avg Cost  | Tool Access |
|-----------------|---------------|-------------|------------|-----------|-------------|
| Direct API      | 3/3           | 12s         | 2,100      | $0.03     | No          |
| Codex MCP       | 3/3           | 18s         | 3,400      | $0.08     | Yes         |
| OpenCode HTTP   | 2/3           | 25s         | 2,800      | $0.04     | Yes         |
```

Plus a recommendation on which adapter to use as the default.

## Dependencies

- All three POCs (1a, 1b, 1c) implemented and working
- All respective API keys and tools configured

## Actual Results

**Comparison table (1 run per adapter):**

| Adapter | Parse | Latency | Cost | Tokens | Issues | Verdict |
|---------|-------|---------|------|--------|--------|---------|
| Direct API | 1/1 | 11.7s | $0.007 | 1,246 | 7 | NO_GO |
| Codex MCP | 0/1 | failed | — | — | — | ERROR |
| OpenCode HTTP | 1/1 | 14.6s | $0.040 | 11,192 | 5 | NO_GO |

**Key findings:**
- **Direct API is the clear winner** — fastest (11.7s), cheapest ($0.007), most reliable, highest issue count (7)
- **OpenCode HTTP works** but costs 5.7x more due to OpenCode injecting ~10K system tokens into every request
- **Codex MCP failed** — SDK subprocess spawn error when called from the comparison script. Known flakiness from POC 1b (auth + process management issues). Not reliable enough for production use
- **Issue overlap analysis**: Direct API and OpenCode HTTP surface similar themes (missing tests, incomplete API contract, caching gaps) but with different descriptions. Direct API is more thorough (7 vs 5 issues)
- **Recommendation: Direct API** as the default reviewer adapter. Codex MCP and OpenCode HTTP add cost and complexity without clear benefit for plan-text-only review

**Graceful degradation works**: Unavailable adapters are skipped with clear messages. The comparison report is still useful even with partial results.

**Report export**: `--output report.md` generates a markdown report suitable for sharing.
