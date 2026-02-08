# Runbook: Ubuntu SSD Node (Headless) – Multi-Project Orchestrator

This runbook describes the recommended operational setup for running `orchestrator-auto` across many repos on a single Ubuntu server via SSH.

## Goals
- Run multiple projects concurrently (Django/Next/Nest/Laravel/etc.)
- Keep Telegram enabled per repo (one bot per repo)
- Run `orchestrator telegram listen` **always-on** (tmux-only for now)
- Avoid cross-project collisions by working from repo directories and using repo-local config

---

## 1) One-Time Server Bootstrap

- Install system basics: `git`, build tools, and language toolchains you need.
- Install Miniconda (recommended) and ensure `conda` is available in SSH shells.
- Install `orchestrator-auto` so the `orchestrator` CLI is available globally (or via a dedicated “tools” env).

Suggested repo layout:
- `~/code/<project>/` (each git repo)
- `~/.claude_orchestrator/` (global DB + optional global config)

---

## 2) Per-Repo Environments (No Containers)

In each repo, create/activate the correct environment:
- Django/Python: `conda activate <env>` (or `python -m venv .venv`)
- Next/Nest: install Node deps per repo (`node_modules`) and manage Node version with your preferred tool
- Laravel: install PHP deps per repo (`composer install`) and ensure correct PHP version

Tip: in each tmux window, always `cd` into the repo first, then activate the repo env.

---

## 3) Telegram: One Bot Per Repo (Repo-Local Config)

For each repo, create a repo-local config file (contains secrets; do not commit):
- Path: `<repo>/.claude_orchestrator/config.yaml`

Example:
```yaml
telegram:
  enabled: true
  bot_token: "123456:ABC..."      # BotFather token (one per repo)
  chat_id: "YOUR_CHAT_ID"            # Your DM chat id
  allowed_user_id: "YOUR_USER_ID"    # Optional but recommended

  stuck_sessions:
    enabled: true
    inactive_minutes: 20
```

Git hygiene:
- Ensure the repo ignores `.claude_orchestrator/` (or at minimum `.claude_orchestrator/config.yaml`).

Verification (run from inside the repo):
- `orchestrator telegram test`

---

## 4) tmux Layout (Always-On Listeners)

Create a single tmux session and one window per project.

Start:
- `tmux new -s orch`

Per project window:
1. Create window: `Ctrl-b c`
2. Rename window: `Ctrl-b ,` (e.g. `dj_api`, `nx_web`, `nest_srv`)
3. In the window:
   - Pane 1: always-on listener
   - Pane 2: interactive shell for start/resume/status

Recommended commands per window:

Pane 1 (listener):
```bash
cd ~/code/<project>
conda activate <env>  # if applicable
orchestrator telegram listen --verbose
```

Pane 2 (operator shell):
```bash
cd ~/code/<project>
conda activate <env>  # if applicable
orchestrator list
orchestrator status <id>
```

Detach/re-attach:
- Detach: `Ctrl-b d`
- Reattach: `tmux a -t orch`

---

## 5) Running Workflows (Per Repo)

Start a workflow (run from the repo):
- `orchestrator start -f "<feature>" --telegram`

During execution:
- You’ll get Telegram notifications for start/milestone/blocker/completion.
- If a blocker occurs, reply to the blocker message in Telegram.
- The always-on listener (`orchestrator telegram listen`) will map the reply to the blocker and resume the workflow.

---

## 6) Recovery / Triage

From within the repo directory:
- List sessions: `orchestrator list`
- Inspect: `orchestrator status <id>`

Common cases:
- Paused with blocker:
  - Prefer answering via Telegram reply (Phase 2).
  - Or manual: `orchestrator resume <id> --answer "..."`
- Orphaned active session (no process running):
  - `orchestrator reset <id>`
  - `orchestrator resume <id> --force`

---

## 7) Operational Notes

- Keep listeners running in tmux even when no sessions are active. This prepares for Phase 3 bot commands (`/status`, `/list`, `/help`) and enables immediate reply handling.
- If you restart SSH, tmux keeps everything alive.

Backups (recommended):
- Copy `~/.claude_orchestrator/db.sqlite` periodically to your network storage.

Security reminders:
- Never commit repo-local `.claude_orchestrator/config.yaml`.
- Prefer `allowed_user_id` allowlisting for DM-only safety.
