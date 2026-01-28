# Proposal: Specialized Validation Sub-Agents

**Status:** Approved by: CTO, 2026-01-28
**Phase:** 1B (Second Priority)
**Author:** Engineering Team
**Created:** 2026-01-28
**Updated:** 2026-01-28
**Category:** Quality Assurance

---

## Version Context

This proposal builds on **orchestrator-auto v1.2.0**, which integrated **Claude Agent SDK 0.1.23**. The SDK's `rewind_files()` capability enables automatic rollback when validation fails with HIGH severity issues.

| Component | Version | Relevant Feature |
|-----------|---------|------------------|
| orchestrator-auto | 1.2.0 | File rewind on rejection, checkpoint tracking |
| claude-agent-sdk | 0.1.23 | `rewind_files()`, `uuid` on UserMessage |

### Rewind Integration

When a validation agent detects HIGH severity issues:
1. Validation report triggers `CHANGES_REQUESTED`
2. Engine calls `executor.rewind_to_checkpoint()` (existing v1.2.0 feature)
3. Files automatically restored to pre-execution state
4. Executor receives validation findings and implements fixes from clean slate

---

## Executive Summary

Introduce specialized validation sub-agents that automatically analyze code changes after milestone execution. These agents perform focused checks (security, performance, accessibility, etc.) and surface issues before human review, reducing the burden on reviewers and catching problems earlier.

## Problem Statement

Current milestone validation relies on:
1. **Planner review** - General code review, not specialized
2. **Human review** - Bottleneck, may miss domain-specific issues
3. **Manual testing** - Time-consuming, inconsistent coverage

Issues that slip through:
- Security vulnerabilities (SQL injection, XSS, hardcoded secrets)
- Performance anti-patterns (N+1 queries, missing indexes)
- Accessibility violations (missing ARIA labels, color contrast)
- API inconsistencies (breaking changes, missing validation)

## Proposed Solution

Add **pluggable validation sub-agents** that run automatically after milestone execution:

```
┌─────────────────────────────────────────────────────────────────┐
│  EXECUTOR completes milestone                                    │
├─────────────────────────────────────────────────────────────────┤
│  Validation Pipeline (parallel)                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │  Security   │ │ Performance │ │    API      │               │
│  │  Validator  │ │  Validator  │ │  Validator  │               │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘               │
│         │               │               │                       │
│         ▼               ▼               ▼                       │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                 Validation Report                           ││
│  │  Security: 1 HIGH, 2 MEDIUM                                 ││
│  │  Performance: 0 issues                                      ││
│  │  API: 1 WARNING                                             ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                 │
│  If HIGH issues: Auto-trigger CHANGES_REQUESTED                 │
│  If MEDIUM/LOW: Include in progress report for human review     │
└─────────────────────────────────────────────────────────────────┘
```

### Validator Types

#### 1. Security Validator
```python
class SecurityValidator(BaseValidator):
    """Scans for common security vulnerabilities."""

    CHECKS = [
        "sql_injection",      # Parameterized queries
        "xss_prevention",     # Output encoding
        "auth_bypass",        # Authentication checks
        "secrets_exposure",   # Hardcoded credentials
        "path_traversal",     # File path validation
        "csrf_protection",    # Token validation
    ]

    async def validate(self, changed_files: List[Path]) -> ValidationResult:
        issues = []
        for file in changed_files:
            content = file.read_text()
            for check in self.CHECKS:
                if finding := self._run_check(check, content):
                    issues.append(finding)
        return ValidationResult(validator="security", issues=issues)
```

#### 2. Performance Validator
```python
class PerformanceValidator(BaseValidator):
    """Identifies performance anti-patterns."""

    CHECKS = [
        "n_plus_one",         # Query in loop
        "missing_index",      # Unindexed query columns
        "unbounded_query",    # No LIMIT clause
        "sync_in_async",      # Blocking calls in async
        "memory_leak",        # Unclosed resources
    ]
```

#### 3. API Validator
```python
class APIValidator(BaseValidator):
    """Checks API consistency and breaking changes."""

    CHECKS = [
        "breaking_change",    # Removed/renamed fields
        "missing_validation", # Unvalidated input
        "inconsistent_errors",# Error format consistency
        "missing_pagination", # Large collections without pagination
        "version_mismatch",   # API version inconsistencies
    ]
```

#### 4. Accessibility Validator
```python
class AccessibilityValidator(BaseValidator):
    """Scans frontend code for a11y issues."""

    CHECKS = [
        "missing_alt_text",   # Images without alt
        "missing_aria",       # Interactive elements without ARIA
        "color_contrast",     # Insufficient contrast
        "keyboard_nav",       # Non-focusable interactive elements
        "heading_order",      # Skipped heading levels
    ]
```

### Architecture

```python
class ValidationPipeline:
    """Orchestrates multiple validators."""

    def __init__(self, validators: List[BaseValidator]):
        self.validators = validators

    async def run(
        self,
        changed_files: List[Path],
        milestone_context: str
    ) -> ValidationReport:
        # Run all validators in parallel
        results = await asyncio.gather(
            *[v.validate(changed_files) for v in self.validators]
        )

        return ValidationReport(
            results=results,
            summary=self._generate_summary(results),
            recommendation=self._get_recommendation(results)
        )

    def _get_recommendation(self, results) -> str:
        high_issues = sum(r.high_count for r in results)
        if high_issues > 0:
            return "CHANGES_REQUESTED"  # Auto-reject
        return "PROCEED_WITH_WARNINGS"  # Human decides
```

### Configuration

```yaml
# config.yaml
validation:
  enabled: true
  auto_reject_on_high: true    # Auto CHANGES_REQUESTED for HIGH issues
  validators:
    security:
      enabled: true
      severity_threshold: medium  # Report MEDIUM and above
    performance:
      enabled: true
      severity_threshold: high
    api:
      enabled: true
      severity_threshold: medium
    accessibility:
      enabled: false            # Disabled by default

  # Custom validators
  custom:
    - name: "license-check"
      command: "npx license-checker --onlyAllow 'MIT;Apache-2.0'"
      severity: high
```

### CLI Integration

```bash
# Run with validation (default)
orchestrator start -f "Add payment processing" --validate

# Specify validators
orchestrator start -f "Add UI" --validators security,accessibility

# Skip validation for quick iterations
orchestrator start -f "Fix typo" --no-validate

# View validation results
orchestrator status <session-id> --validation
# Output:
# Milestone 2: Payment API
# Validation Results:
#   Security:
#     [HIGH] SQL injection risk in process_payment() - line 45
#     [MEDIUM] Hardcoded timeout value - line 78
#   Performance:
#     No issues found
#   API:
#     [WARNING] Missing rate limiting on /payments endpoint
```

## Implementation Plan

### Phase 1: Core Framework
- Implement BaseValidator abstract class
- Create ValidationPipeline orchestrator
- Add validation hooks to engine.py

### Phase 2: Built-in Validators
- Implement SecurityValidator (highest priority)
- Implement PerformanceValidator
- Implement APIValidator

### Phase 3: Integration
- Add validation results to progress reports
- Implement auto-rejection for HIGH issues
- Add CLI flags and status display

### Phase 4: Extensibility
- Custom validator support (shell commands)
- Validator plugins architecture
- Shared finding database for trend analysis

## Benefits

| Benefit | Impact |
|---------|--------|
| Earlier issue detection | Catch problems before human review |
| Consistent quality checks | Every milestone gets same scrutiny |
| Reduced reviewer burden | Focus on architecture, not nitpicks |
| Security compliance | Automated security scanning |
| Knowledge capture | Encode team standards as validators |

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| False positives | Severity thresholds, easy suppression |
| Slow validation | Parallel execution, file-focused analysis |
| Validator maintenance | Start simple, iterate based on findings |
| Over-automation | Human always makes final decision |

## Example Validation Report

```markdown
## Validation Report - Milestone 3: Payment Processing

### Security Validator
| Severity | Issue | Location | Recommendation |
|----------|-------|----------|----------------|
| HIGH | SQL injection risk | payment.py:45 | Use parameterized query |
| MEDIUM | Hardcoded API timeout | client.py:78 | Move to configuration |

### Performance Validator
No issues found.

### API Validator
| Severity | Issue | Location | Recommendation |
|----------|-------|----------|----------------|
| WARNING | Missing rate limiting | routes.py:23 | Add rate limiter decorator |

### Summary
- **HIGH**: 1 issue (requires fix before approval)
- **MEDIUM**: 1 issue (recommended fix)
- **WARNING**: 1 issue (consider for future)

**Recommendation**: CHANGES_REQUESTED - Fix HIGH severity SQL injection before proceeding.
```

## Success Metrics

- Issues caught by validators vs. human review
- False positive rate
- Time saved in review process
- Security vulnerability reduction

## Effort Estimate

**Complexity:** Medium-High
**Files Modified:** 4-5 (engine.py, agents.py, cli.py, parser.py)
**New Files:** 5-8 (validators/, validation.py, report.py)
**Testing:** Validator accuracy tests, integration tests

---

## Appendix: Security Check Patterns

```python
SECURITY_PATTERNS = {
    "sql_injection": [
        r'execute\s*\(\s*f["\']',           # f-string in execute
        r'execute\s*\(\s*["\'].*%s',         # String interpolation
        r'\.format\s*\(.*\).*execute',       # .format() in query
    ],
    "xss_prevention": [
        r'innerHTML\s*=',                    # Direct innerHTML
        r'document\.write\s*\(',             # document.write
        r'\{\{\s*\w+\s*\}\}',               # Unescaped template (check framework)
    ],
    "secrets_exposure": [
        r'api[_-]?key\s*=\s*["\'][^"\']+["\']',  # Hardcoded API key
        r'password\s*=\s*["\'][^"\']+["\']',     # Hardcoded password
        r'secret\s*=\s*["\'][^"\']+["\']',       # Hardcoded secret
    ],
}
```
