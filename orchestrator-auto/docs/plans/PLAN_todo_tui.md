# Plan: TUI Support for `orchestrator todo`

## Problem Statement

The `orchestrator todo` command currently only supports CLI output. When running batch tasks, users cannot see streaming agent output—they only see results after each task completes. This creates a poor experience for long-running tasks where users want real-time visibility into what the agent is doing.

**Current limitations:**
1. `TodoRunner._run_fresh_agent()` buffers the entire response without streaming callbacks
2. No `on_task_chunk` callback exists for streaming output (note: `on_task_start` and `on_task_complete` already exist)
3. `--verbose` mode uses `print()` statements which conflict with TUI rendering
4. No way to visually track task progress in a rich interface

## Solution: `--tui` Flag for Todo Command

Add TUI support to `orchestrator todo` with:
- Real-time streaming of agent output
- Visual task list with status indicators
- Progress tracking across all tasks
- Log panel for system messages

```bash
orchestrator todo tasks.md --tui                    # TUI with streaming output
orchestrator todo tasks.md --tui --model haiku      # With cheaper model
orchestrator todo tasks.md --tui --verbose          # Full agent output in AgentOutput panel
orchestrator todo tasks.md --tui --dry-run          # Preview tasks without executing
```

## Design

### TUI Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│ orchestrator todo                                            15:32:45  │
├────────────────────────────┬────────────────────────────────────────────┤
│ TASKS                      │                                            │
│ ────────────────────────── │  > Executor:                               │
│ ○ Check if auth impl       │  Reading PLAN_auth.md to check             │
│ ▶ Analyze src/utils.py     │  implementation status...                  │
│ ○ Review test coverage     │                                            │
│ ✓ Verify dependencies      │  Found auth module at src/auth/:           │
│ ✗ Update docs              │  - login.py: JWT implementation ✓          │
│                            │  - register.py: User signup ✓              │
│ ────────────────────────── │  - password.py: Hashing with bcrypt ✓      │
│ Progress: 2/5              │                                            │
│ ✓ 1  ✗ 1  ○ 3              │  All required features implemented.        │
│                            │  Moving PLAN_auth.md to archive...         │
│                            │                                            │
│                            │  [TASK_DONE]                               │
│                            │  Result: Auth plan fully implemented       │
│                            │  [/TASK_DONE]                              │
├────────────────────────────┴────────────────────────────────────────────┤
│ LOG                                                                     │
│ [15:32:41] Starting task 2/5: Analyze src/utils.py                      │
│ [15:32:45] Task 2 completed in 4.2s                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           TodoTUIApp                                    │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                        Message Queue                              │  │
│  │  TodoTaskStarted | ChunkReceived | TodoTaskCompleted | Output    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│       ▲                                                                 │
│       │ call_from_thread()                                              │
│       │                                                                 │
│  ┌────┴─────────────────────────────────────────────────────────────┐  │
│  │                     TUITodoAdapter                                │  │
│  │  on_task_start() → TodoTaskStarted message                        │  │
│  │  on_task_chunk() → ChunkReceived message (reuse existing)         │  │
│  │  on_task_complete() → TodoTaskCompleted message                   │  │
│  │  on_log() → OutputReceived message (reuse existing)               │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│       ▲                                                                 │
│       │ callbacks                                                       │
│       │                                                                 │
│  ┌────┴─────────────────────────────────────────────────────────────┐  │
│  │                     TodoRunner (worker thread)                    │  │
│  │  _run_fresh_agent() emits chunks in receive_messages() loop      │  │
│  │  Streams chunks → adapter.on_task_chunk()                         │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Changes to TodoRunner

**Existing callbacks (already in `__init__` at lines 180-181):**
- `on_task_start: Optional[Callable[[int, int, Task], None]]`
- `on_task_complete: Optional[Callable[[TaskResult], None]]`

**New callback to add:**
- `on_task_chunk: Optional[Callable[[str], None]]`

Current code (lines 288-301 in `todo.py`):
```python
async with ClaudeSDKClient(options) as client:
    await client.query(prompt)
    response_text = ""

    async for message in client.receive_messages():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    response_text += block.text
        elif isinstance(message, ResultMessage):
            break

    return response_text
```

Required change—emit chunks in the existing loop:
```python
async def _run_fresh_agent(
    self,
    prompt: str,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> str:
    """Run agent with fresh context, streaming chunks if callback provided."""
    # ... existing setup code ...

    async with ClaudeSDKClient(options) as client:
        await client.query(prompt)
        response_text = ""

        async for message in client.receive_messages():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text
                        # NEW: emit chunk for streaming
                        if on_chunk:
                            on_chunk(block.text)
            elif isinstance(message, ResultMessage):
                break

        return response_text
```

### TUI Messages

Add to `tui/messages.py` using existing Message subclass pattern:

```python
class TodoTaskStarted(Message):
    """Emitted when a task starts."""

    def __init__(self, task_index: int, task_content: str, total_tasks: int) -> None:
        self.task_index = task_index
        self.task_content = task_content
        self.total_tasks = total_tasks
        super().__init__()


class TodoTaskCompleted(Message):
    """Emitted when a task completes."""

    def __init__(
        self,
        task_index: int,
        status: str,
        result: Optional[str],
        duration: float,
    ) -> None:
        self.task_index = task_index
        self.status = status  # "done" | "failed"
        self.result = result
        self.duration = duration
        super().__init__()


class TodoProgressUpdated(Message):
    """Emitted when overall progress changes."""

    def __init__(self, completed: int, failed: int, pending: int, total: int) -> None:
        self.completed = completed
        self.failed = failed
        self.pending = pending
        self.total = total
        super().__init__()
```

**Note:** Reuse existing `ChunkReceived` message for streaming chunks instead of creating a new `TodoTaskChunk`. This reduces surface area and maintains consistency.

### --verbose Behavior in TUI Mode

In CLI mode, `--verbose` prints the full agent response to stdout. In TUI mode:
- Full agent output is always visible in the AgentOutput panel (streaming)
- `--verbose` controls whether the LogPanel shows additional detail (e.g., prompt content, file context injected)
- No `print()` calls—all output routes through TUI messages

### TUI Widgets

**TaskListPanel** - Shows all tasks with status markers:
```
○ pending    (not started)
▶ processing (currently running)
✓ completed  (done)
✗ failed     (error)
```

**AgentOutput** - Reuse existing widget from watch mode for streaming output

**LogPanel** - Reuse existing widget for system messages

### CLI Integration

```python
@cli.command()
@click.argument('file', type=click.Path(exists=True))
@click.option('--tui', is_flag=True, help='Run with Terminal UI')
@click.option('--dry-run', is_flag=True, help='Preview tasks without executing')
@click.option('-m', '--model', default='sonnet', help='Model for execution')
@click.option('--timeout', default=300, type=int, help='Per-task timeout in seconds')
@click.option('--retry-failed', is_flag=True, help='Retry tasks marked [!]')
@click.option('--results', type=click.Path(), help='Write detailed results to file')
@click.option('-v', '--verbose', is_flag=True, help='Show additional detail in logs')
@click.option('--mcp-config', type=click.Path(exists=True), help='MCP config file')
def todo(file, tui, dry_run, model, timeout, retry_failed, results, verbose, mcp_config):
    """Execute tasks from a markdown checkbox file."""

    if tui:
        from .tui.todo_app import TodoTUIApp
        app = TodoTUIApp(
            task_file_path=Path(file),
            model=model,
            timeout=timeout,
            retry_failed=retry_failed,
            dry_run=dry_run,
            results_path=Path(results) if results else None,
            verbose=verbose,
            mcp_config_path=Path(mcp_config) if mcp_config else None,
        )
        app.run()
    else:
        # Existing CLI logic
        ...
```

### --dry-run Behavior in TUI Mode

When `--dry-run` is passed with `--tui`:
1. TUI launches and displays TaskListPanel with all tasks
2. All tasks shown as `○ pending` (no execution)
3. LogPanel shows "Dry run mode - no tasks will be executed"
4. AgentOutput panel shows task list preview
5. App exits after displaying (or waits for user to press `q`)

## Implementation

### New Files

```
orchestrator_auto/
├── tui/
│   ├── todo_app.py           # TodoTUIApp main application
│   ├── todo_adapter.py       # TUITodoAdapter for callbacks
│   ├── widgets/
│   │   └── task_list.py      # TaskListPanel widget
│   └── messages.py           # Add Todo-specific messages
└── todo.py                   # Add on_task_chunk callback
```

### Modifications

| File | Change |
|------|--------|
| `todo.py` | Add `on_task_chunk` callback to `__init__` and `_run_fresh_agent()` |
| `todo.py` | Thread `on_chunk` through `execute_task()` to `_run_fresh_agent()` |
| `cli.py` | Add `--tui` flag to `todo` command, wire all options |
| `tui/messages.py` | Add `TodoTaskStarted`, `TodoTaskCompleted`, `TodoProgressUpdated` |

## Milestones

### Milestone 1: Streaming Callback in TodoRunner
- Add `on_task_chunk: Optional[Callable[[str], None]]` to `TodoRunner.__init__`
- Modify `_run_fresh_agent()` to accept and invoke `on_chunk` callback
- Thread callback from `execute_task()` to `_run_fresh_agent()`
- Emit `on_chunk(block.text)` inside existing `receive_messages()` loop
- Ensure callbacks are optional (CLI mode continues to work unchanged)
- Unit tests for callback invocation

### Milestone 2: TUI Messages and Adapter
- Add `TodoTaskStarted`, `TodoTaskCompleted`, `TodoProgressUpdated` messages (Message subclass pattern)
- Create `TUITodoAdapter` class for thread-safe bridging
- Reuse `ChunkReceived` for streaming chunks
- Reuse `OutputReceived` for log entries
- Wire callbacks: TodoRunner → Adapter → TUI messages

### Milestone 3: TaskListPanel Widget
- Create `TaskListPanel` with task items and status markers (○ ▶ ✓ ✗)
- Handle `TodoTaskStarted` to mark task as ▶ processing
- Handle `TodoTaskCompleted` to update status (✓/✗)
- Show progress summary (completed/failed/pending counts)
- Support initial population from parsed TaskFile

### Milestone 4: TodoTUIApp Integration
- Create `TodoTUIApp` with layout (TaskList | AgentOutput, LogPanel)
- Reuse `AgentOutput` widget for streaming chunks
- Reuse `LogPanel` for system messages
- Add `--tui` flag to CLI with all options wired
- Implement `--dry-run` TUI behavior (preview without execution)
- Handle `--results` file writing in TUI mode
- Route `--verbose` to LogPanel detail level
- Integration tests

## Testing

```bash
# Create test file
cat > test_tasks.md << 'EOF'
# Test Tasks

- [ ] List files in current directory
- [ ] Read pyproject.toml and report version
- [ ] Check if pytest is installed
EOF

# CLI mode (unchanged)
orchestrator todo test_tasks.md --model haiku

# TUI mode
orchestrator todo test_tasks.md --model haiku --tui

# TUI with dry run (preview only)
orchestrator todo test_tasks.md --tui --dry-run

# TUI with results file
orchestrator todo test_tasks.md --tui --results results.md

# TUI with verbose logging
orchestrator todo test_tasks.md --tui --verbose
```

## Comparison: CLI vs TUI Mode

| Aspect | CLI Mode | TUI Mode |
|--------|----------|----------|
| Output | print() statements | Textual widgets |
| Streaming | Buffered (no chunks visible) | Real-time chunks in AgentOutput |
| Progress | Text updates | Visual task list with markers |
| Logs | Inline messages | Dedicated LogPanel |
| Verbose | Full response printed | Additional detail in LogPanel |
| Dry-run | Text preview | Visual task list, no execution |
| Results | Written to file | Written to file (same behavior) |
| Interruption | Ctrl+C exits | Ctrl+C graceful shutdown |

## Dependencies

- Existing TUI infrastructure from watch mode
- `textual>=0.80.0` (already in `[tui]` optional dependency)
- `AgentOutput` widget (reuse)
- `LogPanel` widget (reuse)
- `ChunkReceived` message (reuse)
- `OutputReceived` message (reuse)
- Thread-safe adapter pattern (established)
