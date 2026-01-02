"""
Direct chat session handler for orchestrator-auto.

Provides a stateless chat interface with Claude without the full
orchestration workflow. Useful for quick questions, ad-hoc tasks,
or interactive coding sessions.
"""

import sys
import click
from typing import Optional
from pathlib import Path

from .agents import create_chat_agent, BaseAgent, DEFAULT_TOOLS
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
        """
        Initialize a chat session.

        Args:
            model: Model alias (opus, sonnet, haiku)
            system_prompt: Custom system prompt text
            tools_enabled: Whether to enable file/bash tools
            show_activity: Whether to show streaming activity indicator
        """
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

        allowed_tools = DEFAULT_TOOLS if self.tools_enabled else []

        self.agent = create_chat_agent(
            model=self.model,
            system_prompt=self.system_prompt,
            allowed_tools=allowed_tools,
        )

    def _get_input(self) -> Optional[str]:
        """
        Get user input, with TTY-aware fallback.

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
