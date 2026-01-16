"""
Unit tests for todo_parser module.
"""

import pytest
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto.todo_parser import (
    TaskStatus,
    Task,
    TaskFile,
    parse_task_file,
    render_task_line,
    update_task_file,
    get_actionable_tasks,
    CHECKBOX_PATTERN,
    CONTINUATION_PATTERN,
    FILE_REF_PATTERN,
)


class TestTaskStatus:
    """Test TaskStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.DONE.value == "done"
        assert TaskStatus.FAILED.value == "failed"


class TestCheckboxPattern:
    """Test checkbox regex pattern."""

    def test_pending_checkbox(self):
        """Test parsing pending checkbox."""
        match = CHECKBOX_PATTERN.match("- [ ] Task content")
        assert match is not None
        assert match.group(1) == ""  # indent
        assert match.group(2) == " "  # marker
        assert match.group(3) == "Task content"

    def test_done_checkbox(self):
        """Test parsing done checkbox (lowercase x)."""
        match = CHECKBOX_PATTERN.match("- [x] Done task")
        assert match is not None
        assert match.group(2) == "x"

    def test_done_checkbox_uppercase(self):
        """Test parsing done checkbox (uppercase X)."""
        match = CHECKBOX_PATTERN.match("- [X] Done task")
        assert match is not None
        assert match.group(2) == "X"

    def test_failed_checkbox(self):
        """Test parsing failed checkbox."""
        match = CHECKBOX_PATTERN.match("- [!] Failed task")
        assert match is not None
        assert match.group(2) == "!"

    def test_indented_checkbox(self):
        """Test parsing indented checkbox."""
        match = CHECKBOX_PATTERN.match("  - [ ] Indented task")
        assert match is not None
        assert match.group(1) == "  "
        assert match.group(3) == "Indented task"

    def test_no_match_without_dash(self):
        """Test non-matching lines."""
        assert CHECKBOX_PATTERN.match("[ ] No dash") is None
        assert CHECKBOX_PATTERN.match("Regular text") is None
        assert CHECKBOX_PATTERN.match("") is None


class TestContinuationPattern:
    """Test continuation line pattern."""

    def test_two_space_indent(self):
        """Test two-space continuation."""
        match = CONTINUATION_PATTERN.match("  continuation text")
        assert match is not None

    def test_tab_indent(self):
        """Test tab continuation."""
        match = CONTINUATION_PATTERN.match("\tcontinuation text")
        assert match is not None

    def test_no_match_without_indent(self):
        """Test non-continuation lines."""
        assert CONTINUATION_PATTERN.match("no indent") is None
        assert CONTINUATION_PATTERN.match(" single space") is None


class TestFileRefPattern:
    """Test @file reference pattern."""

    def test_simple_file_ref(self):
        """Test simple file reference."""
        matches = FILE_REF_PATTERN.findall("Review @src/auth.py")
        assert matches == ["src/auth.py"]

    def test_multiple_refs(self):
        """Test multiple file references."""
        matches = FILE_REF_PATTERN.findall("Compare @file1.py with @dir/file2.js")
        assert matches == ["file1.py", "dir/file2.js"]

    def test_complex_path(self):
        """Test complex path with dashes and underscores."""
        matches = FILE_REF_PATTERN.findall("Check @src/my-module/test_file.py")
        assert matches == ["src/my-module/test_file.py"]


class TestParseTaskFile:
    """Test parsing task files."""

    def test_parse_simple_tasks(self, tmp_path):
        """Test parsing simple checkbox file."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""# My Tasks

- [ ] First task
- [x] Second task (done)
- [!] Third task (failed)
""")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 3
        assert result.tasks[0].status == TaskStatus.PENDING
        assert result.tasks[0].content == "First task"
        assert result.tasks[1].status == TaskStatus.DONE
        assert result.tasks[2].status == TaskStatus.FAILED

    def test_parse_multiline_task(self, tmp_path):
        """Test parsing multi-line task with continuation."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Main task line
      Continuation line 1
      Continuation line 2
- [ ] Next task
""")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 2
        assert "Main task line" in result.tasks[0].content
        assert "Continuation line 1" in result.tasks[0].content
        assert "Continuation line 2" in result.tasks[0].content
        assert result.tasks[1].content == "Next task"

    def test_parse_file_refs(self, tmp_path):
        """Test extracting @file references."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Review @src/auth.py and @tests/test_auth.py
""")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 1
        assert len(result.tasks[0].file_refs) == 2
        assert Path("src/auth.py") in result.tasks[0].file_refs
        assert Path("tests/test_auth.py") in result.tasks[0].file_refs

    def test_parse_counts(self, tmp_path):
        """Test task counts."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Pending 1
- [ ] Pending 2
- [x] Done
- [!] Failed 1
- [!] Failed 2
""")

        result = parse_task_file(task_file)

        assert result.pending_count == 2
        assert result.done_count == 1
        assert result.failed_count == 2

    def test_parse_empty_file(self, tmp_path):
        """Test parsing empty file."""
        task_file = tmp_path / "empty.md"
        task_file.write_text("")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 0

    def test_parse_file_not_found(self):
        """Test FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            parse_task_file(Path("/nonexistent/file.md"))


class TestRenderTaskLine:
    """Test rendering tasks back to markdown."""

    def test_render_pending(self):
        """Test rendering pending task."""
        task = Task(line_number=0, content="My task", status=TaskStatus.PENDING)
        assert render_task_line(task) == "- [ ] My task"

    def test_render_done(self):
        """Test rendering done task."""
        task = Task(line_number=0, content="My task", status=TaskStatus.DONE)
        assert render_task_line(task) == "- [x] My task"

    def test_render_failed(self):
        """Test rendering failed task."""
        task = Task(line_number=0, content="My task", status=TaskStatus.FAILED)
        assert render_task_line(task) == "- [!] My task"

    def test_render_multiline_takes_first(self):
        """Test that rendering multiline task uses first line only."""
        task = Task(
            line_number=0,
            content="First line\nSecond line\nThird line",
            status=TaskStatus.PENDING
        )
        assert render_task_line(task) == "- [ ] First line"


class TestUpdateTaskFile:
    """Test atomic file updates."""

    def test_update_status(self, tmp_path):
        """Test updating task status in file."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""# Tasks

- [ ] First task
- [ ] Second task
""")

        result = parse_task_file(task_file)

        # Mark first task as done
        result.tasks[0].status = TaskStatus.DONE
        update_task_file(result)

        # Re-read and verify
        updated = parse_task_file(task_file)
        assert updated.tasks[0].status == TaskStatus.DONE
        assert updated.tasks[1].status == TaskStatus.PENDING

    def test_update_preserves_other_content(self, tmp_path):
        """Test that update preserves non-task content."""
        original_content = """# My Task List

Some description here.

- [ ] Task one

More text between tasks.

- [ ] Task two

Final notes.
"""
        task_file = tmp_path / "tasks.md"
        task_file.write_text(original_content)

        result = parse_task_file(task_file)
        result.tasks[0].status = TaskStatus.DONE
        update_task_file(result)

        updated_content = task_file.read_text()
        assert "# My Task List" in updated_content
        assert "Some description here." in updated_content
        assert "More text between tasks." in updated_content
        assert "Final notes." in updated_content

    def test_no_backup_left_on_success(self, tmp_path):
        """Test that backup file is removed on success."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] Task\n")

        result = parse_task_file(task_file)
        result.tasks[0].status = TaskStatus.DONE
        update_task_file(result)

        backup_path = task_file.with_suffix('.md.bak')
        temp_path = task_file.with_suffix('.md.tmp')

        assert not backup_path.exists()
        assert not temp_path.exists()


class TestGetActionableTasks:
    """Test filtering actionable tasks."""

    def test_get_pending_only(self, tmp_path):
        """Test getting only pending tasks."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Pending
- [x] Done
- [!] Failed
""")

        result = parse_task_file(task_file)
        actionable = get_actionable_tasks(result, retry_failed=False)

        assert len(actionable) == 1
        assert actionable[0].content == "Pending"

    def test_get_pending_and_failed(self, tmp_path):
        """Test getting pending and failed tasks with retry flag."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Pending
- [x] Done
- [!] Failed
""")

        result = parse_task_file(task_file)
        actionable = get_actionable_tasks(result, retry_failed=True)

        assert len(actionable) == 2
        assert actionable[0].content == "Pending"
        assert actionable[1].content == "Failed"


class TestTaskProperties:
    """Test Task dataclass properties."""

    def test_is_actionable_pending(self):
        """Test is_actionable for pending task."""
        task = Task(line_number=0, content="Task", status=TaskStatus.PENDING)
        assert task.is_actionable is True

    def test_is_actionable_done(self):
        """Test is_actionable for done task."""
        task = Task(line_number=0, content="Task", status=TaskStatus.DONE)
        assert task.is_actionable is False

    def test_is_actionable_failed(self):
        """Test is_actionable for failed task."""
        task = Task(line_number=0, content="Task", status=TaskStatus.FAILED)
        assert task.is_actionable is False

    def test_first_line_single(self):
        """Test first_line for single-line task."""
        task = Task(line_number=0, content="Single line")
        assert task.first_line == "Single line"

    def test_first_line_multiline(self):
        """Test first_line for multi-line task."""
        task = Task(line_number=0, content="First\nSecond\nThird")
        assert task.first_line == "First"


class TestIndentationPreservation:
    """Test that indentation is preserved when parsing and updating tasks."""

    def test_parse_captures_indent(self, tmp_path):
        """Test that parsing captures the indent from indented tasks."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Top level task
  - [ ] Two-space indented
    - [ ] Four-space indented
""")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 3
        assert result.tasks[0].indent == ""
        assert result.tasks[1].indent == "  "
        assert result.tasks[2].indent == "    "

    def test_render_preserves_indent(self):
        """Test that rendering includes the original indent."""
        task = Task(line_number=0, content="Indented task", indent="  ", status=TaskStatus.PENDING)
        assert render_task_line(task) == "  - [ ] Indented task"

        task_done = Task(line_number=0, content="Done task", indent="    ", status=TaskStatus.DONE)
        assert render_task_line(task_done) == "    - [x] Done task"

    def test_update_preserves_indent(self, tmp_path):
        """Test that updating a task preserves its indentation."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""# Nested tasks

- [ ] Parent task
  - [ ] Child task
    - [ ] Grandchild task
""")

        result = parse_task_file(task_file)

        # Mark the child task (indented) as done
        result.tasks[1].status = TaskStatus.DONE
        update_task_file(result)

        # Re-read and verify indentation is preserved
        updated_content = task_file.read_text()
        assert "- [ ] Parent task" in updated_content
        assert "  - [x] Child task" in updated_content
        assert "    - [ ] Grandchild task" in updated_content

    def test_update_preserves_all_indents(self, tmp_path):
        """Test updating multiple indented tasks preserves all indents."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Task A
  - [ ] Task B
- [ ] Task C
  - [ ] Task D
""")

        result = parse_task_file(task_file)

        # Mark all tasks done
        for task in result.tasks:
            task.status = TaskStatus.DONE
        update_task_file(result)

        updated_content = task_file.read_text()
        assert "- [x] Task A" in updated_content
        assert "  - [x] Task B" in updated_content
        assert "- [x] Task C" in updated_content
        assert "  - [x] Task D" in updated_content


class TestNestedCheckboxParsing:
    """Test that nested checkboxes are parsed as separate tasks, not continuation."""

    def test_nested_checkbox_not_continuation(self, tmp_path):
        """Test that indented checkboxes are parsed as separate tasks."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Parent task
  - [ ] Child task (should be separate)
  - [ ] Another child
- [ ] Next parent
""")

        result = parse_task_file(task_file)

        # Should be 4 separate tasks, not 2 tasks with continuations
        assert len(result.tasks) == 4
        assert result.tasks[0].content == "Parent task"
        assert result.tasks[1].content == "Child task (should be separate)"
        assert result.tasks[2].content == "Another child"
        assert result.tasks[3].content == "Next parent"

    def test_nested_checkbox_preserves_indent(self, tmp_path):
        """Test that nested checkboxes preserve their indent."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Level 0
  - [ ] Level 1
    - [ ] Level 2
""")

        result = parse_task_file(task_file)

        assert result.tasks[0].indent == ""
        assert result.tasks[1].indent == "  "
        assert result.tasks[2].indent == "    "

    def test_continuation_still_works_before_nested_checkbox(self, tmp_path):
        """Test that continuation lines work but stop at nested checkboxes."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Parent task
      This is a continuation line
      Another continuation
  - [ ] Child task
""")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 2
        assert "Parent task" in result.tasks[0].content
        assert "This is a continuation line" in result.tasks[0].content
        assert "Another continuation" in result.tasks[0].content
        assert result.tasks[1].content == "Child task"

    def test_mixed_nested_and_continuation(self, tmp_path):
        """Test file with both continuations and nested checkboxes."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Task with details
      Detail line 1
      Detail line 2
  - [ ] Nested task also with details
        Nested detail
- [ ] Another top level
""")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 3

        # First task has continuations
        assert "Task with details" in result.tasks[0].content
        assert "Detail line 1" in result.tasks[0].content
        assert "Detail line 2" in result.tasks[0].content

        # Second task (nested) also has continuation
        assert "Nested task also with details" in result.tasks[1].content
        assert "Nested detail" in result.tasks[1].content

        # Third task is separate
        assert result.tasks[2].content == "Another top level"

    def test_deeply_nested_checkboxes(self, tmp_path):
        """Test deeply nested checkbox structure."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Level 0
  - [ ] Level 1a
    - [ ] Level 2a
    - [ ] Level 2b
  - [ ] Level 1b
- [ ] Another Level 0
""")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 6
        assert result.tasks[0].indent == ""
        assert result.tasks[1].indent == "  "
        assert result.tasks[2].indent == "    "
        assert result.tasks[3].indent == "    "
        assert result.tasks[4].indent == "  "
        assert result.tasks[5].indent == ""
