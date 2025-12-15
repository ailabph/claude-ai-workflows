# Orchestrator Auto: Automated Two-Agent Workflow

## Status: DRAFT

---

## Problem Statement

Current manual workflow for using `CLAUDE_orchestrator.md`:

1. Open Claude session 1 → read orchestrator.md → assign as Planner/Validator
2. Discuss idea until clear (discovery phase)
3. Planner creates plan → generates executor prompt
4. Open Claude session 2 → read orchestrator.md → assign as Executor → paste prompt
5. Manually copy-paste back and forth between the two agents
6. Repeat until all milestones complete

**Pain points:**
- Manual copy-paste is tedious and error-prone
- Context can be lost if `/compact` triggers
- No persistent memory of decisions, plans, progress

---

## Proposed Solution

A Python script using the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) that:

1. Automates the back-and-forth between Planner and Executor agents
2. Stores all plans, prompts, responses in SQLite for persistence
3. Pre-emptively triggers `/compact` with recovery prompts when context is low (~10%)
4. Pauses for human input only when Planner is blocked
5. Maintains drop-in portability (just copy files to any project)

---

## Three-Phase Workflow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────────────────┐
│  1. DISCOVERY   │ ──► │  2. PLANNING    │ ──► │  3. EXECUTION               │
│  (Open chat)    │     │  (Create plan)  │     │  (Milestone loop)           │
├─────────────────┤     ├─────────────────┤     ├─────────────────────────────┤
│ Discuss idea    │     │ Read orchestrator│    │ Planner ↔ Executor          │
│ Clarify scope   │     │ Create plan.md  │     │ Auto milestone progression  │
│ Explore options │     │ Define milestones│    │ Human gate on Planner block │
│ Find approach   │     │ Gen executor prompt│  │                             │
│                 │     │                 │     │                             │
│ User: "/ready" ─┼────►│                 │     │                             │
└─────────────────┘     └─────────────────┘     └─────────────────────────────┘
```

### Phase 1: Discovery
- Open-ended conversation with single agent
- User discusses idea, clarifies scope, explores options
- User types `/ready` when satisfied to transition
- All messages stored in SQL

### Phase 2: Planning
- Same agent transitions to Planner role
- Reads `CLAUDE_orchestrator.md`
- Creates implementation plan (`docs/[feature]/DOC_[feature]_plan.md`)
- Defines milestones with clear deliverables
- Generates executor prompt for Milestone 1
- User confirms to start execution

### Phase 3: Execution
- Executor agent spawned (fresh context)
- Receives prompt from Planner
- Works on milestone → generates progress report → STOPS
- Script routes report to Planner for validation
- **Auto-continue**: If Planner approves, script sends next milestone to Executor
- **Human gate**: If Planner is blocked/needs clarification, script pauses for human
- Repeat until all milestones complete

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CLI (Human Interface)                           │
│  • Start: python orchestrator_auto.py --feature "description"           │
│  • Resume: python orchestrator_auto.py --resume <session_id>            │
│  • Respond: python orchestrator_auto.py --respond "answer"              │
│  • List: python orchestrator_auto.py --list                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Orchestrator Engine                                │
│  • Manages agent lifecycle (create, persist, compact)                   │
│  • Routes messages: Discovery → Planning → Execution                    │
│  • Parses responses for: approval, blocker, clarification               │
│  • Monitors context usage (~10% remaining → trigger compact)            │
│  • Pauses for human only when Planner is blocked                        │
└─────────────────────────────────────────────────────────────────────────┘
            │                       │                       │
            ▼                       ▼                       ▼
┌───────────────────┐   ┌───────────────────┐   ┌─────────────────────────┐
│ Discovery/Planner │   │  Executor Agent   │   │   SQLite Memory Store   │
│     Agent         │   │   (Persistent)    │   │  .claude_orchestrator/  │
│   (Persistent)    │   │                   │   │  └── orchestrator.db    │
│                   │   │                   │   │                         │
│ Phases 1 & 2      │   │ Phase 3 only      │   │  Tables:                │
│ Context: ████░    │   │ Context: ███░░    │   │  • sessions             │
│                   │   │                   │   │  • messages             │
│ ~10% = compact    │   │ ~10% = compact    │   │  • plans                │
│ with SQL recovery │   │ with SQL recovery │   │  • milestones           │
└───────────────────┘   └───────────────────┘   │  • agent_state          │
                                                └─────────────────────────┘
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Database** | SQLite | File-based, portable, no server needed |
| **Approval model** | Auto-continue on Planner approval | Reduces human intervention |
| **Human gate** | Only when Planner blocked | Executor clarifications go to Planner first |
| **Agent lifecycle** | Persistent with proactive compact | Preserve context, recover from SQL |
| **Context threshold** | ~10% remaining triggers compact | Pre-emptive, not reactive |
| **Portability** | Drop-in files, no global install | Copy to any project and use |

---

## Drop-in File Structure

```
your-project/
├── CLAUDE_orchestrator.md              # Existing workflow doc (unchanged)
├── CLAUDE_orchestrator_auto.py         # New: main automation script
├── .claude_orchestrator/               # New: runtime data (gitignore)
│   ├── orchestrator.db                 # SQLite database
│   └── logs/                           # Session logs
└── requirements.txt                    # Dependencies (claude-agent-sdk, etc.)
```

---

## Database Schema (Draft)

```sql
-- Workflow sessions
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    feature_description TEXT,
    phase TEXT,  -- 'discovery', 'planning', 'execution'
    status TEXT, -- 'active', 'paused', 'completed', 'failed'
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- All messages (for recovery)
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    phase TEXT,
    agent TEXT,  -- 'discovery', 'planner', 'executor', 'human'
    role TEXT,   -- 'user', 'assistant'
    content TEXT,
    created_at TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Implementation plans
CREATE TABLE plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    file_path TEXT,
    content TEXT,
    created_at TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Milestone tracking
CREATE TABLE milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    milestone_number INTEGER,
    name TEXT,
    status TEXT,  -- 'pending', 'in_progress', 'approved', 'rejected'
    executor_report TEXT,
    planner_feedback TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Agent state (for compact recovery)
CREATE TABLE agent_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    agent TEXT,
    context_summary TEXT,
    key_decisions TEXT,  -- JSON array
    current_task TEXT,
    created_at TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

---

## CLI Commands (Draft)

```bash
# Start new session
python orchestrator_auto.py --feature "user activity logging for admins"

# Resume existing session
python orchestrator_auto.py --resume abc123

# Respond to blocker (when paused for human input)
python orchestrator_auto.py --respond "Use JWT tokens, not sessions"

# List all sessions
python orchestrator_auto.py --list

# Show session status
python orchestrator_auto.py --status abc123

# Export session history
python orchestrator_auto.py --export abc123 --output session_log.md
```

---

## Context Recovery (Compact Handling)

When agent context reaches ~10%:

1. Script detects low context
2. Generates recovery prompt from SQL:
   ```
   Context was compacted. Here's your recovery state:

   ## Session: [feature_description]
   ## Current Phase: [execution]
   ## Current Milestone: [3 of 5]

   ## Approved Milestones:
   - M1: Serializers (approved)
   - M2: Service layer (approved)

   ## Key Decisions Made:
   - Using pagination with cursor-based approach
   - JWT auth required for all endpoints

   ## Current Task:
   Working on M3: View + Routes

   ## Last Message:
   [executor's last progress report]

   Continue from where you left off.
   ```
3. Sends recovery prompt as compact custom prompt
4. Agent continues with restored context

---

## SDK Research Findings (2025-12-15)

### SDK Version
- **Package**: `claude-agent-sdk` v0.1.16 (Dec 13, 2025)
- **Python**: >=3.10
- **License**: MIT
- **Note**: Claude Code CLI is bundled - no separate install needed

### Key APIs Available

| Feature | API | Notes |
|---------|-----|-------|
| **Simple queries** | `query(prompt, options)` | Async iterator of messages |
| **Interactive sessions** | `ClaudeSDKClient` | Bidirectional, persistent |
| **Session management** | `session_id`, `resume`, `continue_conversation` | Built-in persistence |
| **Token tracking** | `ResultMessage.usage`, `total_cost_usd` | Monitor consumption |
| **PreCompact hook** | `HookEvent = "PreCompact"` | Intercept before compaction |
| **Custom tools** | `@tool` decorator + MCP servers | In-process, no subprocess |
| **Multi-agent** | Multiple `ClaudeSDKClient` instances | Independent sessions |

### ClaudeAgentOptions (Key Fields)

```python
@dataclass
class ClaudeAgentOptions:
    system_prompt: str | None = None
    max_turns: int | None = None
    allowed_tools: list[str] | None = None
    permission_mode: str | None = None  # 'acceptEdits'
    cwd: str | Path | None = None
    continue_conversation: bool = False
    resume: str | None = None           # Resume from session_id
    fork_session: bool = False          # Fork to new session on resume
    max_thinking_tokens: int | None = None
    hooks: dict[str, list[HookMatcher]] = None
```

### ResultMessage (Token/Cost Tracking)

```python
@dataclass
class ResultMessage:
    session_id: str
    num_turns: int
    total_cost_usd: float | None = None
    usage: dict[str, Any] | None = None  # Token counts here
    duration_ms: int
    is_error: bool
```

### Hook System

```python
HookEvent = "PreToolUse" | "PostToolUse" | "UserPromptSubmit" | "Stop" | "SubagentStop" | "PreCompact"

# Hook callback signature
async def my_hook(input_data, tool_use_id, context) -> HookJSONOutput:
    return {
        "additionalContext": "Injected context",
        "permissionDecision": "allow",  # or "deny"
    }

# Registration
options = ClaudeAgentOptions(
    hooks={
        "PreCompact": [HookMatcher(matcher="*", hooks=[compact_recovery_hook])],
    }
)
```

### Multi-Agent Pattern

```python
# Two independent agents
async with ClaudeSDKClient(options=planner_options) as planner:
    async with ClaudeSDKClient(options=executor_options) as executor:
        # Route messages between them
        pass
```

---

## Implementation Approach (Updated)

### Context Recovery via PreCompact Hook

```python
async def compact_recovery_hook(input_data, tool_use_id, context):
    """Intercept before compaction, inject SQL-based recovery context."""
    session_id = input_data["session_id"]

    # Generate recovery prompt from SQL
    recovery = generate_recovery_prompt(session_id)

    return {
        "additionalContext": recovery,
    }
```

### Token Monitoring

```python
async for message in client.receive_response():
    if isinstance(message, ResultMessage):
        usage = message.usage
        # Check if approaching context limit
        # Trigger proactive compact if needed
```

### Response Parsing Strategy

Use structured patterns in prompts to make parsing reliable:

```python
# In planner system prompt
"""
When approving a milestone, respond with:
[MILESTONE_APPROVED] Milestone N approved. Proceed to Milestone N+1.

When blocked, respond with:
[HUMAN_INPUT_NEEDED] Description of what you need from the human.
"""

# Parser
def parse_planner_response(content: str) -> tuple[str, dict]:
    if "[MILESTONE_APPROVED]" in content:
        return "approved", extract_milestone_num(content)
    elif "[HUMAN_INPUT_NEEDED]" in content:
        return "blocked", extract_question(content)
    # etc.
```

---

## Remaining Questions

1. **PreCompact hook behavior**: Can we inject a custom compact prompt, or just add context?
2. **Token limit detection**: Is there a way to know context limit before hitting it?
3. **Session file location**: Where does SDK store session data for `resume`?

---

## Next Steps

1. [x] Research Claude Agent SDK - understand available APIs
2. [ ] Create detailed implementation plan with milestones
3. [ ] Implement core orchestrator engine
4. [ ] Add SQLite persistence layer
5. [ ] Implement context monitoring and recovery
6. [ ] Build CLI interface
7. [ ] Test end-to-end with real workflow

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2025-12-15 | Initial draft from discussion |
| 0.2 | 2025-12-15 | Added SDK research findings, updated implementation approach |
