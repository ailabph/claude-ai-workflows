# Contributing to Claude AI Workflows

Thanks for your interest in contributing! This guide covers development setup, coding conventions, and the pull request process.

## Development Setup

### Prerequisites

- Python 3.10+
- conda (recommended) or virtualenv
- An Anthropic API key or Claude Pro/Max subscription

### Environment Setup

```bash
cd orchestrator-auto/
conda env create -f environment.yml
conda activate orchestrator-auto
pip install -e ".[dev]"
```

### Running Tests

```bash
# All tests
pytest tests/ -v

# Single file
pytest tests/test_engine.py -v

# Single test
pytest tests/test_engine.py::TestClass::test_method -v

# Filter by name
pytest -k "planner" -v
```

## Code Style

- **Python 3.10+** with type hints for public APIs
- **`pathlib.Path`** for file paths (not `os.path`)
- **f-strings** for string interpolation
- **Import order:** stdlib, third-party, local (separated by blank lines)
- **Error handling:** `ValueError` for invalid state/input; catch specific exceptions at boundaries
- **DB access:** use `db.get_connection()` context manager with parameterized SQL
- **Subprocess:** always use `subprocess.run(..., capture_output=True, text=True, timeout=N)`
- **Tests:** use pytest fixtures (`tmp_path` for temp files), mock all API/network calls

## Project Structure

```
orchestrator-auto/
  orchestrator_auto/     # Main package
    tui/                 # Textual TUI (watch mode)
      widgets/           # Custom UI components
      screens/           # Modal screens
      styles/            # TCSS stylesheets
    controllers/         # Watch/queue controllers
    validation/          # Post-milestone validators
  tests/                 # pytest test suite
  fixtures/              # Test fixtures
```

## Pull Request Process

1. **Fork** the repository and create a feature branch from `main`
2. **Write tests** for new functionality
3. **Run the test suite** and confirm all tests pass
4. **Keep commits focused** - one logical change per commit
5. **Write a clear PR description** explaining what changed and why
6. **Link related issues** if applicable

### Commit Messages

Use clear, imperative commit messages:

```
feat: add pagination to session list endpoint
fix: resolve token counter reset between files
docs: update CLI usage examples
```

## Reporting Issues

When filing an issue, include:

- **Steps to reproduce** the problem
- **Expected vs actual behavior**
- **Python version** and **OS**
- **Relevant logs** (with secrets redacted)

## Architecture Notes

If you're working on the orchestrator engine or TUI, read these key files first:

- `orchestrator_auto/engine.py` - Core orchestration loop and state machine
- `orchestrator_auto/agents.py` - Claude Agent SDK wrappers
- `orchestrator_auto/state.py` - Session state transitions
- `orchestrator_auto/tui/watch_app.py` - Main TUI application

The TUI has three layout modes (Layout B, Verbose, Compact) - always test changes across all three.
