# Direct Chat Mode - Implementation Plan

## 1. Overview

Add an `orchestrator chat` command that enables direct conversation with Claude without the full two-agent orchestration workflow. This provides a lightweight alternative for quick questions, ad-hoc tasks, or interactive coding sessions where milestone-based oversight is unnecessary.

## 2. Feature Specification

### 2.1 Command Details

| Property | Value |
|----------|-------|
| **Command** | `orchestrator chat` |
| **Purpose** | Direct Claude conversation without orchestration |
| **Session Type** | Stateless (no DB persistence) |
| **Exit Methods** | `/exit`, `/quit`, `Ctrl+C`, `Ctrl+D` |

### 2.2 CLI Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-m, --model` | string | `sonnet` | Model alias: `opus`, `sonnet`, `haiku` |
| `-s, --system-prompt` | path | None | Custom system prompt file (markdown) |
| `--no-tools` | flag | False | Disable file/bash tools (pure chat mode) |
| `--show-activity/--no-activity` | bool | True | Show streaming activity indicator |

> **Note:** Uses `--show-activity/--no-activity` boolean pair to match the existing `start` command (see `cli.py:888`).

### 2.3 User Stories

- As a developer, I can quickly ask Claude questions without starting a full workflow
- As a developer, I can use custom system prompts for specialized tasks (code review, debugging)
- As a developer, I can disable tools for a pure chat experience (brainstorming, planning)

### 2.4 Session Flow

```
$ orchestrator chat -m sonnet

Direct Chat Mode (Sonnet)
Tools: enabled | Activity: enabled
Type /help for commands, /exit to quit

You: How do I implement a binary search in Python?

Claude: Here's a binary search implementation...

You: /exit

Chat session ended.
```

### 2.5 In-Chat Commands

| Command | Description |
|---------|-------------|
| `/exit`, `/quit` | End chat session |
| `/help` | Show available commands |
| `/clear` | Clear conversation history (creates fresh agent) |
| `/model <alias>` | Switch model (resets context, like `/clear`) |

> **Design Decision:** `/model` and `/clear` both reset conversation context by creating a new agent instance. This is intentional - maintaining context across model switches would require transcript replay which adds complexity. Users who want to preserve context should stay on the same model.

## 3. Architecture

### 3.1 File Structure

```
orchestrator_auto/
├── cli.py              # Add chat command (~40 lines)
├── chat.py             # NEW: Chat session handler (~150 lines)
├── agents.py           # Add create_chat_agent() factory (~15 lines)
├── input_handler.py    # Modify to distinguish EOF from empty input (~5 lines changed)
└── output.py           # Reuse StreamingIndicator
```

### 3.2 Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                   orchestrator chat                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │   CLI Entry  │───►│ ChatSession  │                   │
│  │  (cli.py)    │    │  (chat.py)   │                   │
│  └──────────────┘    └──────┬───────┘                   │
│                             │                            │
│         ┌───────────────────┼───────────────────┐       │
│         ▼                   ▼                   ▼       │
│  ┌──────────────┐   ┌──────────────┐   ┌─────────────┐  │
│  │ InputHandler │   │  BaseAgent   │   │  Streaming  │  │
│  │ (TTY-aware)  │   │  (direct)    │   │  Indicator  │  │
│  └──────────────┘   └──────────────┘   └─────────────┘  │
│                                                          │
│  No DB Persistence │ Stateless Session                  │
└─────────────────────────────────────────────────────────┘
```

### 3.3 Agent Instantiation

**Critical:** Chat mode must use `BaseAgent` directly with a custom system prompt, NOT `ExecutorAgent` which hardcodes `EXECUTOR_SYSTEM_PROMPT` (two-agent workflow prompt).

```python
# CORRECT: Use BaseAgent directly via factory
from .agents import create_chat_agent

agent = create_chat_agent(
    model="claude-sonnet-4-5-20250929",
    system_prompt=custom_prompt,
    allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],  # or [] for --no-tools
)

# WRONG: ExecutorAgent uses EXECUTOR_SYSTEM_PROMPT
from .agents import create_executor_agent
agent = create_executor_agent(...)  # <-- hardcoded orchestration prompt
```

### 3.4 Patterns to Follow

| Component | Reference Pattern |
|-----------|-------------------|
| CLI command | `cli.py::start()` - Click options/decorators |
| Agent creation | `agents.py::BaseAgent` - direct instantiation |
| Input handling | `engine.py::_run_discovery_loop()` |
| Activity indicator | `engine.py::_send_with_activity()` |
| Model resolution | `config.py::get_executor_model()` |
| TTY fallback | `input_handler.py::simple_input()` |

## 4. Implementation Details

### 4.1 New Factory Function (agents.py)

```python
def create_chat_agent(
    model: str = "claude-sonnet-4-5-20250929",
    system_prompt: Optional[str] = None,
    allowed_tools: Optional[List[str]] = None,
    cwd: Optional[Path] = None,
) -> BaseAgent:
    """
    Factory function to create a direct chat agent.

    Unlike ExecutorAgent, this uses a custom system prompt suitable
    for general-purpose chat rather than milestone-based execution.

    Args:
        model: Claude model to use
        system_prompt: Custom system prompt (default: DEFAULT_CHAT_PROMPT)
        allowed_tools: List of allowed tools (default: all tools, empty list = no tools)
        cwd: Working directory

    Returns:
        BaseAgent instance configured for direct chat
    """
    from .prompts import DEFAULT_CHAT_PROMPT

    return BaseAgent(
        system_prompt=system_prompt or DEFAULT_CHAT_PROMPT,
        allowed_tools=allowed_tools if allowed_tools is not None else DEFAULT_TOOLS,
        model=model,
        session_id="chat",
        cwd=cwd,
    )
```

### 4.2 Input Handler Enhancement (input_handler.py)

**Problem:** Current `prompt_with_paste_support()` returns `("", "")` for both empty Enter and EOF/Ctrl+D, making them indistinguishable.

**Constraint:** `engine.py:490` calls `user_input.lower()` without None checks. Changing the return type globally would break orchestrator's discovery loop.

**Solution (Option A - scope-safe):** Add optional parameter to distinguish EOF, defaulting to existing behavior:

```python
# input_handler.py - Changes to PasteAwareInput.prompt()

def prompt(
    self,
    prompt_text: str = "You: ",
    return_none_on_eof: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Prompt for user input with paste detection.

    Args:
        prompt_text: The prompt to display
        return_none_on_eof: If True, return (None, None) on EOF/Ctrl+D.
                           If False (default), return ("", "") for backward compatibility.

    Returns:
        Tuple of (display_text, full_content)
        - (None, None) on EOF/Ctrl+D when return_none_on_eof=True
        - ("", "") on EOF/Ctrl+D when return_none_on_eof=False (default)
        - ("", "") on empty input (just Enter)
        - (display, content) on normal input
    """
    session = self._get_session()

    try:
        text = session.prompt(prompt_text)

        if not text:
            return "", ""  # Empty input (Enter key)

        # ... rest of paste detection logic unchanged ...

    except EOFError:
        if return_none_on_eof:
            return None, None
        return "", ""  # Backward compatible
    except KeyboardInterrupt:
        # Always re-raise KeyboardInterrupt - let caller handle it
        # (orchestrator has signal handler, chat has try/except)
        raise
```

**Key Design Decisions:**
1. **Default `return_none_on_eof=False`**: Existing callers (engine.py) unchanged
2. **KeyboardInterrupt always re-raised**: Don't swallow Ctrl+C globally. Let each caller decide:
   - Orchestrator: handled by `signal.signal()` handler in cli.py
   - ChatSession: handled by `try/except KeyboardInterrupt` in `start()`
3. **Only EOF is parameterized**: Ctrl+D exit is chat-specific; Ctrl+C propagates naturally

### 4.3 Update prompt_with_paste_support wrapper (input_handler.py)

```python
def prompt_with_paste_support(
    prompt_text: str = "You: ",
    return_none_on_eof: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Prompt for input with multi-line paste support.

    Args:
        prompt_text: The prompt to display
        return_none_on_eof: If True, return (None, None) on EOF.
                           If False (default), return ("", "").

    Returns:
        Tuple of (display_text, full_content)
    """
    handler = get_input_handler()
    return handler.prompt(prompt_text, return_none_on_eof=return_none_on_eof)
```

**Backward Compatibility:** All existing callers continue to work unchanged. Only chat.py passes `return_none_on_eof=True`.

### 4.4 Default System Prompt (prompts.py)

```python
DEFAULT_CHAT_PROMPT = """You are a helpful AI assistant in a direct chat session.

You have access to the user's codebase and can:
- Read and analyze files
- Execute bash commands
- Search code with grep/glob
- Make edits when requested

Be concise and helpful. Focus on answering questions and completing tasks efficiently.
When making changes, explain what you're doing briefly."""
```

### 4.5 ChatSession Class (chat.py)

```python
import sys
import click
from typing import Optional
from pathlib import Path

from .agents import create_chat_agent, BaseAgent
from .config import get_executor_model, get_model_display_name
from .output import StreamingIndicator


class ChatSession:
    """Stateless direct chat session with Claude."""

    def __init__(
        self,
        model: str = "sonnet",
        system_prompt: Optional[str] = None,
        tools_enabled: bool = True,
        show_activity: bool = True,
    ):
        self.model_alias = model
        self.model = get_executor_model(model)
        self.system_prompt = system_prompt
        self.tools_enabled = tools_enabled
        self.show_activity = show_activity
        self.agent: Optional[BaseAgent] = None
        self.conversation_active = True
        self._is_tty = sys.stdin.isatty()

    def start(self) -> None:
        """Main chat loop."""
        self._create_agent()
        self._print_welcome()

        try:
            while self.conversation_active:
                try:
                    user_input = self._get_input()

                    # Empty input from EOF/Ctrl+D - treat as exit
                    if user_input is None:
                        self._handle_exit()
                        break

                    # Empty string - reprompt
                    if not user_input.strip():
                        continue

                    # Check for commands
                    if self._handle_command(user_input):
                        continue

                    # Send to agent
                    response = self._send_message(user_input)
                    self._print_response(response)

                except KeyboardInterrupt:
                    self._handle_exit()
                    break
        finally:
            self._cleanup()

    def _create_agent(self) -> None:
        """Create or recreate the chat agent."""
        # Close existing agent if any
        if self.agent:
            self.agent.close()

        from .agents import create_chat_agent, DEFAULT_TOOLS

        allowed_tools = DEFAULT_TOOLS if self.tools_enabled else []

        self.agent = create_chat_agent(
            model=self.model,
            system_prompt=self.system_prompt,
            allowed_tools=allowed_tools,
        )

    def _get_input(self) -> Optional[str]:
        """Get user input, with TTY-aware fallback.

        Returns:
            str: User input text
            None: EOF/Ctrl+D (signals exit)

        Raises:
            KeyboardInterrupt: On Ctrl+C (handled by caller's try/except)
        """
        if self._is_tty:
            from .input_handler import prompt_with_paste_support

            # Pass return_none_on_eof=True to distinguish EOF from empty Enter
            display, content = prompt_with_paste_support(
                "\nYou: ",
                return_none_on_eof=True,
            )

            # EOF/Ctrl+D returns (None, None) - signal exit
            if content is None:
                return None

            # Show collapsed preview for multi-line pastes
            if display != content and display:
                click.echo(f"  {display}")

            # Empty string from just hitting Enter - return as-is (will reprompt)
            return content
        else:
            # Non-TTY fallback (CI, pipes)
            from .input_handler import simple_input
            result = simple_input("\nYou: ")
            return None if result == "" else result

    def _send_message(self, content: str) -> str:
        """Send message with optional activity indicator."""
        indicator = None
        if self.show_activity:
            indicator = StreamingIndicator(
                interval=1.5,
                show_tokens=True,
                output_func=lambda s: click.echo(s, nl=False),
            )

        response = self.agent.send_message(
            content,
            on_chunk=indicator.on_chunk if indicator else None
        )

        if indicator:
            indicator.finish()

        return response

    def _handle_command(self, user_input: str) -> bool:
        """Handle in-chat commands. Returns True if command was handled."""
        cmd = user_input.strip().lower()

        if cmd in ('/exit', '/quit'):
            self._handle_exit()
            return True
        elif cmd == '/help':
            self._print_help()
            return True
        elif cmd == '/clear':
            self._clear_conversation()
            return True
        elif cmd.startswith('/model'):
            parts = user_input.strip().split()
            if len(parts) == 2:
                self._switch_model(parts[1])
            else:
                click.echo("Usage: /model <opus|sonnet|haiku>")
            return True
        elif cmd.startswith('/'):
            click.echo(f"Unknown command: {cmd.split()[0]}. Type /help for commands.")
            return True

        return False

    def _switch_model(self, alias: str) -> None:
        """Switch to a different model (resets context)."""
        try:
            new_model = get_executor_model(alias)
            self.model_alias = alias
            self.model = new_model
            self._create_agent()  # Creates new agent, closes old one
            click.secho(
                f"\n✓ Switched to {get_model_display_name(new_model)} (context reset)",
                fg="green"
            )
        except ValueError:
            click.secho(f"Unknown model: {alias}. Use opus, sonnet, or haiku.", fg="red")

    def _clear_conversation(self) -> None:
        """Clear conversation by creating fresh agent."""
        self._create_agent()
        click.secho("\n✓ Conversation cleared", fg="green")

    def _handle_exit(self) -> None:
        """Handle exit request."""
        self.conversation_active = False
        click.echo("\nChat session ended.")

    def _cleanup(self) -> None:
        """Cleanup resources on exit."""
        if self.agent:
            self.agent.close()
            self.agent = None

    def _print_welcome(self) -> None:
        """Print welcome message."""
        model_name = get_model_display_name(self.model)
        tools_status = "enabled" if self.tools_enabled else "disabled"
        activity_status = "enabled" if self.show_activity else "disabled"

        click.echo()
        click.secho(f"Direct Chat Mode ({model_name})", fg="cyan", bold=True)
        click.echo(f"Tools: {tools_status} | Activity: {activity_status}")
        click.echo("Type /help for commands, /exit to quit")

    def _print_help(self) -> None:
        """Print help message."""
        click.echo()
        click.secho("Commands:", bold=True)
        click.echo("  /exit, /quit  - End chat session")
        click.echo("  /help         - Show this help")
        click.echo("  /clear        - Clear conversation (reset context)")
        click.echo("  /model <name> - Switch model (opus/sonnet/haiku, resets context)")
        click.echo()

    def _print_response(self, response: str) -> None:
        """Print agent response."""
        click.echo(f"\nClaude: {response}")
```

### 4.6 CLI Command (cli.py)

```python
@cli.command()
@click.option('--model', '-m', default='sonnet',
              help='Model: opus, sonnet, haiku (default: sonnet)')
@click.option('--system-prompt', '-s', type=click.Path(exists=True),
              help='Path to custom system prompt file')
@click.option('--no-tools', is_flag=True,
              help='Disable file/bash tools (pure chat)')
@click.option('--show-activity/--no-activity', default=True,
              help='Show streaming activity indicator (default: enabled)')
def chat(model: str, system_prompt: Optional[str], no_tools: bool, show_activity: bool):
    """Start a direct chat session with Claude (no orchestration)."""
    from .chat import ChatSession

    # Load system prompt from file if provided
    prompt_content = None
    if system_prompt:
        prompt_content = Path(system_prompt).read_text()

    session = ChatSession(
        model=model,
        system_prompt=prompt_content,
        tools_enabled=not no_tools,
        show_activity=show_activity,
    )
    session.start()
```

## 5. Testing Strategy

### 5.1 Mocking Approach

Interactive components require mocking. **Important:** Patch targets must match where the name is looked up, not where it's defined.

**Patch Target Rules:**
- `prompt_with_paste_support` is imported inside `_get_input()` → patch `orchestrator_auto.input_handler.prompt_with_paste_support`
- `create_chat_agent` is imported at module scope in `chat.py` → patch `orchestrator_auto.chat.create_chat_agent`
- `ChatSession` is imported inside CLI `chat()` → patch `orchestrator_auto.chat.ChatSession`

```python
# test_chat.py - Mock patterns

from unittest.mock import patch, MagicMock, ANY, call
from orchestrator_auto.chat import ChatSession

@patch('orchestrator_auto.input_handler.prompt_with_paste_support')
@patch('orchestrator_auto.chat.create_chat_agent')
def test_chat_basic_conversation(mock_create_agent, mock_input):
    """Test basic send/receive flow."""
    # Setup mock agent
    mock_agent = MagicMock()
    mock_agent.send_message.return_value = "Hello! How can I help?"
    mock_create_agent.return_value = mock_agent

    # Setup mock input sequence: message, then /exit
    # Note: (None, None) = EOF when return_none_on_eof=True
    mock_input.side_effect = [
        ("Hello", "Hello"),        # First input
        ("/exit", "/exit"),        # Exit command
    ]

    session = ChatSession(model="sonnet")
    session.start()

    # Verify prompt_with_paste_support called with return_none_on_eof=True
    mock_input.assert_called_with("\nYou: ", return_none_on_eof=True)
    mock_agent.send_message.assert_called_once_with("Hello", on_chunk=ANY)
    mock_agent.close.assert_called()  # Cleanup called


@patch('orchestrator_auto.input_handler.prompt_with_paste_support')
@patch('orchestrator_auto.chat.create_chat_agent')
def test_chat_eof_exits(mock_create_agent, mock_input):
    """Test Ctrl+D (EOF) exits gracefully."""
    mock_agent = MagicMock()
    mock_create_agent.return_value = mock_agent

    # EOF returns (None, None) when return_none_on_eof=True
    mock_input.return_value = (None, None)

    session = ChatSession(model="sonnet")
    session.start()

    mock_agent.send_message.assert_not_called()  # No message sent
    mock_agent.close.assert_called()  # Cleanup still called


@patch('orchestrator_auto.input_handler.prompt_with_paste_support')
@patch('orchestrator_auto.chat.create_chat_agent')
def test_chat_empty_reprompts(mock_create_agent, mock_input):
    """Test empty Enter reprompts instead of exiting."""
    mock_agent = MagicMock()
    mock_create_agent.return_value = mock_agent

    # Empty Enter returns ("", ""), then /exit
    mock_input.side_effect = [
        ("", ""),           # Empty input - should reprompt
        ("/exit", "/exit"), # Exit
    ]

    session = ChatSession(model="sonnet")
    session.start()

    mock_agent.send_message.assert_not_called()  # Empty input not sent
    assert mock_input.call_count == 2  # Reprompted


@patch('orchestrator_auto.input_handler.prompt_with_paste_support')
@patch('orchestrator_auto.chat.create_chat_agent')
def test_chat_ctrl_c_exits(mock_create_agent, mock_input):
    """Test Ctrl+C exits gracefully via KeyboardInterrupt."""
    mock_agent = MagicMock()
    mock_create_agent.return_value = mock_agent

    # Ctrl+C raises KeyboardInterrupt (not caught by prompt_with_paste_support)
    mock_input.side_effect = KeyboardInterrupt()

    session = ChatSession(model="sonnet")
    session.start()  # Should not raise - caught by try/except in start()

    mock_agent.send_message.assert_not_called()
    mock_agent.close.assert_called()  # Cleanup still called
```

```python
# test_cli_chat.py - CLI integration tests

from click.testing import CliRunner
from unittest.mock import patch, MagicMock

@patch('orchestrator_auto.chat.ChatSession')
def test_cli_chat_invokes_session(mock_session_class):
    """Test CLI creates ChatSession with correct args."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session

    from orchestrator_auto.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ['chat', '-m', 'opus', '--no-tools'])

    mock_session_class.assert_called_once_with(
        model='opus',
        system_prompt=None,
        tools_enabled=False,
        show_activity=True,
    )
    mock_session.start.assert_called_once()
```

### 5.2 Unit Tests (test_chat.py)

| Test | Description |
|------|-------------|
| `test_chat_session_init_defaults` | Verify default model, tools, activity |
| `test_chat_session_custom_prompt` | Custom system prompt loaded |
| `test_chat_session_no_tools` | Tools disabled when flag set |
| `test_handle_exit_command` | `/exit` sets `conversation_active=False` |
| `test_handle_quit_command` | `/quit` sets `conversation_active=False` |
| `test_handle_help_command` | `/help` prints help, returns True |
| `test_handle_clear_command` | `/clear` recreates agent |
| `test_handle_model_switch` | `/model haiku` recreates agent with new model |
| `test_handle_model_invalid` | Invalid model shows error |
| `test_ctrl_c_exits` | `KeyboardInterrupt` caught by `start()`, triggers exit |
| `test_empty_input_reprompts` | `("", "")` from input continues loop (reprompt) |
| `test_eof_exits` | `(None, None)` from input (with `return_none_on_eof=True`) triggers exit |
| `test_cleanup_closes_agent` | `_cleanup()` calls `agent.close()` |
| `test_non_tty_uses_simple_input` | Non-TTY falls back to `simple_input()` |

### 5.3 Unit Tests (test_input_handler.py)

| Test | Description |
|------|-------------|
| `test_prompt_eof_default_returns_empty` | `EOFError` with default params returns `("", "")` |
| `test_prompt_eof_with_flag_returns_none` | `EOFError` with `return_none_on_eof=True` returns `(None, None)` |
| `test_prompt_ctrl_c_raises` | `KeyboardInterrupt` is re-raised (not caught) |
| `test_prompt_returns_empty_on_enter` | Empty input returns `("", "")` |
| `test_prompt_returns_content` | Normal input returns `(content, content)` |
| `test_backward_compat_existing_callers` | Default behavior unchanged for engine.py callers |

### 5.4 Integration Tests (test_cli_chat.py)

| Test | Description |
|------|-------------|
| `test_cli_chat_command_exists` | `orchestrator chat --help` works |
| `test_cli_chat_with_model` | `-m opus` passes correct model |
| `test_cli_chat_with_prompt_file` | `-s prompt.md` loads file content |
| `test_cli_chat_no_tools_flag` | `--no-tools` sets `tools_enabled=False` |
| `test_cli_chat_no_activity_flag` | `--no-activity` sets `show_activity=False` |

### 5.5 Coverage Targets

| Component | Target |
|-----------|--------|
| `chat.py` | 90% |
| `agents.py` (new factory) | 95% |
| `input_handler.py` (changes) | 95% |
| CLI integration | 85% |

## 6. Milestones

### Milestone 1: Input Handler + Agent Factory + Core ChatSession

**Tasks:**
1. Add `return_none_on_eof` parameter to `input_handler.py` (defaults to `False` for backward compat)
2. Re-raise `KeyboardInterrupt` instead of swallowing it (let callers handle Ctrl+C)
3. Add `DEFAULT_CHAT_PROMPT` to `prompts.py`
4. Add `create_chat_agent()` factory to `agents.py`
5. Create `orchestrator_auto/chat.py` with `ChatSession` class
6. Implement basic chat loop (input → send → output)
7. Add TTY detection with `simple_input()` fallback for non-TTY
8. Ensure `agent.close()` called in `_cleanup()` and `_create_agent()`
9. Add graceful `Ctrl+C` (via `KeyboardInterrupt`) and `Ctrl+D` (via `None`) handling

**Deliverables:**
- [ ] `input_handler.py` - Add `return_none_on_eof` param; re-raise `KeyboardInterrupt`
- [ ] `prompts.py` - `DEFAULT_CHAT_PROMPT` constant
- [ ] `agents.py` - `create_chat_agent()` factory function
- [ ] `chat.py` - `ChatSession` class with basic loop
- [ ] TTY-aware input handling
- [ ] Proper agent cleanup on exit
- [ ] Verify backward compat: orchestrator discovery loop unchanged
- [ ] Manual testing confirms: empty Enter reprompts, Ctrl+D exits, Ctrl+C exits

**Key References:**
- `agents.py::BaseAgent` - Direct instantiation pattern
- `engine.py::_run_discovery_loop()` - Must remain unchanged (backward compat)
- `input_handler.py::simple_input()` - Non-TTY fallback

---

### Milestone 2: CLI Command + Options

**Tasks:**
1. Add `chat` command to `cli.py`
2. Implement `--model` option with alias resolution
3. Implement `--system-prompt` option (load from file)
4. Implement `--no-tools` flag (pass empty `allowed_tools` list)
5. Implement `--no-activity` flag (disable `StreamingIndicator`)

**Deliverables:**
- [ ] `orchestrator chat` command works
- [ ] All CLI options functional
- [ ] `orchestrator chat --help` shows usage
- [ ] Manual testing of each option combination

**Key References:**
- `cli.py::start()` - CLI pattern
- `config.py::get_executor_model()` - Model resolution

---

### Milestone 3: In-Chat Commands

**Tasks:**
1. Implement `/exit` and `/quit` commands
2. Implement `/help` command with command list
3. Implement `/clear` command (recreates agent, resets context)
4. Implement `/model <alias>` command (recreates agent with new model, resets context)
5. Add welcome message with model/tools/activity status
6. Handle unknown `/command` with helpful error

**Deliverables:**
- [ ] All in-chat commands working
- [ ] Welcome message shows configuration
- [ ] `/help` displays all available commands
- [ ] `/model` and `/clear` properly close old agent before creating new
- [ ] Unknown commands show error message

---

### Milestone 4: Tests + Documentation

**Tasks:**
1. Write unit tests for `ChatSession` class (mock `prompt_with_paste_support`, `create_chat_agent`)
2. Write unit test for `create_chat_agent()` factory
3. Write CLI integration tests (mock `ChatSession.start()`)
4. Achieve 85%+ coverage on new code
5. Update README.md with `chat` command documentation
6. Add examples to Quick Reference section

**Deliverables:**
- [ ] `tests/test_chat.py` with unit tests
- [ ] `tests/test_cli_chat.py` with CLI tests
- [ ] Coverage report shows 85%+ on new code
- [ ] README.md updated with documentation
- [ ] All tests passing

---

## 7. Quick Reference

| Resource | Path |
|----------|------|
| Implementation Plan | `docs/direct-chat/DOC_direct_chat_plan.md` |
| Input Handler Changes | `orchestrator_auto/input_handler.py` |
| Chat System Prompt | `orchestrator_auto/prompts.py::DEFAULT_CHAT_PROMPT` |
| Chat Agent Factory | `orchestrator_auto/agents.py::create_chat_agent()` |
| ChatSession Class | `orchestrator_auto/chat.py` |
| CLI Entry Point | `orchestrator_auto/cli.py::chat()` |
| Tests | `tests/test_chat.py`, `tests/test_cli_chat.py`, `tests/test_input_handler.py` |

## 8. Anti-Patterns

### Don't: Use ExecutorAgent for chat
```python
# BAD - ExecutorAgent hardcodes EXECUTOR_SYSTEM_PROMPT
from .agents import create_executor_agent
agent = create_executor_agent(model=model)  # Wrong prompt!
```

### Do: Use BaseAgent via factory
```python
# GOOD - BaseAgent with custom prompt
from .agents import create_chat_agent
agent = create_chat_agent(
    model=model,
    system_prompt=custom_prompt,
    allowed_tools=allowed_tools,
)
```

### Don't: Forget to close agents
```python
# BAD - leaks event loops and clients
def _switch_model(self, alias: str):
    self.model = get_executor_model(alias)
    self.agent = create_chat_agent(model=self.model)  # Old agent leaked!
```

### Do: Always close before recreating
```python
# GOOD - clean lifecycle management
def _create_agent(self) -> None:
    if self.agent:
        self.agent.close()  # Close old agent first
    self.agent = create_chat_agent(...)
```

### Don't: Add database persistence
```python
# BAD - overcomplicated for simple chat
class ChatSession:
    def __init__(self):
        self.session_id = db.create_chat_session()
```

### Do: Keep it stateless
```python
# GOOD - simple, no persistence needed
class ChatSession:
    def __init__(self):
        self.agent = None
        self.conversation_active = True
```

---

## 9. Edge Cases & Robustness

| Scenario | Input Handler Behavior | ChatSession Behavior |
|----------|----------------------|---------------------|
| Empty input (just Enter) | Returns `("", "")` | Reprompt (continue loop) |
| `Ctrl+D` / EOF | Returns `(None, None)` when `return_none_on_eof=True` | Graceful exit with cleanup |
| `Ctrl+C` | Re-raises `KeyboardInterrupt` | Caught by `try/except` in `start()`, graceful exit |
| Non-TTY (CI, pipe) | N/A (uses `simple_input()`) | Empty = exit, non-empty = process |
| Invalid `/model` alias | N/A | Show error, don't change model |
| Unknown `/command` | N/A | Show "Unknown command" message |
| Agent creation failure | N/A | Let exception propagate (fail fast) |

**Backward Compatibility:** Orchestrator's `engine.py` continues to use default `return_none_on_eof=False`, so existing behavior (EOF → `("", "")` → reprompt or handle as empty) is unchanged.

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Agent SDK changes | Minimal coupling - only use `BaseAgent` and `send_message()` |
| Model switching loses context | Documented behavior - `/model` explicitly resets |
| Resource leaks | `_cleanup()` in `finally` block, `agent.close()` before recreate |
| prompt_toolkit in CI | TTY detection with `simple_input()` fallback |
| Graceful shutdown | `KeyboardInterrupt` and EOF both trigger `_handle_exit()` |

---

**Plan Status:** Ready for Review (v4 - scope-safe input handler)

**Changes from v3:**
- Fixed: Blocker - `engine.py:490` calls `user_input.lower()` without None checks
- Solution: Add `return_none_on_eof` parameter (defaults `False`) instead of changing global behavior
- Fixed: `KeyboardInterrupt` now re-raised (not swallowed) - callers handle Ctrl+C themselves
- Added: Backward compatibility verification in Milestone 1 deliverables
- Updated: Tests now verify `return_none_on_eof=True` is passed by ChatSession

**Changes from v2:**
- Fixed: CLI uses `--show-activity/--no-activity` boolean pair (matches existing `start` command)
- Fixed: Input handler modified to return `(None, None)` on EOF vs `("", "")` on empty Enter
- Fixed: Test patch targets now reference correct modules (`orchestrator_auto.input_handler.prompt_with_paste_support`, `orchestrator_auto.chat.ChatSession`)
- Added: Tests for input handler EOF/empty distinction
- Updated: Milestone 1 includes input_handler changes

**Changes from v1:**
- Fixed: Use `BaseAgent` directly via `create_chat_agent()` factory (not `ExecutorAgent`)
- Fixed: `/model` explicitly resets context (documented behavior)
- Fixed: Testing strategy with mock patterns for interactive components
- Added: TTY detection with `simple_input()` fallback
- Added: `agent.close()` cleanup in all agent recreation paths
