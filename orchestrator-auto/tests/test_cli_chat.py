"""
CLI integration tests for the chat command.

Tests that the CLI properly instantiates ChatSession with correct parameters.
"""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile


class TestChatCommand:
    """Test the chat CLI command."""

    @patch('orchestrator_auto.chat.ChatSession')
    def test_chat_command_exists(self, mock_session_class):
        """Test that chat command is registered."""
        from orchestrator_auto.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ['chat', '--help'])

        assert result.exit_code == 0
        assert 'chat' in result.output.lower()

    @patch('orchestrator_auto.chat.ChatSession')
    def test_chat_default_options(self, mock_session_class):
        """Test chat command with default options."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['chat'])

        # Verify ChatSession instantiated with defaults
        mock_session_class.assert_called_once_with(
            model='sonnet',
            system_prompt=None,
            tools_enabled=True,
            show_activity=True,
        )
        mock_session.start.assert_called_once()

    @patch('orchestrator_auto.chat.ChatSession')
    def test_chat_with_model_option(self, mock_session_class):
        """Test chat command with -m/--model option."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        from orchestrator_auto.cli import cli
        runner = CliRunner()

        # Test short form
        result = runner.invoke(cli, ['chat', '-m', 'opus'])
        mock_session_class.assert_called_with(
            model='opus',
            system_prompt=None,
            tools_enabled=True,
            show_activity=True,
        )

        mock_session_class.reset_mock()

        # Test long form
        result = runner.invoke(cli, ['chat', '--model', 'haiku'])
        mock_session_class.assert_called_with(
            model='haiku',
            system_prompt=None,
            tools_enabled=True,
            show_activity=True,
        )

    @patch('orchestrator_auto.chat.ChatSession')
    def test_chat_with_system_prompt_file(self, mock_session_class):
        """Test chat command with --system-prompt option."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Create temporary prompt file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Custom test prompt")
            temp_path = f.name

        try:
            from orchestrator_auto.cli import cli
            runner = CliRunner()
            result = runner.invoke(cli, ['chat', '-s', temp_path])

            # Verify system prompt was loaded
            mock_session_class.assert_called_once()
            call_kwargs = mock_session_class.call_args[1]
            assert call_kwargs['system_prompt'] == "Custom test prompt"
            assert call_kwargs['model'] == 'sonnet'
            assert call_kwargs['tools_enabled'] is True
            assert call_kwargs['show_activity'] is True

        finally:
            Path(temp_path).unlink()

    @patch('orchestrator_auto.chat.ChatSession')
    def test_chat_with_no_tools_flag(self, mock_session_class):
        """Test chat command with --no-tools flag."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['chat', '--no-tools'])

        # Verify tools_enabled=False
        mock_session_class.assert_called_once_with(
            model='sonnet',
            system_prompt=None,
            tools_enabled=False,
            show_activity=True,
        )

    @patch('orchestrator_auto.chat.ChatSession')
    def test_chat_with_no_activity_flag(self, mock_session_class):
        """Test chat command with --no-activity flag."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['chat', '--no-activity'])

        # Verify show_activity=False
        mock_session_class.assert_called_once_with(
            model='sonnet',
            system_prompt=None,
            tools_enabled=True,
            show_activity=False,
        )

    @patch('orchestrator_auto.chat.ChatSession')
    def test_chat_with_show_activity_flag(self, mock_session_class):
        """Test chat command with --show-activity flag (explicit)."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['chat', '--show-activity'])

        # Verify show_activity=True
        mock_session_class.assert_called_once_with(
            model='sonnet',
            system_prompt=None,
            tools_enabled=True,
            show_activity=True,
        )

    @patch('orchestrator_auto.chat.ChatSession')
    def test_chat_with_combined_options(self, mock_session_class):
        """Test chat command with multiple options combined."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Create temporary prompt file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test prompt")
            temp_path = f.name

        try:
            from orchestrator_auto.cli import cli
            runner = CliRunner()
            result = runner.invoke(cli, [
                'chat',
                '-m', 'opus',
                '-s', temp_path,
                '--no-tools',
                '--no-activity',
            ])

            # Verify all options passed correctly
            mock_session_class.assert_called_once_with(
                model='opus',
                system_prompt="Test prompt",
                tools_enabled=False,
                show_activity=False,
            )

        finally:
            Path(temp_path).unlink()

    @patch('orchestrator_auto.chat.ChatSession')
    def test_chat_calls_session_start(self, mock_session_class):
        """Test that chat command calls session.start()."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['chat'])

        # Verify start() was called
        mock_session.start.assert_called_once()

    def test_chat_help_shows_options(self):
        """Test that chat --help shows all options."""
        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['chat', '--help'])

        assert result.exit_code == 0
        # Verify all options are documented
        assert '--model' in result.output
        assert '-m' in result.output
        assert '--system-prompt' in result.output
        assert '-s' in result.output
        assert '--no-tools' in result.output
        assert '--show-activity' in result.output
        assert '--no-activity' in result.output

    def test_chat_in_main_help(self):
        """Test that chat command appears in main CLI help."""
        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])

        assert result.exit_code == 0
        assert 'chat' in result.output.lower()


class TestChatCommandEdgeCases:
    """Test edge cases for chat command."""

    def test_chat_with_nonexistent_prompt_file(self):
        """Test that nonexistent prompt file is rejected."""
        from orchestrator_auto.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ['chat', '-s', '/nonexistent/file.txt'])

        # Should fail validation
        assert result.exit_code != 0
        assert 'does not exist' in result.output.lower() or 'invalid' in result.output.lower()

    @patch('orchestrator_auto.chat.ChatSession')
    def test_chat_with_empty_prompt_file(self, mock_session_class):
        """Test chat with empty prompt file."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Create empty prompt file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            temp_path = f.name

        try:
            from orchestrator_auto.cli import cli
            runner = CliRunner()
            result = runner.invoke(cli, ['chat', '-s', temp_path])

            # Should work with empty string
            mock_session_class.assert_called_once()
            call_kwargs = mock_session_class.call_args[1]
            assert call_kwargs['system_prompt'] == ""

        finally:
            Path(temp_path).unlink()

    @patch('orchestrator_auto.chat.ChatSession')
    def test_chat_preserves_model_case(self, mock_session_class):
        """Test that model alias case is preserved."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        from orchestrator_auto.cli import cli
        runner = CliRunner()

        # Test different cases
        for model_arg in ['opus', 'OPUS', 'Opus']:
            mock_session_class.reset_mock()
            result = runner.invoke(cli, ['chat', '-m', model_arg])
            call_kwargs = mock_session_class.call_args[1]
            assert call_kwargs['model'] == model_arg
