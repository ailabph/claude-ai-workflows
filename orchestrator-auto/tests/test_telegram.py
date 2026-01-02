"""
Tests for Telegram integration module.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto.telegram import TelegramNotifier, TelegramListener, HTTPX_AVAILABLE


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.Client."""
    with patch("orchestrator_auto.telegram.httpx.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        yield mock_client


class TestTelegramNotifier:
    """Tests for TelegramNotifier class."""

    def test_send_ping_returns_message_id_on_success(self, mock_httpx_client):
        """send_ping() returns message_id on success."""
        # Setup mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 12345}
        }
        mock_httpx_client.post.return_value = mock_response

        # Create notifier
        notifier = TelegramNotifier(
            bot_token="test_token",
            chat_id="test_chat_id"
        )

        # Send ping
        message_id = notifier.send_ping()

        # Verify
        assert message_id == 12345
        mock_httpx_client.post.assert_called_once()
        call_args = mock_httpx_client.post.call_args
        assert "sendMessage" in call_args[0][0]
        assert "🏓 *Ping!*" in call_args[1]["json"]["text"]

    def test_send_ping_returns_none_on_http_error(self, mock_httpx_client):
        """send_ping() returns None on HTTP error."""
        # Setup mock to raise HTTP error
        mock_httpx_client.post.side_effect = Exception("Connection error")

        # Create notifier
        notifier = TelegramNotifier(
            bot_token="test_token",
            chat_id="test_chat_id"
        )

        # Send ping
        message_id = notifier.send_ping()

        # Verify
        assert message_id is None

    def test_send_ping_returns_none_on_api_error(self, mock_httpx_client):
        """send_ping() returns None when API returns ok=false."""
        # Setup mock response with API error
        mock_response = Mock()
        mock_response.json.return_value = {
            "ok": False,
            "description": "Bad Request: chat not found"
        }
        mock_httpx_client.post.return_value = mock_response

        # Create notifier
        notifier = TelegramNotifier(
            bot_token="test_token",
            chat_id="test_chat_id"
        )

        # Send ping
        message_id = notifier.send_ping()

        # Verify
        assert message_id is None


class TestTelegramListener:
    """Tests for TelegramListener class."""

    def test_wait_for_pong_finds_matching_reply(self, mock_httpx_client):
        """wait_for_pong() returns reply text when reply_to_message_id matches."""
        # Setup mock response with matching reply
        mock_response = Mock()
        mock_response.json.return_value = {
            "ok": True,
            "result": [
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 67890,
                        "chat": {"id": 123456, "type": "private"},
                        "from": {"id": 123456},
                        "text": "pong",
                        "reply_to_message": {
                            "message_id": 12345
                        }
                    }
                }
            ]
        }
        mock_httpx_client.get.return_value = mock_response

        # Create listener
        listener = TelegramListener(
            bot_token="test_token",
            chat_id="123456"
        )

        # Wait for pong
        reply = listener.wait_for_pong(ping_message_id=12345, timeout=5)

        # Verify
        assert reply == "pong"

    def test_wait_for_pong_ignores_non_replies(self, mock_httpx_client):
        """wait_for_pong() ignores messages that aren't replies to ping."""
        # Setup mock response with non-reply message
        mock_response = Mock()
        mock_response.json.return_value = {
            "ok": True,
            "result": [
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 67890,
                        "chat": {"id": 123456, "type": "private"},
                        "from": {"id": 123456},
                        "text": "hello"
                        # No reply_to_message
                    }
                }
            ]
        }
        mock_httpx_client.get.return_value = mock_response

        # Create listener
        listener = TelegramListener(
            bot_token="test_token",
            chat_id="123456",
            poll_interval=0.1
        )

        # Wait for pong (should timeout)
        reply = listener.wait_for_pong(ping_message_id=12345, timeout=0.5)

        # Verify
        assert reply is None

    def test_wait_for_pong_ignores_wrong_message_id(self, mock_httpx_client):
        """wait_for_pong() ignores replies to different messages."""
        # Setup mock response with reply to different message
        mock_response = Mock()
        mock_response.json.return_value = {
            "ok": True,
            "result": [
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 67890,
                        "chat": {"id": 123456, "type": "private"},
                        "from": {"id": 123456},
                        "text": "pong",
                        "reply_to_message": {
                            "message_id": 99999  # Different message ID
                        }
                    }
                }
            ]
        }
        mock_httpx_client.get.return_value = mock_response

        # Create listener
        listener = TelegramListener(
            bot_token="test_token",
            chat_id="123456",
            poll_interval=0.1
        )

        # Wait for pong (should timeout)
        reply = listener.wait_for_pong(ping_message_id=12345, timeout=0.5)

        # Verify
        assert reply is None

    def test_wait_for_pong_timeout(self, mock_httpx_client):
        """wait_for_pong() returns None on timeout."""
        # Setup mock response with no messages
        mock_response = Mock()
        mock_response.json.return_value = {
            "ok": True,
            "result": []
        }
        mock_httpx_client.get.return_value = mock_response

        # Create listener
        listener = TelegramListener(
            bot_token="test_token",
            chat_id="123456",
            poll_interval=0.1
        )

        # Wait for pong (should timeout quickly)
        reply = listener.wait_for_pong(ping_message_id=12345, timeout=0.5)

        # Verify
        assert reply is None

    def test_wait_for_pong_validates_chat_id(self, mock_httpx_client):
        """wait_for_pong() validates chat_id matches."""
        # Setup mock response with reply from different chat
        mock_response = Mock()
        mock_response.json.return_value = {
            "ok": True,
            "result": [
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 67890,
                        "chat": {"id": 999999, "type": "private"},  # Different chat ID
                        "from": {"id": 999999},
                        "text": "pong",
                        "reply_to_message": {
                            "message_id": 12345
                        }
                    }
                }
            ]
        }
        mock_httpx_client.get.return_value = mock_response

        # Create listener
        listener = TelegramListener(
            bot_token="test_token",
            chat_id="123456",
            poll_interval=0.1
        )

        # Wait for pong (should timeout due to chat_id mismatch)
        reply = listener.wait_for_pong(ping_message_id=12345, timeout=0.5)

        # Verify
        assert reply is None


class TestTelegramPingCLI:
    """Tests for telegram ping CLI command."""

    def test_ping_command_success(self, mock_httpx_client):
        """telegram ping succeeds with valid reply."""
        from click.testing import CliRunner
        from orchestrator_auto.cli import cli

        # Setup mocks
        # Mock send_ping response
        mock_send_response = Mock()
        mock_send_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 12345}
        }

        # Mock wait_for_pong response
        mock_get_response = Mock()
        mock_get_response.json.return_value = {
            "ok": True,
            "result": [
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 67890,
                        "chat": {"id": 123456, "type": "private"},
                        "from": {"id": 123456},
                        "text": "pong",
                        "reply_to_message": {
                            "message_id": 12345
                        }
                    }
                }
            ]
        }

        # Setup mock to return different responses for post and get
        mock_httpx_client.post.return_value = mock_send_response
        mock_httpx_client.get.return_value = mock_get_response

        # Mock config
        with patch("orchestrator_auto.cli.get_telegram_config") as mock_config:
            mock_config.return_value = {
                "bot_token": "test_token",
                "chat_id": "123456"
            }

            runner = CliRunner()
            result = runner.invoke(cli, ["telegram", "ping", "--timeout", "5"])

            # Verify success
            assert result.exit_code == 0
            assert "Ping sent" in result.output
            assert "Pong received" in result.output
            assert "2-way communication verified" in result.output

    def test_ping_command_timeout(self, mock_httpx_client):
        """telegram ping exits 1 on timeout."""
        from click.testing import CliRunner
        from orchestrator_auto.cli import cli

        # Setup mocks
        # Mock send_ping response
        mock_send_response = Mock()
        mock_send_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 12345}
        }

        # Mock wait_for_pong response (no messages)
        mock_get_response = Mock()
        mock_get_response.json.return_value = {
            "ok": True,
            "result": []
        }

        mock_httpx_client.post.return_value = mock_send_response
        mock_httpx_client.get.return_value = mock_get_response

        # Mock config
        with patch("orchestrator_auto.cli.get_telegram_config") as mock_config:
            mock_config.return_value = {
                "bot_token": "test_token",
                "chat_id": "123456"
            }

            runner = CliRunner()
            result = runner.invoke(cli, ["telegram", "ping", "--timeout", "1"])

            # Verify timeout
            assert result.exit_code == 1
            assert "Timeout" in result.output
            assert "replied to the ping message" in result.output

    def test_ping_command_no_config(self):
        """telegram ping fails without config."""
        from click.testing import CliRunner
        from orchestrator_auto.cli import cli

        # Mock config as empty
        with patch("orchestrator_auto.cli.get_telegram_config") as mock_config:
            mock_config.return_value = {}

            runner = CliRunner()
            result = runner.invoke(cli, ["telegram", "ping"])

            # Verify failure
            assert result.exit_code == 1
            assert "not configured" in result.output

    def test_ping_command_send_failure(self, mock_httpx_client):
        """telegram ping fails if send_ping returns None."""
        from click.testing import CliRunner
        from orchestrator_auto.cli import cli

        # Setup mock to fail
        mock_httpx_client.post.side_effect = Exception("Connection error")

        # Mock config
        with patch("orchestrator_auto.cli.get_telegram_config") as mock_config:
            mock_config.return_value = {
                "bot_token": "test_token",
                "chat_id": "123456"
            }

            runner = CliRunner()
            result = runner.invoke(cli, ["telegram", "ping"])

            # Verify failure
            assert result.exit_code == 1
            assert "Failed to send ping message" in result.output
