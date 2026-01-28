"""
Security validator for detecting common vulnerabilities.

Checks for:
- SQL injection
- XSS vulnerabilities
- Hardcoded secrets
- Path traversal
- CSRF issues
"""

import re
import time
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any

from .base import BaseValidator, ValidationResult, ValidationIssue, Severity


# Security check patterns
SECURITY_CHECKS: Dict[str, Dict[str, Any]] = {
    "sql_injection": {
        "patterns": [
            # Python
            r'execute\s*\(\s*f["\']',           # f-string in execute
            r'execute\s*\(\s*["\'].*\+',         # String concat in execute
            r'execute\s*\(\s*["\'].*%',          # % formatting in execute
            r'\.format\s*\([^)]*\).*execute',    # .format() before execute
            r'cursor\.execute\s*\([^,]+\+',      # Cursor execute with concat
            # JavaScript/TypeScript
            r'query\s*\(\s*`[^`]*\$\{',          # Template literal in query
            r'query\s*\(\s*["\'].*\+',           # String concat in query
        ],
        "severity": Severity.HIGH,
        "message": "Potential SQL injection vulnerability",
        "recommendation": "Use parameterized queries with placeholders instead of string interpolation",
    },
    "xss_prevention": {
        "patterns": [
            # Direct DOM manipulation
            r'innerHTML\s*=\s*[^"\'\s]',         # Dynamic innerHTML
            r'outerHTML\s*=',                     # Dynamic outerHTML
            r'document\.write\s*\(',              # document.write
            # Framework-specific
            r'dangerouslySetInnerHTML',           # React unescaped
            r'v-html\s*=',                        # Vue unescaped
            r'\[innerHTML\]',                     # Angular unescaped
            r'\{\{\{',                            # Handlebars unescaped
        ],
        "severity": Severity.HIGH,
        "message": "Potential XSS vulnerability - unescaped HTML rendering",
        "recommendation": "Sanitize user input before rendering or use framework's safe rendering methods",
    },
    "secrets_exposure": {
        "patterns": [
            # API keys and tokens
            r'api[_-]?key\s*=\s*["\'][A-Za-z0-9_\-]{20,}["\']',
            r'api[_-]?secret\s*=\s*["\'][A-Za-z0-9_\-]{20,}["\']',
            r'access[_-]?token\s*=\s*["\'][A-Za-z0-9_\-]{20,}["\']',
            r'auth[_-]?token\s*=\s*["\'][A-Za-z0-9_\-]{20,}["\']',
            # Passwords
            r'password\s*=\s*["\'][^"\']{8,}["\']',
            r'passwd\s*=\s*["\'][^"\']{8,}["\']',
            # Private keys
            r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----',
            r'-----BEGIN\s+OPENSSH\s+PRIVATE\s+KEY-----',
            # AWS
            r'AKIA[0-9A-Z]{16}',                  # AWS Access Key ID
            r'aws[_-]?secret[_-]?access[_-]?key\s*=',
        ],
        "severity": Severity.HIGH,
        "message": "Potential hardcoded secret or credential",
        "recommendation": "Move secrets to environment variables or a secrets manager",
    },
    "path_traversal": {
        "patterns": [
            r'open\s*\([^)]*\+[^)]*\)',           # open() with concatenation
            r'Path\s*\([^)]*\+[^)]*\)',           # Path() with concatenation
            r'os\.path\.join\s*\([^)]*request',   # join with request data
            r'\.\./',                              # Literal path traversal
            r'\.\.\\\\',                           # Windows path traversal
        ],
        "severity": Severity.HIGH,
        "message": "Potential path traversal vulnerability",
        "recommendation": "Validate and sanitize file paths, use Path.resolve() and check against allowed directories",
    },
    "command_injection": {
        "patterns": [
            r'subprocess\.(run|call|Popen)\s*\([^)]*shell\s*=\s*True',
            r'os\.system\s*\(',
            r'os\.popen\s*\(',
            r'exec\s*\(\s*[^)]*\+',               # exec with concatenation
            r'eval\s*\(\s*[^)]*\+',               # eval with concatenation
        ],
        "severity": Severity.HIGH,
        "message": "Potential command injection vulnerability",
        "recommendation": "Avoid shell=True, use subprocess with list arguments, never use eval/exec with user input",
    },
}


class SecurityValidator(BaseValidator):
    """
    Validator for security vulnerabilities.

    Analyzes code changes for common security issues like SQL injection,
    XSS, hardcoded secrets, and path traversal.
    """

    name = "security"
    description = "Security vulnerability detection"

    def __init__(
        self,
        severity_threshold: Severity = Severity.MEDIUM,
        enabled_checks: Optional[List[str]] = None,
    ):
        super().__init__(severity_threshold, enabled_checks)
        self.checks = SECURITY_CHECKS

    async def validate(
        self,
        changed_files: List[Path],
        diff: str,
        context: str = "",
        get_file_content: Optional[Callable[[Path], str]] = None,
    ) -> ValidationResult:
        """
        Validate code changes for security issues.

        Primary analysis is on the diff. File content is fetched on-demand
        for context when a potential issue is found.
        """
        start_time = time.time()
        issues: List[ValidationIssue] = []

        # Analyze diff for patterns
        diff_issues = self._analyze_diff(diff)
        issues.extend(diff_issues)

        # If we have file content access, do deeper analysis on flagged files
        if get_file_content and diff_issues:
            flagged_files = set(i.file for i in diff_issues if i.file)
            for file_path in flagged_files:
                if file_path in changed_files:
                    try:
                        content = get_file_content(file_path)
                        file_issues = self._analyze_file(file_path, content)
                        # Deduplicate with diff issues
                        for fi in file_issues:
                            if not any(
                                i.category == fi.category and i.file == fi.file
                                for i in issues
                            ):
                                issues.append(fi)
                    except Exception:
                        pass  # Skip if file can't be read

        # Filter by severity threshold
        filtered_issues = self.filter_issues(issues)

        duration_ms = int((time.time() - start_time) * 1000)

        return ValidationResult(
            validator_name=self.name,
            issues=filtered_issues,
            duration_ms=duration_ms,
        )

    def _analyze_diff(self, diff: str) -> List[ValidationIssue]:
        """Analyze diff for security patterns."""
        issues = []
        current_file = None
        current_line = 0

        for line in diff.split("\n"):
            # Track current file
            if line.startswith("+++ b/"):
                current_file = Path(line[6:])
                current_line = 0
            elif line.startswith("@@ "):
                # Parse line number from @@ -start,count +start,count @@
                match = re.search(r'\+(\d+)', line)
                if match:
                    current_line = int(match.group(1))
            elif line.startswith("+") and not line.startswith("+++"):
                # This is an added line
                added_content = line[1:]
                current_line += 1

                # Check against all patterns
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
                            break  # One issue per line per check

        return issues

    def _analyze_file(
        self, file_path: Path, content: str
    ) -> List[ValidationIssue]:
        """Analyze full file content for security patterns."""
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
