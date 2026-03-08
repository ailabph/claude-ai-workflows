"""
CLI integration tests for the chat-mode command.
"""

import pytest

pytest.importorskip("textual")

from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from pathlib import Path

from orchestrator_auto.cli import cli


class TestChatModeCommand:
    """Test the chat-mode CLI command."""

    def test_chat_mode_command_exists(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["chat-mode", "--help"])
        assert result.exit_code == 0
        assert "chat" in result.output.lower()

    def test_chat_mode_default_model_is_opus(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["chat-mode", "--help"])
        assert "opus" in result.output

    def test_chat_mode_flags_accepted(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["chat-mode", "--help"])
        for flag in ["--tui", "--verbose", "--model", "--system-prompt", "--no-tools"]:
            assert flag in result.output

    @patch("orchestrator_auto.chat.ChatSession")
    @patch("orchestrator_auto.cli.display_auth_info")
    def test_chat_mode_non_tui_calls_chat_session(self, mock_auth, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        runner = CliRunner()
        result = runner.invoke(cli, ["chat-mode"])

        mock_session_cls.assert_called_once()
        call_kwargs = mock_session_cls.call_args
        # Should use PLANNER_CHAT_PROMPT when no --system-prompt given
        from orchestrator_auto.prompts import PLANNER_CHAT_PROMPT
        assert call_kwargs.kwargs.get("system_prompt") == PLANNER_CHAT_PROMPT
        mock_session.start.assert_called_once()

    @patch("orchestrator_auto.chat.ChatSession")
    @patch("orchestrator_auto.cli.display_auth_info")
    def test_chat_mode_non_tui_no_tools(self, mock_auth, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        runner = CliRunner()
        result = runner.invoke(cli, ["chat-mode", "--no-tools"])

        call_kwargs = mock_session_cls.call_args
        assert call_kwargs.kwargs.get("tools_enabled") is False

    @patch("orchestrator_auto.chat.ChatSession")
    @patch("orchestrator_auto.cli.display_auth_info")
    def test_chat_mode_non_tui_custom_system_prompt(self, mock_auth, mock_session_cls, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Custom prompt")

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        runner = CliRunner()
        result = runner.invoke(cli, ["chat-mode", "--system-prompt", str(prompt_file)])

        call_kwargs = mock_session_cls.call_args
        assert call_kwargs.kwargs.get("system_prompt") == "Custom prompt"

    @patch("orchestrator_auto.chat.ChatSession")
    @patch("orchestrator_auto.cli.display_auth_info")
    def test_chat_mode_non_tui_model_passed(self, mock_auth, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        runner = CliRunner()
        result = runner.invoke(cli, ["chat-mode", "-m", "haiku"])

        call_kwargs = mock_session_cls.call_args
        assert call_kwargs.kwargs.get("model") == "haiku"
