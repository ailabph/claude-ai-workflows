"""Reviewer response parser with three-stage fallback.

Parsing order:
  1. JSON (raw or markdown-fenced ``json`` block)
  2. XML-tagged format (``<verdict>``, ``<issues>``, ``<summary>`` tags)
  3. Free-form keyword matching (sentence-level GO/NO_GO signals + bullet issues)
  4. Fallback: NO_GO with a single CRITICAL "could not be parsed" issue

Never raises — ``parse_reviewer_response()`` always returns a valid
``ReviewerResponse``.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Optional

from planner_auto.reviewer.contract import (
    ReviewIssue,
    ReviewerResponse,
    Severity,
    Verdict,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEVERITY_MAP: dict[str, Severity] = {
    "critical": Severity.CRITICAL,
    "major": Severity.MAJOR,
    "minor": Severity.MINOR,
}


def _parse_severity(raw: str) -> Severity:
    """Normalise a severity string into a Severity enum member.

    Falls back to MAJOR for unrecognised strings.
    """
    return _SEVERITY_MAP.get(raw.strip().lower(), Severity.MAJOR)


def _parse_verdict_string(raw: str) -> Optional[Verdict]:
    """Parse a single verdict token like 'GO', 'NO_GO', 'NO-GO', etc."""
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
                target_section=str(
                    item.get("target_section", item.get("target_milestone", ""))
                ),
            )
        )
    return issues


# ---------------------------------------------------------------------------
# Stage 1: JSON parsing
# ---------------------------------------------------------------------------

def _try_parse_json(text: str) -> Optional[ReviewerResponse]:
    """Attempt to parse the response as JSON (possibly embedded in markdown).

    Handles:
    - Raw JSON objects
    - JSON embedded in ```json ... ``` markdown fences
    - JSON embedded in ``` ... ``` plain fences
    - JSON embedded anywhere in the text (brace-extraction fallback)
    """
    # 1a. Try markdown-fenced JSON first.
    fence_match = re.search(r"```(?:json)?\s*\n(\{.*?\})\s*\n```", text, re.DOTALL)
    candidate = fence_match.group(1) if fence_match else text.strip()

    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        # 1b. Try extracting the outermost JSON object from anywhere in the text.
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not brace_match:
            return None
        try:
            data = json.loads(brace_match.group(0))
        except (json.JSONDecodeError, ValueError):
            return None

    if not isinstance(data, dict):
        return None

    # Extract verdict (required).
    raw_verdict = data.get("verdict", "")
    verdict = _parse_verdict_string(str(raw_verdict))
    if verdict is None:
        return None

    # Extract issues list.
    raw_issues = data.get("issues", [])
    issues = _issues_from_dicts(raw_issues) if isinstance(raw_issues, list) else []

    summary = str(data.get("summary", ""))

    # Extract optional keep/trim lists.
    raw_keep = data.get("keep", [])
    keep = [str(item) for item in raw_keep] if isinstance(raw_keep, list) else []
    raw_trim = data.get("trim", [])
    trim = [str(item) for item in raw_trim] if isinstance(raw_trim, list) else []

    return ReviewerResponse(
        verdict=verdict, issues=issues, summary=summary, keep=keep, trim=trim
    )


# ---------------------------------------------------------------------------
# Stage 2: XML parsing
# ---------------------------------------------------------------------------

def _try_parse_xml(text: str) -> Optional[ReviewerResponse]:
    """Attempt to parse XML-tagged reviewer output.

    Looks for ``<verdict>``, ``<summary>``, and ``<issues>`` tags.
    Issue XML is first tried as a well-formed fragment; falls back to
    regex-based extraction if the fragment is not well-formed.
    """
    # Verdict tag is required.
    verdict_match = re.search(
        r"<verdict>\s*(.*?)\s*</verdict>", text, re.IGNORECASE | re.DOTALL
    )
    if not verdict_match:
        return None

    verdict = _parse_verdict_string(verdict_match.group(1))
    if verdict is None:
        return None

    # Summary tag (optional).
    summary_match = re.search(
        r"<summary>\s*(.*?)\s*</summary>", text, re.IGNORECASE | re.DOTALL
    )
    summary = summary_match.group(1).strip() if summary_match else ""

    # Issues block (optional).
    issues: list[ReviewIssue] = []
    issues_match = re.search(
        r"<issues>(.*?)</issues>", text, re.IGNORECASE | re.DOTALL
    )
    if issues_match:
        issues_block = issues_match.group(1)
        # Try parsing as an XML fragment first.
        try:
            root = ET.fromstring(f"<root>{issues_block}</root>")
            for issue_el in root.findall("issue"):
                sev_el = issue_el.find("severity")
                desc_el = issue_el.find("description")
                rat_el = issue_el.find("rationale")
                res_el = issue_el.find("resolution_guidance")
                sec_el = issue_el.find("target_section")
                issues.append(
                    ReviewIssue(
                        severity=_parse_severity(
                            (sev_el.text or "major") if sev_el is not None else "major"
                        ),
                        description=(desc_el.text or "").strip()
                        if desc_el is not None
                        else "",
                        rationale=(rat_el.text or "").strip()
                        if rat_el is not None
                        else "",
                        resolution_guidance=(res_el.text or "").strip()
                        if res_el is not None
                        else "",
                        target_section=(sec_el.text or "").strip()
                        if sec_el is not None
                        else "",
                    )
                )
        except ET.ParseError:
            # Fall back to regex extraction of individual <issue> elements.
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
# Stage 3: Free-form / keyword matching
# ---------------------------------------------------------------------------

# Patterns that indicate NO_GO (checked before GO patterns to handle overlap).
_NOGO_PATTERNS = [
    r"\bNO[_\-\s]GO\b",
    r"\bnot\s+ready\b",
    r"\bneeds\s+(?:work|changes|revision)\b",
    r"\bcannot\s+(?:approve|proceed)\b",
    r"\bdo\s+not\s+proceed\b",
    r"\breject(?:ed)?\b",
]

# Patterns that indicate GO.
_GO_PATTERNS = [
    r"\bGO\b",
    r"\bproceed(?:ing)?\b",
    r"\bready\s+(?:for|to)\b",
    r"\bapproved?\b",
    r"\bgo\s+for\s+implementation\b",
    r"\brecommend\s+proceeding\b",
    r"\bthis\s+plan\s+is\s+ready\b",
    r"\blooks\s+good\b",
]


def _detect_verdict_freeform(text: str) -> Optional[Verdict]:
    """Detect verdict from free-form text using keyword patterns.

    When conflicting signals are found (both GO and NO_GO patterns match),
    defaults to NO_GO for safety.  Returns ``None`` when no verdict patterns
    are detected at all.
    """
    has_nogo = any(re.search(p, text, re.IGNORECASE) for p in _NOGO_PATTERNS)
    has_go = any(re.search(p, text, re.IGNORECASE) for p in _GO_PATTERNS)

    if has_nogo:
        # NO_GO takes precedence over conflicting GO signals.
        return Verdict.NO_GO
    if has_go:
        return Verdict.GO
    return None  # No verdict keywords detected.


def _extract_bullet_issues(text: str) -> list[ReviewIssue]:
    """Extract bullet-point issues with optional severity keywords from text."""
    issues: list[ReviewIssue] = []
    bullet_pattern = re.compile(r"^[\s]*(?:[-*]|\d+[.)])\s+(.+)$", re.MULTILINE)
    for m in bullet_pattern.finditer(text):
        line = m.group(1).strip()
        # Detect inline severity keyword.
        sev_match = re.search(r"\b(critical|major|minor)\b", line, re.IGNORECASE)
        severity = _parse_severity(sev_match.group(1)) if sev_match else Severity.MAJOR
        # Strip the severity keyword token from the description.
        description = re.sub(
            r"\b(?:critical|major|minor)\b[:\s]*", "", line, count=1, flags=re.IGNORECASE
        ).strip()
        if description:
            issues.append(
                ReviewIssue(
                    severity=severity,
                    description=description,
                    rationale="Extracted from free-form bullet point",
                )
            )
    return issues


def _try_parse_freeform(text: str) -> Optional[ReviewerResponse]:
    """Parse a free-form text response using keyword matching.

    Returns ``None`` if no verdict keywords are detected (the text does not
    look like a review), allowing the caller to fall through to the parse-
    failure path.

    Does NOT attempt free-form parsing when the text looks like failed
    structured data (starts with ``{``, ``[``, or ``<?``) to avoid
    false positives from keyword-like strings inside JSON/XML.
    """
    if not text or not text.strip():
        return None

    stripped = text.strip()
    # If the text looks like failed structured data, skip free-form matching.
    if stripped.startswith(("{", "[", "<?")):
        return None

    verdict = _detect_verdict_freeform(text)
    if verdict is None:
        return None  # No actionable verdict signals found.

    issues = _extract_bullet_issues(text)

    # Build summary from the first meaningful line (capped at 200 chars).
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    summary = lines[0] if lines else ""
    if len(summary) > 200:
        summary = summary[:197] + "..."

    return ReviewerResponse(verdict=verdict, issues=issues, summary=summary)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_reviewer_response(raw_text: str) -> ReviewerResponse:
    """Parse raw reviewer output into a structured ReviewerResponse.

    Parsing order:
      1. JSON (raw or markdown-fenced)
      2. XML-tagged format
      3. Free-form keyword matching
      4. Fallback: NO_GO with a CRITICAL "could not be parsed" issue

    Never raises.  Always returns a valid :class:`ReviewerResponse`.

    Args:
        raw_text: Raw text output from the reviewer model.

    Returns:
        A :class:`ReviewerResponse` with a verdict and any extracted issues.
    """
    if not raw_text or not raw_text.strip():
        logger.debug("Parsed as failure: empty input")
        return _make_parse_failure()

    # Stage 1: JSON
    result = _try_parse_json(raw_text)
    if result is not None:
        logger.debug("Parsed as JSON")
        return result

    logger.debug("JSON parse failed, trying XML")

    # Stage 2: XML
    result = _try_parse_xml(raw_text)
    if result is not None:
        logger.debug("Parsed as XML")
        return result

    logger.debug("XML parse failed, trying free-form")

    # Stage 3: Free-form
    result = _try_parse_freeform(raw_text)
    if result is not None:
        logger.debug("Parsed as free-form")
        return result

    # Stage 4: Parse failure
    logger.debug("Parsed as failure: no format matched")
    return _make_parse_failure()
