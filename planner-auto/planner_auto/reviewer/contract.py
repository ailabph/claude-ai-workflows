"""Reviewer contract — abstract interface, data types, and enums.

All reviewer adapters (direct API, MCP, etc.) must implement
``ReviewerContract`` and return ``ReviewerResponse`` objects.
"""

from __future__ import annotations

import dataclasses
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Verdict(str, Enum):
    """Final verdict from the reviewer."""
    GO = "GO"
    NO_GO = "NO_GO"


class Severity(str, Enum):
    """Severity level of a review issue."""
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ReviewIssue:
    """A single actionable issue surfaced by the reviewer.

    Attributes:
        severity: How blocking this issue is (CRITICAL/MAJOR/MINOR).
        description: One-sentence description of the problem.
        rationale: Why this is a problem.
        resolution_guidance: Optional concrete suggestion for how to fix it.
        target_section: Optional reference to the plan section that needs work.
    """
    severity: Severity
    description: str
    rationale: str
    resolution_guidance: str = ""
    target_section: str = ""

    def to_dict(self) -> dict:
        """Serialise to a plain dict (suitable for JSON encoding)."""
        return {
            "severity": self.severity.value,
            "description": self.description,
            "rationale": self.rationale,
            "resolution_guidance": self.resolution_guidance,
            "target_section": self.target_section,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewIssue":
        """Deserialise from a plain dict."""
        return cls(
            severity=Severity(data.get("severity", Severity.MAJOR.value)),
            description=data.get("description", ""),
            rationale=data.get("rationale", ""),
            resolution_guidance=data.get("resolution_guidance", ""),
            target_section=data.get("target_section", ""),
        )


@dataclass
class ReviewerResponse:
    """Structured output from a reviewer call.

    Attributes:
        verdict: GO (plan is implementation-ready) or NO_GO (needs revision).
        issues: List of issues found during review.
        summary: Human-readable summary of the review.
        keep: Sections/aspects of the plan that should be preserved.
        trim: Sections/aspects that add unnecessary scope and should be cut.
    """
    verdict: Verdict
    issues: list[ReviewIssue] = field(default_factory=list)
    summary: str = ""
    keep: list[str] = field(default_factory=list)
    trim: list[str] = field(default_factory=list)

    @property
    def critical_issues(self) -> list[ReviewIssue]:
        """Return only CRITICAL severity issues."""
        return [i for i in self.issues if i.severity == Severity.CRITICAL]

    @property
    def has_critical_issues(self) -> bool:
        """True if any CRITICAL issues are present."""
        return any(i.severity == Severity.CRITICAL for i in self.issues)

    def to_dict(self) -> dict:
        """Serialise to a plain dict (suitable for JSON encoding)."""
        return {
            "verdict": self.verdict.value,
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary,
            "keep": self.keep,
            "trim": self.trim,
        }

    def to_json(self) -> str:
        """Serialise to a JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewerResponse":
        """Deserialise from a plain dict."""
        raw_verdict = data.get("verdict", Verdict.NO_GO.value)
        verdict = Verdict(raw_verdict) if raw_verdict in (v.value for v in Verdict) else Verdict.NO_GO
        issues = [ReviewIssue.from_dict(i) for i in data.get("issues", [])]
        return cls(
            verdict=verdict,
            issues=issues,
            summary=data.get("summary", ""),
            keep=list(data.get("keep", [])),
            trim=list(data.get("trim", [])),
        )


# ---------------------------------------------------------------------------
# Abstract contract
# ---------------------------------------------------------------------------

class ReviewerContract(ABC):
    """Abstract base class for all reviewer adapters.

    Subclasses must implement :meth:`review` and return a
    :class:`ReviewerResponse`.  The caller is responsible for storing the
    response in the database and exporting artifacts.
    """

    @abstractmethod
    async def review(
        self,
        plan_text: str,
        previous_context: Optional[str] = None,
    ) -> ReviewerResponse:
        """Review a plan draft and return a structured response.

        Args:
            plan_text: The full text of the plan draft to review.
            previous_context: Optional context from prior review rounds
                (includes deferred issues list, prior round verdicts, etc.).
                When provided, the reviewer should focus on genuinely NEW
                issues and not re-raise intentionally deferred items.

        Returns:
            A :class:`ReviewerResponse` with a verdict, issues, and summary.
        """
        ...
