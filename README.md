# Claude AI Workflows

Workflow frameworks and tools for orchestrating AI agents (Claude) to execute complex software engineering tasks with human oversight.

## Overview

This repository provides a **milestone-based task execution framework** that enables:

- **Gated approval workflows** - Human review at each checkpoint before proceeding
- **Two-agent architecture** - Expensive model (Opus) for planning, cost-effective model (Sonnet/Haiku) for execution
- **Visual QA integration** - Figma-to-browser comparison for UI implementation
- **Structured progress reporting** - Standardized format for tracking deliverables

### Why Use This?

Instead of:
- Telling Claude to "build X" and hoping it works → You get partial implementations, bugs, lost context
- Manual back-and-forth feedback → Repetitive, slow, hard to track progress

You get:
- **Explicit milestones** → Clear checkpoints where you review before proceeding
- **Cost-effective** → Opus (expensive) plans, Sonnet/Haiku (cheap) executes
- **Reliable** → Executor stops after each milestone, waits for your approval
- **Auditable** → Progress reports show exactly what was built, why changes were made

## Frameworks

### Core Orchestrator (`CLAUDE_orchestrator.md`)

The main framework for breaking complex tasks into 3-5 discrete milestones with clear deliverables. **Use this when:**
- Building new features (backend, frontend, APIs)
- Refactoring existing code
- Fixing complex bugs

**Key concepts:**
- **Planner** reads framework docs → creates implementation plan with 3-5 milestones
- **Executor** implements ONE milestone at a time → generates progress report
- **You review** the report → Approve/reject before next milestone
- **Loop repeats** until all milestones approved

### Figma Visual QA (`CLAUDE_orchestrator_figma_visual_qa.md`)

Specialized workflow for implementing UI components from Figma designs with automated visual comparison. **Use this when:**
- Implementing from Figma mockups
- Need pixel-perfect UI matching
- Have multiple design screens to implement

**Capabilities:**
- **Automatic fetching** → Fetches Figma specs via MCP (no manual screenshots)
- **Executable implementation** → Executor builds components + styles
- **Automated comparison** → Takes browser screenshots, compares to Figma
- **Visual validation** → You review side-by-side comparison at checkpoints

### Frontend Refactor Workflow (`CLAUDE_frontend_refactor_workflow.md`)

Iterative agent-human workflow for refactoring or building frontend UI components. **Use this when:**
- Iterating on UI (back-and-forth refinements)
- Building new components piece-by-piece
- Need tight feedback loop with screenshot validation

**Key concepts:**
- **Single agent** collaborating directly with you (no planner/executor split)
- **Context persistence** → `CLAUDE_frontend_context.md` maintains codebase understanding across sessions
- **Screenshot-driven** feedback loop for visual validation
- **Framework agnostic** → Works with React, Vue, Svelte, Tailwind, CSS Modules, etc.

**Flow:**
1. Human provides page/screenshot or starting point
2. Agent inspects codebase (or loads context file)
3. Agent implements task, reports changes + screenshots
4. Human reviews screenshot, provides feedback
5. Repeat until satisfied, then update context file

### Visual QA Workflow (`CLAUDE_visual_qa_workflow.md`)

Autonomous visual QA workflow using Browser MCP for screenshots. Agent self-corrects until implementation matches design. **Use this when:**
- Testing multiple screens autonomously
- Don't want to review after each screenshot
- Need batch processing of multiple pages

**Key concepts:**
- **Autonomous validation** → Agent takes screenshots, compares to design, self-corrects
- **Self-correction loop** → Max 3 attempts before escalating to you
- **Human-light** → You only review at major checkpoints, not every attempt
- **Batch processing** → Handles multiple screens in sequence

**Flow:**
1. Human provides design reference + route
2. Agent implements → Takes screenshot → Compares to design
3. Agent self-corrects if mismatch (loop up to 3 times)
4. Human reviews and approves at checkpoint
5. Repeat for next screen

**Requirements:** Browser MCP (Playwright or Puppeteer)

### Django Engineer Workflow (`CLAUDE_django_engineer_workflow.md`)

Backend development workflow for Django/DRF projects with strict conventions. **Use this when:**
- Building Django REST API endpoints
- Need proper serializers, views, tests, and migrations
- Want automated formatting and schema validation

**Key concepts:**
- **Environment management** → Auto-detects/creates conda environment
- **Test-first** → pytest with mocks only (never database in tests)
- **Documented APIs** → OpenAPI/Swagger on all endpoints
- **Strict formatting** → Black code formatter + type hints

**Flow:**
1. Agent activates/creates conda environment
2. Agent implements (models, serializer, view, URL, tests)
3. Agent validates (black, pytest, schema validation)
4. Agent reports endpoint table with status

**Conventions:**
- **Serializers** → All fields have `help_text` for OpenAPI docs
- **Views** → All have `@extend_schema` decorators
- **Tests** → Use `@patch` mocks, never touch database
- **Commits** → `api(endpoint): description` format

## Choosing Your Workflow

| I want to... | Use this workflow |
|-------------|-------------------|
| Build a Django REST API with tests | Django Engineer |
| Implement a Figma design pixel-perfectly | Figma Visual QA |
| Build features in any language/framework | Core Orchestrator |
| Refactor/iterate on UI with feedback loop | Frontend Refactor |
| Run autonomous visual tests on multiple screens | Visual QA |
| Develop Web3/Solana code with security checks | Django Engineer (see CLAUDE_orch_solana.md) |

**Still unsure?** Start with **Core Orchestrator**—it's the most flexible and works for anything.

## Key Concepts

| Term | Meaning |
|------|---------|
| **Milestone** | A logical chunk of work (2-5 tasks) that produces a runnable deliverable. You review and approve each milestone before proceeding. |
| **Planner** | Claude Opus—reads your feature description and docs, creates 3-5 milestones |
| **Executor** | Claude Sonnet/Haiku—implements one milestone at a time, generates progress report, waits for approval |
| **Progress Report** | Detailed summary of what was built in a milestone, what tests were added, any design decisions made |
| **Approval Gate** | You review each progress report and decide: approve (proceed), request changes (fix), or abort (stop) |
| **Session** | One workflow execution. Track it with `orchestrator list`, resume with `orchestrator resume <id>` |

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

## Getting Started

### Prerequisites

- Python 3.8+
- `requests` library (for Figma screenshots)
- Anthropic API key or Claude Pro/Max subscription

### Installation

```bash
# Clone repo
git clone https://github.com/ailabph/claude-ai-workflows.git
cd claude-ai-workflows/orchestrator-auto

# Setup environment
conda env create -f environment.yml
conda activate orchestrator-auto
pip install -e .

# Set your API key
export ANTHROPIC_API_KEY="your-key-here"
# OR use Claude Pro:
export CLAUDE_CODE_OAUTH_TOKEN="your-token"
```

### First Workflow

```bash
orchestrator start -f "Add user authentication with email and password"
```

The planner will create milestones, executor will build them one at a time, and you'll review/approve each milestone.

## Quick Start

### 1. Start a Workflow

Describe what you want to build:

```bash
orchestrator start -f "Add email notifications to the notification system"
```

The planner reads framework docs and creates 3-5 milestones for your task.

**Good descriptions:**
- ✅ "Add pagination to /api/products endpoint (50 items per page)"
- ✅ "Fix login endpoint returning 500 errors on invalid credentials"
- ✅ "Refactor User model to track last_login timestamp"

**Bad descriptions:**
- ❌ "Build a notification system" (too vague)
- ❌ "Fix bugs" (unclear what to fix)
- ❌ "Improve performance" (how to measure improvement?)

### 2. Review Plan & Milestones

Planner creates a plan. Review it:

```
✅ Milestone 1: Create EmailTemplate model + migrations
✅ Milestone 2: Implement email service + SendGrid integration
✅ Milestone 3: Add notification endpoints + tests
✅ Milestone 4: Add email scheduling + retry logic
```

Approve, request changes, or provide clarification.

### 3. Review Milestones

For each milestone, the executor reports progress. You then:

- ✅ **Approve**: Executor proceeds to next milestone
- ❌ **Request changes**: Executor fixes and regenerates report
- 🛑 **Abort**: Stop workflow entirely

Example responses:

| Scenario | Your Response |
|----------|---------------|
| Looks good | `✅ Milestone 1 approved. Proceed to Milestone 2.` |
| Has issues | `❌ Milestone 1 needs changes: Email validation is case-sensitive (should be case-insensitive). Fix and regenerate.` |
| Stop completely | `🛑 ABORT: The approach is wrong. Let's rethink this.` |

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
├── CLAUDE_django_engineer_workflow.md      # Django backend development workflow
├── CLAUDE_django_engineer_workflow_ref.md  # Django workflow human reference
├── CLAUDE_figma_screenshots_README.md      # Figma fetcher documentation
└── CLAUDE_fetch_figma_screenshot.py        # Figma screenshot tool
```

## Requirements

**Core:**
- Python 3.8+
- Anthropic API key or Claude Pro/Max subscription

**Optional (by workflow):**
- `requests` library (for Figma screenshot fetcher)
- Figma Personal Access Token (for Figma Visual QA workflow)
- Playwright or Puppeteer (for visual QA workflows)
- Browser MCP (for autonomous Visual QA workflow)

## License

MIT
