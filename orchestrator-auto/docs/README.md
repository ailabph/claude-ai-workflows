# orchestrator-auto Docs

This folder contains design notes for proposed and implemented features.

- Telegram integration design: `docs/FEATURE_telegram_integration.md`
- Activity indicator: `docs/FEATURE_activity_indicator.md`
- Conversation continuity: `docs/FEATURE_conversation_continuity.md`
- Model selection: `docs/FEATURE_model_selection.md`

---

## Next Priorities (Personal/Droplet Use)

1. **Retries (transport-level only):** automatic retry/backoff for transient API/network failures; keep semantic retries gated by planner/human.
2. **Observability shortcuts:** add lightweight CLI helpers like `orchestrator status <id> --tail N` / `--since 10m` to quickly see what changed without exporting.
3. **Safety controls for unattended runs:** quiet hours for non-blocker notifications, and caps per milestone (runtime/token/tool-call limits).
4. **Plan templates:** `orchestrator start --template <name>` to standardize repeatable workflows and reduce setup overhead.

---

## Droplet/Vacation Ops (1 Project = 1 Droplet)

- Recommended deployment model: install `orchestrator` globally on the droplet, `cd` into the project repo, and run sessions from that repo (matches local workflow).
- Persistence: rely on `~/.claude_orchestrator/db.sqlite` for session continuity; use `tmux` or `systemd` for process continuity.
- Auto-start on reboot (safe mode): run a dedicated command (e.g. `orchestrator daemon --auto-resume`) that:
  - acquires a single-instance lock
  - checks for `status=active` sessions in `planning`/`execution`
  - does nothing if heartbeat is recent (runner still alive)
  - force-resumes only if heartbeat is stale (default 20 min)
  - never auto-resumes `paused` (needs blocker answer) or `discovery` (human-driven)
- Multiple active sessions: resume only the most recently active session; alert/log if more exist.
