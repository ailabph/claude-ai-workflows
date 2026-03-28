# Long Context Testing Plan for planner-auto

## Purpose

Validate that planner-auto handles large context inputs end-to-end. Opus 4.6 supports 1M tokens (~4M chars), so the planning stage itself should never be the bottleneck. The potential bottlenecks are:

1. **File loading** — `add-context` has a 500KB per-file limit. Is this sufficient? Should it be configurable?
2. **Context synthesis** — Haiku synthesizes context before plan generation. Does it choke on large inputs? Does it produce useful synthesis from 100KB+ of context?
3. **Direct API payload size** — Does the `anthropic` package handle large message payloads without timeout or error?
4. **GPT reviewer** — GPT-5.4 reviews the generated plan. The plan itself should stay under 3K words (constrained prompt), but does GPT handle large review history context from prior rounds?
5. **Review loop total context** — By round 3+, the prompt includes: current plan + previous plan (5K chars) + previous review (3K chars) + cumulative defers. Does this stay within limits?
6. **Cost** — Large context = more input tokens = higher cost per call. What's the cost curve?

## Test Levels

### Level 1: Moderate Context (~50-80KB total)

Real documentation files from this repo.

```bash
planner-auto start --project ctx-test-moderate

# ~44KB
planner-auto add-context <id> --file planner-auto/planner_auto/cli.py

# ~28KB
planner-auto add-context <id> --file planner-auto/planner_auto/loop/engine.py

# ~13KB
planner-auto add-context <id> --file planner-auto/README.md

# ~8KB
planner-auto add-context <id> --file planner-auto/AGENTS.md

# Total: ~93KB across 4 files
planner-auto status <id>  # verify context_count = 4
```

**Feature:** "Refactor the review loop engine to support pluggable reviewer backends — currently only DirectAPIAdapter exists, but the architecture should make it easy to add Codex MCP or OpenCode HTTP adapters without modifying engine.py"

**Verify:**
- [ ] All 4 files loaded without error
- [ ] `discuss` works with this context size
- [ ] Context synthesis produces useful summary (not truncated or garbled)
- [ ] Plan generation references specific files and functions from context
- [ ] Review loop converges (3-5 rounds expected)
- [ ] Total cost is reasonable (estimate: $0.20-0.50)

### Level 2: Heavy Context (~200-300KB total)

Push the limits with large files and documentation.

```bash
planner-auto start --project ctx-test-heavy

# Load the largest source files
planner-auto add-context <id> --file planner-auto/planner_auto/cli.py                    # ~44KB
planner-auto add-context <id> --file planner-auto/planner_auto/db.py                     # ~28KB
planner-auto add-context <id> --file planner-auto/planner_auto/loop/engine.py             # ~25KB
planner-auto add-context <id> --file planner-auto/planner_auto/sdk_wrapper.py             # ~9KB
planner-auto add-context <id> --file planner-auto/planner_auto/reviewer/direct_api.py     # ~9KB
planner-auto add-context <id> --file planner-auto/planner_auto/reviewer/parser.py          # ~14KB
planner-auto add-context <id> --file planner-auto/planner_auto/loop/feedback.py            # ~8KB
planner-auto add-context <id> --file planner-auto/planner_auto/loop/history.py             # ~7KB
planner-auto add-context <id> --file planner-auto/planner_auto/loop/convergence.py         # ~5KB
planner-auto add-context <id> --file planner-auto/planner_auto/export.py                   # ~12KB

# Load documentation
planner-auto add-context <id> --file planner-auto/README.md                                # ~13KB
planner-auto add-context <id> --file planner-auto/AGENTS.md                                # ~8KB
planner-auto add-context <id> --file planner-auto/CHANGELOG.md                             # ~5KB
planner-auto add-context <id> --file docs/planner-auto/progress.md                         # ~7KB
planner-auto add-context <id> --file docs/plans/planner-auto-proposal-v1.1.md              # ~30KB

# Add notes for additional context
planner-auto add-context <id> --note "This is a planning tool that uses Claude (planner) and GPT-5.4 (reviewer) in a multi-round review loop. Direct Anthropic API is the default backend. Review history with cumulative DEFER tracking is the key convergence mechanism."

# Total: ~224KB across 15 files + 1 note
planner-auto status <id>
```

**Feature:** "Add a TUI mode (--tui flag) for the review command that shows a live dashboard with: current round number, verdict, issue count with severity breakdown, disposition decisions (ACCEPT/DEFER/REJECT) as they happen, revision progress, total cost, and a scrollable log panel. Use the Textual library (already used by orchestrator-auto). The TUI should work alongside the existing headless/verbose/debug output tiers."

**Verify:**
- [ ] All 15 files + note loaded without error
- [ ] Context synthesis completes (may take 10-20s with this much input)
- [ ] Synthesis is useful — not just listing filenames but capturing architecture
- [ ] Plan generation references specific modules and patterns from context
- [ ] Plan stays under 3K words despite large context (constrained prompt working)
- [ ] Review loop completes (may take more rounds due to complexity — TUI is complex)
- [ ] No API timeout errors on large payloads
- [ ] Total cost tracked correctly

### Level 3: Near-Limit Context (~450KB)

Test the 500KB per-file limit and total context near the practical ceiling.

```bash
planner-auto start --project ctx-test-limit

# Load ALL source files
find planner-auto/planner_auto -name "*.py" -not -path "*__pycache__*" | while read f; do
  planner-auto add-context <id> --file "$f"
done

# Load ALL test files
find planner-auto/tests -name "*.py" -not -path "*__pycache__*" | while read f; do
  planner-auto add-context <id> --file "$f"
done

# Load ALL documentation
planner-auto add-context <id> --file planner-auto/README.md
planner-auto add-context <id> --file planner-auto/AGENTS.md
planner-auto add-context <id> --file planner-auto/CHANGELOG.md

planner-auto status <id>  # total context entry count + chars
```

**Feature:** "Perform a comprehensive security audit of the planner-auto codebase. Identify: API key handling vulnerabilities, SQL injection risks, path traversal in file loading, secrets that could leak through logs or artifacts, and any unsafe subprocess invocations. Produce a milestone plan where each milestone addresses one security domain."

**Verify:**
- [ ] All files loaded (how many? what total size?)
- [ ] Context synthesis handles 400KB+ input (may need to chunk)
- [ ] Plan generation works or fails gracefully with clear error
- [ ] If API rejects payload as too large, error message is actionable
- [ ] Cost for this context size

## What to Measure

For each test level, record:

| Metric | Level 1 | Level 2 | Level 3 |
|--------|---------|---------|---------|
| Files loaded | | | |
| Total context size (KB) | | | |
| Context synthesis time (s) | | | |
| Synthesis output quality | | | |
| Plan generation time (s) | | | |
| Plan word count | | | |
| Plan references context? | | | |
| Review rounds to converge | | | |
| Total cost ($) | | | |
| Any errors? | | | |
| Any timeouts? | | | |

## Potential Issues to Watch

| Issue | Symptom | Likely Cause | Fix |
|-------|---------|-------------|-----|
| Synthesis too long | > 60s for synthesis | Haiku overwhelmed by 200KB+ | Chunk context, or use Sonnet for synthesis |
| Plan ignores context | Generic plan, no file references | Context too large for model to process meaningfully | Better synthesis prompt, summarize per-file |
| API timeout on generate | 120s timeout hit | Large prompt + thinking = slow | Increase timeout_sec or reduce context |
| Review context overflow | GPT review fails on later rounds | Plan + history + review context exceeds GPT limit | Cap history context size more aggressively |
| Cost spike | > $2 per session | Large input tokens on every call | Monitor, warn user, consider context pruning |
| 500KB limit too small | User has files > 500KB | Hardcoded limit in add-context | Make configurable with `--max-file-size` |

## Success Criteria

| Level | Criteria |
|-------|---------|
| Level 1 | Full pipeline completes, plan references loaded files, cost < $0.50 |
| Level 2 | Full pipeline completes, synthesis is useful, plan stays under 3K words, cost < $2.00 |
| Level 3 | Either completes or fails with a clear, actionable error message (not a hang or crash) |

## When to Run

- **Level 1:** Now — quick validation (~5 min)
- **Level 2:** After Level 1 passes — thorough validation (~15 min)
- **Level 3:** Optional — boundary testing, mainly to document limits
