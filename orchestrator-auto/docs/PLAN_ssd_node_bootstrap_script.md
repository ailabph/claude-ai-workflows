# Plan: SSD Node Bootstrap Script (Multi-Repo)

This document captures the requirements for a future bash script to bootstrap a fresh Ubuntu SSD node for running multiple projects with `orchestrator-auto`.

## Objectives
- Headless Ubuntu server accessed via SSH.
- Multiple repos cloned via `gh` (user provides an explicit repo list).
- Each repo becomes “ready to run” (deps installed, basic commands available).
- `orchestrator` installed globally (or via a dedicated tools env).
- Telegram setup is repo-local (one bot per repo) using `<repo>/.claude_orchestrator/config.yaml` (gitignored).
- tmux-only operations initially; always-on `orchestrator telegram listen --verbose` per repo.
- Script must be idempotent (safe to re-run).

---

## Key Decisions
- Node toolchain: **nvm** (most stable across Linux versions).
- Node versioning: derive per-repo from `.nvmrc` or `.tool-versions`; otherwise install/use global Node LTS.
- Conda env naming: default env name derived from repo name (e.g., `orch_<repo>`).

---

## Inputs
- `--base-dir` (default: `/home/$USER/code`)
- `--repos-file` (required): lines like `owner/repo | stack_hint | notes`
- `--tmux-session` (default: `orch`)
- Optional toggles: `--with-node`, `--with-conda`, `--with-php` (auto-detect by default)

---

## Script Phases

### Phase A: Server Bootstrap (fresh machine)
- Install base packages: `git`, `curl`, `jq`, `tmux`, build tools.
- Ensure `gh` is installed (auth done manually by operator).
- Install Miniconda and ensure `conda` works in SSH shells.
- Install `nvm` and default Node LTS.
- Install PHP + Composer only if Laravel repos detected (or if `--with-php`).
- Install `orchestrator-auto` globally or in a dedicated tools env.

### Phase B: Per-Repo Bootstrap (loop)
For each repo:
- Clone or update repo via `gh`.
- Detect stack by files:
  - Python: `environment.yml`, `pyproject.toml`, `requirements*.txt`, `manage.py`
  - Node: `package.json`
  - Laravel: `composer.json`, `artisan`
- Enforce `.gitignore` includes `.claude_orchestrator/`.
- Create repo-local Telegram config template if missing:
  - `<repo>/.claude_orchestrator/config.yaml` with placeholders.
- Install deps best-effort:
  - Conda env from `environment.yml` (create/update).
  - Node deps via lockfile-aware command.
  - Composer deps for Laravel.
- Optional best-effort test run (continue on failure):
  - Python: `pytest` if present.
  - Node: `npm test`/`pnpm test` if configured.
  - Laravel: `php artisan test` if configured.

### Phase C: tmux Layout (optional)
- Create tmux session `orch`.
- One window per repo.
- Two panes:
  - Pane 1: `orchestrator telegram listen --verbose`
  - Pane 2: interactive shell (env activated, ready for start/resume)

---

## Open Items (to decide later)
- PHP version strategy for Laravel repos (default distro vs per-repo pinning).
- Whether to run tests by default vs opt-in.
- Whether to generate per-repo helper scripts (e.g., `./orch.sh`) to standardize env activation.
