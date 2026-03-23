# AGENTS.md (repo root)

This repository is mostly workflow documentation plus a Python CLI tool in
`orchestrator-auto/`. Use this file for repo-wide guidance.

Scoped rules:
- `AGENTS.md` files apply to their directory subtree.
- The nearest (most nested) `AGENTS.md` wins.
- For code changes under `orchestrator-auto/`, follow `orchestrator-auto/AGENTS.md`.

## Repo map
- `orchestrator-auto/`: primary Python package + tests (SQLite-backed CLI orchestrator)
- `scripts/`: standalone utility scripts (e.g., `kagi-api.py` for Kagi search/summarize/enrich)
- `docs/`, `design-system/`, `backend-system/`, `CLAUDE_*.md`: workflow docs/templates
- `claude/`, `opencode/`: helper scripts/configs for agents

## Cursor / Copilot rules
Checked locations:
- Cursor rules: none found (no `.cursor/rules/` and no `.cursorrules`).
- Copilot instructions: none found (no `.github/copilot-instructions.md`).

If any of these files are added later, their instructions take precedence.

## Build / run / test (primary project: `orchestrator-auto/`)
Most “build” is an editable install. Run commands from `orchestrator-auto/`.

### Environment setup
```bash
cd orchestrator-auto

# Conda env (environment.yml pins python=3.11)
conda env create -f environment.yml
conda activate orchestrator-auto

# Editable install
pip install -e .

# Dev extras (pytest)
pip install -e ".[dev]"

# Optional Telegram support
pip install -e ".[telegram]"
```

### Run the CLI
```bash
cd orchestrator-auto
orchestrator --help

# Typical usage
orchestrator start -f "Feature description"
orchestrator list
orchestrator status <session-id>
orchestrator resume <session-id>
```

### Tests (pytest)
```bash
cd orchestrator-auto

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_engine.py -v

# Run a single test (node id)
pytest tests/test_engine.py::TestOrchestratorInitialization::test_create_new_session -v

# Filter by name (fast iteration)
pytest -k "planner" -v

# Show prints (disable capture)
pytest tests/test_engine.py::TestOrchestratorInitialization::test_create_new_session -v -s

# Stop on first failure
pytest tests/ -x

# Coverage (optional; requires pytest-cov installed)
pytest tests/ --cov=orchestrator_auto
```

### Lint / format
No linter/formatter is configured in `orchestrator-auto/pyproject.toml`.

Optional local tooling (only run if installed):
```bash
ruff check .
ruff format .
```

## Code style guidelines (Python)
These guidelines reflect existing patterns under `orchestrator-auto/orchestrator_auto/`.

### Python version + typing
- Target Python `>=3.10` (project metadata), env uses Python `3.11`.
- Type-hint public functions/methods where practical.
- Prefer `Optional[T]`, `Dict[str, Any]`, `List[T]` over `T | None` to match the codebase.
- Use `TYPE_CHECKING` to avoid runtime imports for type hints (pattern exists in `engine.py`).

### Naming conventions
- Modules/files: `snake_case.py`.
- Functions/vars: `snake_case`.
- Classes: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.

### Imports
- Prefer grouping: stdlib → third-party → local.
- Keep import style consistent within the file you touch (some files are not perfectly sorted).
- Avoid unused imports.
- Use relative imports inside the package (e.g., `from . import db`).

### Formatting + docstrings
- 4-space indentation.
- Use f-strings for interpolation.
- Use triple-double-quote docstrings for modules/classes/functions.
- Keep lines reasonably short (no enforced max).

### CLI vs library boundaries
- CLI output uses `click.echo` / `click.secho` (`orchestrator_auto/cli.py`).
- Prefer returning values / raising exceptions from library code.
- Catch and present user-friendly messages at boundaries (CLI, network, subprocess).

### Error handling
- Use `ValueError` for invalid user input or invalid workflow state (common pattern).
- Prefer catching specific exceptions (e.g., `OSError`, `subprocess.TimeoutExpired`).
- Use broad `except Exception` only to prevent a workflow crash; include context and/or re-raise.

### Paths + filesystem
- Prefer `pathlib.Path`.
- Ensure parent directories exist before writing (`Path(...).parent.mkdir(..., exist_ok=True)`).
- Be explicit about repo-relative vs user-provided paths.

### Database (SQLite)
- Use `orchestrator_auto.db.get_connection()` context manager; it handles commit/rollback.
- Use parameterized SQL; never string-format SQL.

### Subprocess / git
- Use `subprocess.run(..., capture_output=True, text=True, timeout=N)`.
- Always set timeouts for git/network-ish calls.
- Check `returncode` and handle non-zero results.

### Tests
- Tests use `pytest` + `unittest.mock` (`patch`, `Mock`, `MagicMock`).
- Prefer `tmp_path` for temp dirs/files (some tests use `tempfile` too; follow local style).
- Clean up any files/directories created by the code under test.
- Do not make real network/API calls in unit tests; mock them.

## Documentation conventions (Markdown)
- Avoid reformatting entire documents; make targeted edits only.
- Keep the existing workflow-framework voice (milestones, deliverables, gates).

## Safety defaults for agents
- Do not create `git commit` or push unless explicitly asked.
- Do not add new dependencies unless explicitly requested.
- Treat secrets carefully: never paste API keys/tokens into the repo; avoid committing `.env`.
