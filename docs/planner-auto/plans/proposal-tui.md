# TUI Proposal for planner-auto — Review Dashboard (v2)

## Revision History

- **v1:** Full 3-mode proposal (review + discuss + inspect). Reviewed: NO_GO.
- **v2:** Narrowed to Mode 1 (Review Dashboard) only. Fixes: scope, paused-state UI, metric availability, output suppression, code change inventory. Discuss TUI and Inspect TUI deferred to separate proposals.

---

## Problem

The `review` command runs 4-12 rounds of GPT review + Claude revision, taking 5-25 minutes. The current experience is a wall of log lines scrolling past:

```
2026-03-29 02:05:18 [INFO] planner_auto.cli (665523c1): Command invoked: review...
2026-03-29 02:05:18 [INFO] planner_auto.session (665523c1): Phase PLANNING → REVIEW...
2026-03-29 02:06:22 [INFO] planner_auto.reviewer.direct_api (665523c1): Reviewer call: model=gpt-5.4, elapsed=64.81s...
2026-03-29 02:06:31 [INFO] planner_auto.sdk_wrapper (665523c1): Claude call completed: backend=direct...
(... 50+ more lines per round ...)
```

Users can't tell at a glance: How many rounds left? Is it converging? What's the cost so far? What issues keep recurring? The `--verbose` output helps but requires reading a dense text stream.

## Scope

**In scope:** Review Dashboard TUI — live visualization of the `review` command's review loop.

**Explicitly deferred:**
- Discuss TUI (interactive chat mode) — separate proposal
- Inspect TUI (session inspector) — separate proposal, needs command shape decision first (current CLI is a subgroup with 6 commands: `inspect reviews`, `inspect dispositions`, `inspect config`, `inspect history`, `inspect raw-response`, `inspect dump`)
- New workflow semantics (resume, edit, complete-override from TUI)

## Goals

1. **Real-time review dashboard** — watch rounds progress with live metrics
2. **Convergence visibility** — see issue trend, cost curve, and remaining round budget at a glance
3. **Drill-down capability** — expand rounds to see dispositions, keep/trim, and issue details
4. **Read-only for v1** — TUI displays state, does not change it (except quit)
5. **Consistent with orchestrator-auto** — same framework (Textual), same design language

## Non-Goals

- Replacing the CLI (TUI is opt-in via `--tui` flag)
- Interactive actions from the TUI (resume, edit plan, complete)
- Discuss or Inspect modes
- Mobile/web interface

---

## Design Principles (Shared with orchestrator-auto)

### 1. Thread-Safe Message Passing
Worker thread runs the review loop. TUI main thread handles rendering. Communication via Textual messages only — never touch widgets from the worker thread.

```
ReviewLoopEngine (worker thread)
    |
    |-- on_round_complete(metrics) ---+
    |-- on_revision_start() ----------+
    |-- on_feedback_validated() ------+   TUIAdapter (bridge)
    |                                  |       |
    +-- on_loop_complete(result) -----+       +-- app.call_from_thread(post_message(...))
                                       |               |
                                       v               v
                                  TUI Main Thread -> Message Handlers -> Widget Updates
```

### 2. Progressive Disclosure
- **Level 0 (at-a-glance):** Phase, round N/max, issue trend sparkline, cost, elapsed
- **Level 1 (expand):** Per-round metrics table, dispositions, keep/trim counts
- **Level 2 (deep dive):** Full issue text, history context size, draft diff
- **Level 3 (debug):** Raw GPT response, revision prompt (behind security warning)

### 3. Status-Based Color Coding
| State | Color | Meaning |
|-------|-------|---------|
| Active/Running | Green (`#00ff41`) | Currently processing |
| Completed/GO | Cyan (`#00d9ff`) | Successfully finished |
| Warning/DEFER | Yellow (`#ffcc00`) | Deferred, needs attention |
| Error/REJECT | Red (`#ff3333`) | Rejected, critical issue |
| Idle/Pending | Gray (`#666666`) | Waiting, not started |

### 4. Responsive Layout
Three breakpoints matching orchestrator-auto:
- **Small** (<80 cols): Stacked single column
- **Medium** (80-119 cols): 2-column default
- **Large** (120+ cols): 2-column with wider main panel

### 5. Fail-Safe Widget Updates
All widget updates wrapped in `is_mounted` checks. Missing data displays `--` not crashes. Graceful degradation if terminal doesn't support features.

### 6. Textual Framework
Same stack as orchestrator-auto: Textual + Rich. TCSS for styling. Custom messages for event types. Lazy import so Textual remains an optional dependency.

### 7. Stdout Suppression
When `--tui` is active, the engine must NOT print to stdout. The TUI owns the terminal. This requires a new output mode: `"tui"` alongside the existing `"quiet"` / `"verbose"` / `"debug"`. When `verbosity="tui"`, `_emit_progress()` dispatches to callbacks only and skips all `print()` calls. File logging continues unchanged.

---

## Layout Designs

### Standard View (80+ columns) — Active Review

```
+------------------------------------------------------------------------------+
|  planner-auto review -- ctx-test-heavy (665523c1)              02:15 elapsed |
+--------------------+---------------------------------------------------------+
|  SESSION           |  ROUND PROGRESS                                         |
|                    |                                                         |
|  Phase:   REVIEW   |  R1  ## NO_GO  3 issues  ------------------- $0.038    |
|  Status:  ACTIVE   |  R2  ## NO_GO  1 issue   ------------------- $0.055    |
|  Project: ctx-heavy|  R3  ## NO_GO  2 issues  ------------------- $0.072    |
|  Backend: direct   |  R4  >> reviewing...      ---------- 45s               |
|  Complexity: complx|  R5  oo pending                                        |
|  Round cap: 12     |  R6  oo pending                                        |
|                    |  ...                                                    |
|  CONVERGENCE       |                                                         |
|                    |---------------------------------------------------------|
|  Issues: 3>1>2>_   |  CURRENT ROUND (4)                                     |
|  Trend:  |||.|     |                                                         |
|  Cost:   $0.165    |  Phase: GPT reviewing...  ============....  67s        |
|  GPT tokens: 28.4K |  Reviewer: gpt-5.4 (reasoning=high)                   |
|                    |  Plan size: 13,761 chars                                |
|  PLAN              |  History: 7,187 chars                                   |
|                    |                                                         |
|  Draft: #4         |                                                         |
|  Size: 13,761 ch   |                                                         |
|  Growth: +41%      |                                                         |
|  Milestones: 5     |                                                         |
|                    |                                                         |
+--------------------+---------------------------------------------------------+
|  LOG                                                                         |
|  02:12:31 [R3] NO_GO -- 2 issues (2 ACCEPT)                                |
|  02:13:53 [R3] Revised: 12,563 > 13,761 chars (+1,198)                     |
|  02:13:53 [R4] Starting review...                                           |
+------------------------------------------------------------------------------+
|  [d]ispositions  [h]istory  [p]lan  [l]og filter  [q]uit        R4/12 >>    |
+------------------------------------------------------------------------------+
```

**Metric availability note:** The sidebar shows GPT tokens only, not total tokens. Claude revision tokens and cost are not currently returned by `query_claude()` (see Prerequisite section). The `Cost` field shows GPT review cost only — this is explicitly labeled.

### Expanded Round Detail (press Enter on a round)

```
+------------------------------------------------------------------------------+
|  planner-auto review -- ctx-test-heavy (665523c1)              02:15 elapsed |
+--------------------+---------------------------------------------------------+
|  SESSION           |  ROUND 3 DETAIL                                         |
|                    |                                                         |
|  (same sidebar)    |  Verdict: NO_GO                                         |
|                    |  GPT:     111.7s (5,428 in / 7,615 out)  $0.072        |
|                    |  Claude:   75.6s (tokens: n/a, cost: n/a)               |
|                    |                                                         |
|                    |  Keep (3):                                               |
|                    |    + Credential hardening error hierarchy                |
|                    |    + Log filter regex coverage                           |
|                    |    + Export permission model                             |
|                    |                                                         |
|                    |  Trim (1):                                               |
|                    |    - Overly detailed SECURITY.md specification           |
|                    |                                                         |
|                    |  Issues:                                                 |
|                    |   [ACCEPT] Milestone 3 replaces raw print() with        |
|                    |            logger.debug() but never specifies log        |
|                    |            handler file permissions...                   |
|                    |   [ACCEPT] Export permission hardening only sets         |
|                    |            mode=0o700 on makedirs but not on             |
|                    |            individual file writes...                     |
|                    |                                                         |
|                    |  Draft: 12,563 > 13,761 (+1,198 chars, +9.5%)           |
|                    |  History context: 6,995 chars                            |
|                    |                                                         |
+--------------------+---------------------------------------------------------+
|  [<-] back to rounds  [n]ext round  [p]rev round  [r]aw response            |
+------------------------------------------------------------------------------+
```

**Note:** Claude latency is available (it's timed in the engine). Claude tokens and cost show `n/a` — these are not currently returned by `query_claude()`. The round detail is honest about what data exists.

### Convergence Achieved (final state)

```
+------------------------------------------------------------------------------+
|  planner-auto review -- ctx-test-heavy (665523c1)     [OK] CONVERGED  08:42  |
+--------------------+---------------------------------------------------------+
|  SESSION           |  ROUND PROGRESS                                         |
|                    |                                                         |
|  Phase:   COMPLETE |  R1  ok NO_GO  3 issues  ------------------- $0.038    |
|  Status:  COMPLETE |  R2  ok NO_GO  1 issue   ------------------- $0.055    |
|  Project: ctx-heavy|  R3  ok NO_GO  2 issues  ------------------- $0.072    |
|  Backend: direct   |  R4  ok NO_GO  3 issues  ------------------- $0.065    |
|  Complexity: complx|  R5  ok NO_GO  1 issue   ------------------- $0.077    |
|  Round cap: 12     |  R6  ok NO_GO  2 issues  ------------------- $0.069    |
|                    |  R7  ** GO     0 issues   ------------------- $0.071    |
|  CONVERGENCE       |                                                         |
|                    |---------------------------------------------------------|
|  Issues: 3>1>2>    |  RESULT                                                |
|    3>1>2>0         |                                                         |
|  Trend:  |||.||.|  |  [OK] GPT approved plan (GO)                           |
|  GPT cost: $0.447  |  [OK] Final plan: draft #8 (17,971 chars)              |
|  GPT tokens: 82.1K |  [OK] Exported to .kafra/a-01-plans/ctx-test-heavy.md  |
|                    |  [OK] 15 artifacts exported                             |
|  PLAN              |                                                         |
|                    |  Convergence path:                                      |
|  Draft: #8 (final) |  3--1--2--3--1--2--0  (7 rounds)                       |
|  Size: 17,971 ch   |                                                         |
|  Growth: +89%      |                                                         |
|  Milestones: 5     |                                                         |
|                    |                                                         |
+--------------------+---------------------------------------------------------+
|  LOG                                                                         |
|  02:26:51 [R7] GO -- 0 issues. Converged!                                  |
|  02:26:51 Final plan exported to .kafra/a-01-plans/ctx-test-heavy.md        |
|  02:26:52 Session completed. 7 rounds, $0.447 total.                        |
+------------------------------------------------------------------------------+
|  [d]ispositions  [e]xport  [p]lan view  [c]opy plan path          [OK] DONE |
+------------------------------------------------------------------------------+
```

**Note:** Cost breakdown (GPT vs Claude split) is NOT shown — Claude revision cost is `n/a`. Only GPT review cost is displayed. If the prerequisite plumbing is done, this can be upgraded.

### Cap Reached with Criticals (paused state — read-only)

```
+------------------------------------------------------------------------------+
|  planner-auto review -- my-feature (a1b2c3d4)        [!!] PAUSED     15:33  |
+--------------------+---------------------------------------------------------+
|  SESSION           |  ROUND PROGRESS                                         |
|                    |                                                         |
|  Phase:   REVIEW   |  R1  ok NO_GO  4 issues  ------------------- $0.042    |
|  Status:  PAUSED   |  R2  ok NO_GO  3 issues  ------------------- $0.058    |
|  Project: my-feat  |  ...                                                    |
|  Complexity: std   |  R7  ok NO_GO  2 issues  ------------------- $0.065    |
|  Round cap: 8      |  R8  !! NO_GO  1 CRITICAL ------------------- $0.071   |
|                    |                                                         |
|  CONVERGENCE       |---------------------------------------------------------|
|                    |  !! CAP REACHED -- CRITICAL ISSUES REMAIN                |
|  Issues: 4>3>3>    |                                                         |
|    2>2>1>2>1       |  Outstanding critical issue:                            |
|  Trend:  ||||.||.  |    "SQL injection risk in project name passed to        |
|  GPT cost: $0.512  |     raw query in discover_repo_root -- user-supplied    |
|                    |     input reaches subprocess.run without validation"    |
|  BLOCKER           |                                                         |
|                    |  Session is PAUSED. To continue from the CLI:           |
|  !! Critical issue |    planner-auto resume a1b2c3d4                        |
|    at round cap    |    planner-auto review a1b2c3d4 --max-rounds 12        |
|                    |    planner-auto complete a1b2c3d4                       |
|                    |                                                         |
+--------------------+---------------------------------------------------------+
|  LOG                                                                         |
|  02:32:14 [R8] NO_GO -- 1 CRITICAL issue. Cap reached.                     |
|  02:32:14 Session paused. Use CLI to resume or complete.                    |
+------------------------------------------------------------------------------+
|  [d]ispositions  [p]lan  [l]og filter  [q]uit                    !! R8/8    |
+------------------------------------------------------------------------------+
```

**Key change from v1:** No `[r]esume`, `[e]dit`, or `[c]omplete` actions in the TUI. The paused screen shows the blocker, displays the critical issue text, and tells the user exactly which CLI commands to run. The TUI is read-only — it displays state, it doesn't modify it.

### Small Terminal (<80 columns) — Stacked Layout

```
+----------------------------------------------+
|  planner-auto review -- 665523c1   02:15 >>  |
+----------------------------------------------+
|  REVIEW  complex  R4/12  $0.165  |||.|       |
+----------------------------------------------+
|  R1  ok NO_GO  3 issues         $0.038       |
|  R2  ok NO_GO  1 issue          $0.055       |
|  R3  ok NO_GO  2 issues         $0.072       |
|  R4  >> reviewing...             45s          |
|  R5  oo pending                               |
|  ...                                          |
+----------------------------------------------+
|  02:13:53 [R4] Starting review...            |
|  02:12:37 [R3] Revised +1,198 chars          |
|  02:12:31 [R3] NO_GO 2 issues (2 ACCEPT)    |
+----------------------------------------------+
|  [d]ispos [p]lan [l]og [q]uit    R4/12 >>    |
+----------------------------------------------+
```

### Timeout During Revision

```
+------------------------------------------------------------------------------+
|  planner-auto review -- ctx-test-limit (665523c1)              25:04 elapsed |
+--------------------+---------------------------------------------------------+
|  SESSION           |  ROUND PROGRESS                                         |
|                    |                                                         |
|  Phase:   REVIEW   |  R1-R7  (completed, same as before)                    |
|  Status:  ACTIVE   |  R8  >> revising... (retry 1/1)  ========....  120s    |
|  ...               |                                                         |
|                    |---------------------------------------------------------|
|  CONVERGENCE       |  CURRENT ROUND (8)                                      |
|                    |                                                         |
|  Issues: 3>1>2>    |  Phase: Claude revising... (RETRY after 120s timeout)  |
|    3>1>2>1>1       |  Issues: 1 ACCEPT, 0 DEFER, 0 REJECT                  |
|  GPT cost: $0.47   |  Model: claude-sonnet-4-6 (direct)                     |
|                    |  !! Previous attempt timed out after 120s               |
|                    |                                                         |
+--------------------+---------------------------------------------------------+
|  LOG                                                                         |
|  02:28:57 [!!] Timeout after 120s, retrying (1/1)                           |
|  02:26:57 [R8] Claude revising (1 ACCEPT)...                               |
|  02:26:51 [R8] NO_GO -- 1 issue                                            |
+------------------------------------------------------------------------------+
|  [d]ispositions  [p]lan  [l]og filter  [q]uit                    R8/12 >>   |
+------------------------------------------------------------------------------+
```

---

## Prerequisite: Claude Revision Metadata

**Current state:** `query_claude()` in `sdk_wrapper.py:163` returns only the response text string. The `usage` info (input_tokens, output_tokens) is logged but discarded. The engine sets `revision_cost=None` at lines 258, 291, and 385.

**What this means for the TUI:**
- Claude revision latency: **available** (engine times it)
- Claude revision tokens: **not available** (discarded by `query_claude()`)
- Claude revision cost: **not available** (never calculated)

**Two options:**

### Option A: Display `n/a` for Claude metrics (no plumbing changes)
The TUI shows GPT review metrics fully and Claude revision as latency-only. Cost field is "GPT review cost" not "total cost". This is honest and ships faster.

### Option B: Mini-plan to add Claude revision metadata (prerequisite)
1. Change `query_claude()` return type from `str` to `tuple[str, dict]` where dict has `input_tokens`, `output_tokens`
2. Thread the usage dict through `agents.py` → `engine.py`
3. Calculate Claude revision cost in engine (using Anthropic pricing)
4. Populate `revision_cost` and revision token fields in `_emit_progress`
5. Update all callers of `query_claude()` (6-8 call sites)
6. ~50 lines of plumbing + test updates

**Recommendation:** Start with Option A. Add Option B as a follow-on if users want cost breakdown. The TUI should not block on plumbing work.

---

## Architecture

### Component Hierarchy (Mode 1 only)

```
planner_auto/
+-- tui/
|   +-- __init__.py              # Lazy imports, get_review_app_class()
|   +-- review_app.py            # ReviewTUI (main app class)
|   +-- adapter.py               # TUIAdapter (thread-safe bridge)
|   +-- messages.py              # Custom Textual message types
|   +-- bindings.py              # Keybinding definitions
|   +-- styles/
|   |   +-- theme.tcss           # Shared theme (dark, green accent)
|   +-- widgets/
|   |   +-- session_panel.py     # Session metadata sidebar
|   |   +-- convergence_panel.py # Issue trend, sparkline, cost
|   |   +-- round_list.py        # Scrollable round progress list
|   |   +-- round_detail.py      # Expanded single-round view
|   |   +-- plan_panel.py        # Plan size, draft#, milestones
|   |   +-- current_round.py     # Live progress for active round
|   |   +-- log_panel.py         # Timestamped log messages
|   +-- screens/
|       +-- disposition_screen.py # Full disposition list modal
|       +-- plan_screen.py       # Full plan text viewer
|       +-- raw_response_screen.py # Debug: raw GPT/Claude output
|       +-- help_screen.py       # Keybinding reference
```

### Message Types

```python
# messages.py -- Custom Textual messages for review dashboard

class RoundStarted(Message):
    """Fired when a new review round begins."""
    round_num: int
    max_rounds: int

class ReviewComplete(Message):
    """Fired when GPT review returns."""
    round_num: int
    verdict: str            # "GO" or "NO_GO"
    issue_count: int
    latency_ms: int
    input_tokens: int       # GPT input tokens
    output_tokens: int      # GPT output tokens
    cost: float             # GPT review cost
    keep_count: int
    trim_count: int
    issues: list[dict]      # [{description, severity, target_section, resolution_guidance}]

class FeedbackValidated(Message):
    """Fired after Claude assesses each issue."""
    round_num: int
    dispositions: list[dict]  # [{description, disposition, rationale}]

class RevisionComplete(Message):
    """Fired when Claude finishes revising the plan."""
    round_num: int
    prev_size: int
    new_size: int
    latency_ms: int           # Available (engine times it)
    # NOTE: tokens and cost are NOT available (query_claude returns text only)
    history_context_size: int

class LoopFinished(Message):
    """Fired when the review loop stops."""
    converged: bool
    stop_reason: str          # "go", "cap_no_criticals", "cap_with_criticals"
    rounds: int
    total_cost: float         # GPT review cost only
    final_plan_path: str | None

class RevisionTimeout(Message):
    """Fired when a revision call times out."""
    round_num: int
    timeout_sec: int
    retry_count: int

class LoopError(Message):
    """Fired when the review loop encounters an unrecoverable error."""
    error_message: str
    round_num: int | None
```

### Integration: Adapter Pattern

```python
# adapter.py

class TUIAdapter:
    """Thread-safe bridge between ReviewLoopEngine and Textual app."""

    def __init__(self, app: App):
        self.app = app

    def on_round_start(self, round_num: int, max_rounds: int):
        self.app.call_from_thread(
            self.app.post_message, RoundStarted(round_num, max_rounds)
        )

    def on_review_complete(self, metrics: dict):
        self.app.call_from_thread(
            self.app.post_message, ReviewComplete(**metrics)
        )
    # ... one method per event type
```

### Engine Integration: Output Mode, Not Just Callbacks

The engine change is more than "add callbacks." Here's the full contract:

**1. New verbosity mode: `"tui"`**

When `verbosity="tui"` in `engine_config`, `_emit_progress()` dispatches to callbacks **instead of** (not alongside) `print()` calls. File logging via `logger.*` continues unchanged.

```python
# In _emit_progress():
if self.verbosity == "tui":
    # Dispatch to callbacks only, no stdout
    if self.callbacks:
        self.callbacks["on_review_complete"](metrics)
    return  # Skip all print() calls below

# Existing quiet/verbose/debug paths unchanged
```

**2. Callback dispatch points** (6 locations in engine.py):

| Location | Event | Data |
|----------|-------|------|
| Before GPT review call | `on_round_start` | round_num, max_rounds |
| After GPT review returns | `on_review_complete` | All GPT metrics from ReviewerResponse |
| After feedback validation | `on_feedback_validated` | round_num, dispositions list |
| After Claude revision | `on_revision_complete` | round_num, sizes, latency, history_size |
| On loop exit | `on_loop_finished` | LoopResult fields |
| On timeout/retry | `on_revision_timeout` | round_num, timeout_sec, retry_count |

**3. CLI flag wiring** (in `cli.py` review command):

```python
@click.option("--tui", is_flag=True, help="Launch review dashboard TUI")
def review(ctx, session_id, tui, ...):
    if tui:
        try:
            from planner_auto.tui import get_review_app_class
        except ImportError:
            click.echo("TUI requires 'textual'. Install: pip install planner-auto[tui]")
            ctx.exit(1)
        ReviewTUI = get_review_app_class()
        app = ReviewTUI(session_id=session_id, db_path=db_path, config=engine_config)
        app.run()
        return
    # ... existing CLI path unchanged
```

### Full Inventory of Existing Code Changes

| File | Change | Lines (est.) |
|------|--------|-------------|
| `loop/engine.py` | Add `"tui"` verbosity mode to `_emit_progress()`: skip `print()`, dispatch to callbacks instead. Add 6 callback dispatch points. | ~40 |
| `loop/engine.py` | Accept `callbacks: dict | None = None` in `__init__` | ~5 |
| `cli.py` | Add `--tui` flag to `review` command, lazy import, app launch | ~15 |
| `cli.py` | Set `engine_config["verbosity"] = "tui"` when `--tui` is active | ~3 |
| `pyproject.toml` | Add `tui` optional dependency group | ~2 |
| **Total** | | **~65** |

No changes to: `sdk_wrapper.py`, `agents.py`, `db.py`, `session.py`, `feedback.py`, `history.py`, `convergence.py`, `export.py`, `reviewer/*`.

---

## Widget Specifications

### SessionPanel (left sidebar)

Always visible. Shows static + slowly-changing session metadata.

| Field | Source | Update Frequency |
|-------|--------|-----------------|
| Phase | `session.phase` | On loop start/end |
| Status | `session.status` | On loop start/end/pause |
| Project | `session.project` | Never (static) |
| Backend | `session_config.claude_backend` | Never (static) |
| Complexity | `convergence.detect()` | On loop start |
| Round cap | `convergence.cap` | On loop start |

### ConvergencePanel (left sidebar, below session)

Updates after each round completes.

| Field | Source | Update Frequency | Available? |
|-------|--------|-----------------|------------|
| Issue trend | `[r.issue_count for r in rounds]` | Per round | Yes |
| Sparkline | Rendered from issue trend | Per round | Yes |
| GPT cost | `sum(r.review_cost for r in rounds)` | Per round | Yes |
| GPT tokens | `sum(r.input_tokens + r.output_tokens)` | Per round | Yes |

**Sparkline rendering** (using Unicode block elements):

```
Issues: 3>1>2>3>1
Trend:  |||.|
```

Mapping: `max_issues = max(trend)`, each bar = `round(val/max * 7)` mapped to `" ........"[index]` (actual Unicode: ` ▁▂▃▄▅▆▇`)

### PlanPanel (left sidebar, below convergence)

| Field | Source | Available? |
|-------|--------|------------|
| Draft number | `plan_drafts` table | Yes |
| Size (chars) | `len(current_plan)` | Yes |
| Growth % | `(new - original) / original` | Yes |
| Milestone count | Counted from plan headers | Yes |

### RoundList (main panel)

Scrollable list of rounds with status indicators.

| Icon | Meaning |
|------|---------|
| `ok` | Completed round (NO_GO, revised) |
| `**` | Final round (GO) |
| `!!` | Cap reached with criticals |
| `>>` | Currently active |
| `oo` | Pending (not yet started) |

(Actual rendering uses Unicode: `✓`, `★`, `⚠`, `▶`, `○`)

Each row: `{icon} R{n}  {verdict}  {issue_count} issues  ---- ${cost}`

Selectable — pressing Enter expands to RoundDetail.

### CurrentRound (main panel, below round list)

Shows live progress for the active round. Two sub-phases:

**Sub-phase 1: GPT Reviewing**
```
Phase: GPT reviewing...  ============....  67s
Reviewer: gpt-5.4 (reasoning=high)
Plan size: 13,761 chars
History: 7,187 chars
```

**Sub-phase 2: Claude Revising**
```
Phase: Claude revising...  ======..........  34s
Issues: 2 ACCEPT, 0 DEFER, 0 REJECT
Model: claude-sonnet-4-6 (direct)
```

Progress bar is time-based estimate (average of previous round latencies for that sub-phase).

### LogPanel (bottom)

Timestamped, color-coded messages.

| Level | Color | Examples |
|-------|-------|---------|
| info | default | "R3: NO_GO -- 2 issues (2 ACCEPT)" |
| success | green | "Converged! 7 rounds, $0.447" |
| warning | yellow | "Timeout after 120s, retrying (1/1)" |
| error | red | "Error during review loop: ..." |

Filterable via `l` key (cycle: all > warn+ > error only).

---

## Keybindings

| Key | Action | Context |
|-----|--------|---------|
| `d` | Show dispositions screen | Any time |
| `h` | Show history context size per round | Any time |
| `p` | Show full plan text | Any time |
| `l` | Cycle log filter level | Any time |
| `Enter` | Expand selected round detail | Round list focused |
| `Escape` | Back to round list | In detail/modal view |
| `n` / `k` | Next/prev round in detail view | In round detail |
| `r` | Show raw GPT response (debug) | In round detail |
| `q` | Quit TUI | Any time |
| `?` | Help screen | Any time |

---

## Data Flow (end-to-end)

```
CLI: planner-auto review <id> --tui
  |
  +-- Load session from DB
  +-- Create ReviewTUI app with session_id, db_path, engine_config
  +-- engine_config["verbosity"] = "tui"
  +-- app.run() starts Textual event loop
  |
  +-- on_mount():
       +-- Populate SessionPanel from DB
       +-- Populate ConvergencePanel (empty)
       +-- Populate PlanPanel from latest draft
       +-- Start worker thread:
       |     |
       |     +-- ReviewLoopEngine.run(callbacks=adapter)
       |           |
       |           +-- Round 1:
       |           |   +-- adapter.on_round_start(1, 12)     -> RoundList adds ">> R1"
       |           |   +-- GPT reviews...
       |           |   +-- adapter.on_review_complete(...)    -> RoundList updates "ok R1 NO_GO 3"
       |           |   |                                      -> ConvergencePanel updates
       |           |   +-- Claude validates feedback...
       |           |   +-- adapter.on_feedback_validated(...) -> CurrentRound shows dispositions
       |           |   +-- Claude revises...
       |           |   +-- adapter.on_revision_complete(...)  -> PlanPanel updates size
       |           |
       |           +-- Round 2-N: (same pattern)
       |           |
       |           +-- adapter.on_loop_finished(result)       -> Final state rendered
       |
       +-- on LoopFinished:
            +-- Update all panels to final state
            +-- Show result summary in main panel
            +-- Log panel gets final summary line
```

---

## `--tui` vs `--verbose` / `--debug` Semantics

| Flag combination | Behavior |
|-----------------|----------|
| `--tui` | TUI mode. Engine verbosity = `"tui"`. No stdout. Callbacks only. File logging at INFO. |
| `--tui --verbose` | TUI mode + verbose log panel. File logging at DEBUG. Log panel defaults to showing all levels. |
| `--tui --debug` | TUI mode + debug. Raw response viewable in round detail screen. File logging at DEBUG. |
| `--verbose` (no `--tui`) | Existing CLI behavior unchanged. |
| `--debug` (no `--tui`) | Existing CLI behavior unchanged. |
| (none) | Existing CLI quiet mode unchanged. |

The `--tui` flag is orthogonal to `--verbose`/`--debug`. TUI always suppresses stdout. The verbose/debug flags control how much detail is accessible within the TUI (log panel default level, whether raw response screen is available).

---

## Implementation Milestones

### M1: Foundation + Static Shell (~200 lines new code, ~65 lines changes)
- `tui/__init__.py` with lazy import + `get_review_app_class()`
- `tui/messages.py` with all 7 message types
- `tui/adapter.py` with TUIAdapter (one method per message type)
- `tui/review_app.py` ReviewTUI with static layout (panels populated from DB, no live updates)
- `tui/styles/theme.tcss` (port orchestrator-auto palette)
- `tui/bindings.py` (keybinding constants)
- `cli.py`: `--tui` flag on `review`, lazy import, app launch, verbosity wiring
- `loop/engine.py`: `"tui"` verbosity mode, `callbacks` param, 6 dispatch points
- `pyproject.toml`: `tui` optional dependency
- Tests: adapter message dispatch, verbosity mode routing

### M2: Live Widgets (~400 lines)
- `tui/widgets/session_panel.py` (static, populated on mount)
- `tui/widgets/convergence_panel.py` (sparkline, cost, trend — updates per round)
- `tui/widgets/plan_panel.py` (draft#, size, growth — updates on revision)
- `tui/widgets/round_list.py` (live round updates, selectable rows)
- `tui/widgets/current_round.py` (active round progress with time estimate)
- `tui/widgets/log_panel.py` (timestamped, color-coded, filterable)
- Worker thread integration: engine callbacks -> adapter -> post_message -> widget handlers
- Responsive layout CSS (3 breakpoints)

### M3: Drill-Down Screens (~250 lines)
- `tui/widgets/round_detail.py` (expanded single-round: GPT metrics, keep/trim, issues, draft diff)
- `tui/screens/disposition_screen.py` (full disposition list across all rounds)
- `tui/screens/plan_screen.py` (scrollable full plan text)
- `tui/screens/raw_response_screen.py` (debug: raw GPT response with security warning)
- `tui/screens/help_screen.py` (keybinding reference)
- Round navigation: Enter to expand, Escape to collapse, n/p to navigate

---

## Dependency Changes

```toml
# pyproject.toml
[project.optional-dependencies]
tui = ["textual>=0.80.0"]
dev = ["pytest", "textual[dev]>=0.80.0"]
```

Textual is optional. Without it, `--tui` prints:

```
TUI mode requires the 'textual' package. Install with:
  pip install planner-auto[tui]
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Textual API changes | Medium | High | Pin minimum version, use stable APIs only |
| Thread safety bugs | Medium | High | Strict message-passing, no shared mutable state |
| Terminal compatibility | Low | Medium | Textual handles most terminals; test iTerm2, Terminal.app, tmux |
| Callback overhead | Low | Low | Callbacks are lightweight; only TUI mode pays the cost |
| Plan text too large for modal | Low | Medium | Scrollable views, lazy rendering |
| Engine stdout leak in TUI mode | Medium | High | Explicit `if verbosity == "tui": return` guard at top of `_emit_progress` |
| Claude metrics shown as `n/a` confuses users | Low | Low | Clear labeling: "GPT cost" not "total cost" |

---

## Success Criteria

| Criterion | Measurement |
|-----------|-------------|
| Review dashboard shows GPT round metrics in real time | Run review on stress-test session, verify all available fields update |
| Convergence visible at a glance | Issue trend + sparkline readable without scrolling |
| No regressions in CLI mode | All 401 existing tests pass with no TUI dependency |
| Stdout fully suppressed in TUI mode | Run `--tui` and pipe stdout to `wc -l` — zero lines |
| Small terminal usable | 60-column terminal shows round list + trend + cost |
| `n/a` fields clearly labeled | Claude revision shows "latency only" not broken data |
| No thread safety issues | Run 5+ review sessions without hangs or crashes |

---

## Future Work (Separate Proposals)

| Feature | Depends On | Notes |
|---------|-----------|-------|
| **Discuss TUI** | This proposal (shared theme, adapter pattern) | Chat interface with context sidebar |
| **Inspect TUI** | Command shape decision (`inspect --tui` vs unified inspector) | Read-only session viewer with convergence chart |
| **Claude revision metadata** | `query_claude()` return type change | Enables full cost breakdown in TUI |
| **Interactive actions** | Discuss TUI + workflow semantics | Resume, edit plan, complete from TUI |

---

## References

- orchestrator-auto TUI: `orchestrator-auto/orchestrator_auto/tui/` (13 widgets, 4 app classes, 30+ message types)
- planner-auto engine: `planner-auto/planner_auto/loop/engine.py` (callback integration target)
- planner-auto CLI: `planner-auto/planner_auto/cli.py` (`--tui` flag integration)
- planner-auto inspect: `planner-auto/planner_auto/cli.py:895` (current subgroup structure)
