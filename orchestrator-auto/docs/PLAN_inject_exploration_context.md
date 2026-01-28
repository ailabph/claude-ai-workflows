# Implementation Plan: Inject Exploration Context into Executor

**Status:** DRAFT
**Version:** 1.4.x
**Date:** 2026-01-28

---

## Overview

Currently, the `--explore` flag runs an exploration sub-agent before each milestone to discover codebase patterns, but the results are only used for UI display. This plan proposes injecting those exploration results into the Executor's milestone prompt, giving it pre-gathered context about the codebase.

### Current State

```
Exploration runs → Results emitted as UI events → DISCARDED
                                                      ↓
Executor receives milestone prompt → Must rediscover codebase patterns itself
```

### Proposed State

```
Exploration runs → Results stored → Injected into milestone prompt
                                              ↓
Executor receives milestone prompt + exploration context → Starts with knowledge
```

---

## Goals

1. **Reduce redundant exploration** - Executor won't need to re-discover patterns the explore sub-agent already found
2. **Improve implementation accuracy** - Executor starts with knowledge of existing conventions
3. **Maintain backward compatibility** - No changes to existing behavior without `--explore` flag

## Non-Goals

1. Changing the explore sub-agent's behavior or queries
2. Making exploration mandatory
3. Modifying the validation pipeline

---

## Architecture

### Component Interaction

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         WatchController                                  │
│                                                                         │
│  ┌─────────────────────┐    ┌─────────────────────────────────────┐    │
│  │ _run_exploration()  │───▶│ _exploration_results[milestone] = ctx│    │
│  └─────────────────────┘    └─────────────────────────────────────┘    │
│                                          │                              │
│                                          ▼                              │
│                              ┌───────────────────────┐                  │
│                              │ get_exploration_context│ ◀─── callback   │
│                              │     (milestone: int)   │                 │
│                              └───────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────┘
                                           │
                                           │ passed as parameter
                                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Orchestrator                                   │
│                                                                         │
│  __init__(                                                              │
│      ...                                                                │
│      exploration_context_provider: Optional[Callable[[int], str]]       │
│  )                                                                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                           │
                                           │ calls provider before prompt
                                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Engine._run_execution_loop()                        │
│                                                                         │
│  1. State changes to milestone N                                        │
│  2. _notify_state_change() → exploration runs (synchronous)             │
│  3. Build milestone_prompt                                              │
│  4. IF exploration_context_provider:                                    │
│        context = provider(current_milestone)                            │
│        IF context:                                                      │
│            milestone_prompt += context                                  │
│  5. Send to Executor                                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
ExplorationResult                    Formatted Context String
┌────────────────────┐              ┌─────────────────────────────────────┐
│ query: str         │              │ ## Exploration Context              │
│ findings: str      │  ────────▶   │                                     │
│ sources: List[str] │   format     │ The following patterns were found   │
│ tokens_used: int   │              │ in the codebase before you start:   │
│ is_partial: bool   │              │                                     │
└────────────────────┘              │ ### Query: "find auth patterns"     │
                                    │ [findings text...]                  │
                                    │                                     │
                                    │ ### Query: "find test conventions"  │
                                    │ [findings text...]                  │
                                    └─────────────────────────────────────┘
```

---

## Implementation

### Milestone 1: Store Exploration Results in WatchController

**Files:** `controllers/watch_controller.py`

#### 1.1 Add storage for exploration results

```python
class WatchController:
    def __init__(self, ...):
        # ... existing code ...

        # NEW: Store exploration results by milestone number
        self._exploration_results: Dict[int, List[ExplorationResult]] = {}
```

#### 1.2 Modify `_run_exploration()` to store results

```python
def _run_exploration(self, milestone_num: int) -> None:
    """Run exploration sub-agent before milestone execution."""
    agent = self._init_explore_agent()
    if not agent:
        return

    try:
        from ..explore import generate_exploration_queries

        milestone_text = self._get_milestone_text(milestone_num)
        queries = generate_exploration_queries(milestone_text)

        if not queries:
            return

        self.on_event(WatchEvent.EXPLORE_STARTED, {...})

        results = []
        for i, query in enumerate(queries):
            # ... existing event emission code ...

            result = agent.explore(query)
            results.append(result)

            # ... existing event emission code ...

        self.on_event(WatchEvent.EXPLORE_COMPLETED, {...})

        # NEW: Store results for later injection
        self._exploration_results[milestone_num] = results

    except Exception as e:
        self.on_event(WatchEvent.WARNING, {"message": f"Exploration failed: {e}"})
```

#### 1.3 Add method to format and retrieve exploration context

```python
# Constants for context limits
EXPLORATION_CONTEXT_MAX_CHARS = 4000  # Limit total context size
EXPLORATION_CONTEXT_MAX_PER_QUERY = 1500  # Limit per query

def get_exploration_context(self, milestone_num: int) -> Optional[str]:
    """
    Get formatted exploration context for a milestone.

    Returns None if no exploration results are available.
    Clears results after retrieval to free memory.
    """
    results = self._exploration_results.pop(milestone_num, None)
    if not results:
        return None

    # Filter to successful results only
    successful = [r for r in results if r.is_success()]
    if not successful:
        return None

    return self._format_exploration_context(successful)

def _format_exploration_context(self, results: List[ExplorationResult]) -> str:
    """Format exploration results as context for the Executor."""
    lines = [
        "## Exploration Context",
        "",
        "The following codebase patterns were discovered before this milestone:",
        ""
    ]

    total_chars = 0
    for result in results:
        # Truncate findings if too long
        findings = result.findings
        if len(findings) > EXPLORATION_CONTEXT_MAX_PER_QUERY:
            findings = findings[:EXPLORATION_CONTEXT_MAX_PER_QUERY] + "\n[truncated...]"

        # Check total limit
        entry = f"### Query: {result.query}\n\n{findings}\n"
        if total_chars + len(entry) > EXPLORATION_CONTEXT_MAX_CHARS:
            lines.append("\n[Additional exploration results truncated due to size...]")
            break

        lines.append(entry)
        total_chars += len(entry)

    lines.append("---")
    lines.append("")
    lines.append("Use these patterns to guide your implementation. Do not re-explore these areas.")

    return "\n".join(lines)
```

**Acceptance Criteria:**
- [ ] Exploration results stored in `_exploration_results` dict
- [ ] `get_exploration_context()` returns formatted string or None
- [ ] Results cleared after retrieval (memory management)
- [ ] Context truncated if exceeds limits

---

### Milestone 2: Add Context Provider to Orchestrator

**Files:** `engine.py`

#### 2.1 Add optional parameter to Orchestrator.__init__

```python
class Orchestrator:
    def __init__(
        self,
        feature_description: str = "",
        db_path: Optional[str] = None,
        plan_path: Optional[str] = None,
        session_id: Optional[str] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
        on_state_change: Optional[Callable[["WorkflowState"], None]] = None,
        on_output: Optional[Callable[[str], None]] = None,
        input_provider: Optional[InputProvider] = None,
        planner_model: Optional[str] = None,
        executor_model: Optional[str] = None,
        mcp_config_path: Optional[str] = None,
        headless: bool = False,
        telegram_notifier: Optional[Any] = None,
        show_activity: bool = True,
        auto_commit: bool = False,
        smart_commit: Optional[bool] = None,
        # NEW: Optional provider for exploration context
        exploration_context_provider: Optional[Callable[[int], Optional[str]]] = None,
    ):
        # ... existing code ...

        # NEW: Store exploration context provider
        self._exploration_context_provider = exploration_context_provider
```

#### 2.2 Modify `_run_execution_loop()` to inject context

```python
def _run_execution_loop(self, executor: ExecutorAgent, planner: PlannerAgent) -> None:
    """Run the execution loop for milestones."""
    # ... existing setup code ...

    while current_milestone <= total_milestones:
        self._output(f"\n--- Milestone {current_milestone}/{total_milestones} ---\n")

        # Set checkpoint before milestone
        if self._enable_rewind:
            checkpoint_uuid = executor.set_checkpoint()
            if checkpoint_uuid and isinstance(checkpoint_uuid, str):
                self._output(f"📍 Checkpoint set: {checkpoint_uuid[:8]}...\n")

        # Generate milestone prompt
        milestone_prompt = MILESTONE_PROMPT_TEMPLATE.format(
            feature_description=self.state.feature_description,
            total_milestones=total_milestones,
            plan_path=self.state.plan_path or "docs/plan.md",
            milestone_number=current_milestone,
            milestone_name=f"Milestone {current_milestone}",
            milestone_tasks=f"Execute Milestone {current_milestone} from the plan",
            next_milestone_number=current_milestone + 1
        )

        # NEW: Inject exploration context if available
        if self._exploration_context_provider:
            try:
                exploration_context = self._exploration_context_provider(current_milestone)
                if exploration_context:
                    self._output("📚 Injecting exploration context...\n")
                    milestone_prompt = exploration_context + "\n\n" + milestone_prompt
            except Exception as e:
                # Don't fail milestone if context injection fails
                self._output(f"⚠ Could not inject exploration context: {e}\n")

        # Send to executor
        self._output("→ Sending milestone to Executor...\n")
        executor_response = self._send_with_activity(
            executor, milestone_prompt, "Executor implementing", agent_name="executor"
        )

        # ... rest of existing code ...
```

**Acceptance Criteria:**
- [ ] New optional parameter `exploration_context_provider` added
- [ ] Context injected before milestone prompt if provider returns content
- [ ] Failures in context injection logged but don't break execution
- [ ] Context prepended to prompt (exploration context first, then instructions)

---

### Milestone 3: Wire WatchController to Orchestrator

**Files:** `controllers/watch_controller.py`

#### 3.1 Pass context provider when creating Orchestrator

```python
def _process_file(self, plan_path: Path) -> None:
    """Process a single plan file."""
    # ... existing code ...

    try:
        state_change_callback = self._create_state_change_wrapper(self.on_state_change)

        # NEW: Create context provider bound to this controller
        exploration_provider = None
        if self.explore_enabled:
            exploration_provider = self.get_exploration_context

        orch = Orchestrator(
            feature_description=feature,
            plan_path=str(plan_path),
            db_path=self.db_path,
            on_chunk=self.on_chunk,
            on_state_change=state_change_callback,
            on_output=self.on_output,
            planner_model=self.planner_model,
            executor_model=self.executor_model,
            mcp_config_path=self.mcp_config,
            headless=self.headless,
            telegram_notifier=self._telegram_notifier,
            auto_commit=self.auto_commit,
            smart_commit=self.smart_commit,
            # NEW: Pass exploration context provider
            exploration_context_provider=exploration_provider,
        )

        # ... rest of existing code ...
```

**Acceptance Criteria:**
- [ ] Context provider passed to Orchestrator only when `--explore` is enabled
- [ ] Provider is bound method `self.get_exploration_context`
- [ ] No changes when `--explore` is not enabled

---

### Milestone 4: Testing

**Files:** `tests/test_watch_controller.py`, `tests/test_engine.py`

#### 4.1 Unit tests for exploration context storage

```python
def test_exploration_results_stored():
    """Verify exploration results are stored by milestone number."""
    controller = WatchController(...)
    # Mock exploration
    controller._exploration_results[1] = [mock_result]

    context = controller.get_exploration_context(1)
    assert context is not None
    assert "Exploration Context" in context

    # Verify cleared after retrieval
    assert controller.get_exploration_context(1) is None

def test_exploration_context_truncation():
    """Verify large exploration results are truncated."""
    # Create result with very long findings
    result = ExplorationResult(
        query="test",
        findings="x" * 10000,  # Very long
        ...
    )
    controller._exploration_results[1] = [result]

    context = controller.get_exploration_context(1)
    assert len(context) <= EXPLORATION_CONTEXT_MAX_CHARS + 500  # Allow for formatting

def test_exploration_context_failed_results_excluded():
    """Verify failed exploration results are not included."""
    failed_result = ExplorationResult(query="test", findings="", error="timeout")
    controller._exploration_results[1] = [failed_result]

    context = controller.get_exploration_context(1)
    assert context is None  # No successful results
```

#### 4.2 Integration tests for context injection

```python
def test_milestone_prompt_includes_exploration_context(mock_orchestrator):
    """Verify exploration context is prepended to milestone prompt."""
    provider = lambda m: "## Exploration Context\n\nTest context"
    orch = Orchestrator(..., exploration_context_provider=provider)

    # Capture the prompt sent to executor
    captured_prompt = None
    def capture_send(prompt, *args, **kwargs):
        nonlocal captured_prompt
        captured_prompt = prompt
        return "[PROGRESS_REPORT]...[/PROGRESS_REPORT]"

    # Run execution and verify
    assert "## Exploration Context" in captured_prompt
    assert "Test context" in captured_prompt

def test_milestone_prompt_without_exploration_context(mock_orchestrator):
    """Verify prompt unchanged when no exploration context provider."""
    orch = Orchestrator(..., exploration_context_provider=None)

    # Capture and verify no exploration section
    assert "## Exploration Context" not in captured_prompt
```

#### 4.3 End-to-end test

```python
@pytest.mark.integration
def test_watch_mode_with_explore_injects_context(tmp_path):
    """Full integration test: watch mode with --explore injects context."""
    # Create test plan
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n## Milestone 1\n- Task 1")

    # Run watch with explore
    controller = WatchController(
        plans_dir=str(tmp_path),
        explore_enabled=True,
        ...
    )

    # Mock executor to capture prompt
    # Verify exploration context in prompt
```

**Acceptance Criteria:**
- [ ] Unit tests for storage/retrieval/truncation
- [ ] Unit tests for failed result handling
- [ ] Integration tests for prompt injection
- [ ] Tests pass with and without `--explore` flag

---

## Rollout Plan

### Phase 1: Feature Flag (Optional)

Add config option to enable/disable injection separately from exploration:

```yaml
# config.yaml
exploration:
  enabled: true
  inject_context: true  # NEW: Can disable injection while keeping UI
```

### Phase 2: Default Behavior

Once validated, make injection the default when `--explore` is enabled.

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Large context bloats prompt | Truncate to 4000 chars max |
| Context injection fails | Catch exception, log warning, continue without context |
| Memory leak from stored results | Clear results after retrieval |
| Breaks non-watch mode | Provider is None, no injection |
| Breaks tests | Optional parameter, existing tests unchanged |

---

## Metrics to Track

1. **Token usage** - Compare with/without context injection
2. **Milestone success rate** - Does context improve first-attempt success?
3. **Exploration redundancy** - Does Executor still call Glob/Grep for same patterns?

---

## Future Enhancements

1. **Smart context selection** - Only inject relevant exploration results based on milestone content
2. **Persistent exploration cache** - Store in DB for session resume
3. **Exploration summary** - Use smaller model to summarize findings before injection
4. **Feedback loop** - If Executor finds context unhelpful, adjust queries

---

## Appendix: Example Injected Prompt

```markdown
## Exploration Context

The following codebase patterns were discovered before this milestone:

### Query: find authentication patterns

[EXPLORATION_COMPLETE]
### Files Found
- src/middleware/auth.py - JWT validation middleware
- src/models/user.py - User model with password hashing

### Patterns Identified
- Pattern: JWT tokens stored in Authorization header
- Pattern: Passwords hashed with bcrypt

### Key Snippets
```python
# src/middleware/auth.py
def validate_token(token: str) -> User:
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    return User.get(payload["user_id"])
```

### Recommendations
- Follow existing JWT pattern for new endpoints
- Use User.verify_password() for authentication
[/EXPLORATION_COMPLETE]

---

Use these patterns to guide your implementation. Do not re-explore these areas.

## Agent Task: Add user registration endpoint

### Workflow Instructions

Read `CLAUDE_orchestrator.md` first. You are the **EXECUTOR** agent.
...
```

---

## Approval

- [ ] Architecture approved
- [ ] Implementation milestones approved
- [ ] Risk assessment reviewed
- [ ] Ready for implementation

**Approved by:** _______________
**Date:** _______________
