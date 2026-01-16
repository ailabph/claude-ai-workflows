# Troubleshooting

Common issues and solutions for orchestrator-auto.

## Quick Reference

| Error | Solution |
|-------|----------|
| Session not found | Run `orchestrator list` to find valid IDs |
| Database locked | Close other orchestrator instances |
| Agent timeout | Check internet/API key |
| Workflow error | Check log file at `~/.claude_orchestrator/logs/error_<session_id>_*.log` |

---

## Common Issues

### I started a workflow but it paused with a blocker. What do I do?

**Blocker = Executor asking for clarification or human input.**

The session paused because the executor needs information:
- Unclear requirements
- Decision needed (approach A vs B)
- External dependency (need API key, etc.)

Check what the blocker is:
```bash
orchestrator status <session-id>
```

See the blocker message? Respond:
```bash
orchestrator respond <session-id> "Your answer here"
```

Workflow resumes and continues to next milestone.

---

### My API key doesn't work

**Diagnose:**
```bash
orchestrator check
```

**If check fails:**
1. **API key format wrong:** Should be `sk-ant-api03-...` (not `sk-ant-oat01-...` which is OAuth)
2. **Key has no credits:** Visit https://console.anthropic.com/account/billing/overview
3. **Wrong variable name:** Use `ANTHROPIC_API_KEY` for API keys, not `CLAUDE_CODE_OAUTH_TOKEN`

---

### Workflow seems stuck / no progress for 10+ minutes

**Check status:**
```bash
orchestrator status <session-id>
```

**If it shows ACTIVE but no heartbeat:**
```bash
orchestrator reset <session-id>
```

Then resume:
```bash
orchestrator resume <session-id>
```

**If that doesn't work, force-resume:**
```bash
orchestrator resume <session-id> --force
```

---

### I want to stop and start over

```bash
# Don't use reset—that's just for stuck sessions
# Instead, just start a new workflow:
orchestrator start -f "New feature description"
```

Old session stays in database but won't interfere.

---

### Where are the logs?

Every session logs to:
```
~/.claude_orchestrator/logs/error_<session-id>_<timestamp>.log
```

Check that file if something goes wrong:
```bash
cat ~/.claude_orchestrator/logs/error_*.log
```

---

### I have multiple sessions and want to clean up

List all sessions:
```bash
orchestrator list --all-projects
```

Sessions persist in database. They don't take resources. You can safely leave them.

---

## Error Handling

When a workflow fails, the orchestrator:
1. Logs full stack trace to `~/.claude_orchestrator/logs/error_<session_id>_<timestamp>.log`
2. Marks the session as failed with error context
3. Shows user-friendly message with log file path

Use `--debug` flag for immediate stack trace output:
```bash
orchestrator start -f "My feature" --debug
orchestrator resume <session-id> --debug
```

Use `orchestrator status <session-id>` to view error details for failed sessions.

---

## MCP Process Cleanup

If a session crashes while using Playwright MCP, browser/server processes may be left running.

**Detect potential orphans:**
```bash
orchestrator check
```

**Clean up MCP server processes:**
```bash
orchestrator cleanup --dry-run   # Preview first!
orchestrator cleanup             # Interactive cleanup
orchestrator cleanup -f          # Force without confirmation
```

**Include browser processes (use with caution):**
```bash
orchestrator cleanup --all --dry-run  # Preview
orchestrator cleanup --all            # Kill servers + browsers
```

> **Warning**: The `--all` flag may kill Playwright processes from other applications
> (e.g., if you're running `npx playwright test` in another terminal). Always preview
> with `--dry-run` first.

**Common crash cause:** Using `browser_snapshot` on complex pages (dashboards, large tables)
can exceed the 1MB response buffer limit. The executor is instructed to prefer
`browser_take_screenshot` for safety.

---

## Session States Explained

| Phase | Status | Meaning |
|-------|--------|---------|
| discovery | active | Planner gathering requirements |
| planning | active | Planner creating milestones |
| execution | active | Executor implementing milestones |
| paused | paused | Waiting for human input (blocker) |
| completed | completed | All milestones done |
| completed | failed | Error occurred |

**Key transitions:**
- `active` → `paused`: Blocker created
- `paused` → `active`: Blocker resolved via `respond`
- `active` → `completed`: All work done or error occurred

---

## Debugging Tips

### Check conversation history

```bash
orchestrator export <session-id> -o debug.md
```

This exports all messages, agent responses, and state transitions.

### Check database directly

```bash
sqlite3 ~/.claude_orchestrator/db.sqlite
sqlite> SELECT id, phase, status, current_milestone FROM sessions ORDER BY updated_at DESC LIMIT 5;
sqlite> SELECT agent, content FROM messages WHERE session_id = 'xxx' ORDER BY created_at;
```

### Force session state

If a session is stuck in an invalid state:

```bash
# Reset heartbeat and prepare for force resume
orchestrator reset <session-id>

# Force resume (bypasses pause check)
orchestrator resume <session-id> --force

# Force complete (for stuck-but-done sessions)
orchestrator complete <session-id>
```

---

## Getting Help

- Check logs: `~/.claude_orchestrator/logs/`
- Export session: `orchestrator export <id> -o report.md`
- Run health check: `orchestrator check -v`
- Debug mode: Add `--debug` to any command
