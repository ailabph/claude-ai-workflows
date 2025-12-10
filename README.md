# Claude AI Workflows

Workflow frameworks and tools for orchestrating AI agents (Claude) to execute complex software engineering tasks with human oversight.

## Overview

This repository provides a **milestone-based task execution framework** that enables:

- **Gated approval workflows** - Human review at each checkpoint before proceeding
- **Two-agent architecture** - Expensive model (Opus) for planning, cost-effective model (Sonnet/Haiku) for execution
- **Visual QA integration** - Figma-to-browser comparison for UI implementation
- **Structured progress reporting** - Standardized format for tracking deliverables

## Frameworks

### Core Orchestrator (`CLAUDE_orchestrator.md`)

The main framework for breaking complex tasks into 3-5 discrete milestones with clear deliverables.

**Key concepts:**
- Planner creates implementation plan with milestones
- Executor implements ONE milestone at a time
- Progress report generated after each milestone
- Human approves/rejects before next milestone begins

### Figma Visual QA (`CLAUDE_orchestrator_figma_visual_qa.md`)

Specialized workflow for implementing UI components from Figma designs with automated visual comparison.

**Capabilities:**
- Orchestrator fetches Figma specs via MCP
- Executor takes browser screenshots with Playwright
- Side-by-side visual comparison at checkpoints
- Pixel-perfect implementation validation

### Frontend Refactor Workflow (`CLAUDE_frontend_refactor_workflow.md`)

Iterative agent-human workflow for refactoring or building frontend UI components.

**Key concepts:**
- Single agent collaborating directly with human
- `CLAUDE_frontend_context.md` maintains codebase understanding across sessions
- Screenshot-driven feedback loop for visual validation
- Adaptable to React, Vue, Svelte, or any CSS framework (Tailwind, CSS Modules, Styled Components)

**Flow:**
1. Human provides page/screenshot starting point
2. Agent inspects codebase (or loads existing context file)
3. Agent implements task, reports changes
4. Human reviews via screenshot, provides feedback
5. Iterate until done, then update context file

### Visual QA Workflow (`CLAUDE_visual_qa_workflow.md`)

Autonomous visual QA workflow using Browser MCP for screenshots. Agent self-corrects until implementation matches design.

**Key concepts:**
- Agent takes screenshots autonomously via Browser MCP
- Self-correction loop (max 3 attempts before escalation)
- Human reviews at milestone checkpoints only
- Supports multi-screen batch processing

**Flow:**
1. Human provides design reference + route
2. Agent implements, screenshots, compares
3. Agent self-corrects if mismatch (autonomous loop)
4. Human approves at checkpoint
5. Repeat for next screen

**Requirements:** Browser MCP (Playwright or Puppeteer)

## Tools

### Figma Screenshot Fetcher

Python script for fetching design screenshots from Figma API.

```bash
# Setup
pip install requests
export FIGMA_ACCESS_TOKEN="your-token-here"

# Fetch by URL
python CLAUDE_fetch_figma_screenshot.py \
  --url "https://figma.com/design/FILE_KEY/name?node-id=1-9366" \
  --output screenshots/figma/component.png

# Fetch by file-key and node-id
python CLAUDE_fetch_figma_screenshot.py \
  --file-key FILE_KEY \
  --node-id 1-9366 \
  --output screenshots/figma/component.png \
  --scale 2.0
```

## Quick Start

### 1. Plan a Task

Create an implementation plan with milestones:

```markdown
## Milestones

### M1: [Foundation]
- Task 1
- Task 2
⛔ STOP - Generate progress report, wait for approval

### M2: [Core Implementation]
- Task 3
- Task 4
⛔ STOP - Generate progress report, wait for approval
```

### 2. Execute with Approval Gates

```
Planner → Creates plan → Executor
                              ↓
                         Milestone 1
                              ↓
                      Progress Report
                              ↓
Planner ← Reviews ← Executor STOPS
    ↓
Approve/Reject
    ↓
    → Continue to Milestone 2 (or fix issues)
```

### 3. Review Commands

| Action | Command |
|--------|---------|
| Approve | `Milestone N approved. Proceed to Milestone N+1.` |
| Changes needed | `Milestone N needs changes: [issues]. Fix and regenerate report.` |
| Abort | `ABORT: [Reason]. Do not proceed.` |

## File Structure

```
├── CLAUDE_orchestrator.md                  # Core milestone framework
├── CLAUDE_orchestrator_ref.md              # Quick reference & UI patterns
├── CLAUDE_orchestrator_figma_visual_qa.md  # Figma visual QA workflow
├── CLAUDE_frontend_refactor_workflow.md    # Frontend refactor/build workflow (manual)
├── CLAUDE_frontend_refactor_workflow_ref.md # Frontend workflow human reference
├── CLAUDE_visual_qa_workflow.md            # Autonomous visual QA workflow (Browser MCP)
├── CLAUDE_visual_qa_workflow_ref.md        # Visual QA human reference & MCP setup
├── CLAUDE_visual_qa_workflow_setup.py      # Visual QA setup script (macOS)
├── CLAUDE_figma_screenshots_README.md      # Figma fetcher documentation
└── CLAUDE_fetch_figma_screenshot.py        # Figma screenshot tool
```

## Requirements

- Python 3.8+ (for Figma screenshot fetcher)
- `requests` library
- Figma Personal Access Token (for Figma workflows)
- Playwright (for browser screenshots in Figma Visual QA workflow)
- Browser MCP - Playwright or Puppeteer (for autonomous Visual QA workflow)

## License

MIT
