# Claude AI Workflows

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-green.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-1.9.0-orange.svg)](orchestrator-auto/)

Milestone-based orchestration for AI agents with human oversight. Describe what you want built, review a plan, approve each milestone.

## What Is This?

You describe a feature. A **Planner** (Claude Opus) breaks it into milestones. An **Executor** (Claude Sonnet/Haiku) implements them one at a time. You review and approve between each milestone. Repeat until done.

```mermaid
sequenceDiagram
    participant You
    participant Planner as Planner (Opus)
    participant Executor as Executor (Sonnet/Haiku)

    You->>Planner: "Add user auth"
    Planner-->>You: Plan: 4 milestones
    You->>Planner: Approve plan
    Planner->>Executor: Execute M1
    Executor-->>Planner: Progress report (M1: Schema + models)
    Planner-->>You: Review M1
    You->>Planner: Approve M1
    Planner->>Executor: Execute M2
    Executor-->>Planner: Progress report (M2: Registration + tests)
    Note over You,Executor: ...continues for each milestone...
```

## Features

| | |
|---|---|
| **Gated milestones** | Human approval at every checkpoint — nothing proceeds without you |
| **Two-agent cost model** | Opus plans, Sonnet/Haiku executes — smart where it counts, cheap where it doesn't |
| **Rich TUI** | Live dashboard with token tracking, cost, elapsed time, and milestone progress |
| **Watch mode** | Monitor multiple files with per-file status (pending/ongoing/done/failed) |
| **Telegram integration** | Get notified on milestone completion, answer blockers from your phone |
| **Auto-commit** | Automatically commits on workflow completion with AI-generated messages |
| **Queue mode** | Chain multiple workflows to run sequentially |
| **Sub-agents** | Specialized Explore and Bash sub-agents for deep codebase research |
| **Planner chat** | Dedicated TUI chat window for freeform conversation with the Planner agent |

## Quick Start

```bash
# Install
git clone https://github.com/ailabph/claude-ai-workflows.git
cd claude-ai-workflows/orchestrator-auto
pip install -e .

# Set your API key (choose one)
export ANTHROPIC_API_KEY="your-key"           # Pay-as-you-go
export CLAUDE_CODE_OAUTH_TOKEN="your-token"   # Claude Pro/Max subscription

# Run your first workflow
orchestrator start -f "Add user registration with email validation and password hashing"
```

## How It Works

**1. Describe your task**
```bash
orchestrator start -f "Add pagination to /products endpoint, 50 items per page with next/prev links"
```

**2. Review the plan** — the Planner creates 3-5 milestones:
```
M1: Database query with LIMIT/OFFSET + cursor model
M2: Pagination serializer + response envelope
M3: Endpoint integration + query params + tests
M4: Next/prev link generation + edge cases
```

**3. Approve each milestone** — after each one completes, you decide:

| Response | Effect |
|----------|--------|
| `Approve` | Executor proceeds to next milestone |
| `Request changes` | Executor fixes issues and regenerates report |
| `ABORT` | Workflow stops entirely |

## Workflows

| Task | Workflow | Description |
|------|----------|-------------|
| Any language/framework | [Core Orchestrator](workflows/CLAUDE_orchestrator.md) | General-purpose milestone framework |
| Django REST APIs | [Django Engineer](workflows/CLAUDE_django_engineer_workflow.md) | Models, serializers, views, pytest, migrations |
| Figma-to-code | [Figma Visual QA](workflows/CLAUDE_orchestrator_figma_visual_qa.md) | Pixel-level comparison between Figma and browser |
| UI iteration | [Frontend Refactor](workflows/CLAUDE_frontend_refactor_v2.md) | Screenshot-driven feedback loop |
| Batch visual testing | [Visual QA](workflows/CLAUDE_visual_qa_workflow.md) | Autonomous screenshot validation with self-correction |
| Solana/Web3 | [Solana Orchestrator](workflows/CLAUDE_orch_solana.md) | Security checklist + contract validation |

**Not sure?** Start with **Core Orchestrator** — it works for everything.

## CLI Reference

```bash
orchestrator start -f "Feature description"              # New workflow
orchestrator start -f "Feature" -pm sonnet -em haiku     # Custom models
orchestrator start -f "Feature" --auto-commit             # Auto-commit on completion
orchestrator start -f "Feature" --telegram                # With Telegram notifications
orchestrator start --queue plan1.md plan2.md              # Queue mode
orchestrator resume <session-id>                          # Resume interrupted work
orchestrator list                                         # List sessions
orchestrator status <session-id>                          # Session details
orchestrator chat                                         # Direct chat (no orchestration)
orchestrator check                                        # Health check (auth, deps, API)
orchestrator export <session-id> -o report.md             # Export to markdown
```

See [orchestrator-auto/README.md](orchestrator-auto/README.md) for full CLI documentation.

## Architecture

```mermaid
graph TD
    CLI[CLI · click] --> Engine[Engine · state machine + orchestration loop]
    Engine --> Planner[PlannerAgent · Opus<br/>creates milestones, reviews reports]
    Engine --> Executor[ExecutorAgent · Sonnet<br/>implements one milestone at a time]
    Executor --> Explore[ExploreSubAgent<br/>codebase research]
    Executor --> Bash[BashSubAgent<br/>command execution]
    Engine --> DB[SQLite DB<br/>session persistence]
    Engine --> TUI[TUI · Textual<br/>live dashboard + watch mode]
    Engine --> Telegram[Telegram<br/>notifications + blocker replies]
```

Key modules in [`orchestrator-auto/`](orchestrator-auto/):

| Module | Purpose |
|--------|---------|
| `engine.py` | Core orchestration loop and state machine |
| `agents.py` | Claude Agent SDK wrappers (Planner, Executor, sub-agents) |
| `cli.py` | Click CLI interface |
| `db.py` | SQLite persistence |
| `parser.py` | Response tag parsing (`[PLAN_READY]`, `[BLOCKED]`, etc.) |
| `prompts.py` | System prompts for planner/executor |
| `telegram.py` | Telegram notifications and blocker replies |
| `git.py` | Auto-commit with AI-generated messages |
| `tui/` | Textual-based dashboard widgets |

## Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/kagi-api.py` | Kagi API CLI (search, summarize, enrich, fastgpt) | `python scripts/kagi-api.py search "query"` |

See `README_KAGI.md` for full Kagi API documentation and response formats.

## Requirements

- **Python 3.10+**
- **Anthropic API key** or **Claude Pro/Max subscription** (OAuth token)

Optional:
- [Telegram Bot](https://core.telegram.org/bots) for mobile notifications
- [Playwright](https://playwright.dev/) for visual QA workflows
- [Figma Access Token](https://www.figma.com/developers/api) for Figma workflows
- [Kagi API key](https://kagi.com/settings?p=api) for Kagi search/summarize (`kagiapi` package)

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community standards.

## License

[MIT](LICENSE)
