# Claude Orchestrator v2: Automated Milestone Workflow

## Overview

A **fully automated two-agent workflow** for complex software engineering tasks. The `orchestrator-auto` CLI handles all agent communication, state persistence, and milestone gating - eliminating manual copy-paste between sessions.

**Key Difference from v1**: No manual session management. The orchestrator engine routes messages between planner and executor automatically.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           orchestrator-auto                                   │
│                                                                              │
│  ┌────────────────────┐              ┌────────────────────┐                 │
│  │   PLANNER AGENT    │◄────────────►│   EXECUTOR AGENT   │                 │
│  │   (Opus 4.5)       │   automatic  │   (Sonnet 4.5)     │                 │
│  ├────────────────────┤   routing    ├────────────────────┤                 │
│  │ • Discovery chat   │              │ • Executes ONE     │                 │
│  │ • Creates plan     │              │   milestone        │                 │
│  │ • Reviews reports  │              │ • Progress report  │                 │
│  │ • Approves/rejects │              │ • Waits for review │                 │
│  └────────────────────┘              └────────────────────┘                 │
│           │                                    │                             │
│           └──────────────┬─────────────────────┘                             │
│                          ▼                                                   │
│              ┌───────────────────────┐                                      │
│              │   Orchestrator Engine  │                                      │
│              ├───────────────────────┤                                      │
│              │ • State machine        │                                      │
│              │ • Response parsing     │                                      │
│              │ • Blocker handling     │                                      │
│              │ • Milestone tracking   │                                      │
│              └───────────┬───────────┘                                      │
│                          ▼                                                   │
│              ┌───────────────────────┐                                      │
│              │   SQLite Database      │                                      │
│              │   (~/.claude_orch...)  │                                      │
│              └───────────────────────┘                                      │
│                          │                                                   │
│           ┌──────────────┼──────────────┐                                   │
│           ▼              ▼              ▼                                   │
│     ┌──────────┐  ┌───────────┐  ┌───────────┐                             │
│     │ Sessions │  │ Milestones│  │ Blockers  │                             │
│     └──────────┘  └───────────┘  └───────────┘                             │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Start a New Workflow

```bash
# Interactive discovery → planning → execution
orchestrator start -f "Add user authentication with JWT"

# Skip discovery, use existing plan
orchestrator start --plan docs/feature/DOC_auth_plan.md

# Cost-optimized models
orchestrator start -f "My feature" -pm sonnet -em haiku
```

### 2. Handle Blockers

When an agent needs human input, the workflow pauses:

```bash
# Check what's blocking
orchestrator status <session-id>

# Respond to blocker
orchestrator respond <session-id> "Use PostgreSQL for the database"

# Resume workflow
orchestrator resume <session-id>
```

### 3. Workflow Completes

```bash
# Auto-commit on completion
orchestrator start -f "My feature" --auto-commit

# With AI-generated commit messages
orchestrator start -f "My feature" --auto-commit --smart-commit
```

---

## Workflow Phases

| Phase | Description | Human Action |
|-------|-------------|--------------|
| **Discovery** | Planner asks clarifying questions | Answer questions or type `/ready` |
| **Planning** | Planner creates implementation plan | Review plan, approve or request changes |
| **Execution** | Executor implements milestones, planner reviews | Respond to blockers if any |
| **Completed** | All milestones approved | Optional: review final changes |
| **Paused** | Waiting for human input | `orchestrator respond` or `resume` |

### Phase Flow

```
                    ┌─────────────┐
                    │   START     │
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
           ┌───────►│  DISCOVERY  │◄──────┐
           │        └──────┬──────┘       │
           │               │ /ready       │ questions
           │               ▼              │
           │        ┌─────────────┐       │
           │        │  PLANNING   │───────┘
           │        └──────┬──────┘
           │               │ [PLAN_READY]
           │               ▼
           │        ┌─────────────┐
           │        │  EXECUTION  │◄──────┐
           │        └──────┬──────┘       │
           │               │              │ [CHANGES_REQUESTED]
           │               ▼              │
           │        ┌─────────────┐       │
           │        │   REVIEW    │───────┘
           │        └──────┬──────┘
           │               │ [MILESTONE_APPROVED]
           │               ▼
           │        ┌─────────────┐
    blocker│        │  All done?  │
           │        └──────┬──────┘
           │          yes/ │ \no
           │              ▼   ▼
           │     ┌──────────┐  │
           │     │ COMPLETED│  │
           │     └──────────┘  │
           │                   │
           │        ┌──────────┘
           │        ▼
           │  ┌─────────────┐
           └──│   PAUSED    │ ← [HUMAN_INPUT_NEEDED] / [BLOCKED]
              └─────────────┘
                    │
                    │ orchestrator respond
                    ▼
              (returns to previous phase)
```

---

## Plan Document Format

Plans must have **parseable milestone headers** for the orchestrator to track progress.

### Required Format

```markdown
# Feature Name - Implementation Plan

## Overview
[Brief description of what we're building]

## Milestone 1: [Name]
[Description of deliverables]

### Tasks
- [ ] Task 1
- [ ] Task 2

### Deliverables
- [ ] File created/modified
- [ ] Tests passing

## Milestone 2: [Name]
...

## Milestone N: [Name]
...
```

### Milestone Header Patterns (Parser Compatible)

The parser accepts these formats:

```markdown
## Milestone 1: Schema and Models
### Milestone 1: Schema and Models
## M1: Schema and Models
### M1: Schema and Models
```

**Key Rules:**
- Use `##` or `###` for milestone headers
- Include milestone number (1, 2, 3...)
- Colon separator before name
- Sequential numbering starting from 1

### Converting Existing Plans

```bash
# Check if plan is compatible
orchestrator convert plan.md --validate-only

# Convert to orchestrator format
orchestrator convert plan.md -o converted.md

# Convert in place (creates backup)
orchestrator convert plan.md --in-place
```

---

## Response Tags (Agent Communication)

The orchestrator parses structured tags from agent responses to determine state transitions.

### Planner Tags

| Tag | Meaning | Next Action |
|-----|---------|-------------|
| `[PLAN_READY]` | Plan document created | Transition to execution phase |
| `[MILESTONE_APPROVED]` | Current milestone accepted | Advance to next milestone or complete |
| `[CHANGES_REQUESTED]` | Milestone needs revision | Route feedback to executor |
| `[HUMAN_INPUT_NEEDED]` | Blocker - need human clarification | Pause workflow, await response |

### Executor Tags

| Tag | Meaning | Next Action |
|-----|---------|-------------|
| `[PROGRESS_REPORT]` | Milestone work complete | Route to planner for review |
| `[CLARIFICATION_NEEDED]` | Need planner guidance | Route question to planner |
| `[BLOCKED]` | External dependency blocking | Pause workflow, await response |

### Tag Examples

**Planner approving milestone:**
```
The serializer implementation looks correct. Tests are passing with good coverage.

[MILESTONE_APPROVED]

Proceed to Milestone 2: Service Layer.
```

**Executor reporting progress:**
```
[PROGRESS_REPORT]

## Milestone 1: Serializers - COMPLETED

### Files Created/Modified:
- app/serializers.py (modified)
- app/tests/test_serializers.py (created)

### Test Results:
All 12 tests passing. Coverage: 94%

### Ready for Review: YES
```

**Planner requesting human input:**
```
I need clarification on the authentication approach.

[HUMAN_INPUT_NEEDED]

Should we use:
1. JWT with refresh tokens
2. Session-based auth
3. OAuth2 with external provider
```

---

## Blocker Handling

When an agent emits `[HUMAN_INPUT_NEEDED]` or `[BLOCKED]`, the workflow pauses.

### Check Blocker Status

```bash
orchestrator status <session-id>
```

Output shows:
```
⚠️  UNRESOLVED BLOCKERS:

  Agent: planner
  Question: Should we use JWT or session-based auth?
  Created: 2025-12-15 10:30:00
```

### Respond to Blocker

```bash
# Answer the question
orchestrator respond <session-id> "Use JWT with refresh tokens"

# Then resume (if not auto-resumed)
orchestrator resume <session-id>
```

### Telegram Integration

Receive blocker notifications on your phone and reply directly:

```bash
# Enable notifications
orchestrator start -f "My feature" --telegram

# Listen for replies (run in separate terminal)
orchestrator telegram listen
```

---

## Queue Mode

Execute multiple plans sequentially without manual intervention.

```bash
# Queue multiple plans
orchestrator start --queue plan1.md plan2.md plan3.md

# Resume existing queue
orchestrator start --queue

# Reset and recreate queue
orchestrator start --queue --queue-reset plan1.md plan2.md
```

### Queue Behavior

| Scenario | Behavior |
|----------|----------|
| Plan completes | Next plan starts automatically |
| Plan fails | Recorded as failed, queue continues |
| Blocker encountered | Queue pauses, resume with `orchestrator resume` |
| Crash/restart | Queue resumes from last pending item |

### Queue Visibility

```bash
orchestrator list
```

Shows queue position:
```
a1b2c3d4  My Feature         EXECUTION  ACTIVE   Queue: #1 [RUNNING]
b2c3d4e5  Another Feature    PENDING    PENDING  Queue: #2 [PENDING]
c3d4e5f6  Third Feature      PENDING    PENDING  Queue: #3 [PENDING]
```

---

## Watch Mode

Monitor a directory for new plan files and process automatically.

```bash
# Watch directory
orchestrator watch ./plans/

# With options
orchestrator watch ./plans/ --auto-commit --telegram
```

### File Naming Conventions

| Pattern | Meaning |
|---------|---------|
| `feature.md` | Pending plan (will be processed) |
| `feature_done.md` | Completed successfully |
| `feature_failed.md` | Failed execution |
| `feature_paused.md` | Paused on blocker |
| `_orchestrator-skip__*` | Quarantined (ignored) |

### Watch Workflow

1. Drop `feature.md` into watched directory
2. Watcher validates and auto-converts if needed
3. Orchestrator executes the plan
4. File renamed based on outcome

---

## Auto-Commit

Automatically commit changes when workflow completes.

```bash
# Basic auto-commit
orchestrator start -f "My feature" --auto-commit

# With AI-generated commit messages
orchestrator start -f "My feature" --auto-commit --smart-commit

# Specify model for commit messages
orchestrator start -f "My feature" --auto-commit --auto-commit-model haiku
```

### Smart Commit Messages

AI analyzes the diff and generates Conventional Commits format:

```
feat(auth): add JWT authentication with refresh tokens

- Add JWTService with token generation and validation
- Implement refresh token rotation
- Add authentication middleware
```

**Commit Types:**
| Type | When Used |
|------|-----------|
| `feat` | New functionality |
| `fix` | Bug correction |
| `refactor` | Code restructuring |
| `docs` | Documentation only |
| `test` | Test files only |
| `chore` | Config, dependencies |

### Security

Smart commit scans for secrets before sending diff to AI:
- API keys and tokens
- Passwords in assignments
- Private keys (RSA, EC, SSH)
- AWS credentials
- GitHub PATs, OpenAI keys

If secrets detected, falls back to static message.

---

## Configuration

### Priority Order

CLI flags > env vars > repo config > global config > defaults

### Config File Locations

| Location | Scope |
|----------|-------|
| `~/.claude_orchestrator/config.yaml` | Global (all projects) |
| `<repo>/.claude_orchestrator/config.yaml` | Repository-local |

### Example Config

```yaml
# ~/.claude_orchestrator/config.yaml

models:
  planner: opus
  executor: sonnet

auto_commit:
  smart: true
  model: haiku

telegram:
  enabled: true
  bot_token: "123456789:ABC..."
  chat_id: "YOUR_CHAT_ID"
  stuck_sessions:
    enabled: true
    inactive_minutes: 20
```

### Model Aliases

| Alias | Model ID |
|-------|----------|
| `opus` | claude-opus-4-5-20251101 |
| `sonnet` | claude-sonnet-4-5-20250929 |
| `haiku` | claude-haiku-3-5-20241022 |

---

## Plan Templates

### Backend API Plan

```markdown
# [Feature] API - Implementation Plan

## Overview
[What endpoint(s) and why - 2-3 sentences]

## Milestone 1: Serializers and Schemas
### Tasks
- [ ] Create request/response serializers
- [ ] Add validation rules
- [ ] Write unit tests

### Deliverables
- [ ] `app/serializers.py` updated
- [ ] `tests/test_serializers.py` created
- [ ] All tests passing

## Milestone 2: Service Layer
### Tasks
- [ ] Implement business logic in service
- [ ] Add error handling
- [ ] Write service tests

### Deliverables
- [ ] `app/services/feature.py` created
- [ ] `tests/test_feature_service.py` created
- [ ] 90%+ coverage

## Milestone 3: View and Routes
### Tasks
- [ ] Create API view
- [ ] Add URL routing
- [ ] Write integration tests

### Deliverables
- [ ] `app/views.py` updated
- [ ] `app/urls.py` updated
- [ ] Integration tests passing

## Milestone 4: Final Validation
### Tasks
- [ ] Run full test suite
- [ ] Verify coverage targets
- [ ] Update API documentation

### Deliverables
- [ ] All tests passing
- [ ] Coverage report meets targets
- [ ] OpenAPI schema updated
```

### Frontend Feature Plan

```markdown
# [Feature] - Implementation Plan

## Overview
[What component/page and why - 2-3 sentences]

## Milestone 1: Types and Components
### Tasks
- [ ] Define TypeScript interfaces
- [ ] Create base components
- [ ] Set up component structure

### Deliverables
- [ ] `types/feature.ts` created
- [ ] `components/Feature/` directory structure
- [ ] Base components rendering

## Milestone 2: Logic and State
### Tasks
- [ ] Implement React Query hooks
- [ ] Add state management
- [ ] Handle loading/error states

### Deliverables
- [ ] `hooks/useFeature.ts` created
- [ ] State management working
- [ ] Loading/error states functional

## Milestone 3: Styling and Polish
### Tasks
- [ ] Apply design system styles
- [ ] Implement responsive design
- [ ] Add animations/transitions

### Deliverables
- [ ] Matches design mockups
- [ ] Responsive at all breakpoints
- [ ] Smooth interactions

## Milestone 4: Testing
### Tasks
- [ ] Write component tests
- [ ] Add integration tests
- [ ] Test accessibility

### Deliverables
- [ ] 80%+ component coverage
- [ ] Integration tests passing
- [ ] No accessibility violations
```

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Session not found | Run `orchestrator list` to find valid IDs |
| Database locked | Close other orchestrator instances |
| Agent timeout | Check internet/API key |
| Orphaned session | `orchestrator reset <id>` then `resume --force` |
| Stuck at milestone | `orchestrator complete <id>` to force-complete |

### Debug Mode

```bash
# Full stack trace on error
orchestrator start -f "My feature" --debug
orchestrator resume <session-id> --debug
```

### Log Files

Error logs: `~/.claude_orchestrator/logs/error_<session_id>_*.log`

### Health Check

```bash
orchestrator check -v
```

Validates:
1. Dependencies installed
2. Database permissions
3. Authentication configured
4. API connection working

---

## Best Practices

### Plan Design

| DO | DON'T |
|----|-------|
| Keep milestones focused (2-4 hours work) | Create 10+ milestones |
| Include test requirements in each milestone | Leave testing to final milestone |
| Specify file paths and patterns | Be vague about deliverables |
| Use parseable milestone headers | Use creative header formats |

### Workflow Management

| DO | DON'T |
|----|-------|
| Use `--plan` for pre-written plans | Always rely on discovery phase |
| Use queue mode for multiple features | Start sessions manually one by one |
| Enable `--telegram` for long-running tasks | Check status manually every hour |
| Use `--auto-commit` for clean history | Forget to commit after completion |

### Recovery

| Scenario | Action |
|----------|--------|
| Workflow paused on blocker | `orchestrator respond <id> "answer"` |
| Session crashed mid-execution | `orchestrator resume <id>` |
| Session orphaned (no heartbeat) | `orchestrator reset <id>` then `resume --force` |
| Work done but milestone count wrong | `orchestrator complete <id>` |

---

## CLI Reference

See `CLAUDE_orch_v2_ref.md` for complete command reference.

```bash
orchestrator --help
orchestrator <command> --help
```

---

## Version History

| Version | Key Features |
|---------|--------------|
| v0.10.x | Error handling, per-session logging |
| v0.9.x | Auth detection, health check, force-complete |
| v0.8.x | Smart auto-commit with secrets detection |
| v0.7.x | Plan queue, feature extraction |
| v0.6.x | Telegram two-way, project scoping |
| v0.5.x | Telegram notifications, heartbeat |
| v0.4.x | Model selection, auto-commit |
| v0.3.x | Conversation continuity, multi-line input |
| v0.2.x | Plan import, activity indicator |
| v0.1.x | Initial two-agent orchestration |

---

## Related

- [orchestrator-auto README](orchestrator-auto/README.md) - Full CLI documentation
- [CLAUDE_orchestrator.md](CLAUDE_orchestrator.md) - Manual two-session workflow (v1)
