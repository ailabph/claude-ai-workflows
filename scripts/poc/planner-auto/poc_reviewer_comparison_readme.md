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
