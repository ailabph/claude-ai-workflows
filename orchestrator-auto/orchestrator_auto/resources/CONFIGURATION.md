# Configuration

Complete configuration reference for orchestrator-auto.

## Model Aliases

| Alias | Model ID |
|-------|----------|
| `opus` | `claude-opus-4-5-20251101` |
| `sonnet` | `claude-sonnet-4-5-20250929` |
| `haiku` | `claude-3-5-haiku-20241022` |

**Defaults:** Planner = Opus, Executor = Sonnet

---

## Config Files

**Global config:** `~/.claude_orchestrator/config.yaml`

**Repo-local config:** `<repo>/.claude_orchestrator/config.yaml` (gitignored)

```yaml
models:
  planner: opus
  executor: sonnet
```

Repo-local config is discovered by walking up from the current directory to the git root. If found, it's deep-merged with global config.

**Priority:** CLI flags > env vars > repo config > global config > defaults

---

## Database

Default location: `~/.claude_orchestrator/db.sqlite`

Override with `-d, --db-path` flag.

---

## Project Scoping

Sessions are tagged with project identity (`project_id` = repo root path). The `list` command filters by current project by default; use `--all-projects` to see all sessions. Other commands (`status`, `resume`, `reset`) accept any session ID.

---

## Authentication

### Setup

```bash
# Option A: Claude Pro/Max subscription (recommended)
# First, ensure Claude Code CLI is installed and logged in
claude login
# Then generate a long-lived token
claude setup-token
# Add to your shell config (~/.zshrc or ~/.bashrc)
export CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat01-your-token"

# Option B: API key (pay-as-you-go)
# Get key from https://console.anthropic.com/settings/keys
export ANTHROPIC_API_KEY="sk-ant-api03-your-key"
```

### Methods

| Method | Env Variable | Billing | Best For |
|--------|--------------|---------|----------|
| **Claude Subscription** | `CLAUDE_CODE_OAUTH_TOKEN` | Pro/Max plan | Personal use, included usage |
| **API Key** | `ANTHROPIC_API_KEY` | Pay-per-use | Teams, high volume, CI/CD |

**Important:**
- Don't set both variables simultaneously (causes conflicts)
- OAuth tokens (`sk-ant-oat01-...`) go in `CLAUDE_CODE_OAUTH_TOKEN`
- API keys (`sk-ant-api03-...`) go in `ANTHROPIC_API_KEY`
- Run `orchestrator check` to verify your setup

### Auth Source Detection

At startup, orchestrator displays the detected authentication source:

| Source | Display |
|--------|---------|
| API Key | `Auth: ANTHROPIC_API_KEY (sk-ant-api03-...)` |
| OAuth Token | `Auth: CLAUDE_CODE_OAUTH_TOKEN (sk-ant-oat01-...)` |
| AWS Bedrock | `Auth: AWS Bedrock (CLAUDE_CODE_USE_BEDROCK)` |
| Google Vertex | `Auth: Google Vertex AI (CLAUDE_CODE_USE_VERTEX)` |
| Azure Foundry | `Auth: Azure Foundry (CLAUDE_CODE_USE_FOUNDRY)` |
| Credentials File | `Auth: Credentials file (~/.claude/.credentials.json)` |
| Multiple | Warning listing all detected sources |
| Unknown | Note that keychain/other methods may still work |

**Limitations:**
- macOS Keychain credentials cannot be detected
- Credentials file format (~/.claude/.credentials.json) is best-effort
- When multiple sources detected, Claude Code chooses (we don't assert priority)

---

## Telegram Notifications

Receive workflow notifications via Telegram (workflow start, milestone completion, blockers, completion/errors).

### Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) and get your bot token
2. Start a chat with your bot and get your chat ID (send a message, then check `https://api.telegram.org/bot<TOKEN>/getUpdates`)
3. Install the optional dependency: `pip install httpx`

### Config File

```yaml
# ~/.claude_orchestrator/config.yaml or <repo>/.claude_orchestrator/config.yaml
telegram:
  enabled: true
  bot_token: "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
  chat_id: "YOUR_CHAT_ID"
  stuck_sessions:
    enabled: true
    inactive_minutes: 20
```

### Environment Variables

```bash
export ORCHESTRATOR_TELEGRAM_BOT_TOKEN="your-bot-token"
export ORCHESTRATOR_TELEGRAM_CHAT_ID="your-chat-id"
export ORCHESTRATOR_TELEGRAM_ENABLED="true"
export ORCHESTRATOR_TELEGRAM_STUCK_MINUTES="20"
```

### Features

**Stuck Session Detection:** Automatically notifies when sessions in planning/execution phase have no heartbeat for the configured threshold. Uses `heartbeat_at` timestamp updated during agent activity (not just state transitions).

**Two-Way Messaging:** Run `orchestrator telegram listen` to receive blocker answers via Telegram. When you reply to a blocker notification, the listener resolves the blocker. Recommended: use one Telegram bot per project (via repo-local config) to avoid cross-project routing issues.

**Priority:** CLI flags > env vars > repo config > global config

---

## Smart Auto-Commit

When `--auto-commit` is enabled, Smart Auto-Commit uses AI to analyze actual code changes and generate meaningful commit messages following [Conventional Commits](https://www.conventionalcommits.org/) format.

### Features

- Analyzes `git diff` to understand changes
- Generates semantic commit messages (`feat:`, `fix:`, `refactor:`, etc.)
- Supports Conventional Commits scopes and breaking markers (e.g. `feat(cli):`, `feat!:`)
- Enforces a 72-character subject line (first line)
- Automatic secrets detection (blocks sensitive data from being sent to AI)
- Graceful fallback to static messages on any error
- **Never pushes** - only creates local commits

### Commit Message Format

```
<type>: <description>

- bullet point for significant change
- another bullet point
```

Also accepted (when appropriate):
- Scoped commits: `<type>(<scope>): <description>` (e.g. `feat(cli): add flag`)
- Breaking changes: `<type>!: <description>` or `<type>(<scope>)!: <description>`

### Commit Types

| Type | When Used |
|------|-----------|
| `feat` | New user-visible functionality |
| `fix` | Bug correction |
| `refactor` | Code restructuring (no behavior change) |
| `docs` | Documentation only |
| `test` | Test files only |
| `chore` | Config, build, dependencies |
| `style` | Formatting only |
| `perf` | Performance optimization |

### Config File

```yaml
# ~/.claude_orchestrator/config.yaml or <repo>/.claude_orchestrator/config.yaml
auto_commit:
  smart: true  # Enable AI-generated messages (default: true)
  model: haiku  # Use Haiku for commit messages (optional)
```

### Environment Variables

```bash
export ORCHESTRATOR_SMART_COMMIT="true"  # or "false", "yes", "1"
export ORCHESTRATOR_AUTO_COMMIT_MODEL="haiku"
```

### CLI Flags

```bash
# Enable smart commit (default when --auto-commit is used)
orchestrator start -f "My feature" --auto-commit --smart-commit

# Disable smart commit (use static messages)
orchestrator start -f "My feature" --auto-commit --no-smart-commit

# Use a specific model for commit message generation
orchestrator start -f "My feature" --auto-commit --auto-commit-model haiku
```

**Priority:** CLI `--auto-commit-model` > env var > config file > executor model

### Secrets Detection

Before sending any diff to the AI, Smart Auto-Commit scans for potential secrets:
- API keys and tokens (generic patterns)
- Passwords and secrets in assignments
- Private keys (RSA, EC, DSA, OpenSSH)
- AWS credentials
- GitHub Personal Access Tokens (`ghp_...`)
- OpenAI API keys (`sk-...`)
- Anthropic API key patterns

If secrets are detected, the feature falls back to static message generation and logs a warning (showing pattern names, never values).

---

## MCP Tool Support

Enable external tools like Playwright browser automation in executor agents via MCP (Model Context Protocol) server configuration.

### Setup

1. Create `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-playwright"]
    }
  }
}
```

2. Install the MCP server:

```bash
npm install -g @anthropic/mcp-server-playwright
```

3. Run orchestrator with MCP config:

```bash
# Explicit path
orchestrator start -f "E2E tests" --mcp-config .mcp.json

# Auto-discovery (if .mcp.json exists in project root)
orchestrator start -f "E2E tests"
```

### Verify Playwright MCP Access

This repo includes a committed local test site plus a CLI verification command.

```bash
# Terminal 1: start the test site
cd orchestrator-auto/fixtures/playwright-test-site
npm ci
npm run dev -- --port <PORT>

# Terminal 2: run verification
orchestrator test-playwright planner --test-url http://localhost:<PORT>/
orchestrator test-playwright executor --test-url http://localhost:<PORT>/
orchestrator test-playwright both --test-url http://localhost:<PORT>/

# Artifacts will be written under:
# .orchestrator_artifacts/playwright-test/<timestamp>/
#
# Note: Playwright MCP often writes files into a sandbox folder:
# .orchestrator_artifacts/playwright-test/<timestamp>/.playwright-mcp/
```

### Per-Agent Scoping

Configure different MCP servers for planner vs executor:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-playwright"]
    },
    "figma": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-figma"],
      "env": {
        "FIGMA_ACCESS_TOKEN": "${FIGMA_ACCESS_TOKEN}"
      }
    }
  },
  "orchestrator": {
    "planner": {
      "mcpServers": ["figma"],
      "tools": ["mcp__figma__*"]
    },
    "executor": {
      "mcpServers": ["playwright"],
      "tools": ["mcp__playwright__*"]
    }
  }
}
```

### Environment Variable Expansion

Use `${VAR}` syntax in `.mcp.json` for secrets. Variables are expanded at runtime (not stored in database).

### Session Persistence

MCP configuration is persisted per-session. On `resume` or `respond`, the saved config is restored automatically. Use `--mcp-config` to override.

### Available MCP Tools

| Tool Pattern | Description |
|--------------|-------------|
| `mcp__playwright__browser_navigate` | Navigate to URL |
| `mcp__playwright__browser_click` | Click element |
| `mcp__playwright__browser_type` | Type text |
| `mcp__playwright__browser_snapshot` | Get page accessibility snapshot |
| `mcp__playwright__browser_close` | Close browser |
| `mcp__figma__*` | Figma design tools |

---

## Model Selection Guide

**Planner** (breaks feature into milestones) should be smart → **Use Opus**

**Executor** (builds one milestone) → **Choose based on complexity:**

| Executor Model | Cost | Best For | Example |
|---|---|---|---|
| **Opus** | ~3x Sonnet | Complex logic, hard problems | Refactor legacy code, security features |
| **Sonnet** (default) | ~1x baseline | General purpose, most tasks | Building features, APIs, components |
| **Haiku** | ~0.3x Sonnet | Simple tasks, speed priority | Format fixes, simple CRUD endpoints, documentation |

### Cost Optimization

**Default setup (most accurate):**
```bash
orchestrator start -f "Feature"
# Uses: Planner=Opus, Executor=Sonnet (~$1-5 per feature)
```

**Budget setup (70% cheaper):**
```bash
orchestrator start -f "Feature" -pm sonnet -em haiku
# Uses: Planner=Sonnet, Executor=Haiku (~$0.3-1 per feature)
# Good for: simple features, known patterns
```

**Complex task setup (most accurate):**
```bash
orchestrator start -f "Feature" -pm opus -em opus
# Uses: Both Opus (~$5-15 per feature)
# For: challenging algorithms, security, critical logic
```

**Remember:** You can always restart with different models if a workflow isn't going well. The code written is independent of the model.
