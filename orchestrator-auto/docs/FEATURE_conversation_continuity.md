# Feature: Conversation Continuity for Agents

## Status: IMPLEMENTED

## Problem

Currently, each `send_message()` call to an agent starts a **fresh conversation** with no memory of previous exchanges. This causes:

1. **Discovery phase breaks**: When user sends multiple messages (e.g., feature description, then constraints), the planner loses context after each message
2. **Execution feedback breaks**: When planner requests changes from executor, the executor has no memory of what it was working on
3. **Poor UX**: Users expect a continuous conversation but get confused responses

### Example of the Problem

```
User: "Implement pagination for P2P trades"
Planner: "I'll help! Let me research..." [does research, asks questions]

User: "Use existing Pagination component"
Planner: "I understand. What feature would you like to build?" [LOST CONTEXT]
```

## Root Cause

The current implementation uses `query()` from the Claude Agent SDK:

```python
# agents.py - Current implementation
async for message in query(prompt=content, options=options):
    # Each call starts fresh - no conversation history
```

The SDK provides two approaches:
- `query()` - Stateless, fresh session each time
- `ClaudeSDKClient` - Maintains conversation context across calls

## Proposed Solution

Switch from `query()` to `ClaudeSDKClient` which maintains conversation history automatically.

## Implementation Notes (Completed)

The implementation switched from `query()` to `ClaudeSDKClient` in `orchestrator_auto/agents.py`:

1. **Added client state fields to `__init__`:**
   - `self._client: Optional[ClaudeSDKClient] = None`
   - `self._client_entered: bool = False`

2. **Added `_get_client()` method** - Creates and enters client context on first call, reuses on subsequent calls

3. **Updated `send_message_async()`** - Uses `client.process_query()` instead of `query()` to maintain conversation history

4. **Updated `close()` and added `close_async()`** - Properly exits client context manager

5. **Updated test mocks** - Changed from patching `query` to patching `ClaudeSDKClient`

All 161 tests pass.

---

## Original Implementation Plan

### Phase 1: Update BaseAgent Class

**File:** `orchestrator_auto/agents.py`

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

class BaseAgent:
    def __init__(self, ...):
        # ... existing init ...
        self._client: Optional[ClaudeSDKClient] = None
        self._client_context = None  # For async context manager

    async def _get_client(self) -> ClaudeSDKClient:
        """Get or create the SDK client with conversation continuity."""
        if self._client is None:
            self._client = ClaudeSDKClient()
            self._client_context = await self._client.__aenter__()
        return self._client

    async def send_message_async(
        self,
        content: str,
        on_chunk: Optional[Callable[[str], None]] = None
    ) -> str:
        """Send message with conversation continuity."""
        client = await self._get_client()
        options = self._get_options()
        response_text = ""

        await client.query(content, options=options)

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text
                        if on_chunk:
                            on_chunk(block.text)

        return response_text

    async def close_async(self) -> None:
        """Close the client connection."""
        if self._client_context:
            await self._client.__aexit__(None, None, None)
            self._client = None
            self._client_context = None

    def close(self) -> None:
        """Sync wrapper for close."""
        if self._client:
            asyncio.run(self.close_async())
```

### Phase 2: Update Engine to Manage Client Lifecycle

**File:** `orchestrator_auto/engine.py`

The engine already calls `_cleanup()` which calls `agent.close()`. This should work with the new implementation, but verify:

```python
def _cleanup(self) -> None:
    """Cleanup resources."""
    if self.planner:
        self.planner.close()  # Now properly closes ClaudeSDKClient
        self.planner = None
    if self.executor:
        self.executor.close()
        self.executor = None
```

### Phase 3: Handle Agent Recreation

When an agent is closed and recreated (e.g., resuming a session), it starts fresh. This is acceptable because:
- Session resume loads context from database
- Recovery prompts provide necessary context
- Each workflow phase can start with fresh agent if needed

### Phase 4: Update Tests

Mock `ClaudeSDKClient` instead of `query()` in tests:

```python
@patch('orchestrator_auto.agents.ClaudeSDKClient')
def test_send_message(self, mock_client_class):
    mock_client = AsyncMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client
    # ... test implementation
```

## Alternative Approaches Considered

### Option A: Use `resume` Parameter (Rejected)
- Pass session_id to resume conversations
- Requires capturing and storing session IDs
- More complex state management
- Rejected: ClaudeSDKClient is simpler for same-process continuity

### Option B: Accumulate Messages Manually (Rejected)
- Build conversation history in our code
- Pass full history with each call
- Rejected: SDK already handles this with ClaudeSDKClient

### Option C: Single Long Prompt (Rejected)
- Combine all user messages into one prompt
- Rejected: Changes UX, doesn't work for interactive discovery

## Complexity Estimate

| Task | Estimate |
|------|----------|
| Update BaseAgent class | ~1 hour |
| Test client lifecycle | ~30 min |
| Update mocks in tests | ~1 hour |
| Integration testing | ~30 min |
| **Total** | **~3 hours** |

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Client connection issues | Add retry logic, proper error handling |
| Memory usage with long conversations | Agent recreation between phases clears history |
| Breaking existing tests | Update mocks incrementally, run tests frequently |
| Async complexity | Use existing asyncio patterns from codebase |

## Testing Plan

1. **Unit Tests**
   - Test client creation and reuse
   - Test conversation continuity (mock multiple exchanges)
   - Test proper cleanup

2. **Integration Tests**
   - Test full discovery flow with multiple user messages
   - Test planner remembering context across messages
   - Test executor remembering context after changes requested

3. **Manual Testing**
   - Start session, send multiple messages, verify context retained
   - Test `/ready` detection with context
   - Test session resume after pause

## Success Criteria

1. User can send multiple messages in discovery phase, planner remembers all
2. Executor remembers context when changes are requested
3. All existing tests pass (with updated mocks)
4. No memory leaks from unclosed clients

## Open Questions

1. **Should we expose conversation reset?**
   - Add a method to clear conversation history without closing agent?
   - Use case: User wants to start fresh within same session

2. **Max conversation length?**
   - Should we limit turns to prevent context overflow?
   - SDK may have built-in limits

3. **Error recovery?**
   - If client connection fails mid-conversation, how to recover?
   - Options: Recreate client (loses history) or fail with clear error
