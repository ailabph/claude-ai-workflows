"""Tests for planner_auto.reviewer.contract — dataclasses, enums,
ReviewerContract ABC, and JSON serialisation round-trips."""

from __future__ import annotations

import json
from abc import ABC

import pytest

from planner_auto.reviewer.contract import (
    ReviewIssue,
    ReviewerContract,
    ReviewerResponse,
    Severity,
    Verdict,
)


# ---------------------------------------------------------------------------
# Enum values
# ---------------------------------------------------------------------------

class TestEnumValues:
    def test_verdict_go_value(self):
        assert Verdict.GO.value == "GO"

    def test_verdict_nogo_value(self):
        assert Verdict.NO_GO.value == "NO_GO"

    def test_severity_values(self):
        assert Severity.CRITICAL.value == "critical"
        assert Severity.MAJOR.value == "major"
        assert Severity.MINOR.value == "minor"

    def test_verdict_is_str_enum(self):
        # Verdict inherits str so it compares equal to its value string.
        assert Verdict.GO == "GO"
        assert Verdict.NO_GO == "NO_GO"

    def test_severity_is_str_enum(self):
        assert Severity.CRITICAL == "critical"


# ---------------------------------------------------------------------------
# ReviewIssue dataclass construction and defaults
# ---------------------------------------------------------------------------

class TestReviewIssueConstruction:
    def test_required_fields(self):
        issue = ReviewIssue(
            severity=Severity.CRITICAL,
            description="Missing retry logic",
            rationale="Prod services must retry on transient errors",
        )
        assert issue.severity == Severity.CRITICAL
        assert issue.description == "Missing retry logic"
        assert issue.rationale == "Prod services must retry on transient errors"

    def test_default_resolution_guidance_is_empty(self):
        issue = ReviewIssue(
            severity=Severity.MAJOR,
            description="d",
            rationale="r",
        )
        assert issue.resolution_guidance == ""

    def test_default_target_section_is_empty(self):
        issue = ReviewIssue(
            severity=Severity.MINOR,
            description="d",
            rationale="r",
        )
        assert issue.target_section == ""

    def test_optional_fields_settable(self):
        issue = ReviewIssue(
            severity=Severity.CRITICAL,
            description="d",
            rationale="r",
            resolution_guidance="Add retry with backoff",
            target_section="Milestone 3",
        )
        assert issue.resolution_guidance == "Add retry with backoff"
        assert issue.target_section == "Milestone 3"


# ---------------------------------------------------------------------------
# ReviewIssue serialisation
# ---------------------------------------------------------------------------

class TestReviewIssueSerialisation:
    def test_to_dict_includes_all_fields(self):
        issue = ReviewIssue(
            severity=Severity.CRITICAL,
            description="No error handling",
            rationale="Will crash",
            resolution_guidance="Wrap in try/except",
            target_section="Milestone 2",
        )
        d = issue.to_dict()
        assert d["severity"] == "critical"
        assert d["description"] == "No error handling"
        assert d["rationale"] == "Will crash"
        assert d["resolution_guidance"] == "Wrap in try/except"
        assert d["target_section"] == "Milestone 2"

    def test_from_dict_round_trip(self):
        original = ReviewIssue(
            severity=Severity.MAJOR,
            description="Missing pagination",
            rationale="Will OOM",
            resolution_guidance="Add limit=50",
            target_section="M1",
        )
        restored = ReviewIssue.from_dict(original.to_dict())
        assert restored.severity == original.severity
        assert restored.description == original.description
        assert restored.rationale == original.rationale
        assert restored.resolution_guidance == original.resolution_guidance
        assert restored.target_section == original.target_section

    def test_from_dict_defaults_severity_to_major(self):
        issue = ReviewIssue.from_dict({"description": "x", "rationale": "y"})
        assert issue.severity == Severity.MAJOR


# ---------------------------------------------------------------------------
# ReviewerResponse dataclass construction and defaults
# ---------------------------------------------------------------------------

class TestReviewerResponseConstruction:
    def test_minimal_construction(self):
        resp = ReviewerResponse(verdict=Verdict.GO)
        assert resp.verdict == Verdict.GO
        assert resp.issues == []
        assert resp.summary == ""
        assert resp.keep == []
        assert resp.trim == []

    def test_default_lists_are_independent_instances(self):
        """Mutable default fields must not be shared between instances."""
        r1 = ReviewerResponse(verdict=Verdict.GO)
        r2 = ReviewerResponse(verdict=Verdict.GO)
        r1.issues.append(ReviewIssue(Severity.MINOR, "d", "r"))
        assert r2.issues == []

    def test_full_construction(self):
        issues = [ReviewIssue(Severity.CRITICAL, "Error handling missing", "Will crash")]
        resp = ReviewerResponse(
            verdict=Verdict.NO_GO,
            issues=issues,
            summary="Needs work",
            keep=["DB schema"],
            trim=["Caching layer"],
        )
        assert resp.verdict == Verdict.NO_GO
        assert len(resp.issues) == 1
        assert resp.summary == "Needs work"
        assert resp.keep == ["DB schema"]
        assert resp.trim == ["Caching layer"]


# ---------------------------------------------------------------------------
# ReviewerResponse convenience properties
# ---------------------------------------------------------------------------

class TestReviewerResponseProperties:
    def test_critical_issues_filter(self):
        resp = ReviewerResponse(
            verdict=Verdict.NO_GO,
            issues=[
                ReviewIssue(Severity.CRITICAL, "c1", "r"),
                ReviewIssue(Severity.MAJOR, "m1", "r"),
                ReviewIssue(Severity.CRITICAL, "c2", "r"),
            ],
        )
        assert len(resp.critical_issues) == 2
        assert all(i.severity == Severity.CRITICAL for i in resp.critical_issues)

    def test_has_critical_issues_true(self):
        resp = ReviewerResponse(
            verdict=Verdict.NO_GO,
            issues=[ReviewIssue(Severity.CRITICAL, "x", "r")],
        )
        assert resp.has_critical_issues is True

    def test_has_critical_issues_false(self):
        resp = ReviewerResponse(
            verdict=Verdict.NO_GO,
            issues=[ReviewIssue(Severity.MAJOR, "x", "r")],
        )
        assert resp.has_critical_issues is False

    def test_has_critical_issues_empty(self):
        resp = ReviewerResponse(verdict=Verdict.GO)
        assert resp.has_critical_issues is False


# ---------------------------------------------------------------------------
# ReviewerResponse JSON serialisation
# ---------------------------------------------------------------------------

class TestReviewerResponseSerialisation:
    def test_to_dict_go_no_issues(self):
        resp = ReviewerResponse(verdict=Verdict.GO, summary="Approved")
        d = resp.to_dict()
        assert d["verdict"] == "GO"
        assert d["issues"] == []
        assert d["summary"] == "Approved"
        assert d["keep"] == []
        assert d["trim"] == []

    def test_to_json_is_valid_json(self):
        resp = ReviewerResponse(
            verdict=Verdict.NO_GO,
            issues=[ReviewIssue(Severity.CRITICAL, "Error handling", "Will crash")],
            summary="Needs work",
        )
        raw = resp.to_json()
        parsed = json.loads(raw)
        assert parsed["verdict"] == "NO_GO"
        assert len(parsed["issues"]) == 1
        assert parsed["issues"][0]["severity"] == "critical"

    def test_from_dict_round_trip(self):
        original = ReviewerResponse(
            verdict=Verdict.NO_GO,
            issues=[
                ReviewIssue(
                    Severity.CRITICAL,
                    "Missing auth",
                    "Security risk",
                    resolution_guidance="Add JWT middleware",
                    target_section="Milestone 1",
                )
            ],
            summary="Blocked on auth",
            keep=["DB schema"],
            trim=["Extra logging"],
        )
        restored = ReviewerResponse.from_dict(original.to_dict())
        assert restored.verdict == original.verdict
        assert restored.summary == original.summary
        assert len(restored.issues) == 1
        assert restored.issues[0].resolution_guidance == "Add JWT middleware"
        assert restored.keep == ["DB schema"]
        assert restored.trim == ["Extra logging"]

    def test_from_dict_invalid_verdict_defaults_to_nogo(self):
        d = {"verdict": "MAYBE", "issues": [], "summary": ""}
        resp = ReviewerResponse.from_dict(d)
        assert resp.verdict == Verdict.NO_GO


# ---------------------------------------------------------------------------
# ReviewerContract ABC
# ---------------------------------------------------------------------------

class TestReviewerContractABC:
    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            ReviewerContract()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_review(self):
        """A concrete subclass missing review() cannot be instantiated."""
        class IncompleteAdapter(ReviewerContract):
            pass

        with pytest.raises(TypeError):
            IncompleteAdapter()  # type: ignore[abstract]

    def test_concrete_subclass_is_instantiable(self):
        """A properly implemented adapter can be instantiated."""
        class DummyAdapter(ReviewerContract):
            async def review(self, plan_text, previous_context=None):
                return ReviewerResponse(verdict=Verdict.GO)

        adapter = DummyAdapter()
        assert isinstance(adapter, ReviewerContract)
        assert isinstance(adapter, ABC)
