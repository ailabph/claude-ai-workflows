# Milestone 1: Core Ping-Pong Methods - COMPLETED

## Summary

Successfully implemented the core ping-pong methods for 2-way Telegram communication verification.

## Files Modified

### 1. orchestrator_auto/telegram.py (modified)

#### Added `TelegramNotifier.send_ping()` method (lines 394-402)
```python
def send_ping(self) -> Optional[int]:
    """
    Send a ping message for 2-way verification.

    Returns:
        message_id if successful, None otherwise
    """
    text = "🏓 *Ping!*\n\nReply to this message to verify 2-way communication."
    return self._send_message(text)
```

**Implementation details:**
- Uses existing `_send_message()` method (follows existing patterns)
- Returns `message_id` on success, `None` on failure
- Includes emoji for visual feedback
- Proper error handling via `_send_message()`

#### Added `TelegramListener.wait_for_pong()` method (lines 785-820)
```python
def wait_for_pong(
    self,
    ping_message_id: int,
    timeout: int = 60
) -> Optional[str]:
    """
    Wait for a reply to the ping message.

    Args:
        ping_message_id: The message_id of the sent ping
        timeout: Seconds to wait before timing out

    Returns:
        Reply text if received, None on timeout
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        remaining = timeout - (time.time() - start_time)
        poll_timeout = min(5, remaining)

        updates = self._get_updates(offset=0)

        for update in updates:
            message = update.get("message", {})
            reply_to = message.get("reply_to_message", {})

            # Check if this is a reply to our ping
            if reply_to.get("message_id") == ping_message_id:
                # Validate chat_id matches
                if str(message.get("chat", {}).get("id")) == self.chat_id:
                    return message.get("text", "")

        time.sleep(self.poll_interval)

    return None
```

**Implementation details:**
- Uses bounded timeout (follows anti-pattern guidance from plan)
- Polls using existing `_get_updates()` method
- Validates `reply_to_message.message_id` matches ping
- Validates `chat_id` for security
- Returns reply text on success, `None` on timeout
- Respects `self.poll_interval` between polls

### 2. tests/test_telegram.py (created)

Created comprehensive test suite with 8 tests covering all scenarios:

**TelegramNotifier tests:**
1. `test_send_ping_returns_message_id_on_success` - Verifies successful ping returns message_id
2. `test_send_ping_returns_none_on_http_error` - Verifies HTTP errors are handled
3. `test_send_ping_returns_none_on_api_error` - Verifies API errors are handled

**TelegramListener tests:**
1. `test_wait_for_pong_finds_matching_reply` - Verifies matching reply is detected
2. `test_wait_for_pong_ignores_non_replies` - Verifies non-reply messages are ignored
3. `test_wait_for_pong_ignores_wrong_message_id` - Verifies replies to other messages are ignored
4. `test_wait_for_pong_timeout` - Verifies timeout behavior
5. `test_wait_for_pong_validates_chat_id` - Verifies chat_id validation for security

**Test characteristics:**
- Uses mocked httpx client (no real network calls)
- Follows existing test patterns from test_cli.py
- Includes proper sys.path setup for imports
- Tests both success and error paths
- Verifies security validation (chat_id matching)

## Deliverables Checklist

- ✅ `TelegramNotifier.send_ping()` returns message_id
- ✅ `TelegramListener.wait_for_pong()` polls and matches reply_to_message_id
- ✅ Both methods handle errors gracefully
- ✅ Proper httpx client lifecycle management (reuses lazy-initialized client)
- ✅ Follows existing patterns from telegram.py
- ✅ Comprehensive test coverage (8 tests)
- ✅ Security validation (chat_id matching)

## Key Design Decisions

1. **Reuses existing infrastructure**: Both methods use existing httpx client and patterns
2. **Bounded timeout**: `wait_for_pong()` uses bounded loop to prevent infinite waiting
3. **Security first**: Validates chat_id to prevent spoofing
4. **Error handling**: Both methods handle errors gracefully, returning None on failure
5. **Type hints**: Proper Optional[int] and Optional[str] return types

## Pattern Adherence

✅ **send_ping()** follows `send_test_message()` pattern (lines 375-392)
✅ **wait_for_pong()** follows `poll_once()` pattern (lines 683-708)
✅ Uses lazy-initialized httpx client (no client leaks)
✅ Follows existing docstring format
✅ Uses existing `_get_updates()` and `_send_message()` methods

## Testing Strategy

Tests are designed to be run with pytest:
```bash
pytest tests/test_telegram.py -v
```

Mock httpx responses to avoid real Telegram API calls during testing.

## Notes

- No changes to existing functionality
- No new dependencies added
- Methods are ready for CLI integration in Milestone 2
- All error scenarios properly handled
- Security validations in place
