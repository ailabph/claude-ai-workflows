# Smart Auto-Commit - Implementation Plan

## 1. Overview

Improve the auto-commit feature to use AI (Claude) to analyze actual code changes and generate meaningful commit messages following Conventional Commits format. Includes secrets detection to block sensitive data from being sent to the API.

## 2. Feature Specification

### 2.1 Feature Details

| Property | Value |
|----------|-------|
| **Module** | `orchestrator_auto/git.py` (enhanced) |
| **New Modules** | `orchestrator_auto/secrets.py`, `orchestrator_auto/commit_ai.py` |
| **API Client** | `claude-agent-sdk` (existing dependency) |
| **Model** | `claude-haiku-3-5-20241022` |
| **Config** | `auto_commit.smart: true/false` |
| **CLI Flag** | `--no-smart-commit` |

### 2.2 Requirements

- Generate commit messages based on actual `git diff` content
- Follow **Conventional Commits** format (`feat:`, `fix:`, `refactor:`, etc.)
- **No Claude/AI attribution** in commit messages
- **Never auto-push** to remote
- **Block on secrets** - skip AI if diff contains likely secrets patterns
- Graceful fallback to static message on any error

### 2.3 Commit Message Format

```
<type>: <description>

- bullet point for significant change
- another bullet point
```

| Type | When to Use |
|------|-------------|
| `feat` | New user-visible functionality |
| `fix` | Bug correction |
| `refactor` | Code restructuring (no behavior change) |
| `docs` | Documentation only |
| `test` | Test files only |
| `chore` | Config, build, dependencies |
| `style` | Formatting only |
| `perf` | Performance optimization |

## 3. Architecture

### 3.1 File Structure

```
orchestrator_auto/
├── git.py              # Add diff functions, update auto_commit()
├── secrets.py          # NEW - secrets pattern detection
├── commit_ai.py        # NEW - AI message generation
├── config.py           # Add get_smart_commit_enabled()
└── cli.py              # Add --no-smart-commit flag
tests/
├── test_git.py         # Add diff function tests
├── test_secrets.py     # NEW - secrets detection tests
└── test_commit_ai.py   # NEW - AI generation tests
```

### 3.2 Patterns to Follow

| Component | Reference |
|-----------|-----------|
| ClaudeSDKClient usage | `orchestrator_auto/agents.py:78-96` |
| Config loading | `orchestrator_auto/config.py:get_telegram_config()` |
| CLI flags | `orchestrator_auto/cli.py:795` (`--auto-commit`) |

## 4. Implementation Details

### 4.1 Secrets Detection (`secrets.py`)

```python
from dataclasses import dataclass
import re

@dataclass
class SecretPattern:
    name: str        # Human-readable identifier for logging
    pattern: str     # Regex pattern

SECRETS_PATTERNS = [
    SecretPattern("API_KEY_ASSIGNMENT", r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?[a-zA-Z0-9]{20,}'),
    SecretPattern("PASSWORD_ASSIGNMENT", r'(?i)(secret|password|passwd|pwd)\s*[=:]\s*["\']?.{8,}'),
    SecretPattern("TOKEN_ASSIGNMENT", r'(?i)(token)\s*[=:]\s*["\']?[a-zA-Z0-9_-]{20,}'),
    SecretPattern("BEARER_TOKEN", r'(?i)bearer\s+[a-zA-Z0-9_-]{20,}'),
    SecretPattern("PRIVATE_KEY_BLOCK", r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'),
    SecretPattern("AWS_CREDENTIAL", r'(?i)aws[_-]?(access[_-]?key|secret)'),
    SecretPattern("GITHUB_PAT", r'ghp_[a-zA-Z0-9]{36}'),
    SecretPattern("OPENAI_API_KEY", r'sk-[a-zA-Z0-9]{48}'),
    SecretPattern("ANTHROPIC_API_KEY", r'(?i)anthropic[_-]?api[_-]?key'),
]

def contains_secrets(diff: str) -> tuple[bool, list[str]]:
    """Returns (has_secrets, matched_pattern_names)."""
    matched = []
    for sp in SECRETS_PATTERNS:
        if re.search(sp.pattern, diff):
            matched.append(sp.name)
    return (len(matched) > 0, matched)
```

### 4.2 AI Commit Generator (`commit_ai.py`)

```python
from typing import Optional
from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import ClaudeAgentOptions, AssistantMessage, ResultMessage, TextBlock

SYSTEM_PROMPT = "You are a commit message generator. Output only the commit message, nothing else."

async def generate_smart_commit_message(
    diff: str,
    stats: dict,
    feature_hint: str,
    model: str = "claude-haiku-3-5-20241022",
) -> Optional[str]:
    """Generate Conventional Commits message. Returns None on error."""
    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        tools=[],
        model=model,
        permission_mode="default",
    )
    try:
        async with ClaudeSDKClient(options) as client:
            await client.query(prompt)
            response_text = ""
            async for message in client.receive_messages():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_text += block.text
                elif isinstance(message, ResultMessage):
                    break
            return _validate_and_clean(response_text)
    except Exception:
        return None
```

### 4.3 Updated auto_commit Flow

```python
def auto_commit(
    feature_description: str,
    milestones: List[dict],
    path: Optional[str] = None,
    use_smart_commit: bool = True,
) -> Tuple[bool, str]:
    # 1. Stage all changes
    # 2. Get diff and stats
    # 3. Check for secrets (block if found)
    # 4. Generate smart message (or fallback)
    # 5. Create commit (NEVER push)
```

## 5. Testing Strategy

### 5.1 Unit Tests - git.py

- `test_has_head_commit_new_repo` - no commits
- `test_has_head_commit_with_commits` - normal repo
- `test_get_full_diff_no_head` - new repo edge case
- `test_get_full_diff_truncation` - large diff handling
- `test_get_diff_stats_shortstat_parsing` - various formats

### 5.2 Unit Tests - secrets.py

- `test_contains_secrets_api_key` - API key patterns
- `test_contains_secrets_private_key` - SSH/PEM keys
- `test_contains_secrets_github_pat` - GitHub tokens
- `test_contains_secrets_clean_diff` - no secrets
- `test_contains_secrets_no_value_leak` - returns names, not values

### 5.3 Unit Tests - commit_ai.py

- `test_generate_smart_commit_feat` - feature type
- `test_generate_smart_commit_fix` - fix type
- `test_generate_smart_commit_timeout` - timeout handling
- `test_generate_smart_commit_no_ai_mention` - output validation

### 5.4 Coverage Targets

| Component | Target |
|-----------|--------|
| secrets.py | 95% |
| commit_ai.py | 90% |
| git.py (new code) | 90% |

## 6. Security

- [x] Secrets detected before API call
- [x] Pattern names logged (not values)
- [x] No push operations
- [x] Fallback on any error

## 7. Anti-Patterns

### Don't: Send diff without checking for secrets
```python
# BAD
smart_msg = await generate_smart_commit_message(diff, stats, feature)
```

### Do: Check secrets first, then send
```python
# GOOD
has_secrets, patterns = contains_secrets(diff)
if has_secrets:
    return fallback_message()
smart_msg = await generate_smart_commit_message(diff, stats, feature)
```

---

## Milestones

### Milestone 1: Diff Retrieval Functions

#### Prerequisites
- None (first milestone)

#### Tasks
1. Add `has_head_commit(path) -> bool` helper in `git.py`
2. Add `get_staged_diff(path) -> str` function
3. Add `get_full_diff(path) -> str` with no-HEAD handling and truncation
4. Add `get_diff_stats(path) -> dict` using `--shortstat`
5. Write unit tests for all functions

#### Key References
- `orchestrator_auto/git.py::is_git_repo` - existing pattern
- `orchestrator_auto/git.py::has_changes` - similar subprocess usage

#### Deliverables
- [ ] `has_head_commit()` handles new repos correctly
- [ ] `get_full_diff()` truncates at 8000 chars with indicator
- [ ] `get_diff_stats()` parses `--shortstat` reliably
- [ ] All edge cases tested (empty repo, no changes, large diff)
- [ ] Tests passing

**⛔ STOP - Generate progress report, wait for approval**

---

### Milestone 2: Secrets Detection Module

#### Prerequisites
- Milestone 1 approved

#### Tasks
1. Create `orchestrator_auto/secrets.py` with `SecretPattern` dataclass
2. Implement `SECRETS_PATTERNS` list with named patterns
3. Implement `contains_secrets(diff) -> tuple[bool, list[str]]`
4. Create `tests/test_secrets.py` with synthetic secret tests
5. Verify pattern names returned (not regex text, not values)

#### Key References
- None (new module)

#### Deliverables
- [ ] `secrets.py` created with 9 secret patterns
- [ ] Returns pattern names like `["API_KEY_ASSIGNMENT", "GITHUB_PAT"]`
- [ ] Does NOT log actual secret values
- [ ] All patterns tested with synthetic data
- [ ] Tests passing

**⛔ STOP - Generate progress report, wait for approval**

---

### Milestone 3: AI Commit Message Generator

#### Prerequisites
- Milestone 2 approved

#### Tasks
1. Create `orchestrator_auto/commit_ai.py`
2. Implement `generate_smart_commit_message()` using ClaudeSDKClient
3. Design prompt for Conventional Commits format
4. Add post-processing: strip code fences, validate format, truncate
5. Add timeout handling (30s)
6. Create `tests/test_commit_ai.py` with mocked responses

#### Key References
- `orchestrator_auto/agents.py:78-96` - ClaudeSDKClient usage
- `orchestrator_auto/agents.py:98-131` - async message handling

#### Deliverables
- [ ] `commit_ai.py` created
- [ ] Uses ClaudeSDKClient with `tools=[]`
- [ ] Generates valid Conventional Commits format
- [ ] Returns `None` on any error (timeout, API error, invalid format)
- [ ] No AI/Claude mentions in output
- [ ] Tests passing with mocked agent

**⛔ STOP - Generate progress report, wait for approval**

---

### Milestone 4: Integration into auto_commit Flow

#### Prerequisites
- Milestone 3 approved

#### Tasks
1. Update `auto_commit()` signature to add `use_smart_commit` param
2. Integrate secrets check before API call
3. Integrate AI message generation with fallback
4. Handle async in sync context (`asyncio.run()`)
5. Add integration test in temp git repo

#### Key References
- `orchestrator_auto/git.py::auto_commit` - current implementation
- `orchestrator_auto/cli.py:656-663` - current auto_commit call site

#### Deliverables
- [ ] `auto_commit()` updated with smart commit flow
- [ ] Secrets check runs BEFORE any API call
- [ ] Falls back gracefully on: secrets, AI failure, invalid format
- [ ] No push operations anywhere
- [ ] Integration test passes
- [ ] Tests passing

**⛔ STOP - Generate progress report, wait for approval**

---

### Milestone 5: CLI and Configuration

#### Prerequisites
- Milestone 4 approved

#### Tasks
1. Add `get_smart_commit_enabled()` to `config.py`
2. Add `--smart-commit/--no-smart-commit` flag to CLI
3. Update CLI output with AI analysis feedback
4. Update CLI output with secrets warning when fallback triggered
5. Update all `auto_commit()` call sites to pass config

#### Key References
- `orchestrator_auto/config.py::get_telegram_config` - config pattern
- `orchestrator_auto/cli.py:795` - `--auto-commit` flag pattern

#### Deliverables
- [ ] Config option `auto_commit.smart` works
- [ ] `--no-smart-commit` flag works
- [ ] CLI shows "Analyzing changes with AI..." during generation
- [ ] CLI shows warning when secrets detected
- [ ] Commit message preview shown after commit
- [ ] Tests passing

**⛔ STOP - Generate progress report, wait for approval**

---

### Milestone 6: Documentation and Final Testing

#### Prerequisites
- Milestone 5 approved

#### Tasks
1. Update README.md with Smart Auto-Commit section
2. Document config options and CLI flags
3. Document Conventional Commits format
4. Document secrets detection behavior
5. Run full test suite, verify coverage targets

#### Key References
- `orchestrator-auto/README.md` - existing documentation

#### Deliverables
- [ ] README updated with feature documentation
- [ ] Config and CLI documented
- [ ] Secrets behavior documented
- [ ] All tests passing
- [ ] Coverage targets met (secrets 95%, commit_ai 90%, git 90%)

**⛔ STOP - Generate progress report, TASK COMPLETE**

---

## Quick Reference

| Resource | Path |
|----------|------|
| Implementation Plan | `docs/plans/PLAN_smart_auto_commit.md` |
| Existing git module | `orchestrator_auto/git.py` |
| ClaudeSDKClient pattern | `orchestrator_auto/agents.py:78-96` |
| Config pattern | `orchestrator_auto/config.py:get_telegram_config()` |
| CLI flag pattern | `orchestrator_auto/cli.py:795` |

## Cost Estimate

- Haiku: ~$0.25/1M input, $1.25/1M output
- Typical diff: 2-4K tokens input, 50-100 tokens output
- **~$0.001-0.002 per commit**
