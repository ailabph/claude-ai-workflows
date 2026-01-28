"""
Validation pipeline that orchestrates multiple validators.

Runs validators in parallel and aggregates results into a unified report.
"""

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from .base import BaseValidator, ValidationResult, ValidationIssue, Severity


@dataclass
class ValidationReport:
    """Aggregated report from all validators."""

    results: List[ValidationResult] = field(default_factory=list)
    total_duration_ms: int = 0
    recommendation: str = "PROCEED"  # PROCEED, PROCEED_WITH_WARNINGS, CHANGES_REQUESTED

    @property
    def has_high_severity(self) -> bool:
        """Check if any HIGH severity issues were found."""
        return any(r.high_count > 0 for r in self.results)

    @property
    def total_issues(self) -> int:
        """Total number of issues across all validators."""
        return sum(len(r.issues) for r in self.results)

    @property
    def high_count(self) -> int:
        """Total HIGH severity issues."""
        return sum(r.high_count for r in self.results)

    @property
    def medium_count(self) -> int:
        """Total MEDIUM severity issues."""
        return sum(r.medium_count for r in self.results)

    @property
    def all_issues(self) -> List[ValidationIssue]:
        """All issues from all validators."""
        issues = []
        for r in self.results:
            issues.extend(r.issues)
        return issues

    def get_issues_by_severity(self, severity: Severity) -> List[ValidationIssue]:
        """Get all issues of a specific severity."""
        return [i for i in self.all_issues if i.severity == severity]

    def format_summary(self) -> str:
        """Format a short summary of the report."""
        if not self.results:
            return "No validation performed."

        lines = ["## Validation Summary"]
        lines.append(f"- **HIGH**: {self.high_count} issues")
        lines.append(f"- **MEDIUM**: {self.medium_count} issues")
        lines.append(f"- **Recommendation**: {self.recommendation}")
        return "\n".join(lines)

    def format_for_executor(self) -> str:
        """Format the report as instructions for the executor to fix issues."""
        if not self.has_high_severity:
            return ""

        lines = ["## Validation Issues Requiring Fix\n"]
        lines.append("The following HIGH severity issues must be addressed:\n")

        for result in self.results:
            high_issues = [i for i in result.issues if i.severity == Severity.HIGH]
            if high_issues:
                lines.append(f"### {result.validator_name}")
                for issue in high_issues:
                    lines.append(f"- **{issue.category}**: {issue.message}")
                    if issue.file:
                        loc = f"{issue.file}"
                        if issue.line:
                            loc += f":{issue.line}"
                        lines.append(f"  - Location: `{loc}`")
                    if issue.recommendation:
                        lines.append(f"  - Fix: {issue.recommendation}")
                    if issue.snippet:
                        lines.append(f"  ```\n  {issue.snippet}\n  ```")
                lines.append("")

        return "\n".join(lines)

    def format_for_progress_report(self) -> str:
        """Format the report for inclusion in progress report."""
        if not self.results:
            return ""

        lines = ["## Validation Results\n"]

        for result in self.results:
            if result.error:
                lines.append(f"### {result.validator_name}: ERROR")
                lines.append(f"_{result.error}_\n")
            elif result.issues:
                lines.append(f"### {result.validator_name}")
                lines.append(f"| Severity | Issue | Location |")
                lines.append(f"|----------|-------|----------|")
                for issue in result.issues:
                    loc = ""
                    if issue.file:
                        loc = str(issue.file)
                        if issue.line:
                            loc += f":{issue.line}"
                    lines.append(
                        f"| {issue.severity.value.upper()} | {issue.message} | {loc} |"
                    )
                lines.append("")
            else:
                lines.append(f"### {result.validator_name}: No issues found\n")

        lines.append(f"**Recommendation**: {self.recommendation}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "results": [r.to_dict() for r in self.results],
            "total_duration_ms": self.total_duration_ms,
            "recommendation": self.recommendation,
            "summary": {
                "high": self.high_count,
                "medium": self.medium_count,
                "total": self.total_issues,
            },
        }


class ValidationPipeline:
    """
    Orchestrates multiple validators running in parallel.

    Governance:
    - Runs validators concurrently (max_parallel limit)
    - Total timeout for entire pipeline
    - Individual validator failures are isolated
    """

    def __init__(
        self,
        validators: List[BaseValidator],
        max_parallel: int = 3,
        total_timeout: float = 45.0,
        auto_reject_on_high: bool = True,
    ):
        """
        Initialize the validation pipeline.

        Args:
            validators: List of validators to run
            max_parallel: Maximum concurrent validators
            total_timeout: Total timeout for pipeline (seconds)
            auto_reject_on_high: Auto CHANGES_REQUESTED for HIGH issues
        """
        self.validators = validators
        self.max_parallel = max_parallel
        self.total_timeout = total_timeout
        self.auto_reject_on_high = auto_reject_on_high

    async def run(
        self,
        changed_files: List[Path],
        diff: str,
        milestone_context: str = "",
        get_file_content: Optional[Callable[[Path], str]] = None,
    ) -> ValidationReport:
        """
        Run all validators and aggregate results.

        Args:
            changed_files: List of changed file paths
            diff: Unified diff of all changes
            milestone_context: Optional milestone context
            get_file_content: Callback to fetch file content on-demand

        Returns:
            ValidationReport with aggregated results
        """
        start_time = time.time()
        semaphore = asyncio.Semaphore(self.max_parallel)

        async def run_validator(validator: BaseValidator) -> ValidationResult:
            async with semaphore:
                try:
                    return await asyncio.wait_for(
                        validator.validate(
                            changed_files, diff, milestone_context, get_file_content
                        ),
                        timeout=validator.timeout,
                    )
                except asyncio.TimeoutError:
                    return ValidationResult(
                        validator_name=validator.name,
                        error=f"Timeout after {validator.timeout}s",
                    )
                except Exception as e:
                    return ValidationResult(
                        validator_name=validator.name,
                        error=str(e),
                    )

        # Create tasks with validator references for tracking
        tasks = {
            asyncio.create_task(run_validator(v)): v
            for v in self.validators
        }

        # Wait with timeout, preserving partial results
        done, pending = await asyncio.wait(
            tasks.keys(),
            timeout=self.total_timeout,
            return_when=asyncio.ALL_COMPLETED,
        )

        # Collect completed results
        final_results: List[ValidationResult] = []

        for task in done:
            try:
                result = task.result()
                if isinstance(result, Exception):
                    validator = tasks[task]
                    final_results.append(
                        ValidationResult(
                            validator_name=validator.name,
                            error=str(result),
                        )
                    )
                else:
                    final_results.append(result)
            except Exception as e:
                validator = tasks[task]
                final_results.append(
                    ValidationResult(
                        validator_name=validator.name,
                        error=str(e),
                    )
                )

        # Mark pending tasks as timed out (preserve completed results)
        if pending:
            # Cancel all pending tasks
            for task in pending:
                task.cancel()

            # Await cancellation to avoid "Task was destroyed but pending" warnings
            await asyncio.gather(*pending, return_exceptions=True)

            # Record timeout results
            for task in pending:
                validator = tasks[task]
                final_results.append(
                    ValidationResult(
                        validator_name=validator.name,
                        error="Pipeline timeout (incomplete)",
                    )
                )

        total_duration_ms = int((time.time() - start_time) * 1000)

        # Determine recommendation
        recommendation = self._get_recommendation(final_results)

        return ValidationReport(
            results=final_results,
            total_duration_ms=total_duration_ms,
            recommendation=recommendation,
        )

    def _get_recommendation(self, results: List[ValidationResult]) -> str:
        """Determine the recommendation based on results."""
        high_count = sum(r.high_count for r in results)
        medium_count = sum(r.medium_count for r in results)

        if high_count > 0 and self.auto_reject_on_high:
            return "CHANGES_REQUESTED"
        elif high_count > 0 or medium_count > 0:
            return "PROCEED_WITH_WARNINGS"
        else:
            return "PROCEED"


def create_default_pipeline(
    config: Optional[Dict[str, Any]] = None,
) -> ValidationPipeline:
    """
    Create a validation pipeline with default validators.

    Args:
        config: Optional validation configuration

    Returns:
        ValidationPipeline with configured validators
    """
    from .security import SecurityValidator
    from .performance import PerformanceValidator
    from .api import APIValidator

    config = config or {}
    validators_config = config.get("validators", {})

    validators = []

    # Security validator
    security_cfg = validators_config.get("security", {"enabled": True})
    if security_cfg.get("enabled", True):
        threshold = Severity.from_string(
            security_cfg.get("severity_threshold", "medium")
        )
        validators.append(SecurityValidator(severity_threshold=threshold))

    # Performance validator
    perf_cfg = validators_config.get("performance", {"enabled": True})
    if perf_cfg.get("enabled", True):
        threshold = Severity.from_string(
            perf_cfg.get("severity_threshold", "high")
        )
        validators.append(PerformanceValidator(severity_threshold=threshold))

    # API validator
    api_cfg = validators_config.get("api", {"enabled": True})
    if api_cfg.get("enabled", True):
        threshold = Severity.from_string(
            api_cfg.get("severity_threshold", "medium")
        )
        validators.append(APIValidator(severity_threshold=threshold))

    return ValidationPipeline(
        validators=validators,
        max_parallel=config.get("max_parallel", 3),
        total_timeout=config.get("total_timeout", 45.0),
        auto_reject_on_high=config.get("auto_reject_on_high", True),
    )
