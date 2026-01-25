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
    _update_checkbox_marker,
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


class TestWhitespacePreservation:
    """Test that exact whitespace formatting is preserved during updates."""

    def test_preserves_multiple_spaces_after_bracket(self, tmp_path):
        """Test that multiple spaces after ] are preserved."""
        task_file = tmp_path / "tasks.md"
        # Write file with unusual spacing (3 spaces after ])
        task_file.write_text("- [ ]   Triple spaced content\n")

        result = parse_task_file(task_file)
        result.tasks[0].status = TaskStatus.DONE
        update_task_file(result)

        updated = task_file.read_text()
        # The three spaces should be preserved
        assert "- [x]   Triple spaced content" in updated

    def test_preserves_tab_after_bracket(self, tmp_path):
        """Test that tab character after ] is preserved."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ]\tTab separated content\n")

        result = parse_task_file(task_file)
        result.tasks[0].status = TaskStatus.DONE
        update_task_file(result)

        updated = task_file.read_text()
        assert "- [x]\tTab separated content" in updated

    def test_marker_replacement_preserves_exact_line(self):
        """Test _update_checkbox_marker preserves exact formatting."""
        # Multiple spaces after bracket
        line = "- [ ]   Lots of space"
        updated, success = _update_checkbox_marker(line, TaskStatus.DONE)
        assert success
        assert updated == "- [x]   Lots of space"

        # Tab after bracket
        line = "- [ ]\tTabbed"
        updated, success = _update_checkbox_marker(line, TaskStatus.FAILED)
        assert success
        assert updated == "- [!]\tTabbed"

        # Unusual spacing before bracket
        line = "-   [ ] Extra before bracket"
        updated, success = _update_checkbox_marker(line, TaskStatus.DONE)
        assert success
        assert updated == "-   [x] Extra before bracket"

    def test_preserves_trailing_whitespace(self, tmp_path):
        """Test that trailing whitespace in content is preserved."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] Content with trailing   \n")

        result = parse_task_file(task_file)
        result.tasks[0].status = TaskStatus.DONE
        update_task_file(result)

        updated = task_file.read_text()
        assert "- [x] Content with trailing   " in updated


class TestContentMatchingGuard:
    """Test the content-matching guard against line-number drift."""

    def test_guard_allows_matching_content(self):
        """Test that update proceeds when content matches."""
        line = "- [ ] Expected content"
        updated, success = _update_checkbox_marker(
            line, TaskStatus.DONE, expected_content="Expected content"
        )
        assert success
        assert updated == "- [x] Expected content"

    def test_guard_blocks_mismatched_content(self):
        """Test that update is blocked when content doesn't match."""
        line = "- [ ] Actual content"
        updated, success = _update_checkbox_marker(
            line, TaskStatus.DONE, expected_content="Different content"
        )
        assert not success
        assert updated == "- [ ] Actual content"  # Unchanged

    def test_guard_ignores_leading_trailing_whitespace(self):
        """Test that comparison ignores leading/trailing whitespace."""
        line = "- [ ]   Content with extra spaces   "
        # Should match despite different whitespace in expected
        updated, success = _update_checkbox_marker(
            line, TaskStatus.DONE, expected_content="Content with extra spaces"
        )
        assert success

    def test_guard_returns_warning_on_line_drift(self, tmp_path):
        """Test that update_task_file returns warnings for drifted lines."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] Original task\n")

        result = parse_task_file(task_file)
        # Manually change the task's first_line to simulate drift
        result.tasks[0].content = "Different task content"
        result.tasks[0].status = TaskStatus.DONE

        warnings = update_task_file(result)

        # Should have a warning about content mismatch
        assert len(warnings) == 1
        assert "content mismatch" in warnings[0]
        assert "Different task content" in warnings[0]

        # Original file should be unchanged (task not updated)
        updated = task_file.read_text()
        assert "- [ ] Original task" in updated

    def test_guard_handles_line_out_of_range(self, tmp_path):
        """Test warning when line number exceeds file length."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] Only task\n")

        result = parse_task_file(task_file)
        # Manually set invalid line number
        result.tasks[0].line_number = 100
        result.tasks[0].status = TaskStatus.DONE

        warnings = update_task_file(result)

        assert len(warnings) == 1
        assert "out of range" in warnings[0]

    def test_simulated_agent_line_insertion(self, tmp_path):
        """Test behavior when agent inserts lines before a task."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""# Header
- [ ] Task A
- [ ] Task B
""")

        result = parse_task_file(task_file)
        # Task A at line 1, Task B at line 2
        assert result.tasks[0].line_number == 1
        assert result.tasks[0].content == "Task A"
        assert result.tasks[1].line_number == 2
        assert result.tasks[1].content == "Task B"

        # Simulate agent inserting 2 lines at the top
        new_content = """# Header
# New line 1
# New line 2
- [ ] Task A
- [ ] Task B
"""
        task_file.write_text(new_content)

        # Mark both tasks as done (but line_numbers are now wrong)
        result.tasks[0].status = TaskStatus.DONE
        result.tasks[1].status = TaskStatus.DONE

        warnings = update_task_file(result)

        # Both tasks should warn - line 1 is now "# New line 1", line 2 is "# New line 2"
        assert len(warnings) == 2
        assert any("Task A" in w and "content mismatch" in w for w in warnings)
        assert any("Task B" in w and "content mismatch" in w for w in warnings)

        # Neither task should be marked done (both are now at different lines)
        final_content = task_file.read_text()
        assert "- [ ] Task A" in final_content
        assert "- [ ] Task B" in final_content

    def test_no_warning_when_content_matches(self, tmp_path):
        """Test that no warnings are returned when everything matches."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Task A
- [ ] Task B
""")

        result = parse_task_file(task_file)
        result.tasks[0].status = TaskStatus.DONE
        result.tasks[1].status = TaskStatus.DONE

        warnings = update_task_file(result)

        assert len(warnings) == 0

        # Both tasks should be updated
        updated = task_file.read_text()
        assert "- [x] Task A" in updated
        assert "- [x] Task B" in updated


class TestBlankLinesInMultiLineTasks:
    """Test that blank lines within multi-line task blocks are handled correctly."""

    def test_blank_line_between_checkbox_and_continuation(self, tmp_path):
        """Test parsing task with blank line after checkbox."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] **auth_test.py** - Test HMAC Authentication

  Build a CLI tool for testing.

  Requirements:
  - Create a shared module
  - Load API keys from .env
""")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 1
        task = result.tasks[0]
        assert "**auth_test.py** - Test HMAC Authentication" in task.content
        assert "Build a CLI tool for testing." in task.content
        assert "Requirements:" in task.content
        assert "Create a shared module" in task.content
        assert "Load API keys from .env" in task.content

    def test_multiple_blank_lines_preserved(self, tmp_path):
        """Test that multiple consecutive blank lines are preserved."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Main task


  After two blank lines
""")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 1
        # Content should have blank lines preserved
        assert result.tasks[0].content.count('\n') >= 2

    def test_blank_lines_stop_at_section_divider(self, tmp_path):
        """Test that --- section divider stops continuation even after blank lines."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] First task

  Continuation of first

---

- [ ] Second task
""")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 2
        assert "First task" in result.tasks[0].content
        assert "Continuation of first" in result.tasks[0].content
        assert "Second task" in result.tasks[1].content
        # First task should NOT contain second task content
        assert "Second task" not in result.tasks[0].content

    def test_blank_lines_stop_at_heading(self, tmp_path):
        """Test that # heading stops continuation even after blank lines."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] First task

  Continuation

### Phase 2

- [ ] Second task
""")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 2
        assert "Continuation" in result.tasks[0].content
        assert "Phase 2" not in result.tasks[0].content

    def test_blank_lines_stop_at_new_checkbox(self, tmp_path):
        """Test that new checkbox stops continuation even after blank lines."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] First task

  Continuation

- [ ] Second task
""")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 2
        assert "Continuation" in result.tasks[0].content
        assert "Second task" not in result.tasks[0].content

    def test_complex_multiline_task_format(self, tmp_path):
        """Test the user's exact format with phases and nested bullets."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""### Phase 1: Authentication

- [ ] **auth_test.py** - Test HMAC Authentication

  Build a CLI tool `scripts/cli/coinsher/auth_test.py` for `GET /internal/v1/auth/test/`.

  Requirements:
  - Create a shared `scripts/cli/coinsher/hmac_client.py` module
  - Load API_KEY and API_SECRET from `.env`
  - Display response fields: api_key_prefix, credential_name

---

### Phase 2: Deposit Address Management

- [ ] **deposit_address_create.py** - Create Deposit Address

  Build a CLI tool for `POST /internal/v1/deposit/address/`.

  Requirements:
  - Prompt for: partner_payer_ref, currency, network
  - Use hmac_client.py for signed requests
""")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 2

        # First task should have all its content
        first = result.tasks[0]
        assert "**auth_test.py**" in first.content
        assert "Build a CLI tool" in first.content
        assert "Requirements:" in first.content
        assert "hmac_client.py" in first.content
        assert "Display response fields" in first.content

        # Second task should have all its content
        second = result.tasks[1]
        assert "**deposit_address_create.py**" in second.content
        assert "POST /internal/v1/deposit/address/" in second.content
        assert "partner_payer_ref" in second.content

        # Tasks should NOT bleed into each other
        assert "deposit_address_create" not in first.content
        assert "auth_test" not in second.content

    def test_blank_lines_stop_at_unindented_content(self, tmp_path):
        """Test that unindented non-checkbox content stops continuation."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Task with continuation

  Indented content

Some unindented text that is not part of the task

- [ ] Next task
""")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 2
        assert "Indented content" in result.tasks[0].content
        assert "unindented text" not in result.tasks[0].content

    def test_blank_lines_at_end_of_file(self, tmp_path):
        """Test handling blank lines at end of file after task."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("""- [ ] Final task

  Some continuation


""")

        result = parse_task_file(task_file)

        assert len(result.tasks) == 1
        assert "Final task" in result.tasks[0].content
        assert "Some continuation" in result.tasks[0].content
