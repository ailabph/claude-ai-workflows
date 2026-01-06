# Chat Dashboard Plugin

A Claude Code plugin that captures chat history via hooks and displays it on a web dashboard, enabling quick context recall when switching between projects.

**Official Reference:** [Claude Code Hooks Documentation](https://code.claude.com/docs/en/hooks)

## Problem

When managing multiple repositories, it's hard to remember the context when switching between workspaces. You often return to a Claude Code session and forget what the AI agent was responding to.

## Solution

A plugin that:
1. **Captures user messages** in real-time via `UserPromptSubmit` hook
2. **Generates AI summaries** when sessions end via `Stop` hook
3. **Displays history** on a searchable web dashboard

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     Claude Code Session                           │
├──────────────────────────────────────────────────────────────────┤
│  UserPromptSubmit Hook          │     Stop Hook                   │
│  ┌─────────────────────────┐    │  ┌───────────────────────────┐ │
│  │ Capture:                │    │  │ On session end:           │ │
│  │ - session_id            │    │  │ - Parse transcript_path   │ │
│  │ - prompt text           │    │  │ - Generate AI summary     │ │
│  │ - timestamp             │    │  │ - Store summary to DB     │ │
│  │ - project_id (cwd)      │    │  └───────────┬───────────────┘ │
│  └──────────┬──────────────┘    │              │                  │
└─────────────┼────────────────────┼──────────────┼──────────────────┘
              │                    │              │
              ▼                    │              ▼
        ┌─────────────────────────────────────────────┐
        │              SQLite Database                 │
        │  ~/.claude_orchestrator/chat_history.sqlite  │
        └────────────────────┬────────────────────────┘
                             │
                             ▼
        ┌─────────────────────────────────────────────┐
        │            FastAPI Web Server               │
        │            http://localhost:8765            │
        └────────────────────┬────────────────────────┘
                             │
                             ▼
        ┌─────────────────────────────────────────────┐
        │            HTML Dashboard UI                │
        │  - Project switcher                          │
        │  - Session list with summaries               │
        │  - Search functionality                      │
        │  - Session detail view                       │
        └─────────────────────────────────────────────┘
```

## File Structure

```
claude/chat-dashboard/
├── chat_dashboard/
│   ├── __init__.py
│   ├── hooks/
│   │   ├── __init__.py
│   │   ├── capture_prompt.py      # UserPromptSubmit hook
│   │   └── summarize_session.py   # Stop hook
│   ├── db.py                      # SQLite operations
│   ├── models.py                  # Dataclasses
│   ├── transcript.py              # JSONL parser
│   ├── summarizer.py              # AI summarization (Claude Haiku)
│   ├── server.py                  # FastAPI server
│   ├── config.py                  # Configuration
│   └── cli.py                     # CLI commands
├── static/
│   ├── style.css
│   └── app.js
├── templates/
│   └── index.html
└── pyproject.toml
```

## Database Schema

```sql
-- Projects (derived from cwd)
CREATE TABLE projects (
    id TEXT PRIMARY KEY,              -- Hash of project path
    path TEXT NOT NULL UNIQUE,        -- Absolute path to project
    name TEXT NOT NULL,               -- Display name (basename)
    git_remote TEXT,                  -- Git remote URL if available
    created_at TIMESTAMP,
    last_accessed_at TIMESTAMP
);

-- Chat sessions
CREATE TABLE chat_sessions (
    id TEXT PRIMARY KEY,              -- Claude session_id
    project_id TEXT NOT NULL,         -- FK to projects
    transcript_path TEXT,             -- Path to .jsonl transcript
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    message_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',     -- active, completed, abandoned
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- User messages (prompts only)
CREATE TABLE chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,               -- 'user'
    content TEXT NOT NULL,
    content_preview TEXT,             -- First 200 chars
    timestamp TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
);

-- AI-generated summaries
CREATE TABLE session_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL,            -- 1-3 sentence summary
    topics TEXT,                      -- JSON array of tags
    files_modified TEXT,              -- JSON array of files
    key_decisions TEXT,               -- JSON array of decisions
    model_used TEXT,                  -- Model for summarization
    generated_at TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
);
```

## Hook Configuration

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "python3 -m chat_dashboard.hooks.capture_prompt",
        "timeout": 5
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "python3 -m chat_dashboard.hooks.summarize_session",
        "timeout": 30
      }
    ]
  }
}
```

## Hook Input Format

Hooks receive JSON via stdin:

```json
{
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../session.jsonl",
  "cwd": "/path/to/project",
  "permission_mode": "default",
  "hook_event_name": "UserPromptSubmit",
  "prompt": "User's prompt text here"
}
```

**Common fields:**
- `session_id` - Unique session identifier
- `transcript_path` - Path to conversation transcript (JSONL)
- `cwd` - Current working directory (project path)
- `hook_event_name` - Which event triggered the hook

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/projects` | List projects with session counts |
| GET | `/api/sessions` | List sessions (filter by project, status) |
| GET | `/api/sessions/{id}` | Session detail with summary |
| GET | `/api/sessions/{id}/messages` | User messages for session |
| GET | `/api/search?q=...` | Search by summary/topics/content |
| GET | `/api/recent-context/{project_id}` | Recent context for hook injection |
| GET | `/` | Dashboard HTML |

## Summary Generation

The Stop hook generates summaries using Claude Haiku:

1. **Parse Transcript**: Read JSONL file to extract messages
2. **Extract Metadata**: Files modified, tools used
3. **Call Claude Haiku**: Generate concise summary with topics
4. **Store Result**: Save to `session_summaries` table
5. **Fallback**: Static summary if API unavailable

**Summary prompt asks for:**
- 1-3 sentence summary of what was accomplished
- 2-5 key topics/tags for filtering
- Major decisions or changes made

## Installation

```bash
# 1. Install the package
cd claude/chat-dashboard
pip install -e .

# 2. Initialize database
chat-dashboard init

# 3. Update Claude Code settings (add hooks)
# Edit ~/.claude/settings.json

# 4. Start the server
chat-dashboard serve --port 8765

# 5. Open dashboard
open http://localhost:8765
```

## CLI Commands

```bash
# Start web server
chat-dashboard serve [--host HOST] [--port PORT]

# Initialize database
chat-dashboard init

# Show statistics
chat-dashboard stats [--project-id ID] [--limit N]
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAT_DASHBOARD_DB_PATH` | `~/.claude_orchestrator/chat_history.sqlite` | Database path |
| `CHAT_DASHBOARD_HOST` | `127.0.0.1` | Server host |
| `CHAT_DASHBOARD_PORT` | `8765` | Server port |
| `CHAT_DASHBOARD_MODEL` | `claude-haiku-3-5-20241022` | Summary model |
| `ANTHROPIC_API_KEY` | (required for summaries) | Anthropic API key |

## Cloud Deployment

For future cloud deployment:

1. **Database**: Migrate SQLite to PostgreSQL
2. **Authentication**: Add OAuth or API key auth
3. **Storage**: Store transcripts in S3/GCS
4. **Deployment**: Docker container with gunicorn/uvicorn
5. **HTTPS**: TLS via nginx or cloud load balancer

## Dashboard Features

- **Project Switcher**: Filter sessions by project
- **Session List**: Recent sessions with summaries and topics
- **Search**: Full-text search across summaries, topics, messages
- **Session Detail**: Full summary, files modified, key decisions, message timeline
- **Responsive**: Works on desktop and mobile

## Dependencies

```toml
[project]
dependencies = [
    "fastapi>=0.100",
    "uvicorn>=0.20",
    "anthropic>=0.20",
]
```

## Related

- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks)
- [orchestrator-auto](../orchestrator-auto/) - Two-agent workflow orchestration
