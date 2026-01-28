# Proposal: Executor Exploration Sub-Agents

**Status:** Approved
**Phase:** 1A (First Priority)
**Author:** Engineering Team
**Created:** 2026-01-28
**Updated:** 2026-01-28
**Category:** Architecture Enhancement

---

## Version Context

This proposal builds on **orchestrator-auto v1.2.0**, which integrated **Claude Agent SDK 0.1.23**. The SDK provides the foundational subagent capabilities (Task tool, context isolation) that this feature extends.

| Component | Version | Relevant Feature |
|-----------|---------|------------------|
| orchestrator-auto | 1.2.0 | File rewind, MCP status, tool audit |
| claude-agent-sdk | 0.1.23 | Task tool, subagent spawning, `rewind_files()` |

---

## Executive Summary

Enhance the Executor agent with the ability to spawn lightweight Explore sub-agents before implementing milestones. This reduces wasted tokens from incorrect assumptions and improves first-attempt success rates by ensuring the executor understands the codebase structure before writing code.

## Problem Statement

Currently, the Executor agent:
1. Receives a milestone prompt and immediately begins implementation
2. May make incorrect assumptions about file locations, naming conventions, or existing patterns
3. Wastes tokens exploring the codebase inline with implementation
4. Sometimes produces code that doesn't match existing project conventions

This leads to:
- Higher token consumption per milestone
- More frequent `CHANGES_REQUESTED` cycles
- Inconsistent code that requires manual cleanup

## Proposed Solution

Add an **optional exploration phase** before milestone execution:

```
┌─────────────────────────────────────────────────────────────────┐
│  EXECUTOR receives milestone                                     │
├─────────────────────────────────────────────────────────────────┤
│  1. Spawn Explore sub-agent with targeted questions             │
│     - "Find existing patterns for X"                            │
│     - "Locate files related to Y"                               │
│     - "Identify naming conventions for Z"                       │
│                                                                 │
│  2. Receive summarized exploration results                      │
│                                                                 │
│  3. Execute milestone with context-aware implementation         │
└─────────────────────────────────────────────────────────────────┘
```

### Architecture

```python
class ExecutorAgent(BaseAgent):
    async def execute_milestone_with_exploration(
        self,
        milestone: str,
        exploration_queries: List[str] = None
    ) -> str:
        # Phase 1: Exploration (optional)
        if exploration_queries or self.auto_explore:
            context = await self._run_exploration(milestone)
        else:
            context = ""

        # Phase 2: Implementation with enriched context
        enriched_prompt = f"{context}\n\n{milestone}"
        return await self.query_async(enriched_prompt)

    async def _run_exploration(self, milestone: str) -> str:
        """Spawn Explore sub-agent for codebase understanding."""
        explore_prompt = self._generate_exploration_prompt(milestone)

        # Sub-agent runs with read-only tools (Glob, Grep, Read)
        result = await self.client.query_async(
            prompt=explore_prompt,
            tools=["Glob", "Grep", "Read"],  # Read-only
            max_turns=5  # Limited exploration
        )

        return self._summarize_exploration(result)
```

### Configuration

```yaml
# config.yaml
executor:
  auto_explore: true           # Enable automatic exploration
  explore_max_turns: 5         # Limit exploration depth
  explore_patterns:            # What to look for
    - "existing implementations"
    - "naming conventions"
    - "test patterns"
    - "import structure"
```

### CLI Integration

```bash
# Enable exploration (default when auto_explore: true)
orchestrator start -f "Add user authentication" --explore

# Disable exploration for simple tasks
orchestrator start -f "Fix typo in README" --no-explore

# Custom exploration queries
orchestrator start -f "Add caching" --explore-query "Find existing cache implementations"
```

## Implementation Plan

### Phase 1: Core Infrastructure
- Add `ExploreSubAgent` class with read-only tool access
- Implement `_run_exploration()` method in ExecutorAgent
- Add exploration prompt templates

### Phase 2: Smart Exploration
- Analyze milestone text to auto-generate exploration queries
- Pattern matching for common exploration needs (new endpoint → find existing endpoints)
- Caching of exploration results for similar queries

### Phase 3: Configuration & CLI
- Add config file options
- Add CLI flags
- Add exploration metrics to session status

## Benefits

| Benefit | Impact |
|---------|--------|
| Reduced token waste | 20-40% fewer tokens per milestone |
| Higher first-attempt success | Fewer CHANGES_REQUESTED cycles |
| Consistent code style | Executor learns patterns before writing |
| Faster overall completion | Less back-and-forth with planner |

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Exploration takes too long | Cap at 5 turns, timeout after 30s |
| Sub-agent finds wrong patterns | Planner validates in review phase |
| Overhead for simple tasks | Auto-detect simple tasks, skip exploration |
| Token cost of exploration | Exploration uses cheaper model (Haiku) |

## Success Metrics

- Reduction in CHANGES_REQUESTED rate
- Tokens per successful milestone
- Exploration cache hit rate
- User satisfaction (optional exploration toggle usage)

## Effort Estimate

**Complexity:** Medium
**Files Modified:** 4-6 (agents.py, engine.py, config.py, cli.py, prompts.py)
**New Files:** 1-2 (explore.py, exploration templates)
**Testing:** Unit tests + integration tests for exploration flow

---

## Appendix: Exploration Prompt Template

```markdown
You are exploring a codebase to gather context for an upcoming implementation task.

## Task Context
{milestone_description}

## Exploration Goals
1. Find existing implementations of similar functionality
2. Identify naming conventions and patterns used
3. Locate relevant test files and testing patterns
4. Understand import structure and dependencies

## Constraints
- Read-only exploration (no file modifications)
- Focus on patterns, not implementation details
- Summarize findings concisely

Report your findings in this format:
[EXPLORATION_COMPLETE]
- Existing patterns: ...
- Naming conventions: ...
- Test locations: ...
- Key dependencies: ...
[/EXPLORATION_COMPLETE]
```
