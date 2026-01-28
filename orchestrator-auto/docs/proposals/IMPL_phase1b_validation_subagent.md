# Implementation Ticket: Phase 1B - Validation Sub-Agent

**Ticket ID:** ORCH-SUB-002
**Status:** Ready for Development
**Priority:** High
**Proposal:** [PROPOSAL_subagent_validation.md](./PROPOSAL_subagent_validation.md)
**Dependencies:** orchestrator-auto v1.2.0, claude-agent-sdk 0.1.23, Phase 1A patterns

---

## Summary

Implement specialized validation sub-agents that analyze code changes after milestone execution. Validators perform focused checks (security, performance, API) and surface issues before human review. HIGH severity issues trigger automatic file rewind (leveraging v1.2.0 rewind capability) and `CHANGES_REQUESTED`.

---

## Acceptance Criteria

### Functional Requirements

- [ ] **AC-1**: Validation pipeline runs after milestone execution, before progress report
- [ ] **AC-2**: SecurityValidator checks for common vulnerabilities (SQL injection, XSS, secrets)
- [ ] **AC-3**: PerformanceValidator checks for anti-patterns (N+1, unbounded queries)
- [ ] **AC-4**: APIValidator checks for breaking changes and missing validation
- [ ] **AC-5**: Validation results included in `[PROGRESS_REPORT]` for human review
- [ ] **AC-6**: HIGH severity issues auto-trigger `CHANGES_REQUESTED` + file rewind
- [ ] **AC-7**: CLI flag `--validate` enables validation (default when configured)
- [ ] **AC-8**: CLI flag `--no-validate` disables validation
- [ ] **AC-9**: CLI flag `--validators security,api` selects specific validators
- [ ] **AC-10**: Validation results visible in `orchestrator status <session-id> --validation`

### Rewind Integration Requirements

- [ ] **REWIND-1**: HIGH severity triggers `executor.rewind_to_checkpoint()`
- [ ] **REWIND-2**: Rewind only occurs if checkpoint exists (graceful skip otherwise)
- [ ] **REWIND-3**: Validation findings passed to executor as fix instructions
- [ ] **REWIND-4**: Rewind event logged to session for audit trail

### Governance Requirements (Mandatory)

- [ ] **GOV-1**: Token cap per validator: **max 15,000 tokens**
  - Validators analyze diffs, not full files
  - Exceeded = validator skipped with warning

- [ ] **GOV-2**: Turn cap per validator: **max 3 turns**
  - Validators should be decisive, not exploratory

- [ ] **GOV-3**: Timeout per validator: **20 seconds**
  - Hard timeout, validator marked as "timed out"

- [ ] **GOV-4**: Concurrency cap: **max 3 validators in parallel**
  - All validators run concurrently via `asyncio.gather`
  - Config option `validation.max_parallel: 3`

- [ ] **GOV-5**: Total validation timeout: **45 seconds**
  - If validation pipeline exceeds 45s, proceed with partial results

### Failure Propagation Requirements (Mandatory)

- [ ] **FAIL-1**: Individual validator failure does NOT block other validators
  ```python
  results = await asyncio.gather(
      *[v.validate(files) for v in validators],
      return_exceptions=True  # Isolate failures
  )
  ```

- [ ] **FAIL-2**: Validator errors surface in validation report
  - `"SecurityValidator: ERROR - {reason}"`
  - Does not block milestone, but visible to human reviewer

- [ ] **FAIL-3**: Validation failure does NOT block milestone execution
  - If all validators fail, proceed with warning
  - User sees: "Validation incomplete: {N} validators failed. Manual review recommended."

- [ ] **FAIL-4**: Rewind failure logs error but does not crash
  - If `rewind_to_checkpoint()` fails, log error and proceed
  - User sees: "Rewind failed: {reason}. Manual file restore may be needed."

---

## Technical Design

### New Files

| File | Purpose |
|------|---------|
| `orchestrator_auto/validation/` | Validation package |
| `validation/__init__.py` | Package exports |
| `validation/base.py` | `BaseValidator` abstract class |
| `validation/pipeline.py` | `ValidationPipeline` orchestrator |
| `validation/security.py` | `SecurityValidator` implementation |
| `validation/performance.py` | `PerformanceValidator` implementation |
| `validation/api.py` | `APIValidator` implementation |
| `validation/report.py` | `ValidationReport` formatting |

### Modified Files

| File | Changes |
|------|---------|
| `engine.py` | Add validation step after execution, before progress report |
| `cli.py` | Add `--validate`, `--no-validate`, `--validators` flags |
| `config.py` | Add `validation.*` configuration options |
| `db.py` | Add `validation_results` table |
| `parser.py` | Parse validation section in progress reports |

### API Contract

```python
class BaseValidator(ABC):
    name: str
    severity_threshold: Severity  # Minimum severity to report

    @abstractmethod
    async def validate(
        self,
        changed_files: List[Path],
        diff: str,
        context: str
    ) -> ValidationResult:
        """
        Returns:
            ValidationResult with:
            - issues: List[ValidationIssue]
            - validator_name: str
            - tokens_used: int
            - duration_ms: int
        """

class ValidationIssue:
    severity: Severity  # HIGH, MEDIUM, LOW, WARNING
    category: str       # e.g., "sql_injection"
    message: str
    file: Path
    line: Optional[int]
    recommendation: str

class ValidationPipeline:
    async def run(
        self,
        changed_files: List[Path],
        diff: str,
        milestone_context: str
    ) -> ValidationReport:
        """
        Runs all enabled validators in parallel.
        Returns aggregated report with recommendation.
        """
```

### Rewind Integration

```python
# In engine.py, after validation
if validation_report.has_high_severity:
    # Trigger rewind
    if self.enable_rewind and executor.get_checkpoint():
        rewind_success = await executor.rewind_to_checkpoint_async()
        if rewind_success:
            log.info("Files rewound due to HIGH severity validation issues")
        else:
            log.warning("Rewind failed, manual intervention may be needed")

    # Return CHANGES_REQUESTED with validation findings
    return PlannerResponse(
        response_type=PlannerResponseType.CHANGES_REQUESTED,
        changes_requested=validation_report.format_for_executor()
    )
```

### Configuration Schema

```yaml
# config.yaml
validation:
  enabled: true
  auto_reject_on_high: true      # Auto CHANGES_REQUESTED for HIGH
  max_parallel: 3                # Concurrent validators
  total_timeout: 45              # Pipeline timeout (seconds)

  validators:
    security:
      enabled: true
      severity_threshold: medium
      checks:
        - sql_injection
        - xss_prevention
        - secrets_exposure
        - path_traversal

    performance:
      enabled: true
      severity_threshold: high
      checks:
        - n_plus_one
        - unbounded_query
        - sync_in_async

    api:
      enabled: true
      severity_threshold: medium
      checks:
        - breaking_change
        - missing_validation
```

---

## Security Check Patterns (Phase 1)

```python
SECURITY_CHECKS = {
    "sql_injection": {
        "patterns": [
            r'execute\s*\(\s*f["\']',        # f-string in execute
            r'execute\s*\(\s*["\'].*\+',     # String concat in execute
            r'\.format\s*\(.*\).*execute',   # .format() in query
        ],
        "severity": "HIGH",
        "recommendation": "Use parameterized queries with placeholders"
    },
    "xss_prevention": {
        "patterns": [
            r'innerHTML\s*=\s*[^"\'`]',      # Dynamic innerHTML
            r'document\.write\s*\(',          # document.write
            r'v-html\s*=',                    # Vue unescaped HTML
            r'dangerouslySetInnerHTML',       # React unescaped
        ],
        "severity": "HIGH",
        "recommendation": "Sanitize user input before rendering"
    },
    "secrets_exposure": {
        "patterns": [
            r'api[_-]?key\s*=\s*["\'][A-Za-z0-9]{20,}["\']',
            r'password\s*=\s*["\'][^"\']{8,}["\']',
            r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----',
        ],
        "severity": "HIGH",
        "recommendation": "Move secrets to environment variables"
    },
}
```

---

## Test Plan

### Unit Tests

- [ ] `test_security_validator_detects_sql_injection` - Pattern matching
- [ ] `test_security_validator_detects_secrets` - Secret patterns
- [ ] `test_performance_validator_detects_n_plus_one` - N+1 detection
- [ ] `test_api_validator_detects_breaking_change` - Breaking change detection
- [ ] `test_validation_pipeline_runs_parallel` - Concurrent execution
- [ ] `test_validation_timeout_returns_partial` - Graceful timeout
- [ ] `test_validator_failure_isolated` - Individual failure handling
- [ ] `test_high_severity_triggers_rewind` - Rewind integration

### Integration Tests

- [ ] `test_milestone_with_validation_enabled` - End-to-end validation
- [ ] `test_validation_auto_reject_high` - AUTO CHANGES_REQUESTED flow
- [ ] `test_validation_rewind_on_high` - Rewind + re-execution flow
- [ ] `test_validation_results_in_status` - CLI status display

---

## Rollout Plan

1. **Feature flag**: `ORCHESTRATOR_VALIDATE_ENABLED=false` (off by default)
2. **Security validator first**: Enable only security checks initially
3. **False positive tuning**: Adjust patterns based on real-world usage
4. **Add performance/API**: Enable after security validator stabilizes
5. **Default on**: Flip `validation.enabled: true` after validation

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Validation success rate | > 98% |
| False positive rate | < 5% |
| Average validation time | < 10 seconds |
| HIGH issues caught before human | > 90% |
| Rewind success rate | > 99% |

---

## Open Questions

1. Should validators be pluggable (user-defined validators)? (Deferred to Phase 2)
2. Should validation results feed into planner review? (Deferred to Phase 2)
3. Add AccessibilityValidator for frontend? (Deferred, optional)
