# Telegram Integration Design

**Status:** Draft
**Priority:** High
**Complexity:** Medium

---

## Overview

Enable Telegram bot integration for orchestrator-auto to:
1. Receive real-time notifications on workflow events
2. Respond to blockers directly from Telegram
3. Monitor and control workflows remotely
4. Support multiple projects/droplets without conflicts

---

## Goals

| Goal | Priority |
|------|----------|
| Blocker notifications with reply capability | P0 |
| Milestone completion notifications | P0 |
| Workflow start/complete notifications | P1 |
| Status check commands | P1 |
| Start workflow from Telegram | P2 |
| Multi-project isolation | P0 |

---

## Architecture

### Recommended: One Bot Per Project

```
┌─────────────────────────────────────────────────────────────┐
│                        DROPLET 1                             │
│  ┌─────────────────┐     ┌─────────────────────────────┐   │
│  │ orchestrator    │────►│ TelegramNotifier            │   │
│  │ engine.py       │     │                             │   │
│  │                 │◄────│ • Sends notifications       │   │
│  │ • on_blocker()  │     │ • Polls for replies         │   │
│  │ • on_milestone()│     │ • Routes answers to engine  │   │
│  │ • on_complete() │     │                             │   │
│  └─────────────────┘     └──────────┬──────────────────┘   │
│                                     │                       │
└─────────────────────────────────────┼───────────────────────┘
                                      │
                                      ▼
                          ┌───────────────────────┐
                          │   Telegram API        │
                          │   @ProjectA_Bot       │
                          └───────────┬───────────┘
                                      │
                                      ▼
                          ┌───────────────────────┐
                          │   Your Phone          │
                          │   Telegram App        │
                          └───────────────────────┘
```

### Why One Bot Per Project?

| Approach | Pros | Cons |
|----------|------|------|
| **One bot per project** | Simple, isolated, no routing | Multiple chat windows |
| Central router | Single chat | Complex, extra infra, single point of failure |
| Shared bot with prefixes | Single chat | Race conditions, complex routing |

**Recommendation:** One bot per project. Use Telegram folders to organize.

---

## Components

### 1. TelegramNotifier Class

```python
# orchestrator_auto/telegram.py

class TelegramNotifier:
    """Handles Telegram bot communication."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        enabled: bool = True
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled
        self.pending_blockers: Dict[int, int] = {}  # message_id -> blocker_id

    # Notifications (outbound)
    def notify_workflow_started(self, session_id: str, feature: str) -> None
    def notify_milestone_completed(self, session_id: str, milestone: int, total: int, name: str) -> None
    def notify_blocker(self, session_id: str, blocker_id: int, question: str) -> int  # returns message_id
    def notify_workflow_completed(self, session_id: str, feature: str, duration: str) -> None
    def notify_error(self, session_id: str, error: str) -> None

    # Polling (inbound)
    def poll_for_replies(self) -> List[BlockerReply]
    def get_blocker_reply(self, message_id: int, timeout: int = 0) -> Optional[str]
```

### 2. Configuration

```yaml
# ~/.claude_orchestrator/config.yaml

telegram:
  enabled: true
  bot_token: "123456:ABC-DEF..."  # From @BotFather
  chat_id: "YOUR_CHAT_ID"            # Your chat ID

  notifications:
    workflow_start: true
    workflow_complete: true
    milestone_complete: true
    blocker: true                 # Always recommended
    error: true

  # Optional: quiet hours (no notifications except blockers)
  quiet_hours:
    enabled: false
    start: "22:00"
    end: "08:00"
```

### 3. CLI Integration

```bash
# Enable via CLI flag
orchestrator start -f "My feature" --telegram

# Or use config file (always enabled if configured)
orchestrator start -f "My feature"

# Test connection
orchestrator telegram test

# Set up interactively
orchestrator telegram setup
```

### 4. Environment Variables (Alternative)

```bash
export ORCHESTRATOR_TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
export ORCHESTRATOR_TELEGRAM_CHAT_ID="YOUR_CHAT_ID"
```

Priority: CLI flag > env vars > config file

---

## Message Formats

### Workflow Started

```
🚀 *Workflow Started*

Session: `a1b2c3d4`
Feature: Add user authentication with JWT
Models: P=opus-4.5 | E=sonnet-4.5

_Started at 14:32_
```

### Milestone Completed

```
✅ *Milestone 2/5 Completed*

Session: `a1b2c3d4`
Milestone: API Endpoints

_Completed in 8 min_
```

### Blocker (Interactive)

```
⚠️ *BLOCKER - Input Required*

Session: `a1b2c3d4`
Agent: Planner

❓ Should we persist theme preference in localStorage or database?

_Reply to this message with your answer_
```

User replies directly → bot captures → workflow resumes.

### Workflow Completed

```
🎉 *Workflow Completed*

Session: `a1b2c3d4`
Feature: Add user authentication with JWT
Milestones: 5/5
Duration: 47 minutes

✓ Changes auto-committed
```

### Error

```
❌ *Workflow Error*

Session: `a1b2c3d4`
Error: API timeout after 3 retries

_Use `orchestrator resume a1b2c3d4` to retry_
```

---

## Blocker Reply Flow

```
┌─────────────────┐
│ Engine detects  │
│ blocker         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ Save blocker    │────►│ Send Telegram   │
│ to database     │     │ notification    │
└─────────────────┘     └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │ Store message_id│
                        │ ↔ blocker_id    │
                        └────────┬────────┘
                                 │
         ┌───────────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ Poll for reply  │◄────│ User replies    │
│ to message_id   │     │ on Telegram     │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐
│ Resolve blocker │
│ Resume workflow │
└─────────────────┘
```

### Reply Detection

```python
def poll_for_replies(self) -> List[BlockerReply]:
    """Poll Telegram for replies to blocker messages."""
    updates = self._get_updates()

    replies = []
    for update in updates:
        # Check if it's a reply to one of our blocker messages
        if update.reply_to_message_id in self.pending_blockers:
            blocker_id = self.pending_blockers[update.reply_to_message_id]
            replies.append(BlockerReply(
                blocker_id=blocker_id,
                answer=update.text,
                message_id=update.reply_to_message_id
            ))

    return replies
```

---

## Commands (Phase 2)

| Command | Description |
|---------|-------------|
| `/status` | Show active workflow status |
| `/status <id>` | Show specific session status |
| `/list` | List recent sessions |
| `/pause` | Pause current workflow |
| `/resume` | Resume paused workflow |
| `/cancel` | Cancel current workflow |
| `/help` | Show available commands |

### Command Implementation

```python
def handle_command(self, text: str) -> str:
    """Handle incoming Telegram commands."""
    if text.startswith('/status'):
        return self._handle_status(text)
    elif text.startswith('/list'):
        return self._handle_list()
    elif text.startswith('/pause'):
        return self._handle_pause()
    # ...
```

---

## Implementation Phases

### Phase 1: Basic Notifications (MVP)

**Scope:**
- [ ] Create `telegram.py` module
- [ ] Implement `TelegramNotifier` class
- [ ] Add notifications for: blocker, milestone, complete, error
- [ ] Add `--telegram` CLI flag
- [ ] Add config file support
- [ ] Integrate with engine hooks

**Effort:** 3-4 hours

### Phase 2: Interactive Blockers

**Scope:**
- [ ] Implement reply polling
- [ ] Track message_id ↔ blocker_id mapping
- [ ] Auto-resume workflow on reply
- [ ] Add reply timeout handling
- [ ] Persist pending blockers across restarts

**Effort:** 2-3 hours

### Phase 3: Commands

**Scope:**
- [ ] Implement `/status` command
- [ ] Implement `/list` command
- [ ] Implement `/pause` and `/resume`
- [ ] Add `/help` command

**Effort:** 2-3 hours

### Phase 4: Start from Telegram (Optional)

**Scope:**
- [ ] Implement `/start <feature>` command
- [ ] Support plan templates
- [ ] Background workflow execution

**Effort:** 3-4 hours

---

## Database Schema Changes

```sql
-- Add telegram tracking to blockers table
ALTER TABLE blockers ADD COLUMN telegram_message_id INTEGER;

-- Track notification history (optional)
CREATE TABLE IF NOT EXISTS telegram_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,  -- 'start', 'milestone', 'blocker', 'complete', 'error'
    message_id INTEGER,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

---

## Security Considerations

### Bot Token Protection

```python
# Never log or expose bot token
def __init__(self, bot_token: str, ...):
    self.bot_token = bot_token
    # Log sanitized version only
    logger.info(f"Telegram bot initialized: ...{bot_token[-4:]}")
```

### Chat ID Validation

```python
def _validate_chat(self, chat_id: str) -> bool:
    """Only accept messages from configured chat."""
    return str(chat_id) == self.chat_id
```

### Rate Limiting

```python
# Respect Telegram rate limits
# Max 30 messages/second to same chat
# Max 20 messages/minute to same group

RATE_LIMIT_DELAY = 0.05  # 50ms between messages
```

---

## Dependencies

```toml
# pyproject.toml
dependencies = [
    # ... existing
    "python-telegram-bot>=20.0",  # or httpx for raw API
]
```

**Options:**
1. `python-telegram-bot` - Full featured, async support
2. `httpx` - Lightweight, just HTTP calls (simpler)

**Recommendation:** Use `httpx` for simplicity - we only need:
- Send messages
- Poll for updates
- No need for full bot framework

---

## Configuration Examples

### Single Project Setup

```yaml
# ~/.claude_orchestrator/config.yaml
telegram:
  enabled: true
  bot_token: "123456:ABC-DEF..."
  chat_id: "YOUR_CHAT_ID"
```

### Multi-Project Setup (3 Droplets)

**Droplet 1 - Project A:**
```yaml
telegram:
  enabled: true
  bot_token: "111111:AAA-ProjectA..."  # @ProjectA_Bot
  chat_id: "YOUR_CHAT_ID"
```

**Droplet 2 - Project B:**
```yaml
telegram:
  enabled: true
  bot_token: "222222:BBB-ProjectB..."  # @ProjectB_Bot
  chat_id: "YOUR_CHAT_ID"  # Same chat ID (your account)
```

**Droplet 3 - Project C:**
```yaml
telegram:
  enabled: true
  bot_token: "333333:CCC-ProjectC..."  # @ProjectC_Bot
  chat_id: "YOUR_CHAT_ID"
```

Each bot is independent. Organize with Telegram folders:
```
📁 Orchestrators
   ├── ProjectA Bot
   ├── ProjectB Bot
   └── ProjectC Bot
```

---

## Testing

### Unit Tests

```python
# tests/test_telegram.py

class TestTelegramNotifier:
    def test_format_blocker_message(self)
    def test_format_milestone_message(self)
    def test_parse_reply(self)
    def test_validate_chat_id(self)

class TestTelegramIntegration:
    @pytest.mark.integration
    def test_send_notification(self)
    def test_poll_replies(self)
```

### Manual Testing

```bash
# Test notification
orchestrator telegram test

# Output:
# ✓ Connected to Telegram bot @MyOrch_Bot
# ✓ Sent test message to chat YOUR_CHAT_ID
# ✓ Message delivered successfully
```

---

## Open Questions

1. **Quiet hours:** Skip non-critical notifications during sleep?
2. **Message grouping:** Batch rapid milestone completions?
3. **Rich formatting:** Use inline keyboards for quick actions?
4. **File attachments:** Send plan.md or export.md as files?

---

## Success Metrics

- [ ] Blocker response time reduced (can respond from phone)
- [ ] No missed blockers (notifications always delivered)
- [ ] Multi-droplet setup works without conflicts
- [ ] < 5 second notification latency

---

## Timeline Estimate

| Phase | Effort | Cumulative |
|-------|--------|------------|
| Phase 1: Basic notifications | 3-4 hours | 3-4 hours |
| Phase 2: Interactive blockers | 2-3 hours | 5-7 hours |
| Phase 3: Commands | 2-3 hours | 7-10 hours |
| Phase 4: Start from Telegram | 3-4 hours | 10-14 hours |

**Recommended MVP:** Phase 1 + Phase 2 (5-7 hours)
