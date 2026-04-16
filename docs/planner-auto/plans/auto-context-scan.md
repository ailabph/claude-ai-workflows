# Auto-Context Scan

Automatically discover and add key codebase files as session context when starting a planner-auto session, instead of requiring manual `add-context --file` for each file.

## Problem

planner-auto detects the repo root via `git rev-parse` but doesn't read any files from it. Users must manually add every context file, which is tedious and error-prone. Plans generated without codebase context are generic and low-quality.

## Design

### CLI surface

```bash
# New flag on start and session commands
planner-auto start --project my-api --scan
planner-auto session --project my-api --tui --scan

# Standalone command for existing sessions
planner-auto scan <session-id>

# Control what gets scanned
planner-auto start --project my-api --scan --scan-max 30
planner-auto start --project my-api --scan --scan-include "*.py,*.ts"
planner-auto start --project my-api --scan --scan-exclude "migrations/*"
```

### Default scan behavior

1. Run `git ls-files` from repo root (respects `.gitignore` automatically)
2. Filter to recognized source extensions: `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.go`, `.rs`, `.java`, `.rb`, `.vue`, `.svelte`
3. Include config files by name: `pyproject.toml`, `setup.py`, `setup.cfg`, `package.json`, `tsconfig.json`, `Cargo.toml`, `go.mod`, `Makefile`, `Dockerfile`, `docker-compose.yml`
4. Include documentation: `README.md`, `CLAUDE.md`, `AGENTS.md` (top-level only)
5. Exclude known noise: `*lock*`, `*.min.js`, `*.generated.*`, `node_modules/`, `dist/`, `build/`, `__pycache__/`, `.git/`
6. Sort by priority: config files first, then source files sorted by directory depth (shallower = more important)
7. Cap at `--scan-max` files (default: 20)
8. Add each file via existing `add_context_entry()` with type `file`

### Why `git ls-files`

- Already respects `.gitignore` — no vendored/generated junk
- Fast even on large repos
- Only tracked files — no untracked experiments
- Already have `subprocess.run` pattern in `git_utils.py`

## Implementation

### Files to change

| File | Change |
|------|--------|
| `planner_auto/context_service.py` | Add `scan_repo(conn, session_id, repo_root, **opts)` function |
| `planner_auto/git_utils.py` | Add `list_tracked_files(cwd, extensions, excludes)` function |
| `planner_auto/cli.py` | Add `--scan`, `--scan-max`, `--scan-include`, `--scan-exclude` flags to `start` and `session` commands. Add `scan` standalone command |
| `planner_auto/tui/session_app.py` | If `--scan` passed, run scan on mount and populate context list |
| `tests/test_context_scan.py` | New test file |

### `git_utils.py` — new function

```python
def list_tracked_files(
    cwd: str | None = None,
    extensions: set[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> list[str]:
    """Return tracked files from git ls-files, filtered and sorted."""
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True, text=True, timeout=10, cwd=cwd,
    )
    if result.returncode != 0:
        return []

    files = result.stdout.strip().splitlines()
    # filter by extension, exclude patterns, sort by depth
    ...
    return files
```

### `context_service.py` — new function

```python
def scan_repo(
    conn, session_id: str, repo_root: str,
    max_files: int = 20,
    include_ext: set[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> int:
    """Scan repo and add files as context entries. Returns count added."""
    files = list_tracked_files(cwd=repo_root, extensions=include_ext, ...)

    # Priority sort: config > docs > shallow source > deep source
    files = _prioritize(files)
    files = files[:max_files]

    count = 0
    for f in files:
        full_path = os.path.join(repo_root, f)
        add_context_entry(conn, session_id, "file", path=full_path)
        count += 1
    conn.commit()
    return count
```

### `cli.py` — flag additions

Add to both `start` and `session` commands:

```python
@click.option("--scan", is_flag=True, default=False, help="Auto-scan repo and add key files as context.")
@click.option("--scan-max", default=20, type=int, help="Max files to add during scan (default: 20).")
@click.option("--scan-include", default=None, help="Comma-separated extensions to include (e.g. '*.py,*.ts').")
@click.option("--scan-exclude", default=None, help="Comma-separated patterns to exclude.")
```

After session creation, if `--scan` and `resolved_repo_root`:

```python
if scan and resolved_repo_root:
    count = scan_repo(conn, session_id, resolved_repo_root,
                      max_files=scan_max, ...)
    click.echo(f"Scanned: {count} files added as context")
```

### Standalone `scan` command

```python
@cli.command("scan")
@click.argument("session_id")
@click.option("--max", "scan_max", default=20, type=int)
def scan_cmd(session_id, scan_max):
    """Scan repo and add files to an existing session's context."""
```

## File size guard

Skip files larger than 100KB to avoid blowing up context. Log a warning for skipped files.

## Status: Implemented

Implemented and merged. 34 tests in `tests/test_context_scan.py`, 648 total passing.

### Design decisions made during implementation

- **Phase enforcement**: `scan` is registered in `PHASE_ALLOWED_COMMANDS` for SETUP and CONTEXT only. The standalone `scan` command calls `SessionManager.check_command()` to prevent context mutation on PAUSED/REVIEW/COMPLETE sessions.
- **`--scan-include` parsing**: Accepts `*.py`, `.py`, or `py` formats — all normalized to `.py` by stripping leading `*` before adding the dot prefix.
- **File size guard**: 100KB (not 500KB like manual `add-context`) to keep scanned context lean.

## Not in scope

- Intelligent file selection (e.g., ranking by import graph) — future enhancement
- Incremental re-scan (add only new files) — can add later
- Automatic scan without `--scan` flag — explicit opt-in to avoid surprises
