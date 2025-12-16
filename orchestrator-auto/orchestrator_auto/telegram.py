"""
Telegram integration for orchestrator-auto.

Provides outbound notifications via Telegram Bot API.
"""

import logging
from typing import Optional
from datetime import datetime

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


class TelegramNotifier:
    """
    Outbound notifications via Telegram Bot API.

    Uses sync httpx client for simplicity since the codebase is synchronous.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        enabled: bool = True,
        timeout: float = 10.0,
    ):
        """
        Initialize Telegram notifier.

        Args:
            bot_token: Telegram bot token from @BotFather
            chat_id: Target chat ID (your DM chat ID)
            enabled: Whether notifications are enabled
            timeout: Request timeout in seconds
        """
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx is required for Telegram integration. Install with: pip install httpx")

        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

        # Log sanitized token
        logger.info(f"Telegram notifier initialized: ...{bot_token[-4:]}")

    @property
    def client(self) -> "httpx.Client":
        """Lazy-initialize httpx client."""
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _send_message(
        self,
        text: str,
        parse_mode: str = "Markdown",
        disable_notification: bool = False,
    ) -> Optional[int]:
        """
        Send a message via Telegram Bot API.

        Args:
            text: Message text (supports Markdown)
            parse_mode: Parse mode (Markdown or HTML)
            disable_notification: Send silently

        Returns:
            Message ID if successful, None otherwise
        """
        if not self.enabled:
            logger.debug("Telegram notifications disabled, skipping")
            return None

        url = f"{TELEGRAM_API_BASE}{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_notification": disable_notification,
        }

        try:
            response = self.client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()

            if result.get("ok"):
                message_id = result.get("result", {}).get("message_id")
                logger.debug(f"Telegram message sent: {message_id}")
                return message_id
            else:
                logger.error(f"Telegram API error: {result.get('description')}")
                return None

        except httpx.HTTPStatusError as e:
            logger.error(f"Telegram HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Telegram request error: {e}")
            return None
        except Exception as e:
            logger.error(f"Telegram unexpected error: {e}")
            return None

    def notify_workflow_started(
        self,
        session_id: str,
        feature: str,
        planner_model: Optional[str] = None,
        executor_model: Optional[str] = None,
    ) -> Optional[int]:
        """
        Send notification when workflow starts.

        Returns message ID if successful.
        """
        models_line = ""
        if planner_model or executor_model:
            p = planner_model or "default"
            e = executor_model or "default"
            # Shorten model names for display
            p = p.replace("claude-", "").split("-202")[0] if "claude-" in p else p
            e = e.replace("claude-", "").split("-202")[0] if "claude-" in e else e
            models_line = f"\nModels: P={p} | E={e}"

        text = f"""🚀 *Workflow Started*

Session: `{session_id}`
Feature: {self._escape_markdown(feature)}{models_line}

_Started at {datetime.now().strftime('%H:%M')}_"""

        return self._send_message(text)

    def notify_milestone_completed(
        self,
        session_id: str,
        milestone_num: int,
        total_milestones: int,
        milestone_name: Optional[str] = None,
    ) -> Optional[int]:
        """
        Send notification when milestone is completed.

        Returns message ID if successful.
        """
        name_line = f"\nMilestone: {self._escape_markdown(milestone_name)}" if milestone_name else ""

        text = f"""✅ *Milestone {milestone_num}/{total_milestones} Completed*

Session: `{session_id}`{name_line}

_Completed at {datetime.now().strftime('%H:%M')}_"""

        return self._send_message(text)

    def notify_blocker(
        self,
        session_id: str,
        blocker_id: int,
        question: str,
        agent: str = "Planner",
    ) -> Optional[int]:
        """
        Send notification when blocker is encountered.

        Returns message ID if successful (used for reply tracking in Phase 2).
        """
        text = f"""⚠️ *BLOCKER - Input Required*

Session: `{session_id}`
Agent: {agent}

❓ {self._escape_markdown(question)}

_Reply to this message with your answer_"""

        return self._send_message(text)

    def notify_workflow_completed(
        self,
        session_id: str,
        feature: str,
        total_milestones: int,
        duration_minutes: Optional[int] = None,
        auto_committed: bool = False,
    ) -> Optional[int]:
        """
        Send notification when workflow completes successfully.

        Returns message ID if successful.
        """
        duration_line = f"\nDuration: {duration_minutes} minutes" if duration_minutes else ""
        commit_line = "\n\n✓ Changes auto-committed" if auto_committed else ""

        text = f"""🎉 *Workflow Completed*

Session: `{session_id}`
Feature: {self._escape_markdown(feature)}
Milestones: {total_milestones}/{total_milestones}{duration_line}{commit_line}"""

        return self._send_message(text)

    def notify_error(
        self,
        session_id: str,
        error: str,
    ) -> Optional[int]:
        """
        Send notification when workflow encounters an error.

        Returns message ID if successful.
        """
        text = f"""❌ *Workflow Error*

Session: `{session_id}`
Error: {self._escape_markdown(error)}

_Use `orchestrator resume {session_id}` to retry_"""

        return self._send_message(text)

    def send_test_message(self) -> tuple[bool, str]:
        """
        Send a test message to verify configuration.

        Returns (success, message).
        """
        text = """🔔 *Orchestrator Auto - Test Notification*

Your Telegram integration is configured correctly!

_This is a test message._"""

        message_id = self._send_message(text)

        if message_id:
            return True, f"Test message sent successfully (ID: {message_id})"
        else:
            return False, "Failed to send test message. Check bot token and chat ID."

    @staticmethod
    def _escape_markdown(text: str) -> str:
        """Escape special Markdown characters."""
        # Escape characters that have special meaning in Telegram Markdown
        chars_to_escape = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in chars_to_escape:
            text = text.replace(char, f'\\{char}')
        return text


def create_notifier_from_config(
    config: dict,
    cli_enabled: Optional[bool] = None,
) -> Optional[TelegramNotifier]:
    """
    Create TelegramNotifier from config dict.

    Args:
        config: Telegram config dict with bot_token, chat_id, enabled
        cli_enabled: Override from CLI flag (--telegram/--no-telegram)

    Returns:
        TelegramNotifier instance or None if disabled/not configured
    """
    if not config:
        return None

    bot_token = config.get("bot_token")
    chat_id = config.get("chat_id")

    if not bot_token or not chat_id:
        logger.debug("Telegram not configured: missing bot_token or chat_id")
        return None

    # Determine if enabled: CLI flag > config > default (True if configured)
    if cli_enabled is not None:
        enabled = cli_enabled
    else:
        enabled = config.get("enabled", True)

    if not enabled:
        logger.debug("Telegram notifications disabled")
        return None

    return TelegramNotifier(
        bot_token=str(bot_token),
        chat_id=str(chat_id),
        enabled=True,
    )
