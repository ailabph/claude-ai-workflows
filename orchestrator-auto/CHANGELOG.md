# Changelog

All notable changes to orchestrator-auto will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
