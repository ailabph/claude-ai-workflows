# Plan: Telegram Phase 2 (Two-Way DM) + Repo-Local Config

## Goal
Enable answering blockers via Telegram (DM-only) so workflows can resume without being at the terminal. The design must work in both:
- Local dev: one globally-installed `orchestrator`, multiple repos on one machine
- Cloud: one repo per droplet (one orchestrator per project)

## Core Decisions
- **Routing strategy:** one bot per repo (simplest and safest).
- **Repo-local config:** support `<repo>/.claude_orchestrator/config.yaml` (contains secrets; must be gitignored).
- **Global fallback:** retain `~/.claude_orchestrator/config.yaml`.
- **Config precedence:** `CLI flags > env vars > repo config > global config > defaults`.
- **Listener runtime:** `orchestrator telegram listen` runs from within a repo by default; add `--repo` override for automation.
- **DB strategy:** keep the default global DB (`~/.claude_orchestrator/db.sqlite`), but enforce **project isolation** by tagging sessions with `project_id` (repo root path) and optionally storing `project_remote` (git origin URL) for display/debugging.

## Non-Goals (for Phase 2)
- No Telegram command bot (`/status`, `/list`, etc.) beyond reply-to-blocker routing.
- No webhooks/server mode.
- No multi-tenant routing within a single chat (avoid “central router” complexity).

---

## 1) Repo-Local Config Discovery Algorithm (CWD-aware)

### File locations
- **Repo config path:** `.claude_orchestrator/config.yaml` (relative to a repo root or any subdir)
- **Global config path:** `~/.claude_orchestrator/config.yaml`

### Discovery rules
Given `cwd = Path.cwd()`:
1. Walk upward from `cwd` to the filesystem root.
2. At each directory `d` visited:
   - If `d/.claude_orchestrator/config.yaml` exists, record it as a candidate.
   - If `d/.git` exists, treat `d` as the **git root boundary** and stop walking upward *after checking this directory*.
3. If one or more candidates were found, choose the **nearest** one (closest to `cwd`).
4. If no candidate found, repo-local config is `None`.

### Merge semantics
- Load global config first as base (if present).
- Load repo-local config second and shallow-merge over global:
  - For nested dicts (like `telegram`), merge recursively so repo config can override only `telegram.*` without wiping unrelated global config.
  - If parsing fails for repo config, ignore it and proceed with global.

### Precedence integration
Existing getters (e.g., `get_telegram_config()`, `get_stuck_sessions_config()`) should continue to apply env var overrides on top of the merged config.

### Safety notes
- This design supports local multi-repo operation without requiring users to set env vars.
- It also supports droplet automation via `systemd WorkingDirectory` or `--repo`.

---

## 2) Git Ignore (Secrets)

Update `.gitignore` to prevent accidental commits:
- Ignore `.claude_orchestrator/` at repo root.
- Optionally ignore only `.claude_orchestrator/config.yaml` if you want other files tracked.

Acceptance criteria:
- A repo-local telegram token cannot be committed by default.

---

## 3) DB + Persistence for Reply Routing

### Note on project isolation
Even with a single global DB, sessions must be isolated per repo. See **3.5) Project Scoping (Global DB Isolation)**.

### Schema changes
1. Add `telegram_message_id INTEGER` to `blockers`.
2. Create `telegram_state` table to persist polling cursor:
   - single-row store: `(id INTEGER PRIMARY KEY CHECK(id=1), last_update_id INTEGER)`

### DB helpers
Add (or equivalent) functions:
- `set_blocker_telegram_message_id(blocker_id: int, telegram_message_id: int, db_path: Optional[str]) -> None`
- `get_blocker_by_telegram_message_id(telegram_message_id: int, db_path: Optional[str]) -> Optional[Dict[str, Any]]`
- `get_telegram_last_update_id(db_path) -> int` (default 0)
- `set_telegram_last_update_id(last_update_id: int, db_path) -> None`

Acceptance criteria:
- Blocker notifications store Telegram `message_id` for reply mapping.
- Listener restarts do not reprocess old updates.

---

## 3.5) Project Scoping (Global DB Isolation)

### Why
Local dev runs one globally-installed `orchestrator` across many repos. To prevent cross-project collisions while still using a single DB, each session must be tagged with a stable project identity derived from the current repo.

### Schema changes
Add (backward-compatible) columns to `sessions`:
- `project_id TEXT` (recommended: absolute repo root path)
- `project_remote TEXT` (optional but preferred: git origin URL if available)

### How to compute project identity
- Determine repo root by walking up from `Path.cwd()` until `.git` is found.
- If no `.git` exists, treat `Path.cwd()` as the project root.
- Set `project_id = str(repo_root.resolve())`.
- Attempt to read git origin URL; if available, store as `project_remote`.

### When to set/update
- On `create_session(...)`, persist `project_id` (+ `project_remote`).
- For older sessions without these fields:
  - best-effort backfill on first load/resume (if the command is run inside a repo), OR
  - treat missing `project_id` as "unknown" and require explicit `--all-projects` to operate on it.

### CLI scoping rules
Default behavior when running inside a repo:
- `list`, `status`, `resume`, `reset`, and `telegram listen` operate only on sessions whose `project_id` matches the current repo.

Escape hatches:
- Add `--all-projects` (or equivalent) to `list`/`status` to show everything.
- Add `--force-project-mismatch` (or equivalent) to `resume`/`reset` if needed.

Acceptance criteria:
- From repo A, you cannot accidentally `resume` a repo B session without an explicit override.

---

## 4) Listener Command: `orchestrator telegram listen`

### CLI shape
Add a command under the existing `telegram` group:
- `orchestrator telegram listen`

Recommended options:
- `--repo PATH` (optional): sets project context (config discovery + working directory);
- `--db-path PATH` (optional): existing pattern;
- `--poll-interval SECONDS` (default ~2–5);
- `--once` (boolean): fetch + process one batch, then exit.
- `--verbose` (boolean): print decision traces for ignored updates and mapping failures (useful for debugging).

### DM-only validation
Accept inbound updates only if:
- `chat.type == "private"`
- `chat.id == configured chat_id`
- (optional but recommended) `from.id == allowed_user_id`

### Poll loop behavior
- Call `getUpdates` using `offset = last_update_id + 1`.
- For each update:
  - skip if no `message`.
  - if message is not a reply (`reply_to_message` missing), skip.
  - read `reply_to_message.message_id`.
  - find blocker by `telegram_message_id`.
  - if blocker exists and is unresolved:
    - persist the answer via existing blocker resolution path
    - call existing resume logic for that session (same semantics as `orchestrator resume <id> --answer ...`)
  - if blocker exists but is already resolved:
    - (optional UX) send a Telegram message/reply: "Already resolved; no action taken".
  - update `last_update_id` after processing.

### Error handling
- Never crash the entire loop on a single bad update; log and continue.
- Handle Telegram API errors with backoff (especially 429 / network errors).
- Add signal handling for clean shutdown under systemd (SIGTERM/SIGINT): close client and exit gracefully.

### Rate limits (document)
- Telegram Bot API is rate-limited; expect guidance like ~30 messages/sec overall, and lower practical limits per chat.
- Ensure the listener respects 429 retry-after responses and uses a conservative polling interval (2–5s).

---

## 5) Hook Blocker Notifications -> Store message_id

In the existing blocker flow:
- `notify_blocker(...)` returns Telegram `message_id`.
- If a message id is returned:
  - call `set_blocker_telegram_message_id(blocker_id, message_id)`.

Must be best-effort:
- Telegram failures should not crash workflow.

---

## 6) Local Multi-Project Setup (Option A)

Document recommended local setup to avoid cross-project collisions:
- Keep `orchestrator` installed globally.
- `cd` into a repo and rely on **repo-local config** OR per-repo env vars.

### Recommended tool: direnv (macOS compatible)
- Install via Homebrew: `brew install direnv`
- Add `eval "$(direnv hook zsh)"` (or bash) to shell rc.
- In each repo, create `.envrc` exporting:
  - `ORCHESTRATOR_TELEGRAM_BOT_TOKEN`
  - `ORCHESTRATOR_TELEGRAM_CHAT_ID`
  - `ORCHESTRATOR_TELEGRAM_ALLOWED_USER_ID` (optional)

Note: env vars should still override repo config (useful for temporary overrides).

---

## 7) Tests

### Config tests
- Repo-local override is discovered from nested subdirectories.
- Search stops at git root boundary.
- Merge behavior preserves unrelated global keys.
- Precedence: env vars override repo/global.
- Project identity derivation:
  - repo root detection works
  - git origin URL extraction works (when present)

### DB tests
- Migrations create `telegram_message_id` and `telegram_state`.
- Migrations add `sessions.project_id` and `sessions.project_remote`.
- `telegram_state.last_update_id` persists across calls.
- Blocker lookup by `telegram_message_id` works.
- `create_session(...)` persists the correct `project_id` (+ `project_remote`).

### Listener tests
- DM-only filters reject non-private chats and wrong chat_id.
- Reply mapping: reply_to_message.message_id resolves correct blocker.
- Listener resolves blocker and triggers resume call (mock Orchestrator/resume).
- Listener ignores replies for unknown message_id (and logs in `--verbose` mode).
- Listener optionally replies "already resolved" for resolved blockers.
- Cursor prevents duplicate processing.
- Project scoping: listener refuses to resume a session whose `project_id` does not match the current repo (unless explicit override).

---

## 8) Acceptance Criteria (End-to-End)

Local (multi-repo):
- Repo A and Repo B can run `orchestrator telegram listen` in separate terminals/tmux panes without cross-talk.
- Repo A commands (`list`, `status`, `resume`, `reset`) only operate on repo A sessions by default.
- Replying in Telegram to a blocker message resumes the correct repo’s session.

Droplet (single repo):
- Running `orchestrator telegram listen` from the repo resumes blockers.
- Running under systemd with `WorkingDirectory` works; alternatively `--repo` works.
- Listener shuts down cleanly on SIGTERM/SIGINT (no partial processing/cursor loss).

---

## 9) Rollout Notes
- Phase 2 should remain opt-in by running `orchestrator telegram listen`.
- Outbound notifications (Phase 1) continue to work without the listener.
- Recommend one bot per repo; organize in Telegram folders.
