# Orchestrator Auto

**Automated two-agent workflow orchestration for complex software engineering tasks.**

---

## Quick Reference

```bash
# Start a new workflow
orchestrator start -f "Add user authentication with JWT"

# Start with custom models (cost savings)
orchestrator start -f "My feature" -pm sonnet -em haiku

# Start with existing plan (skip discovery/planning)
orchestrator start -f "My feature" --plan docs/plan.md

# Start with auto-commit on completion
orchestrator start -f "My feature" --auto-commit

# Start with Telegram notifications
orchestrator start -f "My feature" --telegram

# Test Telegram configuration
orchestrator telegram test

# List all sessions
orchestrator list

# Check session status
orchestrator status <session-id>

# Resume a session
orchestrator resume <session-id>

# Respond to a blocker
orchestrator respond <session-id> "Your answer here"

# Export session to markdown
orchestrator export <session-id> -o report.md
```

---

## Installation

```bash
# 1. Navigate to directory
cd orchestrator-auto

# 2. Create conda environment
conda env create -f environment.yml
conda activate orchestrator-auto

# 3. Install
pip install -e .

# 4. Set API key
export ANTHROPIC_API_KEY="your-api-key"

# 5. Verify
orchestrator --help
```

---

## CLI Commands

### `start` - Start new workflow

```bash
orchestrator start -f "Feature description" [options]
```

| Option | Description |
|--------|-------------|
| `-f, --feature` | Feature description (required) |
| `-p, --plan` | Path to existing plan file |
| `-pm, --planner-model` | Planner model: `opus`, `sonnet`, `haiku` |
| `-em, --executor-model` | Executor model: `opus`, `sonnet`, `haiku` |
| `--auto-commit` | Auto-commit on completion |
| `--telegram` | Enable Telegram notifications |
| `--no-telegram` | Disable Telegram notifications |
| `--no-activity` | Disable activity indicator |
| `-d, --db-path` | Custom database path |

### `resume` - Resume existing session

```bash
orchestrator resume <session-id> [-a "answer"]
```

### `respond` - Answer a blocker

```bash
orchestrator respond <session-id> "Your answer"
```

### `list` - List sessions

```bash
orchestrator list [-s active|paused|completed|failed]
```

### `status` - Session details

```bash
orchestrator status <session-id>
```

### `export` - Export to markdown

```bash
orchestrator export <session-id> [-o output.md]
```

### `telegram test` - Test Telegram configuration

```bash
orchestrator telegram test
```

---

## Configuration

### Model Aliases

| Alias | Model ID |
|-------|----------|
| `opus` | `claude-opus-4-5-20251101` |
| `sonnet` | `claude-sonnet-4-5-20250929` |
| `haiku` | `claude-haiku-3-5-20241022` |

**Defaults:** Planner = Opus, Executor = Sonnet

### Config File

`~/.claude_orchestrator/config.yaml`:

```yaml
models:
  planner: opus
  executor: sonnet
```

**Priority:** CLI flags > config file > defaults

### Database

Default: `~/.claude_orchestrator/db.sqlite`

### Telegram Notifications

Receive workflow notifications via Telegram (workflow start, milestone completion, blockers, completion/errors).

**Setup:**

1. Create a bot via [@BotFather](https://t.me/BotFather) and get your bot token
2. Start a chat with your bot and get your chat ID (send a message, then check `https://api.telegram.org/bot<TOKEN>/getUpdates`)
3. Install the optional dependency: `pip install httpx`

**Config file** (`~/.claude_orchestrator/config.yaml`):

```yaml
telegram:
  enabled: true
  bot_token: "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
  chat_id: "YOUR_CHAT_ID"
```

**Environment variables** (override config file):

```bash
export ORCHESTRATOR_TELEGRAM_BOT_TOKEN="your-bot-token"
export ORCHESTRATOR_TELEGRAM_CHAT_ID="your-chat-id"
export ORCHESTRATOR_TELEGRAM_ENABLED="true"
```

**Priority:** CLI flags > env vars > config file

---

## Workflow Phases

1. **Discovery** - Refine requirements with planner
2. **Planning** - Create implementation plan with milestones
3. **Execution** - Execute milestones, planner reviews each
4. **Completed** - All milestones approved
5. **Paused** - Waiting for human input

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    orchestrator-auto                          │
│  ┌────────────────┐         ┌─────────────────┐             │
│  │  Planner Agent │ ◄─────► │ Executor Agent  │             │
│  │  (Opus 4.5)    │         │ (Sonnet 4.5)    │             │
│  └────────────────┘         └─────────────────┘             │
│         ▲                            ▲                        │
│         │                            │                        │
│  ┌──────┴────────────────────────────┴─────┐                │
│  │       Orchestrator Engine                │                │
│  │  • State machine                         │                │
│  │  • Message routing                       │                │
│  │  • Blocker handling                      │                │
│  └──────────────────┬───────────────────────┘                │
│                     │                                         │
│              ┌──────▼──────┐                                 │
│              │  SQLite DB   │                                 │
│              └──────────────┘                                 │
└──────────────────────────────────────────────────────────────┘
```

---

## Response Tags

### Planner
- `[PLAN_READY]` - Plan created
- `[MILESTONE_APPROVED]` - Proceed to next
- `[CHANGES_REQUESTED]` - Revisions needed
- `[HUMAN_INPUT_NEEDED]` - Blocker

### Executor
- `[PROGRESS_REPORT]` - Milestone report
- `[CLARIFICATION_NEEDED]` - Need info
- `[BLOCKED]` - External dependency

---

## Development

### Project Structure

```
orchestrator-auto/
├── orchestrator_auto/
│   ├── cli.py               # CLI interface
│   ├── engine.py            # Core orchestration
│   ├── state.py             # State machine
│   ├── parser.py            # Response parsing
│   ├── agents.py            # Agent wrappers
│   ├── config.py            # Model config
│   ├── git.py               # Auto-commit
│   ├── telegram.py          # Telegram notifications
│   ├── recovery.py          # Context recovery
│   ├── prompts.py           # System prompts
│   └── db.py                # Database ops
├── tests/
└── README.md
```

### Running Tests

```bash
pytest tests/ -v
pytest tests/ --cov=orchestrator_auto
```

---

## Troubleshooting

| Error | Solution |
|-------|----------|
| Session not found | Run `orchestrator list` to find valid IDs |
| Database locked | Close other orchestrator instances |
| Agent timeout | Check internet/API key |

---

## TODO

- [ ] **Telegram Phase 2** - Inbound blocker responses via Telegram polling
- [ ] **Post Feedback** - User feedback at milestones/completion
- [x] **Telegram Phase 1** - Outbound notifications (start, milestone, blocker, complete)
- [x] **Auto-Commit** - `--auto-commit` flag for git commit on completion
- [x] **Model Selection** - `-pm`/`-em` flags with aliases
- [x] **Activity Indicator** - Streaming feedback with token count
- [x] **Import Plan** - `--plan` flag to skip discovery/planning

---

## Related

- [CLAUDE_orchestrator.md](../CLAUDE_orchestrator.md) - Framework docs
- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk) - SDK docs
