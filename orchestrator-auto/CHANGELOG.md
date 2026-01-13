# Changelog

All notable changes to orchestrator-auto will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

## [0.11.0] - 2026-01-10

### Changed

- Updated Planner system prompt with explicit "Tool Usage" section
- Planner now instructed to run tests via Bash during validation instead of asking the human
- Clarified human's role is requirements and decisions, not command execution

### Fixed

- Planner no longer asks users to run tests or execute commands it can perform itself

## [0.10.0] - Previous Release

- Queue mode for sequential plan execution
- Telegram notifications and blocker replies
- Auto-commit with smart commit messages
- Watch mode for directory monitoring
- Session recovery and context compression handling
- SQLite persistence for sessions, messages, milestones, blockers
