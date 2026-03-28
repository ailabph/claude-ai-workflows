"""Tests for planner_auto.reviewer.parser — ported from POC 2a.

Covers all three parsing stages (JSON, XML, free-form) plus edge cases:
clean GO/NO_GO, markdown-fenced JSON, XML tags, free-form keyword matching,
malformed/empty/truncated inputs, conflicting signals, unicode content,
keep/trim extraction, and resolution_guidance round-trip.
"""

from __future__ import annotations

import json

import pytest

from planner_auto.reviewer.contract import ReviewIssue, ReviewerResponse, Severity, Verdict
from planner_auto.reviewer.parser import (
    _make_parse_failure,
    _try_parse_freeform,
    _try_parse_json,
    _try_parse_xml,
    parse_reviewer_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _go(**kwargs) -> dict:
    return {"verdict": "GO", "issues": [], "summary": "Looks good.", **kwargs}


def _nogo(issues: list[dict], summary: str = "Needs work.") -> dict:
    return {"verdict": "NO_GO", "issues": issues, "summary": summary}


def _issue(severity: str, description: str, rationale: str = "R", **kwargs) -> dict:
    return {"severity": severity, "description": description, "rationale": rationale, **kwargs}


# ---------------------------------------------------------------------------
# 1. Clean GO JSON
# ---------------------------------------------------------------------------

class TestCleanGoJson:
    def test_clean_go_json(self):
        raw = json.dumps(_go())
        result = parse_reviewer_response(raw)
        assert result.verdict == Verdict.GO
        assert result.issues == []

    def test_clean_go_json_summary(self):
        raw = json.dumps(_go(summary="All good."))
        result = parse_reviewer_response(raw)
        assert result.summary == "All good."


# ---------------------------------------------------------------------------
# 2. Clean NO_GO JSON
# ---------------------------------------------------------------------------

class TestCleanNoGoJson:
    def test_clean_nogo_json(self):
        raw = json.dumps(
            _nogo([
                _issue("critical", "No error handling"),
                _issue("major", "Missing migration"),
                _issue("minor", "Naming inconsistency"),
            ])
        )
        result = parse_reviewer_response(raw)
        assert result.verdict == Verdict.NO_GO
        assert len(result.issues) == 3

    def test_issue_severity_mapped_correctly(self):
        raw = json.dumps(
            _nogo([
                _issue("critical", "C"),
                _issue("major", "M"),
                _issue("minor", "m"),
            ])
        )
        result = parse_reviewer_response(raw)
        severities = [i.severity for i in result.issues]
        assert severities == [Severity.CRITICAL, Severity.MAJOR, Severity.MINOR]


# ---------------------------------------------------------------------------
# 3. GO with non-blocking notes
# ---------------------------------------------------------------------------

class TestGoWithNotes:
    def test_go_with_minor_issue(self):
        raw = json.dumps(
            {"verdict": "GO", "issues": [_issue("minor", "Optional tracing")], "summary": "Looks good."}
        )
        result = parse_reviewer_response(raw)
        assert result.verdict == Verdict.GO
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.MINOR


# ---------------------------------------------------------------------------
# 4. XML-tagged format
# ---------------------------------------------------------------------------

class TestXmlTaggedFormat:
    def test_xml_nogo_two_issues(self):
        raw = """
<verdict>NO_GO</verdict>
<summary>Critical security gap.</summary>
<issues>
  <issue>
    <severity>critical</severity>
    <description>Tokens stored in plain text</description>
    <rationale>Must be encrypted at rest</rationale>
  </issue>
  <issue>
    <severity>major</severity>
    <description>No input validation</description>
    <rationale>Prevent injection attacks</rationale>
  </issue>
</issues>
"""
        result = parse_reviewer_response(raw)
        assert result.verdict == Verdict.NO_GO
        assert len(result.issues) == 2
        assert result.issues[0].severity == Severity.CRITICAL
        assert result.summary == "Critical security gap."

    def test_xml_go(self):
        raw = """
<verdict>GO</verdict>
<summary>Plan is implementation-ready.</summary>
<issues></issues>
"""
        result = parse_reviewer_response(raw)
        assert result.verdict == Verdict.GO


# ---------------------------------------------------------------------------
# 5. Free-form keyword matching
# ---------------------------------------------------------------------------

class TestFreeformKeywordMatching:
    def test_freeform_go(self):
        raw = """
I've reviewed the plan thoroughly. The architecture is sound.

I recommend proceeding with implementation. This plan is ready.
"""
        result = parse_reviewer_response(raw)
        assert result.verdict == Verdict.GO

    def test_freeform_nogo(self):
        raw = """
After reviewing the plan, I believe it needs work before we can proceed.

Key problems:
- critical: No rollback strategy
- major: Missing multi-tenancy support
- minor: Inconsistent naming

This plan is not ready for implementation.
"""
        result = parse_reviewer_response(raw)
        assert result.verdict == Verdict.NO_GO
        assert len(result.issues) == 3

    def test_freeform_extracts_bullet_severities(self):
        raw = """
The plan needs changes.

Issues:
- critical: Missing authentication
- major: No pagination limit
"""
        result = parse_reviewer_response(raw)
        severities = {i.severity for i in result.issues}
        assert Severity.CRITICAL in severities
        assert Severity.MAJOR in severities


# ---------------------------------------------------------------------------
# 6. Malformed / empty inputs
# ---------------------------------------------------------------------------

class TestMalformedAndEmpty:
    def test_empty_string(self):
        result = parse_reviewer_response("")
        assert result.verdict == Verdict.NO_GO
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.CRITICAL

    def test_whitespace_only(self):
        result = parse_reviewer_response("   \n  \t  ")
        assert result.verdict == Verdict.NO_GO
        assert result.issues[0].description == "Reviewer output could not be parsed"

    def test_random_garbage(self):
        result = parse_reviewer_response("asdf 1234 !@#$ random noise ~~~ {{{ ]]]")
        assert result.verdict == Verdict.NO_GO
        assert len(result.issues) == 1

    def test_partial_json_truncated(self):
        raw = '{"verdict": "GO", "issues": [{"severity": "minor", "desc'
        result = parse_reviewer_response(raw)
        assert result.verdict == Verdict.NO_GO  # parse failure


# ---------------------------------------------------------------------------
# 7. Conflicting signals
# ---------------------------------------------------------------------------

class TestConflictingSignals:
    def test_conflicting_go_and_nogo_defaults_to_nogo(self):
        raw = """
Overall this looks good and I'd say GO for the architecture.

However, there are significant issues:
- critical: Token leak vulnerability
- major: No rate limiting

Actually, on reflection, this needs changes before we can proceed.
"""
        result = parse_reviewer_response(raw)
        assert result.verdict == Verdict.NO_GO

    def test_no_go_word_not_matched_as_go(self):
        raw = """
My verdict is NO_GO. The plan has fundamental issues:
- critical: Missing error handling
- major: No test strategy defined
"""
        result = parse_reviewer_response(raw)
        assert result.verdict == Verdict.NO_GO
        assert len(result.issues) == 2


# ---------------------------------------------------------------------------
# 8. Markdown-fenced JSON
# ---------------------------------------------------------------------------

class TestMarkdownFencedJson:
    def test_json_in_markdown_fence(self):
        raw = """Here's my review of the plan:

```json
{
  "verdict": "NO_GO",
  "issues": [
    {
      "severity": "major",
      "description": "Milestone 2 has no test deliverables",
      "rationale": "Every milestone should include test requirements"
    }
  ],
  "summary": "Plan needs test coverage requirements added to Milestone 2."
}
```

Let me know if you'd like me to elaborate.
"""
        result = parse_reviewer_response(raw)
        assert result.verdict == Verdict.NO_GO
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.MAJOR

    def test_json_in_plain_fence(self):
        raw = """Review:

```
{"verdict": "GO", "issues": [], "summary": "Approved."}
```
"""
        result = parse_reviewer_response(raw)
        assert result.verdict == Verdict.GO


# ---------------------------------------------------------------------------
# 9. Unicode content
# ---------------------------------------------------------------------------

class TestUnicodeContent:
    def test_unicode_in_summary(self):
        raw = json.dumps({
            "verdict": "GO",
            "issues": [],
            "summary": "Plan is approved \u2014 architecture looks solid. \u2705 Ready to proceed. Caf\u00e9-style microservices \ud83d\ude0e",
        })
        result = parse_reviewer_response(raw)
        assert result.verdict == Verdict.GO
        assert "\u2014" in result.summary


# ---------------------------------------------------------------------------
# 10. keep / trim extraction
# ---------------------------------------------------------------------------

class TestKeepTrimExtraction:
    def test_keep_trim_parsed_from_json(self):
        raw = json.dumps({
            "verdict": "NO_GO",
            "issues": [_issue("major", "Missing pagination")],
            "summary": "Needs work.",
            "keep": ["Auth flow design", "DB schema"],
            "trim": ["Unnecessary caching layer"],
        })
        result = parse_reviewer_response(raw)
        assert result.keep == ["Auth flow design", "DB schema"]
        assert result.trim == ["Unnecessary caching layer"]

    def test_missing_keep_trim_defaults_to_empty(self):
        raw = json.dumps(_go())
        result = parse_reviewer_response(raw)
        assert result.keep == []
        assert result.trim == []


# ---------------------------------------------------------------------------
# 11. resolution_guidance round-trip
# ---------------------------------------------------------------------------

class TestResolutionGuidance:
    def test_resolution_guidance_round_trip(self):
        raw = json.dumps({
            "verdict": "NO_GO",
            "issues": [
                {
                    "severity": "critical",
                    "description": "No retry logic",
                    "rationale": "Required for prod reliability",
                    "resolution_guidance": "Add exponential backoff in the API client",
                    "target_section": "Milestone 3",
                }
            ],
            "summary": "Needs retry logic.",
        })
        result = parse_reviewer_response(raw)
        assert result.issues[0].resolution_guidance == "Add exponential backoff in the API client"
        assert result.issues[0].target_section == "Milestone 3"

    def test_missing_resolution_guidance_defaults_to_empty(self):
        raw = json.dumps(_nogo([_issue("major", "X")]))
        result = parse_reviewer_response(raw)
        assert result.issues[0].resolution_guidance == ""
        assert result.issues[0].target_section == ""


# ---------------------------------------------------------------------------
# 12. Explicit stage isolation tests
# ---------------------------------------------------------------------------

class TestParsingStages:
    def test_json_stage_succeeds_on_valid_json(self):
        raw = json.dumps(_go())
        result = _try_parse_json(raw)
        assert result is not None
        assert result.verdict == Verdict.GO

    def test_json_stage_returns_none_on_xml(self):
        raw = "<verdict>GO</verdict>"
        result = _try_parse_json(raw)
        # No valid JSON object → returns None
        assert result is None

    def test_xml_stage_succeeds_on_xml(self):
        raw = "<verdict>GO</verdict><summary>ok</summary>"
        result = _try_parse_xml(raw)
        assert result is not None
        assert result.verdict == Verdict.GO

    def test_freeform_stage_returns_none_on_garbage(self):
        result = _try_parse_freeform("asdf 1234 !@#$")
        assert result is None

    def test_make_parse_failure_returns_nogo_critical(self):
        result = _make_parse_failure()
        assert result.verdict == Verdict.NO_GO
        assert result.issues[0].severity == Severity.CRITICAL
