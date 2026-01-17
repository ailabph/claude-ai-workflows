"""
Unit tests for todo module (TodoRunner and completion tag parsing).
"""

import pytest
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto.todo import (
    TaskResult,
    parse_completion_tags,
    build_file_context,
    get_model_id,
    TASK_PROMPT_TEMPLATE,
)
from orchestrator_auto.todo_parser import Task, TaskStatus


class TestParseCompletionTags:
    """Test completion tag parsing from agent responses."""

    def test_parse_task_done(self):
        """Test parsing TASK_DONE tag."""
        response = """
        I've completed the analysis.

        [TASK_DONE]
        Result: Found 3 issues in the authentication module
        [/TASK_DONE]
        """

        status, result = parse_completion_tags(response)

        assert status == TaskStatus.DONE
        assert "Found 3 issues" in result

    def test_parse_task_done_multiline_result(self):
        """Test parsing TASK_DONE with multiline result."""
        response = """
        [TASK_DONE]
        Result: Fixed the bug by updating the validation logic
        and adding proper error handling
        [/TASK_DONE]
        """

        status, result = parse_completion_tags(response)

        assert status == TaskStatus.DONE
        assert "Fixed the bug" in result

    def test_parse_task_failed(self):
        """Test parsing TASK_FAILED tag."""
        response = """
        I attempted to complete the task but encountered an issue.

        [TASK_FAILED]
        Reason: File not found - the specified path does not exist
        [/TASK_FAILED]
        """

        status, reason = parse_completion_tags(response)

        assert status == TaskStatus.FAILED
        assert "File not found" in reason

    def test_parse_task_failed_multiline_reason(self):
        """Test parsing TASK_FAILED with multiline reason."""
        response = """
        [TASK_FAILED]
        Reason: Multiple issues prevented completion:
        1. Missing dependencies
        2. Invalid configuration
        [/TASK_FAILED]
        """

        status, reason = parse_completion_tags(response)

        assert status == TaskStatus.FAILED
        assert "Multiple issues" in reason

    def test_parse_no_tag(self):
        """Test response without completion tag."""
        response = """
        I'm working on the task and making progress.
        Here's what I've done so far...
        """

        status, reason = parse_completion_tags(response)

        assert status == TaskStatus.FAILED
        assert "No completion tag" in reason

    def test_parse_empty_response(self):
        """Test empty response."""
        status, reason = parse_completion_tags("")

        assert status == TaskStatus.FAILED
        assert "No completion tag" in reason

    def test_parse_case_insensitive(self):
        """Test case insensitivity of tags."""
        response = """
        [task_done]
        Result: Task completed successfully
        [/task_done]
        """

        status, result = parse_completion_tags(response)

        assert status == TaskStatus.DONE
        assert "Task completed" in result


class TestBuildFileContext:
    """Test file context building for @path references."""

    def test_no_refs(self, tmp_path):
        """Test task without file references."""
        task = Task(line_number=0, content="No refs here", file_refs=[])

        context = build_file_context(task, tmp_path)

        assert context == ""

    def test_single_ref_existing_file(self, tmp_path):
        """Test single file reference to existing file."""
        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        task = Task(
            line_number=0,
            content="Review @test.py",
            file_refs=[Path("test.py")]
        )

        context = build_file_context(task, tmp_path)

        assert "FILE CONTEXT:" in context
        assert "test.py" in context
        assert "def hello(): pass" in context

    def test_ref_missing_file(self, tmp_path):
        """Test reference to missing file."""
        task = Task(
            line_number=0,
            content="Review @missing.py",
            file_refs=[Path("missing.py")]
        )

        context = build_file_context(task, tmp_path)

        assert "[File not found]" in context

    def test_multiple_refs(self, tmp_path):
        """Test multiple file references."""
        # Create test files
        (tmp_path / "file1.py").write_text("content 1")
        (tmp_path / "file2.py").write_text("content 2")

        task = Task(
            line_number=0,
            content="Compare files",
            file_refs=[Path("file1.py"), Path("file2.py")]
        )

        context = build_file_context(task, tmp_path)

        assert "file1.py" in context
        assert "file2.py" in context
        assert "content 1" in context
        assert "content 2" in context

    def test_absolute_path_rejected(self, tmp_path):
        """Test that absolute paths are rejected for security."""
        task = Task(
            line_number=0,
            content="Read @/etc/passwd",
            file_refs=[Path("/etc/passwd")]
        )

        context = build_file_context(task, tmp_path)

        assert "Rejected: absolute paths not allowed" in context

    def test_parent_directory_escape_rejected(self, tmp_path):
        """Test that ../ escapes are rejected for security."""
        # Create a file outside tmp_path that we shouldn't be able to access
        task = Task(
            line_number=0,
            content="Read @../../../etc/passwd",
            file_refs=[Path("../../../etc/passwd")]
        )

        context = build_file_context(task, tmp_path)

        assert "Rejected: path escapes task directory" in context

    def test_subdirectory_access_allowed(self, tmp_path):
        """Test that subdirectory access is allowed."""
        # Create subdirectory and file
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file.py").write_text("subdir content")

        task = Task(
            line_number=0,
            content="Read @subdir/file.py",
            file_refs=[Path("subdir/file.py")]
        )

        context = build_file_context(task, tmp_path)

        assert "subdir content" in context
        assert "Rejected" not in context


class TestGetModelId:
    """Test model alias resolution."""

    def test_alias_opus(self):
        """Test opus alias."""
        assert "opus" in get_model_id("opus")

    def test_alias_sonnet(self):
        """Test sonnet alias."""
        assert "sonnet" in get_model_id("sonnet")

    def test_alias_haiku(self):
        """Test haiku alias."""
        assert "haiku" in get_model_id("haiku")

    def test_alias_case_insensitive(self):
        """Test case insensitivity."""
        assert get_model_id("SONNET") == get_model_id("sonnet")
        assert get_model_id("Opus") == get_model_id("opus")

    def test_full_id_passthrough(self):
        """Test that full model IDs pass through unchanged."""
        full_id = "claude-3-opus-20240229"
        assert get_model_id(full_id) == full_id


class TestTaskResult:
    """Test TaskResult dataclass."""

    def test_result_done(self):
        """Test TaskResult for completed task."""
        task = Task(line_number=0, content="Test task")
        result = TaskResult(
            task=task,
            status=TaskStatus.DONE,
            result="Completed successfully",
            duration=5.2,
        )

        assert result.status == TaskStatus.DONE
        assert result.result == "Completed successfully"
        assert result.duration == 5.2
        assert result.error is None

    def test_result_failed(self):
        """Test TaskResult for failed task."""
        task = Task(line_number=0, content="Test task")
        result = TaskResult(
            task=task,
            status=TaskStatus.FAILED,
            error="Timeout after 300s",
            duration=300.0,
        )

        assert result.status == TaskStatus.FAILED
        assert result.error == "Timeout after 300s"
        assert result.result is None


class TestPromptTemplate:
    """Test prompt template formatting."""

    def test_template_has_placeholders(self):
        """Test that template contains expected placeholders."""
        assert "{task_content}" in TASK_PROMPT_TEMPLATE
        assert "{file_context}" in TASK_PROMPT_TEMPLATE

    def test_template_has_completion_instructions(self):
        """Test that template includes completion tag instructions."""
        assert "[TASK_DONE]" in TASK_PROMPT_TEMPLATE
        assert "[TASK_FAILED]" in TASK_PROMPT_TEMPLATE
        assert "Result:" in TASK_PROMPT_TEMPLATE
        assert "Reason:" in TASK_PROMPT_TEMPLATE

    def test_template_format(self):
        """Test that template can be formatted."""
        formatted = TASK_PROMPT_TEMPLATE.format(
            task_content="Test the API endpoint",
            file_context="",
        )

        assert "Test the API endpoint" in formatted
        assert "[TASK_DONE]" in formatted


class TestTodoRunnerCallbacks:
    """Test TodoRunner callback functionality."""

    def test_on_task_chunk_callback_stored(self):
        """Test that on_task_chunk callback is stored on runner."""
        from orchestrator_auto.todo import TodoRunner

        chunks_received = []

        def chunk_callback(text: str):
            chunks_received.append(text)

        # Create runner with chunk callback
        runner = TodoRunner(
            model="haiku",
            on_task_chunk=chunk_callback,
        )

        # Verify callback is stored
        assert runner.on_task_chunk == chunk_callback

        # Verify chunks list is initially empty
        assert chunks_received == []

    def test_on_task_chunk_callback_optional(self):
        """Test that on_task_chunk callback is optional."""
        from orchestrator_auto.todo import TodoRunner

        # Create runner without chunk callback
        runner = TodoRunner(model="haiku")

        # Verify callback is None
        assert runner.on_task_chunk is None

    def test_on_task_chunk_callback_invoked_during_execution(self, tmp_path, monkeypatch):
        """Test that on_task_chunk callback is actually invoked during task execution."""
        from orchestrator_auto.todo import TodoRunner, TaskResult
        from orchestrator_auto.todo_parser import parse_task_file, TaskStatus
        import asyncio

        # Create test task file
        task_file_path = tmp_path / "tasks.md"
        task_file_path.write_text("- [ ] Test task")

        chunks_received = []

        def chunk_callback(text: str):
            chunks_received.append(text)

        # Mock execute_task to simulate streaming chunks
        async def mock_execute_task(task, base_path):
            # Simulate chunk emission via the callback
            if runner.on_task_chunk:
                runner.on_task_chunk("chunk1")
                runner.on_task_chunk("chunk2")
            return TaskResult(
                task=task,
                status=TaskStatus.DONE,
                result="Test completed",
                duration=0.1,
            )

        runner = TodoRunner(
            model="haiku",
            on_task_chunk=chunk_callback,
        )

        # Monkeypatch execute_task
        monkeypatch.setattr(runner, "execute_task", mock_execute_task)

        task_file = parse_task_file(task_file_path)
        results = runner.run_all(task_file)

        # Verify chunks were received
        assert chunks_received == ["chunk1", "chunk2"]
        assert len(results) == 1
        assert results[0].status == TaskStatus.DONE


class TestTodoRunnerStop:
    """Test TodoRunner graceful stop functionality."""

    def test_stop_flag_initially_false(self):
        """Test that stop flag is initially False."""
        from orchestrator_auto.todo import TodoRunner

        runner = TodoRunner(model="haiku")

        assert runner._stop_requested is False

    def test_stop_method_sets_flag(self):
        """Test that stop() method sets the stop flag."""
        from orchestrator_auto.todo import TodoRunner

        runner = TodoRunner(model="haiku")
        runner.stop()

        assert runner._stop_requested is True

    def test_stop_prevents_next_task_execution(self, tmp_path, monkeypatch):
        """Test that stop flag prevents execution of subsequent tasks."""
        from orchestrator_auto.todo import TodoRunner, TaskResult
        from orchestrator_auto.todo_parser import parse_task_file, TaskStatus
        import asyncio

        # Create a test task file with multiple tasks
        task_file_path = tmp_path / "tasks.md"
        task_file_path.write_text("""
# Test Tasks

- [ ] Task 1
- [ ] Task 2
- [ ] Task 3
""")

        # Track which tasks were executed
        tasks_executed = []

        # Mock execute_task to return fast results
        async def mock_execute_task(task, base_path):
            tasks_executed.append(task.first_line.strip())
            return TaskResult(
                task=task,
                status=TaskStatus.DONE,
                result=f"Completed: {task.first_line}",
                duration=0.01,
            )

        # Track which tasks started (via callback)
        tasks_started_via_callback = []

        def on_start(index, total, task):
            tasks_started_via_callback.append(index)
            # Stop after first task starts
            if index == 1:
                runner.stop()

        runner = TodoRunner(
            model="haiku",
            timeout=1,
            on_task_start=on_start,
        )

        # Monkeypatch execute_task to avoid real agent calls
        monkeypatch.setattr(runner, "execute_task", mock_execute_task)

        # Parse task file
        task_file = parse_task_file(task_file_path)

        # Run all tasks - should stop after first due to stop() in on_start callback
        results = runner.run_all(task_file)

        # Verify only first task was executed
        assert len(tasks_executed) == 1
        assert "Task 1" in tasks_executed[0]

        # Verify only first task triggered on_start callback
        assert tasks_started_via_callback == [1]

        # Verify stop flag is set
        assert runner._stop_requested is True

        # Verify we got exactly 1 result
        assert len(results) == 1
        assert results[0].status == TaskStatus.DONE
