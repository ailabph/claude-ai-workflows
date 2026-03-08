# Fix Packaging for Homebrew Distribution

**Status:** Ready to implement
**Scope:** `orchestrator-auto/pyproject.toml` only (2 changes)

---

## Problem Summary

Two bugs in `pyproject.toml` prevent a clean Homebrew install from working correctly:

| # | Severity | Issue | Impact |
|---|----------|-------|--------|
| 1 | High | `tui/styles/theme.tcss` not in `package-data` | TUI crashes on clean install — file missing from sdist/wheel |
| 2 | Medium | `anthropic` not declared as a dependency | `orchestrator check` (API key path) crashes on clean install |

---

## Fix 1 — Add TUI stylesheet to package-data

### Root Cause

`pyproject.toml:42–43` currently only declares:
```toml
[tool.setuptools.package-data]
orchestrator_auto = ["resources/*.md"]
```

The file `orchestrator_auto/tui/styles/theme.tcss` exists on disk but is excluded from the built
distribution because `.tcss` files are not matched by `resources/*.md`.

All four TUI apps reference it at class level — not lazily — so the failure happens at app startup,
not on import:

| File | Line | Reference |
|------|------|-----------|
| `tui/app.py` | 42 | `CSS_PATH = "styles/theme.tcss"` |
| `tui/watch_app.py` | 76 | `CSS_PATH = "styles/theme.tcss"` |
| `tui/queue_app.py` | 50 | `CSS_PATH = "styles/theme.tcss"` |
| `tui/todo_app.py` | 51 | `CSS_PATH = "styles/theme.tcss"` |

### Fix

Add `tui/styles/*.tcss` to the `package-data` glob. Using `*.tcss` rather than `theme.tcss`
future-proofs for any additional stylesheets added later.

**Before:**
```toml
[tool.setuptools.package-data]
orchestrator_auto = ["resources/*.md"]
```

**After:**
```toml
[tool.setuptools.package-data]
orchestrator_auto = [
    "resources/*.md",
    "tui/styles/*.tcss",
]
```

### Verification

Build both sdist and wheel, then check both artifacts (wheel is what pip actually installs):
```bash
cd orchestrator-auto/
python -m build                                                          # builds sdist + wheel
tar -tzf dist/orchestrator_auto-*.tar.gz | grep theme.tcss              # sdist check
unzip -l dist/orchestrator_auto-*.whl | grep theme.tcss                 # wheel check
# Expected in both: orchestrator_auto/tui/styles/theme.tcss
```

---

## Fix 2 — Declare `anthropic` as a core dependency

### Root Cause

`cli.py:2947` imports `anthropic` inside the API-key branch of `orchestrator check`:
```python
import anthropic  # line 2947 — inside `else` branch when auth_source == API_KEY
client = anthropic.Anthropic()
```

`anthropic` is **not** declared in `pyproject.toml:11` and is **not** a transitive dependency:
- `claude-agent-sdk` only requires `anyio` and `mcp` (confirmed via `pip show claude-agent-sdk`)
- On a clean Homebrew install without `anthropic` in the formula's `resource` blocks, this import
  will raise `ModuleNotFoundError` for any user on the API-key auth path

### Fix

Add `anthropic` to core `dependencies` in `pyproject.toml`. Pin to `>=0.40.0` to allow broad
compatibility while ensuring the `Anthropic()` client and `messages.create()` API used in
`cli.py:2950–2953` are available (both stable since 0.40.x).

**Before:**
```toml
dependencies = [
    "claude-agent-sdk>=0.1.46,<0.2.0",
    "click>=8.0",
    "prompt_toolkit>=3.0",
    "pyyaml>=6.0",
]
```

**After:**
```toml
dependencies = [
    "anthropic>=0.40.0",
    "claude-agent-sdk>=0.1.46,<0.2.0",
    "click>=8.0",
    "prompt_toolkit>=3.0",
    "pyyaml>=6.0",
]
```

### Why core and not optional

- The `orchestrator check` command is a general-purpose health check, not a TUI or Telegram
  feature. It is part of the base CLI surface area.
- API-key auth is one of only two supported auth methods (`CONFIGURATION.md:62–64`). Silently
  breaking it on a clean install is unacceptable.
- Adding it as core ensures it appears in the Homebrew formula's `resource` blocks automatically
  when `brew update-python-resources` or `poet` is run.

### Homebrew formula impact

After this change, re-run resource generation so `anthropic` and its own deps appear in the formula:
```bash
brew update-python-resources Formula/orchestrator-auto.rb
# or
poet -f orchestrator-auto   # in a fresh venv with updated package installed
```

---

## Combined Diff (pyproject.toml)

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "orchestrator-auto"
version = "1.9.0"
description = "Automated two-agent orchestrator workflow using Claude Agent SDK"
license = "MIT"
requires-python = ">=3.10"
dependencies = [
    "anthropic>=0.40.0",                      # <-- added
    "claude-agent-sdk>=0.1.46,<0.2.0",
    "click>=8.0",
    "prompt_toolkit>=3.0",
    "pyyaml>=6.0",
]

[project.urls]
Homepage = "https://github.com/ailabph/claude-ai-workflows"
Repository = "https://github.com/ailabph/claude-ai-workflows"
Issues = "https://github.com/ailabph/claude-ai-workflows/issues"

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]
telegram = [
    "httpx>=0.27",
]
tui = [
    "textual>=0.80.0",
]

[project.scripts]
orchestrator = "orchestrator_auto.cli:cli"

[tool.setuptools.packages.find]
include = ["orchestrator_auto*"]
exclude = ["tests*", "fixtures*", "test_plans*"]

[tool.setuptools.package-data]
orchestrator_auto = [
    "resources/*.md",
    "tui/styles/*.tcss",                      # <-- added
]
```

---

## Out of Scope (this plan)

| Item | Reason deferred |
|------|----------------|
| `orchestrator check` writing to `~/.claude_orchestrator/` during formula test | Formula test uses `--version`, not `check` — no change needed now |
| Missing repo-root `LICENSE` file in monorepo subdir packaging | Low priority; does not affect runtime or formula install |
| Bumping version to `1.9.1` | Separate release decision |

---

## Checklist

- [ ] Add `anthropic>=0.40.0` to `dependencies` in `pyproject.toml`
- [ ] Add `tui/styles/*.tcss` to `[tool.setuptools.package-data]` in `pyproject.toml`
- [ ] Build sdist and wheel (`python -m build`)
- [ ] Confirm `theme.tcss` is present in both built artifacts (sdist tar + wheel zip)
- [ ] Install the built wheel into a **fresh venv** (`pip install dist/orchestrator_auto-*.whl`) — not editable install, which reads from source and hides packaging mistakes
- [ ] In that venv, run `python -c "import anthropic"` — must succeed
- [ ] In that venv, run `ANTHROPIC_API_KEY=dummy orchestrator check` — confirm it does **not** fail with `ModuleNotFoundError: anthropic` (may still fail on invalid auth — that is expected)
- [ ] Re-run `brew update-python-resources` (or `poet`) to refresh formula resource blocks with `anthropic` included
