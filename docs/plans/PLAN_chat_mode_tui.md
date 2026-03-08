# PLAN: `orchestrator chat-mode --tui --verbose`

**Feature:** Dedicated TUI chat window for direct conversation with the Planner agent
**Command:** `orchestrator chat-mode [--tui] [--verbose] [--model ALIAS]`
**Status:** Planning

---

## Overview

Add a new `chat-mode` CLI command that launches a dedicated, polished Textual TUI for chatting directly with the Planner agent. Unlike the existing `orchestrator chat` (which is a raw CLI loop), `chat-mode --tui` provides a proper chat UI: scrollable message history, a persistent text input field, a Send button, and optional verbose output (tool calls, notifications, token usage).

**Key distinctions from existing `orchestrator chat`:**

| Aspect | `orchestrator chat` | `orchestrator chat-mode --tui` |
|--------|---------------------|-------------------------------|
| UI | CLI readline loop | Full Textual TUI |
| Input | Multiline paste + `/commands` | Persistent text field + Send button |
| Streaming | `StreamingIndicator` spinner | Live chunk streaming in chat bubble |
| Verbose | Not available | `--verbose` flag: tool calls, notifications |
| Stats | None | Token/cost counter panel |
| Agent | Any model | Planner agent (Opus by default) |

---

## Architecture

```
cli.py
  └─ chat_mode() command
        ├─ [--tui=False] → ChatSession (existing, reused as-is)
        └─ [--tui=True]  → ChatTUIApp (new Textual app)

tui/chat_app.py
  └─ ChatTUIApp(App)
        ├─ ChatAdapter (thread bridge)
        └─ Worker thread → ChatBackend

chat_backend.py  (new module — TUI path only)
  └─ ChatBackend
        ├─ creates agent via create_planner_chat_agent()
        ├─ exposes send(content, on_chunk, on_response_complete, on_notification)
        └─ streams response back via callbacks

prompts.py  (modified)
  └─ PLANNER_CHAT_PROMPT  (new — freeform, no workflow tags)

agents.py  (modified)
  └─ create_planner_chat_agent()  (new factory — accepts system_prompt, on_notification)

tui/widgets/chat_message_view.py  (new widget)
  └─ ChatMessageView(ScrollableContainer)
        ├─ Renders user + assistant bubbles
        └─ Appends chunks in real-time

tui/widgets/chat_input_bar.py  (new widget)
  └─ ChatInputBar(Widget)
        ├─ TextArea (multiline input)
        └─ Send Button
```

---

## Module Map (new files)

| File | Role |
|------|------|
| `orchestrator_auto/chat_backend.py` | Agent wrapper for chat-mode; handles send/stream/callbacks |
| `orchestrator_auto/tui/chat_app.py` | Textual `App` subclass for chat-mode TUI |
| `orchestrator_auto/tui/chat_adapter.py` | Thread-safe bridge from backend callbacks → TUI messages |
| `orchestrator_auto/tui/widgets/chat_message_view.py` | Scrollable chat history widget with bubbles |
| `orchestrator_auto/tui/widgets/chat_input_bar.py` | Text input + Send button widget |
| `orchestrator_auto/tui/widgets/verbose_panel.py` | Tool calls + notification log (--verbose only) |

**Modified files:**

| File | Change |
|------|--------|
| `orchestrator_auto/cli.py` | Add `chat-mode` command with `--tui`, `--verbose`, `--model`, `--system-prompt`, `--no-tools` flags |
| `orchestrator_auto/prompts.py` | Add `PLANNER_CHAT_PROMPT` — freeform assistant prompt (no workflow tags) |
| `orchestrator_auto/agents.py` | Add `create_planner_chat_agent()` factory (accepts `system_prompt`, `on_notification`; handles empty `allowed_tools`) |
| `orchestrator_auto/tui/messages.py` | Add `ChatChunkReceived`, `ChatResponseComplete`, `ChatNotification` messages |

---

## Milestones

---

### Milestone 1 — CLI Scaffold, Prompt & Factory

**Deliverables:**
- `PLANNER_CHAT_PROMPT` added to `prompts.py`
- `create_planner_chat_agent()` factory added to `agents.py`
- New `orchestrator chat-mode` command in `cli.py` (non-TUI path works via existing `ChatSession`)
- `chat_backend.py` module with `ChatBackend` class (callback-driven; TUI path only)

**Implementation details:**

#### `prompts.py` — new `PLANNER_CHAT_PROMPT`

Add a freeform system prompt that gives the agent its identity as an expert planner without any workflow-phase instructions or response tags:

```python
PLANNER_CHAT_PROMPT = """You are an expert software architect and planning assistant.

You have deep knowledge of this project's codebase and can:
- Read and analyse files
- Execute bash commands
- Search code with grep/glob
- Discuss architecture, design patterns, and implementation strategies
- Help plan features and milestones

Be concise and direct. Focus on technical accuracy. When making suggestions,
reference specific files and line numbers where relevant."""
```

#### `agents.py` — new `create_planner_chat_agent()` factory

The existing `create_planner_agent()` lacks `system_prompt` and `on_notification`. Add a sibling factory for chat use:

```python
def create_planner_chat_agent(
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    session_id: str = "planner-chat",
    allowed_tools: Optional[List[str]] = None,
    on_token_usage: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_notification: Optional[Callable[[Dict[str, Any]], None]] = None,
    cwd: Optional[Path] = None,
) -> BaseAgent:
    """Create a freeform chat agent using the planner-chat prompt."""
    from .prompts import PLANNER_CHAT_PROMPT
    from .config import get_planner_model

    resolved_model = get_planner_model(model)  # opus by default
    prompt = system_prompt or PLANNER_CHAT_PROMPT

    # Ensure allowed_tools=[] is forwarded correctly even when falsy.
    # Verify during implementation: check if BaseAgent.__init__ guards on `if allowed_tools`
    # and adjust if so (pass sentinel or use DEFAULT_TOOLS when None, explicit [] when no-tools).
    tools = allowed_tools if allowed_tools is not None else None  # None = use DEFAULT_TOOLS

    return BaseAgent(
        system_prompt=prompt,
        allowed_tools=tools,
        model=resolved_model,
        session_id=session_id,
        on_token_usage=on_token_usage,
        on_notification=on_notification,
        cwd=cwd,
    )
```

#### `cli.py` — new command

Model alias resolution uses `get_planner_model()` (same pattern as other commands). Non-TUI path delegates to the existing `ChatSession` — no duplication of `/clear`, `/model`, paste support, etc.

```python
@cli.command("chat-mode")
@click.option("--tui", is_flag=True, default=False, help="Launch TUI chat window")
@click.option("--verbose", is_flag=True, default=False, help="Show notifications (TUI only)")
@click.option("--model", "-m", default="opus", show_default=True,
              help="Model alias: opus, sonnet, haiku")
@click.option("--system-prompt", "-s", type=click.Path(exists=True),
              help="Path to custom system prompt file (overrides default planner-chat prompt)")
@click.option("--no-tools", is_flag=True, default=False,
              help="Disable file/bash tools (pure text chat)")
def chat_mode(tui: bool, verbose: bool, model: str, system_prompt: Optional[str],
              no_tools: bool) -> None:
    """Direct freeform chat with the Planner agent."""
    display_auth_info()
    system_content = Path(system_prompt).read_text() if system_prompt else None

    if tui:
        from .tui.chat_app import ChatTUIApp
        app = ChatTUIApp(
            model=model,          # ChatTUIApp resolves via get_planner_model() internally
            verbose=verbose,
            system_prompt=system_content,
            tools_enabled=not no_tools,
        )
        app.run()
    else:
        # Non-TUI: reuse ChatSession with PLANNER_CHAT_PROMPT as default system prompt.
        # ChatSession already provides /clear, /model, /help, paste-aware input, StreamingIndicator.
        from .prompts import PLANNER_CHAT_PROMPT
        from .chat import ChatSession
        prompt = system_content or PLANNER_CHAT_PROMPT
        session = ChatSession(
            model=model,
            system_prompt=prompt,
            tools_enabled=not no_tools,
        )
        session.start()
```

#### `chat_backend.py` — TUI-only, callback-driven wrapper

`ChatBackend` is only needed for the TUI path. It has no CLI loop — that responsibility stays with `ChatSession`.

```python
class ChatBackend:
    """Callback-driven agent wrapper for the TUI chat path."""

    def __init__(
        self,
        model: str = "opus",
        system_prompt: Optional[str] = None,
        tools_enabled: bool = True,
        on_chunk: Optional[Callable[[str], None]] = None,
        on_response_complete: Optional[Callable[[str, Dict], None]] = None,
        on_notification: Optional[Callable[[Dict], None]] = None,
    ) -> None: ...

    def send(self, content: str) -> str:
        """Sync: send message, return full response. Fires all callbacks."""
        ...

    def reset(self) -> None:
        """Destroy agent; next send() creates a fresh one (context cleared)."""
        ...
```

Uses `create_planner_chat_agent()` with `on_notification` wired through.

**Acceptance criteria:**
- `orchestrator chat-mode` (no flags) opens a `ChatSession` using `PLANNER_CHAT_PROMPT` — no workflow tags emitted
- `orchestrator chat-mode --model sonnet` resolves via `get_planner_model()`
- `orchestrator chat-mode --no-tools` passes empty tools list; verify `allowed_tools=[]` is honoured in `BaseAgent` (not silently ignored by a truthy guard — fix factory if needed)
- `orchestrator chat-mode --system-prompt path/to/file.md` overrides the default prompt
- `/exit`, `/clear`, `/model`, paste support all work (inherited from `ChatSession`)
- `ChatBackend.send()` fires `on_chunk` and `on_response_complete` callbacks; `on_notification` fires on SDK notifications
- Unit tests: `tests/test_chat_backend.py` — mock agent, assert callbacks fire; test model resolution

---

### Milestone 2 — Core TUI App Layout

**Deliverables:**
- `tui/chat_app.py` with `ChatTUIApp(App)`
- `tui/widgets/chat_message_view.py` — scrollable bubble view (static, no streaming yet)
- `tui/widgets/chat_input_bar.py` — text input + Send button
- `tui/messages.py` additions: `ChatChunkReceived`, `ChatResponseComplete`
- App launches, renders layout, input bar is focusable

**UI Layout:**

```
┌─────────────────────────────────────────────────────────┐
│  Chat  [model: opus]                          [F1: Help] │  ← Header
├─────────────────────────────────────────────────────────┤
│                                                          │
│  [Assistant]  Hello! I'm the Planner. How can I help?   │
│                                                          │
│                [User]  How do I add a new CLI flag?      │
│                                                          │
│  [Assistant]  To add a new CLI flag:                     │
│               1. Add @click.option in cli.py...  ▌       │  ← streaming cursor
│                                                          │
│                                                          │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────┐  ┌──────────┐ │
│  │  Type a message...                   │  │   Send   │ │  ← ChatInputBar
│  └──────────────────────────────────────┘  └──────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Responsive:** on terminal width < 80, input bar stacks vertically (textarea full width, button below).

#### `tui/widgets/chat_message_view.py`

```python
class ChatMessageView(ScrollableContainer):
    """Scrollable chat history. Append user/assistant messages."""

    def append_user_message(self, content: str) -> None:
        """Mount a new user bubble."""
        ...

    def begin_assistant_message(self) -> "AssistantBubble":
        """Mount an empty assistant bubble; return handle for streaming."""
        ...

    def append_chunk(self, bubble: "AssistantBubble", chunk: str) -> None:
        """Append text to in-progress assistant bubble."""
        ...

    def finalize_assistant_message(self, bubble: "AssistantBubble") -> None:
        """Mark bubble complete (remove streaming cursor)."""
        ...
```

Messages are styled with Rich markup:
- **User bubbles**: right-aligned, `bold cyan` label `[You]`
- **Assistant bubbles**: left-aligned, `bold green` label `[Planner]`, Markdown rendering via Textual `Markdown` widget
- Streaming cursor: `▌` appended during generation, removed on completion

#### `tui/widgets/chat_input_bar.py`

```python
class ChatInputBar(Widget):
    """Text input + Send button. Posts SendMessage on submit."""

    class SendMessage(Message):
        """Posted when user submits. content = full text."""
        def __init__(self, content: str) -> None: ...

    DEFAULT_CSS = """
    ChatInputBar {
        height: auto;
        max-height: 8;
        layout: horizontal;
        padding: 0 1;
        border-top: solid $primary;
    }
    ChatInputBar TextArea {
        width: 1fr;
        height: auto;
        min-height: 1;
        max-height: 6;
    }
    ChatInputBar Button {
        width: 10;
        height: 3;
        margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield TextArea(id="chat-input")
        yield Button("Send", id="send-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            self._submit()

    def on_key(self, event: Key) -> None:
        # Ctrl+Enter submits; Enter adds newline
        if event.key == "ctrl+enter":
            self._submit()

    def _submit(self) -> None:
        ta = self.query_one(TextArea)
        content = ta.text.strip()
        if content:
            ta.clear()
            self.post_message(self.SendMessage(content=content))
```

#### `tui/chat_app.py`

```python
class ChatTUIApp(App):
    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("f1", "show_help", "Help"),
        ("ctrl+l", "clear_chat", "Clear"),
    ]

    CSS = """..."""  # layout grid

    def __init__(self, model, verbose, system_prompt, tools_enabled): ...

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield ChatMessageView(id="chat-view")
        yield ChatInputBar(id="input-bar")
        yield Footer()

    def on_chat_input_bar_send_message(self, event: ChatInputBar.SendMessage) -> None:
        """User pressed Send — start worker."""
        self._dispatch_message(event.content)

    def _dispatch_message(self, content: str) -> None:
        """Append user bubble, start worker thread for backend call."""
        view = self.query_one(ChatMessageView)
        view.append_user_message(content)
        self._current_bubble = view.begin_assistant_message()
        self.run_worker(
            lambda: self._backend.send(content),
            thread=True,
            name="chat-send",
        )
```

**Acceptance criteria:**
- `orchestrator chat-mode --tui` opens TUI, shows layout
- Typing in input bar and pressing Send or Ctrl+Enter dispatches message
- Empty input is ignored (button/shortcut does nothing)
- `ctrl+c` exits cleanly
- Unit tests: `tests/test_chat_app.py` — mock backend, assert bubbles mount

---

### Milestone 3 — Streaming Integration

**Deliverables:**
- `tui/chat_adapter.py` — thread-safe bridge for chat callbacks
- Worker thread calls `ChatBackend.send()` with `on_chunk` callback
- Chunks streamed live into assistant bubble via `call_from_thread()`
- `ChatResponseComplete` message finalizes bubble, re-enables input
- Stats: token count displayed in header subtitle or footer

**New TUI messages (add to `tui/messages.py`):**

```python
class ChatChunkReceived(Message):
    def __init__(self, chunk: str, bubble_id: str) -> None: ...

class ChatResponseComplete(Message):
    def __init__(self, bubble_id: str, full_text: str, usage: Dict) -> None: ...

class ChatNotification(Message):
    def __init__(self, notification: Dict) -> None: ...

# ChatToolEvent is deferred — see Milestone 4 notes.
```

#### `tui/chat_adapter.py`

```python
class ChatAdapter:
    """Thread-safe bridge from ChatBackend callbacks → TUI messages."""

    def __init__(self, app: "ChatTUIApp", bubble_id: str) -> None:
        self.app = app
        self.bubble_id = bubble_id

    def on_chunk(self, chunk: str) -> None:
        self.app.call_from_thread(
            self.app.post_message,
            ChatChunkReceived(chunk=chunk, bubble_id=self.bubble_id)
        )

    def on_response_complete(self, full_text: str, usage: Dict) -> None:
        self.app.call_from_thread(
            self.app.post_message,
            ChatResponseComplete(bubble_id=self.bubble_id, full_text=full_text, usage=usage)
        )

    def on_notification(self, notification: Dict) -> None:
        self.app.call_from_thread(
            self.app.post_message,
            ChatNotification(notification=notification)
        )

    # on_tool_event deferred — see Milestone 4 notes.
```

#### Message handlers in `ChatTUIApp`

```python
def on_chat_chunk_received(self, event: ChatChunkReceived) -> None:
    view = self.query_one(ChatMessageView)
    view.append_chunk(self._current_bubble, event.chunk)

def on_chat_response_complete(self, event: ChatResponseComplete) -> None:
    view = self.query_one(ChatMessageView)
    view.finalize_assistant_message(self._current_bubble)
    self._current_bubble = None
    # Update token counter
    self._total_tokens += event.usage.get("input_tokens", 0) + event.usage.get("output_tokens", 0)
    self._update_subtitle()
    # Re-enable input
    self.query_one(ChatInputBar).disabled = False
    self.query_one("#chat-input").focus()
```

**Input locking:** While a response is streaming:
- Send button is disabled (`button.disabled = True`)
- `ChatInputBar` posts `SendMessage` only when not locked
- A visual indicator ("Thinking...") shows in the assistant bubble until first chunk arrives

**Auto-scroll:** After each chunk, call `view.scroll_end(animate=False)` to keep latest content visible.

**Header subtitle** shows live token count: `Tokens: 1,234 | Cost: $0.012`

**Acceptance criteria:**
- Typing a message streams response live into the bubble
- Input field and Send button are disabled during streaming
- Auto-scroll keeps the latest text visible
- Token count updates in header after each response
- Tests: mock `ChatBackend.send()` to fire callbacks, assert TUI state

---

### Milestone 4 — Verbose Panel

**Deliverables:**
- `tui/widgets/verbose_panel.py` — collapsible panel showing notifications (and tool events if SDK supports it)
- Panel is only mounted when `--verbose` flag is set
- `ChatNotification` messages populate notification entries (confirmed working via `on_notification` hook)
- Tool call entries: best-effort — requires verifying `PostToolUse` success hook fires in the SDK. If unavailable, tool events are deferred to a follow-up and the panel shows notifications only.
- Toggle visibility with `F2` key binding

**UI Layout (with `--verbose`):**

```
┌─────────────────────────────────────────────────────────┐
│  Chat [opus] [Tokens: 1,234 | $0.012]         [F1 Help] │
├──────────────────────────────┬──────────────────────────┤
│                              │  VERBOSE [F2: toggle]    │
│  [You]  What files exist?    │  ─────────────────────   │
│                              │  🔧 tool: Glob           │
│  [Planner]  I'll check...    │     pattern: **/*.py     │
│             Found 12 files:  │     → 12 results         │
│             - agents.py      │                          │
│             - cli.py         │  📢 notification:        │
│             ...              │     "Running Glob..."    │
│                              │                          │
├──────────────────────────────┴──────────────────────────┤
│  ┌────────────────────────────────────┐  ┌──────────┐   │
│  │  Type a message...                 │  │   Send   │   │
│  └────────────────────────────────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────┘
```

#### `tui/widgets/verbose_panel.py`

```python
class VerbosePanel(Widget):
    """Displays tool calls and notifications when --verbose is active."""

    DEFAULT_CSS = """
    VerbosePanel {
        width: 35%;
        min-width: 25;
        border-left: solid $panel;
        padding: 0 1;
        overflow-y: auto;
    }
    VerbosePanel .tool-entry { color: $text-muted; }
    VerbosePanel .tool-name  { color: $warning; bold: true; }
    VerbosePanel .notif-entry { color: $accent; }
    """

    def add_tool_event(self, tool_name: str, tool_input: Dict, result: Optional[str]) -> None:
        """Append a tool call entry (only called if SDK PostToolUse hook is available)."""
        ...

    def add_notification(self, message: str, level: str = "info") -> None:
        """Append a notification entry."""
        ...

    def clear_events(self) -> None:
        """Clear all entries (on chat clear)."""
        ...
```

Each tool entry renders as:
```
🔧 Glob
   pattern: **/*.py
   → 12 results
```

Each notification entry renders as:
```
📢 "Reading file agents.py..."
```

#### Layout changes in `ChatTUIApp`

```python
def compose(self) -> ComposeResult:
    yield Header(show_clock=True)
    with Horizontal(id="main-area"):
        yield ChatMessageView(id="chat-view")
        if self._verbose:
            yield VerbosePanel(id="verbose-panel")
    yield ChatInputBar(id="input-bar")
    yield Footer()
```

CSS for `#main-area`:
```css
#main-area {
    height: 1fr;
}
#chat-view {
    width: 1fr;
}
#verbose-panel {
    width: 35;
    min-width: 20;
}
```

**F2 binding** toggles `VerbosePanel` visibility: `panel.display = not panel.display`.

**Acceptance criteria:**
- `orchestrator chat-mode --tui` (no `--verbose`): no verbose panel, full width chat
- `orchestrator chat-mode --tui --verbose`: verbose panel on right
- Notifications (e.g., "Reading file...") appear in verbose panel in real time
- Tool events: verify `PostToolUse` success hook during M4 implementation. If confirmed, wire `ChatToolEvent` and `VerbosePanel.add_tool_event()`; if not, document as follow-up and ship notifications-only
- F2 toggles panel visibility
- Tests: assert panel is/isn't mounted based on `verbose` flag; assert notifications render

---

### Milestone 5 — Polish, Keyboard Shortcuts & Help Screen

**Deliverables:**
- Full keyboard navigation (no mouse required)
- Help screen (F1) listing all shortcuts
- `/clear` command support inside chat input
- Markdown rendering for assistant messages
- `ctrl+l` clears chat history
- Focus trap: Tab cycles between input and (if visible) verbose panel
- Graceful shutdown: `ctrl+c` / `q` asks "End session?" confirm before exit

**Keyboard shortcuts:**

| Key | Action |
|-----|--------|
| `Ctrl+Enter` | Send message |
| `Enter` | Add newline in input |
| `Ctrl+C` / `Q` | Quit (with confirm) |
| `Ctrl+L` | Clear chat |
| `F1` | Toggle help overlay |
| `F2` | Toggle verbose panel (only with `--verbose`) |
| `Tab` | Cycle focus: input → verbose panel → input |
| `PgUp` / `PgDn` | Scroll chat history |
| `Ctrl+Home` | Scroll to top of chat |
| `Ctrl+End` | Scroll to bottom of chat |

**Help Overlay (`HelpModal`):**
A `ModalScreen` listing all shortcuts, dismissible with `Escape` or `F1`.

**Markdown rendering:**
Assistant bubble content uses Textual's `Markdown` widget inside the bubble container. Code blocks get syntax highlighting via Rich.

**`/clear` in input:**
Before sending, `ChatTUIApp._dispatch_message()` checks if `content == "/clear"`:
- Removes all messages from `ChatMessageView`
- Clears verbose panel
- Does NOT send to backend (no API call)

**Exit confirmation:**
```python
def action_quit(self) -> None:
    self.push_screen(ConfirmModal("End chat session?"), self._on_quit_confirmed)

def _on_quit_confirmed(self, confirmed: bool) -> None:
    if confirmed:
        self.exit()
```

**Acceptance criteria:**
- All keyboard shortcuts work
- F1 shows help overlay
- `/clear` clears chat without API call
- Markdown code blocks render with syntax highlighting
- Quit prompts for confirmation
- Full `pytest tests/test_chat_app.py` suite passes

---

## Data Flow Diagram

```
User types → ChatInputBar.SendMessage event
                  │
                  ▼
          ChatTUIApp._dispatch_message(content)
                  │
                  ├─ append_user_message() → ChatMessageView (main thread)
                  ├─ begin_assistant_message() → ChatMessageView (main thread)
                  ├─ disable ChatInputBar
                  └─ run_worker(thread=True)
                            │
                            ▼
                    [Worker Thread]
                    ChatBackend.send(content,
                        on_chunk=adapter.on_chunk,
                        on_response_complete=adapter.on_response_complete,
                        on_notification=adapter.on_notification,
                        on_tool_event=adapter.on_tool_event
                    )
                            │
                            ├─ agent.send_message_async()
                            │         │
                            │    TextBlock chunk → adapter.on_chunk()
                            │         │               │
                            │         │         call_from_thread →
                            │         │         ChatChunkReceived →
                            │         │         append_chunk() [main]
                            │         │
                            │    ResultMessage → adapter.on_response_complete()
                            │                       │
                            │               call_from_thread →
                            │               ChatResponseComplete →
                            │               finalize_bubble() [main]
                            │               re-enable input [main]
                            │
                            ├─ Notification hook → adapter.on_notification()
                            │                           │
                            │                   call_from_thread →
                            │                   ChatNotification →
                            │                   VerbosePanel.add_notification() [main]
                            │
                            └─ PostToolUse hook (verify SDK support in M4) →
                               if available: adapter.on_tool_event() →
                               call_from_thread → ChatToolEvent →
                               VerbosePanel.add_tool_event() [main]
```

---

## File Checklist

### New files
- [ ] `orchestrator_auto/chat_backend.py`
- [ ] `orchestrator_auto/tui/chat_app.py`
- [ ] `orchestrator_auto/tui/chat_adapter.py`
- [ ] `orchestrator_auto/tui/widgets/chat_message_view.py`
- [ ] `orchestrator_auto/tui/widgets/chat_input_bar.py`
- [ ] `orchestrator_auto/tui/widgets/verbose_panel.py`
- [ ] `tests/test_chat_backend.py`
- [ ] `tests/test_chat_app.py`

### Modified files
- [ ] `orchestrator_auto/cli.py` — add `chat-mode` command
- [ ] `orchestrator_auto/prompts.py` — add `PLANNER_CHAT_PROMPT`
- [ ] `orchestrator_auto/agents.py` — add `create_planner_chat_agent()` factory
- [ ] `orchestrator_auto/tui/messages.py` — add `ChatChunkReceived`, `ChatResponseComplete`, `ChatNotification` (+ `ChatToolEvent` if tool events confirmed in M4)

### Docs to update
- [ ] `docs/CLI_REFERENCE.md` — add `chat-mode` command entry
- [ ] `orchestrator-auto/AGENTS.md` — add `chat_backend.py` and new TUI files to module maps

---

## Testing Strategy

| Test file | What it covers |
|-----------|---------------|
| `test_chat_backend.py` | `ChatBackend.send()` fires `on_chunk`/`on_response_complete`/`on_notification` callbacks; `create_planner_chat_agent()` resolves model via `get_planner_model()`; `reset()` clears agent |
| `test_chat_app.py` | Layout renders; `SendMessage` event dispatches; chunk → bubble update; input locked during streaming; verbose panel mount/unmount; `/clear` command; F2 toggle |
| `test_cli.py` (extend) | `chat-mode` command exists; `--tui` flag parsed; `--verbose` flag parsed |

All tests use `unittest.mock.patch` to avoid real API calls. Textual's `App.run_test()` async context manager for widget tests.

---

## Implementation Notes

### Why `ChatBackend` exists alongside `ChatSession`

`ChatSession` (in `chat.py`) is tightly coupled to CLI: readline loop, `print()` calls, `StreamingIndicator`. The non-TUI path of `chat-mode` **reuses `ChatSession` directly** — passing `PLANNER_CHAT_PROMPT` as the system prompt — so all existing CLI features (`/clear`, `/model`, multi-line paste) come for free.

`ChatBackend` exists only for the TUI path. It is callback-driven and has no CLI loop. The TUI worker thread calls `ChatBackend.send()` and receives results through `on_chunk` / `on_response_complete` / `on_notification`.

### Why `TextArea` instead of `Input` for the input bar

`Input` is single-line. Chat messages can be multi-line (code snippets, long prompts). `TextArea` supports `Ctrl+Enter` to submit while `Enter` adds newlines — matching user expectations from Slack/Discord.

### Agent choice: `create_planner_chat_agent()` not `create_planner_agent()`

`create_planner_agent()` uses `PLANNER_SYSTEM_PROMPT`, which instructs the agent to run Discovery → Planning → Review phases and emit structured tags (`[PLAN_READY]`, `[MILESTONE_APPROVED]`, etc.). Using it for freeform chat would produce awkward, workflow-flavoured responses.

Instead, `chat-mode` uses the new `create_planner_chat_agent()` backed by `PLANNER_CHAT_PROMPT` — a freeform prompt with no phase instructions or tags. The agent still defaults to Opus and has full tool access, but behaves as a conversational assistant. `--system-prompt` can override the prompt entirely.

### Thread safety

Same pattern as `tui/adapter.py`: callbacks from the worker thread use `app.call_from_thread(app.post_message, ...)`. The main thread handles all widget mutations. `ChatInputBar` disabled state is set via `app.call_from_thread()` too.

### Bubble IDs

Each assistant bubble gets a unique ID (`f"bubble-{uuid4().hex[:8]}"`) so `ChatChunkReceived` can target the correct bubble even if multiple messages are in flight (though only one message is in flight at a time — input is locked during streaming).
