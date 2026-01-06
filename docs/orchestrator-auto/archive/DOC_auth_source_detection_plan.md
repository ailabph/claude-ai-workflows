# Auth Source Detection - Implementation Plan (v2)

## 1. Overview

Add the ability for orchestrator-auto to detect and display which authentication method is being used to access Claude. This provides transparency about billing source and helps users avoid unexpected charges.

**Key Design Principle:** Be conservative and accurate rather than assertive and wrong. Report what we can detect with confidence, and use neutral messaging for ambiguous situations.

## 2. Feature Specification

### 2.1 Feature Details

| Property | Value |
|----------|-------|
| **Module** | `orchestrator_auto/auth.py` (new) |
| **Integration Points** | `cli.py`, `engine.py`, `db.py` |
| **Dependencies** | None (uses stdlib only) |
| **Detection Strategy** | Multi-signal (env vars + credentials file + optional CLI probe) |

### 2.2 User Stories

- As a user, I can see which auth method is detected at startup so I know how I'll be billed
- As a user, I get a neutral warning if multiple auth sources are detected (not asserting priority)
- As a user, I see "Unknown" rather than false "No auth configured" when detection is inconclusive
- As a user, I can see the auth method used in session history for auditing

### 2.3 Detection Strategy (Multi-Signal)

**Primary Detection (Environment Variables):**

| Source | Detection | Confidence |
|--------|-----------|------------|
| **API Key** | `ANTHROPIC_API_KEY` is set | High |
| **OAuth Token (env)** | `CLAUDE_CODE_OAUTH_TOKEN` is set | High |
| **AWS Bedrock** | `CLAUDE_CODE_USE_BEDROCK=1` | High |
| **Google Vertex** | `CLAUDE_CODE_USE_VERTEX=1` | High |
| **Azure Foundry** | `CLAUDE_CODE_USE_FOUNDRY=1` | High |

**Secondary Detection (Credentials File - Linux only):**

| Source | Detection | Confidence |
|--------|-----------|------------|
| **OAuth (credentials)** | `~/.claude/.credentials.json` exists with `claudeAiOauth` key | Medium (best-effort, format not guaranteed) |

**Important Limitations:**
- macOS stores credentials in encrypted Keychain - we cannot read this
- No reliable CLI command exists to query auth status (as of Claude Code 2.0.76)
- We do NOT assert priority order - Claude Code's internal precedence may differ
- Credentials file format is speculative - errors must be silent

### 2.4 Key Prefix Detection (Informational Only)

Used only for display hints, NOT for determining auth source:

| Prefix | Suggests |
|--------|----------|
| `sk-ant-api...` | API key format |
| `sk-ant-oat01-...` | OAuth token format |

**Note:** Users can set OAuth-format tokens in `ANTHROPIC_API_KEY`. We report the env var name, not what we infer from prefix.

### 2.5 CLI Output

**Single auth source detected:**
```
Auth: ANTHROPIC_API_KEY (sk-ant-api03-...)
```
```
Auth: CLAUDE_CODE_OAUTH_TOKEN (sk-ant-oat01-...)
```
```
Auth: AWS Bedrock (CLAUDE_CODE_USE_BEDROCK)
```
```
Auth: Credentials file (~/.claude/.credentials.json)
```

**Multiple auth sources detected (neutral warning):**
```
⚠ Multiple auth sources detected:
  - ANTHROPIC_API_KEY (sk-ant-api03-...)
  - CLAUDE_CODE_OAUTH_TOKEN (sk-ant-oat01-...)
  Claude Code will choose one. Consider unsetting one to avoid ambiguity.
```

**No env vars but credentials file exists:**
```
Auth: Credentials file (~/.claude/.credentials.json)
  Note: No env vars set.
```

**Nothing detected (conservative):**
```
Auth: Unknown (no env vars detected)
  Note: Claude Code may still authenticate via keychain or other methods.
  If this fails, set ANTHROPIC_API_KEY or run 'claude setup-token'.
```

## 3. Architecture

### 3.1 File Structure

```
orchestrator_auto/
├── auth.py              # NEW: Auth detection module
├── cli.py               # MODIFY: Display auth at startup
├── engine.py            # MODIFY: Store auth in session
├── db.py                # MODIFY: Add auth columns
└── tests/
    └── test_auth.py     # NEW: Auth detection tests
```

### 3.2 Patterns to Follow

- Config detection: `orchestrator_auto/config.py::get_telegram_config()`
- CLI output: `orchestrator_auto/cli.py::start_workflow()` startup block
- DB schema migration: `orchestrator_auto/db.py::init_db()` (line 49)

## 4. Implementation Details

### 4.1 Auth Module (`auth.py`)

```python
"""Authentication source detection for orchestrator-auto."""
import os
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List


class AuthSource(Enum):
    """Authentication sources supported by Claude SDK."""
    API_KEY = "api_key"           # ANTHROPIC_API_KEY env var
    OAUTH_TOKEN = "oauth_token"   # CLAUDE_CODE_OAUTH_TOKEN env var
    CREDENTIALS_FILE = "credentials_file"  # ~/.claude/.credentials.json
    BEDROCK = "bedrock"           # AWS Bedrock
    VERTEX = "vertex"             # Google Vertex AI
    FOUNDRY = "foundry"           # Azure Foundry
    MULTIPLE = "multiple"         # Multiple sources detected (sentinel)
    UNKNOWN = "unknown"           # No detection possible


@dataclass
class AuthSignal:
    """A single detected authentication signal."""
    source: AuthSource
    env_var: Optional[str] = None
    file_path: Optional[str] = None
    key_hint: Optional[str] = None  # Masked first chars (for display only)


@dataclass
class AuthInfo:
    """Authentication detection result."""
    signals: List[AuthSignal] = field(default_factory=list)
    detected_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def auth_source_for_db(self) -> str:
        """
        Return auth source value for database storage.

        - If exactly one signal: return that source's value
        - If multiple signals: return "multiple" (we don't pick a winner)
        - If no signals: return "unknown"
        """
        if len(self.signals) == 0:
            return AuthSource.UNKNOWN.value
        if len(self.signals) == 1:
            return self.signals[0].source.value
        return AuthSource.MULTIPLE.value

    @property
    def is_configured(self) -> bool:
        """True if any auth signal detected."""
        return len(self.signals) > 0

    @property
    def has_multiple(self) -> bool:
        """True if multiple auth sources detected."""
        return len(self.signals) > 1

    def to_db_dict(self) -> dict:
        """Return dict for database storage. Does NOT store sensitive key hints."""
        return {
            "auth_source": self.auth_source_for_db,
            "auth_signals": json.dumps([s.source.value for s in self.signals]),
            "auth_detected_at": self.detected_at.isoformat(),
        }


def detect_auth(check_credentials_file: bool = True) -> AuthInfo:
    """
    Detect authentication sources from environment and filesystem.

    Args:
        check_credentials_file: Check ~/.claude/.credentials.json (Linux only)

    Returns:
        AuthInfo with all detected signals (may be empty)

    Note:
        Detection order is deterministic but does NOT imply priority.
        Claude Code's actual runtime selection may differ.
    """
    signals = []

    # 1. Check cloud provider env vars
    if os.environ.get("CLAUDE_CODE_USE_BEDROCK") == "1":
        signals.append(AuthSignal(AuthSource.BEDROCK, env_var="CLAUDE_CODE_USE_BEDROCK"))

    if os.environ.get("CLAUDE_CODE_USE_VERTEX") == "1":
        signals.append(AuthSignal(AuthSource.VERTEX, env_var="CLAUDE_CODE_USE_VERTEX"))

    if os.environ.get("CLAUDE_CODE_USE_FOUNDRY") == "1":
        signals.append(AuthSignal(AuthSource.FOUNDRY, env_var="CLAUDE_CODE_USE_FOUNDRY"))

    # 2. Check API key env var
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        signals.append(AuthSignal(
            AuthSource.API_KEY,
            env_var="ANTHROPIC_API_KEY",
            key_hint=mask_key(api_key),
        ))

    # 3. Check OAuth token env var
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if oauth_token:
        signals.append(AuthSignal(
            AuthSource.OAUTH_TOKEN,
            env_var="CLAUDE_CODE_OAUTH_TOKEN",
            key_hint=mask_key(oauth_token),
        ))

    # 4. Check credentials file (Linux/Ubuntu - macOS uses Keychain)
    if check_credentials_file:
        creds_signal = _check_credentials_file()
        if creds_signal:
            signals.append(creds_signal)

    return AuthInfo(signals=signals)


def _check_credentials_file() -> Optional[AuthSignal]:
    """
    Check for ~/.claude/.credentials.json with OAuth tokens.

    Best-effort detection - file format is not guaranteed stable.
    All errors are silently ignored.
    """
    creds_path = Path.home() / ".claude" / ".credentials.json"

    if not creds_path.exists():
        return None

    try:
        with open(creds_path, "r") as f:
            data = json.load(f)

        if "claudeAiOauth" in data:
            return AuthSignal(
                AuthSource.CREDENTIALS_FILE,
                file_path=str(creds_path),
            )
    except (json.JSONDecodeError, IOError, PermissionError, OSError):
        # Silent failure - this is best-effort detection
        pass

    return None


def mask_key(key: str, visible_chars: int = 12) -> str:
    """Mask API key/token for safe display."""
    if not key or len(key) <= visible_chars:
        return "***"
    return key[:visible_chars] + "..."


def format_auth_display(auth_info: AuthInfo) -> str:
    """Format auth info for CLI display. Shows env var name + masked key hint."""
    if not auth_info.is_configured:
        return (
            "Auth: Unknown (no env vars detected)\n"
            "  Note: Claude Code may still authenticate via keychain or other methods.\n"
            "  If this fails, set ANTHROPIC_API_KEY or run 'claude setup-token'."
        )

    if auth_info.has_multiple:
        lines = ["⚠ Multiple auth sources detected:"]
        for signal in auth_info.signals:
            if signal.env_var and signal.key_hint:
                lines.append(f"  - {signal.env_var} ({signal.key_hint})")
            elif signal.env_var:
                lines.append(f"  - {signal.env_var}")
            elif signal.file_path:
                lines.append(f"  - {signal.file_path}")
        lines.append("  Claude Code will choose one. Consider unsetting one to avoid ambiguity.")
        return "\n".join(lines)

    # Single source - format: "Auth: ENV_VAR_NAME (masked_hint)"
    signal = auth_info.signals[0]

    if signal.source == AuthSource.API_KEY:
        hint = f" ({signal.key_hint})" if signal.key_hint else ""
        return f"Auth: {signal.env_var}{hint}"

    if signal.source == AuthSource.OAUTH_TOKEN:
        hint = f" ({signal.key_hint})" if signal.key_hint else ""
        return f"Auth: {signal.env_var}{hint}"

    if signal.source == AuthSource.CREDENTIALS_FILE:
        return f"Auth: Credentials file ({signal.file_path})"

    if signal.source == AuthSource.BEDROCK:
        return f"Auth: AWS Bedrock ({signal.env_var})"

    if signal.source == AuthSource.VERTEX:
        return f"Auth: Google Vertex AI ({signal.env_var})"

    if signal.source == AuthSource.FOUNDRY:
        return f"Auth: Azure Foundry ({signal.env_var})"

    return f"Auth: {signal.source.value}"
```

### 4.2 Database Schema Changes

Add to `init_db()` in `db.py`:

```python
# Add auth tracking columns if they don't exist
for column, col_type in [
    ("auth_source", "TEXT"),
    ("auth_signals", "TEXT"),  # JSON array of detected sources
    ("auth_detected_at", "TIMESTAMP"),
]:
    try:
        cursor.execute(f"ALTER TABLE sessions ADD COLUMN {column} {col_type}")
    except sqlite3.OperationalError:
        pass  # Column already exists
```

### 4.3 CLI Integration

In `cli.py`, add to startup output:

```python
from .auth import detect_auth, format_auth_display

# At startup (start_workflow, resume_workflow, chat_command)
auth_info = detect_auth()
click.echo(format_auth_display(auth_info))
```

## 5. Milestones

### Milestone 1: Core Auth Detection Module

**Deliverables:**
- [ ] Create `orchestrator_auto/auth.py` with:
  - [ ] `AuthSource` enum (8 values: API_KEY, OAUTH_TOKEN, CREDENTIALS_FILE, BEDROCK, VERTEX, FOUNDRY, MULTIPLE, UNKNOWN)
  - [ ] `AuthSignal` dataclass
  - [ ] `AuthInfo` dataclass with `auth_source_for_db`, `has_multiple`, `to_db_dict()`
  - [ ] `detect_auth()` function (env vars + credentials file)
  - [ ] `_check_credentials_file()` helper (silent errors)
  - [ ] `mask_key()` helper
  - [ ] `format_auth_display()` formatter
- [ ] Create `tests/test_auth.py` with:
  - [ ] Test each env var detection individually
  - [ ] Test credentials file detection (mock file)
  - [ ] Test multiple signals detected (has_multiple=True, auth_source_for_db="multiple")
  - [ ] Test no signals detected (returns UNKNOWN, not error)
  - [ ] Test key masking edge cases
  - [ ] Test format_auth_display() for all scenarios
  - [ ] Test credentials file with PermissionError (silent failure)

**Key References:**
- Pattern: `config.py::get_telegram_config()` for env var detection
- Credentials path: `~/.claude/.credentials.json`

**Tests Required:**
```bash
pytest tests/test_auth.py -v
```

**Acceptance Criteria:**
- All 6 auth sources correctly detected from env vars
- Credentials file detection works on Linux (gracefully skipped if not exists)
- Multiple signals returned when multiple sources set (no false priority assertion)
- No false "not configured" when we simply can't detect
- Tests pass with >90% coverage on auth.py

---

### Milestone 2: CLI Integration

**Prerequisites:**
- Milestone 1 approved

**Deliverables:**
- [ ] Modify `cli.py`:
  - [ ] Import auth module
  - [ ] Add auth display to `start_workflow()` after "Starting new workflow session..."
  - [ ] Add auth display to `resume_workflow()` at startup
  - [ ] Add auth display to `chat_command()` at startup
  - [ ] Use yellow color for conflict/unknown warnings

**Key References:**
- Location: `cli.py` startup output sections
- Pattern: Existing click.echo/click.secho usage

**Manual Verification:**
```bash
# Test with API key
ANTHROPIC_API_KEY=sk-ant-api03-test orchestrator start -f "test" --help

# Test with OAuth token
CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-test orchestrator list

# Test with both (conflict)
ANTHROPIC_API_KEY=sk-ant-api03-test CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-test orchestrator list

# Test with nothing (should say Unknown, not "no auth configured")
unset ANTHROPIC_API_KEY CLAUDE_CODE_OAUTH_TOKEN && orchestrator list
```

**Acceptance Criteria:**
- Auth source displayed on every `start`, `resume`, `chat` command
- Conflict warning shown in yellow when multiple auth sources detected
- "Unknown" shown when no env vars detected (not false "no auth")
- No breaking changes to existing CLI behavior

---

### Milestone 3: Database & Session Tracking

**Prerequisites:**
- Milestone 2 approved

**Deliverables:**
- [ ] Modify `db.py`:
  - [ ] Add `auth_source`, `auth_signals`, `auth_detected_at` columns to sessions table
  - [ ] Handle migration for existing databases (nullable columns)
  - [ ] Update `create_session()` to accept auth_info dict
- [ ] Modify `engine.py`:
  - [ ] Import and call `detect_auth()` in `__init__` or session creation
  - [ ] Pass `auth_info.to_db_dict()` to `create_session()`
- [ ] Update `status` command to show auth_source from DB
- [ ] Update `export` command to include auth info in markdown

**Key References:**
- Schema migration pattern: `db.py::init_db()` (line 49)
- Session creation: `db.py::create_session()`
- Engine init: `engine.py::Orchestrator.__init__()`

**Tests Required:**
```bash
pytest tests/test_db.py -v
pytest tests/test_engine.py -v
```

**Acceptance Criteria:**
- Existing databases continue to work (migration handles NULL)
- New sessions store auth_source, auth_signals, auth_detected_at
- `orchestrator status <id>` shows auth method used for that session
- Session export includes auth method

---

### Milestone 4: Testing & Documentation

**Prerequisites:**
- Milestone 3 approved

**Deliverables:**
- [ ] Add integration tests:
  - [ ] Test full workflow with mocked env vars
  - [ ] Test session creation stores auth correctly
  - [ ] Test no env vars does NOT incorrectly claim "no auth"
  - [ ] Test credentials file detection when file exists
- [ ] Update `README.md`:
  - [ ] Add "Auth Source Detection" to feature list in TODO section (mark complete)
  - [ ] Add section explaining auth display under Configuration
  - [ ] Document detected sources and limitations
  - [ ] Update changelog with new version entry
- [ ] Run full test suite and verify coverage

**Tests Required:**
```bash
pytest tests/ -v --cov=orchestrator_auto --cov-report=term-missing
```

**Acceptance Criteria:**
- All tests pass
- Coverage remains >80% overall
- README documents the new feature including limitations
- Changelog updated

---

## 6. Testing Strategy

### 6.1 Unit Tests (auth.py)

| Test | Description |
|------|-------------|
| `test_detect_api_key_only` | API key detected when only ANTHROPIC_API_KEY set |
| `test_detect_oauth_token_only` | OAuth detected when only CLAUDE_CODE_OAUTH_TOKEN set |
| `test_detect_bedrock` | Bedrock detected when USE_BEDROCK=1 |
| `test_detect_vertex` | Vertex detected when USE_VERTEX=1 |
| `test_detect_foundry` | Foundry detected when USE_FOUNDRY=1 |
| `test_detect_multiple_signals` | Multiple signals returned when API key + OAuth both set |
| `test_detect_none_returns_unknown` | Returns UNKNOWN (not error) when nothing set |
| `test_credentials_file_detected` | Credentials file detected when exists with claudeAiOauth |
| `test_credentials_file_missing` | No signal when credentials file doesn't exist |
| `test_credentials_file_invalid_json` | No signal when credentials file has invalid JSON |
| `test_mask_key_short` | Short keys return "***" |
| `test_mask_key_long` | Long keys masked after 12 chars |
| `test_format_single_api_key` | Display format for single API key |
| `test_format_single_oauth` | Display format for single OAuth token |
| `test_format_multiple` | Display format for multiple sources |
| `test_format_unknown` | Display format for no detection (neutral message) |
| `test_has_multiple_property` | has_multiple returns True for multiple signals |
| `test_auth_source_for_db_single` | Returns source value when exactly one signal |
| `test_auth_source_for_db_multiple` | Returns "multiple" when multiple signals |
| `test_to_db_dict` | Database dict correctly formatted (no sensitive data) |
| `test_credentials_file_permission_error` | Silent failure on PermissionError |

### 6.2 Integration Tests

| Test | Description |
|------|-------------|
| `test_cli_shows_auth_on_start` | CLI startup displays auth info |
| `test_session_stores_auth` | Session DB records auth_source and auth_detected_at |
| `test_status_shows_auth` | Status command shows auth from DB |
| `test_export_includes_auth` | Exported markdown includes auth |
| `test_no_false_negative` | No env vars doesn't claim "no auth configured" |

### 6.3 Coverage Targets

| Component | Target |
|-----------|--------|
| `auth.py` | 95% |
| `cli.py` changes | 80% |
| `db.py` changes | 85% |
| `engine.py` changes | 80% |

## 7. Security Considerations

- [ ] Never log full API keys or tokens
- [ ] Mask keys to show only first 12 characters (for CLI display only)
- [ ] Don't store keys or masked hints in database (only source type: "api_key", "multiple", etc.)
- [ ] Warnings don't expose key values
- [ ] Credentials file read is read-only, fail gracefully on permission errors

## 8. Known Limitations

| Limitation | Mitigation |
|------------|------------|
| macOS Keychain not readable | Show "Unknown" instead of false negative |
| No CLI command to query auth status | Rely on env vars and credentials file only |
| Can't determine Claude Code's actual priority | Neutral messaging, store "multiple" in DB |
| OAuth token in ANTHROPIC_API_KEY | Report env var name, not inferred type |
| Credentials file format is speculative | Best-effort detection, silent failures |
| Credentials file expires (~6 hours) | Detection is point-in-time, may not reflect runtime |

## 9. Anti-Patterns

### Don't: Assert priority we can't verify
```python
# BAD
if api_key and oauth_token:
    return "Using: API Key (takes priority)"
```

### Do: Report neutrally
```python
# GOOD
if api_key and oauth_token:
    return "Multiple auth sources detected. Claude Code will choose one."
```

### Don't: Claim "no auth" when we can't be sure
```python
# BAD
if not api_key and not oauth_token:
    return "⚠ No authentication configured"
```

### Do: Acknowledge detection limits
```python
# GOOD
if not signals:
    return "Auth: Unknown (no env vars detected)\n  Note: Claude Code may still authenticate via keychain."
```

## 10. Rollback Strategy

| Milestone | Rollback Action |
|-----------|-----------------|
| M1 | Delete `auth.py` and `test_auth.py` |
| M2 | Revert CLI changes (git checkout cli.py) |
| M3 | Columns are nullable, no migration needed |
| M4 | Revert README/docs changes |

## 11. Git Checkpoints

| Milestone | Expected Commit |
|-----------|-----------------|
| M1 | `feat(auth): add auth source detection module` |
| M2 | `feat(cli): display auth source at startup` |
| M3 | `feat(db): track auth source in sessions` |
| M4 | `docs: add auth source detection documentation` |

---

## Quick Reference

| Resource | Path |
|----------|------|
| Implementation Plan | `docs/orchestrator-auto/DOC_auth_source_detection_plan.md` |
| Auth Module | `orchestrator_auto/auth.py` (to create) |
| CLI Integration | `orchestrator_auto/cli.py` |
| DB Schema | `orchestrator_auto/db.py::init_db()` (line 49) |
| Config Pattern | `orchestrator_auto/config.py::get_telegram_config()` |
| Credentials File | `~/.claude/.credentials.json` |

## References

- [Claude Code IAM Documentation](https://code.claude.com/docs/en/iam)
- [GitHub Issue #8002 - Auth status bug](https://github.com/anthropics/claude-code/issues/8002)
- [GitHub Issue #6536 - SDK OAuth support](https://github.com/anthropics/claude-code/issues/6536)
