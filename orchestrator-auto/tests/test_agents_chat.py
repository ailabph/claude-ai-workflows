"""
Unit tests for create_chat_agent factory function.

Tests the factory function that creates chat-specific agents.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from orchestrator_auto.agents import create_chat_agent, DEFAULT_TOOLS, BaseAgent


class TestCreateChatAgent:
    """Test create_chat_agent factory function."""

    @patch('orchestrator_auto.agents.BaseAgent')
    def test_creates_base_agent(self, mock_base_agent_class):
        """Test that create_chat_agent creates a BaseAgent."""
        mock_agent = MagicMock()
        mock_base_agent_class.return_value = mock_agent

        result = create_chat_agent()

        # Verify BaseAgent was instantiated
        mock_base_agent_class.assert_called_once()
        assert result == mock_agent

    @patch('orchestrator_auto.agents.BaseAgent')
    def test_default_parameters(self, mock_base_agent_class):
        """Test default parameters are correct."""
        from orchestrator_auto.prompts import DEFAULT_CHAT_PROMPT

        create_chat_agent()

        # Verify default parameters
        call_kwargs = mock_base_agent_class.call_args[1]
        assert call_kwargs['system_prompt'] == DEFAULT_CHAT_PROMPT
        assert call_kwargs['allowed_tools'] == DEFAULT_TOOLS
        assert call_kwargs['model'] == "claude-sonnet-4-5-20250929"
        assert call_kwargs['session_id'] == "chat"
        assert call_kwargs['cwd'] is None

    @patch('orchestrator_auto.agents.BaseAgent')
    def test_custom_model(self, mock_base_agent_class):
        """Test with custom model."""
        custom_model = "claude-opus-4-5-20251101"

        create_chat_agent(model=custom_model)

        call_kwargs = mock_base_agent_class.call_args[1]
        assert call_kwargs['model'] == custom_model

    @patch('orchestrator_auto.agents.BaseAgent')
    def test_custom_system_prompt(self, mock_base_agent_class):
        """Test with custom system prompt."""
        custom_prompt = "You are a Python expert."

        create_chat_agent(system_prompt=custom_prompt)

        call_kwargs = mock_base_agent_class.call_args[1]
        assert call_kwargs['system_prompt'] == custom_prompt

    @patch('orchestrator_auto.agents.BaseAgent')
    def test_custom_allowed_tools(self, mock_base_agent_class):
        """Test with custom allowed_tools."""
        custom_tools = ["Read", "Grep"]

        create_chat_agent(allowed_tools=custom_tools)

        call_kwargs = mock_base_agent_class.call_args[1]
        assert call_kwargs['allowed_tools'] == custom_tools

    @patch('orchestrator_auto.agents.BaseAgent')
    def test_no_tools(self, mock_base_agent_class):
        """Test with no tools (empty list)."""
        create_chat_agent(allowed_tools=[])

        call_kwargs = mock_base_agent_class.call_args[1]
        assert call_kwargs['allowed_tools'] == []

    @patch('orchestrator_auto.agents.BaseAgent')
    def test_custom_cwd(self, mock_base_agent_class):
        """Test with custom working directory."""
        custom_cwd = Path("/custom/path")

        create_chat_agent(cwd=custom_cwd)

        call_kwargs = mock_base_agent_class.call_args[1]
        assert call_kwargs['cwd'] == custom_cwd

    @patch('orchestrator_auto.agents.BaseAgent')
    def test_none_allowed_tools_uses_default(self, mock_base_agent_class):
        """Test that allowed_tools=None uses DEFAULT_TOOLS."""
        create_chat_agent(allowed_tools=None)

        call_kwargs = mock_base_agent_class.call_args[1]
        assert call_kwargs['allowed_tools'] == DEFAULT_TOOLS

    @patch('orchestrator_auto.agents.BaseAgent')
    def test_none_system_prompt_uses_default(self, mock_base_agent_class):
        """Test that system_prompt=None uses DEFAULT_CHAT_PROMPT."""
        from orchestrator_auto.prompts import DEFAULT_CHAT_PROMPT

        create_chat_agent(system_prompt=None)

        call_kwargs = mock_base_agent_class.call_args[1]
        assert call_kwargs['system_prompt'] == DEFAULT_CHAT_PROMPT

    @patch('orchestrator_auto.agents.BaseAgent')
    def test_session_id_always_chat(self, mock_base_agent_class):
        """Test that session_id is always 'chat'."""
        # Try various parameters
        create_chat_agent(model="opus")
        call_kwargs = mock_base_agent_class.call_args[1]
        assert call_kwargs['session_id'] == "chat"

        create_chat_agent(model="sonnet")
        call_kwargs = mock_base_agent_class.call_args[1]
        assert call_kwargs['session_id'] == "chat"

    @patch('orchestrator_auto.agents.BaseAgent')
    def test_all_custom_parameters(self, mock_base_agent_class):
        """Test with all custom parameters."""
        custom_model = "claude-opus-4-5-20251101"
        custom_prompt = "Custom prompt"
        custom_tools = ["Read"]
        custom_cwd = Path("/test")

        create_chat_agent(
            model=custom_model,
            system_prompt=custom_prompt,
            allowed_tools=custom_tools,
            cwd=custom_cwd,
        )

        call_kwargs = mock_base_agent_class.call_args[1]
        assert call_kwargs['model'] == custom_model
        assert call_kwargs['system_prompt'] == custom_prompt
        assert call_kwargs['allowed_tools'] == custom_tools
        assert call_kwargs['cwd'] == custom_cwd
        assert call_kwargs['session_id'] == "chat"


class TestCreateChatAgentVsExecutorAgent:
    """Test that create_chat_agent differs from ExecutorAgent."""

    def test_uses_default_chat_prompt_not_executor_prompt(self):
        """Test that chat agent uses DEFAULT_CHAT_PROMPT, not EXECUTOR_SYSTEM_PROMPT."""
        from orchestrator_auto.prompts import DEFAULT_CHAT_PROMPT, EXECUTOR_SYSTEM_PROMPT

        # Verify prompts are different
        assert DEFAULT_CHAT_PROMPT != EXECUTOR_SYSTEM_PROMPT

        with patch('orchestrator_auto.agents.BaseAgent') as mock_base:
            create_chat_agent()

            call_kwargs = mock_base.call_args[1]
            assert call_kwargs['system_prompt'] == DEFAULT_CHAT_PROMPT
            assert call_kwargs['system_prompt'] != EXECUTOR_SYSTEM_PROMPT

    def test_allows_custom_tools_unlike_executor(self):
        """Test that chat agent can have custom tool lists."""
        custom_tools = ["Read", "Grep"]  # Subset of tools

        with patch('orchestrator_auto.agents.BaseAgent') as mock_base:
            create_chat_agent(allowed_tools=custom_tools)

            call_kwargs = mock_base.call_args[1]
            assert call_kwargs['allowed_tools'] == custom_tools

    def test_allows_no_tools_unlike_executor(self):
        """Test that chat agent can have no tools."""
        with patch('orchestrator_auto.agents.BaseAgent') as mock_base:
            create_chat_agent(allowed_tools=[])

            call_kwargs = mock_base.call_args[1]
            assert call_kwargs['allowed_tools'] == []

    def test_allows_custom_system_prompt_unlike_executor(self):
        """Test that chat agent accepts custom system prompts."""
        custom_prompt = "You are a helpful coding assistant."

        with patch('orchestrator_auto.agents.BaseAgent') as mock_base:
            create_chat_agent(system_prompt=custom_prompt)

            call_kwargs = mock_base.call_args[1]
            assert call_kwargs['system_prompt'] == custom_prompt
