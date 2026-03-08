"""Tests for ChatBackend — callback-driven agent wrapper for TUI chat."""

from unittest.mock import patch, MagicMock, call
import pytest

from orchestrator_auto.chat_backend import ChatBackend


@pytest.fixture
def mock_agent():
    """Create a mock BaseAgent."""
    agent = MagicMock()
    agent.send_message.return_value = "Hello from the agent"
    agent.close.return_value = None
    return agent


@pytest.fixture
def mock_create_agent(mock_agent):
    """Patch create_planner_chat_agent to return mock_agent."""
    with patch(
        "orchestrator_auto.chat_backend.create_planner_chat_agent",
        return_value=mock_agent,
    ) as factory:
        yield factory


class TestChatBackendSend:
    """Tests for ChatBackend.send()."""

    def test_send_returns_full_response(self, mock_create_agent, mock_agent):
        backend = ChatBackend(model="opus")
        result = backend.send("Hello")

        assert result == "Hello from the agent"
        mock_agent.send_message.assert_called_once()

    def test_send_fires_on_chunk_callback(self, mock_create_agent, mock_agent):
        chunks = []

        def on_chunk(chunk):
            chunks.append(chunk)

        backend = ChatBackend(model="opus", on_chunk=on_chunk)
        backend.send("Hello")

        # on_chunk is passed through to agent.send_message
        _, kwargs = mock_agent.send_message.call_args
        assert kwargs["on_chunk"] is on_chunk

    def test_send_fires_on_response_complete(self, mock_create_agent, mock_agent):
        completed = []

        def on_response_complete(text, usage):
            completed.append((text, usage))

        backend = ChatBackend(model="opus", on_response_complete=on_response_complete)
        backend.send("Hello")

        assert len(completed) == 1
        assert completed[0][0] == "Hello from the agent"
        # Usage dict captured from on_token_usage callback
        assert isinstance(completed[0][1], dict)

    def test_send_captures_token_usage(self, mock_create_agent, mock_agent):
        """Token usage from agent is forwarded to on_response_complete."""
        completed = []

        def on_response_complete(text, usage):
            completed.append((text, usage))

        backend = ChatBackend(model="opus", on_response_complete=on_response_complete)

        # Simulate the agent calling on_token_usage during send.
        # send() monkey-patches agent.on_token_usage with a request-local lambda,
        # so we call it through the agent's attribute at send time.
        def fake_send(content, on_chunk=None):
            mock_agent.on_token_usage({"input_tokens": 100, "output_tokens": 50})
            return "Response with usage"

        mock_agent.send_message.side_effect = fake_send

        backend.send("Hello")

        assert completed[0][1] == {"input_tokens": 100, "output_tokens": 50}

    def test_send_without_callbacks(self, mock_create_agent, mock_agent):
        """send() works with no callbacks set."""
        backend = ChatBackend(model="opus")
        result = backend.send("Hello")
        assert result == "Hello from the agent"


class TestChatBackendNotification:
    """Tests for notification wiring."""

    def test_on_notification_passed_to_factory(self, mock_create_agent):
        notifications = []

        def on_notification(n):
            notifications.append(n)

        backend = ChatBackend(model="opus", on_notification=on_notification)
        backend.send("Hello")  # triggers lazy agent creation

        # The factory receives a forwarding lambda; verify it delegates correctly
        _, kwargs = mock_create_agent.call_args
        assert kwargs["on_notification"] is not None
        # Call the forwarding lambda and verify it reaches our callback
        kwargs["on_notification"]({"message": "test"})
        assert notifications == [{"message": "test"}]


class TestChatBackendReset:
    """Tests for ChatBackend.reset()."""

    def test_reset_clears_agent(self, mock_create_agent, mock_agent):
        backend = ChatBackend(model="opus")
        backend.send("Hello")  # creates agent

        assert backend._agent is not None

        backend.reset()

        assert backend._agent is None
        mock_agent.close.assert_called_once()

    def test_reset_allows_new_agent_on_next_send(self, mock_create_agent, mock_agent):
        backend = ChatBackend(model="opus")
        backend.send("Hello")
        backend.reset()

        # Next send creates a new agent
        new_agent = MagicMock()
        new_agent.send_message.return_value = "New response"
        mock_create_agent.return_value = new_agent

        result = backend.send("Hello again")
        assert result == "New response"
        assert mock_create_agent.call_count == 2

    def test_reset_without_agent_is_noop(self, mock_create_agent):
        backend = ChatBackend(model="opus")
        backend.reset()  # should not raise


class TestChatBackendModelResolution:
    """Tests for model alias resolution."""

    def test_model_alias_passed_to_factory(self, mock_create_agent):
        backend = ChatBackend(model="opus")
        backend.send("Hello")

        _, kwargs = mock_create_agent.call_args
        assert kwargs["model"] == "opus"

    def test_custom_model_passed_to_factory(self, mock_create_agent):
        backend = ChatBackend(model="sonnet")
        backend.send("Hello")

        _, kwargs = mock_create_agent.call_args
        assert kwargs["model"] == "sonnet"


class TestChatBackendToolsEnabled:
    """Tests for tools_enabled flag."""

    def test_tools_enabled_passes_none(self, mock_create_agent):
        """tools_enabled=True passes None (factory uses DEFAULT_TOOLS)."""
        backend = ChatBackend(model="opus", tools_enabled=True)
        backend.send("Hello")

        _, kwargs = mock_create_agent.call_args
        assert kwargs["allowed_tools"] is None

    def test_tools_disabled_passes_empty_list(self, mock_create_agent):
        """tools_enabled=False passes [] to disable all tools."""
        backend = ChatBackend(model="opus", tools_enabled=False)
        backend.send("Hello")

        _, kwargs = mock_create_agent.call_args
        assert kwargs["allowed_tools"] == []

    def test_custom_system_prompt_passed(self, mock_create_agent):
        backend = ChatBackend(model="opus", system_prompt="Custom prompt")
        backend.send("Hello")

        _, kwargs = mock_create_agent.call_args
        assert kwargs["system_prompt"] == "Custom prompt"
