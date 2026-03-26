#!/usr/bin/env python3
"""POC 2a: Go/No-Go Response Parsing

Validate that reviewer responses can be reliably parsed into the
ReviewerResponse schema.

Steps:
  1. Define ReviewerResponse dataclass:
     - verdict: GO | NO_GO
     - issues: list of { severity: critical|major|minor, description, rationale }
     - summary: str
  2. Define parse_reviewer_response(raw_text: str) -> ReviewerResponse
  3. Build test suite of 10+ synthetic responses covering:
     - Clean GO / NO_GO
     - GO with non-blocking notes
     - Malformed / empty / truncated
     - Free-form with keyword matching fallback
     - Conflicting signals
  4. Run each test case through the parser
  5. Compare against expected output
  6. Print pass/fail summary table

Usage:
  python scripts/poc/planner-auto/poc_parse_go_nogo.py
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Verdict(Enum):
    GO = "GO"
    NO_GO = "NO_GO"


class Severity(Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ReviewIssue:
    severity: Severity
    description: str
    rationale: str
    resolution_guidance: str = ""
    target_section: str = ""


@dataclass
class ReviewerResponse:
    verdict: Verdict
    issues: list[ReviewIssue] = field(default_factory=list)
    summary: str = ""
    keep: list[str] = field(default_factory=list)
    trim: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEVERITY_MAP: dict[str, Severity] = {
    "critical": Severity.CRITICAL,
    "major": Severity.MAJOR,
    "minor": Severity.MINOR,
}


def _parse_severity(raw: str) -> Severity:
    """Normalise a severity string into a Severity enum member."""
    return _SEVERITY_MAP.get(raw.strip().lower(), Severity.MAJOR)


def _parse_verdict_string(raw: str) -> Verdict | None:
    """Parse a single verdict token like 'GO', 'NO_GO', etc."""
    cleaned = raw.strip().upper().replace("-", "_")
    if cleaned == "NO_GO":
        return Verdict.NO_GO
    if cleaned == "GO":
        return Verdict.GO
    return None


def _make_parse_failure() -> ReviewerResponse:
    """Return the canonical 'could not parse' fallback response."""
    return ReviewerResponse(
        verdict=Verdict.NO_GO,
        issues=[
            ReviewIssue(
                severity=Severity.CRITICAL,
                description="Reviewer output could not be parsed",
                rationale="The raw response did not match any expected format",
            )
        ],
        summary="Parse failure — treating as NO_GO",
    )


def _issues_from_dicts(raw_issues: list[dict[str, Any]]) -> list[ReviewIssue]:
    """Convert a list of dicts into ReviewIssue objects."""
    issues: list[ReviewIssue] = []
    for item in raw_issues:
        if not isinstance(item, dict):
            continue
        issues.append(
            ReviewIssue(
                severity=_parse_severity(str(item.get("severity", "major"))),
                description=str(item.get("description", "")),
                rationale=str(item.get("rationale", "")),
                resolution_guidance=str(item.get("resolution_guidance", "")),
                target_section=str(item.get("target_section", item.get("target_milestone", ""))),
            )
        )
    return issues


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def _try_parse_json(text: str) -> ReviewerResponse | None:
    """Attempt to parse the response as JSON (possibly embedded in markdown)."""
    # Try to find a JSON block in markdown fences first
    fence_match = re.search(r"```(?:json)?\s*\n(\{.*?\})\s*\n```", text, re.DOTALL)
    candidate = fence_match.group(1) if fence_match else text.strip()

    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        # Try stripping leading/trailing non-JSON characters
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not brace_match:
            return None
        try:
            data = json.loads(brace_match.group(0))
        except (json.JSONDecodeError, ValueError):
            return None

    if not isinstance(data, dict):
        return None

    # Extract verdict
    raw_verdict = data.get("verdict", "")
    verdict = _parse_verdict_string(str(raw_verdict))
    if verdict is None:
        return None

    # Extract issues
    raw_issues = data.get("issues", [])
    issues = _issues_from_dicts(raw_issues) if isinstance(raw_issues, list) else []

    summary = str(data.get("summary", ""))

    # Extract optional keep/trim lists
    raw_keep = data.get("keep", [])
    keep = [str(item) for item in raw_keep] if isinstance(raw_keep, list) else []
    raw_trim = data.get("trim", [])
    trim = [str(item) for item in raw_trim] if isinstance(raw_trim, list) else []

    return ReviewerResponse(verdict=verdict, issues=issues, summary=summary, keep=keep, trim=trim)


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------

def _try_parse_xml(text: str) -> ReviewerResponse | None:
    """Attempt to parse XML-tagged reviewer output."""
    # Look for <verdict> tag
    verdict_match = re.search(r"<verdict>\s*(.*?)\s*</verdict>", text, re.IGNORECASE | re.DOTALL)
    if not verdict_match:
        return None

    verdict = _parse_verdict_string(verdict_match.group(1))
    if verdict is None:
        return None

    # Look for <summary>
    summary_match = re.search(r"<summary>\s*(.*?)\s*</summary>", text, re.IGNORECASE | re.DOTALL)
    summary = summary_match.group(1).strip() if summary_match else ""

    # Look for <issues> block and try to parse individual <issue> elements
    issues: list[ReviewIssue] = []
    issues_match = re.search(r"<issues>(.*?)</issues>", text, re.IGNORECASE | re.DOTALL)
    if issues_match:
        issues_block = issues_match.group(1)
        # Try parsing as XML fragment
        try:
            wrapped = f"<root>{issues_block}</root>"
            root = ET.fromstring(wrapped)
            for issue_el in root.findall("issue"):
                sev_el = issue_el.find("severity")
                desc_el = issue_el.find("description")
                rat_el = issue_el.find("rationale")
                issues.append(
                    ReviewIssue(
                        severity=_parse_severity((sev_el.text or "major") if sev_el is not None else "major"),
                        description=(desc_el.text or "").strip() if desc_el is not None else "",
                        rationale=(rat_el.text or "").strip() if rat_el is not None else "",
                    )
                )
        except ET.ParseError:
            # Fall back to regex for individual issues
            for m in re.finditer(
                r"<issue>.*?<severity>\s*(.*?)\s*</severity>.*?"
                r"<description>\s*(.*?)\s*</description>.*?"
                r"<rationale>\s*(.*?)\s*</rationale>.*?</issue>",
                issues_block,
                re.IGNORECASE | re.DOTALL,
            ):
                issues.append(
                    ReviewIssue(
                        severity=_parse_severity(m.group(1)),
                        description=m.group(2).strip(),
                        rationale=m.group(3).strip(),
                    )
                )

    return ReviewerResponse(verdict=verdict, issues=issues, summary=summary)


# ---------------------------------------------------------------------------
# Free-form / keyword parsing
# ---------------------------------------------------------------------------

_NOGO_PATTERNS = [
    r"\bNO[_\-\s]GO\b",
    r"\bnot\s+ready\b",
    r"\bneeds\s+(?:work|changes|revision)\b",
    r"\bcannot\s+(?:approve|proceed)\b",
    r"\bdo\s+not\s+proceed\b",
    r"\breject(?:ed)?\b",
]

_GO_PATTERNS = [
    r"\bGO\b",  # word-boundary match; NO_GO won't match because _ is \w; conflict handled by _detect_verdict_freeform checking nogo first
    r"\bproceed(?:ing)?\b",
    r"\bready\s+(?:for|to)\b",
    r"\bapproved?\b",
    r"\bgo\s+for\s+implementation\b",
    r"\brecommend\s+proceeding\b",
    r"\bthis\s+plan\s+is\s+ready\b",
    r"\blooks\s+good\b",
]


def _detect_verdict_freeform(text: str) -> Verdict | None:
    """Detect verdict from free-form text using keyword patterns.

    If conflicting signals are found (both GO and NO_GO patterns match),
    default to NO_GO for safety.  Returns None if no verdict patterns are
    detected at all.
    """
    has_nogo = any(re.search(p, text, re.IGNORECASE) for p in _NOGO_PATTERNS)
    has_go = any(re.search(p, text, re.IGNORECASE) for p in _GO_PATTERNS)

    if has_nogo:
        return Verdict.NO_GO
    if has_go:
        return Verdict.GO
    # Neither detected — caller decides what to do
    return None


def _extract_bullet_issues(text: str) -> list[ReviewIssue]:
    """Try to extract bullet-point issues with severity keywords from text."""
    issues: list[ReviewIssue] = []
    # Match lines starting with - or * or numbered bullets
    bullet_pattern = re.compile(
        r"^[\s]*(?:[-*]|\d+[.)])\s+(.+)$", re.MULTILINE
    )
    for m in bullet_pattern.finditer(text):
        line = m.group(1).strip()
        # Check for severity keyword at start or in brackets
        sev_match = re.search(r"\b(critical|major|minor)\b", line, re.IGNORECASE)
        severity = _parse_severity(sev_match.group(1)) if sev_match else Severity.MAJOR
        # Remove the severity keyword from description
        description = re.sub(r"\b(?:critical|major|minor)\b[:\s]*", "", line, count=1, flags=re.IGNORECASE).strip()
        if description:
            issues.append(
                ReviewIssue(
                    severity=severity,
                    description=description,
                    rationale="Extracted from free-form bullet point",
                )
            )
    return issues


def _try_parse_freeform(text: str) -> ReviewerResponse | None:
    """Parse a free-form text response using keyword matching.

    Returns None if no verdict keywords are detected (the text doesn't look
    like a review at all), allowing the caller to fall through to the parse-
    failure path.
    """
    if not text or not text.strip():
        return None

    # If the text looks like failed structured data (starts with { or [),
    # don't attempt freeform keyword matching — the keywords inside JSON/XML
    # fragments would produce false positives.
    stripped = text.strip()
    if stripped.startswith(("{", "[", "<?")):
        return None

    verdict = _detect_verdict_freeform(text)
    if verdict is None:
        # No verdict keywords found — this isn't a review we can parse
        return None

    issues = _extract_bullet_issues(text)

    # Build a summary from the first meaningful line
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    summary = lines[0] if lines else ""
    if len(summary) > 200:
        summary = summary[:197] + "..."

    return ReviewerResponse(verdict=verdict, issues=issues, summary=summary)


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_reviewer_response(raw_text: str) -> ReviewerResponse:
    """Parse raw reviewer output into a structured ReviewerResponse.

    Parsing order:
      1. JSON (possibly in markdown fences)
      2. XML-tagged format
      3. Free-form keyword matching
      4. Fallback: NO_GO with critical parse-failure issue

    Never raises — always returns a valid ReviewerResponse.
    """
    if not raw_text or not raw_text.strip():
        return _make_parse_failure()

    # 1. Try JSON
    result = _try_parse_json(raw_text)
    if result is not None:
        return result

    # 2. Try XML
    result = _try_parse_xml(raw_text)
    if result is not None:
        return result

    # 3. Try free-form
    result = _try_parse_freeform(raw_text)
    if result is not None:
        return result

    # 4. Fallback
    return _make_parse_failure()


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

TEST_CASES: list[dict[str, Any]] = [
    {
        "name": "clean_go_json",
        "input": json.dumps({
            "verdict": "GO",
            "issues": [],
            "summary": "The plan is well-structured and ready for implementation.",
        }),
        "expected_verdict": Verdict.GO,
        "expected_issue_count": 0,
        "notes": "Clean GO response in JSON format, no issues",
    },
    {
        "name": "clean_nogo_json",
        "input": json.dumps({
            "verdict": "NO_GO",
            "issues": [
                {
                    "severity": "critical",
                    "description": "No error handling for API failures",
                    "rationale": "Production services must handle upstream failures gracefully",
                },
                {
                    "severity": "major",
                    "description": "Missing database migration step",
                    "rationale": "Schema changes require explicit migration scripts",
                },
                {
                    "severity": "minor",
                    "description": "Inconsistent naming in module imports",
                    "rationale": "Convention is snake_case for all internal modules",
                },
            ],
            "summary": "Plan has critical gaps in error handling and migration strategy.",
        }),
        "expected_verdict": Verdict.NO_GO,
        "expected_issue_count": 3,
        "notes": "Clean NO_GO in JSON format with 3 issues (1 critical, 1 major, 1 minor)",
    },
    {
        "name": "go_with_notes",
        "input": json.dumps({
            "verdict": "GO",
            "issues": [
                {
                    "severity": "minor",
                    "description": "Consider adding rate limiting in a follow-up",
                    "rationale": "Not blocking, but good to track",
                },
            ],
            "summary": "Plan looks good. One non-blocking suggestion noted.",
        }),
        "expected_verdict": Verdict.GO,
        "expected_issue_count": 1,
        "notes": "GO verdict but includes non-blocking suggestions — treat as GO",
    },
    {
        "name": "nogo_minor_only",
        "input": json.dumps({
            "verdict": "NO_GO",
            "issues": [
                {
                    "severity": "minor",
                    "description": "Logging format inconsistent with project standard",
                    "rationale": "Should follow structured logging pattern",
                },
                {
                    "severity": "minor",
                    "description": "Test coverage target not specified",
                    "rationale": "Need explicit coverage targets for CI gate",
                },
            ],
            "summary": "Several minor issues need addressing before proceeding.",
        }),
        "expected_verdict": Verdict.NO_GO,
        "expected_issue_count": 2,
        "notes": "NO_GO with only minor issues — still NO_GO per spec",
    },
    {
        "name": "xml_tagged_nogo",
        "input": """
<verdict>NO_GO</verdict>
<summary>The plan has a critical security gap.</summary>
<issues>
  <issue>
    <severity>critical</severity>
    <description>Authentication tokens are stored in plain text</description>
    <rationale>Tokens must be encrypted at rest per security policy</rationale>
  </issue>
  <issue>
    <severity>major</severity>
    <description>No input validation on user-facing endpoints</description>
    <rationale>All inputs must be validated to prevent injection attacks</rationale>
  </issue>
</issues>
""",
        "expected_verdict": Verdict.NO_GO,
        "expected_issue_count": 2,
        "notes": "Response uses XML tags for structure",
    },
    {
        "name": "freeform_go",
        "input": """
I've reviewed the implementation plan thoroughly. The architecture is sound,
the milestones are well-scoped, and the testing strategy is comprehensive.

I recommend proceeding with implementation. This plan is ready.

A few optional things to consider later:
- Could add OpenTelemetry tracing in a future iteration
- Documentation could be more detailed for the auth flow
""",
        "expected_verdict": Verdict.GO,
        "expected_issue_count": 2,  # approximate — the two bullet points
        "notes": "Free-form paragraph with 'recommend proceeding' / 'plan is ready'",
    },
    {
        "name": "freeform_nogo",
        "input": """
After reviewing the plan, I believe it needs work before we can proceed.

Key problems:
- critical: No rollback strategy if deployment fails
- major: The database schema doesn't account for multi-tenancy
- minor: Variable naming is inconsistent across modules

This plan is not ready for implementation.
""",
        "expected_verdict": Verdict.NO_GO,
        "expected_issue_count": 3,
        "notes": "Free-form paragraph listing problems, says 'not ready' / 'needs work'",
    },
    {
        "name": "malformed_empty",
        "input": "",
        "expected_verdict": Verdict.NO_GO,
        "expected_issue_count": 1,
        "notes": "Empty string — parse failure, single critical issue",
    },
    {
        "name": "malformed_garbage",
        "input": "asdf 1234 !@#$ random noise ~~~ {{{ ]]]",
        "expected_verdict": Verdict.NO_GO,
        "expected_issue_count": 1,  # parse failure critical issue
        "notes": "Random non-review text — should be NO_GO with parse failure issue",
    },
    {
        "name": "partial_json",
        "input": '{"verdict": "GO", "issues": [{"severity": "minor", "desc',
        "expected_verdict": Verdict.NO_GO,
        "expected_issue_count": 1,  # parse failure
        "notes": "Valid JSON start but truncated — cannot parse, falls to freeform/failure",
    },
    {
        "name": "conflicting_signals",
        "input": """
Overall this looks good and I'd say GO for the architecture.

However, there are significant issues that need to be addressed:
- critical: The authentication flow has a token leak vulnerability
- major: No rate limiting on public endpoints

Actually, on reflection, this needs changes before we can proceed.
""",
        "expected_verdict": Verdict.NO_GO,
        "expected_issue_count": 2,
        "notes": "Says 'GO' in one place and 'needs changes' in another — default to NO_GO",
    },
    {
        "name": "go_embedded_in_nogo_word",
        "input": """
My verdict is NO_GO. The plan has fundamental issues:
- critical: Missing error handling
- major: No test strategy defined
""",
        "expected_verdict": Verdict.NO_GO,
        "expected_issue_count": 2,
        "notes": "Text contains 'NO_GO' — should not false-match as GO (word boundary test)",
    },
    {
        "name": "markdown_fenced_json",
        "input": """Here's my review of the plan:

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

Let me know if you'd like me to elaborate on any of these points.
""",
        "expected_verdict": Verdict.NO_GO,
        "expected_issue_count": 1,
        "notes": "JSON embedded in markdown code fences — most likely real-world GPT format",
    },
    {
        "name": "unicode_response",
        "input": json.dumps({
            "verdict": "GO",
            "issues": [],
            "summary": "Plan is approved \u2014 architecture looks solid. \u2705 Ready to proceed. Caf\u00e9-style microservices \ud83d\ude0e",
        }),
        "expected_verdict": Verdict.GO,
        "expected_issue_count": 0,
        "notes": "Response with unicode characters (em-dash, checkmark, emoji), still parseable",
    },
]


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """Execute all test cases and print a summary table."""
    print("POC 2a: Go/No-Go Response Parsing")
    print("\u2550" * 78)

    header = (
        f"{'#':>2} \u2502 {'Test Name':<26} \u2502 {'Expected':<9} \u2502 "
        f"{'Actual':<9} \u2502 {'Issues':>6} \u2502 Result"
    )
    separator = (
        f"{'':->3}\u253c{'':->28}\u253c{'':->11}\u253c"
        f"{'':->11}\u253c{'':->8}\u253c{'':->8}"
    )

    print(header)
    print(separator)

    passed = 0
    total = len(TEST_CASES)

    for i, tc in enumerate(TEST_CASES, 1):
        result = parse_reviewer_response(tc["input"])

        verdict_ok = result.verdict == tc["expected_verdict"]
        issues_ok = len(result.issues) == tc["expected_issue_count"]
        test_passed = verdict_ok and issues_ok

        if test_passed:
            passed += 1

        status = "PASS" if test_passed else "FAIL"
        actual_verdict = result.verdict.value
        expected_verdict = tc["expected_verdict"].value

        line = (
            f"{i:>2} \u2502 {tc['name']:<26} \u2502 {expected_verdict:<9} \u2502 "
            f"{actual_verdict:<9} \u2502 {len(result.issues):>6} \u2502 {status}"
        )
        print(line)

        if not test_passed:
            if not verdict_ok:
                print(f"   \u2502 {'':26} \u2502 \u2191 verdict mismatch")
            if not issues_ok:
                print(
                    f"   \u2502 {'':26} \u2502 \u2191 expected {tc['expected_issue_count']} "
                    f"issues, got {len(result.issues)}"
                )
            # Show issues for debugging
            for iss in result.issues:
                print(f"   \u2502   - [{iss.severity.value}] {iss.description}")

    print("\u2550" * 78)
    print(f"Results: {passed}/{total} passed")

    if passed < total:
        print(f"\n{total - passed} test(s) FAILED. Review output above.")
    else:
        print("\nAll tests passed.")


if __name__ == "__main__":
    _run_tests()
