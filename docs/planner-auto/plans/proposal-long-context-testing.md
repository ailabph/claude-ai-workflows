# Long Context Testing Plan for planner-auto

## Purpose

Validate that planner-auto handles large context inputs. Opus 4.6 supports 1M tokens (~4M chars), so the planning stage itself should never be the bottleneck. The potential bottlenecks are:

1. **File loading** — `add-context` has a 500KB per-file limit. Is this sufficient?
2. **Context synthesis** — Haiku synthesizes before plan generation. Does it produce useful output from 100KB+?
3. **Direct API payload size** — Does the `anthropic` package handle large payloads without timeout?
4. **Review loop history growth** — By round 3+, history context accumulates. Does it stay within limits?
5. **Cost** — Large context = more input tokens. What's the cost curve?

## Test Structure

Each level runs **two passes** to isolate failures:

**Pass A (plan-only):** `start` → `add-context` → `discuss --done` → `generate`. Tests context loading, synthesis, and plan generation without the review loop.

**Pass B (full-loop):** Same session, continue with `review --verbose`. Tests the review loop, history accumulation, and convergence on top of the already-generated plan.

If Pass A fails, the issue is in context handling or plan generation. If Pass A succeeds but Pass B fails, the issue is in the review loop under large-context conditions.

---

## Test Levels

### Level 1: Moderate Context (~93KB total)

4 real files from this repo.

**Pass A (plan-only):**
```bash
planner-auto start --project ctx-test-moderate

planner-auto add-context <id> --file planner-auto/planner_auto/cli.py            # ~44KB
planner-auto add-context <id> --file planner-auto/planner_auto/loop/engine.py     # ~25KB
planner-auto add-context <id> --file planner-auto/README.md                       # ~13KB
planner-auto add-context <id> --file planner-auto/AGENTS.md                       # ~8KB

# Verify: context_count = 4
planner-auto status <id>

planner-auto discuss <id> "Refactor the review loop engine to support pluggable reviewer backends — currently only DirectAPIAdapter exists, but the architecture should make it easy to add new adapters without modifying engine.py" --done

planner-auto generate <id>
```

**Verify Pass A:**
- [ ] All 4 files loaded without error
- [ ] `discuss` responds (synthesis happens internally)
- [ ] `generate` produces a plan that references specific files/functions from context
- [ ] Plan stays under 3K words

**Pass B (full-loop):**
```bash
planner-auto review <id> --verbose
```

**Verify Pass B:**
- [ ] Review loop converges (3-5 rounds expected)
- [ ] No timeout errors
- [ ] Total cost < $0.50

### Level 2: Heavy Context (~224KB total)

15 source files + documentation. Feature stays within this repo's domain (no external dependencies like TUI).

**Pass A (plan-only):**
```bash
planner-auto start --project ctx-test-heavy

# Source files (~161KB)
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

# Documentation (~63KB)
planner-auto add-context <id> --file planner-auto/README.md                                # ~13KB
planner-auto add-context <id> --file planner-auto/AGENTS.md                                # ~8KB
planner-auto add-context <id> --file planner-auto/CHANGELOG.md                             # ~5KB
planner-auto add-context <id> --file docs/planner-auto/progress.md                         # ~7KB
planner-auto add-context <id> --file docs/plans/planner-auto-proposal-v1.1.md              # ~30KB

planner-auto add-context <id> --note "Direct Anthropic API is the default backend. Review history with cumulative DEFER tracking is the key convergence mechanism."

planner-auto status <id>   # verify context_count = 16

planner-auto discuss <id> "Add a session comparison command: planner-auto compare <id1> <id2> that shows a side-by-side diff of two sessions — milestones, issue counts per round, disposition patterns, convergence speed, and total cost. Output as a formatted table or with --json. This helps users understand which session configuration produced better results." --done

planner-auto generate <id>
```

**Verify Pass A:**
- [ ] All 16 entries loaded without error
- [ ] Context synthesis completes (may take 10-20s)
- [ ] Synthesis captures architecture, not just file names
- [ ] Plan references specific modules and patterns from loaded context
- [ ] Plan stays under 3K words despite 224KB context

**Pass B (full-loop):**
```bash
planner-auto review <id> --verbose
```

**Verify Pass B:**
- [ ] Review loop completes
- [ ] History context size stays bounded across rounds
- [ ] No API timeout errors
- [ ] Total cost < $2.00

### Level 3: Near-Limit Context (~450KB)

All source + test + doc files. Boundary test.

**Pass A (plan-only):**
```bash
planner-auto start --project ctx-test-limit

# Load ALL source files
for f in $(find planner-auto/planner_auto -name "*.py" -not -path "*__pycache__*"); do
  planner-auto add-context <id> --file "$f"
done

# Load ALL test files
for f in $(find planner-auto/tests -name "*.py" -not -path "*__pycache__*"); do
  planner-auto add-context <id> --file "$f"
done

# Documentation
planner-auto add-context <id> --file planner-auto/README.md
planner-auto add-context <id> --file planner-auto/AGENTS.md
planner-auto add-context <id> --file planner-auto/CHANGELOG.md

# Verify entry count
planner-auto status <id>

planner-auto discuss <id> "Perform a comprehensive security audit of the planner-auto codebase. Identify: API key handling vulnerabilities, SQL injection risks, path traversal in file loading, secrets that could leak through logs or artifacts, and any unsafe subprocess invocations." --done

planner-auto generate <id>
```

**Verify Pass A:**
- [ ] All files loaded (record count and any rejections)
- [ ] Context synthesis handles input or fails gracefully
- [ ] Plan generation works or produces clear error

**Pass B (full-loop) — only if Pass A succeeds:**
```bash
planner-auto review <id> --verbose
```

**Verify Pass B:**
- [ ] Review loop handles large history context or caps it
- [ ] If API rejects payload as too large, error message is actionable
- [ ] Cost recorded

---

## What to Measure

For each test level, record per pass:

| Metric | L1 Pass A | L1 Pass B | L2 Pass A | L2 Pass B | L3 Pass A | L3 Pass B |
|--------|-----------|-----------|-----------|-----------|-----------|-----------|
| Files loaded | | | | | | |
| Total context size (KB) | | | | | | |
| Context synthesis time (s) | | | | | | |
| Synthesis input size (KB) | | | | | | |
| Synthesis output quality | | | | | | |
| Plan generation time (s) | | | | n/a | | n/a |
| Plan word count | | | | n/a | | n/a |
| Plan references context? | | | | n/a | | n/a |
| Review rounds to converge | n/a | | n/a | | n/a | |
| History context size (chars) per round | n/a | | n/a | | n/a | |
| Total cost ($) | | | | | | |
| Errors / timeouts | | | | | | |

---

## Potential Issues to Watch

| Issue | Symptom | Likely Cause | Fix |
|-------|---------|-------------|-----|
| Synthesis too long | > 60s | Haiku overwhelmed by 200KB+ | Chunk context, or use Sonnet for synthesis |
| Plan ignores context | Generic plan, no file references | Context too large for meaningful processing | Better synthesis prompt, per-file summaries |
| API timeout on generate | 120s timeout hit | Large prompt + thinking = slow | Increase timeout_sec or reduce context |
| Review history overflow | GPT review fails on later rounds | Plan + history exceeds GPT limit | Cap history context size more aggressively |
| Cost spike | > $2 per session | Large input tokens every call | Monitor, warn user, consider context pruning |
| 500KB limit too small | User has files > 500KB | Hardcoded in add-context | Make configurable with `--max-file-size` |

---

## Success Criteria

| Level | Pass A (plan-only) | Pass B (full-loop) |
|-------|-------------------|-------------------|
| Level 1 | Plan generated, references context files | Converges, cost < $0.50 |
| Level 2 | Plan generated despite 224KB, stays under 3K words | Converges, history stays bounded, cost < $2.00 |
| Level 3 | Completes or fails with clear actionable error | Completes or fails with clear actionable error |

---

## Results

### Level 1: Moderate Context (~93KB) — PASS

**Session:** `0ca49f61` (ctx-test-moderate)

**Pass A (plan-only):**

| Metric | Result |
|--------|--------|
| Files loaded | 4 (cli.py 44K, engine.py 28K, README 13K, AGENTS 9.5K) |
| Total context size | ~93KB |
| Discuss works | Yes — Claude asked 12 clarifying questions referencing loaded code |
| Plan references context? | Yes — specific classes (`ReviewerContract`, `DirectAPIAdapter`), file paths, patterns |
| Plan word count | ~1,500 (well under 3K limit) |
| Plan quality | 5 milestones: contract hardening, registry, CLI refactor, config snapshot, docs. Highly specific to the codebase. |
| Errors | None |

**Pass B (full-loop):**

| Metric | Result |
|--------|--------|
| Review rounds | 5 (issue trend: 2→1→1→1→GO) |
| History context size | Stable at ~6.5-7.5K chars (bounded, not growing) |
| Plan growth | 9.5K → 11.6K (22% over 5 rounds — well controlled) |
| GPT review latency | 58s→69s→104s→116s→137s (growing but within timeout) |
| All feedback | ACCEPT (no DEFER/REJECT needed) |
| Total cost | $0.29 |
| Artifacts | 11 exported + .kafra handoff |
| Errors/timeouts | None |

**Verdict:** PASS. Plan references loaded files, converges in 5 rounds, cost $0.29 (under $0.50 threshold). History context stays bounded. No timeouts despite growing review latency.

---

## When to Run

- **Level 1:** Complete — PASS
- **Level 2:** Next — ~15 min total
- **Level 3:** Optional boundary test — time depends on context size
