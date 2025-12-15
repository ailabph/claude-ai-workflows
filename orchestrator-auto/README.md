# Orchestrator Auto

**Automated two-agent workflow orchestration for complex software engineering tasks.**

Orchestrator Auto is a CLI tool that automates the milestone-based orchestrator workflow, managing planner and executor agents with persistent state, automatic context recovery, and human-in-the-loop oversight.

---

## Overview

Orchestrator Auto implements the [Claude Orchestrator Framework](../CLAUDE_orchestrator.md) as an automated CLI tool. It manages two Claude agents (Planner/Reviewer and Executor) that collaborate to implement complex features through a gated milestone workflow.

### Key Features

- **Automated Agent Communication** - Planner and executor agents communicate via structured message routing
- **State Persistence** - Complete workflow state saved to SQLite database
- **Pause/Resume** - Handle blockers gracefully, resume with human input
- **Context Recovery** - PreCompact hooks automatically restore agent context after compression
- **Milestone Tracking** - Automated milestone transitions with approval gates
- **Session Export** - Export complete workflow history to markdown
- **Colored CLI** - Progress indicators and status with terminal colors

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
│              │  (sessions,  │                                 │
│              │   messages,  │                                 │
│              │  milestones, │                                 │
│              │   blockers)  │                                 │
│              └──────────────┘                                 │
└──────────────────────────────────────────────────────────────┘
```

### Workflow Phases

1. **Discovery** - Interactive conversation with planner to refine requirements
2. **Planning** - Planner creates implementation plan with milestones
3. **Execution** - Executor implements milestones, planner reviews each one
4. **Completed** - All milestones approved
5. **Paused** - Workflow blocked, waiting for human input

---

## Installation

### Prerequisites

- Python 3.11+
- Anthropic API key
- Claude Agent SDK (`claude-agent-sdk`)

### Setup

1. **Clone and navigate to directory:**
   ```bash
   cd orchestrator-auto
   ```

2. **Create conda environment:**
   ```bash
   conda env create -f environment.yml
   conda activate orchestrator-auto
   ```

3. **Install in development mode:**
   ```bash
   pip install -e .
   ```

4. **Verify installation:**
   ```bash
   orchestrator --help
   ```

5. **Set API key (if not already set):**
   ```bash
   export ANTHROPIC_API_KEY="your-api-key"
   ```

---

## Quick Start

### Start a new workflow

```bash
orchestrator start -f "Add user authentication with JWT"
```

The orchestrator will:
1. Create a new session
2. Enter discovery phase for requirement refinement
3. Generate an implementation plan with milestones
4. Execute milestones with automatic planner review
5. Handle blockers and pause for human input when needed

### Resume a paused workflow

```bash
orchestrator list                    # Find your session ID
orchestrator resume <session-id>     # Resume workflow
```

### Respond to a blocker

When the workflow pauses due to a blocker:

```bash
orchestrator status <session-id>     # See the blocker question
orchestrator respond <session-id> "Your answer here"
```

---

## CLI Commands

### `start`

Start a new workflow session.

```bash
orchestrator start -f "Feature description" [-d /path/to/db.sqlite]
```

**Options:**
- `-f, --feature` (required): Feature description
- `-d, --db-path` (optional): Custom database path

**Example:**
```bash
orchestrator start -f "Implement user profile page with avatar upload"
```

---

### `resume`

Resume an existing workflow session.

```bash
orchestrator resume <session-id> [-a "answer"] [-d /path/to/db.sqlite]
```

**Arguments:**
- `session-id`: Session ID to resume

**Options:**
- `-a, --answer` (optional): Answer to blocker question
- `-d, --db-path` (optional): Custom database path

**Example:**
```bash
# Resume active session
orchestrator resume a1b2c3d4

# Resume paused session with answer
orchestrator resume a1b2c3d4 -a "Use PostgreSQL"
```

---

### `respond`

Respond to a blocker and continue workflow.

```bash
orchestrator respond <session-id> <answer> [-d /path/to/db.sqlite]
```

**Arguments:**
- `session-id`: Session ID
- `answer`: Answer to blocker question

**Options:**
- `-d, --db-path` (optional): Custom database path

**Example:**
```bash
orchestrator respond a1b2c3d4 "Use S3 for file storage"
```

---

### `list`

List all workflow sessions.

```bash
orchestrator list [-s status] [-d /path/to/db.sqlite]
```

**Options:**
- `-s, --status` (optional): Filter by status (`active`, `paused`, `completed`, `failed`)
- `-d, --db-path` (optional): Custom database path

**Example:**
```bash
# List all sessions
orchestrator list

# List only completed sessions
orchestrator list -s completed
```

---

### `status`

Show detailed status for a session.

```bash
orchestrator status <session-id> [-d /path/to/db.sqlite]
```

**Arguments:**
- `session-id`: Session ID

**Options:**
- `-d, --db-path` (optional): Custom database path

**Example:**
```bash
orchestrator status a1b2c3d4
```

**Output includes:**
- Session ID and feature description
- Current phase and status
- Milestone progress
- Unresolved blockers
- Message count
- Milestone history

---

### `export`

Export session history to markdown file.

```bash
orchestrator export <session-id> [-o output.md] [-d /path/to/db.sqlite]
```

**Arguments:**
- `session-id`: Session ID

**Options:**
- `-o, --output` (optional): Output file path (auto-generated if not specified)
- `-d, --db-path` (optional): Custom database path

**Example:**
```bash
# Export with auto-generated filename
orchestrator export a1b2c3d4

# Export to specific file
orchestrator export a1b2c3d4 -o session_report.md
```

**Export includes:**
- Session metadata
- Milestone details with reports
- Blocker history
- Complete message history by phase

---

## Configuration

### Database Location

By default, sessions are stored in `~/.claude_orchestrator/db.sqlite`.

Customize with `--db-path` option:
```bash
orchestrator start -f "My feature" -d /custom/path/db.sqlite
```

### Agent Models

Default models (configured in `orchestrator_auto/agents.py`):
- **Planner**: `claude-opus-4-5-20251101`
- **Executor**: `claude-sonnet-4-5-20250929`

To customize models, modify the agent factory functions in `agents.py`:
```python
def create_planner_agent(session_id, db_path=None, model="custom-model"):
    # ...
```

---

## Response Format Tags

The orchestrator uses structured tags for agent communication:

### Planner Tags

- `[PLAN_READY]` - Plan document created, ready for execution
- `[MILESTONE_APPROVED]` - Milestone approved, proceed to next
- `[CHANGES_REQUESTED]` - Milestone needs changes, executor should revise
- `[HUMAN_INPUT_NEEDED]` - Blocker, need human clarification

### Executor Tags

- `[PROGRESS_REPORT]` - Milestone completion report
- `[CLARIFICATION_NEEDED]` - Need planner clarification
- `[BLOCKED]` - Blocked by external dependency

---

## Example Workflow

```bash
# 1. Start a new feature
$ orchestrator start -f "Add dark mode toggle to settings"

Starting new workflow session...
Feature: Add dark mode toggle to settings

✓ Session created: x7y8z9

============================================================
Session: x7y8z9
Phase: DISCOVERY
Status: ACTIVE
============================================================

[Planner starts discovery conversation...]
Planner: "I'll help you implement dark mode. Let me ask a few questions..."

# 2. Discovery phase continues with back-and-forth
# User types /ready when requirements are clear

# 3. Planner creates plan
[PLAN_READY] Implementation plan created at: docs/dark-mode/DOC_dark_mode_plan.md
Milestones: 3 total

# 4. Execution begins - Milestone 1
Executor: Implementing theme context and provider...

[PROGRESS_REPORT]
## Milestone 1: Theme Infrastructure - COMPLETED
...
[/PROGRESS_REPORT]

Planner: [MILESTONE_APPROVED] Milestone 1 approved. Proceed to Milestone 2.

# 5. Workflow continues through all milestones...

# 6. If blocker occurs
Planner: [HUMAN_INPUT_NEEDED] Should we persist theme preference in localStorage or database?

============================================================
Session: x7y8z9
Phase: PAUSED
Status: PAUSED
============================================================

# 7. Respond to blocker
$ orchestrator respond x7y8z9 "Use localStorage for quick access"

Resuming workflow...

# 8. Complete workflow
[All milestones complete]

============================================================
Session: x7y8z9
Phase: COMPLETED
Status: COMPLETED
============================================================

✓ Workflow completed!

# 9. Export session history
$ orchestrator export x7y8z9 -o dark_mode_session.md

✓ Session exported to: dark_mode_session.md
  Messages: 38
  Milestones: 3
  Blockers: 1
```

---

## Development

### Project Structure

```
orchestrator-auto/
├── orchestrator_auto/
│   ├── __init__.py
│   ├── __main__.py          # Entry point
│   ├── cli.py               # CLI interface
│   ├── engine.py            # Core orchestration logic
│   ├── state.py             # State machine
│   ├── parser.py            # Response parsing
│   ├── agents.py            # Agent wrappers
│   ├── recovery.py          # Context recovery
│   ├── prompts.py           # System prompts
│   └── db.py                # Database operations
├── tests/
│   ├── test_db.py           # Database tests
│   ├── test_agents.py       # Agent tests
│   ├── test_state.py        # State machine tests
│   ├── test_parser.py       # Parser tests
│   ├── test_engine.py       # Engine tests
│   ├── test_cli.py          # CLI tests
│   └── test_integration.py  # E2E tests
├── environment.yml           # Conda environment
├── pyproject.toml           # Package config
└── README.md                # This file
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_engine.py -v

# Run with coverage
pytest tests/ --cov=orchestrator_auto
```

### Code Style

The codebase follows:
- PEP 8 style guidelines
- Type hints for function signatures
- Docstrings for all public APIs

---

## Troubleshooting

### Session not found

**Error:** `Session 'xyz' not found`

**Solution:** Use `orchestrator list` to find valid session IDs.

---

### Database locked

**Error:** `database is locked`

**Solution:** Only one orchestrator instance can access the database at a time. Close any running instances.

---

### Agent timeout

**Error:** Agent request timeout

**Solution:** Check your internet connection and API key. The Claude API may be experiencing high load.

---

### Context compression

The agents automatically handle context compression via PreCompact hooks. If you notice context loss:

1. Check that hooks are registered (logged in debug output)
2. Verify database contains message history
3. Review recovery prompts in `recovery.py`

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

---

## Future Features / TODO

- [ ] **Model Selection CLI Options** - Add `--planner-model` and `--executor-model` flags to allow choosing different Claude models (e.g., use Haiku for executor to reduce costs)
- [ ] **Auto-Commit on Completion** - Have the planner automatically create a git commit (without pushing) after all milestones are approved. Commit message should summarize the feature implemented.
- [x] **Activity Indicator** - Add CLI UI feedback showing streaming snippets with token count. Use `--no-activity` to disable. See `docs/FEATURE_activity_indicator.md`.
- [x] **Import Existing Plan** - Add `--plan` flag to start a session with a pre-existing milestone plan file, skipping discovery and planning phases. Useful for reusing proven plan templates or resuming failed workflows with a known-good plan.

---

## License

See parent repository for license information.

---

## Related Documentation

- [CLAUDE_orchestrator.md](../CLAUDE_orchestrator.md) - Full orchestrator framework documentation
- [DOC_orchestrator_auto_plan.md](../docs/orchestrator-auto/DOC_orchestrator_auto_plan.md) - Implementation plan for this tool
- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk) - SDK documentation

---

## Support

For issues or questions:
- Open an issue in the parent repository
- Check the orchestrator framework documentation
- Review test cases for usage examples
