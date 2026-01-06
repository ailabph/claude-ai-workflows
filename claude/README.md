# Claude Code Configuration

This directory contains Claude Code configuration files, custom hooks, and agent definitions for enhanced development workflows.

**Official Documentation:** [Claude Code CLI Reference](https://docs.anthropic.com/en/docs/claude-code/cli-reference)

## Directory Structure

```
claude/
├── README.md                          # This file
├── settings.json                      # Claude Code settings
├── GLOBAL_GIT_RULES.md               # Git commit instructions
├── agents/
│   └── backend-architect.md          # Backend architect agent
└── hooks/
    ├── smart-readonly-analyzer.py    # Bash script with pattern matching
    └── ai-readonly-analyzer.py       # Python AI fallback analyzer
```

## Installation

### 1. Copy to your home directory

```bash
# Copy the entire claude directory
cp -r claude ~/.claude

# Or symlink for easier updates
ln -s $(pwd)/claude ~/.claude
```

### 2. Set up API key (for AI fallback)

```bash
export ANTHROPIC_API_KEY="your-api-key"
```

### 3. Install Python dependencies (optional, for AI analyzer)

```bash
pip install anthropic
```

## Components

### settings.json

Claude Code configuration with:

| Setting | Description |
|---------|-------------|
| `permissions.allow` | Auto-allowed tools (WebFetch) |
| `hooks.PreToolUse` | Bash command analyzer hook |
| `statusLine` | Custom status line with git branch, model, output style |
| `alwaysThinkingEnabled` | Enable extended thinking |
| `instructions` | Reference to global git rules |

**Status Line Output:**
```
project-name (main) Claude Sonnet [verbose]
```

### GLOBAL_GIT_RULES.md

Global instructions loaded for all sessions:
- No Co-authored-by attribution in commits
- No Claude/AI mentions in commit messages
- Author info comes from git metadata

### Hooks

#### smart-readonly-analyzer.py (Bash Script)

Primary hook that analyzes bash commands before execution:

**Flow:**
1. Check against 50+ read-only patterns → auto-approve
2. Check against dangerous patterns → block
3. Fall back to AI analysis for uncertain commands

**Read-Only Patterns Covered:**
- System: `ls`, `cat`, `grep`, `find`, `head`, `tail`, `pwd`, `tree`, `file`
- Git: `status`, `log`, `diff`, `show`, `branch`, `blame`, `reflog`
- Python: `pytest`, `mypy`, `pylint`, `flake8`, `coverage report`, `black --check`
- Django: `manage.py test`, `check`, `showmigrations`, `show_urls`, `migrate --plan`
- Node.js: `npm test`, `jest`, `vitest`, `eslint`, `next lint`
- Rails: `rspec`, `rubocop`, `rails routes`, `db:migrate:status`
- PHP: `phpunit`, `phpcs`, `artisan test`, `artisan route:list`
- Rust: `cargo check`, `cargo test`, `cargo clippy`
- Go: `go test`, `go vet`, `go list`
- Docker: `ps`, `images`, `inspect`, `logs`
- Kubernetes: `kubectl get`, `describe`, `logs`
- Terraform: `plan`, `validate`, `show`
- GitHub CLI: `gh pr list`, `gh issue view`
- AWS CLI: `describe-*`, `list-*`, `get-*`

**Dangerous Patterns Blocked:**
- System: `rm`, `sudo`, `mv`, `kill`, `shutdown`
- Git: `push`, `reset --hard`, `clean -fd`, `rebase`
- Package: `pip install`, `npm install`, `brew install`
- Django: `migrate` (without `--plan`), `makemigrations`, `flush`
- Docker: `rm`, `rmi`, `stop`, `build`, `push`
- Kubernetes: `delete`, `apply`, `create`
- AWS: `delete-*`, `terminate-*`, `s3 rm`

#### ai-readonly-analyzer.py

Python script for AI-based command analysis:
- Uses Claude Sonnet for analysis
- 80% confidence threshold for read-only approval
- 85% confidence threshold for dangerous blocking
- Framework-aware prompts (Django, Rails, Node.js, etc.)

**Console Output:**
```
✅ Pattern match (read-only): pytest tests/ -v
🚫 Pattern match (dangerous): rm -rf node_modules
🤔 Uncertain command, using AI: python custom_script.py
🤖 AI Auto-approved: python custom_script.py
   Reason: Script only reads and prints data
   Confidence: 92%
```

### Agents

#### backend-architect.md

Specialized agent for backend development tasks:

**Capabilities:**
- API design (REST, GraphQL)
- Database architecture (SQL, NoSQL, caching)
- Microservices design
- Security implementation (JWT, OAuth2, RBAC)
- Performance optimization
- DevOps integration

**Technology Stack:**
- Languages: Node.js, Python, Go, Java, Rust
- Frameworks: Express, FastAPI, Gin, Spring Boot
- Databases: PostgreSQL, MongoDB, Redis, DynamoDB
- Message Queues: RabbitMQ, Kafka, SQS
- Cloud: AWS, GCP, Azure

## Customization

### Adding Custom Read-Only Patterns

Edit `hooks/smart-readonly-analyzer.py`, add a new pattern block:

```bash
# ============================================
# MY CUSTOM TOOL
# ============================================
if echo "$cmd" | grep -qE '^my-tool\s+(check|verify|list)(\s|$)'; then
    debug_log "Matched my-tool read-only"
    return 0
fi
```

### Adding Custom Dangerous Patterns

In the `is_dangerous_command` function:

```bash
# My dangerous command
if echo "$cmd" | grep -qE '^my-tool\s+(delete|destroy)(\s|$)'; then
    debug_log "Matched my-tool dangerous"
    return 0
fi
```

### Creating Custom Agents

Create a new `.md` file in `agents/` with frontmatter:

```yaml
---
name: my-agent
description: Description shown in Claude Code
color: blue
tools: Write, Read, Bash, Grep
---

Your agent system prompt here...
```

## Debugging

Enable debug mode in `smart-readonly-analyzer.py`:

```bash
# Set to true for debugging
DEBUG=true
```

This will output detailed pattern matching logs:
```
🔍 DEBUG: Matched Django read-only command
🔍 DEBUG: Entering AI analysis path
🔍 DEBUG: AI analyzer exit code: 0
```

## Requirements

- Claude Code CLI
- Bash (for smart-readonly-analyzer)
- Python 3.x (for AI fallback)
- `anthropic` Python package (optional, for AI analysis)
- `jq` (for JSON parsing in hooks)

## Note

The `smart-readonly-analyzer.py` file is actually a Bash script (note the `#!/bin/bash` shebang). The `.py` extension may be a misnomer - consider renaming to `.sh` for clarity. Update `settings.json` accordingly if you rename it.
