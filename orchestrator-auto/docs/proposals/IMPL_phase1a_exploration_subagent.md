# Implementation Ticket: Phase 1A - Exploration Sub-Agent

**Ticket ID:** ORCH-SUB-001
**Status:** Ready for Development
**Priority:** High
**Proposal:** [PROPOSAL_subagent_exploration.md](./PROPOSAL_subagent_exploration.md)
**Dependencies:** orchestrator-auto v1.2.0, claude-agent-sdk 0.1.23

---

## Summary

Implement the ability for the Executor agent to spawn lightweight Explore sub-agents before milestone execution. Sub-agents perform read-only codebase exploration and return structured findings (file paths, pattern names, key snippets) with light compaction to enrich the executor's context.

> **Distinction from Research:** Exploration returns structured findings with minimal processing. Research agents (Phase 2) perform full summarization of large content bodies. This separation keeps Exploration simple and fast.

---

## Acceptance Criteria

### Functional Requirements

- [ ] **AC-1**: Executor can spawn Explore sub-agent via `_run_exploration()` method
- [ ] **AC-2**: Explore sub-agent has access only to read-only tools: `Glob`, `Grep`, `Read`
- [ ] **AC-3**: Exploration results are lightly compacted (structured findings) before injection into executor context - not full summarization
- [ ] **AC-4**: CLI flag `--explore` enables exploration (default when `auto_explore: true`)
- [ ] **AC-5**: CLI flag `--no-explore` disables exploration for simple tasks
- [ ] **AC-6**: CLI flag `--explore-query "..."` allows custom exploration queries
- [ ] **AC-7**: Exploration metrics visible in `orchestrator status <session-id>`

### Governance Requirements (Mandatory)

- [ ] **GOV-1**: Token cap per exploration sub-agent: **max 25,000 tokens**
  - Enforced via `max_tokens` parameter on sub-agent query
  - If exceeded, exploration terminates gracefully with partial results

- [ ] **GOV-2**: Turn cap per exploration: **max 5 turns**
  - Prevents runaway exploration loops
  - Configurable via `explore_max_turns` in config.yaml

- [ ] **GOV-3**: Timeout per exploration: **30 seconds**
  - Hard timeout, returns partial results on expiry

- [ ] **GOV-4**: Concurrency cap: **1 exploration sub-agent at a time** (Phase 1)
  - Parallel exploration deferred to Phase 3
  - Config option `explore_max_parallel: 1` (immutable in Phase 1)

### Failure Propagation Requirements (Mandatory)

- [ ] **FAIL-1**: Sub-agent errors surface to parent with full context
  ```python
  class ExplorationError(Exception):
      def __init__(self, query: str, cause: Exception, partial_results: str = None):
          self.query = query
          self.cause = cause
          self.partial_results = partial_results
  ```

- [ ] **FAIL-2**: Exploration failure does NOT block milestone execution
  - Log warning, continue with empty exploration context
  - User sees: "Exploration failed: {reason}. Proceeding without exploration context."

- [ ] **FAIL-3**: Exploration errors logged to session error table
  - Error type, query, cause, timestamp
  - Visible in `orchestrator status --errors`

- [ ] **FAIL-4**: Partial results on timeout/token-limit are usable
  - Return whatever was gathered before limit hit
  - Marked as `[EXPLORATION_PARTIAL]` in context

---

## Technical Design

### New Files

| File | Purpose |
|------|---------|
| `orchestrator_auto/explore.py` | `ExploreSubAgent` class, exploration prompt templates |

### Modified Files

| File | Changes |
|------|---------|
| `agents.py` | Add `_run_exploration()`, `_compact_findings()` to ExecutorAgent |
| `engine.py` | Call exploration before milestone execution when enabled |
| `cli.py` | Add `--explore`, `--no-explore`, `--explore-query` flags |
| `config.py` | Add `executor.auto_explore`, `executor.explore_max_turns` |
| `db.py` | Add `exploration_results` table for metrics/caching |

### API Contract

```python
class ExploreSubAgent:
    async def explore(
        self,
        queries: List[str],
        scope: Optional[str] = None,  # e.g., "src/auth/"
        max_turns: int = 5,
        max_tokens: int = 25_000,
        timeout: float = 30.0
    ) -> ExplorationResult:
        """
        Returns:
            ExplorationResult with:
            - findings: str (summarized)
            - sources_consulted: List[str]
            - tokens_used: int
            - is_partial: bool
        """
```

### Configuration Schema

```yaml
# config.yaml
executor:
  auto_explore: false          # Initial default: false; recommend true after validation
  explore_max_turns: 5         # Default: 5
  explore_max_tokens: 25000    # Default: 25000
  explore_timeout: 30          # Default: 30 seconds
  explore_patterns:            # Auto-detection patterns
    - "existing implementations"
    - "naming conventions"
    - "test patterns"
```

---

## Test Plan

### Unit Tests

- [ ] `test_explore_subagent_read_only_tools` - Verify only Glob/Grep/Read available
- [ ] `test_explore_token_limit_enforced` - Verify 25K cap
- [ ] `test_explore_turn_limit_enforced` - Verify 5 turn cap
- [ ] `test_explore_timeout_returns_partial` - Verify graceful timeout
- [ ] `test_explore_failure_does_not_block_execution` - Verify fallback
- [ ] `test_explore_error_logged_to_db` - Verify error persistence
- [ ] `test_explore_results_compacted` - Verify light compaction (not full summarization)

### Integration Tests

- [ ] `test_milestone_with_exploration_enabled` - End-to-end with `--explore`
- [ ] `test_milestone_with_exploration_disabled` - End-to-end with `--no-explore`
- [ ] `test_custom_explore_query` - End-to-end with `--explore-query`

---

## Rollout Plan

1. **Feature flag**: `ORCHESTRATOR_EXPLORE_ENABLED=false` (off by default)
2. **Internal testing**: Enable for 1 week on internal projects
3. **Documentation**: Update README, add to CLI help
4. **Default on**: Flip `auto_explore: true` after validation

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Exploration success rate | > 95% |
| Average exploration tokens | < 15,000 |
| Average exploration time | < 15 seconds |
| CHANGES_REQUESTED reduction | 15-25% fewer rejections |

---

## Open Questions

1. Should exploration results be cached across milestones? (Deferred to Phase 2)
2. Should we support multiple exploration queries in parallel? (Deferred to Phase 3)
