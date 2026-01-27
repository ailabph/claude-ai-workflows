# Changelog

All notable changes to orchestrator-auto will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.2] - 2026-01-27

### Added

- **Watch TUI: Context visibility** - Repo name and branch displayed in header subtitle (auto-refreshes every 30s), current plan filename with per-file elapsed time in status panel
- **Watch TUI: Copy session ID** - Press `y` to copy current/paused session ID to clipboard
- **Watch TUI: View full blocker** - Press `b` to open modal showing full blocker question with respond option
- **Watch TUI: Panel navigation** - Press `Tab`/`Shift+Tab` to cycle focus between panels, `j`/`k` to scroll focused panel
- **Watch TUI: Log filtering** - Press `1`/`2`/`3` to filter log panel (errors only, +warnings, all)
- **Watch TUI: Pause polling** - Press `p` to pause/resume directory polling without stopping in-flight execution
- **WatchController: Pause API** - New `pause_polling()`, `resume_polling()`, `is_polling_paused()` methods with `POLLING_PAUSED`/`POLLING_RESUMED` events
- **BlockerModal screen** - New modal screen for viewing full blocker questions

### Changed

- **LogPanel: Filter support** - Added `set_filter_level()` method and filter indicator in border title
- **WatchPanel: Polling status** - New `set_polling_paused()` method to show paused state

## [1.1.1] - 2026-01-25

### Changed

- **Todo parser: blank line support** - Multi-line tasks now support blank lines between checkbox and continuation content, enabling more readable task formats with paragraph breaks and nested bullets

## [1.1.0] - 2026-01-16

### Added

- **CLI: `--tui` on watch command** - Enable TUI for directory watch mode (`orchestrator start --watch ./plans --tui`)

### Changed

- **Unified WatchController** - CLI and TUI now share the same WatchController for consistent behavior

### Fixed

- **Watch option passthrough** - All watch options (poll interval, convert, auto-commit, telegram) now correctly passed to TUI mode with warnings for unsupported options
- **Milestone pattern validation** - Unified milestone header pattern (`## Milestone` or `### Milestone`) across start and watch modes
- **Watch mode parity** - Addressed regressions in unified watch mode (file processing, state tracking)
- **Output callback handling** - Always pass output_callback regardless of show_activity setting in watch mode
- **Rich markup in AgentOutput** - Disabled Rich markup parsing to prevent crashes on agent output containing bracket patterns

## [1.0.0] - 2026-01-16

### Added

- **TUI (Text User Interface)** - Full terminal UI for all orchestrator modes
- **CLI: `--tui`** - Enable TUI on `start`, `resume`, `watch`, and queue commands
- **Single Session TUI** - Real-time streaming output, status panel, milestone tracking
- **Queue TUI** - Queue progress visualization, item status, current session detail
- **Watch TUI** - Directory monitoring, file status tracking, processing stats
- **Responsive layouts** - Adapts to terminal width (small <80, medium 80-119, large 120+)
- **HelpScreen** - Modal with keybinding reference for each mode (`?` key)
- **SessionPickerScreen** - Resume session selection with status indicators
- **Thread-safe adapters** - TUIOutputAdapter and TUIInputProvider bridge worker threads to UI
- **StatusPanel widget** - Phase, status, models, API calls, tokens, elapsed time
- **MilestoneList widget** - Progress tracking with checkmarks
- **AgentOutput widget** - Streaming output with syntax highlighting and auto-scroll
- **LogPanel widget** - Orchestrator message log with level indicators
- **InputModal widget** - Modal for blocker/discovery input
- **QueuePanel widget** - Queue item list with position and status
- **WatchPanel widget** - Watch directory stats, pending files, last result
- **New package** - `orchestrator_auto.tui` with widgets, screens, messages, adapters
- **Optional dependency** - `pip install orchestrator-auto[tui]` (requires textual>=0.80.0)

### Changed

- **Version 1.0.0** - First stable release with complete TUI implementation

## [0.13.0] - 2026-01-16

### Added

- **CLI: `todo`** - Batch task execution from markdown checkbox files
- **Fresh agent context** - Each task runs in isolated session (no token accumulation)
- **Checkbox format** - `[ ]` pending, `[x]` done, `[!]` failed
- **File references** - `@path/to/file` injects file contents as context
- **Completion tags** - Agents must output `[TASK_DONE]` or `[TASK_FAILED]`
- **CLI flags** - `--retry-failed`, `--dry-run`, `--verbose`, `--timeout`, `-m/--model`
- **MCP support** - `--mcp-config` for external tools
- **New modules** - `todo.py` (TodoRunner), `todo_parser.py` (checkbox parsing)

### Security

- **Path restrictions** - `@path` only allows relative paths within task directory
- **Symlink rejection** - Symlinks pointing outside task directory are rejected
- **Parent escape blocked** - `../` path traversal is rejected

### Fixed

- **Content-matching guard** - Prevents updating wrong checkbox when line numbers drift due to agent file modifications
- **Whitespace preservation** - Exact formatting preserved when updating checkbox markers (multiple spaces, tabs)
- **Atomic file updates** - Re-reads file before applying updates to avoid clobbering agent edits

## [0.12.1] - 2026-01-14

### Fixed

- Plan file parser now accepts both `##` and `###` for milestone headers
- Previously only `### Milestone N: Name` was recognized; now `## Milestone N: Name` also works

## [0.12.0] - 2026-01-10

### Changed

- Agent permission mode changed from `acceptEdits` to `bypassPermissions`
- Agents can now run Bash commands (tests, builds, etc.) without approval blocks

### Fixed

- Agents no longer get stuck waiting for Bash command approval when running tests
- Resolves issue where agents would ask humans to run tests due to permission blocks

## [0.11.2] - 2026-01-09

### Fixed

- **Unclosed tag detection** - `[PROGRESS_REPORT]` without closing `[/PROGRESS_REPORT]` is now correctly detected as truncated, triggering auto-continue instead of pausing
- **Planner auto-continue** - Extended auto-continue support to planner responses (previously executor-only)
- **Empty issues fallback** - When `[CHANGES_REQUESTED]` has no parsed issues, executor receives helpful fallback message instead of empty feedback
- **CLI: `--headless` on `respond`** - Added missing `--headless` flag to `respond` command for continuing paused sessions

### Technical

- Added 25+ unit tests for truncation detection and continuation flow
- Refactored `_route_to_executor()` to include truncation handling for consistency with `_route_to_planner()`

## [0.11.1] - 2026-01-08

### Added

- **CLI: `--headless`** - Run Playwright MCP browser in headless mode (no browser window). Available on `start`, `resume`, `watch`, and `respond` commands.
- **Auto-continue on truncated responses** - Automatically detects when planner or executor responses are truncated (e.g., hitting token limits mid-stream) and prompts the agent to continue, preventing unnecessary pauses.

### Technical

- **New function: `inject_headless_mode()`** - Automatically injects `--headless` into Playwright MCP server args
- **New function: `is_response_truncated()`** - Heuristic detection of incomplete responses (ends with `:`, "Let me...", etc.)
- **Improved error handling** - Better error messages when continuation also fails

## [0.11.0] - 2026-01-10

### Changed

- Updated Planner system prompt with explicit "Tool Usage" section
- Planner now instructed to run tests via Bash during validation instead of asking the human
- Clarified human's role is requirements and decisions, not command execution

### Fixed

- Planner no longer asks users to run tests or execute commands it can perform itself

### Added

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

## [0.10.1] - 2026-01-05

### Added

- **Graceful error handling** - User-friendly error messages with log file paths
- **Per-session logging** - Stack traces logged to `~/.claude_orchestrator/logs/error_<session_id>_<timestamp>.log`
- **Lazy file creation** - Log files only created when errors occur (no empty files)
- **CLI: `--debug`** - Flag for immediate stack trace output on `start` and `resume` commands
- **CLI: `status`** - Shows error details (type, message, log path) for failed sessions
- **Custom exceptions** - `OrchestratorError`, `AgentError`, `SessionStateError`, `PlanParseError` with session context
- **DB: `session_errors` table** - Persist error details for debugging and retry guidance
- **New modules** - `logging_config.py` (per-session loggers), `exceptions.py` (exception hierarchy)

## [0.10.0] - 2026-01-04

### Added

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

## [0.9.1] - 2026-01-02

### Fixed (Critical)

- **Blocker response not sent to agent** - When humans responded to blockers, the answer was logged but never actually sent to the agent that raised the blocker. Added `_inject_pending_response()` method that delivers human responses to the appropriate agent's conversation on resume, ensuring continuity.

- **BLOCKED tag parser too strict** - The `[BLOCKED]` response parser required exact text `Cannot proceed:` after the tag, causing valid blocker responses like `[BLOCKED] Cannot execute tests...` to be parsed as "Unexpected response format". Parser now accepts any text after `[BLOCKED]`.

- **MILESTONE_APPROVED parser too strict** - The `[MILESTONE_APPROVED]` parser required "Milestone N approved" text. Now accepts the tag alone and extracts milestone number if present in the response.

- **Unrecognized response creates proper blocker** - When planner/executor responses didn't match expected tags, the code returned "blocked" without creating a blocker record, leaving sessions in an inconsistent state. Now creates proper blocker with descriptive message.

### Fixed (Medium)

- **Infinite loop prevention in changes_requested** - Added retry counter (max 3 attempts) for milestone changes. After max retries, pauses for human intervention instead of looping indefinitely. Also fixed `_route_to_planner` to return executor's response to feedback, avoiding duplicate milestone prompts.

### Fixed (Minor)

- **Event loop conflicts in agents** - Removed global event loop setting (`asyncio.set_event_loop()`) that caused conflicts when planner and executor agents were both active. Each agent now manages its own event loop without global side effects.

- **current_milestone falsy check** - Changed `current_milestone or 1` to explicit None check (`if current_milestone is not None`) to properly handle edge case where milestone could be 0.

- **Truncated diff warning to AI** - When large diffs are truncated for AI commit message generation, the AI is now informed with a `[DIFF TRUNCATED]` marker so it doesn't make assumptions about unseen code changes.

### Added

- **CLI: `complete`** - Force-complete stuck sessions that have finished all work but are blocked due to incorrect milestone counts or unresolvable blockers. Supports `--auto-commit` for committing changes.

### Improved

- **Blocker message shows CLI command** - When a blocker occurs, the message now shows a copy-paste ready CLI command (`orchestrator respond <id> "answer"`) instead of Python code.

## [0.9.0] - 2025-12-30

### Added

- **Auth Source Detection** - Display detected auth method at startup (API key, OAuth, cloud providers)
- **Multi-signal detection** - Detects env vars + credentials file (~/.claude/.credentials.json on Linux)
- **Session tracking** - Auth source stored in database per session
- **CLI: `check`** - Health check command for dependencies, permissions, auth, and API connection
- **CLI: `check` OAuth support** - Tests OAuth tokens via Claude Agent SDK, API keys via Anthropic SDK
- **CLI: `status`** - Shows auth method used for session
- **CLI: `export`** - Includes auth method in markdown export
- **New module** - `auth.py` with `detect_auth()`, `format_auth_display()`
- **DB schema** - Added `auth_source`, `auth_signals`, `auth_detected_at` columns

## [0.8.0] - 2025-12-28

### Added

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

## [0.7.0] - 2025-12-25

### Added

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

## [0.6.0] - 2025-12-22

### Added

- **Telegram Phase 2** - Inbound blocker responses via `orchestrator telegram listen`
- **Project scoping** - Sessions tagged with `project_id`; CLI commands filter by current project
- **Repo-local config** - Support for `<repo>/.claude_orchestrator/config.yaml` with deep merge
- **CLI: `--all-projects`** - Show sessions from all projects in `list` command
- **CLI: `telegram listen`** - Poll for Telegram replies to blocker notifications
- **DB: `telegram_state` table** - Persist polling cursor across restarts
- **DB: `telegram_message_id`** - Track blocker notification messages for reply routing

## [0.5.0] - 2025-12-18

### Added

- **Telegram Phase 1** - Outbound notifications (start, milestone, blocker, complete)
- **Heartbeat hardening** - Stuck session detection with `heartbeat_at` timestamp
- **CLI: `--telegram/--no-telegram`** - Enable/disable notifications
- **CLI: `orchestrator telegram test`** - Validate bot configuration
- **CLI: `orchestrator reset`** - Reset orphaned sessions
- **CLI: `--force` flag** - Force resume with guardrails
- **Config: `stuck_sessions.inactive_minutes`** - Configurable threshold (default 20 min)

## [0.4.0] - 2025-12-15

### Added

- **Model selection** - `-pm`/`-em` flags with aliases (opus/sonnet/haiku)
- **Auto-commit** - `--auto-commit` flag for git commit on completion
- **Config file** - `~/.claude_orchestrator/config.yaml` for default models

## [0.3.0] - 2025-12-12

### Added

- **Conversation continuity** - ClaudeSDKClient for persistent agent sessions
- **Multi-line paste** - Support for pasting multi-line input with preview
- **Discovery UX** - Wait for user input, improved `/ready` detection

### Fixed

- Response handling with ResultMessage termination

## [0.2.0] - 2025-12-08

### Added

- **`--plan` flag** - Import existing plan files, skip discovery/planning
- **Activity indicator** - Streaming snippets with token count
- **Plan saving** - Engine saves plan file from `PLAN_CONTENT` tags

## [0.1.0] - 2025-12-05

### Added

- **Two-agent orchestration** - Planner (Opus) + Executor (Sonnet) workflow
- **Milestone-gated execution** - Planner reviews each milestone before proceeding
- **Session persistence** - SQLite database for workflow state and history
- **CLI commands** - `start`, `resume`, `respond`, `list`, `status`, `export`
- **Blocker handling** - Pause workflow for human input
- **Agent SDK integration** - Async query pattern with auto-approve
