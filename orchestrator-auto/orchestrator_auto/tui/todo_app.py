"""
Todo mode TUI application for orchestrator-auto.

Provides a TUI for executing tasks from markdown checkbox files.
"""

from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer
from textual.worker import Worker
from typing import Optional, Dict, Any
import time

from . import messages
from .adapter import TUIOutputAdapter
from .bindings import GLOBAL_BINDINGS, TODO_BINDINGS
from .widgets import (
    AgentOutput,
    LogPanel,
    TaskListPanel,
)
from .screens import HelpScreen


class TodoTUI(App):
    """
    Text User Interface for todo mode.

    Shows:
    - Task list panel with progress
    - Agent output panel with streaming
    - Log panel for messages

    Usage:
        app = TodoTUI(
            task_file=task_file,
            model="haiku",
            timeout=300,
            retry_failed=False,
            results_file=None,
            verbose=False,
            mcp_config=None,
            dry_run=False,
        )
        app.run()
    """

    TITLE = "Orchestrator Auto - Todo Mode"
    SUB_TITLE = "Task Executor"
    CSS_PATH = "styles/theme.tcss"

    CSS = """
    #main-row {
        width: 100%;
        height: 1fr;
    }

    /* Left column: Task List */
    #left-col {
        width: 1fr;
        min-width: 30;
        max-width: 35;
        height: 100%;
    }

    #task-list-panel {
        height: 1fr;
    }

    /* Right column: Agent Output + Log */
    #right-col {
        width: 2fr;
        min-width: 60;
        height: 100%;
    }

    #agent-output {
        height: 1fr;
        min-height: 20;
    }

    #log-panel {
        height: 12;
        min-height: 8;
    }
    """

    BINDINGS = GLOBAL_BINDINGS + TODO_BINDINGS

    def __init__(
        self,
        task_file,
        model: str = "sonnet",
        timeout: int = 300,
        retry_failed: bool = False,
        results_file: Optional[str] = None,
        verbose: bool = False,
        mcp_config: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
        **kwargs,
    ) -> None:
        """
        Initialize the Todo TUI.

        Args:
            task_file: Parsed TaskFile object
            model: Model alias or full ID
            timeout: Per-task timeout in seconds
            retry_failed: Whether to retry failed tasks
            results_file: Optional path to write results
            verbose: Show detailed logging
            mcp_config: MCP server configuration (already expanded)
            dry_run: Preview mode (don't execute tasks)
        """
        super().__init__(**kwargs)
        self.task_file = task_file
        self.model = model
        self.timeout = timeout
        self.retry_failed = retry_failed
        self.results_file = results_file
        self.verbose = verbose
        self.mcp_config = mcp_config
        self.dry_run = dry_run

        # Internal state
        self._runner: Optional[Any] = None
        self._stop_requested = False
        self._worker: Optional[Worker] = None
        self._start_time = 0.0
        self._adapter = TUIOutputAdapter(self)

    def compose(self) -> ComposeResult:
        """Compose the TUI layout with containers."""
        yield Header()
        with Horizontal(id="main-row"):
            with Vertical(id="left-col"):
                yield TaskListPanel(id="task-list-panel")
            with Vertical(id="right-col"):
                yield AgentOutput(
                    id="agent-output",
                    header_title="AGENT OUTPUT"
                )
                yield LogPanel(id="log-panel")
        yield Footer()

    def on_mount(self) -> None:
        """Handle app mount - initialize task list and start worker."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_info("Todo Mode TUI Started")
        log_panel.log_info(f"File: {self.task_file.path}")
        log_panel.log_info(f"Model: {self.model}")

        # Initialize task list panel
        task_list_panel = self.query_one("#task-list-panel", TaskListPanel)

        # Prepare tasks for display
        from ..todo_parser import get_actionable_tasks
        tasks_to_run = get_actionable_tasks(self.task_file, retry_failed=self.retry_failed)

        tasks_data = [
            {
                "index": i,
                "content": task.first_line,
                "status": "pending",
            }
            for i, task in enumerate(tasks_to_run, 1)
        ]
        task_list_panel.set_tasks(tasks_data)

        if self.dry_run:
            log_panel.log_warning("DRY RUN MODE - Tasks will not be executed")
            log_panel.log_info(f"Would process {len(tasks_to_run)} task(s)")
            log_panel.log_info("Press 'q' to exit")
            return

        # Start worker for task execution
        log_panel.log_info(f"Processing {len(tasks_to_run)} task(s)...")
        self._start_time = time.time()
        self._worker = self.run_worker(
            self._run_todo_worker,
            thread=True,
            name="todo-worker",
        )

    def _run_todo_worker(self) -> None:
        """Run the todo runner in a worker thread (must be sync)."""
        from ..todo import TodoRunner
        from ..todo_parser import TaskStatus

        try:
            # Track task index via closure
            current_task_index = [0]  # Use list for mutability in closure

            # Create callbacks
            def on_task_start(index: int, total: int, task):
                current_task_index[0] = index
                self._adapter.notify_todo_task_started(
                    task_index=index,
                    total_tasks=total,
                    task_content=task.first_line,
                )
                if self.verbose:
                    self._adapter.on_output(f"[{index}/{total}] Starting: {task.first_line}")

            def on_task_complete(result):
                status = "done" if result.status == TaskStatus.DONE else "failed"
                result_text = result.result if result.status == TaskStatus.DONE else result.error

                self._adapter.notify_todo_task_completed(
                    task_index=current_task_index[0],  # Use index from on_task_start
                    status=status,
                    result=result_text,
                    duration=result.duration,
                )

                if self.verbose:
                    status_icon = "✓" if status == "done" else "✗"
                    self._adapter.on_output(f"  {status_icon} {status.upper()} ({result.duration:.1f}s)")
                    if result_text:
                        self._adapter.on_output(f"    → {result_text[:100]}")

            def on_task_chunk(chunk: str):
                self._adapter.on_chunk(chunk, agent="executor")

            # Create runner
            # Note: Force verbose=False in TUI mode to prevent print() corrupting the UI
            # Verbose info is routed through on_task_chunk callback instead
            self._runner = TodoRunner(
                model=self.model,
                timeout=self.timeout,
                verbose=False,  # Never use verbose in TUI - prints corrupt Textual
                mcp_config=self.mcp_config,
                on_task_start=on_task_start,
                on_task_complete=on_task_complete,
                on_task_chunk=on_task_chunk,
            )

            # Check if stop was requested before runner was created (race condition fix)
            if self._stop_requested:
                self._runner.stop()
                log_panel = self.query_one("#log-panel", LogPanel)
                log_panel.log_warning("Stopped before execution started")
                self._adapter.notify_todo_completed(
                    completed=0,
                    failed=0,
                    total=0,
                    duration=0.0,
                    stopped=True,
                )
                return

            # Emit start event
            from ..todo_parser import get_actionable_tasks
            tasks_to_run = get_actionable_tasks(self.task_file, retry_failed=self.retry_failed)
            planned_total = len(tasks_to_run)  # Store planned count before execution
            tasks_data = [
                {
                    "index": i,
                    "content": task.first_line,
                    "status": "pending",
                }
                for i, task in enumerate(tasks_to_run, 1)
            ]

            self._adapter.notify_todo_started(
                task_file=str(self.task_file.path),
                total_tasks=len(tasks_to_run),
                tasks=tasks_data,
            )

            # Run tasks
            results = self._runner.run_all(
                self.task_file,
                retry_failed=self.retry_failed,
                dry_run=False,
            )

            # Write results file if requested
            if self.results_file and results:
                self._write_results_file(results)

            # Calculate summary
            completed = sum(1 for r in results if r.status == TaskStatus.DONE)
            failed = sum(1 for r in results if r.status == TaskStatus.FAILED)
            duration = time.time() - self._start_time

            # Emit completion event
            # Use planned_total (not len(results)) so UI can show "Stopped 2/5" correctly
            self._adapter.notify_todo_completed(
                completed=completed,
                failed=failed,
                total=planned_total,
                duration=duration,
                stopped=self._stop_requested,
            )

        except Exception as e:
            self._adapter.on_output(f"Error: {str(e)}")
            # Emit error completion
            self._adapter.notify_todo_completed(
                completed=0,
                failed=0,
                total=0,
                duration=time.time() - self._start_time,
                stopped=True,
            )

    def _write_results_file(self, results) -> None:
        """Write detailed results to file."""
        try:
            from ..todo_parser import TaskStatus

            with open(self.results_file, 'w') as f:
                f.write("# Todo Task Results\n\n")
                f.write(f"**File**: {self.task_file.path}\n")
                f.write(f"**Model**: {self.model}\n")
                f.write(f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                f.write("## Summary\n\n")
                completed = sum(1 for r in results if r.status == TaskStatus.DONE)
                failed = sum(1 for r in results if r.status == TaskStatus.FAILED)
                f.write(f"- Total: {len(results)}\n")
                f.write(f"- Completed: {completed}\n")
                f.write(f"- Failed: {failed}\n\n")

                f.write("## Task Details\n\n")
                for i, result in enumerate(results, 1):
                    status = "✓ DONE" if result.status == TaskStatus.DONE else "✗ FAILED"
                    f.write(f"### Task {i}: {result.task.first_line}\n\n")
                    f.write(f"**Status**: {status}\n")
                    f.write(f"**Duration**: {result.duration:.1f}s\n\n")

                    if result.status == TaskStatus.DONE and result.result:
                        f.write(f"**Result**:\n```\n{result.result}\n```\n\n")
                    elif result.error:
                        f.write(f"**Error**:\n```\n{result.error}\n```\n\n")

            self._adapter.on_output(f"Results written to: {self.results_file}")
        except Exception as e:
            self._adapter.on_output(f"Failed to write results file: {str(e)}")

    def action_quit(self) -> None:
        """
        Handle quit action (q key or Ctrl+C).

        IMPORTANT: Do NOT call self.exit() directly.
        Set stop flag and wait for on_todo_completed() to exit gracefully.
        """
        if self.dry_run:
            # In dry run mode, exit immediately
            self.exit()
            return

        if self._stop_requested:
            # Already stopping
            return

        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.log_warning("Stop requested - finishing current task...")

        self._stop_requested = True

        # Tell runner to stop after current task
        if self._runner:
            self._runner.stop()

    def on_todo_started(self, message: messages.TodoStarted) -> None:
        """Handle todo execution started."""
        # Task list already initialized in on_mount
        pass

    def on_todo_task_started(self, message: messages.TodoTaskStarted) -> None:
        """Handle task started event."""
        # Forward to task list panel
        task_list_panel = self.query_one("#task-list-panel", TaskListPanel)
        task_list_panel.on_todo_task_started(message)

    def on_todo_task_completed(self, message: messages.TodoTaskCompleted) -> None:
        """Handle task completed event."""
        # Forward to task list panel
        task_list_panel = self.query_one("#task-list-panel", TaskListPanel)
        task_list_panel.on_todo_task_completed(message)

    def on_todo_completed(self, message: messages.TodoCompleted) -> None:
        """Handle all tasks completed - log summary and exit."""
        log_panel = self.query_one("#log-panel", LogPanel)

        if message.stopped:
            log_panel.log_warning("Execution stopped by user")
        else:
            log_panel.log_success("All tasks completed!")

        log_panel.log_info(
            f"Summary: ✓ {message.completed}  ✗ {message.failed}  "
            f"Total: {message.total}  Duration: {message.duration:.1f}s"
        )

        # Exit after a short delay to let user see final status
        self.set_timer(0.5, self._cleanup_and_exit)

    def _cleanup_and_exit(self) -> None:
        """Cleanup and exit the app."""
        self.exit()

    def on_chunk_received(self, message: messages.ChunkReceived) -> None:
        """Handle streaming chunk from agent."""
        output = self.query_one("#agent-output", AgentOutput)
        output.write_chunk(message.chunk, agent=message.agent)

    def on_output_received(self, message: messages.OutputReceived) -> None:
        """Handle general output message."""
        log_panel = self.query_one("#log-panel", LogPanel)
        if message.level == "error":
            log_panel.log_error(message.message)
        elif message.level == "warning":
            log_panel.log_warning(message.message)
        elif message.level == "success":
            log_panel.log_success(message.message)
        else:
            log_panel.log_info(message.message)

    def action_show_help(self) -> None:
        """Show help screen."""
        self.push_screen(HelpScreen(mode="todo"))

    def action_toggle_logs(self) -> None:
        """Toggle log panel visibility."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.display = not log_panel.display

    def action_toggle_tasks(self) -> None:
        """Toggle task list panel visibility."""
        task_list_panel = self.query_one("#task-list-panel", TaskListPanel)
        task_list_panel.display = not task_list_panel.display

    def action_show_status(self) -> None:
        """Show status summary."""
        log_panel = self.query_one("#log-panel", LogPanel)
        task_list_panel = self.query_one("#task-list-panel", TaskListPanel)

        log_panel.log_info(
            f"Status: ✓ {task_list_panel._completed}  "
            f"✗ {task_list_panel._failed}  "
            f"○ {task_list_panel._total - task_list_panel._completed - task_list_panel._failed}"
        )
