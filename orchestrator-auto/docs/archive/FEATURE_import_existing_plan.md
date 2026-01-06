# Feature: Import Existing Plan

## Status: Draft / TODO

## Overview

Allow users to start a workflow session with a pre-existing milestone plan file, skipping the discovery and planning phases. This enables:

- **Recovery workflows** - Restart failed sessions with the same plan
- **Reusable templates** - Use proven plans across similar features
- **Human-crafted plans** - Use manually written or edited plans
- **Faster execution** - Skip discovery/planning, go straight to implementation

## Current Behavior

```bash
orchestrator start -f "Add user authentication"
```

1. Creates session in `discovery` phase
2. Planner engages in discovery conversation
3. User types `/ready`
4. Planner creates plan document
5. Transitions to `execution` phase
6. Executor implements milestones

## Proposed Behavior

```bash
orchestrator start -f "Add user authentication" --plan docs/auth/DOC_auth_plan.md
```

1. Creates session directly in `execution` phase
2. Validates plan file exists and parses milestone count
3. Skips discovery and planning entirely
4. Executor starts implementing Milestone 1 immediately

## Implementation Plan

### 1. Update CLI with `--plan` flag

**File:** `orchestrator_auto/cli.py`

```python
@click.command()
@click.option("-f", "--feature", required=True, help="Feature description")
@click.option("-d", "--db-path", default=None, help="Database path")
@click.option(
    "-p", "--plan",
    default=None,
    type=click.Path(exists=True),
    help="Path to existing plan file (skips discovery/planning)"
)
def start(feature: str, db_path: Optional[str], plan: Optional[str]):
    """Start a new workflow session."""
    try:
        orch = Orchestrator(
            feature_description=feature,
            db_path=db_path,
            plan_path=plan,  # New parameter
            on_output=click.echo,
        )
        orch.run()
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
```

### 2. Add plan parser utility

**File:** `orchestrator_auto/parser.py`

Add function to extract milestone count from plan file:

```python
def parse_plan_file(plan_path: str) -> Dict[str, Any]:
    """
    Parse a plan file and extract metadata.

    Args:
        plan_path: Path to plan markdown file

    Returns:
        Dict with:
        - milestones: int - number of milestones
        - milestone_names: List[str] - milestone names
        - valid: bool - whether plan is valid
        - error: Optional[str] - error message if invalid
    """
    from pathlib import Path

    path = Path(plan_path)
    if not path.exists():
        return {"valid": False, "error": f"Plan file not found: {plan_path}"}

    content = path.read_text()

    # Extract milestones using regex
    # Pattern: ### Milestone N: Name
    milestone_pattern = r'###\s*Milestone\s*(\d+):\s*(.+)'
    matches = re.findall(milestone_pattern, content, re.IGNORECASE)

    if not matches:
        return {"valid": False, "error": "No milestones found in plan file"}

    milestone_names = [name.strip() for _, name in matches]

    return {
        "valid": True,
        "milestones": len(matches),
        "milestone_names": milestone_names,
        "error": None
    }
```

### 3. Update Orchestrator constructor

**File:** `orchestrator_auto/engine.py`

```python
class Orchestrator:
    def __init__(
        self,
        feature_description: Optional[str] = None,
        session_id: Optional[str] = None,
        db_path: Optional[str] = None,
        plan_path: Optional[str] = None,  # New parameter
        on_output: Optional[Callable[[str], None]] = None,
    ):
        # ... existing init code ...

        if session_id:
            # Resume existing session (unchanged)
            self._resume_session(session_id)
        elif feature_description:
            if plan_path:
                # New: Start with existing plan
                self._start_with_plan(feature_description, plan_path)
            else:
                # Existing: Start fresh with discovery
                self._create_new_session(feature_description)
        else:
            raise ValueError("Must provide feature_description or session_id")
```

### 4. Implement `_start_with_plan` method

**File:** `orchestrator_auto/engine.py`

```python
def _start_with_plan(self, feature_description: str, plan_path: str) -> None:
    """
    Start a new session with an existing plan file.

    Skips discovery and planning phases, goes directly to execution.

    Args:
        feature_description: Feature being implemented
        plan_path: Path to existing plan file
    """
    from .parser import parse_plan_file

    # Validate plan file
    plan_info = parse_plan_file(plan_path)
    if not plan_info["valid"]:
        raise ValueError(f"Invalid plan file: {plan_info['error']}")

    self._output(f"\n→ Using existing plan: {plan_path}")
    self._output(f"  Milestones: {plan_info['milestones']}")
    self._output(f"  Names: {', '.join(plan_info['milestone_names'])}\n")

    # Create session directly in execution phase
    self.session_id = db.create_session(
        feature_description=feature_description,
        db_path=self.db_path
    )

    # Update to execution phase with plan info
    db.update_session(
        self.session_id,
        {
            "phase": "execution",
            "plan_path": plan_path,
            "current_milestone": 1,
            "total_milestones": plan_info["milestones"],
        },
        self.db_path
    )

    # Load state
    self.state = self.state_machine.get_state(self.session_id)

    self._output(f"✓ Session created: {self.session_id[:8]}\n")
    self._output(f"  Phase: EXECUTION (skipped discovery/planning)\n")
```

### 5. Update run() to handle execution-start

**File:** `orchestrator_auto/engine.py`

The existing `run()` method should already handle this since it checks `self.state.phase` and routes accordingly. Verify it works:

```python
def run(self) -> None:
    """Run the orchestrator workflow."""
    try:
        self._show_status()

        while self.state.status == "active":
            if self.state.phase == "discovery":
                self._run_discovery()
            elif self.state.phase == "planning":
                self._run_planning()
            elif self.state.phase == "execution":
                self._run_execution_loop()  # Will start here with --plan
            elif self.state.phase == "completed":
                break
            elif self.state.phase == "paused":
                break

    except Exception as e:
        # ... error handling ...
```

## Usage Examples

### Start with existing plan

```bash
# Use a plan from a previous session
orchestrator start -f "Add JWT auth" --plan docs/auth/DOC_auth_plan.md

# Use a template plan
orchestrator start -f "Add user profile" --plan templates/user_feature_plan.md
```

### Recovery workflow

```bash
# 1. Session fails mid-execution
$ orchestrator status abc123
Phase: FAILED at Milestone 2

# 2. Export the plan (or find it in docs/)
$ cat docs/abc123/DOC_abc123_plan.md

# 3. Start new session with same plan
$ orchestrator start -f "Same feature" --plan docs/abc123/DOC_abc123_plan.md
```

### Reusable templates

Create template plans for common patterns:

```
templates/
├── api_endpoint_plan.md      # Standard CRUD API
├── auth_feature_plan.md      # Authentication features
├── ui_component_plan.md      # React component pattern
└── migration_plan.md         # Database migration
```

## Plan File Format

Plans must follow this structure for parsing:

```markdown
# Implementation Plan: [Feature Name]

## Overview
[Description]

## Milestones

### Milestone 1: [Name]
**Deliverables:**
- [deliverable 1]
- [deliverable 2]

### Milestone 2: [Name]
**Deliverables:**
- [deliverable 1]

### Milestone 3: [Name]
**Deliverables:**
- [deliverable 1]
```

The parser extracts milestones via regex: `### Milestone N: Name`

## Complexity Estimate

- CLI changes: ~15 min
- Parser function: ~20 min
- Engine `_start_with_plan`: ~30 min
- Testing: ~30 min
- **Total: ~1.5-2 hours**

## Testing Plan

### Unit Tests

```python
# test_parser.py
def test_parse_plan_file_valid():
    """Test parsing valid plan file."""

def test_parse_plan_file_not_found():
    """Test parsing non-existent file."""

def test_parse_plan_file_no_milestones():
    """Test parsing file without milestones."""

# test_engine.py
def test_start_with_plan():
    """Test starting session with existing plan."""

def test_start_with_invalid_plan():
    """Test error handling for invalid plan."""

# test_cli.py
def test_start_with_plan_flag():
    """Test CLI --plan flag."""
```

### Integration Tests

```python
def test_full_workflow_with_imported_plan():
    """Test complete workflow using imported plan."""
```

## Edge Cases

1. **Plan file not found** - Clear error message
2. **Plan with 0 milestones** - Reject with error
3. **Plan with malformed milestone headers** - Reject with error
4. **Relative vs absolute paths** - Support both
5. **Plan file in different directory** - Should work with any valid path

## Future Enhancements

- [ ] `orchestrator validate-plan <path>` - Validate plan file without starting session
- [ ] `--start-milestone N` - Start at a specific milestone (for partial recovery)
- [ ] Plan file auto-detection from session ID
