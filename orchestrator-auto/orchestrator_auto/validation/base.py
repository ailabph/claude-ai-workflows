"""
Base classes for validation sub-agents.

Defines the validator interface, severity levels, and result types.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable


class Severity(Enum):
    """Severity levels for validation issues."""

    HIGH = "high"       # Must fix before approval
    MEDIUM = "medium"   # Recommended fix
    LOW = "low"         # Minor issue
    WARNING = "warning" # Informational

    def __lt__(self, other: "Severity") -> bool:
        order = [Severity.WARNING, Severity.LOW, Severity.MEDIUM, Severity.HIGH]
        return order.index(self) < order.index(other)

    def __le__(self, other: "Severity") -> bool:
        return self == other or self < other

    @classmethod
    def from_string(cls, s: str) -> "Severity":
        """Parse severity from string."""
        return cls(s.lower())


@dataclass
class ValidationIssue:
    """A single validation issue found by a validator."""

    severity: Severity
    category: str       # e.g., "sql_injection", "n_plus_one"
    message: str        # Human-readable description
    file: Optional[Path] = None
    line: Optional[int] = None
    recommendation: str = ""
    snippet: str = ""   # Code snippet showing the issue

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "file": str(self.file) if self.file else None,
            "line": self.line,
            "recommendation": self.recommendation,
            "snippet": self.snippet,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationIssue":
        """Create from dictionary."""
        return cls(
            severity=Severity.from_string(data["severity"]),
            category=data["category"],
            message=data["message"],
            file=Path(data["file"]) if data.get("file") else None,
            line=data.get("line"),
            recommendation=data.get("recommendation", ""),
            snippet=data.get("snippet", ""),
        )


@dataclass
class ValidationResult:
    """
    Result from a single validator.

    Note: tokens_used is only populated for LLM-based validators. Pattern-based
    validators (SecurityValidator, PerformanceValidator, APIValidator) do not
    use LLM calls and will always have tokens_used=0.
    """

    validator_name: str
    issues: List[ValidationIssue] = field(default_factory=list)
    tokens_used: int = 0  # Only populated for LLM-based validators; 0 for pattern-based
    duration_ms: int = 0
    error: Optional[str] = None

    @property
    def high_count(self) -> int:
        """Count of HIGH severity issues."""
        return sum(1 for i in self.issues if i.severity == Severity.HIGH)

    @property
    def medium_count(self) -> int:
        """Count of MEDIUM severity issues."""
        return sum(1 for i in self.issues if i.severity == Severity.MEDIUM)

    @property
    def low_count(self) -> int:
        """Count of LOW severity issues."""
        return sum(1 for i in self.issues if i.severity == Severity.LOW)

    @property
    def warning_count(self) -> int:
        """Count of WARNING severity issues."""
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    def is_success(self) -> bool:
        """Check if validation completed without errors."""
        return self.error is None

    def has_issues(self) -> bool:
        """Check if any issues were found."""
        return len(self.issues) > 0

    def filter_by_severity(self, min_severity: Severity) -> List[ValidationIssue]:
        """Get issues at or above a minimum severity."""
        return [i for i in self.issues if i.severity >= min_severity]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "validator_name": self.validator_name,
            "issues": [i.to_dict() for i in self.issues],
            "tokens_used": self.tokens_used,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class BaseValidator(ABC):
    """
    Abstract base class for validators.

    Validators analyze code changes (diffs and files) to find issues.
    Each validator focuses on a specific domain (security, performance, etc.).

    Governance limits:
    - max_tokens: Token limit for LLM-based validators (pattern-based validators ignore this)
    - max_turns: Turn limit for LLM-based validators (pattern-based validators ignore this)
    - timeout: Enforced by ValidationPipeline via asyncio.wait_for

    Note: The built-in validators (SecurityValidator, PerformanceValidator, APIValidator)
    are pattern-based and do not use LLM calls, so max_tokens and max_turns are not
    enforced for them. They complete in a single synchronous pass.
    """

    name: str = "base"
    description: str = "Base validator"

    # Governance limits (enforced for LLM-based validators; timeout enforced for all)
    max_tokens: int = 15_000  # Token limit for LLM-based validators
    max_turns: int = 3        # Turn limit for LLM-based validators
    timeout: float = 20.0     # Timeout enforced by ValidationPipeline

    def __init__(
        self,
        severity_threshold: Severity = Severity.MEDIUM,
        enabled_checks: Optional[List[str]] = None,
    ):
        """
        Initialize the validator.

        Args:
            severity_threshold: Minimum severity to report
            enabled_checks: List of check names to run (None = all)
        """
        self.severity_threshold = severity_threshold
        self.enabled_checks = enabled_checks

    @abstractmethod
    async def validate(
        self,
        changed_files: List[Path],
        diff: str,
        context: str = "",
        get_file_content: Optional[Callable[[Path], str]] = None,
    ) -> ValidationResult:
        """
        Validate code changes.

        Args:
            changed_files: List of changed file paths
            diff: Unified diff of all changes
            context: Optional milestone context
            get_file_content: Callback to fetch file content on-demand

        Returns:
            ValidationResult with any issues found
        """
        pass

    def should_run_check(self, check_name: str) -> bool:
        """Check if a specific check should run."""
        if self.enabled_checks is None:
            return True
        return check_name in self.enabled_checks

    def filter_issues(self, issues: List[ValidationIssue]) -> List[ValidationIssue]:
        """Filter issues by severity threshold."""
        return [i for i in issues if i.severity >= self.severity_threshold]
