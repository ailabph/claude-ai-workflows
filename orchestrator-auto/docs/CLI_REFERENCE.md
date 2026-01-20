# CLI Reference

Complete command reference for `orchestrator`.

## All CLI Examples

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

# Start with TUI dashboard (rich visual interface)
orchestrator start -f "Add user authentication" --tui

# Start with TUI and custom models
orchestrator start -f "Add feature" --tui -pm sonnet -em haiku

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

## Commands

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
| `--tui` | Run in TUI (Text User Interface) mode |
| `-d, --db-path` | Custom database path |

**Note**: `--tui` is not compatible with:
- `--queue` (queue mode has its own TUI)
- `--auto-commit` / `--smart-commit` (not yet implemented in TUI)
- `--no-rename` (has no effect in TUI mode)

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

---

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

---

### `reset` - Reset orphaned session

```bash
orchestrator reset <session-id>
```

Refreshes heartbeat and prepares session for force resume. Use when a session is stuck in ACTIVE status but no process is running.

---

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

---

### `respond` - Answer a blocker

```bash
orchestrator respond <session-id> "Your answer"
```

---

### `list` - List sessions

```bash
orchestrator list [-s active|paused|completed|failed] [--all-projects]
```

| Option | Description |
|--------|-------------|
| `-s, --status` | Filter by status |
| `-a, --all-projects` | Show sessions from all projects (default: current project only) |

---

### `status` - Session details

```bash
orchestrator status <session-id>
```

---

### `export` - Export to markdown

```bash
orchestrator export <session-id> [-o output.md]
```

---

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

---

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

---

### `telegram test` - Test Telegram configuration

```bash
orchestrator telegram test
```

---

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

---

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

---

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

---

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

### `cleanup` - Clean up MCP processes

```bash
orchestrator cleanup [options]
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview what would be killed without killing |
| `-f, --force` | Skip confirmation prompt |
| `--all` | Also kill Playwright browser processes (use with caution) |

If a session crashes while using Playwright MCP, browser/server processes may be left running.

**Examples:**
```bash
orchestrator cleanup --dry-run   # Preview first!
orchestrator cleanup             # Interactive cleanup
orchestrator cleanup -f          # Force without confirmation
orchestrator cleanup --all       # Kill servers + browsers
```

> **Warning**: The `--all` flag may kill Playwright processes from other applications.
