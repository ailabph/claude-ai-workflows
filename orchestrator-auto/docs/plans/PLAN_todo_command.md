# Plan: `orchestrator todo` Command

## Problem Statement

User has many independent tasks that need agent processing, but current orchestrator-auto breaks because it accumulates context across tasks within a single session. Examples:
- Audit plan files to check if implemented
- Process multiple bug reports independently
- Run analysis on multiple files

**Key insight:** Each task is independent and doesn't need context from previous tasks.

## Solution: `orchestrator todo` Command

A batch task runner that processes tasks **independently** with **fresh agent context per task**.

```bash
orchestrator todo tasks.md                           # Process all unchecked tasks
orchestrator todo tasks.md --dry-run                 # Preview without executing
orchestrator todo tasks.md --model haiku             # Use cheaper model
orchestrator todo tasks.md --retry-failed            # Retry tasks marked [!]
orchestrator todo tasks.md --results results.md      # Write results to separate file
```

## Input Format: Markdown Checkboxes

```markdown
# My Tasks

- [ ] Check if PLAN_auth.md is implemented, archive if yes
- [ ] Analyze src/utils.py for performance issues
- [ ] Review tests/test_api.py for missing edge cases
- [x] Already done task (skipped)
- [!] Previously failed task (retry with --retry-failed)
```

### Multi-line Tasks

Tasks can span multiple lines using indentation:

```markdown
- [ ] Audit PLAN_notifications.md
      Check if email notification system is implemented.
      Look for: EmailService, queue workers, templates.
      If implemented, move to ./archive/
```

### Context File References

Use `@path` syntax to inject file contents into task prompt:

```markdown
- [ ] Review @src/auth.py for security issues
- [ ] Implement the feature described in @docs/spec.md
```

## Output Format

### Console Output

```
Processing 5 tasks from tasks.md...

[1/5] Check if PLAN_auth.md is implemented, archive if yes
      ✓ Done (12.3s)
      → Implemented. Moved to ./archive/

[2/5] Analyze src/utils.py for performance issues
      ✓ Done (8.7s)
      → Found 2 issues: N+1 query on line 45, unnecessary copy on line 78

[3/5] Review tests/test_api.py for missing edge cases
      ✗ Failed (timeout after 300s)
      → Agent did not complete within timeout

[4/5] Already done task
      ⊘ Skipped (already checked)

[5/5] Previously failed task
      ⊘ Skipped (use --retry-failed to retry)

Summary:
  ✓ Completed: 2
  ✗ Failed:    1 (marked [!] in file)
  ⊘ Skipped:   2
```

### File Updates

After processing, the original file is updated:

```markdown
# My Tasks

- [x] Check if PLAN_auth.md is implemented, archive if yes
- [x] Analyze src/utils.py for performance issues
- [!] Review tests/test_api.py for missing edge cases
- [x] Already done task (skipped)
- [!] Previously failed task (retry with --retry-failed)
```

## Design

### Command Signature

```bash
orchestrator todo <file> [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `file` | required | Markdown file with checkbox tasks |
| `--dry-run` | false | Preview tasks without executing |
| `--model` | sonnet | Model for task execution |
| `--timeout` | 300 | Per-task timeout in seconds |
| `--retry-failed` | false | Retry tasks marked `[!]` |
| `--results` | none | Write detailed results to separate file |
| `--verbose` | false | Show agent's full response |
| `--mcp-config` | auto | MCP server configuration file |

### Per-Task Workflow

```
For each unchecked task [ ]:
    1. Create FRESH agent session (new UUID, no shared context)
    2. Build prompt with task content + any @file references
    3. Agent executes task with full capabilities (read, write, bash)
    4. Wait for explicit completion tag:
       - [TASK_DONE] → Mark as [x], record result
       - [TASK_FAILED] → Mark as [!], record error
       - Timeout/error → Mark as [!], record reason
    5. Update file atomically (backup → write → verify)
    6. Agent session closed completely
    7. Next task starts with zero context
```

### Agent Prompt Template

```
You are executing a single task. When finished, you MUST end your response with
exactly one of these tags:

[TASK_DONE]
Result: <one-line summary of what you accomplished>
[/TASK_DONE]

OR

[TASK_FAILED]
Reason: <why you could not complete the task>
[/TASK_FAILED]

TASK:
{task_content}

{file_context if @path references exist}

Execute this task now. Use any tools needed (read files, write files, run commands).
When complete, output the appropriate completion tag.
```

### Completion Tag Detection

The agent MUST output explicit completion tags. This distinguishes:
- "Task done" vs "Agent stopped talking mid-task"
- "Task failed for real reason" vs "Agent hit token limit"

```python
def parse_task_result(response: str) -> TaskResult:
    if "[TASK_DONE]" in response:
        # Extract result between tags
        return TaskResult(status="done", result=extract_result(response))
    elif "[TASK_FAILED]" in response:
        # Extract reason between tags
        return TaskResult(status="failed", reason=extract_reason(response))
    else:
        # No tag = incomplete (timeout, crash, token limit)
        return TaskResult(status="failed", reason="No completion tag - task may be incomplete")
```

### File Atomicity

To prevent data loss on crash:

```python
def update_task_file(path: Path, tasks: List[Task]):
    backup_path = path.with_suffix('.md.bak')
    temp_path = path.with_suffix('.md.tmp')

    # 1. Create backup of original
    shutil.copy(path, backup_path)

    # 2. Write to temp file
    temp_path.write_text(render_tasks(tasks))

    # 3. Atomic rename
    temp_path.rename(path)

    # 4. Remove backup on success
    backup_path.unlink()
```

### Key Differences from Main Workflow

| Aspect | `orchestrator start` | `orchestrator todo` |
|--------|---------------------|---------------------|
| Context | Accumulates across milestones | Fresh per task |
| Agents | Planner + Executor | Single agent |
| Goal | Implement features | Execute tasks |
| Output | Code changes | Task status + results |
| Session | Persisted in DB | Ephemeral (no DB) |
| Human loop | Approval between milestones | None (autonomous) |

## Implementation

### New Files

```
orchestrator_auto/
├── todo_parser.py    # Checkbox parsing & file I/O
├── todo.py           # Core runner logic
└── cli.py            # Add todo command
```

### `todo_parser.py`

```python
"""Parse and update markdown checkbox task files."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional
import re
import shutil


class TaskStatus(Enum):
    PENDING = "pending"      # [ ]
    DONE = "done"            # [x]
    FAILED = "failed"        # [!]


@dataclass
class Task:
    """A single task from a markdown checkbox."""
    line_number: int
    content: str                          # Task text (may be multi-line)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None          # Result summary after execution
    file_refs: List[Path] = field(default_factory=list)  # @path references

    @property
    def is_actionable(self) -> bool:
        """Task should be processed (pending or failed with retry)."""
        return self.status == TaskStatus.PENDING


@dataclass
class TaskFile:
    """Parsed markdown file with tasks."""
    path: Path
    tasks: List[Task]
    raw_lines: List[str]                  # Original lines for reconstruction

    @property
    def pending_count(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.PENDING)

    @property
    def failed_count(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.FAILED)


# Regex patterns
CHECKBOX_PATTERN = re.compile(r'^(\s*)-\s*\[([ x!])\]\s*(.+)$', re.IGNORECASE)
CONTINUATION_PATTERN = re.compile(r'^(\s{2,}|\t+)\S')  # Indented continuation
FILE_REF_PATTERN = re.compile(r'@([\w./\-_]+)')


def parse_task_file(path: Path) -> TaskFile:
    """Parse a markdown file into tasks."""
    if not path.exists():
        raise FileNotFoundError(f"Task file not found: {path}")

    lines = path.read_text().splitlines()
    tasks = []

    i = 0
    while i < len(lines):
        line = lines[i]
        match = CHECKBOX_PATTERN.match(line)

        if match:
            indent, marker, content = match.groups()

            # Determine status from marker
            if marker == ' ':
                status = TaskStatus.PENDING
            elif marker.lower() == 'x':
                status = TaskStatus.DONE
            elif marker == '!':
                status = TaskStatus.FAILED
            else:
                status = TaskStatus.PENDING

            # Collect continuation lines
            task_lines = [content]
            j = i + 1
            while j < len(lines) and CONTINUATION_PATTERN.match(lines[j]):
                task_lines.append(lines[j].strip())
                j += 1

            full_content = '\n'.join(task_lines)

            # Extract @file references
            file_refs = [Path(m) for m in FILE_REF_PATTERN.findall(full_content)]

            tasks.append(Task(
                line_number=i,
                content=full_content,
                status=status,
                file_refs=file_refs,
            ))

            i = j  # Skip continuation lines
        else:
            i += 1

    return TaskFile(path=path, tasks=tasks, raw_lines=lines)


def update_task_file(task_file: TaskFile) -> None:
    """Write updated task statuses back to file atomically."""
    path = task_file.path
    backup_path = path.with_suffix('.md.bak')
    temp_path = path.with_suffix('.md.tmp')

    # Build updated content
    new_lines = task_file.raw_lines.copy()

    for task in task_file.tasks:
        line = new_lines[task.line_number]
        match = CHECKBOX_PATTERN.match(line)
        if match:
            indent = match.group(1)
            # Map status to marker
            marker = {
                TaskStatus.PENDING: ' ',
                TaskStatus.DONE: 'x',
                TaskStatus.FAILED: '!',
            }[task.status]

            # Reconstruct line with new marker
            new_lines[task.line_number] = f"{indent}- [{marker}] {task.content.split(chr(10))[0]}"

    # Atomic write
    shutil.copy(path, backup_path)
    try:
        temp_path.write_text('\n'.join(new_lines) + '\n')
        temp_path.rename(path)
        backup_path.unlink()
    except Exception:
        # Restore from backup on failure
        if backup_path.exists():
            shutil.copy(backup_path, path)
        raise


def get_actionable_tasks(task_file: TaskFile, retry_failed: bool = False) -> List[Task]:
    """Get tasks that should be processed."""
    tasks = []
    for task in task_file.tasks:
        if task.status == TaskStatus.PENDING:
            tasks.append(task)
        elif task.status == TaskStatus.FAILED and retry_failed:
            tasks.append(task)
    return tasks
```

### `todo.py`

```python
"""Execute tasks with fresh agent context per task."""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import re

from anthropic_sdk_beta import AsyncAnthropic
from claude_code_sdk import ClaudeCodeSDK, query

from .todo_parser import (
    Task, TaskFile, TaskStatus,
    parse_task_file, update_task_file, get_actionable_tasks
)
from .config import get_model_id, load_mcp_config_raw
from .agents import build_allowed_tools


@dataclass
class TaskResult:
    """Result of executing a single task."""
    task: Task
    status: TaskStatus
    result: Optional[str] = None
    duration: float = 0.0
    error: Optional[str] = None


TASK_PROMPT_TEMPLATE = '''You are executing a single task. When finished, you MUST end your response with exactly one of these completion tags:

[TASK_DONE]
Result: <one-line summary of what you accomplished>
[/TASK_DONE]

OR if you cannot complete the task:

[TASK_FAILED]
Reason: <why you could not complete the task>
[/TASK_FAILED]

IMPORTANT: You MUST output one of these tags when done. Do not stop without a completion tag.

---

TASK:
{task_content}

{file_context}

---

Execute this task now. Use any tools you need (read files, write files, run bash commands).
When complete, output the appropriate completion tag.
'''


def parse_completion_tags(response: str) -> tuple[TaskStatus, Optional[str]]:
    """Parse [TASK_DONE] or [TASK_FAILED] from response."""

    # Check for TASK_DONE
    done_match = re.search(
        r'\[TASK_DONE\]\s*Result:\s*(.+?)\s*\[/TASK_DONE\]',
        response,
        re.DOTALL | re.IGNORECASE
    )
    if done_match:
        return TaskStatus.DONE, done_match.group(1).strip()

    # Check for TASK_FAILED
    failed_match = re.search(
        r'\[TASK_FAILED\]\s*Reason:\s*(.+?)\s*\[/TASK_FAILED\]',
        response,
        re.DOTALL | re.IGNORECASE
    )
    if failed_match:
        return TaskStatus.FAILED, failed_match.group(1).strip()

    # No completion tag found
    return TaskStatus.FAILED, "No completion tag - task may be incomplete"


def build_file_context(task: Task, base_path: Path) -> str:
    """Build context string from @file references."""
    if not task.file_refs:
        return ""

    context_parts = ["FILE CONTEXT:"]
    for ref in task.file_refs:
        file_path = base_path / ref if not ref.is_absolute() else ref
        if file_path.exists():
            try:
                content = file_path.read_text()
                context_parts.append(f"\n--- {ref} ---\n{content}\n")
            except Exception as e:
                context_parts.append(f"\n--- {ref} ---\n[Error reading file: {e}]\n")
        else:
            context_parts.append(f"\n--- {ref} ---\n[File not found]\n")

    return '\n'.join(context_parts)


class TodoRunner:
    """Execute tasks with fresh agent context per task."""

    def __init__(
        self,
        model: str = "sonnet",
        timeout: int = 300,
        verbose: bool = False,
        mcp_config_path: Optional[Path] = None,
    ):
        self.model = model
        self.model_id = get_model_id(model)
        self.timeout = timeout
        self.verbose = verbose
        self.mcp_config = None

        if mcp_config_path:
            self.mcp_config = load_mcp_config_raw(mcp_config_path)

    async def execute_task(self, task: Task, base_path: Path) -> TaskResult:
        """Execute a single task with fresh agent context."""
        start_time = time.time()

        # Build prompt
        file_context = build_file_context(task, base_path)
        prompt = TASK_PROMPT_TEMPLATE.format(
            task_content=task.content,
            file_context=file_context,
        )

        try:
            # Create fresh agent session
            allowed_tools = build_allowed_tools(self.mcp_config, agent_type="executor")

            # Run with timeout
            response = await asyncio.wait_for(
                self._run_agent(prompt, allowed_tools),
                timeout=self.timeout
            )

            # Parse completion tags
            status, result = parse_completion_tags(response)

            return TaskResult(
                task=task,
                status=status,
                result=result,
                duration=time.time() - start_time,
            )

        except asyncio.TimeoutError:
            return TaskResult(
                task=task,
                status=TaskStatus.FAILED,
                error=f"Timeout after {self.timeout}s",
                duration=time.time() - start_time,
            )
        except Exception as e:
            return TaskResult(
                task=task,
                status=TaskStatus.FAILED,
                error=str(e),
                duration=time.time() - start_time,
            )

    async def _run_agent(self, prompt: str, allowed_tools: Optional[List[str]]) -> str:
        """Run agent query with fresh context."""
        # Use claude-code-sdk for full tool access
        result = await query(
            prompt=prompt,
            model=self.model_id,
            permission_mode="bypassPermissions",
            allowed_tools=allowed_tools,
        )
        return result.text if hasattr(result, 'text') else str(result)

    def run_all(
        self,
        task_file: TaskFile,
        retry_failed: bool = False,
        dry_run: bool = False,
    ) -> List[TaskResult]:
        """Run all actionable tasks."""
        tasks = get_actionable_tasks(task_file, retry_failed)

        if not tasks:
            return []

        if dry_run:
            # Return preview without executing
            return [
                TaskResult(task=t, status=TaskStatus.PENDING, result="[dry-run]")
                for t in tasks
            ]

        results = []
        base_path = task_file.path.parent

        for i, task in enumerate(tasks, 1):
            print(f"\n[{i}/{len(tasks)}] {task.content.split(chr(10))[0][:60]}...")

            # Execute with fresh context
            result = asyncio.run(self.execute_task(task, base_path))
            results.append(result)

            # Update task status
            task.status = result.status
            task.result = result.result or result.error

            # Write progress to file
            update_task_file(task_file)

            # Print result
            if result.status == TaskStatus.DONE:
                print(f"      ✓ Done ({result.duration:.1f}s)")
                if result.result:
                    print(f"      → {result.result}")
            else:
                print(f"      ✗ Failed ({result.duration:.1f}s)")
                if result.error:
                    print(f"      → {result.error}")

        return results
```

### CLI Addition to `cli.py`

```python
@cli.command()
@click.argument('file', type=click.Path(exists=True))
@click.option('--dry-run', is_flag=True, help='Preview tasks without executing')
@click.option('-m', '--model', default='sonnet', help='Model for execution')
@click.option('--timeout', default=300, type=int, help='Per-task timeout in seconds')
@click.option('--retry-failed', is_flag=True, help='Retry tasks marked [!]')
@click.option('--results', type=click.Path(), help='Write detailed results to file')
@click.option('-v', '--verbose', is_flag=True, help='Show full agent responses')
@click.option('--mcp-config', type=click.Path(exists=True), help='MCP config file')
def todo(file, dry_run, model, timeout, retry_failed, results, verbose, mcp_config):
    """Execute tasks from a markdown checkbox file.

    Each task runs with fresh agent context (no accumulated state).

    Example file format:

        - [ ] Check if feature is implemented
        - [ ] Analyze src/utils.py for issues
        - [x] Already done (skipped)
        - [!] Previously failed (use --retry-failed)

    Usage:

        orchestrator todo tasks.md
        orchestrator todo tasks.md --dry-run
        orchestrator todo tasks.md --model haiku --retry-failed
    """
    from pathlib import Path
    from .todo_parser import parse_task_file, TaskStatus
    from .todo import TodoRunner

    task_file = parse_task_file(Path(file))

    # Show summary
    total = len(task_file.tasks)
    pending = task_file.pending_count
    failed = task_file.failed_count
    done = total - pending - failed

    click.echo(f"Task file: {file}")
    click.echo(f"  Total: {total}, Pending: {pending}, Failed: {failed}, Done: {done}")

    if pending == 0 and (not retry_failed or failed == 0):
        click.echo("\nNo tasks to process.")
        return

    actionable = pending + (failed if retry_failed else 0)
    click.echo(f"\nProcessing {actionable} task(s)..." + (" [DRY RUN]" if dry_run else ""))

    # Run tasks
    runner = TodoRunner(
        model=model,
        timeout=timeout,
        verbose=verbose,
        mcp_config_path=Path(mcp_config) if mcp_config else None,
    )

    task_results = runner.run_all(task_file, retry_failed=retry_failed, dry_run=dry_run)

    # Summary
    completed = sum(1 for r in task_results if r.status == TaskStatus.DONE)
    failed_count = sum(1 for r in task_results if r.status == TaskStatus.FAILED)

    click.echo(f"\nSummary:")
    click.echo(f"  ✓ Completed: {completed}")
    click.echo(f"  ✗ Failed:    {failed_count}" + (" (marked [!] in file)" if failed_count else ""))

    # Write results file if requested
    if results and task_results:
        results_path = Path(results)
        with results_path.open('w') as f:
            f.write(f"# Task Results\n\n")
            f.write(f"Source: {file}\n")
            f.write(f"Model: {model}\n\n")
            for r in task_results:
                status_emoji = "✓" if r.status == TaskStatus.DONE else "✗"
                f.write(f"## {status_emoji} {r.task.content.split(chr(10))[0]}\n\n")
                f.write(f"- Status: {r.status.value}\n")
                f.write(f"- Duration: {r.duration:.1f}s\n")
                if r.result:
                    f.write(f"- Result: {r.result}\n")
                if r.error:
                    f.write(f"- Error: {r.error}\n")
                f.write("\n")
        click.echo(f"\nResults written to: {results}")
```

## Milestones

### Milestone 1: Parser + Core Types
- Create `todo_parser.py` with checkbox parsing
- Support multi-line tasks with indentation
- Extract `@path` file references
- Atomic file updates with backup
- Unit tests for parsing

### Milestone 2: Task Runner
- Create `todo.py` with `TodoRunner` class
- Fresh agent session per task (no context accumulation)
- Completion tag parsing (`[TASK_DONE]`/`[TASK_FAILED]`)
- Per-task timeout handling
- File context injection for `@path` references

### Milestone 3: CLI Integration
- Add `todo` command to `cli.py`
- Implement `--dry-run` preview mode
- Implement `--retry-failed` for `[!]` tasks
- Implement `--results` file output
- Progress display and summary

### Milestone 4: Polish
- MCP config support
- Verbose mode with full responses
- Graceful interruption (Ctrl+C saves progress)
- Error handling and edge cases
- Integration tests

## Testing

```bash
# Create test file
cat > test_tasks.md << 'EOF'
# Test Tasks

- [ ] List files in current directory and count them
- [ ] Read README.md and summarize in one sentence
- [ ] Check if pytest is installed
- [x] Already done task
EOF

# Dry run
orchestrator todo test_tasks.md --dry-run

# Execute with haiku (cheap)
orchestrator todo test_tasks.md --model haiku

# Verbose output
orchestrator todo test_tasks.md --model haiku --verbose

# With results file
orchestrator todo test_tasks.md --model haiku --results results.md
```

## Use Case: Plan File Auditing

The original use case that motivated this feature:

```markdown
# Plans to Audit

- [ ] Check if @docs/plans/PLAN_auth.md is implemented, move to ./archive/ if yes
- [ ] Check if @docs/plans/PLAN_email.md is implemented, move to ./archive/ if yes
- [ ] Check if @docs/plans/PLAN_cache.md is implemented, move to ./archive/ if yes
```

```bash
orchestrator todo plans_to_audit.md --model haiku
```

Each plan is audited independently with fresh context, preventing token accumulation.

## Cost Estimate

Using Haiku for tasks:
- ~2000 tokens input (prompt + file context)
- ~1000 tokens output
- Cost: ~$0.001 per task
- 100 tasks = ~$0.10

Very economical for batch processing.
