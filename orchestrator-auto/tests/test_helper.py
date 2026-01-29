"""
CLI integration tests for the helper command.

Tests that the CLI properly instantiates the helper agent with correct parameters
and handles various input formats.
"""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock, Mock
from pathlib import Path


class TestHelperCommand:
    """Test the helper CLI command."""

    def test_helper_command_exists(self):
        """Test that helper command is registered."""
        from orchestrator_auto.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ['helper', '--help'])

        assert result.exit_code == 0
        assert 'helper' in result.output.lower()

    @patch('orchestrator_auto.resources.load_docs')
    @patch('orchestrator_auto.agents.create_chat_agent')
    @patch('orchestrator_auto.auth.detect_auth')
    def test_helper_with_quoted_question(self, mock_auth, mock_create_agent, mock_load_docs):
        """Test helper command with quoted question."""
        # Setup mocks
        mock_auth.return_value = Mock(is_configured=True)
        mock_load_docs.return_value = ("# Documentation content", ["README.md"])
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = "Test response"
        mock_create_agent.return_value = mock_agent

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['helper', 'how do I start a workflow?'])

        assert result.exit_code == 0
        # Verify agent was created with allowed_tools=[]
        mock_create_agent.assert_called_once()
        call_kwargs = mock_create_agent.call_args[1]
        assert call_kwargs['allowed_tools'] == []
        # Verify send_message was called with the question
        mock_agent.send_message.assert_called_once_with('how do I start a workflow?')

    @patch('orchestrator_auto.resources.load_docs')
    @patch('orchestrator_auto.agents.create_chat_agent')
    @patch('orchestrator_auto.auth.detect_auth')
    def test_helper_with_unquoted_question(self, mock_auth, mock_create_agent, mock_load_docs):
        """Test helper command with unquoted multi-word question (nargs=-1)."""
        # Setup mocks
        mock_auth.return_value = Mock(is_configured=True)
        mock_load_docs.return_value = ("# Documentation content", ["README.md"])
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = "Test response"
        mock_create_agent.return_value = mock_agent

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        # Test unquoted question
        result = runner.invoke(cli, ['helper', 'how', 'do', 'I', 'resume'])

        assert result.exit_code == 0
        # Verify the words were joined correctly
        mock_agent.send_message.assert_called_once_with('how do I resume')

    @patch('orchestrator_auto.resources.load_docs')
    @patch('orchestrator_auto.agents.create_chat_agent')
    @patch('orchestrator_auto.auth.detect_auth')
    def test_helper_model_alias_resolution(self, mock_auth, mock_create_agent, mock_load_docs):
        """Test that model aliases are resolved via resolve_model()."""
        # Setup mocks
        mock_auth.return_value = Mock(is_configured=True)
        mock_load_docs.return_value = ("# Documentation content", ["README.md"])
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = "Test response"
        mock_create_agent.return_value = mock_agent

        from orchestrator_auto.cli import cli
        runner = CliRunner()

        # Test sonnet alias
        result = runner.invoke(cli, ['helper', 'test', '-m', 'sonnet'])
        call_kwargs = mock_create_agent.call_args[1]
        assert call_kwargs['model'] == 'claude-sonnet-4-5-20250929'

        mock_create_agent.reset_mock()

        # Test opus alias
        result = runner.invoke(cli, ['helper', 'test', '-m', 'opus'])
        call_kwargs = mock_create_agent.call_args[1]
        assert call_kwargs['model'] == 'claude-opus-4-5-20251101'

    @patch('orchestrator_auto.resources.load_docs')
    @patch('orchestrator_auto.agents.create_chat_agent')
    @patch('orchestrator_auto.auth.detect_auth')
    def test_helper_full_model_id(self, mock_auth, mock_create_agent, mock_load_docs):
        """Test helper with full model ID instead of alias."""
        # Setup mocks
        mock_auth.return_value = Mock(is_configured=True)
        mock_load_docs.return_value = ("# Documentation content", ["README.md"])
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = "Test response"
        mock_create_agent.return_value = mock_agent

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['helper', 'test', '-m', 'claude-sonnet-4-5-20250929'])

        call_kwargs = mock_create_agent.call_args[1]
        assert call_kwargs['model'] == 'claude-sonnet-4-5-20250929'

    @patch('orchestrator_auto.resources.load_docs')
    @patch('orchestrator_auto.agents.create_chat_agent')
    @patch('orchestrator_auto.auth.detect_auth')
    def test_helper_verbose_flag(self, mock_auth, mock_create_agent, mock_load_docs):
        """Test that verbose flag outputs included filenames."""
        # Setup mocks
        mock_auth.return_value = Mock(is_configured=True)
        mock_load_docs.return_value = (
            "# Documentation content",
            ["README.md", "CLI_REFERENCE.md", "CONFIGURATION.md", "TROUBLESHOOTING.md"]
        )
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = "Test response"
        mock_create_agent.return_value = mock_agent

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['helper', 'test', '-v'])

        assert result.exit_code == 0
        # Verify included files are shown
        assert 'Including:' in result.output
        assert 'README.md' in result.output
        assert 'CLI_REFERENCE.md' in result.output
        assert 'CONFIGURATION.md' in result.output
        assert 'TROUBLESHOOTING.md' in result.output

    @patch('orchestrator_auto.resources.load_docs')
    @patch('orchestrator_auto.auth.detect_auth')
    def test_helper_missing_auth(self, mock_auth, mock_load_docs):
        """Test that missing auth shows error message and exits."""
        # Setup mocks
        mock_auth.return_value = Mock(is_configured=False)
        mock_load_docs.return_value = ("# Documentation content", ["README.md"])

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['helper', 'test'])

        # Should show auth error message
        assert 'No authentication detected' in result.output
        assert 'ANTHROPIC_API_KEY' in result.output

    @patch('orchestrator_auto.resources.load_docs')
    @patch('orchestrator_auto.agents.create_chat_agent')
    @patch('orchestrator_auto.auth.detect_auth')
    def test_helper_system_prompt_includes_docs(self, mock_auth, mock_create_agent, mock_load_docs):
        """Test that system prompt includes documentation content."""
        # Setup mocks
        mock_auth.return_value = Mock(is_configured=True)
        test_docs = "# Test Documentation\nThis is test content."
        mock_load_docs.return_value = (test_docs, ["README.md"])
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = "Test response"
        mock_create_agent.return_value = mock_agent

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['helper', 'test question'])

        # Verify system prompt includes docs content
        call_kwargs = mock_create_agent.call_args[1]
        system_prompt = call_kwargs['system_prompt']
        assert test_docs in system_prompt
        assert '<documentation>' in system_prompt
        assert '</documentation>' in system_prompt

    @patch('orchestrator_auto.resources.load_docs')
    @patch('orchestrator_auto.agents.create_chat_agent')
    @patch('orchestrator_auto.auth.detect_auth')
    def test_helper_allowed_tools_empty(self, mock_auth, mock_create_agent, mock_load_docs):
        """Test that helper agent is created with allowed_tools=[] for safety."""
        # Setup mocks
        mock_auth.return_value = Mock(is_configured=True)
        mock_load_docs.return_value = ("# Documentation content", ["README.md"])
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = "Test response"
        mock_create_agent.return_value = mock_agent

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['helper', 'test'])

        # Verify allowed_tools is empty list (no file system access)
        call_kwargs = mock_create_agent.call_args[1]
        assert call_kwargs['allowed_tools'] == []

    @patch('orchestrator_auto.resources.load_docs')
    @patch('orchestrator_auto.agents.create_chat_agent')
    @patch('orchestrator_auto.auth.detect_auth')
    def test_helper_default_model(self, mock_auth, mock_create_agent, mock_load_docs):
        """Test that helper uses haiku as default model."""
        # Setup mocks
        mock_auth.return_value = Mock(is_configured=True)
        mock_load_docs.return_value = ("# Documentation content", ["README.md"])
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = "Test response"
        mock_create_agent.return_value = mock_agent

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['helper', 'test'])

        # Verify default model is haiku (resolved to full ID)
        call_kwargs = mock_create_agent.call_args[1]
        assert call_kwargs['model'] == 'claude-3-5-haiku-20241022'

    @patch('orchestrator_auto.resources.load_docs')
    @patch('orchestrator_auto.agents.create_chat_agent')
    @patch('orchestrator_auto.auth.detect_auth')
    def test_helper_exception_handling(self, mock_auth, mock_create_agent, mock_load_docs):
        """Test that helper handles agent exceptions gracefully."""
        # Setup mocks
        mock_auth.return_value = Mock(is_configured=True)
        mock_load_docs.return_value = ("# Documentation content", ["README.md"])
        mock_agent = MagicMock()
        mock_agent.send_message.side_effect = Exception("Test error")
        mock_create_agent.return_value = mock_agent

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['helper', 'test'])

        # Should show error message
        assert 'Error:' in result.output
        assert 'Test error' in result.output

    def test_helper_in_main_help(self):
        """Test that helper command appears in main CLI help."""
        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])

        assert result.exit_code == 0
        assert 'helper' in result.output.lower()


class TestHelperCommandEdgeCases:
    """Test edge cases for helper command."""

    def test_helper_requires_question(self):
        """Test that helper command requires at least one question word."""
        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['helper'])

        # Should fail with missing argument error
        assert result.exit_code != 0
        assert 'Missing argument' in result.output or 'QUESTION' in result.output

    @patch('orchestrator_auto.resources.load_docs')
    @patch('orchestrator_auto.agents.create_chat_agent')
    @patch('orchestrator_auto.auth.detect_auth')
    def test_helper_with_single_word_question(self, mock_auth, mock_create_agent, mock_load_docs):
        """Test helper with single word question."""
        # Setup mocks
        mock_auth.return_value = Mock(is_configured=True)
        mock_load_docs.return_value = ("# Documentation content", ["README.md"])
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = "Test response"
        mock_create_agent.return_value = mock_agent

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['helper', 'help'])

        assert result.exit_code == 0
        mock_agent.send_message.assert_called_once_with('help')

    @patch('orchestrator_auto.resources.load_docs')
    @patch('orchestrator_auto.agents.create_chat_agent')
    @patch('orchestrator_auto.auth.detect_auth')
    def test_helper_with_special_characters(self, mock_auth, mock_create_agent, mock_load_docs):
        """Test helper with special characters in question."""
        # Setup mocks
        mock_auth.return_value = Mock(is_configured=True)
        mock_load_docs.return_value = ("# Documentation content", ["README.md"])
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = "Test response"
        mock_create_agent.return_value = mock_agent

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['helper', 'what is --tui flag?'])

        assert result.exit_code == 0
        mock_agent.send_message.assert_called_once_with('what is --tui flag?')
