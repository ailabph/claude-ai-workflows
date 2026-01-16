"""
Execute tasks with fresh agent context per task.

Key design:
- Each task gets a completely fresh agent session (no context accumulation)
- Agent MUST output explicit completion tags ([TASK_DONE] or [TASK_FAILED])
- Per-task timeout prevents runaway executions
- File updates are atomic with backup
"""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Callable
import re

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import (
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

from .todo_parser import (
    Task, TaskFile, TaskStatus,
    parse_task_file, update_task_file, get_actionable_tasks
)
from .config import MODEL_ALIASES
from .agents import DEFAULT_TOOLS


@dataclass
class TaskResult:
    """Result of executing a single task."""
    task: Task
    status: TaskStatus
    result: Optional[str] = None
    duration: float = 0.0
    error: Optional[str] = None


# Prompt template requiring explicit completion tags
TASK_PROMPT_TEMPLATE = '''You are executing a single task. When finished, you MUST end your response with exactly one of these completion tags:

[TASK_DONE]
Result: <one-line summary of what you accomplished>
[/TASK_DONE]

OR if you cannot complete the task:

[TASK_FAILED]
Reason: <why you could not complete the task>
[/TASK_FAILED]

IMPORTANT:
- You MUST output one of these tags when done. Do not stop without a completion tag.
- Do NOT modify the task file itself (the markdown file containing this task). The orchestrator manages task status automatically.

---

TASK:
{task_content}

{file_context}

---

Execute this task now. Use any tools you need (read files, write files, run bash commands).
When complete, output the appropriate completion tag.'''


def parse_completion_tags(response: str) -> tuple[TaskStatus, Optional[str]]:
    """
    Parse [TASK_DONE] or [TASK_FAILED] from agent response.

    Returns:
        Tuple of (status, result/reason)
        - If TASK_DONE: (DONE, result message)
        - If TASK_FAILED: (FAILED, reason message)
        - If no tag: (FAILED, "No completion tag" message)
    """
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

    # No completion tag found - this means the agent stopped without finishing
    return TaskStatus.FAILED, "No completion tag - task may be incomplete"


def build_file_context(task: Task, base_path: Path) -> str:
    """
    Build context string from @file references in task.

    Security: Only allows relative paths within the base directory.
    Absolute paths and paths escaping base_path (via ..) are rejected.

    Args:
        task: Task with file_refs list
        base_path: Base path for resolving relative paths (task file directory)

    Returns:
        Formatted context string, or empty string if no refs
    """
    if not task.file_refs:
        return ""

    context_parts = ["FILE CONTEXT:"]
    base_resolved = base_path.resolve()

    for ref in task.file_refs:
        # Security: reject absolute paths
        if ref.is_absolute():
            context_parts.append(f"\n--- {ref} ---\n[Rejected: absolute paths not allowed for security]\n")
            continue

        # Resolve the path relative to base
        file_path = (base_path / ref).resolve()

        # Security: ensure path is within base directory (no ../ escapes)
        try:
            file_path.relative_to(base_resolved)
        except ValueError:
            context_parts.append(f"\n--- {ref} ---\n[Rejected: path escapes task directory]\n")
            continue

        if file_path.exists():
            try:
                content = file_path.read_text()
                # Truncate very large files
                if len(content) > 50000:
                    content = content[:50000] + "\n... [truncated, file too large]"
                context_parts.append(f"\n--- {ref} ---\n{content}\n")
            except Exception as e:
                context_parts.append(f"\n--- {ref} ---\n[Error reading file: {e}]\n")
        else:
            context_parts.append(f"\n--- {ref} ---\n[File not found]\n")

    return '\n'.join(context_parts)


def get_model_id(model: str) -> str:
    """Resolve model alias to full model ID."""
    return MODEL_ALIASES.get(model.lower(), model)


class TodoRunner:
    """
    Execute tasks with fresh agent context per task.

    Each task runs in a completely isolated agent session:
    - New session ID
    - No conversation history from previous tasks
    - Agent closed after task completes

    This prevents token accumulation across many tasks.
    """

    def __init__(
        self,
        model: str = "sonnet",
        timeout: int = 300,
        verbose: bool = False,
        mcp_config: Optional[dict] = None,
        on_task_start: Optional[Callable[[int, int, Task], None]] = None,
        on_task_complete: Optional[Callable[[TaskResult], None]] = None,
    ):
        """
        Initialize the todo runner.

        Args:
            model: Model alias (opus, sonnet, haiku) or full ID
            timeout: Per-task timeout in seconds
            verbose: Show full agent responses
            mcp_config: MCP server configuration (already expanded)
            on_task_start: Callback when task starts (index, total, task)
            on_task_complete: Callback when task completes (result)
        """
        self.model = model
        self.model_id = get_model_id(model)
        self.timeout = timeout
        self.verbose = verbose
        self.mcp_config = mcp_config
        self.on_task_start = on_task_start
        self.on_task_complete = on_task_complete

    async def execute_task(self, task: Task, base_path: Path) -> TaskResult:
        """
        Execute a single task with fresh agent context.

        Creates a new agent session, runs the task, parses completion tags,
        and closes the session completely.

        Args:
            task: Task to execute
            base_path: Base path for resolving @file references

        Returns:
            TaskResult with status, result/error, and duration
        """
        start_time = time.time()

        # Build prompt with file context
        file_context = build_file_context(task, base_path)
        prompt = TASK_PROMPT_TEMPLATE.format(
            task_content=task.content,
            file_context=file_context,
        )

        try:
            # Run agent with timeout
            response = await asyncio.wait_for(
                self._run_fresh_agent(prompt),
                timeout=self.timeout
            )

            if self.verbose:
                print(f"\n--- Agent Response ---\n{response}\n---")

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

    async def _run_fresh_agent(self, prompt: str) -> str:
        """
        Run agent query with completely fresh context.

        Creates new agent session, sends prompt, collects response,
        and closes session. Each call is fully isolated.

        Args:
            prompt: Full prompt to send to agent

        Returns:
            Agent's text response
        """
        # Build agent options
        options_kwargs = {
            "system_prompt": "You are a helpful assistant executing tasks.",
            "tools": DEFAULT_TOOLS.copy(),
            "model": self.model_id,
            "cwd": Path.cwd(),
            "permission_mode": "bypassPermissions",
        }

        # Add MCP servers if configured
        if self.mcp_config:
            options_kwargs["mcp_servers"] = self.mcp_config

        options = ClaudeAgentOptions(**options_kwargs)

        # Create fresh client, run query, close client
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

    def run_all(
        self,
        task_file: TaskFile,
        retry_failed: bool = False,
        dry_run: bool = False,
    ) -> List[TaskResult]:
        """
        Run all actionable tasks.

        Args:
            task_file: Parsed task file
            retry_failed: If True, retry tasks marked [!]
            dry_run: If True, don't execute, just preview

        Returns:
            List of TaskResult for each processed task
        """
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
            # Callback: task starting
            if self.on_task_start:
                self.on_task_start(i, len(tasks), task)

            # Execute with fresh context
            result = asyncio.run(self.execute_task(task, base_path))
            results.append(result)

            # Update task status in file
            task.status = result.status
            task.result = result.result or result.error

            # Write progress to file (atomic)
            update_task_file(task_file)

            # Callback: task complete
            if self.on_task_complete:
                self.on_task_complete(result)

        return results


def run_todo_file(
    file_path: Path,
    model: str = "sonnet",
    timeout: int = 300,
    retry_failed: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
    mcp_config: Optional[dict] = None,
) -> List[TaskResult]:
    """
    Convenience function to run a todo file.

    Args:
        file_path: Path to markdown checkbox file
        model: Model alias or full ID
        timeout: Per-task timeout in seconds
        retry_failed: Retry tasks marked [!]
        dry_run: Preview without executing
        verbose: Show full agent responses
        mcp_config: MCP server configuration

    Returns:
        List of TaskResult
    """
    task_file = parse_task_file(file_path)
    runner = TodoRunner(
        model=model,
        timeout=timeout,
        verbose=verbose,
        mcp_config=mcp_config,
    )
    return runner.run_all(task_file, retry_failed=retry_failed, dry_run=dry_run)
