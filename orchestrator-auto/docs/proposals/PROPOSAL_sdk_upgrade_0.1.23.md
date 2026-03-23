> **Status:** Superseded by PROPOSAL_sdk_upgrade_0.1.50.md

# Proposal: Upgrade to Claude Agent SDK 0.1.23

**Author:** Claude
**Created:** 2026-01-28
**Status:** Draft
**SDK Version:** 0.1.16 → 0.1.23

---

## Summary

Upgrade orchestrator-auto from `claude-agent-sdk` 0.1.16 to 0.1.23 and implement three new features enabled by the SDK improvements:

1. **File Rewind on Milestone Rejection** - Automatic rollback when `[CHANGES_REQUESTED]`
2. **MCP Status Monitoring** - Proactive MCP server health checks
3. **Tool Use Audit Trail** - Track tool invocations for debugging

---

## Motivation

### Current Limitations

| Problem | Impact |
|---------|--------|
| No file rollback on rejection | Executor must manually undo changes, risking incomplete cleanup |
| MCP failures detected late | Users only see errors when tools fail mid-execution |
| No tool usage visibility | Difficult to debug failed milestones or audit agent behavior |

### SDK Changelog (0.1.16 → 0.1.23)

| Version | Feature | Relevance |
|---------|---------|-----------|
| 0.1.17 | `uuid` field in UserMessage | Enables `rewind_files()` |
| 0.1.17 | `rewind_files(user_message_id)` method | File checkpoint/rollback |
| 0.1.22 | `tool_use_result` field in UserMessage | Tool invocation tracking |
| 0.1.23 | `get_mcp_status()` method | MCP server health monitoring |

---

## Feature 1: File Rewind on Milestone Rejection

### Overview

When a milestone is rejected (`[CHANGES_REQUESTED]`), automatically revert all file changes made during that milestone attempt before the executor retries.

### User Experience

```
┌─────────────────────────────────────────────────────────────┐
│ Milestone 2: Add user validation                            │
├─────────────────────────────────────────────────────────────┤
│ Executor: [PROGRESS_REPORT] Completed validation logic...   │
│                                                             │
│ Planner: [CHANGES_REQUESTED] Missing email format check     │
│                                                             │
│ ⟲ Rewinding 3 files to pre-milestone state...              │
│   ✓ src/validators.py                                       │
│   ✓ src/models/user.py                                      │
│   ✓ tests/test_validators.py                                │
│                                                             │
│ Executor: Retrying milestone with feedback...               │
└─────────────────────────────────────────────────────────────┘
```

### Technical Design

#### 1. Track Message UUIDs in BaseAgent

```python
# agents.py

class BaseAgent:
    def __init__(self, ...):
        # ...existing code...
        self._checkpoint_uuid: Optional[str] = None  # Last checkpoint before milestone
        self._last_message_uuid: Optional[str] = None  # Most recent message UUID

    async def send_message_async(self, content: str, ...) -> str:
        client = await self._get_client()
        response_text = ""

        await client.query(content)
        async for message in client.receive_messages():
            # NEW: Capture UUID from UserMessage (SDK 0.1.17+)
            if hasattr(message, 'uuid') and message.uuid:
                self._last_message_uuid = message.uuid

            if isinstance(message, AssistantMessage):
                # ...existing text extraction...
            elif isinstance(message, ResultMessage):
                # ...existing token usage...
                break

        return response_text

    def set_checkpoint(self) -> Optional[str]:
        """Mark current state as a checkpoint for potential rewind."""
        self._checkpoint_uuid = self._last_message_uuid
        return self._checkpoint_uuid

    async def rewind_to_checkpoint(self) -> bool:
        """Rewind files to last checkpoint. Returns True if successful."""
        if not self._checkpoint_uuid or not self._client:
            return False
        try:
            await self._client.rewind_files(self._checkpoint_uuid)
            return True
        except Exception as e:
            # Log but don't fail - rewind is best-effort
            return False
```

#### 2. Checkpoint Before Each Milestone

```python
# engine.py

async def _run_execution(self):
    """Execute milestones with file checkpointing."""

    for milestone_num in range(self.current_milestone, self.total_milestones + 1):
        # NEW: Set checkpoint before milestone starts
        checkpoint_id = self.executor.set_checkpoint()
        self._log(f"Checkpoint set: {checkpoint_id[:8]}..." if checkpoint_id else "No checkpoint")

        # Execute milestone
        response = await self.executor.send_message_async(milestone_prompt)

        # Validate with planner
        validation = await self.planner.send_message_async(validation_prompt)
        response_type, data = parse_planner_response(validation)

        if response_type == PLANNER_CHANGES_REQUESTED:
            # NEW: Rewind files before retry
            if await self.executor.rewind_to_checkpoint():
                self._log("⟲ Files rewound to checkpoint")

            # Continue with feedback to executor
            feedback = CHANGES_REQUESTED_TEMPLATE.format(...)
            response = await self.executor.send_message_async(feedback)
```

#### 3. Optional Rewind Flag

```python
# cli.py

@click.option('--no-rewind', is_flag=True,
              help='Disable automatic file rewind on milestone rejection')
def start(no_rewind, ...):
    orchestrator = Orchestrator(
        ...,
        enable_rewind=not no_rewind,
    )
```

### Database Schema Change

```sql
-- Add checkpoint tracking to milestones table
ALTER TABLE milestones ADD COLUMN checkpoint_uuid TEXT;
ALTER TABLE milestones ADD COLUMN rewind_count INTEGER DEFAULT 0;
```

### Edge Cases

| Scenario | Behavior |
|----------|----------|
| No checkpoint available | Skip rewind, log warning |
| Rewind fails | Log error, continue without rewind |
| Multiple rejections | Rewind to same checkpoint each time |
| User manually edited files | Rewind overwrites manual changes (warn in docs) |

---

## Feature 2: MCP Status Monitoring

### Overview

Add `get_mcp_status()` calls to provide visibility into MCP server connection health.

### Integration Points

#### 1. Enhance `orchestrator check`

```python
# cli.py

@cli.command()
def check():
    """Health check for orchestrator setup."""
    # ...existing checks...

    # NEW: Check MCP servers if configured
    mcp_config = load_mcp_config()
    if mcp_config:
        click.echo("\nMCP Servers:")
        async def check_mcp():
            async with ClaudeSDKClient(options) as client:
                status = await client.get_mcp_status()
                for server_name, info in status.items():
                    if info.get('connected'):
                        click.echo(f"  ✓ {server_name}: connected")
                    else:
                        click.echo(f"  ✗ {server_name}: {info.get('error', 'disconnected')}")
        asyncio.run(check_mcp())
```

#### 2. TUI Status Panel

```python
# tui/widgets/status_panel.py

class StatusPanel(Static):
    def compose(self):
        # ...existing widgets...
        yield Label("MCP:", id="mcp-label")
        yield Label("--", id="mcp-status")  # Updated via message

# tui/app.py
class OrchestratorTUI(App):
    async def update_mcp_status(self):
        if self.orchestrator.executor._client:
            status = await self.orchestrator.executor._client.get_mcp_status()
            connected = sum(1 for s in status.values() if s.get('connected'))
            total = len(status)
            self.query_one("#mcp-status").update(f"{connected}/{total}")
```

#### 3. Watch Mode Health Check

```python
# controllers/watch_controller.py

class WatchController:
    async def _check_mcp_health(self) -> bool:
        """Verify MCP servers before processing next file."""
        if not self.mcp_config:
            return True

        status = await self.client.get_mcp_status()
        unhealthy = [name for name, info in status.items()
                     if not info.get('connected')]

        if unhealthy:
            self._emit(WatchEvent.MCP_UNHEALTHY, servers=unhealthy)
            return False
        return True
```

---

## Feature 3: Tool Use Audit Trail

### Overview

Capture `tool_use_result` from UserMessage to create an audit trail of tool invocations.

### Data Model

```python
# New dataclass in types or agents module
@dataclass
class ToolInvocation:
    tool_name: str
    input_summary: str  # Truncated input
    output_summary: str  # Truncated output
    success: bool
    timestamp: datetime
    milestone_number: Optional[int]
```

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS tool_invocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    milestone_number INTEGER,
    tool_name TEXT NOT NULL,
    input_summary TEXT,
    output_summary TEXT,
    success INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX idx_tool_invocations_session ON tool_invocations(session_id);
```

### Agent Integration

```python
# agents.py

async def send_message_async(self, content: str, ...) -> str:
    # ...existing code...

    async for message in client.receive_messages():
        # NEW: Capture tool results (SDK 0.1.22+)
        if hasattr(message, 'tool_use_result') and message.tool_use_result:
            for result in message.tool_use_result:
                self._tool_invocations.append(ToolInvocation(
                    tool_name=result.get('tool_name', 'unknown'),
                    input_summary=_truncate(str(result.get('input', '')), 200),
                    output_summary=_truncate(str(result.get('output', '')), 500),
                    success=result.get('success', True),
                    timestamp=datetime.now(),
                    milestone_number=self._current_milestone,
                ))
```

### CLI Export

```bash
# Export tool invocations for a session
orchestrator export <session-id> --tools -o tools.json
```

```python
# cli.py
@click.option('--tools', is_flag=True, help='Include tool invocation audit trail')
def export(session_id, output, tools):
    # ...existing export...
    if tools:
        invocations = db.get_tool_invocations(session_id)
        data['tool_invocations'] = [asdict(t) for t in invocations]
```

---

## Implementation Plan

### Phase 1: SDK Upgrade (Low Risk)

| Task | File(s) | Effort |
|------|---------|--------|
| Update dependency to `>=0.1.23` | `pyproject.toml`, `environment.yml` | 5 min |
| Run existing tests | `tests/` | 10 min |
| Verify no breaking changes | Manual testing | 30 min |

### Phase 2: File Rewind (Medium Risk)

| Task | File(s) | Effort |
|------|---------|--------|
| Add UUID tracking to BaseAgent | `agents.py` | 1 hr |
| Add checkpoint/rewind methods | `agents.py` | 1 hr |
| Integrate with engine execution loop | `engine.py` | 2 hr |
| Add `--no-rewind` CLI flag | `cli.py` | 30 min |
| Update database schema | `db.py` | 30 min |
| Write unit tests | `tests/test_agents.py` | 2 hr |
| Write integration tests | `tests/test_engine.py` | 2 hr |
| Update documentation | `docs/` | 1 hr |

### Phase 3: MCP Status (Low Risk)

| Task | File(s) | Effort |
|------|---------|--------|
| Add MCP check to `orchestrator check` | `cli.py` | 1 hr |
| Add MCP status to TUI StatusPanel | `tui/widgets/status_panel.py` | 1 hr |
| Add health check to WatchController | `controllers/watch_controller.py` | 1 hr |
| Write tests | `tests/` | 1 hr |

### Phase 4: Tool Audit (Low Risk)

| Task | File(s) | Effort |
|------|---------|--------|
| Define ToolInvocation dataclass | `agents.py` or new `types.py` | 30 min |
| Create database table | `db.py` | 30 min |
| Capture tool results in agent | `agents.py` | 1 hr |
| Add `--tools` export option | `cli.py` | 1 hr |
| Write tests | `tests/` | 1 hr |

---

## Testing Strategy

### Unit Tests

```python
# tests/test_agents.py

class TestFileRewind:
    def test_checkpoint_set(self):
        """Checkpoint captures last message UUID."""

    def test_rewind_to_checkpoint(self):
        """Rewind calls SDK method with correct UUID."""

    def test_rewind_without_checkpoint(self):
        """Rewind returns False when no checkpoint exists."""

class TestMCPStatus:
    def test_get_mcp_status_connected(self):
        """Returns connected status for healthy servers."""

    def test_get_mcp_status_disconnected(self):
        """Returns error info for failed servers."""

class TestToolAudit:
    def test_capture_tool_result(self):
        """Tool invocations captured from UserMessage."""

    def test_tool_summary_truncation(self):
        """Long inputs/outputs are truncated."""
```

### Integration Tests

```python
# tests/test_integration.py

class TestRewindIntegration:
    def test_rewind_on_changes_requested(self):
        """Files rewound when milestone rejected."""

    def test_no_rewind_flag(self):
        """--no-rewind disables automatic rewind."""
```

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| SDK breaking changes | Low | High | Pin to 0.1.23, test thoroughly |
| Rewind overwrites user edits | Medium | Medium | Document behavior, add warning |
| MCP status adds latency | Low | Low | Cache status, async checks |
| Tool audit bloats database | Medium | Low | Truncate summaries, add cleanup |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Test coverage for new features | ≥90% |
| No regressions in existing tests | 100% pass |
| Rewind success rate | ≥95% when checkpoint exists |
| MCP status check latency | <500ms |

---

## Open Questions

1. **Rewind scope:** Should rewind also reset git staging area, or just file contents?
2. **Checkpoint retention:** How long to keep checkpoint UUIDs in database?
3. **Tool audit privacy:** Should we redact sensitive tool inputs (file contents, API keys)?

---

## References

- [Claude Agent SDK CHANGELOG](https://github.com/anthropics/claude-agent-sdk-python/blob/main/CHANGELOG.md)
- [SDK PyPI Page](https://pypi.org/project/claude-agent-sdk/)
- [orchestrator-auto Architecture](./ARCHITECTURE.md)
