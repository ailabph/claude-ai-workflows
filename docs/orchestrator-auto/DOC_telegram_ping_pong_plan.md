# Telegram Ping-Pong - Implementation Plan

## 1. Overview

Implement a `orchestrator telegram ping` command that verifies 2-way Telegram communication by sending a ping message and waiting for the user to reply with "pong" (or any text). This provides a simple verification mechanism beyond the existing `telegram test` (outbound-only) to confirm both directions work before relying on blocker replies.

## 2. Feature Specification

### 2.1 Command Details

| Property | Value |
|----------|-------|
| **Command** | `orchestrator telegram ping` |
| **Module** | `orchestrator_auto/telegram.py` |
| **CLI** | `orchestrator_auto/cli.py` |
| **Config** | Uses existing `telegram` config section |

### 2.2 User Flow

```
$ orchestrator telegram ping

Sending ping message to Telegram...
✓ Ping sent (message_id: 12345)

Waiting for your reply in Telegram (timeout: 60s)...
Reply to the ping message with any text to confirm 2-way communication.

[User replies "pong" in Telegram]

✓ Pong received: "pong"
✓ 2-way communication verified!
```

### 2.3 Command Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--timeout` | int | 60 | Seconds to wait for reply |
| `--verbose` | flag | false | Show debug output |

### 2.4 Error Scenarios

| Scenario | Output |
|----------|--------|
| No httpx | `Error: httpx not installed. Run: pip install httpx` |
| Invalid config | `Error: Telegram not configured. Set bot_token and chat_id.` |
| Send failure | `Error: Failed to send ping message: {reason}` |
| Timeout | `Timeout: No reply received within 60s. Check that you replied to the ping message.` |
| Wrong message | (ignored, keeps waiting) |

## 3. Architecture

### 3.1 File Structure

```
orchestrator_auto/
├── telegram.py          # Add ping_pong() method to TelegramNotifier
│                        # Add wait_for_reply() to TelegramListener
├── cli.py               # Add 'ping' subcommand to telegram group
└── tests/
    └── test_telegram.py # Add tests for ping-pong flow
```

### 3.2 Patterns to Follow

- **CLI**: Follow existing `telegram test` pattern (lines 1674-1720)
- **Polling**: Follow `TelegramListener.poll_once()` pattern
- **Config**: Use existing `get_telegram_config()` and `create_notifier_from_config()`

## 4. Implementation Details

### 4.1 TelegramNotifier.send_ping()

```python
def send_ping(self) -> Optional[int]:
    """Send a ping message for 2-way verification.

    Returns:
        message_id if successful, None otherwise
    """
    text = "🏓 *Ping!*\n\nReply to this message to verify 2-way communication."
    return self._send_message(text)
```

### 4.2 TelegramListener.wait_for_pong()

```python
def wait_for_pong(
    self,
    ping_message_id: int,
    timeout: int = 60
) -> Optional[str]:
    """Wait for a reply to the ping message.

    Args:
        ping_message_id: The message_id of the sent ping
        timeout: Seconds to wait before timing out

    Returns:
        Reply text if received, None on timeout
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        updates = self._get_updates(timeout=min(5, timeout))

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

### 4.3 CLI Command

```python
@telegram.command()
@click.option("--timeout", default=60, help="Seconds to wait for reply")
@click.option("-v", "--verbose", is_flag=True, help="Show debug output")
def ping(timeout: int, verbose: bool):
    """Verify 2-way Telegram communication with ping-pong."""
    if not HTTPX_AVAILABLE:
        click.echo("Error: httpx not installed. Run: pip install httpx")
        sys.exit(1)

    config = get_telegram_config()
    notifier = create_notifier_from_config(config)

    if not notifier:
        click.echo("Error: Telegram not configured. Set bot_token and chat_id.")
        sys.exit(1)

    click.echo("Sending ping message to Telegram...")
    message_id = notifier.send_ping()

    if not message_id:
        click.echo("Error: Failed to send ping message")
        sys.exit(1)

    click.echo(f"✓ Ping sent (message_id: {message_id})")
    click.echo(f"\nWaiting for your reply in Telegram (timeout: {timeout}s)...")
    click.echo("Reply to the ping message with any text to confirm 2-way communication.\n")

    listener = TelegramListener(
        bot_token=config.get("bot_token"),
        chat_id=config.get("chat_id"),
        on_blocker_reply=lambda *args: None,  # No-op callback
    )

    try:
        reply = listener.wait_for_pong(message_id, timeout=timeout)

        if reply:
            click.echo(f'✓ Pong received: "{reply}"')
            click.echo("✓ 2-way communication verified!")
            # Send confirmation back
            notifier._send_message(f"✓ Pong received! 2-way communication verified.")
        else:
            click.echo(f"Timeout: No reply received within {timeout}s.")
            click.echo("Check that you replied to the ping message (not a new message).")
            sys.exit(1)
    finally:
        listener.close()
        notifier.close()
```

## 5. Milestones

### Milestone 1: Core Ping-Pong Methods

**Tasks:**
1. Add `send_ping()` method to `TelegramNotifier` class
2. Add `wait_for_pong()` method to `TelegramListener` class
3. Ensure proper httpx client lifecycle management

**Deliverables:**
- [ ] `TelegramNotifier.send_ping()` returns message_id
- [ ] `TelegramListener.wait_for_pong()` polls and matches reply_to_message_id
- [ ] Both methods handle errors gracefully

**Key References:**
- `telegram.py:129-180` (send_message pattern)
- `telegram.py:614-681` (update polling pattern)

### Milestone 2: CLI Command Implementation

**Tasks:**
1. Add `ping` subcommand to `telegram` group in `cli.py`
2. Implement config loading and validation
3. Add `--timeout` and `--verbose` options
4. Handle all error scenarios with clear messages

**Deliverables:**
- [ ] `orchestrator telegram ping` command works end-to-end
- [ ] Timeout behavior correct (exits with code 1)
- [ ] Error messages are user-friendly
- [ ] Sends confirmation message on success

**Key References:**
- `cli.py:1674-1720` (`telegram test` command pattern)
- `cli.py:1722-1841` (`telegram listen` command pattern)

### Milestone 3: Tests and Documentation

**Tasks:**
1. Add unit tests for `send_ping()` and `wait_for_pong()`
2. Add integration test for CLI command (mocked)
3. Update README.md with new command documentation

**Deliverables:**
- [ ] Unit tests for new methods (mock httpx)
- [ ] CLI command test with mocked Telegram API
- [ ] README.md updated with `telegram ping` docs
- [ ] TODO item marked as complete

**Key References:**
- `tests/test_telegram.py` (existing test patterns)
- `README.md:203-221` (Telegram command docs)

## 6. Testing Strategy

### 6.1 Unit Tests

```python
# test_telegram.py

def test_send_ping_returns_message_id(mock_httpx):
    """send_ping() returns message_id on success"""

def test_send_ping_returns_none_on_failure(mock_httpx):
    """send_ping() returns None on HTTP error"""

def test_wait_for_pong_finds_matching_reply(mock_httpx):
    """wait_for_pong() returns reply text when reply_to_message_id matches"""

def test_wait_for_pong_ignores_non_replies(mock_httpx):
    """wait_for_pong() ignores messages that aren't replies to ping"""

def test_wait_for_pong_timeout(mock_httpx):
    """wait_for_pong() returns None on timeout"""
```

### 6.2 CLI Tests

```python
def test_ping_command_success(runner, mock_telegram):
    """telegram ping succeeds with valid reply"""

def test_ping_command_timeout(runner, mock_telegram):
    """telegram ping exits 1 on timeout"""

def test_ping_command_no_config(runner):
    """telegram ping fails without config"""
```

### 6.3 Coverage Targets

| Component | Target |
|-----------|--------|
| telegram.py (new methods) | 90% |
| cli.py (ping command) | 85% |

## 7. Security Considerations

- [ ] Validate `chat_id` on incoming messages (prevent spoofing)
- [ ] Use existing `allowed_user_id` filter if configured
- [ ] No secrets logged (bot_token never in output)
- [ ] Timeout prevents indefinite waiting

## 8. Anti-Patterns

### Don't: Poll without timeout
```python
# BAD - can hang forever
while True:
    updates = self._get_updates()
```

### Do: Always use bounded timeout
```python
# GOOD - bounded by total timeout
while time.time() - start_time < timeout:
    updates = self._get_updates(timeout=min(5, remaining))
```

### Don't: Create new httpx client per request
```python
# BAD - expensive, leaks connections
def wait_for_pong(self):
    client = httpx.Client()  # New client each call
```

### Do: Reuse lazy-initialized client
```python
# GOOD - reuses existing client
def wait_for_pong(self):
    updates = self._get_updates()  # Uses self._client
```

## 9. Quick Reference

| Resource | Path |
|----------|------|
| Telegram module | `orchestrator_auto/telegram.py` |
| CLI module | `orchestrator_auto/cli.py` |
| Config module | `orchestrator_auto/config.py` |
| Existing tests | `orchestrator_auto/tests/test_telegram.py` |
| README | `orchestrator-auto/README.md` |

## 10. Acceptance Criteria

1. `orchestrator telegram ping` sends a ping message
2. Command waits for user to reply to that specific message
3. On reply, confirms 2-way communication works
4. On timeout, provides helpful error message
5. Works with existing Telegram config (no new settings needed)
6. Tests pass with mocked Telegram API
7. README updated with new command
