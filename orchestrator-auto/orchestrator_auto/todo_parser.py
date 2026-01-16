"""
Parse and update markdown checkbox task files.

Supports:
- Standard checkboxes: [ ] pending, [x] done, [!] failed
- Multi-line tasks via indentation
- @path file references for context injection
- Atomic file updates with backup
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional
import re
import shutil


class TaskStatus(Enum):
    """Status of a task in the checkbox file."""
    PENDING = "pending"      # [ ]
    DONE = "done"            # [x]
    FAILED = "failed"        # [!]


@dataclass
class Task:
    """A single task from a markdown checkbox."""
    line_number: int
    content: str                          # Task text (may be multi-line)
    indent: str = ""                      # Leading whitespace (preserved on update)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None          # Result summary after execution
    file_refs: List[Path] = field(default_factory=list)  # @path references
    continuation_lines: List[int] = field(default_factory=list)  # Line numbers of continuation

    @property
    def is_actionable(self) -> bool:
        """Task should be processed (pending)."""
        return self.status == TaskStatus.PENDING

    @property
    def first_line(self) -> str:
        """Get first line of task content (for display)."""
        return self.content.split('\n')[0]


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

    @property
    def done_count(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.DONE)


# Regex patterns
# Match checkbox line: optional leading whitespace, -, [ ], then content
CHECKBOX_PATTERN = re.compile(r'^(\s*)-\s*\[([ xX!])\]\s*(.*)$')
# Match continuation line: at least 2 spaces or tab, then non-whitespace
CONTINUATION_PATTERN = re.compile(r'^(\s{2,}|\t+)(\S.*)$')
# Match @path file references (alphanumeric, dots, slashes, dashes, underscores)
FILE_REF_PATTERN = re.compile(r'@([\w./\-_]+)')


def parse_task_file(path: Path) -> TaskFile:
    """
    Parse a markdown file into tasks.

    Args:
        path: Path to the markdown file

    Returns:
        TaskFile with parsed tasks

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    if not path.exists():
        raise FileNotFoundError(f"Task file not found: {path}")

    content = path.read_text()
    lines = content.splitlines()
    tasks = []

    i = 0
    while i < len(lines):
        line = lines[i]
        match = CHECKBOX_PATTERN.match(line)

        if match:
            indent, marker, content_text = match.groups()

            # Determine status from marker
            marker_lower = marker.lower()
            if marker == ' ':
                status = TaskStatus.PENDING
            elif marker_lower == 'x':
                status = TaskStatus.DONE
            elif marker == '!':
                status = TaskStatus.FAILED
            else:
                status = TaskStatus.PENDING

            # Collect continuation lines (indented lines following the checkbox)
            # NOTE: Stop if we encounter another checkbox (nested checkboxes are separate tasks)
            task_lines = [content_text]
            continuation_line_numbers = []
            j = i + 1

            while j < len(lines):
                next_line = lines[j]
                # Check if this line is a checkbox (nested task) - if so, stop
                if CHECKBOX_PATTERN.match(next_line):
                    break
                # Check if this is a continuation line (indented non-checkbox)
                cont_match = CONTINUATION_PATTERN.match(next_line)
                if cont_match:
                    task_lines.append(cont_match.group(2))  # Just the content part
                    continuation_line_numbers.append(j)
                    j += 1
                else:
                    break

            full_content = '\n'.join(task_lines)

            # Extract @file references
            file_refs = [Path(m) for m in FILE_REF_PATTERN.findall(full_content)]

            tasks.append(Task(
                line_number=i,
                content=full_content,
                indent=indent,  # Preserve indentation for rendering
                status=status,
                file_refs=file_refs,
                continuation_lines=continuation_line_numbers,
            ))

            i = j  # Skip continuation lines
        else:
            i += 1

    return TaskFile(path=path, tasks=tasks, raw_lines=lines)


def render_task_line(task: Task) -> str:
    """
    Render a task back to markdown checkbox format.

    Only renders the first line (main checkbox). Continuation lines
    are preserved as-is. Indentation is preserved from original parsing.
    """
    marker = {
        TaskStatus.PENDING: ' ',
        TaskStatus.DONE: 'x',
        TaskStatus.FAILED: '!',
    }[task.status]

    return f"{task.indent}- [{marker}] {task.first_line}"


def update_task_file(task_file: TaskFile) -> None:
    """
    Write updated task statuses back to file atomically.

    Uses backup/temp/rename pattern to prevent data loss on crash:
    1. Create backup of original
    2. Write to temp file
    3. Atomic rename temp -> original
    4. Remove backup on success

    Args:
        task_file: TaskFile with updated task statuses

    Raises:
        IOError: If write fails (original file preserved from backup)
    """
    path = task_file.path
    backup_path = path.with_suffix('.md.bak')
    temp_path = path.with_suffix('.md.tmp')

    # Build updated content
    new_lines = task_file.raw_lines.copy()

    for task in task_file.tasks:
        # Only update the checkbox line, not continuation lines
        new_lines[task.line_number] = render_task_line(task)

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
            backup_path.unlink()
        if temp_path.exists():
            temp_path.unlink()
        raise


def get_actionable_tasks(
    task_file: TaskFile,
    retry_failed: bool = False
) -> List[Task]:
    """
    Get tasks that should be processed.

    Args:
        task_file: Parsed task file
        retry_failed: If True, also include tasks marked [!]

    Returns:
        List of tasks to process
    """
    tasks = []
    for task in task_file.tasks:
        if task.status == TaskStatus.PENDING:
            tasks.append(task)
        elif task.status == TaskStatus.FAILED and retry_failed:
            tasks.append(task)
    return tasks
