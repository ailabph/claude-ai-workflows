# Feature: Model Selection CLI Options

## Status: Draft / TODO

## Overview

Add CLI flags to allow users to specify which Claude models to use for the Planner and Executor agents. This enables cost optimization (e.g., using Haiku for executor) and experimentation with different model combinations.

## Problem

Currently, agent models are hardcoded in `agents.py`:
- Planner: `claude-opus-4-6` (most capable, highest cost)
- Executor: `claude-sonnet-4-6` (balanced)

Users cannot:
1. Use cheaper models for simple tasks
2. Experiment with different model combinations
3. Override defaults without modifying code

## Proposed Solution

Add `--planner-model` and `--executor-model` CLI flags to the `start` command.

### Usage Examples

```bash
# Use defaults (Opus planner, Sonnet executor)
orchestrator start -f "My feature"

# Use Haiku for executor (cost savings)
orchestrator start -f "My feature" --executor-model claude-haiku-3-5-20241022

# Use Sonnet for both (balanced)
orchestrator start -f "My feature" \
  --planner-model claude-sonnet-4-6 \
  --executor-model claude-sonnet-4-6

# Use Opus for both (maximum capability)
orchestrator start -f "My feature" \
  --planner-model claude-opus-4-6 \
  --executor-model claude-opus-4-6
```

## Implementation Plan

### Phase 1: Create Config Module (`config.py`)

New module for configuration and model resolution:

```python
"""Configuration management for orchestrator-auto."""

from pathlib import Path
from typing import Optional, Dict, Any

# Model aliases mapping to full model IDs
MODEL_ALIASES = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-3-5-20241022",
}

# Default models
DEFAULT_PLANNER_MODEL = "claude-opus-4-6"
DEFAULT_EXECUTOR_MODEL = "claude-sonnet-4-6"

def get_config_path() -> Path:
    """Get path to config file."""
    return Path.home() / ".claude_orchestrator" / "config.yaml"

def load_config() -> Dict[str, Any]:
    """Load config from ~/.claude_orchestrator/config.yaml"""
    config_path = get_config_path()
    if config_path.exists():
        import yaml
        return yaml.safe_load(config_path.read_text()) or {}
    return {}

def resolve_model(model: Optional[str]) -> Optional[str]:
    """Resolve model alias to full model ID."""
    if model is None:
        return None
    return MODEL_ALIASES.get(model.lower(), model)

def get_planner_model(cli_model: Optional[str] = None) -> str:
    """Get planner model with priority: CLI > config > default."""
    if cli_model:
        return resolve_model(cli_model)

    config = load_config()
    config_model = config.get("models", {}).get("planner")
    if config_model:
        return resolve_model(config_model)

    return DEFAULT_PLANNER_MODEL

def get_executor_model(cli_model: Optional[str] = None) -> str:
    """Get executor model with priority: CLI > config > default."""
    if cli_model:
        return resolve_model(cli_model)

    config = load_config()
    config_model = config.get("models", {}).get("executor")
    if config_model:
        return resolve_model(config_model)

    return DEFAULT_EXECUTOR_MODEL
```

### Phase 2: Update CLI (`cli.py`)

Add options to the `start` command:

```python
@click.option(
    '--planner-model', '-pm',
    default=None,
    help='Model for planner agent (default: opus). Aliases: opus, sonnet, haiku'
)
@click.option(
    '--executor-model', '-em',
    default=None,
    help='Model for executor agent (default: sonnet). Aliases: opus, sonnet, haiku'
)
def start(feature, db_path, plan, show_activity, planner_model, executor_model):
    ...
```

### Phase 3: Update Orchestrator (`engine.py`)

1. Accept model parameters in `__init__`:
   ```python
   def __init__(
       self,
       feature_description: Optional[str] = None,
       session_id: Optional[str] = None,
       db_path: Optional[str] = None,
       plan_path: Optional[str] = None,
       on_output: Optional[Callable[[str], None]] = None,
       show_activity: bool = True,
       planner_model: Optional[str] = None,  # NEW
       executor_model: Optional[str] = None,  # NEW
   ):
   ```

2. Store model preferences and pass to agent creation:
   ```python
   self.planner_model = planner_model
   self.executor_model = executor_model
   ```

3. Update `_create_planner()` and `_create_executor()`:
   ```python
   def _create_planner(self) -> PlannerAgent:
       if self.planner is None:
           kwargs = {"session_id": f"{self.session_id}-planner"}
           if self.planner_model:
               kwargs["model"] = self.planner_model
           self.planner = create_planner_agent(**kwargs)
       return self.planner
   ```

### Phase 4: Persist Model Selection in Database

Store selected models in session for resume functionality:

1. Add columns to sessions table (or use existing metadata JSON):
   ```sql
   ALTER TABLE sessions ADD COLUMN planner_model TEXT;
   ALTER TABLE sessions ADD COLUMN executor_model TEXT;
   ```

2. Save on session creation:
   ```python
   db.create_session(
       feature_description=feature,
       planner_model=planner_model,
       executor_model=executor_model,
       db_path=db_path
   )
   ```

3. Load on session resume:
   ```python
   session = db.get_session(session_id)
   self.planner_model = session.get("planner_model")
   self.executor_model = session.get("executor_model")
   ```

### Phase 5: Display in Status Output

Show model info in `status` command and session header:

```
=== Orchestrator Auto: My Feature ===

Session ID: abc123
Models: Planner=opus-4.5 | Executor=haiku-3.5
Phase: EXECUTION
```

### Phase 6: Update Tests

1. Test CLI accepts new options
2. Test models are passed to orchestrator
3. Test models are persisted in database
4. Test resume uses stored models
5. Test default models when not specified

## Files to Modify

| File | Changes |
|------|---------|
| `cli.py` | Add `--planner-model` and `--executor-model` options |
| `engine.py` | Accept and use model parameters |
| `db.py` | Store/retrieve model selection |
| `config.py` | **NEW** - Config file loading, model aliases, resolution |
| `pyproject.toml` | Add `pyyaml` dependency |
| `tests/test_cli.py` | Test new CLI options |
| `tests/test_engine.py` | Test model passing |
| `tests/test_config.py` | **NEW** - Test config loading and model resolution |
| `README.md` | Document new options and config file |

## Model Reference

| Model ID | Alias | Best For |
|----------|-------|----------|
| `claude-opus-4-6` | Opus 4.5 | Complex planning, strategic decisions |
| `claude-sonnet-4-6` | Sonnet 4.5 | Balanced capability/cost |
| `claude-haiku-3-5-20241022` | Haiku 3.5 | Fast, simple tasks, cost-sensitive |

## Validation

Consider validating model IDs:
- Option A: No validation (allow any string, SDK will error if invalid)
- Option B: Warn on unknown models but allow
- Option C: Strict validation against known models

**Recommendation:** Option A (no validation) - SDK handles errors, future models work automatically.

## Success Criteria

1. Users can specify models via CLI flags
2. Models persist across session resume
3. Status output shows current models
4. Default behavior unchanged when flags not provided
5. All existing tests pass
6. Documentation updated

## Decisions

### 1. Short Aliases - YES

Support short names that map to latest model versions:

| Alias | Full Model ID |
|-------|---------------|
| `opus` | `claude-opus-4-6` |
| `sonnet` | `claude-sonnet-4-6` |
| `haiku` | `claude-haiku-3-5-20241022` |

Usage:
```bash
orchestrator start -f "My feature" --planner-model opus --executor-model haiku
```

Implementation:
```python
MODEL_ALIASES = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-3-5-20241022",
}

def resolve_model(model: str) -> str:
    """Resolve model alias to full model ID."""
    return MODEL_ALIASES.get(model.lower(), model)
```

### 2. Config File - YES

Support default models in config file at `~/.claude_orchestrator/config.yaml`:

```yaml
# ~/.claude_orchestrator/config.yaml
models:
  planner: opus      # or full model ID
  executor: sonnet   # or full model ID
```

Priority (highest to lowest):
1. CLI flags (`--planner-model`, `--executor-model`)
2. Config file (`~/.claude_orchestrator/config.yaml`)
3. Hardcoded defaults (opus, sonnet)

Implementation:
```python
def load_config() -> dict:
    """Load config from ~/.claude_orchestrator/config.yaml"""
    config_path = Path.home() / ".claude_orchestrator" / "config.yaml"
    if config_path.exists():
        import yaml
        return yaml.safe_load(config_path.read_text())
    return {}
```

### 3. Cost Estimation - NO

Not needed - user is on Claude Max subscription.
