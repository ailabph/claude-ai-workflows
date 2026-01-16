# Plan: `orchestrator audit` Command

## Problem Statement

User has many plan files and wants to:
1. Check if each plan is already implemented in the codebase
2. Archive implemented plans
3. Process efficiently without hitting token limits

Current orchestrator-auto breaks because it accumulates context across milestones within a single session.

## Solution: `orchestrator audit` Command

A new command that processes plan files **independently** with **fresh context per file**.

```bash
orchestrator audit ./plans/ --archive-dir ./plans/archive/
orchestrator audit plan1.md plan2.md plan3.md --dry-run
orchestrator audit ./plans/ --auto-archive --model haiku
```

## Design

### Command Signature

```bash
orchestrator audit <paths...> [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `paths` | required | Directory or file paths to audit |
| `--archive-dir` | `./archive/` | Where to move implemented plans |
| `--dry-run` | false | Report status without moving files |
| `--auto-archive` | false | Auto-archive IMPLEMENTED plans (no confirmation) |
| `--model` | haiku | Model for research (haiku recommended for cost) |
| `--verbose` | false | Show research details |

### Per-File Workflow

```
For each plan file:
    1. Create FRESH agent (no shared context)
    2. Agent reads plan content
    3. Agent searches codebase for implementation evidence
    4. Agent returns verdict:
       - IMPLEMENTED: All major features exist
       - PARTIAL: Some features exist
       - NOT_IMPLEMENTED: No evidence found
    5. Based on verdict + mode:
       - dry-run: Just report
       - auto-archive: Move IMPLEMENTED to archive
       - interactive: Ask user per file
    6. Agent context discarded (fresh for next file)
```

### Output Format

```
Auditing 15 plan files...

[1/15] PLAN_user_auth.md
       Status: IMPLEMENTED
       Evidence: src/auth/jwt.py, src/middleware/auth.py, tests/test_auth.py
       → Moved to ./plans/archive/

[2/15] PLAN_email_notifications.md
       Status: PARTIAL
       Evidence: src/notifications/email.py exists, but no queue worker
       → Skipped (not fully implemented)

[3/15] PLAN_password_reset.md
       Status: NOT_IMPLEMENTED
       Evidence: No password reset endpoints or templates found
       → Skipped

...

Summary:
  IMPLEMENTED:     8 files (archived)
  PARTIAL:         4 files (skipped)
  NOT_IMPLEMENTED: 3 files (skipped)
```

### Agent Prompt

```
You are auditing whether a plan has been implemented in the codebase.

PLAN CONTENT:
{plan_content}

INSTRUCTIONS:
1. Read the plan carefully to understand what should be implemented
2. Search the codebase for evidence of implementation:
   - Look for relevant files, classes, functions
   - Check for tests
   - Check for database migrations if applicable
3. Return your verdict in this exact format:

[AUDIT_RESULT]
Status: IMPLEMENTED | PARTIAL | NOT_IMPLEMENTED
Evidence:
- file1.py: description of what exists
- file2.py: description of what exists
Reasoning: Brief explanation of your conclusion
[/AUDIT_RESULT]

Be conservative: only mark IMPLEMENTED if you find strong evidence that
the major features described in the plan exist and work.
```

### Key Differences from Main Workflow

| Aspect | `orchestrator start` | `orchestrator audit` |
|--------|---------------------|---------------------|
| Context | Accumulates across milestones | Fresh per file |
| Agents | Planner + Executor | Single research agent |
| Goal | Implement features | Check implementation |
| Output | Code changes | Status report |
| Session | Persisted in DB | Ephemeral (no DB) |

## Implementation

### New Files

```
orchestrator_auto/
├── audit.py          # Core audit logic
└── cli.py            # Add audit command
```

### `audit.py` Structure

```python
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional
import shutil

class AuditStatus(Enum):
    IMPLEMENTED = "IMPLEMENTED"
    PARTIAL = "PARTIAL"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    ERROR = "ERROR"

@dataclass
class AuditResult:
    file_path: Path
    status: AuditStatus
    evidence: List[str]
    reasoning: str
    error: Optional[str] = None

class PlanAuditor:
    def __init__(self, model: str = "haiku", verbose: bool = False):
        self.model = model
        self.verbose = verbose

    def audit_file(self, plan_path: Path) -> AuditResult:
        """Audit a single plan file with fresh agent context."""
        # 1. Read plan content
        # 2. Create fresh agent
        # 3. Run audit prompt
        # 4. Parse result
        # 5. Return AuditResult
        pass

    def audit_directory(self, dir_path: Path, ...) -> List[AuditResult]:
        """Audit all .md files in directory."""
        pass

def parse_audit_response(response: str) -> tuple[AuditStatus, List[str], str]:
    """Parse [AUDIT_RESULT] tags from agent response."""
    pass
```

### CLI Addition

```python
@cli.command()
@click.argument('paths', nargs=-1, required=True, type=click.Path(exists=True))
@click.option('--archive-dir', default='./archive/', help='Archive directory')
@click.option('--dry-run', is_flag=True, help='Report without moving files')
@click.option('--auto-archive', is_flag=True, help='Auto-archive implemented plans')
@click.option('-m', '--model', default='haiku', help='Model for research')
@click.option('-v', '--verbose', is_flag=True, help='Show research details')
def audit(paths, archive_dir, dry_run, auto_archive, model, verbose):
    """Audit plan files to check if they're implemented."""
    pass
```

## Milestones

### Milestone 1: Core Audit Logic
- Create `audit.py` with `PlanAuditor` class
- Implement `audit_file()` with fresh agent per file
- Implement response parsing for `[AUDIT_RESULT]` tags
- Unit tests for parsing

### Milestone 2: CLI Integration
- Add `audit` command to `cli.py`
- Handle directory vs file inputs
- Implement dry-run mode
- Implement archive logic

### Milestone 3: Interactive Mode
- Add confirmation prompts for non-auto mode
- Add summary output
- Add `--verbose` output with full evidence

### Milestone 4: Polish
- Error handling (file not found, agent errors)
- Progress indicator
- Graceful interruption (Ctrl+C)

## Testing

```bash
# Create test plans
mkdir -p test_plans
echo "# Feature: User Authentication\n- JWT tokens\n- Login endpoint" > test_plans/PLAN_auth.md
echo "# Feature: Time Travel\n- Go back in time" > test_plans/PLAN_impossible.md

# Dry run
orchestrator audit test_plans/ --dry-run

# Auto archive
orchestrator audit test_plans/ --auto-archive --archive-dir test_plans/done/

# Verbose
orchestrator audit test_plans/PLAN_auth.md --verbose
```

## Cost Estimate

Using Haiku for research:
- ~1000 tokens per plan file (plan content + search results)
- ~500 tokens response
- Cost: ~$0.0004 per file
- 100 files = ~$0.04

Very cheap compared to full orchestrator workflow.
