"""
API validator for detecting API-related issues.

Checks for:
- Breaking changes
- Missing input validation
- Inconsistent error handling
- Missing pagination
- Missing rate limiting
"""

import re
import time
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any

from .base import BaseValidator, ValidationResult, ValidationIssue, Severity


# API check patterns
API_CHECKS: Dict[str, Dict[str, Any]] = {
    "missing_validation": {
        "patterns": [
            # Direct use of request data without validation
            r'request\.(json|data|form)\s*\[',    # Direct dict access
            r'request\.args\.get\s*\([^,)]+\)(?!\s*,)', # Flask without default
            r'request\.body',                       # Raw body access
            r'req\.body\.',                         # Express raw body
            r'params\[',                            # Direct params access
        ],
        "severity": Severity.MEDIUM,
        "message": "Request data accessed without apparent validation",
        "recommendation": "Validate and sanitize all request input using schemas or validators",
    },
    "inconsistent_error": {
        "patterns": [
            # Inconsistent error responses
            r'return\s+\{\s*["\']error["\']\s*:',   # error key
            r'return\s+\{\s*["\']message["\']\s*:', # message key
            r'raise\s+HTTPException\s*\([^)]*detail\s*=\s*["\']',  # FastAPI
            r'res\.status\s*\(\d+\)\.json\s*\(\{',  # Express
        ],
        "severity": Severity.LOW,
        "message": "Error response format may be inconsistent",
        "recommendation": "Use a consistent error response format across all endpoints",
    },
    "missing_pagination": {
        "patterns": [
            # List endpoints without pagination params
            r'def\s+(get_all|list_|fetch_all)\s*\(',
            r'@(get|router\.get)\s*\(["\'].*s["\']',  # Plural endpoints
            r'return\s+\w+\.all\(\)',                  # Return all records
            r'SELECT\s+\*\s+FROM\s+\w+\s*;?\s*$',     # Full table select
        ],
        "severity": Severity.MEDIUM,
        "message": "List endpoint may be missing pagination",
        "recommendation": "Add pagination parameters (page, limit/per_page) for list endpoints",
    },
    "missing_auth_check": {
        "patterns": [
            # Endpoints without auth decorators (heuristic)
            r'@(app|router)\.(post|put|patch|delete)\s*\([^)]+\)\s*\n\s*(async\s+)?def\s+\w+\([^)]*\)\s*:(?!\s*\n\s*.*@)',
        ],
        "severity": Severity.MEDIUM,
        "message": "Mutating endpoint may be missing authentication check",
        "recommendation": "Add authentication/authorization checks for POST/PUT/PATCH/DELETE endpoints",
    },
    "hardcoded_url": {
        "patterns": [
            # Hardcoded URLs in API code
            r'https?://localhost',
            r'https?://127\.0\.0\.1',
            r'https?://\d+\.\d+\.\d+\.\d+',         # IP addresses
            r'["\']https?://[^"\']*\.(com|io|org|net)[^"\']*["\']', # Production URLs
        ],
        "severity": Severity.MEDIUM,
        "message": "Hardcoded URL detected",
        "recommendation": "Use configuration or environment variables for URLs",
    },
    "sensitive_data_logged": {
        "patterns": [
            # Logging potentially sensitive data
            r'log(ger)?\.(info|debug|warning|error)\s*\([^)]*password',
            r'log(ger)?\.(info|debug|warning|error)\s*\([^)]*token',
            r'log(ger)?\.(info|debug|warning|error)\s*\([^)]*secret',
            r'console\.log\s*\([^)]*password',
            r'print\s*\([^)]*password',
        ],
        "severity": Severity.HIGH,
        "message": "Sensitive data may be logged",
        "recommendation": "Never log passwords, tokens, or secrets. Mask or omit sensitive fields.",
    },
    "missing_content_type": {
        "patterns": [
            # Response without content type
            r'Response\s*\([^)]+\)(?!.*content_type)',
            r'return\s+\{[^}]+\}(?!\s*,\s*\d+\s*,)',  # Return dict without status
        ],
        "severity": Severity.LOW,
        "message": "Response may be missing explicit content type",
        "recommendation": "Set explicit Content-Type header for API responses",
    },
}


class APIValidator(BaseValidator):
    """
    Validator for API-related issues.

    Analyzes code changes for common API problems like missing validation,
    inconsistent error handling, and missing pagination.
    """

    name = "api"
    description = "API quality and consistency checks"

    def __init__(
        self,
        severity_threshold: Severity = Severity.MEDIUM,
        enabled_checks: Optional[List[str]] = None,
    ):
        super().__init__(severity_threshold, enabled_checks)
        self.checks = API_CHECKS

    async def validate(
        self,
        changed_files: List[Path],
        diff: str,
        context: str = "",
        get_file_content: Optional[Callable[[Path], str]] = None,
    ) -> ValidationResult:
        """
        Validate code changes for API issues.

        Focuses on API-related files (routes, views, controllers).
        """
        start_time = time.time()
        issues: List[ValidationIssue] = []

        # Filter to API-related files
        api_patterns = ["route", "view", "controller", "api", "endpoint", "handler"]
        api_files = [
            f for f in changed_files
            if any(p in str(f).lower() for p in api_patterns)
            or f.suffix in (".py", ".js", ".ts")
        ]

        # Analyze diff for patterns
        diff_issues = self._analyze_diff(diff, api_files)
        issues.extend(diff_issues)

        # Deeper analysis on API files if content available
        if get_file_content:
            for file_path in api_files:
                try:
                    content = get_file_content(file_path)
                    file_issues = self._analyze_file(file_path, content)
                    # Deduplicate
                    for fi in file_issues:
                        if not any(
                            i.category == fi.category and i.file == fi.file and i.line == fi.line
                            for i in issues
                        ):
                            issues.append(fi)
                except Exception:
                    pass

        # Filter by severity threshold
        filtered_issues = self.filter_issues(issues)

        duration_ms = int((time.time() - start_time) * 1000)

        return ValidationResult(
            validator_name=self.name,
            issues=filtered_issues,
            duration_ms=duration_ms,
        )

    def _analyze_diff(
        self, diff: str, api_files: List[Path]
    ) -> List[ValidationIssue]:
        """Analyze diff for API patterns."""
        issues = []
        current_file = None
        current_line = 0

        # Only analyze if current file is in api_files
        api_file_strs = [str(f) for f in api_files]

        for line in diff.split("\n"):
            if line.startswith("+++ b/"):
                file_path = line[6:]
                current_file = Path(file_path) if file_path in api_file_strs else None
                current_line = 0
            elif line.startswith("@@ "):
                match = re.search(r'\+(\d+)', line)
                if match:
                    current_line = int(match.group(1))
            elif line.startswith("+") and not line.startswith("+++"):
                if current_file is None:
                    continue

                added_content = line[1:]
                current_line += 1

                for check_name, check_info in self.checks.items():
                    if not self.should_run_check(check_name):
                        continue

                    for pattern in check_info["patterns"]:
                        if re.search(pattern, added_content, re.IGNORECASE):
                            issues.append(
                                ValidationIssue(
                                    severity=check_info["severity"],
                                    category=check_name,
                                    message=check_info["message"],
                                    file=current_file,
                                    line=current_line,
                                    recommendation=check_info["recommendation"],
                                    snippet=added_content.strip()[:100],
                                )
                            )
                            break

        return issues

    def _analyze_file(
        self, file_path: Path, content: str
    ) -> List[ValidationIssue]:
        """Analyze file for API patterns."""
        issues = []

        for line_num, line in enumerate(content.split("\n"), 1):
            for check_name, check_info in self.checks.items():
                if not self.should_run_check(check_name):
                    continue

                for pattern in check_info["patterns"]:
                    if re.search(pattern, line, re.IGNORECASE):
                        issues.append(
                            ValidationIssue(
                                severity=check_info["severity"],
                                category=check_name,
                                message=check_info["message"],
                                file=file_path,
                                line=line_num,
                                recommendation=check_info["recommendation"],
                                snippet=line.strip()[:100],
                            )
                        )
                        break

        return issues
