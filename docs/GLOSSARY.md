# Documentation Glossary

Quick-reference index for agents, AI assistants, and LLMs working in this repository. Start here to find the right file for any topic.

## How to Use This File

1. Identify what you need (architecture, CLI usage, a specific feature, etc.)
2. Find the matching section below
3. Read the linked file before making changes

---

## Project Root

| File | What It Covers |
|------|---------------|
| [README.md](../README.md) | Project overview, quick start, feature list, CLI cheat sheet |
| [CLAUDE.md](../CLAUDE.md) | **Primary context file for agents.** Architecture, dev commands, code style, milestone patterns, response tags, config priority |
| [AGENTS.md](../AGENTS.md) | Repo-wide scoping rules for AGENTS.md files (nearest wins) |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Contribution guidelines |
| [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | Community standards |

---

## orchestrator-auto (Core CLI Tool)

### Essential Reading

| File | What It Covers | When to Read |
|------|---------------|-------------|
| [orchestrator-auto/README.md](../orchestrator-auto/README.md) | Package overview, install, architecture, workflow phases, module map | Starting any work on the CLI tool |
| [orchestrator-auto/AGENTS.md](../orchestrator-auto/AGENTS.md) | Scoped dev rules, env setup, test commands, code conventions | Before writing or modifying orchestrator-auto code |
| [orchestrator-auto/CHANGELOG.md](../orchestrator-auto/CHANGELOG.md) | Version history, breaking changes, migration notes | Checking what changed between versions |

### Architecture & Internals

| File | What It Covers | When to Read |
|------|---------------|-------------|
| [orchestrator-auto/docs/ARCHITECTURE.md](../orchestrator-auto/docs/ARCHITECTURE.md) | Session lifecycle, state machine transitions, data flow, module interaction diagram | Understanding how the orchestrator engine works internally |

### User-Facing Documentation

| File | What It Covers | When to Read |
|------|---------------|-------------|
| [orchestrator-auto/docs/CLI_REFERENCE.md](../orchestrator-auto/docs/CLI_REFERENCE.md) | Complete CLI command reference with examples | Looking up command syntax, flags, or options |
| [orchestrator-auto/docs/CONFIGURATION.md](../orchestrator-auto/docs/CONFIGURATION.md) | Model aliases, config file format, env vars, priority order | Setting up or debugging configuration |
| [orchestrator-auto/docs/TROUBLESHOOTING.md](../orchestrator-auto/docs/TROUBLESHOOTING.md) | Common errors and solutions, debug techniques | Diagnosing runtime issues |

### Feature Documentation (Implemented)

| File | What It Covers |
|------|---------------|
| [orchestrator-auto/docs/FEATURE_telegram_integration.md](../orchestrator-auto/docs/FEATURE_telegram_integration.md) | Telegram bot architecture, one-bot-per-project pattern, notification flow |
| [orchestrator-auto/docs/FEATURE_activity_indicator.md](../orchestrator-auto/docs/FEATURE_activity_indicator.md) | Real-time streaming snippets during agent processing |
| [orchestrator-auto/docs/FEATURE_conversation_continuity.md](../orchestrator-auto/docs/FEATURE_conversation_continuity.md) | Persistent conversation context across agent messages |
| [orchestrator-auto/docs/FEATURE_model_selection.md](../orchestrator-auto/docs/FEATURE_model_selection.md) | CLI flags for planner/executor model selection |
| [orchestrator-auto/docs/DOC_implement_watch_mode.md](../orchestrator-auto/docs/DOC_implement_watch_mode.md) | Watch mode file state machine, candidate selection, rename logic |

### Plans (Implementation Specs)

| File | What It Covers |
|------|---------------|
| [orchestrator-auto/docs/PLAN_tui_implementation.md](../orchestrator-auto/docs/PLAN_tui_implementation.md) | TUI dashboard implementation plan |
| [orchestrator-auto/docs/PLAN_telegram_phase2.md](../orchestrator-auto/docs/PLAN_telegram_phase2.md) | Telegram DM-only listener for blocker replies |
| [orchestrator-auto/docs/PLAN_inject_exploration_context.md](../orchestrator-auto/docs/PLAN_inject_exploration_context.md) | Injecting codebase exploration results into executor context |
| [orchestrator-auto/docs/PLAN_watch_tui_layout_v2.md](../orchestrator-auto/docs/PLAN_watch_tui_layout_v2.md) | Watch mode TUI layout redesign |
| [orchestrator-auto/docs/PLAN_ssd_node_bootstrap_script.md](../orchestrator-auto/docs/PLAN_ssd_node_bootstrap_script.md) | Bootstrap script for headless server deployment |
| [orchestrator-auto/docs/RUNBOOK_ssd_node.md](../orchestrator-auto/docs/RUNBOOK_ssd_node.md) | Ops runbook for running orchestrator on Ubuntu SSD nodes |

### Proposals (Design RFCs)

| File | Status | What It Covers |
|------|--------|---------------|
| [proposals/PROPOSAL_subagent_exploration.md](../orchestrator-auto/docs/proposals/PROPOSAL_subagent_exploration.md) | Approved | Exploration sub-agents for deep codebase research |
| [proposals/PROPOSAL_subagent_research.md](../orchestrator-auto/docs/proposals/PROPOSAL_subagent_research.md) | Draft | Context-isolated research agents to avoid context pollution |
| [proposals/PROPOSAL_subagent_validation.md](../orchestrator-auto/docs/proposals/PROPOSAL_subagent_validation.md) | Draft | Pluggable validation sub-agents (security, perf, API) |
| [proposals/PROPOSAL_subagent_parallel_tasks.md](../orchestrator-auto/docs/proposals/PROPOSAL_subagent_parallel_tasks.md) | Draft | Parallel task execution within milestones |
| [proposals/PROPOSAL_multi_model_migration.md](../orchestrator-auto/docs/proposals/PROPOSAL_multi_model_migration.md) | Draft | Multi-provider LLM support (beyond Anthropic) |
| [proposals/PROPOSAL_empty_response_auto_retry.md](../orchestrator-auto/docs/proposals/PROPOSAL_empty_response_auto_retry.md) | Draft | Auto-retry for empty planner responses |
| [proposals/PROPOSAL_sdk_upgrade_0.1.23.md](../orchestrator-auto/docs/proposals/PROPOSAL_sdk_upgrade_0.1.23.md) | Draft | Claude Agent SDK upgrade path |
| [proposals/PROPOSAL_watch_tui_qol.md](../orchestrator-auto/docs/proposals/PROPOSAL_watch_tui_qol.md) | Draft | Watch TUI quality-of-life improvements |

### Implementation Tickets

| File | What It Covers |
|------|---------------|
| [proposals/IMPL_phase1a_exploration_subagent.md](../orchestrator-auto/docs/proposals/IMPL_phase1a_exploration_subagent.md) | Implementation ticket for exploration sub-agent |
| [proposals/IMPL_phase1b_validation_subagent.md](../orchestrator-auto/docs/proposals/IMPL_phase1b_validation_subagent.md) | Implementation ticket for validation sub-agent |
| [proposals/IMPL_watch_tui_layout_b.md](../orchestrator-auto/docs/proposals/IMPL_watch_tui_layout_b.md) | Watch TUI layout redesign (sub-agent aware) |

---

## Workflows

Workflow templates that define how agents execute tasks. The orchestrator feeds these to the planner agent.

| File | Task Type | When to Use |
|------|-----------|-------------|
| [CLAUDE_orchestrator.md](../workflows/CLAUDE_orchestrator.md) | **Any language/framework** | Default choice. General-purpose milestone framework |
| [CLAUDE_django_engineer_workflow.md](../workflows/CLAUDE_django_engineer_workflow.md) | Django REST APIs | Models, serializers, views, pytest, migrations |
| [CLAUDE_orchestrator_figma_visual_qa.md](../workflows/CLAUDE_orchestrator_figma_visual_qa.md) | Figma-to-code | Pixel-level comparison between Figma design and browser |
| [CLAUDE_frontend_refactor_v2.md](../workflows/CLAUDE_frontend_refactor_v2.md) | UI iteration | Screenshot-driven feedback loop for frontend changes |
| [CLAUDE_visual_qa_workflow.md](../workflows/CLAUDE_visual_qa_workflow.md) | Batch visual testing | Autonomous screenshot validation with self-correction |
| [CLAUDE_orch_solana.md](../workflows/CLAUDE_orch_solana.md) | Solana/Web3 | Security checklist + contract validation |
| [CLAUDE_orchestrator_batch.md](../workflows/CLAUDE_orchestrator_batch.md) | Batch orchestration | Multiple workflows in sequence |
| [CLAUDE_orch_v2.md](../workflows/CLAUDE_orch_v2.md) | Orchestrator v2 | Extended orchestrator variant |
| [CLAUDE_orch_ui_refactor.md](../workflows/CLAUDE_orch_ui_refactor.md) | UI refactoring | Orchestrated UI component refactoring |
| [CLAUDE_frontend_refactor_workflow.md](../workflows/CLAUDE_frontend_refactor_workflow.md) | Frontend refactor (v1) | Original frontend refactoring workflow |
| [CLAUDE_frontend_visual_qa_workflow.md](../workflows/CLAUDE_frontend_visual_qa_workflow.md) | Frontend visual QA | Visual QA specific to frontend components |

> **Not sure which workflow?** Start with `CLAUDE_orchestrator.md` -- it works for everything.

### Reference Variants (`*_ref.md`)

These are read-only reference copies of workflows with additional context or examples. They are not used directly by the orchestrator.

---

## Historical Docs (docs/orchestrator-auto/)

Plans and investigations from earlier development phases.

| File | What It Covers |
|------|---------------|
| [docs/orchestrator-auto/DOC_debugging_claude_cli_terminated_process.md](../docs/orchestrator-auto/DOC_debugging_claude_cli_terminated_process.md) | Debug notes on Claude CLI process termination issues |
| [docs/orchestrator-auto/DOC_mcp_tool_passing_investigation.md](../docs/orchestrator-auto/DOC_mcp_tool_passing_investigation.md) | Investigation into MCP tool passing to agents |
| [docs/orchestrator-auto/DOC_mcp_tool_passing_solution.md](../docs/orchestrator-auto/DOC_mcp_tool_passing_solution.md) | Solution for MCP tool passing |
| [docs/orchestrator-auto/DOC_telegram_ping_pong_plan.md](../docs/orchestrator-auto/DOC_telegram_ping_pong_plan.md) | Telegram bot ping-pong test plan |
| [docs/orchestrator-auto/PLAN_error_handling_logging.md](../docs/orchestrator-auto/PLAN_error_handling_logging.md) | Error handling and logging strategy |
| [docs/orchestrator-auto/PLAN_queue_feature.md](../docs/orchestrator-auto/PLAN_queue_feature.md) | Queue mode feature plan |

---

## Backend System Templates

Reusable documentation templates for backend projects. Copy and fill in for your specific codebase.

| File | What It Covers |
|------|---------------|
| [backend-system/README.md](../backend-system/README.md) | Overview and directory structure |
| [backend-system/BACKEND_MAP.md](../backend-system/BACKEND_MAP.md) | Domain-to-file navigation map |
| [backend-system/API_PATTERNS.md](../backend-system/API_PATTERNS.md) | Response formats, pagination, envelope patterns |
| [backend-system/AUTH_PATTERNS.md](../backend-system/AUTH_PATTERNS.md) | JWT claims, RBAC, permission patterns |
| [backend-system/DATABASE_PATTERNS.md](../backend-system/DATABASE_PATTERNS.md) | Models, migrations, naming conventions |
| [backend-system/SERVICE_PATTERNS.md](../backend-system/SERVICE_PATTERNS.md) | Business logic, dependency injection |
| [backend-system/ERROR_CODES.md](../backend-system/ERROR_CODES.md) | Error handling conventions |
| [backend-system/ENDPOINT_AUDIT.md](../backend-system/ENDPOINT_AUDIT.md) | Endpoint inventory and audit |
| [backend-system/VALIDATION_PATTERNS.md](../backend-system/VALIDATION_PATTERNS.md) | Input validation patterns |

> Blank templates live in `backend-system/template/`.

---

## Design System Templates

Reusable documentation templates for frontend/UI projects.

| File | What It Covers |
|------|---------------|
| [design-system/STYLE_GUIDE.md](../design-system/STYLE_GUIDE.md) | Typography, spacing, layout conventions |
| [design-system/COLOR_TOKENS.md](../design-system/COLOR_TOKENS.md) | Color palette and design tokens |
| [design-system/COMPONENT_PATTERNS.md](../design-system/COMPONENT_PATTERNS.md) | Reusable UI component patterns |
| [design-system/PAGE_AUDIT.md](../design-system/PAGE_AUDIT.md) | Page inventory and audit |
| [design-system/SYSTEM_UI_GLOSSARY.md](../design-system/SYSTEM_UI_GLOSSARY.md) | UI component naming and terminology |

> Blank templates live in `design-system/template/`.

---

## Claude Code Configuration

Files for configuring Claude Code IDE integration. Install by copying `claude/` to `~/.claude/`.

| File | What It Covers |
|------|---------------|
| [claude/README.md](../claude/README.md) | Setup instructions and directory structure |
| [claude/GLOBAL_GIT_RULES.md](../claude/GLOBAL_GIT_RULES.md) | Git commit instructions loaded into all sessions |
| [claude/agents/backend-architect.md](../claude/agents/backend-architect.md) | Custom agent definition for backend architecture tasks |
| [claude/agents/orchestrator-expert.md](../claude/agents/orchestrator-expert.md) | Custom agent definition for orchestrator expertise |

---

## Quick Decision Tree

```
What do you need?
|
+-- Understanding the project?
|   --> README.md, then CLAUDE.md
|
+-- Working on orchestrator-auto code?
|   --> orchestrator-auto/AGENTS.md (rules)
|   --> orchestrator-auto/docs/ARCHITECTURE.md (internals)
|
+-- Looking up CLI usage?
|   --> orchestrator-auto/docs/CLI_REFERENCE.md
|
+-- Debugging an issue?
|   --> orchestrator-auto/docs/TROUBLESHOOTING.md
|
+-- Choosing a workflow?
|   --> Workflows section above (default: CLAUDE_orchestrator.md)
|
+-- Understanding a feature?
|   --> Feature Documentation section above
|
+-- Reviewing a design proposal?
|   --> Proposals section above
|
+-- Setting up backend docs for a project?
|   --> backend-system/README.md
|
+-- Setting up frontend docs for a project?
|   --> design-system/ templates
```
