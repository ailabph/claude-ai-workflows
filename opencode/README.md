# Smart Read-Only Analyzer

Claude Code plugins that automatically approve read-only bash commands and block dangerous operations, reducing permission prompts during development sessions.

## Overview

These plugins hook into Claude Code's permission system to:
- **Auto-approve** known read-only commands (tests, linters, git status, etc.)
- **Auto-block** dangerous commands (rm, sudo, git push, etc.)
- **AI fallback** for uncertain commands - uses Claude to analyze if a command is safe

## Files

| File | Description |
|------|-------------|
| `readonly-analyzer.js` | Minimal version with basic patterns and AI fallback |
| `smart-readonly-analyzer.js` | Comprehensive version with 50+ framework-specific patterns |

## Installation

### 1. Copy the plugin to your project

```bash
# Copy to your project root
cp smart-readonly-analyzer.js /path/to/your/project/
```

### 2. Configure Claude Code settings

Add to your project's `.claude/settings.json` or global `~/.claude/settings.json`:

```json
{
  "hooks": {
    "permission.ask": {
      "command": "node /path/to/your/project/smart-readonly-analyzer.js"
    }
  }
}
```

Or use as a Claude Code plugin by adding to your settings:

```json
{
  "plugins": [
    "/path/to/your/project/smart-readonly-analyzer.js"
  ]
}
```

## Supported Patterns

### Read-Only (Auto-Approved)

| Category | Examples |
|----------|----------|
| **System** | `ls`, `cat`, `grep`, `find`, `head`, `tail`, `wc`, `pwd`, `tree`, `file` |
| **Git** | `git status`, `git log`, `git diff`, `git branch`, `git blame` |
| **Python Testing** | `pytest`, `python -m pytest`, `tox`, `unittest` |
| **Python Linting** | `mypy`, `pylint`, `flake8`, `ruff check`, `bandit` |
| **Python Format Check** | `black --check`, `isort --check`, `autopep8 --diff` |
| **Django** | `manage.py test`, `manage.py check`, `manage.py showmigrations`, `manage.py show_urls` |
| **Node.js** | `npm test`, `yarn test`, `jest`, `vitest`, `mocha` |
| **Node Linting** | `eslint`, `prettier --check`, `tsc --noEmit` |
| **Next.js** | `next lint`, `next info` |
| **React/Vue/Angular** | `react-scripts test`, `vue lint`, `ng test`, `ng lint` |
| **Ruby/Rails** | `rspec`, `rails routes`, `rubocop`, `rails db:migrate:status` |
| **PHP/Laravel** | `phpunit`, `artisan test`, `artisan route:list`, `phpcs` |
| **Rust** | `cargo check`, `cargo test`, `cargo clippy`, `rustfmt --check` |
| **Go** | `go test`, `go vet`, `go list`, `go fmt -n` |
| **Java** | `mvn test`, `gradle test`, `./gradlew check` |
| **Docker** | `docker ps`, `docker images`, `docker logs`, `docker inspect` |
| **Kubernetes** | `kubectl get`, `kubectl describe`, `kubectl logs` |
| **Terraform** | `terraform plan`, `terraform validate`, `terraform show` |
| **GitHub CLI** | `gh pr list`, `gh issue view`, `gh api GET` |
| **AWS CLI** | `aws s3 ls`, `aws ec2 describe-*`, `aws * list-*` |

### Dangerous (Auto-Blocked)

| Category | Examples |
|----------|----------|
| **System** | `rm`, `sudo`, `mv`, `dd`, `mkfs`, `shutdown`, `kill` |
| **Git** | `git push`, `git reset --hard`, `git clean -fd`, `git rebase` |
| **Package Install** | `pip install`, `npm install`, `yarn add`, `brew install` |
| **Docker** | `docker rm`, `docker rmi`, `docker stop`, `docker build` |
| **Kubernetes** | `kubectl delete`, `kubectl apply`, `kubectl create` |
| **AWS** | `aws * delete-*`, `aws s3 rm`, `aws * terminate-*` |
| **Database** | SQL with `DROP`, `DELETE`, `UPDATE`, `TRUNCATE` |
| **Django** | `manage.py migrate` (without `--plan`), `makemigrations`, `flush` |
| **Formatters** | `black` (without `--check`), `prettier --write` |

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    Bash Command Request                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                   ┌─────────────────────┐
                   │  Check Read-Only    │
                   │  Pattern Match      │
                   └─────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
         ✅ Match       No Match        🚫 Match
         (allow)            │           (deny)
                            ▼
                   ┌─────────────────────┐
                   │  Check Dangerous    │
                   │  Pattern Match      │
                   └─────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
         🚫 Match      No Match      ✅ Safe
         (deny)             │
                            ▼
                   ┌─────────────────────┐
                   │  AI Analysis        │
                   │  (Claude API)       │
                   └─────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
         ✅ ReadOnly   ❓ Uncertain  🚫 Dangerous
         (>80% conf)   (ask user)   (>85% conf)
```

## Console Output

The plugin logs decisions to the console:

```
✅ SmartReadOnlyAnalyzer plugin loaded!
✅ Auto-approved (pattern): pytest tests/ -v
✅ Auto-approved (pattern): git status
🚫 Blocked (pattern): rm -rf node_modules
🤔 Analyzing with AI: python scripts/custom_script.py
🤖 AI Auto-approved: python scripts/custom_script.py
   Reason: Script only reads files and prints output
   Confidence: 92%
❓ AI uncertain (65%), asking user
```

## Customization

### Adding Custom Read-Only Patterns

Edit the `readOnlyPatterns` object in `smart-readonly-analyzer.js`:

```javascript
const readOnlyPatterns = {
  // Add your custom patterns
  myTool: /^my-custom-tool\s+(check|verify|list)(\\s|$)/,

  // Existing patterns...
};
```

### Adjusting AI Confidence Thresholds

```javascript
// In the permission.ask handler
if (analysis.isReadOnly && analysis.confidence > 0.80) {  // Adjust this
  return { status: "allow" };
}
```

## Versions

### `readonly-analyzer.js` (Minimal)
- Basic safe commands: `ls`, `cat`, `grep`, `find`, `head`, `tail`, `pwd`, `echo`, `git status`, `git log`, `git diff`, `wc`, `file`
- Basic dangerous patterns: `rm`, `mv`, `cp >`, `git push`, `sudo`, `> /`, `curl -X POST/PUT/DELETE`
- AI fallback with 85% confidence threshold

### `smart-readonly-analyzer.js` (Comprehensive)
- 50+ framework-specific patterns
- Detailed dangerous pattern matching
- AI fallback with 80% (read-only) / 85% (dangerous) thresholds
- Detailed console logging

## Requirements

- Claude Code CLI
- Node.js (for running the plugin)
- Anthropic API key (for AI fallback analysis)

## License

MIT
