"""
Telegram integration for orchestrator-auto.

Provides outbound notifications via Telegram Bot API.
Phase 2: Adds inbound message handling for blocker replies.
"""

import logging
import signal
import time
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

# Default polling configuration
DEFAULT_POLL_INTERVAL = 3  # seconds
DEFAULT_POLL_TIMEOUT = 30  # long polling timeout


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

    def notify_stuck_session(
        self,
        session_id: str,
        feature: str,
        phase: str,
        last_updated: str,
        inactive_minutes: int,
    ) -> Optional[int]:
        """
        Send notification when a stuck session is detected.

        Returns message ID if successful.
        """
        text = f"""⚠️ *Stuck Session Detected*

Session: `{session_id}`
Feature: {self._escape_markdown(feature)}
Phase: {phase}
Last Activity: {last_updated}
Inactive: {inactive_minutes}\\+ minutes

_Use `orchestrator resume {session_id} \\-\\-force` to restart_"""

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


# ============================================================================
# Telegram Listener (Phase 2)
# ============================================================================


class TelegramListener:
    """
    Polls for incoming Telegram messages and routes blocker replies.

    DM-only: Only accepts messages from configured chat_id in private chats.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        allowed_user_id: Optional[str] = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = 10.0,
        verbose: bool = False,
    ):
        """
        Initialize Telegram listener.

        Args:
            bot_token: Telegram bot token
            chat_id: Expected chat ID (only messages from this chat are processed)
            allowed_user_id: Optional user ID filter (additional security)
            poll_interval: Seconds between polls (default: 3)
            timeout: HTTP request timeout (default: 10)
            verbose: Log verbose debug info (default: False)
        """
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx is required for Telegram integration. Install with: pip install httpx")

        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.allowed_user_id = str(allowed_user_id) if allowed_user_id else None
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.verbose = verbose
        self._client: Optional[httpx.Client] = None
        self._running = False

        logger.info(f"Telegram listener initialized for chat {chat_id}")

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

    def _get_updates(self, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Fetch updates from Telegram using long polling.

        Args:
            offset: Update ID offset (only get updates > offset)

        Returns:
            List of update objects
        """
        url = f"{TELEGRAM_API_BASE}{self.bot_token}/getUpdates"
        params = {
            "offset": offset,
            "timeout": DEFAULT_POLL_TIMEOUT,
            "allowed_updates": ["message"],
        }

        try:
            response = self.client.get(url, params=params, timeout=DEFAULT_POLL_TIMEOUT + 5)
            response.raise_for_status()
            result = response.json()

            if result.get("ok"):
                return result.get("result", [])
            else:
                logger.error(f"Telegram API error: {result.get('description')}")
                return []

        except httpx.TimeoutException:
            # Normal timeout for long polling, just return empty
            return []
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # Rate limited - back off
                retry_after = int(e.response.headers.get("Retry-After", 30))
                logger.warning(f"Rate limited, backing off {retry_after}s")
                time.sleep(retry_after)
            else:
                logger.error(f"Telegram HTTP error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Telegram request error: {e}")
            return []

    def _validate_message(self, message: Dict[str, Any]) -> bool:
        """
        Validate that a message is from allowed DM chat.

        Args:
            message: Telegram message object

        Returns:
            True if message should be processed
        """
        chat = message.get("chat", {})
        from_user = message.get("from", {})

        # Must be private chat (DM)
        if chat.get("type") != "private":
            if self.verbose:
                logger.debug(f"Ignoring non-private chat: {chat.get('type')}")
            return False

        # Must match configured chat_id
        if str(chat.get("id")) != self.chat_id:
            if self.verbose:
                logger.debug(f"Ignoring chat_id mismatch: {chat.get('id')} != {self.chat_id}")
            return False

        # Optional user_id filter
        if self.allowed_user_id:
            if str(from_user.get("id")) != self.allowed_user_id:
                if self.verbose:
                    logger.debug(f"Ignoring user_id mismatch: {from_user.get('id')}")
                return False

        return True

    def _send_reply(self, chat_id: str, text: str, reply_to_message_id: Optional[int] = None) -> Optional[int]:
        """
        Send a reply message.

        Args:
            chat_id: Chat to send to
            text: Message text
            reply_to_message_id: Optional message to reply to

        Returns:
            Message ID if successful
        """
        url = f"{TELEGRAM_API_BASE}{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        try:
            response = self.client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            if result.get("ok"):
                return result.get("result", {}).get("message_id")
        except Exception as e:
            logger.error(f"Failed to send reply: {e}")

        return None

    def process_update(
        self,
        update: Dict[str, Any],
        on_blocker_reply: Callable[[int, str, str], Optional[str]],
    ) -> bool:
        """
        Process a single update.

        Args:
            update: Telegram update object
            on_blocker_reply: Callback(telegram_message_id, answer, chat_id) -> error or None

        Returns:
            True if update was processed (valid reply)
        """
        message = update.get("message")
        if not message:
            return False

        # Validate DM-only
        if not self._validate_message(message):
            return False

        # Must be a reply to another message
        reply_to = message.get("reply_to_message")
        if not reply_to:
            if self.verbose:
                logger.debug("Ignoring non-reply message")
            return False

        # Get the original message ID we're replying to
        original_message_id = reply_to.get("message_id")
        if not original_message_id:
            return False

        # Get the reply text
        reply_text = message.get("text", "").strip()
        if not reply_text:
            if self.verbose:
                logger.debug("Ignoring empty reply")
            return False

        # Call the blocker resolution callback
        try:
            error = on_blocker_reply(original_message_id, reply_text, self.chat_id)
            if error:
                self._send_reply(
                    self.chat_id,
                    f"❌ {error}",
                    reply_to_message_id=message.get("message_id"),
                )
                return False
            else:
                # Success - send confirmation (don't say "resuming" since we only record the answer)
                self._send_reply(
                    self.chat_id,
                    "✅ Answer recorded. Run `orchestrator resume` to continue.",
                    reply_to_message_id=message.get("message_id"),
                )
                return True
        except Exception as e:
            logger.error(f"Error processing blocker reply: {e}")
            self._send_reply(
                self.chat_id,
                f"❌ Error: {e}",
                reply_to_message_id=message.get("message_id"),
            )
            return False

    def poll_once(
        self,
        last_update_id: int,
        on_blocker_reply: Callable[[int, str, str], Optional[str]],
    ) -> int:
        """
        Poll once and process any updates.

        Args:
            last_update_id: Last processed update ID
            on_blocker_reply: Callback for blocker replies

        Returns:
            New last_update_id after processing
        """
        updates = self._get_updates(offset=last_update_id + 1 if last_update_id else 0)

        for update in updates:
            update_id = update.get("update_id", 0)
            self.process_update(update, on_blocker_reply)

            # Always advance cursor (even for ignored messages)
            if update_id > last_update_id:
                last_update_id = update_id

        return last_update_id

    def run(
        self,
        on_blocker_reply: Callable[[int, str, str], Optional[str]],
        get_last_update_id: Callable[[], int],
        set_last_update_id: Callable[[int], None],
        on_shutdown: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Run the polling loop.

        Args:
            on_blocker_reply: Callback(telegram_message_id, answer, chat_id) -> error or None
            get_last_update_id: Callback to get persisted cursor
            set_last_update_id: Callback to persist cursor
            on_shutdown: Optional callback when shutting down
        """
        self._running = True
        last_update_id = get_last_update_id()

        logger.info(f"Starting listener loop (last_update_id={last_update_id})")

        # Setup signal handlers for graceful shutdown
        def handle_signal(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            self._running = False

        original_sigint = signal.signal(signal.SIGINT, handle_signal)
        original_sigterm = signal.signal(signal.SIGTERM, handle_signal)

        try:
            while self._running:
                try:
                    new_last_update_id = self.poll_once(last_update_id, on_blocker_reply)

                    # Persist cursor if changed
                    if new_last_update_id != last_update_id:
                        set_last_update_id(new_last_update_id)
                        last_update_id = new_last_update_id

                    # Small sleep between polls (long polling already waits)
                    if self._running:
                        time.sleep(self.poll_interval)

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"Error in poll loop: {e}")
                    if self._running:
                        time.sleep(self.poll_interval)

        finally:
            # Restore signal handlers
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)

            if on_shutdown:
                on_shutdown()

            self.close()
            logger.info("Listener stopped")

    def stop(self) -> None:
        """Stop the polling loop gracefully."""
        self._running = False


def create_listener_from_config(config: dict) -> Optional[TelegramListener]:
    """
    Create TelegramListener from config dict.

    Args:
        config: Telegram config dict with bot_token, chat_id, allowed_user_id

    Returns:
        TelegramListener instance or None if not configured
    """
    if not config:
        return None

    bot_token = config.get("bot_token")
    chat_id = config.get("chat_id")

    if not bot_token or not chat_id:
        logger.debug("Telegram not configured: missing bot_token or chat_id")
        return None

    return TelegramListener(
        bot_token=str(bot_token),
        chat_id=str(chat_id),
        allowed_user_id=config.get("allowed_user_id"),
        verbose=config.get("verbose", False),
    )
