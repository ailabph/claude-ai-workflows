"""
Performance validator for detecting anti-patterns.

Checks for:
- N+1 query patterns
- Unbounded queries (missing LIMIT)
- Sync operations in async code
- Missing indexes hints
- Memory leak patterns
"""

import re
import time
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any

from .base import BaseValidator, ValidationResult, ValidationIssue, Severity


# Performance check patterns
# Note: "multiline": True indicates patterns that span multiple lines and should
# only be checked against aggregated content, not individual diff lines.
PERFORMANCE_CHECKS: Dict[str, Dict[str, Any]] = {
    "n_plus_one": {
        "patterns": [
            # Query in loop patterns (multiline - span for...query)
            r'for\s+\w+\s+in\s+.*:\s*\n\s*.*\.(query|execute|filter|get)\s*\(',
            r'for\s+\w+\s+in\s+.*:\s*\n\s*.*\.objects\.',
            r'\.forEach\s*\([^)]*\)\s*=>\s*\{[^}]*fetch\s*\(',
            r'\.map\s*\([^)]*\)\s*=>\s*\{[^}]*query\s*\(',
            # Nested query patterns
            r'SELECT.*FROM.*WHERE.*IN\s*\(\s*SELECT',
        ],
        "multiline": True,  # Patterns span multiple lines
        "severity": Severity.HIGH,
        "message": "Potential N+1 query pattern detected",
        "recommendation": "Use eager loading, batch queries, or joins instead of queries in loops",
    },
    "unbounded_query": {
        "patterns": [
            # SELECT without LIMIT
            r'SELECT\s+\*\s+FROM\s+\w+\s*(?!.*LIMIT)',
            r'\.all\(\)\s*$',                     # Django .all() without limit
            r'\.find\(\{\}\)',                    # MongoDB find all
            r'\.objects\.filter\([^)]*\)(?!\s*\[)', # Django filter without slice
        ],
        "multiline": False,  # Single-line patterns
        "severity": Severity.MEDIUM,
        "message": "Query without LIMIT may return unbounded results",
        "recommendation": "Add LIMIT clause or use pagination for large tables",
    },
    "sync_in_async": {
        "patterns": [
            # Blocking calls in async functions (multiline - span def...call)
            r'async\s+def\s+\w+[^:]*:\s*\n(?:[^#\n]*\n)*?\s*time\.sleep\s*\(',
            r'async\s+def\s+\w+[^:]*:\s*\n(?:[^#\n]*\n)*?\s*requests\.(get|post|put)',
            r'async\s+def\s+\w+[^:]*:\s*\n(?:[^#\n]*\n)*?\s*open\s*\(',
            r'await\s+.*\bsync\b',
        ],
        "multiline": True,  # Most patterns span multiple lines
        "severity": Severity.MEDIUM,
        "message": "Blocking operation in async context",
        "recommendation": "Use async versions: asyncio.sleep, aiohttp, aiofiles",
    },
    "missing_index_hint": {
        "patterns": [
            # Queries on likely-indexed columns without hints
            r'WHERE\s+\w+_id\s*=',                # FK lookup
            r'WHERE\s+created_at\s*[<>]',         # Date range query
            r'WHERE\s+status\s*=',                # Status field
            r'ORDER\s+BY\s+created_at',           # Ordering by date
        ],
        "multiline": False,  # Single-line patterns
        "severity": Severity.LOW,
        "message": "Query pattern suggests an index may be beneficial",
        "recommendation": "Verify database indexes exist for frequently queried columns",
    },
    "large_object_in_memory": {
        "patterns": [
            # Loading large data into memory
            r'\.read\(\)\s*$',                    # Read entire file
            r'json\.load\s*\(\s*open\s*\(',       # Load entire JSON
            r'list\(\s*.*\.all\(\)\s*\)',         # Materialize entire queryset
            r'pd\.read_csv\s*\([^)]*\)(?!\s*,\s*chunksize)', # Pandas without chunks
        ],
        "multiline": False,  # Single-line patterns
        "severity": Severity.MEDIUM,
        "message": "Large object loaded entirely into memory",
        "recommendation": "Use streaming, chunking, or iterators for large data",
    },
    "unclosed_resource": {
        "patterns": [
            # Resources opened without context manager
            r'(?<!with\s)open\s*\([^)]+\)\s*(?!\s*as\s)',
            r'(?<!with\s)connection\s*=\s*\w+\.connect\(',
            r'cursor\s*=\s*\w+\.cursor\(\)(?!.*finally)',
        ],
        "multiline": False,  # Single-line patterns
        "severity": Severity.MEDIUM,
        "message": "Resource opened without context manager",
        "recommendation": "Use 'with' statement or ensure proper cleanup in finally block",
    },
}


class PerformanceValidator(BaseValidator):
    """
    Validator for performance anti-patterns.

    Analyzes code changes for common performance issues like N+1 queries,
    unbounded queries, and blocking operations in async code.
    """

    name = "performance"
    description = "Performance anti-pattern detection"

    def __init__(
        self,
        severity_threshold: Severity = Severity.HIGH,
        enabled_checks: Optional[List[str]] = None,
    ):
        super().__init__(severity_threshold, enabled_checks)
        self.checks = PERFORMANCE_CHECKS

    async def validate(
        self,
        changed_files: List[Path],
        diff: str,
        context: str = "",
        get_file_content: Optional[Callable[[Path], str]] = None,
    ) -> ValidationResult:
        """
        Validate code changes for performance issues.

        Analyzes diff for anti-patterns. Some patterns require multi-line
        analysis which may need file content.
        """
        start_time = time.time()
        issues: List[ValidationIssue] = []

        # Analyze diff for patterns
        diff_issues = self._analyze_diff(diff)
        issues.extend(diff_issues)

        # For multi-line patterns, analyze file content if available
        if get_file_content:
            for file_path in changed_files:
                # Only analyze Python and JS/TS files
                if file_path.suffix in (".py", ".js", ".ts", ".jsx", ".tsx"):
                    try:
                        content = get_file_content(file_path)
                        file_issues = self._analyze_file_multiline(file_path, content)
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

    def _analyze_diff(self, diff: str) -> List[ValidationIssue]:
        """Analyze diff for performance patterns."""
        issues = []
        current_file = None
        current_line = 0

        # Build added content blocks for multi-line analysis
        added_blocks: Dict[Path, List[str]] = {}

        for line in diff.split("\n"):
            if line.startswith("+++ b/"):
                current_file = Path(line[6:])
                if current_file not in added_blocks:
                    added_blocks[current_file] = []
            elif line.startswith("@@ "):
                match = re.search(r'\+(\d+)', line)
                if match:
                    current_line = int(match.group(1))
            elif line.startswith("+") and not line.startswith("+++"):
                added_content = line[1:]
                current_line += 1

                if current_file:
                    added_blocks[current_file].append(added_content)

                # Single-line pattern checks only (skip multiline patterns)
                for check_name, check_info in self.checks.items():
                    if not self.should_run_check(check_name):
                        continue

                    # Skip multiline patterns - they're checked on aggregated content
                    if check_info.get("multiline", False):
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

        # Multi-line pattern checks on added blocks (only for multiline patterns)
        for file_path, lines in added_blocks.items():
            content = "\n".join(lines)
            for check_name, check_info in self.checks.items():
                if not self.should_run_check(check_name):
                    continue

                # Only run multiline patterns here
                if not check_info.get("multiline", False):
                    continue

                for pattern in check_info["patterns"]:
                    if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                        issues.append(
                            ValidationIssue(
                                severity=check_info["severity"],
                                category=check_name,
                                message=check_info["message"],
                                file=file_path,
                                recommendation=check_info["recommendation"],
                            )
                        )
                        break

        return issues

    def _analyze_file_multiline(
        self, file_path: Path, content: str
    ) -> List[ValidationIssue]:
        """Analyze file for multi-line patterns."""
        issues = []

        for check_name, check_info in self.checks.items():
            if not self.should_run_check(check_name):
                continue

            for pattern in check_info["patterns"]:
                matches = list(re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE))
                for match in matches:
                    # Calculate line number
                    line_num = content[:match.start()].count("\n") + 1
                    issues.append(
                        ValidationIssue(
                            severity=check_info["severity"],
                            category=check_name,
                            message=check_info["message"],
                            file=file_path,
                            line=line_num,
                            recommendation=check_info["recommendation"],
                            snippet=match.group(0)[:100],
                        )
                    )

        return issues
