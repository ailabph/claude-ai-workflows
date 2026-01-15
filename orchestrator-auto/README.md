# Orchestrator Auto

**Automated two-agent workflow orchestration for complex software engineering tasks.**

---

## Quick Reference

```bash
# Start a new workflow
orchestrator start -f "Add user authentication with JWT"

# Start with custom models (cost savings)
orchestrator start -f "My feature" -pm sonnet -em haiku

# Start with existing plan (feature auto-extracted, renamed to *_done.md on completion)
orchestrator start --plan docs/plan.md

# Start with plan and explicit feature override
orchestrator start --plan docs/plan.md -f "My feature"

# Start with plan but skip auto-rename on completion
orchestrator start --plan docs/plan.md --no-rename

# Start with auto-commit on completion
orchestrator start -f "My feature" --auto-commit

# Start with smart auto-commit (AI-generated messages)
orchestrator start -f "My feature" --auto-commit --smart-commit

# Disable smart commit (use static messages)
orchestrator start -f "My feature" --auto-commit --no-smart-commit

# Start with MCP tools (e.g., Playwright browser automation)
orchestrator start -f "E2E tests" --mcp-config .mcp.json

# Start with Playwright in headless mode (no browser window)
orchestrator start -f "E2E tests" --mcp-config .mcp.json --headless

# Verify Planner + Executor have Playwright MCP tools
# Terminal 1: start the local fixture site
cd orchestrator-auto/fixtures/playwright-test-site
npm ci
npm run dev -- --port <PORT>

# Terminal 2: run the verification tool
orchestrator test-playwright both --test-url http://localhost:<PORT>/

# Start with Telegram notifications
orchestrator start -f "My feature" --telegram

# Run multiple plans sequentially (queue mode)
orchestrator start --queue plan1.md plan2.md plan3.md

# Resume existing queue
orchestrator start --queue

# Reset and recreate queue
orchestrator start --queue --queue-reset plan1.md plan2.md

# Test Telegram configuration
orchestrator telegram test

# Listen for Telegram blocker replies (Phase 2)
orchestrator telegram listen

# Watch mode: monitor directory for new plan files
orchestrator watch ./plans/
orchestrator watch ./plans/ --poll-interval 5
orchestrator watch ./plans/ --auto-commit

# Direct chat with Claude (no orchestration)
orchestrator chat
orchestrator chat -m opus --no-tools

# List sessions (current project only)
orchestrator list

# List all sessions across projects
orchestrator list --all-projects

# Check session status
orchestrator status <session-id>

# Resume a session
orchestrator resume <session-id>

# Force resume an orphaned/stuck session
orchestrator resume <session-id> --force

# Reset an orphaned session (refresh heartbeat)
orchestrator reset <session-id>

# Force-complete a stuck session
orchestrator complete <session-id>
orchestrator complete <session-id> --auto-commit

# Respond to a blocker
orchestrator respond <session-id> "Your answer here"

# Export session to markdown
orchestrator export <session-id> -o report.md

# Health check (dependencies, permissions, auth, API connection)
orchestrator check
orchestrator check -v  # verbose output

# Convert a regular plan to orchestrator format
orchestrator convert plan.md                    # Output to stdout
orchestrator convert plan.md -o converted.md   # Output to file
orchestrator convert plan.md --in-place        # Modify in place (with backup)
orchestrator convert plan.md --validate-only   # Check if already valid
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

# 4. Configure authentication (choose one)

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

# 5. Verify installation and auth
orchestrator check
```

### Authentication Notes

| Method | Env Variable | Billing | Best For |
|--------|--------------|---------|----------|
| **Claude Subscription** | `CLAUDE_CODE_OAUTH_TOKEN` | Pro/Max plan | Personal use, included usage |
| **API Key** | `ANTHROPIC_API_KEY` | Pay-per-use | Teams, high volume, CI/CD |

**Important:**
- Don't set both variables simultaneously (causes conflicts)
- OAuth tokens (`sk-ant-oat01-...`) go in `CLAUDE_CODE_OAUTH_TOKEN`
- API keys (`sk-ant-api03-...`) go in `ANTHROPIC_API_KEY`
- Run `orchestrator check` to verify your setup

---

## CLI Commands

### `start` - Start new workflow

```bash
orchestrator start -f "Feature description" [options]
```

| Option | Description |
|--------|-------------|
| `-f, --feature` | Feature description (auto-extracted from `--plan` if not provided) |
| `-p, --plan` | Path to existing plan file |
| `--queue` | Queue mode: run multiple plans sequentially |
| `--queue-reset` | Reset existing queue for this project |
| `queue_plans` | Plan file paths (when using `--queue`) |
| `-pm, --planner-model` | Planner model: `opus`, `sonnet`, `haiku` |
| `-em, --executor-model` | Executor model: `opus`, `sonnet`, `haiku` |
| `--auto-commit` | Auto-commit on completion |
| `--smart-commit/--no-smart-commit` | Use AI-generated commit messages (default: enabled) |
| `--auto-commit-model` | Model for AI commit messages (default: executor model) |
| `--telegram` | Enable Telegram notifications |
| `--no-telegram` | Disable Telegram notifications |
| `--mcp-config` | Path to MCP configuration file (`.mcp.json`) |
| `--headless` | Run Playwright MCP browser in headless mode |
| `--no-rename` | Do not rename plan file to `*_done.md` on completion |
| `--no-activity` | Disable activity indicator |
| `--debug` | Enable debug mode (full stack trace on error) |
| `-d, --db-path` | Custom database path |

#### Queue Mode

Queue mode enables sequential execution of multiple plan files:

```bash
# Create and run queue
orchestrator start --queue plan1.md plan2.md plan3.md

# Resume existing queue (if interrupted)
orchestrator start --queue

# Overwrite existing queue
orchestrator start --queue --queue-reset plan1.md plan2.md
```

**Behavior:**

- **Sequential execution:** Plans execute in order provided. Each plan creates a new session.
- **Feature extraction:** Feature descriptions are extracted from each plan file (from YAML frontmatter, `# Feature:` header, or filename).
- **Automatic advancement:** When a session completes, the next plan starts automatically.
- **Fail-forward:** Failed plans are recorded but don't stop the queue. The next plan starts.
- **Pause on blocker:** If a plan hits a blocker (needs human input), the queue halts. Use `orchestrator resume <session-id>` to continue.
- **Auto-commit:** Use `--auto-commit` to commit changes after each completed plan (not once at queue end).
- **Crash recovery:** Queue state is persisted in the database. Resuming after a crash continues from the next pending item.
- **Queue matching:** Running the same plan list again resumes the existing queue (no duplication). Use `--queue-reset` to force recreation.
- **Project scoping:** Queues are scoped to the current project (repo root).

**Queue visibility:**

- `orchestrator list` shows queue position and status for sessions in a queue
- Queue items are displayed as: `Queue: #2 [RUNNING]`

### `resume` - Resume existing session

```bash
orchestrator resume <session-id> [-a "answer"] [--force] [--auto-commit]
```

| Option | Description |
|--------|-------------|
| `-a, --answer` | Answer to blocker question |
| `--force` | Force resume orphaned sessions (bypasses pause check) |
| `--auto-commit` | Auto-commit changes on completion (for queue continuation) |
| `--smart-commit/--no-smart-commit` | Use AI-generated commit messages (default: enabled) |
| `--auto-commit-model` | Model for AI commit messages (default: executor model) |
| `--mcp-config` | Path to MCP configuration file (overrides saved config) |
| `--headless` | Run Playwright MCP browser in headless mode |
| `--debug` | Enable debug mode (full stack trace on error) |

### `reset` - Reset orphaned session

```bash
orchestrator reset <session-id>
```

Refreshes heartbeat and prepares session for force resume. Use when a session is stuck in ACTIVE status but no process is running.

### `complete` - Force-complete a stuck session

```bash
orchestrator complete <session-id> [options]
```

| Option | Description |
|--------|-------------|
| `--auto-commit` | Auto-commit changes after completion |
| `--smart-commit/--no-smart-commit` | Use AI-generated commit messages (default: enabled) |
| `--auto-commit-model` | Model for AI commit messages |

Force-completes a session that has finished all work but is stuck due to:
- Incorrect milestone count in the system
- Blocker that cannot be resolved normally
- Other edge cases where manual completion is needed

**What it does:**
1. Resolves any unresolved blockers (marks them as "Force-completed by user")
2. Sets session phase and status to COMPLETED
3. Optionally runs auto-commit with smart commit message generation

**Examples:**
```bash
# Simple force-complete
orchestrator complete 7a6b014b

# Force-complete and commit changes
orchestrator complete 7a6b014b --auto-commit

# Force-complete with specific commit model
orchestrator complete 7a6b014b --auto-commit --auto-commit-model haiku
```

### `respond` - Answer a blocker

```bash
orchestrator respond <session-id> "Your answer"
```

### `list` - List sessions

```bash
orchestrator list [-s active|paused|completed|failed] [--all-projects]
```

| Option | Description |
|--------|-------------|
| `-s, --status` | Filter by status |
| `-a, --all-projects` | Show sessions from all projects (default: current project only) |

### `status` - Session details

```bash
orchestrator status <session-id>
```

### `export` - Export to markdown

```bash
orchestrator export <session-id> [-o output.md]
```

### `check` - Health check

```bash
orchestrator check [-v]
```

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Show detailed output (session count, response text) |

Runs health checks on:
1. **Dependencies** - Required packages (claude-agent-sdk, click, prompt_toolkit, pyyaml) and optional (httpx)
2. **Permissions** - Database directory writable, database file accessible
3. **Authentication** - Detected auth source (API key, OAuth token, cloud providers, credentials file)
4. **API Connection** - Tests connection with a minimal request:
   - **OAuth tokens** (`CLAUDE_CODE_OAUTH_TOKEN`) - Tests via Claude Agent SDK
   - **API keys** (`ANTHROPIC_API_KEY`) - Tests via Anthropic SDK

Exit code: 0 if all checks pass, 1 if any fail.

**Example output:**
```
1. Dependencies
   ✓ claude-agent-sdk
   ✓ click
   ...

2. Permissions
   ✓ Database directory: ~/.claude_orchestrator

3. Authentication
   ✓ CLAUDE_CODE_OAUTH_TOKEN (sk-ant-oat01...)

4. API Connection
   Testing connection via Claude Agent SDK...
   ✓ Connection successful (OAuth)
```

### `convert` - Convert plan to orchestrator format

```bash
orchestrator convert <input.md> [options]
```

| Option | Description |
|--------|-------------|
| `-o, --output` | Output file path (default: stdout) |
| `-i, --in-place` | Modify input file in place (creates .bak backup) |
| `--no-backup` | Skip backup creation when using --in-place |
| `-m, --model` | Model: opus, sonnet, haiku (default: sonnet) |
| `--max-milestones` | Maximum milestones to create (default: 5) |
| `--validate-only` | Only check if file is orchestrator-compatible |
| `--dry-run` | Preview conversion without writing |

Uses AI to convert regular markdown plans into orchestrator-compatible format with properly formatted milestone headers (`## Milestone N: Name` or `### Milestone N: Name`).

**Exit codes:**
- 0: Success (conversion completed or file already valid)
- 1: Error (file not found, read error)
- 2: Conversion validation failed after retry

**Examples:**

```bash
# Check if a plan is already orchestrator-compatible
orchestrator convert plan.md --validate-only

# Convert and output to stdout
orchestrator convert plan.md

# Convert and save to new file
orchestrator convert plan.md -o converted_plan.md

# Convert in place (creates plan.md.bak backup)
orchestrator convert plan.md --in-place

# Convert in place without backup
orchestrator convert plan.md --in-place --no-backup

# Preview conversion without writing
orchestrator convert plan.md --dry-run

# Use a different model
orchestrator convert plan.md -m opus

# Limit to 3 milestones
orchestrator convert plan.md --max-milestones 3
```

### `telegram test` - Test Telegram configuration

```bash
orchestrator telegram test
```

### `telegram ping` - Verify 2-way communication

```bash
orchestrator telegram ping [--timeout N] [--verbose]
```

| Option | Description |
|--------|-------------|
| `--timeout` | Seconds to wait for reply (default: 60) |
| `-v, --verbose` | Show debug output |

Sends a ping message to your configured Telegram chat and waits for you to reply. This verifies that both outbound (sending) and inbound (receiving) messaging work correctly before relying on blocker replies.

**Important:** Reply to the ping message itself (not a new message) to confirm 2-way communication.

### `telegram listen` - Listen for blocker replies

```bash
orchestrator telegram listen [--poll-interval N] [--once] [--verbose]
```

| Option | Description |
|--------|-------------|
| `--poll-interval` | Seconds between polls (default: 3) |
| `--once` | Process one batch and exit |
| `-v, --verbose` | Show debug output for ignored messages |

Listens for Telegram replies to blocker notifications. When you reply to a blocker message in Telegram, the listener resolves the blocker and prepares the session for resume.

### `watch` - Watch Directory for Plans

```bash
orchestrator watch PLANS_DIR [options]
```

| Option | Description |
|--------|-------------|
| `PLANS_DIR` | Directory to watch (required) |
| `--poll-interval` | Poll interval in seconds (default: 2) |
| `--convert/--no-convert` | Auto-convert invalid plans (default: enabled) |
| `--auto-commit` | Auto-commit on completion |
| `--smart-commit` | Use AI-generated commit messages |
| `--telegram` | Enable Telegram notifications |
| `--mcp-config` | Path to MCP configuration file for all watched sessions |
| `--headless` | Run Playwright MCP browser in headless mode |
| `-pm, --planner-model` | Model for planner agent |
| `-em, --executor-model` | Model for executor agent |
| `--show-activity` | Show streaming activity indicator (default) |

Monitor a directory for new `.md` plan files. Plans are processed oldest-first (by modification time), auto-converted to orchestrator format if needed, and renamed to terminal state on completion.

**File naming conventions:**
- `_orchestrator-skip__*` - Quarantined originals (ignored)
- `*_done.md` - Completed successfully
- `*_failed.md` - Failed execution
- `*_paused.md` - Paused on blocker (queue halted until resumed)

**Examples:**

```bash
# Watch a directory with defaults
orchestrator watch ./plans/

# Watch with longer poll interval
orchestrator watch ./plans/ --poll-interval 5

# Watch without auto-conversion (quarantine invalid plans)
orchestrator watch ./plans/ --no-convert

# Watch with auto-commit on completion
orchestrator watch ./plans/ --auto-commit

# Watch with Telegram notifications
orchestrator watch ./plans/ --telegram
```

**Workflow:**
1. Drop a plan file (e.g., `feature-x.md`) into the watched directory
2. Watcher validates and auto-converts if needed
3. Orchestrator executes the plan
4. On completion: `feature-x.md` → `feature-x_done.md`
5. On failure: `feature-x.md` → `feature-x_failed.md`
6. On blocker: `feature-x.md` → `feature-x_paused.md` (queue halts)
7. After manual resume: `feature-x_paused.md` → `feature-x_done.md` or `feature-x_failed.md`

**Note on restart behavior:** If the watcher is stopped while a session is paused, and you manually resume the session (`orchestrator resume <session_id>`), the `*_paused.md` file will not be automatically renamed to `*_done.md` or `*_failed.md`. The file remains as `*_paused.md` (safely ignored) and can be renamed manually if desired.

### `chat` - Direct chat with Claude

```bash
orchestrator chat [options]
```

| Option | Description |
|--------|-------------|
| `-m, --model` | Model: opus, sonnet, haiku (default: sonnet) |
| `-s, --system-prompt` | Path to custom system prompt file |
| `--no-tools` | Disable file/bash tools (pure chat mode) |
| `--show-activity` | Show streaming activity indicator (default) |
| `--no-activity` | Disable streaming activity indicator |

Start a direct chat session with Claude without the orchestration workflow. Useful for quick questions, ad-hoc tasks, or interactive coding sessions.

**In-Chat Commands:**
- `/exit`, `/quit` - End chat session
- `/help` - Show available commands
- `/clear` - Clear conversation (reset context)
- `/model <alias>` - Switch model (resets context)

**Examples:**

```bash
# Default chat (Sonnet with tools)
orchestrator chat

# Chat with Opus
orchestrator chat -m opus

# Pure chat mode (no file/bash tools)
orchestrator chat --no-tools

# Custom system prompt
echo "You are a Python expert." > prompt.txt
orchestrator chat -s prompt.txt

# Combine options
orchestrator chat -m opus --no-tools --no-activity
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

### Config Files

**Global config:** `~/.claude_orchestrator/config.yaml`

**Repo-local config:** `<repo>/.claude_orchestrator/config.yaml` (gitignored)

```yaml
models:
  planner: opus
  executor: sonnet
```

Repo-local config is discovered by walking up from the current directory to the git root. If found, it's deep-merged with global config.

**Priority:** CLI flags > env vars > repo config > global config > defaults

### Database

Default: `~/.claude_orchestrator/db.sqlite`

### Project Scoping

Sessions are tagged with project identity (`project_id` = repo root path). The `list` command filters by current project by default; use `--all-projects` to see all sessions. Other commands (`status`, `resume`, `reset`) accept any session ID.

### Telegram Notifications

Receive workflow notifications via Telegram (workflow start, milestone completion, blockers, completion/errors).

**Setup:**

1. Create a bot via [@BotFather](https://t.me/BotFather) and get your bot token
2. Start a chat with your bot and get your chat ID (send a message, then check `https://api.telegram.org/bot<TOKEN>/getUpdates`)
3. Install the optional dependency: `pip install httpx`

**Config file** (`~/.claude_orchestrator/config.yaml` or `<repo>/.claude_orchestrator/config.yaml`):

```yaml
telegram:
  enabled: true
  bot_token: "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
  chat_id: "YOUR_CHAT_ID"
  stuck_sessions:
    enabled: true
    inactive_minutes: 20
```

**Environment variables** (override config file):

```bash
export ORCHESTRATOR_TELEGRAM_BOT_TOKEN="your-bot-token"
export ORCHESTRATOR_TELEGRAM_CHAT_ID="your-chat-id"
export ORCHESTRATOR_TELEGRAM_ENABLED="true"
export ORCHESTRATOR_TELEGRAM_STUCK_MINUTES="20"
```

**Stuck Session Detection:** Automatically notifies when sessions in planning/execution phase have no heartbeat for the configured threshold. Uses `heartbeat_at` timestamp updated during agent activity (not just state transitions).

**Two-Way Messaging (Phase 2):** Run `orchestrator telegram listen` to receive blocker answers via Telegram. When you reply to a blocker notification, the listener resolves the blocker. Recommended: use one Telegram bot per project (via repo-local config) to avoid cross-project routing issues.

**Priority:** CLI flags > env vars > repo config > global config

### Smart Auto-Commit

When `--auto-commit` is enabled, Smart Auto-Commit uses AI to analyze actual code changes and generate meaningful commit messages following [Conventional Commits](https://www.conventionalcommits.org/) format.

**Features:**
- Analyzes `git diff` to understand changes
- Generates semantic commit messages (`feat:`, `fix:`, `refactor:`, etc.)
- Supports Conventional Commits scopes and breaking markers (e.g. `feat(cli):`, `feat!:`)
- Enforces a 72-character subject line (first line)
- Automatic secrets detection (blocks sensitive data from being sent to AI)
- Graceful fallback to static messages on any error
- **Never pushes** - only creates local commits

**Commit Message Format:**
```
<type>: <description>

- bullet point for significant change
- another bullet point
```

Also accepted (when appropriate):
- Scoped commits: `<type>(<scope>): <description>` (e.g. `feat(cli): add flag`)
- Breaking changes: `<type>!: <description>` or `<type>(<scope>)!: <description>`

Smart commit enforces a 72-character subject line (first line) and truncates safely if needed.

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

**Config file** (`~/.claude_orchestrator/config.yaml` or `<repo>/.claude_orchestrator/config.yaml`):

```yaml
auto_commit:
  smart: true  # Enable AI-generated messages (default: true)
```

**Environment variable:**

```bash
export ORCHESTRATOR_SMART_COMMIT="true"  # or "false", "yes", "1"
```

**CLI flags:**

```bash
# Enable smart commit (default when --auto-commit is used)
orchestrator start -f "My feature" --auto-commit --smart-commit

# Disable smart commit (use static messages)
orchestrator start -f "My feature" --auto-commit --no-smart-commit

# Use a specific model for commit message generation
orchestrator start -f "My feature" --auto-commit --auto-commit-model haiku
```

**Model Selection:**

By default, Smart Auto-Commit uses the same model as the executor (typically Sonnet). You can override this to use a faster/cheaper model:

```yaml
# Config file: .claude_orchestrator/config.yaml
auto_commit:
  smart: true
  model: haiku  # Use Haiku for commit messages
```

```bash
# Environment variable
export ORCHESTRATOR_AUTO_COMMIT_MODEL="haiku"

# CLI flag (highest priority)
orchestrator start -f "My feature" --auto-commit --auto-commit-model haiku
```

**Priority:** CLI `--auto-commit-model` > env var > config file > executor model

**Secrets Detection:** Before sending any diff to the AI, Smart Auto-Commit scans for potential secrets:
- API keys and tokens (generic patterns)
- Passwords and secrets in assignments
- Private keys (RSA, EC, DSA, OpenSSH)
- AWS credentials
- GitHub Personal Access Tokens (`ghp_...`)
- OpenAI API keys (`sk-...`)
- Anthropic API key patterns

If secrets are detected, the feature falls back to static message generation and logs a warning (showing pattern names, never values).

**Priority:** CLI flags > env vars > repo config > global config > default (enabled)

### MCP Tool Support

Enable external tools like Playwright browser automation in executor agents via MCP (Model Context Protocol) server configuration.

**Setup:**

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

**Verify Playwright MCP Access (Planner + Executor):**

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

**Per-Agent Scoping:**

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

**Environment Variable Expansion:**

Use `${VAR}` syntax in `.mcp.json` for secrets. Variables are expanded at runtime (not stored in database).

**Session Persistence:**

MCP configuration is persisted per-session. On `resume` or `respond`, the saved config is restored automatically. Use `--mcp-config` to override.

**Available MCP Tools (when configured):**

| Tool Pattern | Description |
|--------------|-------------|
| `mcp__playwright__browser_navigate` | Navigate to URL |
| `mcp__playwright__browser_click` | Click element |
| `mcp__playwright__browser_type` | Type text |
| `mcp__playwright__browser_snapshot` | Get page accessibility snapshot |
| `mcp__playwright__browser_close` | Close browser |
| `mcp__figma__*` | Figma design tools |

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
│   ├── secrets.py           # Secrets detection for smart commit
│   ├── commit_ai.py         # AI commit message generation
│   ├── telegram.py          # Telegram notifications
│   ├── recovery.py          # Context recovery
│   ├── prompts.py           # System prompts
│   ├── db.py                # Database ops
│   ├── logging_config.py    # Per-session logging
│   └── exceptions.py        # Custom exception hierarchy
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
| Workflow error | Check log file at `~/.claude_orchestrator/logs/error_<session_id>_*.log` |

### Error Handling

When a workflow fails, the orchestrator:
1. Logs full stack trace to `~/.claude_orchestrator/logs/error_<session_id>_<timestamp>.log`
2. Marks the session as failed with error context
3. Shows user-friendly message with log file path

Use `--debug` flag for immediate stack trace output:
```bash
orchestrator start -f "My feature" --debug
orchestrator resume <session-id> --debug
```

Use `orchestrator status <session-id>` to view error details for failed sessions.

---

## TODO

- [x] **MCP Tool Support** - Enable external tools (Playwright, Figma) in executor/planner agents via `.mcp.json` configuration
- [x] **Plan Queue** - Queue multiple plan files (`--queue plan1.md plan2.md ...`), auto-start next session on completion
- [x] **Direct Chat Mode** - Chat directly with Claude without orchestration (`orchestrator chat`), useful for quick questions or ad-hoc tasks
- [ ] **Post Feedback** - User feedback at milestones/completion
- [x] **Plan Conversion** - Convert regular markdown plans into orchestrator-compatible format (`orchestrator convert plan.md`)
- [x] **Plan Completion Rename** - Automatically rename completed plan files to `*_done.md` suffix
- [x] **Smart Feature Flag** - Auto-extract feature description from plan content (enabled by default), eliminating need for `-f "description"` when using `--plan`
- [x] **Watch Mode** - Monitor a designated plans directory for new `.md` files, auto-convert to orchestrator format, execute, rename to `_done.md` on completion, and continue listening (`orchestrator watch ./plans/`)
- [x] **Auth Source Detection** - Determine if Claude is accessed via API key or Claude Code login (OAuth)
- [x] **Telegram Ping-Pong** - Verify 2-way communication with `orchestrator telegram ping` command
- [x] **Smart Auto-Commit** - AI-generated commit messages based on code diff (Conventional Commits format, secrets detection, no push)
- [x] **Telegram Phase 2** - Inbound blocker responses via Telegram polling (`orchestrator telegram listen`)
- [x] **Telegram Phase 1** - Outbound notifications (start, milestone, blocker, complete)
- [x] **Auto-Commit** - `--auto-commit` flag for git commit on completion
- [x] **Model Selection** - `-pm`/`-em` flags with aliases
- [x] **Activity Indicator** - Streaming feedback with token count
- [x] **Import Plan** - `--plan` flag to skip discovery/planning

---

## Next Priorities (Personal/Droplet Use)

1. **Retries (transport-level only):** automatic retry/backoff for transient API/network failures; keep semantic retries gated by planner/human.
2. **Observability shortcuts:** add lightweight CLI helpers like `orchestrator status <id> --tail N` / `--since 10m` to quickly see what changed without exporting.
3. **Safety controls for unattended runs:** quiet hours for non-blocker notifications, and caps per milestone (runtime/token/tool-call limits).
4. **Plan templates:** `orchestrator start --template <name>` to standardize repeatable workflows and reduce setup overhead.

---

## Droplet/Vacation Ops (1 Project = 1 Droplet)

- Recommended deployment model: install `orchestrator` globally on the droplet, `cd` into the project repo, and run sessions from that repo (matches local workflow).
- Persistence: rely on `~/.claude_orchestrator/db.sqlite` for session continuity; use `tmux` or `systemd` for process continuity.
- Auto-start on reboot (safe mode): run a dedicated command (e.g. `orchestrator daemon --auto-resume`) that:
    - acquires a single-instance lock
    - checks for `status=active` sessions in `planning`/`execution`
    - does nothing if heartbeat is recent (runner still alive)
    - force-resumes only if heartbeat is stale (default 20 min)
    - never auto-resumes `paused` (needs blocker answer) or `discovery` (human-driven)
- Multiple active sessions: resume only the most recently active session; alert/log if more exist.

---

## Changelog

### v0.11.1 - Headless Mode & Auto-Continue

**New Features:**

- **CLI: `--headless`** - Run Playwright MCP browser in headless mode (no browser window). Available on `start`, `resume`, and `watch` commands.
- **Auto-continue on truncated responses** - Automatically detects when planner or executor responses are truncated (e.g., hitting token limits mid-stream) and prompts the agent to continue, preventing unnecessary pauses.

**Technical:**

- **New function: `inject_headless_mode()`** - Automatically injects `--headless` into Playwright MCP server args
- **New function: `is_response_truncated()`** - Heuristic detection of incomplete responses (ends with `:`, "Let me...", etc.)
- **Improved error handling** - Better error messages when continuation also fails

### v0.11.0 - MCP Tool Support

- **MCP Tool Support** - Enable external tools (Playwright, Figma, etc.) in executor/planner agents
- **Per-agent scoping** - Configure different MCP servers for planner vs executor via `orchestrator` section
- **Environment variable expansion** - Support `${VAR}` syntax in `.mcp.json` configs (expanded at runtime, not stored)
- **Session persistence** - MCP config persisted in database for resume/respond continuity
- **Auto-discovery** - Automatically loads `.mcp.json` from project root or `~/.mcp.json`
- **CLI: `--mcp-config`** - Flag on `start`, `resume`, `respond`, and `watch` commands
- **Queue/watch mode support** - MCP config propagated to all sessions in batch workflows
- **New config functions** - `load_mcp_config_raw()`, `expand_env_vars()` in `config.py`
- **New helper** - `build_allowed_tools()` in `agents.py` for clean MCP tool integration
- **DB: `mcp_config_json` column** - Store raw MCP config per session
- **Documentation** - Investigation report and solution proposal in `docs/orchestrator-auto/`

### v0.10.1 - Error Handling & Logging

- **Graceful error handling** - User-friendly error messages with log file paths
- **Per-session logging** - Stack traces logged to `~/.claude_orchestrator/logs/error_<session_id>_<timestamp>.log`
- **Lazy file creation** - Log files only created when errors occur (no empty files)
- **CLI: `--debug`** - Flag for immediate stack trace output on `start` and `resume` commands
- **CLI: `status`** - Shows error details (type, message, log path) for failed sessions
- **Custom exceptions** - `OrchestratorError`, `AgentError`, `SessionStateError`, `PlanParseError` with session context
- **DB: `session_errors` table** - Persist error details for debugging and retry guidance
- **New modules** - `logging_config.py` (per-session loggers), `exceptions.py` (exception hierarchy)

### v0.10.0 - Watch Mode

- **Watch Mode** - Monitor a directory for new plan files (`orchestrator watch ./plans/`)
- **Automatic processing** - Plans processed oldest-first (by mtime), one at a time
- **Auto-conversion** - Invalid plans converted to orchestrator format (with quarantine of originals)
- **Terminal state renaming** - Files renamed to `*_done.md`, `*_failed.md`, or `*_paused.md` on completion
- **Pause handling** - Queue halts on blocker; resumes after `orchestrator resume <id> --answer`
- **Post-resume reconciliation** - Paused files renamed to final terminal state after external resume
- **CLI: `--poll-interval`** - Configure poll interval (default: 2 seconds)
- **CLI: `--convert/--no-convert`** - Toggle auto-conversion (default: enabled)
- **CLI: `--auto-commit`** - Auto-commit on completion
- **CLI: `--telegram`** - Enable Telegram notifications
- **File conventions** - `_orchestrator-skip__*` (quarantined), `*_done.md`, `*_failed.md`, `*_paused.md`

### v0.9.1 - Bug Fixes

**Critical Fixes:**

- **Fix: Blocker response not sent to agent** - When humans responded to blockers, the answer was logged but never actually sent to the agent that raised the blocker. Added `_inject_pending_response()` method that delivers human responses to the appropriate agent's conversation on resume, ensuring continuity.

- **Fix: BLOCKED tag parser too strict** - The `[BLOCKED]` response parser required exact text `Cannot proceed:` after the tag, causing valid blocker responses like `[BLOCKED] Cannot execute tests...` to be parsed as "Unexpected response format". Parser now accepts any text after `[BLOCKED]`.

- **Fix: MILESTONE_APPROVED parser too strict** - The `[MILESTONE_APPROVED]` parser required "Milestone N approved" text. Now accepts the tag alone and extracts milestone number if present in the response.

- **Fix: Unrecognized response creates proper blocker** - When planner/executor responses didn't match expected tags, the code returned "blocked" without creating a blocker record, leaving sessions in an inconsistent state. Now creates proper blocker with descriptive message.

**Medium Fixes:**

- **Fix: Infinite loop prevention in changes_requested** - Added retry counter (max 3 attempts) for milestone changes. After max retries, pauses for human intervention instead of looping indefinitely. Also fixed `_route_to_planner` to return executor's response to feedback, avoiding duplicate milestone prompts.

**Minor Fixes:**

- **Fix: Event loop conflicts in agents** - Removed global event loop setting (`asyncio.set_event_loop()`) that caused conflicts when planner and executor agents were both active. Each agent now manages its own event loop without global side effects.

- **Fix: current_milestone falsy check** - Changed `current_milestone or 1` to explicit None check (`if current_milestone is not None`) to properly handle edge case where milestone could be 0.

- **Fix: Truncated diff warning to AI** - When large diffs are truncated for AI commit message generation, the AI is now informed with a `[DIFF TRUNCATED]` marker so it doesn't make assumptions about unseen code changes.

**New Features:**

- **CLI: `complete`** - Force-complete stuck sessions that have finished all work but are blocked due to incorrect milestone counts or unresolvable blockers. Supports `--auto-commit` for committing changes.

**UX Improvements:**

- **Blocker message shows CLI command** - When a blocker occurs, the message now shows a copy-paste ready CLI command (`orchestrator respond <id> "answer"`) instead of Python code.

### v0.9.0 - Auth Source Detection & Health Check

- **Auth Source Detection** - Display detected auth method at startup (API key, OAuth, cloud providers)
- **Multi-signal detection** - Detects env vars + credentials file (~/.claude/.credentials.json on Linux)
- **Session tracking** - Auth source stored in database per session
- **CLI: `check`** - Health check command for dependencies, permissions, auth, and API connection
- **CLI: `check` OAuth support** - Tests OAuth tokens via Claude Agent SDK, API keys via Anthropic SDK
- **CLI: `status`** - Shows auth method used for session
- **CLI: `export`** - Includes auth method in markdown export
- **New module** - `auth.py` with `detect_auth()`, `format_auth_display()`
- **DB schema** - Added `auth_source`, `auth_signals`, `auth_detected_at` columns

### v0.8.0 - Smart Auto-Commit

- **Smart Auto-Commit** - AI-generated commit messages using Claude Haiku
- **Conventional Commits** - Messages follow `feat:`, `fix:`, `refactor:` etc. format
- **Secrets Detection** - Blocks diffs with API keys, tokens, or private keys from AI
- **Graceful Fallback** - Falls back to static messages on secrets, AI errors, or timeout
- **CLI: `--smart-commit/--no-smart-commit`** - Enable/disable AI commit messages
- **CLI: `--auto-commit-model`** - Override model for commit message generation (default: executor model)
- **Config: `auto_commit.smart`** - Configure via config file or `ORCHESTRATOR_SMART_COMMIT` env var
- **Config: `auto_commit.model`** - Configure commit model via config file or `ORCHESTRATOR_AUTO_COMMIT_MODEL` env var
- **New modules** - `secrets.py` (9 secret patterns), `commit_ai.py` (async generation)
- **Security** - Never logs secret values, only pattern names

### v0.7.0 - Plan Queue

- **Plan Queue** - Queue multiple plan files for sequential execution (`--queue plan1.md plan2.md`)
- **Queue resume** - Resume existing queue with `orchestrator start --queue` (no args)
- **Queue reset** - Overwrite existing queue with `--queue-reset`
- **Feature extraction** - Auto-extract feature description from plan headers (YAML frontmatter, `# Feature:`, H1)
- **Crash recovery** - Reconcile queue state on restart; handles running/paused/orphaned items
- **Fail-forward** - Failed plans are recorded but don't stop the queue
- **Auto-commit per session** - `--auto-commit` applies to each completed plan in queue
- **CLI: `resume --auto-commit`** - Resume with auto-commit for queue continuation
- **Queue visibility** - `orchestrator list` shows queue position for queued sessions
- **Telegram queue notifications** - Queue start, item progress, completion summary
- **DB: `queue_items` table** - Persist queue state with project scoping

### v0.6.0 - Telegram Two-Way & Project Scoping

- **Telegram Phase 2** - Inbound blocker responses via `orchestrator telegram listen`
- **Project scoping** - Sessions tagged with `project_id`; CLI commands filter by current project
- **Repo-local config** - Support for `<repo>/.claude_orchestrator/config.yaml` with deep merge
- **CLI: `--all-projects`** - Show sessions from all projects in `list` command
- **CLI: `telegram listen`** - Poll for Telegram replies to blocker notifications
- **DB: `telegram_state` table** - Persist polling cursor across restarts
- **DB: `telegram_message_id`** - Track blocker notification messages for reply routing

### v0.5.0 - Telegram Integration

- **Telegram Phase 1** - Outbound notifications (start, milestone, blocker, complete) (`9211393`)
- **Heartbeat hardening** - Stuck session detection with `heartbeat_at` timestamp (`3bc0537`)
- **CLI: `--telegram/--no-telegram`** - Enable/disable notifications
- **CLI: `orchestrator telegram test`** - Validate bot configuration
- **CLI: `orchestrator reset`** - Reset orphaned sessions
- **CLI: `--force` flag** - Force resume with guardrails
- **Config: `stuck_sessions.inactive_minutes`** - Configurable threshold (default 20 min)

### v0.4.0 - Model Selection & Auto-Commit

- **Model selection** - `-pm`/`-em` flags with aliases (opus/sonnet/haiku) (`0b10daf`)
- **Auto-commit** - `--auto-commit` flag for git commit on completion (`64c7e5a`)
- **Config file** - `~/.claude_orchestrator/config.yaml` for default models

### v0.3.0 - UX Improvements

- **Conversation continuity** - ClaudeSDKClient for persistent agent sessions (`61a179b`)
- **Multi-line paste** - Support for pasting multi-line input with preview (`1223e61`)
- **Discovery UX** - Wait for user input, improved `/ready` detection (`df7a7e8`, `89b84ae`)
- **Response handling** - Fixed ResultMessage termination (`e55a9ef`)

### v0.2.0 - Plan Import & Activity Indicator

- **`--plan` flag** - Import existing plan files, skip discovery/planning (`59d8c26`)
- **Activity indicator** - Streaming snippets with token count (`0a2c95c`)
- **Plan saving** - Engine saves plan file from `PLAN_CONTENT` tags (`c2a742e`)

### v0.1.0 - Initial Release

- **Two-agent orchestration** - Planner (Opus) + Executor (Sonnet) workflow (`b6b8256`)
- **Milestone-gated execution** - Planner reviews each milestone before proceeding
- **Session persistence** - SQLite database for workflow state and history
- **CLI commands** - `start`, `resume`, `respond`, `list`, `status`, `export`
- **Blocker handling** - Pause workflow for human input
- **Agent SDK integration** - Async query pattern with auto-approve (`761267c`, `52b5134`)

---

## Related

- [CLAUDE_orchestrator.md](../CLAUDE_orchestrator.md) - Framework docs
- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk) - SDK docs
