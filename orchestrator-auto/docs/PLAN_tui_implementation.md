# TUI Implementation Plan for orchestrator-auto

**Version:** 2.0
**Date:** 2026-01-16
**Status:** Planning (Revised)

## Executive Summary

This document outlines the implementation plan for an elegant Text User Interface (TUI) for orchestrator-auto. The TUI will provide a professional, hacker-aesthetic dashboard for monitoring and controlling AI agent workflows with real-time streaming output, milestone tracking, logs, and system statistics.

**Key Change in v2.0:** This revision addresses critical architectural gaps identified in review:
1. Engine I/O abstraction must be implemented BEFORE any widget work
2. Three distinct TUI modes must be supported (single session, queue, directory watch)
3. Queue and watch controllers must be extracted as reusable library modules
4. Thread-safety and lifecycle management require explicit design

---

## 1. Scope: Three TUI Modes

The TUI must support three distinct operational modes, matching existing CLI capabilities:

| Mode | CLI Command | TUI Behavior |
|------|-------------|--------------|
| **Single Session** | `orchestrator start -f "..." --tui` | Dashboard for one workflow |
| **Explicit Queue** | `orchestrator start --queue p1.md p2.md --tui` | Queue panel + session detail |
| **Directory Watch** | `orchestrator watch .plans --tui` | Watcher panel + queue + session |

### 1.1 Mode Comparison

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SINGLE SESSION MODE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  [Status] [Milestones] [Agent Output]                                       │
│  [Logs]                                                                      │
│  User input for discovery/planning/blockers                                 │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                        QUEUE MODE                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  [Queue List: pending/running/done] │ [Current Session Dashboard]           │
│  Controls: skip, pause queue        │ [Agent Output] [Logs]                 │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                        DIRECTORY WATCH MODE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  [Watcher Status: dir, interval]    │                                       │
│  [File Queue: detected files]       │ [Current Session Dashboard]           │
│  [Last Result: success/quarantine]  │ [Agent Output] [Logs]                 │
│  Controls: start/stop, skip file    │                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Library Recommendation

### 2.1 Library Comparison

| Library | Stars | Last Updated | Async Support | Rich Widgets | Learning Curve | Active Maintenance |
|---------|-------|--------------|---------------|--------------|----------------|-------------------|
| **Textual** | 24k+ | Weekly | Native async | Extensive | Medium | Excellent (Textualize team) |
| **Rich** | 48k+ | Weekly | Limited | Display only | Low | Excellent (same team) |
| **urwid** | 2.7k+ | Monthly | Via asyncio | Basic | High | Moderate |
| **blessed** | 1.2k+ | Bi-monthly | Manual | Minimal | Medium | Moderate |
| **Prompt Toolkit** | 9k+ | Monthly | Native async | Input-focused | Medium | Good |

### 2.2 Recommendation: Textual

**Primary Choice: Textual v0.80+**

Reasons:
1. **Native async/await** - Perfect for streaming agent responses
2. **CSS-like styling** - Easy to achieve the hacker aesthetic with dark themes and neon accents
3. **Rich widget library** - DataTable, Tree, Log, TextArea, ProgressBar, Footer, Header
4. **Same ecosystem as Rich** - Seamless integration with Rich formatting
5. **Active development** - Backed by Textualize, weekly releases, excellent documentation
6. **Terminal size handling** - Built-in responsive layout system with CSS grid/flexbox
7. **Thread-safe messaging** - `post_message()` for cross-thread communication
8. **Worker pattern** - Built-in `run_worker()` for background tasks

**Secondary Integration: Rich**

Use Rich for:
- Console output formatting outside TUI (fallback mode)
- Markdown/syntax highlighting within Textual widgets
- Export functionality

---

## 3. Current Architecture Analysis

### 3.1 Critical Integration Points

```
orchestrator-auto/
  orchestrator_auto/
    cli.py           # Entry point - contains queue/watch logic (MUST EXTRACT)
    engine.py        # Orchestrator class - terminal-bound I/O (MUST ABSTRACT)
    output.py        # StreamingIndicator - chunks not exposed (MUST FIX)
    state.py         # StateMachine - no change callbacks (SHOULD ADD)
    agents.py        # BaseAgent.send_message() - streaming via on_chunk
    db.py            # Session/queue data - read-only for TUI
    input_handler.py # prompt_with_paste_support() - hardcoded (MUST INJECT)
```

### 3.2 Current Problems (Why Engine Abstraction is Required)

#### Problem 1: Input is Terminal-Bound

```python
# engine.py:687 - Direct terminal call, not injectable
display_text, user_input = prompt_with_paste_support("\nYou: ")
```

The TUI cannot supply input without modifying this. Need an `InputProvider` abstraction.

#### Problem 2: Streaming Chunks Are Lost

```python
# engine.py:655-656 - When show_activity=False, chunks go nowhere
on_chunk = self._create_heartbeat_callback(
    indicator.on_chunk if indicator else None,  # None for TUI!
    interval_seconds=60
)
```

With `show_activity=False` (which TUI would set), streaming data is lost. Need an `on_chunk` callback on the Orchestrator.

#### Problem 3: No State Change Events

State transitions happen internally in `StateMachine`. The TUI has no way to know when phase/milestone changes without polling or parsing output.

#### Problem 4: Agents Are Closed on Pause

```python
# engine.py:1380-1385
def _cleanup(self) -> None:
    if self.planner:
        self.planner.close()
    if self.executor:
        self.executor.close()
```

After pause, agent objects are unusable. TUI cannot reuse an Orchestrator instance after pause.

#### Problem 5: Queue/Watch Logic Embedded in CLI

```python
# cli.py:740 - _run_queue() is not reusable
# cli.py:3215 - watch() command has all logic inline
```

TUI would have to duplicate this logic or call CLI functions inappropriately.

---

## 4. Phase 0: Engine I/O Abstraction (GATING PHASE)

**This phase MUST be completed before any widget work begins.**

### 4.1 Input Provider Abstraction

```python
# orchestrator_auto/io/input_provider.py

from abc import ABC, abstractmethod
from typing import Tuple, Optional

class InputProvider(ABC):
    """Abstract input provider for orchestrator."""

    @abstractmethod
    def prompt(self, prompt_text: str) -> Tuple[str, str]:
        """
        Get user input.

        Args:
            prompt_text: Text to display as prompt

        Returns:
            Tuple of (display_text, actual_input)
            display_text may be truncated for long pastes
        """
        pass

    @abstractmethod
    def prompt_choice(self, prompt_text: str, choices: list[str]) -> str:
        """Get user choice from options."""
        pass


class CLIInputProvider(InputProvider):
    """Terminal-based input using prompt_toolkit."""

    def prompt(self, prompt_text: str) -> Tuple[str, str]:
        from ..input_handler import prompt_with_paste_support
        return prompt_with_paste_support(prompt_text)

    def prompt_choice(self, prompt_text: str, choices: list[str]) -> str:
        import click
        return click.prompt(prompt_text, type=click.Choice(choices))


class TUIInputProvider(InputProvider):
    """TUI-based input that signals the app for input."""

    def __init__(self, app: "OrchestratorTUI"):
        self.app = app
        self._pending_input = None
        self._input_event = asyncio.Event()

    def prompt(self, prompt_text: str) -> Tuple[str, str]:
        """Block until TUI provides input."""
        # Signal TUI to show input widget
        self.app.post_message(InputRequestedMessage(prompt_text))

        # Wait for input (blocking - runs in worker thread)
        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self._input_event.wait())
        self._input_event.clear()

        result = self._pending_input
        self._pending_input = None
        return (result, result)

    def submit_input(self, text: str) -> None:
        """Called by TUI when user submits input."""
        self._pending_input = text
        self._input_event.set()
```

### 4.2 Streaming Callback (on_chunk)

```python
# Modify Orchestrator.__init__ to accept on_chunk callback

class Orchestrator:
    def __init__(
        self,
        ...
        on_output: Optional[Callable[[str], None]] = None,
        on_chunk: Optional[Callable[[str], None]] = None,  # NEW
        on_state_change: Optional[Callable[[WorkflowState], None]] = None,  # NEW
        input_provider: Optional[InputProvider] = None,  # NEW
        ...
    ):
        self.on_output = on_output or print
        self.on_chunk = on_chunk  # NEW: For streaming to TUI
        self.on_state_change = on_state_change  # NEW: For state updates
        self.input_provider = input_provider or CLIInputProvider()  # NEW
```

### 4.3 Modified _send_with_activity

```python
def _send_with_activity(
    self,
    agent,
    message: str,
    activity_label: str = "Working"
) -> str:
    indicator = self._create_activity_indicator()

    if indicator:
        self._output(f"  {activity_label}... ")

    self._touch_heartbeat()

    # Combine indicator callback with external on_chunk
    def combined_chunk_handler(chunk: str):
        # Activity indicator (if enabled)
        if indicator:
            indicator.on_chunk(chunk)
        # External callback (for TUI)
        if self.on_chunk:
            self.on_chunk(chunk)

    on_chunk = self._create_heartbeat_callback(
        combined_chunk_handler,  # Always call, not just when indicator exists
        interval_seconds=60
    )

    response = agent.send_message(message, on_chunk=on_chunk)

    self._touch_heartbeat()

    if indicator:
        indicator.finish()

    return response
```

### 4.4 State Change Notifications

```python
# In StateMachine.transition() or Orchestrator state changes

def _notify_state_change(self) -> None:
    """Notify listeners of state change."""
    if self.on_state_change:
        self.on_state_change(self.state)

# Call after each transition:
success, self.state, error = self.state_machine.transition(...)
self._notify_state_change()
```

### 4.5 Replace Hardcoded Input Calls

```python
# Before (engine.py:687)
display_text, user_input = prompt_with_paste_support("\nYou: ")

# After
display_text, user_input = self.input_provider.prompt("\nYou: ")
```

### 4.6 Deliverables for Phase 0

| File | Change |
|------|--------|
| `io/__init__.py` | New package |
| `io/input_provider.py` | InputProvider ABC + CLI/TUI implementations |
| `io/events.py` | Event types for state/chunk/input |
| `engine.py` | Add on_chunk, on_state_change, input_provider params |
| `engine.py` | Replace all prompt_with_paste_support calls |
| `engine.py` | Modify _send_with_activity to always call on_chunk |

---

## 5. Phase 1: Controller Extraction

Extract queue and watch logic from cli.py into reusable library modules.

### 5.1 Queue Controller

```python
# orchestrator_auto/controllers/queue_controller.py

from dataclasses import dataclass
from typing import Optional, Callable, Iterator
from enum import Enum

class QueueEvent(Enum):
    STARTED = "started"
    ITEM_STARTED = "item_started"
    ITEM_COMPLETED = "item_completed"
    ITEM_FAILED = "item_failed"
    ITEM_PAUSED = "item_paused"
    COMPLETED = "completed"
    HALTED = "halted"

@dataclass
class QueueItem:
    id: str
    position: int
    plan_path: str
    feature_description: str
    status: str  # pending, running, completed, failed, paused
    session_id: Optional[str] = None

@dataclass
class QueueState:
    items: list[QueueItem]
    current_index: int
    is_running: bool
    completed_count: int
    failed_count: int
    paused_count: int


class QueueController:
    """
    Reusable queue runner for sequential plan execution.

    Can be used by both CLI and TUI.
    """

    def __init__(
        self,
        project_id: str,
        db_path: Optional[str] = None,
        on_event: Optional[Callable[[QueueEvent, dict], None]] = None,
        on_output: Optional[Callable[[str], None]] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
        on_state_change: Optional[Callable, None]] = None,
        input_provider: Optional["InputProvider"] = None,
        planner_model: Optional[str] = None,
        executor_model: Optional[str] = None,
        auto_commit: bool = False,
        telegram_notifier: Optional["TelegramNotifier"] = None,
    ):
        self.project_id = project_id
        self.db_path = db_path
        self.on_event = on_event or (lambda e, d: None)
        self.on_output = on_output
        self.on_chunk = on_chunk
        self.on_state_change = on_state_change
        self.input_provider = input_provider
        self.planner_model = planner_model
        self.executor_model = executor_model
        self.auto_commit = auto_commit
        self.telegram_notifier = telegram_notifier

        self._current_orchestrator: Optional[Orchestrator] = None
        self._should_stop = False

    def get_state(self) -> QueueState:
        """Get current queue state."""
        items = db.list_queue_items(self.project_id, self.db_path)
        return QueueState(
            items=[QueueItem(**item) for item in items],
            current_index=self._find_current_index(items),
            is_running=self._current_orchestrator is not None,
            completed_count=sum(1 for i in items if i["status"] == "completed"),
            failed_count=sum(1 for i in items if i["status"] == "failed"),
            paused_count=sum(1 for i in items if i["status"] == "paused"),
        )

    def run(self) -> None:
        """
        Run queue to completion or until halted.

        This is a blocking call - run in a worker thread for TUI.
        """
        self.on_event(QueueEvent.STARTED, {"item_count": len(self.get_state().items)})

        while not self._should_stop:
            action, next_item = self._reconcile_head()

            if action == "empty":
                break
            if action in ("halt_paused", "halt_active", "halt_orphaned"):
                self.on_event(QueueEvent.HALTED, {"reason": action})
                break
            if action != "ready":
                break

            self._run_item(next_item)

        self.on_event(QueueEvent.COMPLETED, self.get_state().__dict__)

    def stop(self) -> None:
        """Signal queue to stop after current item."""
        self._should_stop = True

    def skip_current(self) -> None:
        """Skip the current/next pending item."""
        # Mark as skipped in DB
        pass

    def _run_item(self, item: dict) -> None:
        """Run a single queue item."""
        self.on_event(QueueEvent.ITEM_STARTED, item)

        try:
            orchestrator = Orchestrator(
                feature_description=item["feature_description"],
                plan_path=item["plan_path"],
                on_output=self.on_output,
                on_chunk=self.on_chunk,
                on_state_change=self.on_state_change,
                input_provider=self.input_provider,
                planner_model=self.planner_model,
                executor_model=self.executor_model,
            )
            self._current_orchestrator = orchestrator
            orchestrator.start()

            self.on_event(QueueEvent.ITEM_COMPLETED, item)

        except Exception as e:
            self.on_event(QueueEvent.ITEM_FAILED, {**item, "error": str(e)})

        finally:
            self._current_orchestrator = None
```

### 5.2 Watch Controller

```python
# orchestrator_auto/controllers/watch_controller.py

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable
from enum import Enum
import time

class WatchEvent(Enum):
    STARTED = "started"
    FILE_DETECTED = "file_detected"
    FILE_PROCESSING = "file_processing"
    FILE_COMPLETED = "file_completed"
    FILE_QUARANTINED = "file_quarantined"
    FILE_SKIPPED = "file_skipped"
    STOPPED = "stopped"

@dataclass
class WatchState:
    directory: Path
    poll_interval: int
    is_running: bool
    auto_convert: bool
    pending_files: list[Path]
    current_file: Optional[Path]
    last_result: Optional[str]  # "success", "failed", "quarantined"
    processed_count: int
    quarantined_count: int


class WatchController:
    """
    Directory watcher for .plans folder processing.

    Handles:
    - File detection (oldest-first)
    - Auto-conversion of non-.md files
    - Quarantine on failure
    - Rename on success
    """

    def __init__(
        self,
        plans_dir: Path,
        poll_interval: int = 10,
        auto_convert: bool = True,
        on_event: Optional[Callable[[WatchEvent, dict], None]] = None,
        queue_controller: Optional[QueueController] = None,
    ):
        self.plans_dir = plans_dir
        self.poll_interval = poll_interval
        self.auto_convert = auto_convert
        self.on_event = on_event or (lambda e, d: None)
        self.queue_controller = queue_controller

        self._is_running = False
        self._current_file: Optional[Path] = None
        self._processed_count = 0
        self._quarantined_count = 0

    def get_state(self) -> WatchState:
        """Get current watcher state."""
        return WatchState(
            directory=self.plans_dir,
            poll_interval=self.poll_interval,
            is_running=self._is_running,
            auto_convert=self.auto_convert,
            pending_files=self._scan_pending(),
            current_file=self._current_file,
            last_result=None,  # Track separately
            processed_count=self._processed_count,
            quarantined_count=self._quarantined_count,
        )

    def start(self) -> None:
        """
        Start watching directory.

        This is a blocking call - run in a worker thread for TUI.
        """
        self._is_running = True
        self.on_event(WatchEvent.STARTED, {"directory": str(self.plans_dir)})

        while self._is_running:
            pending = self._scan_pending()

            if pending:
                self._process_file(pending[0])
            else:
                time.sleep(self.poll_interval)

        self.on_event(WatchEvent.STOPPED, {})

    def stop(self) -> None:
        """Stop the watcher."""
        self._is_running = False

    def skip_file(self, path: Path) -> None:
        """Skip a pending file (rename to .skipped)."""
        new_path = path.with_suffix(path.suffix + ".skipped")
        path.rename(new_path)
        self.on_event(WatchEvent.FILE_SKIPPED, {"path": str(path)})

    def _scan_pending(self) -> list[Path]:
        """Scan for pending plan files, oldest first."""
        candidates = []
        for p in self.plans_dir.glob("*.md"):
            if self._is_watch_candidate(p):
                candidates.append(p)
        # Sort by modification time (oldest first)
        return sorted(candidates, key=lambda p: p.stat().st_mtime)

    def _is_watch_candidate(self, path: Path) -> bool:
        """Check if file should be processed."""
        name = path.name.lower()
        # Skip already-processed files
        if any(name.endswith(s) for s in [".done.md", ".failed.md", ".skipped.md"]):
            return False
        return True

    def _process_file(self, path: Path) -> None:
        """Process a single plan file."""
        self._current_file = path
        self.on_event(WatchEvent.FILE_PROCESSING, {"path": str(path)})

        try:
            # Add to queue and run
            # ... implementation details ...
            self._processed_count += 1
            self.on_event(WatchEvent.FILE_COMPLETED, {"path": str(path)})

        except Exception as e:
            self._quarantine_file(path, str(e))

        finally:
            self._current_file = None

    def _quarantine_file(self, path: Path, error: str) -> None:
        """Move failed file to quarantine."""
        new_path = path.with_suffix(".failed.md")
        path.rename(new_path)
        self._quarantined_count += 1
        self.on_event(WatchEvent.FILE_QUARANTINED, {
            "path": str(path),
            "error": error
        })
```

### 5.3 Deliverables for Phase 1

| File | Change |
|------|--------|
| `controllers/__init__.py` | New package |
| `controllers/queue_controller.py` | QueueController class |
| `controllers/watch_controller.py` | WatchController class |
| `cli.py` | Refactor to use controllers (maintain backward compatibility) |

---

## 6. Lifecycle and Pause/Resume Design

### 6.1 The Problem

The current system assumes pause/resume happens via separate CLI invocations:

```bash
# Session pauses (blocks for input)
# User closes terminal
# Later:
orchestrator resume <session-id>
```

In a long-running TUI, we need different semantics.

### 6.2 Design Decision: Treat Pause as Terminal

**Recommended approach:** When a session pauses (blocker, human input needed), the Orchestrator instance terminates normally. To resume:

1. Create a NEW Orchestrator instance with `session_id=...`
2. Call `.resume(answer)` or `.start()` which detects the paused state

This mirrors CLI semantics and avoids issues with reusing closed agent instances.

### 6.3 TUI Pause/Resume Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR RUNNING                                                         │
│                                                                              │
│  User clicks Pause OR session hits blocker                                  │
│         │                                                                    │
│         ▼                                                                    │
│  Orchestrator.pause() called → _cleanup() runs → agents closed              │
│         │                                                                    │
│         ▼                                                                    │
│  TUI shows "PAUSED" state, input widget for answer                          │
│         │                                                                    │
│         ▼                                                                    │
│  User provides answer and clicks Resume                                     │
│         │                                                                    │
│         ▼                                                                    │
│  TUI creates NEW Orchestrator(session_id=...) → start() or resume(answer)  │
│         │                                                                    │
│         ▼                                                                    │
│  New agents created, workflow continues                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.4 Implementation

```python
class OrchestratorTUI(App):

    def __init__(self):
        super().__init__()
        self._orchestrator: Optional[Orchestrator] = None
        self._worker_task: Optional[asyncio.Task] = None

    async def _run_orchestrator(self, orchestrator: Orchestrator) -> None:
        """Run orchestrator in background worker."""
        self._orchestrator = orchestrator
        try:
            await asyncio.to_thread(orchestrator.start)
        except Exception as e:
            self.post_message(OrchestratorErrorMessage(str(e)))
        finally:
            self._orchestrator = None
            # Orchestrator has cleaned up, agents are closed
            self.post_message(OrchestratorStoppedMessage())

    def action_pause(self) -> None:
        """Request pause - orchestrator will stop at next safe point."""
        if self._orchestrator:
            # Signal pause (orchestrator checks this flag)
            self._orchestrator.request_pause()
            self.notify("Pause requested...")

    async def action_resume(self, answer: Optional[str] = None) -> None:
        """Resume paused session with optional answer."""
        session_id = self.current_session_id
        if not session_id:
            return

        # Create NEW orchestrator instance for resume
        orchestrator = Orchestrator(
            session_id=session_id,
            on_output=self._adapter.on_output,
            on_chunk=self._adapter.on_chunk,
            on_state_change=self._adapter.on_state_change,
            input_provider=TUIInputProvider(self),
        )

        # Resume with answer if provided
        if answer:
            orchestrator.set_blocker_response(answer)

        # Run in worker
        self.run_worker(self._run_orchestrator(orchestrator))
```

---

## 7. Thread-Safety Requirements

### 7.1 Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MAIN THREAD                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Textual Event Loop                                                  │   │
│  │  - Widget rendering                                                  │   │
│  │  - User input handling                                               │   │
│  │  - Message processing                                                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         ▲                                                                    │
│         │ post_message() - THREAD-SAFE                                      │
│         │                                                                    │
│  ┌──────┴──────────────────────────────────────────────────────────────┐   │
│  │  Worker Thread (asyncio.to_thread)                                   │   │
│  │  - Orchestrator.start()                                              │   │
│  │  - Agent API calls                                                   │   │
│  │  - on_chunk callbacks                                                │   │
│  │  - on_state_change callbacks                                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Rules

1. **Orchestrator runs in worker thread** via `asyncio.to_thread()` or `run_worker()`
2. **Callbacks (on_chunk, on_state_change) execute in worker thread**
3. **Widget updates MUST use `app.post_message()`** - never update widgets directly from callbacks
4. **Input from TUI to worker** uses thread-safe primitives (Event, Queue)

### 7.3 TUI Output Adapter

```python
# orchestrator_auto/tui/adapter.py

from textual.message import Message

class ChunkMessage(Message):
    def __init__(self, chunk: str):
        super().__init__()
        self.chunk = chunk

class StateChangeMessage(Message):
    def __init__(self, state: WorkflowState):
        super().__init__()
        self.state = state

class OutputMessage(Message):
    def __init__(self, text: str):
        super().__init__()
        self.text = text


class TUIOutputAdapter:
    """
    Bridges Orchestrator callbacks to TUI messages.

    All methods are called from worker thread - must use post_message().
    """

    def __init__(self, app: "OrchestratorTUI"):
        self.app = app
        self._token_count = 0
        self._api_calls = 0

    def on_output(self, message: str) -> None:
        """Handle orchestrator output - RUNS IN WORKER THREAD."""
        # Thread-safe: post_message marshals to main thread
        self.app.post_message(OutputMessage(message))

    def on_chunk(self, chunk: str) -> None:
        """Handle streaming chunk - RUNS IN WORKER THREAD."""
        self._token_count += len(chunk.split())
        # Thread-safe
        self.app.post_message(ChunkMessage(chunk))

    def on_state_change(self, state: "WorkflowState") -> None:
        """Handle state transition - RUNS IN WORKER THREAD."""
        # Thread-safe
        self.app.post_message(StateChangeMessage(state))
```

### 7.4 Message Handlers in TUI

```python
class OrchestratorTUI(App):

    def on_chunk_message(self, message: ChunkMessage) -> None:
        """Handle chunk - RUNS IN MAIN THREAD."""
        # Safe to update widgets here
        self.query_one("#agent-output", AgentOutput).write_chunk(message.chunk)

    def on_state_change_message(self, message: StateChangeMessage) -> None:
        """Handle state change - RUNS IN MAIN THREAD."""
        state = message.state
        status_panel = self.query_one("#status", StatusPanel)
        status_panel.phase = state.phase
        status_panel.status = state.status
        # ... etc
```

---

## 8. TUI Layout Design

### 8.1 Single Session Mode (80x24 Minimum)

```
+==============================================================================+
|  ORCHESTRATOR-AUTO v0.14.0                    [Session: a1b2c3d4] [14:32:05] |
+==============================================================================+
|                                                                              |
| +-- STATUS ----------------+  +-- MILESTONES --------------------------+    |
| | Phase: EXECUTION         |  | [x] M1: Database schema setup          |    |
| | Status: ACTIVE           |  | [x] M2: API endpoints implementation   |    |
| | Feature: User auth       |  | [>] M3: Authentication middleware      |    |
| | Models: opus/sonnet      |  | [ ] M4: Testing and validation         |    |
| +---- STATS ---------------+  +----------------------------------------+    |
| | API Calls: 47            |                                               |
| | Tokens: 12,847           |                                               |
| | Elapsed: 00:08:23        |                                               |
| +--------------------------+                                               |
|                                                                              |
| +-- AGENT OUTPUT ---------------------------------------------------------+ |
| | > Executor implementing M3...                                           | |
| | > Writing auth middleware to src/middleware/auth.py                     | |
| | > Added JWT validation logic                                            | |
| | > Running tests: pytest tests/test_auth.py                              | |
| |   [streaming] ...checking token expiration...                           | |
| +-------------------------------------------------------------------------+ |
|                                                                              |
| +-- LOGS (tail) ----------------------------------------------------------+ |
| | [14:31:42] Planner approved M2                                          | |
| | [14:31:45] Starting M3: Authentication middleware                       | |
| | [14:32:01] Executor: Reading existing auth patterns                     | |
| +-------------------------------------------------------------------------+ |
|                                                                              |
+==============================================================================+
| [Q]uit  [P]ause  [R]esume  [L]ogs  [S]tatus  [?]Help        Status: RUNNING |
+==============================================================================+
```

### 8.2 Queue Mode Layout

```
+==============================================================================+
|  ORCHESTRATOR-AUTO v0.14.0  [QUEUE MODE]                         [14:32:05] |
+==============================================================================+
|                                                                              |
| +-- QUEUE ----------------------+  +-- CURRENT SESSION -------------------+ |
| | [x] 1. setup-database.md     |  | Session: a1b2c3d4                     | |
| | [x] 2. add-auth.md           |  | Phase: EXECUTION  Status: ACTIVE     | |
| | [>] 3. api-endpoints.md      |  | Feature: Add REST API endpoints      | |
| | [ ] 4. tests.md              |  | Milestone: 2/4                        | |
| | [ ] 5. deploy-config.md      |  +---------------------------------------+ |
| +------------------------------+                                            |
| | Completed: 2  Failed: 0      |  +-- AGENT OUTPUT -----------------------+ |
| | Remaining: 3                 |  | > Creating endpoint handlers...       | |
| +------------------------------+  | > Added GET /users endpoint           | |
|                                   | > Added POST /users endpoint          | |
|                                   | > Writing tests...                    | |
|                                   +---------------------------------------+ |
|                                                                              |
| +-- LOGS (tail) ----------------------------------------------------------+ |
| | [14:30:12] Queue started: 5 items                                       | |
| | [14:30:15] Item 1 completed: setup-database.md                          | |
| | [14:31:02] Item 2 completed: add-auth.md                                | |
| | [14:31:05] Item 3 started: api-endpoints.md                             | |
| +-------------------------------------------------------------------------+ |
|                                                                              |
+==============================================================================+
| [Q]uit  [S]kip  [P]ause Queue  [?]Help                   Queue: 3/5 RUNNING |
+==============================================================================+
```

### 8.3 Directory Watch Mode Layout

```
+==============================================================================+
|  ORCHESTRATOR-AUTO v0.14.0  [WATCH MODE]                         [14:32:05] |
+==============================================================================+
|                                                                              |
| +-- WATCHER --------------------+  +-- CURRENT SESSION -------------------+ |
| | Directory: ./plans/          |  | Session: a1b2c3d4                     | |
| | Poll: 10s  Auto-convert: ON  |  | Phase: EXECUTION  Status: ACTIVE     | |
| | Status: WATCHING             |  | Feature: Add user endpoints          | |
| +------------------------------+  | Milestone: 1/3                        | |
| +-- PENDING FILES --------------+  +---------------------------------------+ |
| | [>] 001_users.md (running)   |                                          |
| | [ ] 002_products.md          |  +-- AGENT OUTPUT -----------------------+ |
| | [ ] 003_orders.md            |  | > Creating user model...              | |
| +------------------------------+  | > Added validation logic              | |
| +-- LAST RESULT ----------------+  | > Writing migration...               | |
| | 000_init.md -> .done.md      |  +---------------------------------------+ |
| | Completed in 2m 34s          |                                          |
| +------------------------------+                                            |
|                                                                              |
| +-- LOGS (tail) ----------------------------------------------------------+ |
| | [14:28:00] Watcher started: ./plans/                                    | |
| | [14:28:05] Detected: 000_init.md                                        | |
| | [14:30:39] Completed: 000_init.md -> 000_init.done.md                   | |
| | [14:30:42] Detected: 001_users.md                                       | |
| +-------------------------------------------------------------------------+ |
|                                                                              |
+==============================================================================+
| [Q]uit  [S]kip File  [T]oggle Watch  [?]Help             Watch: ON  Files: 3|
+==============================================================================+
```

### 8.4 Responsive Layouts

**Large Terminal (120+ cols):** 3-column layout with full panels

**Medium Terminal (80-119 cols):** 2-column, queue/watch panel collapses

**Small Terminal (80x24):** Single column, tabbed navigation between panels

---

## 9. Color Scheme (Hacker Aesthetic)

```css
/* TUI CSS Theme - Matrix/Cyberpunk Style */

Screen {
    background: #0a0a0a;  /* Near black */
}

.header {
    background: #1a1a2e;  /* Dark blue-black */
    color: #00ff41;       /* Matrix green */
    text-style: bold;
}

.status-panel {
    border: tall #00ff41; /* Green border */
    background: #0d0d0d;
}

.phase-active {
    color: #00ff41;       /* Green - active */
}

.phase-paused {
    color: #ffcc00;       /* Amber - paused */
}

.phase-error {
    color: #ff0040;       /* Neon red - error */
}

.milestone-done {
    color: #00ff41;       /* Green checkmark */
}

.milestone-current {
    color: #00d4ff;       /* Cyan - in progress */
    text-style: bold;
}

.milestone-pending {
    color: #666666;       /* Gray - pending */
}

.agent-output {
    background: #0a0a0a;
    color: #e0e0e0;       /* Light gray text */
    border: round #00d4ff; /* Cyan border */
}

.streaming-text {
    color: #00d4ff;       /* Cyan for streaming */
}

.queue-panel {
    border: tall #ff00ff; /* Magenta for queue */
    background: #0d0d0d;
}

.watch-panel {
    border: tall #ffcc00; /* Amber for watch */
    background: #0d0d0d;
}

.log-panel {
    background: #050505;
    color: #888888;       /* Muted gray */
    border: round #333333;
}

.stats-value {
    color: #ff00ff;       /* Magenta for numbers */
}

.footer {
    background: #1a1a2e;
    color: #00ff41;
}
```

---

## 10. Module Structure

```
orchestrator_auto/
    __init__.py
    cli.py                    # Modified: --tui flags, uses controllers
    engine.py                 # Modified: I/O abstraction
    io/                       # NEW: I/O abstraction layer
        __init__.py
        input_provider.py     # InputProvider ABC + implementations
        events.py             # Event types
    controllers/              # NEW: Extracted business logic
        __init__.py
        queue_controller.py   # QueueController
        watch_controller.py   # WatchController
    tui/                      # NEW: TUI package
        __init__.py           # Package exports
        app.py                # Main OrchestratorTUI class
        adapter.py            # TUIOutputAdapter
        modes/
            __init__.py
            single.py         # Single session mode
            queue.py          # Queue mode
            watch.py          # Watch mode
        screens/
            __init__.py
            dashboard.py      # Main dashboard screen
            logs.py           # Full-screen logs viewer
            help.py           # Help/keybindings screen
            session_picker.py # Session selection screen
        widgets/
            __init__.py
            status_panel.py   # Status/stats display
            milestone_list.py # Milestone progress list
            agent_output.py   # Streaming agent output panel
            log_panel.py      # Log tail display
            queue_panel.py    # Queue list display
            watch_panel.py    # Watcher status display
            input_modal.py    # Input dialog for blockers
        styles/
            __init__.py
            theme.tcss        # Main theme CSS
            colors.py         # Color constants
        bindings.py           # Keyboard bindings
tests/
    test_io_providers.py      # Input provider tests
    test_controllers.py       # Controller tests
    test_tui_widgets.py       # Widget unit tests
    test_tui_integration.py   # Integration tests
```

---

## 11. CLI Integration

### 11.1 Updated Start Command

```python
@cli.command()
@click.option('-f', '--feature', help='Feature description')
@click.option('--plan', 'plan_path', type=click.Path(exists=True),
              help='Path to existing plan file')
@click.option('--queue', 'queue_plans', multiple=True, type=click.Path(exists=True),
              help='Queue mode: plan files to run sequentially')
@click.option('-pm', '--planner-model', help='Planner model')
@click.option('-em', '--executor-model', help='Executor model')
@click.option('--auto-commit', is_flag=True, help='Auto-commit on completion')
@click.option('--tui', is_flag=True, default=False, help='Launch TUI dashboard')
@click.option('--debug', is_flag=True, help='Enable debug logging')
@click.pass_context
def start(ctx, feature, plan_path, queue_plans, planner_model,
          executor_model, auto_commit, tui, debug):
    """Start a new orchestration workflow."""

    if tui:
        if queue_plans:
            _start_queue_tui(queue_plans, planner_model, executor_model, auto_commit)
        elif feature:
            _start_single_tui(feature, plan_path, planner_model, executor_model, auto_commit)
        else:
            click.secho("Error: --tui requires -f or --queue", fg="red")
            sys.exit(1)
    else:
        # Existing CLI behavior
        ...
```

### 11.2 Updated Watch Command

```python
@cli.command()
@click.argument('plans_dir', type=click.Path(exists=True, file_okay=False))
@click.option('--poll-interval', default=10, help='Seconds between directory scans')
@click.option('--no-convert', is_flag=True, help='Disable auto-conversion')
@click.option('--auto-commit', is_flag=True, help='Auto-commit completed sessions')
@click.option('--tui', is_flag=True, default=False, help='Launch TUI dashboard')
@click.option('-pm', '--planner-model', help='Planner model')
@click.option('-em', '--executor-model', help='Executor model')
def watch(plans_dir, poll_interval, no_convert, auto_commit, tui,
          planner_model, executor_model):
    """Watch a directory for plan files and process them."""

    if tui:
        _start_watch_tui(
            plans_dir=plans_dir,
            poll_interval=poll_interval,
            auto_convert=not no_convert,
            auto_commit=auto_commit,
            planner_model=planner_model,
            executor_model=executor_model,
        )
    else:
        # Existing CLI behavior using WatchController
        controller = WatchController(
            plans_dir=Path(plans_dir),
            poll_interval=poll_interval,
            auto_convert=not no_convert,
            on_event=_cli_watch_event_handler,
        )
        controller.start()
```

---

## 12. Implementation Phases (Revised)

### Phase 0: Engine I/O Abstraction (GATING)

**Must complete before any TUI work.**

| Task | Description |
|------|-------------|
| Create `io/` package | InputProvider ABC, CLIInputProvider |
| Add `on_chunk` to Orchestrator | Always emit chunks, not just when indicator exists |
| Add `on_state_change` to Orchestrator | Emit on phase/milestone transitions |
| Add `input_provider` to Orchestrator | Inject input handling |
| Refactor engine.py | Replace all `prompt_with_paste_support()` calls |
| Tests | Unit tests for new I/O layer |

**Deliverables:** Engine can run headlessly with injected I/O

### Phase 1: Controller Extraction

| Task | Description |
|------|-------------|
| Create `controllers/` package | Package structure |
| Extract QueueController | From cli.py `_run_queue()` |
| Extract WatchController | From cli.py `watch()` |
| Add event callbacks | on_event for queue/watch state changes |
| Refactor cli.py | Use controllers, maintain compatibility |
| Tests | Controller unit tests |

**Deliverables:** Queue/watch logic reusable by CLI and TUI

### Phase 2: Core TUI Scaffold

| Task | Description |
|------|-------------|
| Add Textual dependency | pyproject.toml `[tui]` extra |
| Create `tui/` package | Package structure |
| Implement OrchestratorTUI base | App class, worker pattern |
| Implement TUIOutputAdapter | Thread-safe message posting |
| Implement TUIInputProvider | Blocking input from TUI widgets |
| Create theme.tcss | Dark hacker aesthetic |
| Add --tui flag to CLI | start and watch commands |

**Deliverables:** TUI launches, shows static dashboard

### Phase 3: Single Session Mode

| Task | Description |
|------|-------------|
| StatusPanel widget | Phase, status, models, stats |
| MilestoneList widget | Progress tracking |
| AgentOutput widget | Streaming with auto-scroll |
| LogPanel widget | Tail display |
| InputModal widget | For discovery/blockers |
| Keyboard bindings | Quit, pause, resume, help |
| Integration | Wire up to Orchestrator callbacks |

**Deliverables:** Full single-session TUI workflow

### Phase 4: Queue Mode

| Task | Description |
|------|-------------|
| QueuePanel widget | List of items with status |
| Queue mode screen | Layout with queue + session detail |
| Wire to QueueController | Event handling |
| Queue controls | Skip, pause queue |
| Queue status footer | Running/paused, progress |

**Deliverables:** Queue mode TUI with live updates

### Phase 5: Watch Mode

| Task | Description |
|------|-------------|
| WatchPanel widget | Directory, interval, pending files |
| Watch mode screen | Layout with watcher + queue + session |
| Wire to WatchController | Event handling |
| Watch controls | Start/stop, skip file |
| File status display | Pending, current, last result |

**Deliverables:** Watch mode TUI with directory monitoring

### Phase 6: Polish and Testing

| Task | Description |
|------|-------------|
| Responsive layouts | Breakpoints for 80/120+ cols |
| Help screen | Keybinding reference |
| Session picker | For resume command |
| Visual polish | Animations, transitions |
| Snapshot tests | Visual regression |
| Integration tests | Full workflow tests |
| Documentation | README, examples |

**Deliverables:** Production-ready TUI

---

## 13. Success Metrics

| Metric | Target |
|--------|--------|
| Input latency | <100ms from keypress to display |
| Streaming latency | <50ms from chunk to display |
| Memory usage | <100MB additional over CLI |
| Minimum terminal | 80x24 fully functional |
| Terminal compatibility | iTerm2, Terminal.app, VS Code, SSH, tmux |
| Long-running stability | 24+ hours without memory growth |
| Log retention | Configurable max lines (default 10k) |

---

## 14. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Engine abstraction breaks existing CLI | High | Extensive tests, backward compatibility layer |
| Textual API changes | Medium | Pin version, test on updates |
| Thread-safety bugs | High | Strict post_message() discipline, code review |
| Long-running memory growth | Medium | Log rotation, widget recycling |
| Watch mode file race conditions | Medium | Preserve existing rename semantics |
| Input blocking worker thread | Medium | Use proper threading primitives |
| Pause/resume state corruption | High | Clear lifecycle contract, integration tests |
| Large log files slow rendering | Medium | Virtualized log display, line limits |

---

## 15. Dependencies

### 15.1 New Dependencies

```toml
# pyproject.toml

[project.optional-dependencies]
tui = [
    "textual>=0.80.0",
]
```

### 15.2 Development Dependencies

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "textual-dev>=1.0",  # For TUI development/testing
]
```

---

## Appendix A: Quick Start Examples

```bash
# Install with TUI support
pip install -e ".[tui]"

# Single session with TUI
orchestrator start -f "Add user authentication" --tui

# Queue mode with TUI
orchestrator start --queue plan1.md plan2.md plan3.md --tui

# Watch mode with TUI
orchestrator watch ./plans --tui

# Resume paused session with TUI
orchestrator resume abc123 --tui
```

---

## Appendix B: Keyboard Shortcuts

| Key | Single Session | Queue Mode | Watch Mode |
|-----|----------------|------------|------------|
| `q` | Quit | Quit | Quit |
| `p` | Pause session | Pause queue | - |
| `r` | Resume session | Resume queue | - |
| `s` | - | Skip item | Skip file |
| `t` | - | - | Toggle watch |
| `l` | Full logs | Full logs | Full logs |
| `?` | Help | Help | Help |
| `Tab` | Next panel | Next panel | Next panel |
| `Esc` | Close modal | Close modal | Close modal |

---

**Document Author:** Claude (Backend Architect)
**Version:** 2.0 (Revised per architectural review)
**Review Status:** Ready for implementation review
