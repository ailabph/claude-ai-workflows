"""
Unit tests for ChatSession class.

Tests the direct chat session functionality including:
- Basic conversation flow
- In-chat commands
- Exit handling
- Agent lifecycle
- Error handling
"""

import pytest
from unittest.mock import patch, MagicMock, ANY, call
from orchestrator_auto.chat import ChatSession


class TestChatSessionInit:
    """Test ChatSession initialization."""

    def test_init_defaults(self):
        """Test default initialization values."""
        session = ChatSession()

        assert session.model_alias == "sonnet"
        assert session.tools_enabled is True
        assert session.show_activity is True
        assert session.system_prompt is None
        assert session.conversation_active is True
        assert session.agent is None

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        custom_prompt = "Custom system prompt"
        session = ChatSession(
            model="opus",
            system_prompt=custom_prompt,
            tools_enabled=False,
            show_activity=False,
        )

        assert session.model_alias == "opus"
        assert session.system_prompt == custom_prompt
        assert session.tools_enabled is False
        assert session.show_activity is False


class TestChatSessionConversation:
    """Test basic conversation flow."""

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    def test_basic_conversation(self, mock_create_agent, mock_input):
        """Test basic send/receive flow."""
        # Setup mock agent
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = "Hello! How can I help?"
        mock_create_agent.return_value = mock_agent

        # Setup mock input sequence: message, then /exit
        mock_input.side_effect = [
            ("Hello", "Hello"),        # First input
            ("/exit", "/exit"),        # Exit command
        ]

        session = ChatSession(model="sonnet")
        session.start()

        # Verify prompt_with_paste_support called with return_none_on_eof=True
        assert mock_input.call_count == 2
        mock_input.assert_called_with("\nYou: ", return_none_on_eof=True)
        mock_agent.send_message.assert_called_once_with("Hello", on_chunk=ANY)
        mock_agent.close.assert_called()  # Cleanup called

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    def test_multiple_messages(self, mock_create_agent, mock_input):
        """Test multiple message exchanges."""
        mock_agent = MagicMock()
        mock_agent.send_message.side_effect = ["Response 1", "Response 2", "Response 3"]
        mock_create_agent.return_value = mock_agent

        mock_input.side_effect = [
            ("Message 1", "Message 1"),
            ("Message 2", "Message 2"),
            ("Message 3", "Message 3"),
            ("/exit", "/exit"),
        ]

        session = ChatSession(model="sonnet")
        session.start()

        assert mock_agent.send_message.call_count == 3
        mock_agent.send_message.assert_any_call("Message 1", on_chunk=ANY)
        mock_agent.send_message.assert_any_call("Message 2", on_chunk=ANY)
        mock_agent.send_message.assert_any_call("Message 3", on_chunk=ANY)


class TestChatSessionExitHandling:
    """Test various exit mechanisms."""

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    def test_eof_exits(self, mock_create_agent, mock_input):
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
    def test_ctrl_c_exits(self, mock_create_agent, mock_input):
        """Test Ctrl+C exits gracefully via KeyboardInterrupt."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        # Ctrl+C raises KeyboardInterrupt
        mock_input.side_effect = KeyboardInterrupt()

        session = ChatSession(model="sonnet")
        session.start()  # Should not raise - caught by try/except in start()

        mock_agent.send_message.assert_not_called()
        mock_agent.close.assert_called()  # Cleanup still called

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    def test_empty_reprompts(self, mock_create_agent, mock_input):
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


class TestChatSessionCommands:
    """Test in-chat commands."""

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    def test_exit_command(self, mock_create_agent, mock_input):
        """Test /exit command."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_input.return_value = ("/exit", "/exit")

        session = ChatSession(model="sonnet")
        session.start()

        assert session.conversation_active is False
        mock_agent.close.assert_called()

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    def test_quit_command(self, mock_create_agent, mock_input):
        """Test /quit command."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_input.return_value = ("/quit", "/quit")

        session = ChatSession(model="sonnet")
        session.start()

        assert session.conversation_active is False
        mock_agent.close.assert_called()

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    def test_help_command(self, mock_create_agent, mock_input):
        """Test /help command."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_input.side_effect = [
            ("/help", "/help"),
            ("/exit", "/exit"),
        ]

        session = ChatSession(model="sonnet")
        with patch('orchestrator_auto.chat.click.echo') as mock_echo:
            session.start()

            # Verify help was printed
            assert any('/exit' in str(call) for call in mock_echo.call_args_list)

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    def test_clear_command(self, mock_create_agent, mock_input):
        """Test /clear command recreates agent."""
        mock_agent1 = MagicMock()
        mock_agent2 = MagicMock()
        mock_create_agent.side_effect = [mock_agent1, mock_agent2, MagicMock()]

        mock_input.side_effect = [
            ("/clear", "/clear"),
            ("/exit", "/exit"),
        ]

        session = ChatSession(model="sonnet")
        session.start()

        # Verify old agent was closed
        mock_agent1.close.assert_called()
        # Verify new agent was created (initial + after /clear)
        assert mock_create_agent.call_count >= 2

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    @patch('orchestrator_auto.chat.get_executor_model')
    def test_model_command(self, mock_get_model, mock_create_agent, mock_input):
        """Test /model command switches model."""
        mock_agent1 = MagicMock()
        mock_agent2 = MagicMock()
        mock_create_agent.side_effect = [mock_agent1, mock_agent2, MagicMock()]

        mock_get_model.side_effect = [
            "claude-sonnet-4-5-20250929",
            "claude-opus-4-5-20251101",
            "claude-sonnet-4-5-20250929",
        ]

        mock_input.side_effect = [
            ("/model opus", "/model opus"),
            ("/exit", "/exit"),
        ]

        session = ChatSession(model="sonnet")
        session.start()

        # Verify old agent was closed
        mock_agent1.close.assert_called()
        # Verify new agent was created
        assert mock_create_agent.call_count >= 2

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    def test_unknown_command(self, mock_create_agent, mock_input):
        """Test unknown commands show error."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_input.side_effect = [
            ("/unknown", "/unknown"),
            ("/exit", "/exit"),
        ]

        session = ChatSession(model="sonnet")
        with patch('orchestrator_auto.chat.click.echo') as mock_echo:
            session.start()

            # Verify error was shown
            echo_calls = [str(call) for call in mock_echo.call_args_list]
            assert any('unknown' in str(call).lower() for call in echo_calls)


class TestChatSessionAgentLifecycle:
    """Test agent creation and cleanup."""

    @patch('orchestrator_auto.chat.create_chat_agent')
    def test_create_agent_with_tools_enabled(self, mock_create_agent):
        """Test agent created with tools when enabled."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        session = ChatSession(model="sonnet", tools_enabled=True)
        session._create_agent()

        # Verify create_chat_agent called with DEFAULT_TOOLS
        from orchestrator_auto.agents import DEFAULT_TOOLS
        mock_create_agent.assert_called_once()
        call_kwargs = mock_create_agent.call_args[1]
        assert call_kwargs['allowed_tools'] == DEFAULT_TOOLS

    @patch('orchestrator_auto.chat.create_chat_agent')
    def test_create_agent_with_tools_disabled(self, mock_create_agent):
        """Test agent created without tools when disabled."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        session = ChatSession(model="sonnet", tools_enabled=False)
        session._create_agent()

        # Verify create_chat_agent called with empty tools list
        mock_create_agent.assert_called_once()
        call_kwargs = mock_create_agent.call_args[1]
        assert call_kwargs['allowed_tools'] == []

    @patch('orchestrator_auto.chat.create_chat_agent')
    def test_create_agent_closes_old_agent(self, mock_create_agent):
        """Test that creating new agent closes old one."""
        mock_agent1 = MagicMock()
        mock_agent2 = MagicMock()
        mock_create_agent.side_effect = [mock_agent1, mock_agent2]

        session = ChatSession(model="sonnet")
        session._create_agent()  # Create first agent
        session._create_agent()  # Create second agent

        # Verify first agent was closed
        mock_agent1.close.assert_called_once()

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    def test_cleanup_called_on_exit(self, mock_create_agent, mock_input):
        """Test cleanup is called when session ends."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_input.return_value = ("/exit", "/exit")

        session = ChatSession(model="sonnet")
        session.start()

        # Verify cleanup was called
        mock_agent.close.assert_called()


class TestChatSessionActivityIndicator:
    """Test streaming activity indicator integration."""

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    @patch('orchestrator_auto.chat.StreamingIndicator')
    def test_activity_indicator_enabled(self, mock_indicator_class, mock_create_agent, mock_input):
        """Test activity indicator created when enabled."""
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = "Response"
        mock_create_agent.return_value = mock_agent

        mock_indicator = MagicMock()
        mock_indicator_class.return_value = mock_indicator

        mock_input.side_effect = [
            ("Hello", "Hello"),
            ("/exit", "/exit"),
        ]

        session = ChatSession(model="sonnet", show_activity=True)
        session.start()

        # Verify indicator was created
        mock_indicator_class.assert_called_once()
        # Verify indicator.finish() was called
        mock_indicator.finish.assert_called()

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    @patch('orchestrator_auto.chat.StreamingIndicator')
    def test_activity_indicator_disabled(self, mock_indicator_class, mock_create_agent, mock_input):
        """Test no activity indicator when disabled."""
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = "Response"
        mock_create_agent.return_value = mock_agent

        mock_input.side_effect = [
            ("Hello", "Hello"),
            ("/exit", "/exit"),
        ]

        session = ChatSession(model="sonnet", show_activity=False)
        session.start()

        # Verify no indicator was created
        mock_indicator_class.assert_not_called()


class TestChatSessionEdgeCases:
    """Test edge cases and error conditions."""

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    def test_whitespace_only_input_reprompts(self, mock_create_agent, mock_input):
        """Test whitespace-only input reprompts."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_input.side_effect = [
            ("   ", "   "),     # Whitespace only
            ("/exit", "/exit"),
        ]

        session = ChatSession(model="sonnet")
        session.start()

        # Verify no message sent to agent
        mock_agent.send_message.assert_not_called()

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    @patch('orchestrator_auto.chat.get_executor_model')
    def test_invalid_model_shows_error(self, mock_get_model, mock_create_agent, mock_input):
        """Test invalid model alias shows error."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        # Simulate ValueError for invalid model
        mock_get_model.side_effect = [
            "claude-sonnet-4-5-20250929",  # Initial
            ValueError("Invalid model"),    # /model invalid
        ]

        mock_input.side_effect = [
            ("/model invalid", "/model invalid"),
            ("/exit", "/exit"),
        ]

        session = ChatSession(model="sonnet")
        with patch('orchestrator_auto.chat.click.secho') as mock_secho:
            session.start()

            # Verify error was shown
            secho_calls = [str(call) for call in mock_secho.call_args_list]
            assert any('unknown model' in str(call).lower() for call in secho_calls)

    @patch('orchestrator_auto.input_handler.prompt_with_paste_support')
    @patch('orchestrator_auto.chat.create_chat_agent')
    def test_model_command_without_argument(self, mock_create_agent, mock_input):
        """Test /model without argument shows usage."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_input.side_effect = [
            ("/model", "/model"),
            ("/exit", "/exit"),
        ]

        session = ChatSession(model="sonnet")
        with patch('orchestrator_auto.chat.click.echo') as mock_echo:
            session.start()

            # Verify usage was shown
            echo_calls = [str(call) for call in mock_echo.call_args_list]
            assert any('usage' in str(call).lower() for call in echo_calls)
