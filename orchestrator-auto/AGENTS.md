# AGENTS.md (orchestrator-auto)

This file scopes to the `orchestrator-auto/` subtree and overrides repo-root rules.
This project is a Python CLI + SQLite persistence layer for orchestrating a two-agent workflow.

---

## Architecture & Mental Model

Read `docs/ARCHITECTURE.md` for full diagrams. Summary below.

### Two-Agent Orchestration Loop

```
User → Orchestrator (engine.py)
          ├── PlannerAgent (Claude Opus)
          │     Phase 1 DISCOVERY: asks clarifying questions
          │     Phase 2 PLANNING:  creates milestone plan, writes plan file
          │     Phase 3 REVIEW:    validates executor reports, approves/rejects
          └── ExecutorAgent (Claude Sonnet/Haiku)
                Phase 3 EXECUTION: implements ONE milestone, sends progress report, STOPS
```

The engine routes messages between agents. Agents never talk directly to each other — everything goes through `engine.py`.

### Workflow Phases (state machine)

```
discovery → planning → execution → completed
    ↓           ↓          ↓
  paused ←────────────────── (any phase, on blocker)
  paused → previous_phase   (on human response)
```

State is persisted in SQLite. The `StateMachine` in `state.py` validates all transitions — you cannot jump phases arbitrarily.

### Response Tag Protocol (inter-agent communication contract)

Agents output structured tags in their text responses. `parser.py` detects these and `engine.py` routes them. **This is the core communication contract — do not break it.**

| Tag | Agent | Meaning | Engine action |
|-----|-------|---------|---------------|
| `[PLAN_READY]` + `Path:` + `Milestones:` | Planner | Plan file written | Save plan, transition → execution |
| `[PLAN_CONTENT]...[/PLAN_CONTENT]` | Planner | Inline plan content | Extract and save to disk |
| `[MILESTONE_APPROVED]` | Planner | Milestone accepted | Increment milestone counter, send next prompt to executor |
| `[CHANGES_REQUESTED]` | Planner | Milestone rejected | Re-send executor with feedback |
| `[HUMAN_INPUT_NEEDED]` | Planner | Needs human answer | Create blocker, pause workflow |
| `[PROGRESS_REPORT]...[/PROGRESS_REPORT]` | Executor | Milestone complete | Display to user, wait for planner review |
| `[CLARIFICATION_NEEDED]` | Executor | Needs clarification | Create blocker, pause workflow |
| `[BLOCKED]` | Executor | Cannot proceed | Create blocker, pause workflow |

If a response ends mid-sentence or with a colon, `parser.py:is_response_truncated()` detects it and `engine.py` auto-continues (handles token limit cutoffs).

---

## Module Map (where to look)

### Entry Points
| File | Role |
|------|------|
| `cli.py` | Click CLI — all commands (`start`, `resume`, `respond`, `watch`, `queue`, `chat`, `chat-mode`, `convert`, `check`, `telegram`) |
| `engine.py:Orchestrator` | Core loop — runs discovery/planning/execution phases, routes messages, handles blockers |
| `agents.py:BaseAgent` | SDK wrapper — persistent async event loop, conversation continuity, hooks, checkpoint/rewind |
| `state.py:StateMachine` | Phase transitions — validates moves, persists to DB |
| `parser.py` | Tag detection — parses planner/executor responses into typed tuples |
| `prompts.py` | System prompts — `PLANNER_SYSTEM_PROMPT`, `EXECUTOR_SYSTEM_PROMPT`, templates |
| `db.py` | All SQLite ops — sessions, messages, blockers, milestones, queue items |
| `config.py` | Model aliases, config file loading, MCP config parsing |

### Subsystems
| Package / File | Role |
|----------------|------|
| `io/input_provider.py` | `InputProvider` ABC + `CLIInputProvider` — pluggable user input (CLI, TUI, Telegram) |
| `io/events.py` | IO event types passed between engine and input layer |
| `controllers/queue_controller.py` | Queue mode — sequential plan execution, fail-forward, crash recovery |
| `controllers/watch_controller.py` | Watch mode — directory polling, file state machine (`_done`, `_failed`, `_paused`) |
| `validation/` | Input validation pipeline (security, API, performance checks) |
| `chat_backend.py` | Callback-driven agent wrapper for chat-mode TUI path |
| `tui/app.py` | Main TUI (Textual) — connects to engine via `tui/adapter.py` |
| `tui/chat_app.py` | Chat-mode TUI app (ChatTUIApp, HelpModal, ConfirmModal) |
| `tui/chat_adapter.py` | Thread-safe bridge from ChatBackend callbacks → TUI messages |
| `tui/watch_app.py` | Watch mode TUI |
| `tui/queue_app.py` | Queue mode TUI |
| `tui/adapter.py` | Bridges engine callbacks → TUI messages |
| `tui/widgets/` | All reusable Textual widgets (stats, milestones, agent output, git panel, etc.) |
| `tui/widgets/chat_message_view.py` | Scrollable chat history with user/assistant bubbles (Markdown rendering) |
| `tui/widgets/chat_input_bar.py` | Text input + Send button for chat-mode |
| `tui/widgets/verbose_panel.py` | Tool calls + notification log for chat-mode (--verbose) |
| `telegram.py` | Send notifications + listen for blocker replies |
| `git.py` | Auto-commit after completion |
| `commit_ai.py` | AI-generated commit messages (Conventional Commits via Haiku) |
| `secrets.py` | Pre-commit secrets scanner (blocks diffs with API keys/tokens from being sent to AI) |
| `recovery.py` | Context recovery for compressed agent sessions |
| `explore.py` | Codebase exploration helpers |
| `convert.py` | AI-assisted plan format conversion (`orchestrator convert`) |
| `playwright_test.py` | Playwright MCP verification tool (`orchestrator test-playwright`) |
| `auth.py` | Auth source detection (API key, OAuth, Bedrock, Vertex, Foundry) |
| `output.py` | `StreamingIndicator` — live activity display during agent runs |
| `input_handler.py` | Multi-line paste support for CLI input |
| `todo.py` / `todo_parser.py` | Todo tracking |
| `logging_config.py` | Per-session file logging (`~/.claude_orchestrator/logs/`) |
| `exceptions.py` | `OrchestratorError`, `AgentError` |

---

## Key Implementation Patterns

### Agent lifecycle
Each agent (`PlannerAgent`, `ExecutorAgent`) owns its own `asyncio` event loop. **Never call `asyncio.set_event_loop()` on an agent loop** — this was explicitly removed to prevent planner/executor conflicts. See `agents.py:BaseAgent._get_loop()`.

```python
# Correct: agent manages its own loop
loop = self._get_loop()   # creates new_event_loop if needed
loop.run_until_complete(self.send_message_async(...))
```

### Agents always run bypassPermissions
`ClaudeAgentOptions` is always constructed with `permission_mode="bypassPermissions"`. This means both agents auto-approve all tool calls (Read, Write, Edit, Bash, Glob, Grep + any MCP tools). Do not add user-prompt logic inside agent tool calls.

### CLAUDE.md injection
`agents.py:build_system_prompt_with_claude_md()` prepends the project's `CLAUDE.md` to every agent's system prompt (capped at 50KB). This means agents working in a repo automatically inherit its project instructions. Controlled by `include_claude_md=True` (default).

### Checkpoint / rewind
Before each milestone, the executor's last message UUID is saved as a checkpoint. If a milestone is rejected, `agent.rewind_to_checkpoint()` reverts file changes made during that milestone. Controlled by `enable_rewind=True` (default). Implemented in `agents.py:BaseAgent.set_checkpoint()` / `rewind_to_checkpoint()`.

### Pluggable input via InputProvider
`engine.py` never calls `input()` directly. It calls `self.input_provider.get_input(prompt)`. For CLI this is `CLIInputProvider`; for TUI it's overridden by the adapter. When adding new input modes, implement `io/input_provider.py:InputProvider`.

### Token usage callbacks
Agents accept `on_token_usage: Callable[[Dict], None]`. The engine passes an `on_token_usage` closure that scopes usage by agent name (planner/executor) and forwards to `on_token_usage(agent_name, usage_dict)` at the orchestrator level. TUI subscribes to this for the stats panel.

### MCP servers (per-agent scoping)
`.mcp.json` supports per-agent tool scoping via an `"orchestrator"` key:
```json
{
  "mcpServers": { "playwright": {...}, "figma": {...} },
  "orchestrator": {
    "planner": { "mcpServers": ["figma"], "tools": ["mcp__figma__*"] },
    "executor": { "mcpServers": ["playwright"], "tools": ["mcp__playwright__*"] }
  }
}
```
Parsed by `config.py:get_agent_mcp_config()`. MCP config is stored in DB per session and restored on resume.

### Hooks
`BaseAgent._build_hooks()` always registers:
- `PostToolUseFailure` → `_on_tool_failure()` (tracks failures, logs warning)
- `Notification` → `_on_notification()` (tracks + forwards to `on_notification` callback)

Caller-provided hooks are merged in (same event key = extend list). Use `HookMatcher(matcher="*", hooks=[fn])`.

---

## Common Change Patterns

### Add a new CLI flag
1. Add Click option in `cli.py` (relevant command)
2. Pass through to `Orchestrator.__init__()` in `engine.py`
3. Store as `self._new_flag` and use in the phase method that needs it
4. Add to `docs/CLI_REFERENCE.md`

### Add a new CLI command
1. Define `@cli.command()` in `cli.py`
2. If it needs orchestration, instantiate `Orchestrator` or call the relevant module directly
3. Add to `docs/CLI_REFERENCE.md`

### Add a new agent capability (e.g. new tool)
1. Add tool name to `DEFAULT_TOOLS` in `agents.py` or pass via `allowed_tools`
2. If MCP: add to `.mcp.json` + `get_agent_mcp_config()` in `config.py`
3. Update `docs/CONFIGURATION.md` if config-driven

### Add a new workflow phase
1. Add new `Phase` enum value in `state.py`
2. Add valid transitions to `StateMachine.TRANSITIONS`
3. Add corresponding `_run_<phase>()` method in `engine.py`
4. Add `TransitionEvent` if needed
5. Update `docs/ARCHITECTURE.md` state diagram

### Add a new database column
1. Add to `db.py:init_db()` (CREATE TABLE statement)
2. Add to relevant `db.create_*()` / `db.get_*()` / `db.update_*()` functions
3. If session-level: add to `WorkflowState` dataclass in `state.py` and `WorkflowState.from_db()` / `to_db_update()`

### Add a new TUI widget
1. Create in `tui/widgets/<name>.py` as a Textual `Widget` subclass
2. Mount in `tui/app.py` (or relevant app) via `compose()`
3. Wire data via `tui/adapter.py` — engine callbacks → `app.post_message()`

### Add a new response tag
1. Add constant in `parser.py`
2. Add detection regex in `parse_planner_response()` or `parse_executor_response()`
3. Add handling in `engine.py` where the response is routed
4. Add tag to `prompts.py` system prompts so agents know to use it
5. Add to `is_response_truncated()` in `parser.py` (simple tags → no truncation, paired tags → check closing tag)

---

## Database Schema (key tables)

```
sessions        id, feature_description, phase, status, current_milestone,
                total_milestones, plan_path, previous_phase, planner_model,
                executor_model, project_id, project_remote, mcp_config,
                heartbeat_at, created_at, updated_at

messages        session_id, phase, agent, role, content, token_count

blockers        session_id, phase, agent, question, response,
                created_at, resolved_at

milestones      session_id, milestone_number, title, description, status
                (status: pending | in_progress | approved | rejected)

queue_items     id, project_id, plan_path, feature, status, session_id,
                position, created_at, updated_at
```

Access pattern: always use `db.get_connection(db_path)` context manager, never raw `sqlite3.connect()`.

---

## Model Aliases & Defaults

| Alias | Model ID | Default role |
|-------|----------|--------------|
| `opus` | `claude-opus-4-6` | Planner (default) |
| `sonnet` | `claude-sonnet-4-6` | Executor (default) |
| `haiku` | `claude-haiku-4-5-20251001` | Budget executor / commit AI |

Config priority: CLI flags > env vars > repo config (`.claude_orchestrator/config.yaml`) > global config (`~/.claude_orchestrator/config.yaml`) > defaults.

---

## Reference Docs

| Doc | When to read |
|-----|-------------|
| `docs/ARCHITECTURE.md` | Full data flow diagrams, state machine, blocker mechanics, design patterns |
| `docs/CLI_REFERENCE.md` | All commands and flags with examples |
| `docs/CONFIGURATION.md` | Config files, auth methods, Telegram setup, MCP setup, smart commit |
| `docs/TROUBLESHOOTING.md` | Common failure modes and fixes |
| `docs/FEATURE_*.md` | Design notes for specific implemented features |

---

## Quick Commands

### Environment / Install
```bash
# From repo root
cd orchestrator-auto

# Conda env
conda env create -f environment.yml
conda activate orchestrator-auto

# Editable install
pip install -e .

# Dev deps (pytest)
pip install -e ".[dev]"

# Optional Telegram support (httpx)
pip install -e ".[telegram]"

# Required for real agent runs
export ANTHROPIC_API_KEY="your-key"
```

### Run the CLI
```bash
orchestrator --help

orchestrator start -f "Feature description"
orchestrator start -f "Feature" -pm sonnet -em haiku
orchestrator start -f "Feature" --plan docs/plan.md
orchestrator start -f "Feature" --auto-commit
orchestrator start -f "Feature" --telegram

orchestrator list
orchestrator list --all-projects
orchestrator status <session-id>
orchestrator resume <session-id>
orchestrator resume <session-id> --force
orchestrator reset <session-id>
orchestrator respond <session-id> "Answer"
orchestrator export <session-id> -o report.md

# Queue mode
orchestrator start --queue plan1.md plan2.md
orchestrator start --queue            # resume existing queue
orchestrator start --queue --queue-reset plan1.md plan2.md
```

## Tests (pytest)
Run from `orchestrator-auto/`.

- All tests:
  ```bash
  pytest tests/ -v
  ```

- Single file:
  ```bash
  pytest tests/test_engine.py -v
  ```

- Single test:
  ```bash
  pytest tests/test_engine.py::TestOrchestratorInitialization::test_create_new_session -v
  ```

- Filter by name:
  ```bash
  pytest -k "planner" -v
  ```

- Queue integration tests:
  ```bash
  pytest tests/test_integration.py::TestQueueWorkflows -v
  pytest tests/test_integration.py::TestQueueWorkflows::test_queue_completes_sequentially -v
  ```

- Coverage (optional):
  ```bash
  pytest tests/ --cov=orchestrator_auto
  ```

## Lint / Format
No linter/formatter is configured in `pyproject.toml`.

- Optional local tooling:
  ```bash
  ruff check .
  ruff format .
  ```

## Code Style (follow existing patterns)

### Typing
- Python `>=3.10`.
- Type-hint public APIs.
- Prefer `Optional[T]` / `Dict[str, Any]` over newer union syntax to match the codebase.

### Imports
- Prefer stdlib → third-party → local; keep changes consistent within a file.

### Docstrings
- Use triple-double-quote docstrings for modules/classes/functions.
- Keep them short and descriptive.

### Paths
- Prefer `pathlib.Path`.
- Be careful with repo-relative paths vs user-provided paths.

### Error Handling
- Core modules commonly raise `ValueError` for invalid state/user input.
- At boundaries (CLI, network, subprocess) catch errors and surface a helpful message.
- Prefer specific exceptions; use broad `except Exception` only to prevent workflow crashes.

### Database
- Always use `db.get_connection()` context manager; it commits/rolls back automatically.
- Use parameterized SQL.

### Subprocess/Git
- Use `subprocess.run(..., capture_output=True, text=True, timeout=N)`.
- Keep timeouts on all git commands.

### Tests
- Use `pytest` fixtures (`tmp_path` when possible).
- Use `unittest.mock.patch` to avoid real API calls.
- Clean up any files/directories created by tests.
