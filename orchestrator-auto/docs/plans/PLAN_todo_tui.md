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

Following the established layout patterns from `WatchTUI`:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ orchestrator todo                                            [?] Help   │
├─────────────────────────┬───────────────────────────────────────────────┤
│ TASKS                   │ AGENT OUTPUT                                  │
│ ─────────────────────── │ ─────────────────────────────────────────────│
│ ○ Check if auth impl    │ > executor:                                   │
│ ▶ Analyze src/utils.py  │ Reading PLAN_auth.md to check                 │
│ ○ Review test coverage  │ implementation status...                      │
│ ✓ Verify dependencies   │                                               │
│ ✗ Update docs           │ Found auth module at src/auth/:               │
│                         │ - login.py: JWT implementation ✓              │
│ ─────────────────────── │ - register.py: User signup ✓                  │
│ Progress: 2/5           │ - password.py: Hashing with bcrypt ✓          │
│ ✓ 1  ✗ 1  ○ 3           │                                               │
│                         │ All required features implemented.            │
│                         │ Moving PLAN_auth.md to archive...             │
│                         │                                               │
│                         │ [TASK_DONE]                                   │
│                         │ Result: Auth plan fully implemented           │
│                         │ [/TASK_DONE]                                  │
├─────────────────────────┴───────────────────────────────────────────────┤
│ LOG                                                                     │
│ 15:32:41 Starting task 2/5: Analyze src/utils.py                        │
│ 15:32:45 Task 2 completed (4.2s) ✓                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

### Architecture

Following the established adapter pattern from `WatchTUI` and `OrchestratorTUI`:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           TodoTUI (App)                                 │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    Textual Message Queue                          │  │
│  │  TodoTaskStarted | ChunkReceived | TodoTaskCompleted | Output    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│       ▲                                                                 │
│       │ call_from_thread() / post_message()                             │
│       │                                                                 │
│  ┌────┴─────────────────────────────────────────────────────────────┐  │
│  │                   TUIOutputAdapter (reuse)                        │  │
│  │  + notify_todo_task_started()                                     │  │
│  │  + notify_todo_task_completed()                                   │  │
│  │  on_chunk() → ChunkReceived (existing)                            │  │
│  │  on_output() → OutputReceived (existing)                          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│       ▲                                                                 │
│       │ callbacks                                                       │
│       │                                                                 │
│  ┌────┴─────────────────────────────────────────────────────────────┐  │
│  │                   TodoRunner (worker thread via run_worker)       │  │
│  │  on_task_start → adapter.notify_todo_task_started()               │  │
│  │  on_task_chunk → adapter.on_chunk(chunk, "executor")              │  │
│  │  on_task_complete → adapter.notify_todo_task_completed()          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Stop Semantics

The `q` key triggers a **graceful stop** that finishes the current task before exiting. This is critical because todo tasks mutate files—stopping mid-task could leave partial edits or corrupted state.

**Behavior:**
- `q` pressed → set `_stop_requested` flag → current task completes → loop exits before next task
- Matches Watch/Queue's "stop after current unit" model
- LogPanel shows "Stopping after current task..." when stop requested

**Implementation in TodoRunner:**

```python
class TodoRunner:
    def __init__(self, ...):
        # ... existing params ...
        self._stop_requested = False

    def stop(self) -> None:
        """Request graceful stop after current task completes."""
        self._stop_requested = True

    def run_all(self, task_file, retry_failed=False, dry_run=False) -> List[TaskResult]:
        tasks = get_actionable_tasks(task_file, retry_failed)
        # ...
        results = []

        for i, task in enumerate(tasks, 1):
            # Check stop flag BEFORE starting next task
            if self._stop_requested:
                break

            # ... execute task ...
            results.append(result)

        return results
```

**TodoTUI integration:**

```python
class TodoTUI(App):
    def __init__(self, ...):
        # ...
        self._stop_requested = False  # Track if user requested stop

    def action_quit(self) -> None:
        """Graceful quit - finish current task first."""
        if self._runner and not self._stop_requested:
            self._stop_requested = True
            self._runner.stop()
            log_panel = self.query_one("#log-panel", LogPanel)
            log_panel.log_warning("Stopping after current task...")
            # Don't call self.exit() here - wait for on_todo_completed
        else:
            # No runner or already stopping - exit immediately
            self._cleanup_and_exit()

    def on_todo_completed(self, message: messages.TodoCompleted) -> None:
        """Handle todo completion - exit the app."""
        log_panel = self.query_one("#log-panel", LogPanel)
        if message.stopped:
            log_panel.log_warning(f"Stopped: {message.completed}/{message.total} tasks completed")
        else:
            log_panel.log_success(f"All tasks complete: {message.completed} done, {message.failed} failed")
        # Exit after brief delay to show final message
        self.set_timer(0.5, self._cleanup_and_exit)

    def _cleanup_and_exit(self) -> None:
        """Clean up resources and exit."""
        if self._timer:
            self._timer.stop()
        self.exit()
```

**Key difference from WatchTUI:** WatchTUI calls `self.exit()` immediately in `action_quit()` because its controller handles graceful shutdown internally. TodoTUI uses a worker thread, so we must wait for `TodoCompleted` message before exiting to ensure the current task finishes.

### Key Changes to TodoRunner

**Existing callbacks (in `__init__`):**
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

Add to `tui/messages.py` following the existing `Message` subclass pattern.

**4 new todo-specific messages:**

```python
class TodoStarted(Message):
    """Emitted when todo execution starts."""

    def __init__(
        self,
        task_file: str,
        total_tasks: int,
        tasks: list,  # List of dicts with 'index', 'content', 'status'
    ) -> None:
        self.task_file = task_file
        self.total_tasks = total_tasks
        self.tasks = tasks
        super().__init__()


class TodoTaskStarted(Message):
    """Emitted when a todo task starts."""

    def __init__(
        self,
        task_index: int,
        total_tasks: int,
        task_content: str,
    ) -> None:
        self.task_index = task_index
        self.total_tasks = total_tasks
        self.task_content = task_content
        super().__init__()


class TodoTaskCompleted(Message):
    """Emitted when a todo task completes."""

    def __init__(
        self,
        task_index: int,
        status: str,  # "done" | "failed"
        result: Optional[str],
        duration: float,
    ) -> None:
        self.task_index = task_index
        self.status = status
        self.result = result
        self.duration = duration
        super().__init__()


class TodoCompleted(Message):
    """Emitted when all todo tasks complete (or stopped early)."""

    def __init__(
        self,
        completed: int,
        failed: int,
        total: int,
        duration: float,
        stopped: bool = False,  # True if stopped via q key
    ) -> None:
        self.completed = completed
        self.failed = failed
        self.total = total
        self.duration = duration
        self.stopped = stopped
        super().__init__()
```

**Note:** Reuse existing `ChunkReceived` message for streaming chunks (with agent="executor") and `OutputReceived` for log entries.

**Progress tracking:** The UI computes progress locally from `TodoStarted.total_tasks` + `TodoTaskCompleted` events, following the pattern in `WatchTUI` which maintains `self._completed`, `self._failed` counters updated by event handlers. This avoids message coupling and progress drift issues.

### Adapter Extensions

Add methods to `TUIOutputAdapter` for todo-specific messages:

```python
# In tui/adapter.py

def notify_todo_started(
    self,
    task_file: str,
    total_tasks: int,
    tasks: list,
) -> None:
    """Notify TUI that todo execution started."""
    self.app.call_from_thread(
        self.app.post_message,
        messages.TodoStarted(
            task_file=task_file,
            total_tasks=total_tasks,
            tasks=tasks,
        )
    )

def notify_todo_task_started(
    self,
    task_index: int,
    total_tasks: int,
    task_content: str,
) -> None:
    """Notify TUI that a task started."""
    self.app.call_from_thread(
        self.app.post_message,
        messages.TodoTaskStarted(
            task_index=task_index,
            total_tasks=total_tasks,
            task_content=task_content,
        )
    )

def notify_todo_task_completed(
    self,
    task_index: int,
    status: str,
    result: Optional[str],
    duration: float,
) -> None:
    """Notify TUI that a task completed."""
    self.app.call_from_thread(
        self.app.post_message,
        messages.TodoTaskCompleted(
            task_index=task_index,
            status=status,
            result=result,
            duration=duration,
        )
    )

def notify_todo_completed(
    self,
    completed: int,
    failed: int,
    total: int,
    duration: float,
    stopped: bool = False,
) -> None:
    """Notify TUI that all tasks completed."""
    self.app.call_from_thread(
        self.app.post_message,
        messages.TodoCompleted(
            completed=completed,
            failed=failed,
            total=total,
            duration=duration,
            stopped=stopped,
        )
    )
```

### --verbose Behavior in TUI Mode

In CLI mode, `--verbose` prints the full agent response to stdout. In TUI mode:
- Full agent output is always visible in the AgentOutput panel (streaming)
- `--verbose` controls whether the LogPanel shows additional detail (e.g., prompt content, file context injected)
- No `print()` calls—all output routes through TUI messages

### TUI Widgets

**TaskListPanel** (new) - Shows all tasks with status markers:
```
○ pending    (not started)
▶ processing (currently running)
✓ completed  (done)
✗ failed     (error)
```

Similar structure to `WatchPanel` widget. Maintains local counters for progress display:
```python
class TaskListPanel(Vertical):
    def __init__(self, ...):
        self._completed = 0
        self._failed = 0
        self._total = 0

    def on_todo_task_completed(self, message: TodoTaskCompleted) -> None:
        if message.status == "done":
            self._completed += 1
        else:
            self._failed += 1
        self._update_progress_display()
```

**AgentOutput** - Reuse existing widget for streaming output (no agent_filter needed since todo only uses executor)

**LogPanel** - Reuse existing widget for timestamped system messages

### Key Bindings

Add to `tui/bindings.py`:

```python
# Todo mode bindings
TODO_BINDINGS = [
    Binding("l", "toggle_logs", "Logs"),
    Binding("t", "toggle_tasks", "Tasks"),
    Binding("s", "show_status", "Status"),
]
```

### CLI Integration

**Important:** The `--tui` check must come FIRST, before any `click.echo()` calls. The existing CLI prints a large banner (file info, model, task counts) before processing. If TUI mode launches after this banner, it clutters the terminal right before Textual takes over.

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

    # TUI mode: launch immediately, skip CLI banner
    if tui:
        from .tui.todo_app import TodoTUI
        app = TodoTUI(
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
        return  # Exit after TUI closes

    # CLI mode: existing logic with banner, summary, etc.
    from .todo_parser import parse_task_file, TaskStatus
    # ... rest of existing CLI implementation ...
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
│   ├── todo_app.py           # TodoTUI main application
│   ├── widgets/
│   │   └── task_list.py      # TaskListPanel widget
│   ├── messages.py           # Add Todo-specific messages
│   └── bindings.py           # Add TODO_BINDINGS
└── todo.py                   # Add on_task_chunk callback + stop() method
```

### Modifications

| File | Change |
|------|--------|
| `todo.py` | Add `on_task_chunk` callback to `__init__` and `_run_fresh_agent()` |
| `todo.py` | Add `stop()` method and `_stop_requested` flag checked in `run_all()` |
| `todo.py` | Thread `on_chunk` through `execute_task()` to `_run_fresh_agent()` |
| `cli.py` | Add `--tui` flag to `todo` command |
| `tui/adapter.py` | Add `notify_todo_*` methods |
| `tui/messages.py` | Add `TodoStarted`, `TodoTaskStarted`, `TodoTaskCompleted`, `TodoCompleted` |
| `tui/bindings.py` | Add `TODO_BINDINGS` |
| `tui/widgets/__init__.py` | Export `TaskListPanel` |

## Milestones

## Milestone 1: Streaming Callback and Stop Flag in TodoRunner

### Goal
Add streaming callback support and graceful stop mechanism to `TodoRunner` so the TUI can display real-time agent output and safely stop execution between tasks.

### Tasks
- [ ] Add `on_task_chunk: Optional[Callable[[str], None]]` parameter to `TodoRunner.__init__`
- [ ] Modify `_run_fresh_agent()` to accept `on_chunk` callback parameter
- [ ] Emit `on_chunk(block.text)` inside existing `receive_messages()` loop when callback provided
- [ ] Thread `on_chunk` callback from `execute_task()` through to `_run_fresh_agent()`
- [ ] Add `_stop_requested: bool = False` instance variable to `TodoRunner.__init__`
- [ ] Add `stop()` method that sets `self._stop_requested = True`
- [ ] Check `_stop_requested` at start of each iteration in `run_all()` loop, break if True
- [ ] Ensure all callbacks are optional (CLI mode continues to work unchanged)
- [ ] Write unit test for `on_task_chunk` callback invocation
- [ ] Write unit test for `stop()` flag behavior (stops before next task, not mid-task)

### Deliverables
- [ ] `orchestrator_auto/todo.py` - modified with streaming callback and graceful stop
- [ ] `tests/test_todo.py` - new tests for `on_task_chunk` and `stop()` behavior

### Validation
```bash
cd orchestrator-auto
pytest tests/test_todo.py -v -k "chunk or stop"
```

### Risks / Notes
- Callback is invoked from async context; TUI adapter must handle thread-safely via `call_from_thread()`
- Stop flag only checked between tasks, not mid-task (by design—tasks mutate files)

## Milestone 2: TUI Messages and Adapter Extensions

### Goal
Add todo-specific Textual messages and extend `TUIOutputAdapter` with notification methods to bridge `TodoRunner` callbacks to the TUI message queue.

### Tasks
- [ ] Add `TodoStarted` message class to `tui/messages.py` (task_file, total_tasks, tasks list)
- [ ] Add `TodoTaskStarted` message class to `tui/messages.py` (task_index, total_tasks, task_content)
- [ ] Add `TodoTaskCompleted` message class to `tui/messages.py` (task_index, status, result, duration)
- [ ] Add `TodoCompleted` message class to `tui/messages.py` (completed, failed, total, duration, stopped)
- [ ] Add `notify_todo_started()` method to `TUIOutputAdapter` in `tui/adapter.py`
- [ ] Add `notify_todo_task_started()` method to `TUIOutputAdapter`
- [ ] Add `notify_todo_task_completed()` method to `TUIOutputAdapter`
- [ ] Add `notify_todo_completed()` method to `TUIOutputAdapter`
- [ ] Add `TODO_BINDINGS` list to `tui/bindings.py` with `l` (logs), `t` (tasks), `s` (status)
- [ ] Add `get_bindings_for_mode("todo")` support in `tui/bindings.py`

### Deliverables
- [ ] `orchestrator_auto/tui/messages.py` - 4 new message classes added
- [ ] `orchestrator_auto/tui/adapter.py` - 4 new `notify_todo_*` methods added
- [ ] `orchestrator_auto/tui/bindings.py` - `TODO_BINDINGS` added

### Validation
```bash
cd orchestrator-auto
python -c "from orchestrator_auto.tui.messages import TodoStarted, TodoTaskStarted, TodoTaskCompleted, TodoCompleted; print('Messages OK')"
python -c "from orchestrator_auto.tui.adapter import TUIOutputAdapter; print('Adapter OK')"
python -c "from orchestrator_auto.tui.bindings import TODO_BINDINGS; print('Bindings OK')"
```

### Risks / Notes
- Reuse existing `ChunkReceived` message for streaming chunks (agent="executor")
- Reuse existing `OutputReceived` message for log entries
- All `notify_*` methods must use `call_from_thread()` for thread safety

## Milestone 3: TaskListPanel Widget

### Goal
Create a `TaskListPanel` widget that displays all tasks with status markers and progress summary, updating in real-time as tasks complete.

### Tasks
- [ ] Create `tui/widgets/task_list.py` with `TaskListPanel` class extending `Vertical`
- [ ] Implement status markers: `○` pending, `▶` processing, `✓` done, `✗` failed
- [ ] Add `_completed`, `_failed`, `_total` instance counters
- [ ] Implement `set_tasks(tasks: list)` method to populate initial task list
- [ ] Implement `on_todo_task_started()` handler to mark task as `▶` processing
- [ ] Implement `on_todo_task_completed()` handler to update status (✓/✗) and increment counters
- [ ] Implement `_update_progress_display()` to show summary (e.g., "✓ 2  ✗ 1  ○ 3")
- [ ] Add DEFAULT_CSS for styling (borders, colors for status markers)
- [ ] Export `TaskListPanel` from `tui/widgets/__init__.py`

### Deliverables
- [ ] `orchestrator_auto/tui/widgets/task_list.py` - new widget file
- [ ] `orchestrator_auto/tui/widgets/__init__.py` - updated to export `TaskListPanel`

### Validation
```bash
cd orchestrator-auto
python -c "from orchestrator_auto.tui.widgets import TaskListPanel; print('TaskListPanel OK')"
pytest tests/test_tui.py -v -k "task_list or TaskList"
```

### Risks / Notes
- Follow `WatchPanel` structure for consistency
- Progress computed locally from events (no separate `TodoProgressUpdated` message)
- Task content may be long; truncate display with ellipsis if needed

## Milestone 4: TodoTUI App Integration

### Goal
Create the `TodoTUI` Textual app that integrates all components, wire up to CLI with `--tui` flag, and ensure graceful exit behavior.

### Tasks
- [ ] Create `tui/todo_app.py` with `TodoTUI` class extending `App`
- [ ] Implement layout: TaskListPanel (left) | AgentOutput (right), LogPanel (bottom)
- [ ] Add `_runner: Optional[TodoRunner]` and `_stop_requested: bool` instance variables
- [ ] Implement `on_mount()` to start worker via `run_worker()`
- [ ] Implement `_run_todo_worker()` that creates `TodoRunner` and calls `run_all()`
- [ ] Wire `TodoRunner` callbacks to adapter notification methods
- [ ] Implement `action_quit()`: set `_stop_requested`, call `runner.stop()`, log warning, do NOT exit
- [ ] Implement `on_todo_completed()`: log final status, call `self.exit()` after 0.5s delay
- [ ] Implement `_cleanup_and_exit()` helper to stop timer and call `self.exit()`
- [ ] Handle `--dry-run` mode: show tasks, log "Dry run mode", wait for `q` to exit
- [ ] Handle `--results` file writing after completion
- [ ] Handle `--verbose` flag to control LogPanel detail level
- [ ] Update `cli.py`: add `--tui` flag to `todo` command
- [ ] Update `cli.py`: check `--tui` FIRST before any `click.echo()` calls, return after `app.run()`
- [ ] Add `TodoTUI` import test to `tests/test_tui.py`
- [ ] Add new messages import test to `tests/test_tui.py`

### Deliverables
- [ ] `orchestrator_auto/tui/todo_app.py` - new TUI app file
- [ ] `orchestrator_auto/cli.py` - `--tui` flag added to `todo` command (early return before banner)
- [ ] `tests/test_tui.py` - import tests for `TodoTUI` and new messages

### Validation
```bash
cd orchestrator-auto
# Import test
python -c "from orchestrator_auto.tui.todo_app import TodoTUI; print('TodoTUI OK')"

# CLI help shows --tui flag
orchestrator todo --help | grep -q "\-\-tui" && echo "CLI flag OK"

# Dry run with TUI (manual verification)
echo "- [ ] Test task" > /tmp/test_tasks.md
orchestrator todo /tmp/test_tasks.md --tui --dry-run

# Full integration test
pytest tests/test_tui.py -v
```

### Risks / Notes
- `action_quit()` must NOT call `self.exit()` directly—wait for `on_todo_completed()` to ensure current task finishes
- CLI must check `--tui` before any `click.echo()` to avoid banner clutter before TUI launches
- Timer (if any) must be stopped in `_cleanup_and_exit()` to prevent orphaned callbacks

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

### Test File Locations

| Test | File |
|------|------|
| `TodoTUI` import | `tests/test_tui.py` |
| New messages import | `tests/test_tui.py` |
| `on_task_chunk` callback | `tests/test_todo.py` |
| `TodoRunner.stop()` behavior | `tests/test_todo.py` |
| `TaskListPanel` widget | `tests/test_tui.py` |

## Comparison: CLI vs TUI Mode

| Aspect | CLI Mode | TUI Mode |
|--------|----------|----------|
| Output | print() statements | Textual widgets |
| Streaming | Buffered (no chunks visible) | Real-time chunks in AgentOutput |
| Progress | Text updates | Visual task list with markers |
| Logs | Inline messages | Dedicated LogPanel with timestamps |
| Verbose | Full response printed | Additional detail in LogPanel |
| Dry-run | Text preview | Visual task list, no execution |
| Results | Written to file | Written to file (same behavior) |
| Interruption | Ctrl+C exits | `q` key graceful stop (finishes current task) |

## Dependencies

- Existing TUI infrastructure (adapter pattern, widgets, messages)
- `textual>=0.80.0` (already in `[tui]` optional dependency)
- `AgentOutput` widget (reuse)
- `LogPanel` widget (reuse)
- `TUIOutputAdapter` (extend)
- `ChunkReceived` message (reuse)
- `OutputReceived` message (reuse)
- Thread-safe adapter pattern (established)

## Reference Files

Key files to study for implementation patterns:

| File | Pattern |
|------|---------|
| `tui/watch_app.py` | App structure, worker pattern, message handlers, graceful stop |
| `tui/adapter.py` | `TUIOutputAdapter`, `call_from_thread()` |
| `tui/messages.py` | Message class definitions |
| `tui/widgets/watch_panel.py` | Panel with file/item list + local counter pattern |
| `tui/widgets/agent_output.py` | Streaming output widget |
| `tui/widgets/log_panel.py` | Timestamped log widget |
| `tui/bindings.py` | Key binding definitions |
| `todo.py` | `TodoRunner` class to extend |
| `tests/test_tui.py` | TUI import/instantiation test patterns |
| `tests/test_todo.py` | Todo unit test patterns |
