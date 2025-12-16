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
    """Outbound notifications via Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled

    def notify_workflow_started(self, session_id: str, feature: str) -> None
    def notify_milestone_completed(self, session_id: str, milestone: int, total: int, name: str) -> None
    def notify_blocker(self, session_id: str, blocker_id: int, question: str) -> int  # returns telegram message_id
    def notify_workflow_completed(self, session_id: str, feature: str, duration: str) -> None
    def notify_error(self, session_id: str, error: str) -> None


class TelegramListener:
    """Inbound DM replies via long-polling `getUpdates`."""

    def __init__(self, bot_token: str, chat_id: str, allowed_user_id: str | None = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.allowed_user_id = allowed_user_id

    def poll_once(self) -> list[dict]:
        """Fetch new updates and return parsed messages."""
```

Note: interactive replies are handled by the **separate** CLI command `orchestrator telegram listen` so the main workflow process does not need to stay running.

### 2. Configuration

```yaml
# ~/.claude_orchestrator/config.yaml

telegram:
  enabled: true
  # DM-only recommended: configure your own bot + your personal chat/user IDs
  bot_token: "123456:ABC-DEF..."      # From @BotFather
  chat_id: "YOUR_CHAT_ID"                # Your DM chat ID
  allowed_user_id: "YOUR_CHAT_ID"         # Optional but recommended (Telegram user id)

  notifications:
    workflow_start: true
    workflow_complete: true
    milestone_complete: true
    blocker: true                       # Always recommended
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

# Or use config file (enabled if configured)
orchestrator start -f "My feature"

# Test connection
orchestrator telegram test

# Listen for DM replies (Phase 2)
orchestrator telegram listen
```

### 4. Environment Variables (Alternative)

```bash
export ORCHESTRATOR_TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
export ORCHESTRATOR_TELEGRAM_CHAT_ID="YOUR_CHAT_ID"
export ORCHESTRATOR_TELEGRAM_ALLOWED_USER_ID="YOUR_CHAT_ID"  # optional, recommended
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
# Inside `orchestrator telegram listen`

def handle_update(update: dict) -> None:
    """Process one Telegram update (DM-only)."""
    message = update.get("message")
    if not message:
        return

    chat = message.get("chat", {})
    from_user = message.get("from", {})
    if chat.get("type") != "private":
        return
    if str(chat.get("id")) != str(config.chat_id):
        return
    if config.allowed_user_id and str(from_user.get("id")) != str(config.allowed_user_id):
        return

    reply_to = message.get("reply_to_message")
    if not reply_to:
        return

    telegram_message_id = reply_to.get("message_id")
    answer = (message.get("text") or "").strip()
    if not telegram_message_id or not answer:
        return

    blocker = db.get_blocker_by_telegram_message_id(telegram_message_id, db_path)
    if not blocker or blocker.get("resolved_at") is not None:
        return

    db.resolve_blocker(blocker["id"], answer, db_path)
    Orchestrator(session_id=blocker["session_id"], db_path=db_path).resume(answer=answer)
```

Persist `last_update_id` after processing each update to avoid replay on restart.

---

## Bot Commands (Optional / Phase 3)

Keep commands DM-only and minimal at first.

| Command | Description |
|---------|-------------|
| `/status` | Show most recent active/paused session status |
| `/status <id>` | Show status for a specific session |
| `/list` | List recent sessions |
| `/help` | Show available commands |

Defer `/pause`, `/resume`, `/cancel` until session selection semantics are clear and access control is implemented.

### Command Implementation

```python
def handle_command(self, text: str) -> str:
    """Handle incoming Telegram commands (DM-only)."""
    if text.startswith('/status'):
        return self._handle_status(text)
    if text.startswith('/list'):
        return self._handle_list()
    if text.startswith('/help'):
        return self._handle_help()
    return "Unknown command. Try /help"
```

---

## Runtime Model

This codebase pauses workflows by transitioning to `paused` and returning (see `orchestrator_auto.engine.Orchestrator._handle_blocker`). Because the original CLI process may exit, **interactive Telegram replies require a separate long-running listener**.

**Recommendation (DM-only):**
- `orchestrator start ...` sends outbound notifications.
- `orchestrator telegram listen` long-polls Telegram `getUpdates`, resolves blockers, and calls the existing resume flow.

---

## Implementation Phases (Tightened)

### Phase 1: Outbound Notifications (MVP)

**Scope:**
- [ ] Add `orchestrator_auto/telegram.py` (sync `httpx` client + `TelegramNotifier`)
- [ ] Config support in `~/.claude_orchestrator/config.yaml` (`telegram.enabled`, `bot_token`, `chat_id`)
- [ ] Env var overrides: `ORCHESTRATOR_TELEGRAM_BOT_TOKEN`, `ORCHESTRATOR_TELEGRAM_CHAT_ID`
- [ ] CLI: `orchestrator start|resume --telegram/--no-telegram`
- [ ] CLI: `orchestrator telegram test` (validate config + send test message)
- [ ] Engine hooks for notifications:
      - workflow started (at `Orchestrator.start()`)
      - blocker created (inside `_handle_blocker()`)
      - milestone approved (after `TransitionEvent.MILESTONE_APPROVED`)
      - completed/failed

**Effort:** 3-5 hours

### Phase 2: Interactive Blockers (Listener)

**Scope:**
- [ ] Persist `telegram_message_id` on blocker notifications
- [ ] Persist Telegram polling cursor (`last_update_id`) to DB
- [ ] Add `orchestrator telegram listen`:
      - long-polls `getUpdates` using `offset=last_update_id+1`
      - DM-only validation (`chat.type == private`, `chat.id == configured chat_id`)
      - match replies via `reply_to_message.message_id -> blocker.telegram_message_id`
      - call existing unblock flow: `Orchestrator(session_id).resume(answer=...)`
      - options: `--poll-interval`, `--once`, `--db-path`

**Effort:** 3-5 hours

### Phase 3: Bot Commands (Optional)

**Scope:**
- [ ] Implement `/status` and `/list` (reply in DM)
- [ ] (Optional) `/pause` and `/resume` (requires clear session selection semantics)

**Effort:** 2-4 hours

### Phase 4: Start from Telegram (Optional)

**Scope:**
- [ ] `/start <feature>` creates a new workflow
- [ ] Background execution + safety controls

**Effort:** 3-6 hours

---

## Database Schema Changes

```sql
-- Map Telegram blocker notification -> blocker row
ALTER TABLE blockers ADD COLUMN telegram_message_id INTEGER;

-- Persist polling cursor to avoid reprocessing updates after restart
CREATE TABLE IF NOT EXISTS telegram_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_update_id INTEGER
);
INSERT OR IGNORE INTO telegram_state (id, last_update_id) VALUES (1, 0);

-- (Optional) Track notification history for debugging/auditing
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

### DM-Only Validation (Recommended)

```python
def _validate_update(self, chat_type: str, chat_id: str, from_user_id: str | None = None) -> bool:
    """Accept messages only from the configured DM."""
    if chat_type != "private":
        return False
    if str(chat_id) != str(self.chat_id):
        return False
    if self.allowed_user_id is not None and str(from_user_id) != str(self.allowed_user_id):
        return False
    return True
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

Prefer a lightweight HTTP client over a full bot framework.

```toml
# pyproject.toml
dependencies = [
    # ... existing
    "httpx>=0.27",
]
```

Also add `httpx` to `environment.yml` (pip section) so conda installs stay consistent.

**Why `httpx` (sync):** we only need `sendMessage` + `getUpdates`, and the current codebase is synchronous/CLI-driven.

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
    def test_validate_dm_only_update(self)

class TestTelegramListener:
    def test_reply_resolves_blocker_and_resumes(self)
    def test_dedup_uses_last_update_id(self)

# Optional (only if env vars are set): real Telegram smoke tests
# @pytest.mark.integration
# def test_send_notification_live(self)
```

### Manual Testing

```bash
# Test notification
orchestrator telegram test

# Listener (Phase 2)
orchestrator telegram listen --poll-interval 2.0

# One-shot poll (useful for debugging)
orchestrator telegram listen --once
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
| Phase 1: Outbound notifications | 3-5 hours | 3-5 hours |
| Phase 2: Interactive blockers (listener) | 3-5 hours | 6-10 hours |
| Phase 3: Bot commands (optional) | 2-4 hours | 8-14 hours |
| Phase 4: Start from Telegram (optional) | 3-6 hours | 11-20 hours |

**Recommended MVP:** Phase 1 only (notifications) or Phase 1+2 if you want full phone-based unblock (6-10 hours).
