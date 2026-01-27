# Proposal: Auto-Retry for Empty Planner Responses

## Problem Statement

When the planner agent returns an empty response during milestone validation, the orchestrator immediately creates a blocker requiring human intervention. This happens more frequently than expected due to:

- API timeouts or transient network issues
- Agent session disconnects
- Token limit edge cases
- Claude API rate limiting

**Example from session `ce35c85d`:**
```
executor → 5417 chars (valid progress report with [PROGRESS_REPORT] tag)
planner  → 0 chars (empty response - no tags!)
         → Blocker created, workflow paused
```

The user must manually run `orchestrator respond <id> "..."` to continue, even though a simple retry would likely succeed.

## Current Behavior

In `engine.py:_route_to_planner()`:

1. Planner receives validation prompt with executor's progress report
2. Response is parsed for tags (`[MILESTONE_APPROVED]`, `[CHANGES_REQUESTED]`, `[HUMAN_INPUT_NEEDED]`)
3. If no valid tag found:
   - Check if response is truncated → auto-continue (existing fix)
   - Otherwise → create blocker (requires human intervention)

**The gap:** Empty responses (`""` or whitespace-only) are not considered "truncated" by `is_response_truncated()` (line 308-309 in `parser.py`):
```python
if not content:
    return False  # Empty is NOT truncated
```

So empty responses bypass the auto-continuation logic and immediately create a blocker.

**Additional risk:** If `agent.send_message()` returns `None` (possible on SDK/network edge cases), `parse_planner_response(None)` will crash with `TypeError` because `re.search()` expects a string.

## Proposed Solution

Add empty response detection with auto-retry **immediately after receiving the response** in `_route_to_planner()`, before any parsing or logging that assumes a string.

### Algorithm

```
1. Send validation prompt to planner
2. IMMEDIATELY check if response is None/empty/whitespace (before parsing!):
   a. If empty → Log warning: "Planner returned empty response. Retrying..."
   b. For retry_num in 1..MAX_EMPTY_RETRIES (default: 2):
      - Wait backoff (0.5 * retry_num seconds)
      - Send retry prompt with progress report excerpt
      - If response is non-empty:
        - Parse for tags (safe now - response is a non-empty string)
        - If valid tag found → handle normally (approve/changes/blocked)
        - If no valid tag → break loop, fall through to existing logic
      - If still empty → log and continue to next retry
   c. If all retries empty → create blocker with helpful message
3. If response is non-empty → proceed with existing parsing and truncation checks
```

**Critical ordering:** The empty/None check MUST happen before `parse_planner_response()` or `_log_message()` to avoid `TypeError` on `None`.

### Retry Prompt Design

```
Your previous response was empty. Please validate Milestone {N}.

Progress report summary:
{report[:1500]}...

Respond with [MILESTONE_APPROVED], [CHANGES_REQUESTED] with issues, or [HUMAN_INPUT_NEEDED].
```

Key design choices:
- **Truncate report to 1500 chars** - Reduces token usage on retry, less likely to hit limits
- **Explicit tag options** - Reminds planner of expected output format
- **Milestone number included** - Provides context if agent state was lost
- **Small backoff between retries** - `0.5 * retry_num` seconds helps with transient rate limiting
- **Treat `None` as empty** - SDK may return `None` on network edge cases; handle identically to `""`

## Implementation Details

### File: `orchestrator_auto/engine.py`

**Location:** `_route_to_planner()` method, **immediately after** `response = self._send_with_activity(...)` and **before** any `parse_planner_response()` or `_log_message()` calls.

**Critical:** The empty/None check must be the first thing that touches `response` to avoid `TypeError`.

**Dependencies:**
- Add `import time` at module level (not currently imported in engine.py)
- Helper function `_is_empty_response(response)` recommended for clarity:
  ```python
  def _is_empty_response(response: Optional[str]) -> bool:
      return response is None or not response.strip()
  ```

### Code Changes

```python
# At top of engine.py (add if not present)
import time

# Helper method (add to Orchestrator class)
def _is_empty_response(self, response: Optional[str]) -> bool:
    """Check if response is None, empty, or whitespace-only."""
    return response is None or not response.strip()

# In _route_to_planner(), IMMEDIATELY after initial send:
response = self._send_with_activity(
    planner, validation_prompt, "Validating milestone", agent_name="planner"
)

# NEW: Check for empty/None BEFORE any parsing or logging
MAX_EMPTY_RETRIES = 2
if self._is_empty_response(response):
    self._output("\n⚠ Planner returned empty response. Retrying validation...\n")

    for retry_num in range(1, MAX_EMPTY_RETRIES + 1):
        # Small backoff to help with transient rate limiting
        time.sleep(0.5 * retry_num)

        retry_prompt = (
            f"Your previous response was empty. Please validate Milestone {self.state.current_milestone}.\n\n"
            f"Progress report summary:\n{report[:1500]}{'...' if len(report) > 1500 else ''}\n\n"
            "Respond with [MILESTONE_APPROVED], [CHANGES_REQUESTED] with issues, or [HUMAN_INPUT_NEEDED]."
        )
        response = self._send_with_activity(
            planner, retry_prompt, f"Planner retry {retry_num}/{MAX_EMPTY_RETRIES}", agent_name="planner"
        )

        if not self._is_empty_response(response):
            # Got non-empty response - log it and parse
            self._log_message("planner", "assistant", response)
            response_type, data = parse_planner_response(response)

            if response_type == PLANNER_APPROVED:
                milestone_num = data.get("milestone", self.state.current_milestone)
                self._output(f"\n✓ Planner approved Milestone {milestone_num} (after retry)\n")
                return ("approved", None)

            elif response_type == PLANNER_CHANGES_REQUESTED:
                issues = data.get("issues", [])
                self._output(f"\n⚠ Planner requested changes (after retry):\n")
                for issue in issues:
                    self._output(f"  - {issue}\n")
                if issues:
                    issues_text = "\n".join([f"- {issue}" for issue in issues])
                else:
                    issues_text = "- No specific issues parsed. Please review the planner's feedback above."
                feedback = CHANGES_REQUESTED_TEMPLATE.format(
                    milestone_number=self.state.current_milestone,
                    issues=issues_text
                )
                executor_response = self._route_to_executor(feedback)
                return ("changes_requested", executor_response)

            elif response_type == PLANNER_BLOCKED:
                question = data.get("question", "Unknown question")
                self._handle_blocker("planner", question)
                return ("blocked", None)

            # Got non-empty response but no valid tag - break to try existing logic
            break

        self._output(f"\n⚠ Retry {retry_num} also returned empty.\n")

    # All retries exhausted and still empty
    if self._is_empty_response(response):
        self._output("\n⚠ All retries returned empty. Pausing for human review.\n")
        self._handle_blocker(
            "planner",
            f"Planner returned empty responses after {MAX_EMPTY_RETRIES} retries. "
            f"This may indicate API issues. Please respond with guidance "
            f"(e.g., 'approve milestone {self.state.current_milestone}')."
        )
        return ("blocked", None)

# NOW safe to log and parse (response is guaranteed non-empty string here)
self._log_message("planner", "assistant", response)
response_type, data = parse_planner_response(response)

# EXISTING: Handle response_type (approved/changes/blocked) or truncation check...
```

**Note on code duplication:** The retry loop re-implements approved/changes/blocked handling. This is acceptable for the initial implementation but could be refactored into a shared helper if the main handling logic changes frequently.

## Testing Strategy

### Unit Tests (`tests/test_engine.py`)

**Note:** Existing `TestTruncatedResponseContinuation` class already uses the side-effect pattern needed for these tests (planner returns incomplete text, then valid response on continuation). Empty-retry tests follow the same pattern, substituting `""` for incomplete text. No test harness changes required.

1. **test_route_to_planner_empty_response_retry_succeeds**
   - Mock planner to return `""` on first call, `"[MILESTONE_APPROVED]"` on second
   - Assert: returns `("approved", None)`, no blocker created

2. **test_route_to_planner_none_response_retry_succeeds**
   - Mock planner to return `None` on first call, `"[MILESTONE_APPROVED]"` on second
   - Assert: returns `("approved", None)`, no crash, no blocker created

3. **test_route_to_planner_empty_response_all_retries_fail**
   - Mock planner to return `""` on all calls
   - Assert: blocker created with retry count in message

4. **test_route_to_planner_empty_then_changes_requested**
   - Mock planner to return `""` then `"[CHANGES_REQUESTED]\n- Fix tests"`
   - Assert: returns `("changes_requested", executor_response)`

5. **test_route_to_planner_empty_then_unparseable**
   - Mock planner to return `""` then `"I think it looks good"` (no tag)
   - Assert: falls through to truncation check or blocker

### Integration Test

- Simulate transient API failure during milestone validation
- Verify workflow auto-recovers without human intervention

## Alternatives Considered

### 1. Modify `is_response_truncated()` to return `True` for empty strings

**Pros:** Simpler change, reuses existing auto-continuation logic
**Cons:** Semantically incorrect (empty != truncated), continuation prompt assumes partial content exists

### 2. Add generic retry wrapper around all agent calls

**Pros:** Handles empty responses everywhere
**Cons:** Over-engineered, different contexts need different retry strategies

### 3. Increase API timeout / add connection retry at SDK level

**Pros:** Addresses root cause
**Cons:** Doesn't help if the issue is agent-side (context loss, etc.)

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Infinite retry loop | Hard cap at MAX_EMPTY_RETRIES (2) |
| Increased API costs | Max 2 extra calls per validation, only on failure |
| Retry succeeds but with wrong context | Include milestone number and report excerpt in retry prompt |
| Masking real issues | Still creates blocker after retries, with clear "after N retries" message |
| Rate limiting causes repeated failures | Small backoff (0.5s, 1.0s) gives API time to recover |
| `None` response crashes parser | Check for `None`/empty **before** any parsing or logging |
| Code duplication in retry loop | Acceptable for now; refactor to shared helper if main logic changes |

## Success Metrics

- **Reduction in blocker rate** for empty response issues (target: 80%+ auto-recovered)
- **No increase** in incorrect milestone approvals
- **Session logs** show retry attempts for debugging

## Rollout Plan

1. Implement and add unit tests
2. Test on 2-3 real workflows with intentional API interruptions
3. Monitor blocker creation rate for first week
4. Adjust MAX_EMPTY_RETRIES if needed (consider making configurable only if ops requests it)

## Open Questions (Resolved)

| Question | Decision | Rationale |
|----------|----------|-----------|
| Should MAX_EMPTY_RETRIES be configurable? | **No** (for now) | Hardcoded constant is fine initially. Add config later if ops needs tuning. |
| Should we add a small delay between retries? | **Yes** | Added `time.sleep(0.5 * retry_num)` to help with transient rate limiting. |
| Should this apply to `_route_to_executor()` too? | **Deferred** | Executor already has truncation continuation. Empty executor responses are a separate concern for a future change. |

## Review Status

### Review Round 1 (2025-01-27)
- **Verdict:** Approved with minor additions
- **Notes:** Testing feasibility verified—existing `TestTruncatedResponseContinuation` class uses the same side-effect pattern. Added backoff, resolved open questions.

### Review Round 2 (2025-01-27)
- **Verdict:** Ready for implementation (critical fix applied)
- **Critical fix:** Empty/None check must happen **immediately after** `_send_with_activity()` and **before** any parsing/logging to avoid `TypeError` on `None` responses.
- **Minor fixes:**
  - `import time` must be added (not currently in engine.py)
  - Added `_is_empty_response()` helper for clarity
  - Added test case for `None` response
  - Noted code duplication as future refactoring opportunity
