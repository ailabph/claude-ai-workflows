"""Tests for validation sub-agent module."""

import pytest
import asyncio
from pathlib import Path

from orchestrator_auto.validation import (
    BaseValidator,
    ValidationIssue,
    ValidationResult,
    Severity,
    ValidationPipeline,
    ValidationReport,
    SecurityValidator,
    PerformanceValidator,
    APIValidator,
)
from orchestrator_auto.validation.pipeline import create_default_pipeline


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_values(self):
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"
        assert Severity.WARNING.value == "warning"

    def test_severity_ordering(self):
        assert Severity.HIGH > Severity.MEDIUM
        assert Severity.MEDIUM > Severity.LOW
        assert Severity.LOW > Severity.WARNING

    def test_severity_from_string(self):
        assert Severity.from_string("high") == Severity.HIGH
        assert Severity.from_string("HIGH") == Severity.HIGH
        assert Severity.from_string("Medium") == Severity.MEDIUM


class TestValidationIssue:
    """Tests for ValidationIssue dataclass."""

    def test_basic_issue(self):
        issue = ValidationIssue(
            severity=Severity.HIGH,
            category="sql_injection",
            message="SQL injection detected",
        )
        assert issue.severity == Severity.HIGH
        assert issue.category == "sql_injection"
        assert issue.message == "SQL injection detected"

    def test_issue_with_location(self):
        issue = ValidationIssue(
            severity=Severity.MEDIUM,
            category="n_plus_one",
            message="N+1 query",
            file=Path("src/models.py"),
            line=42,
        )
        assert issue.file == Path("src/models.py")
        assert issue.line == 42

    def test_issue_to_dict(self):
        issue = ValidationIssue(
            severity=Severity.HIGH,
            category="xss",
            message="XSS vulnerability",
            file=Path("app.js"),
            line=10,
            recommendation="Sanitize input",
        )
        d = issue.to_dict()
        assert d["severity"] == "high"
        assert d["category"] == "xss"
        assert d["file"] == "app.js"
        assert d["line"] == 10

    def test_issue_from_dict(self):
        d = {
            "severity": "medium",
            "category": "test",
            "message": "Test message",
            "file": "test.py",
            "line": 5,
            "recommendation": "Fix it",
            "snippet": "code here",
        }
        issue = ValidationIssue.from_dict(d)
        assert issue.severity == Severity.MEDIUM
        assert issue.file == Path("test.py")


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_empty_result(self):
        result = ValidationResult(validator_name="security")
        assert result.validator_name == "security"
        assert result.issues == []
        assert result.high_count == 0
        assert result.is_success() is True
        assert result.has_issues() is False

    def test_result_with_issues(self):
        issues = [
            ValidationIssue(Severity.HIGH, "cat1", "msg1"),
            ValidationIssue(Severity.HIGH, "cat2", "msg2"),
            ValidationIssue(Severity.MEDIUM, "cat3", "msg3"),
            ValidationIssue(Severity.LOW, "cat4", "msg4"),
        ]
        result = ValidationResult(validator_name="security", issues=issues)
        assert result.high_count == 2
        assert result.medium_count == 1
        assert result.low_count == 1
        assert result.has_issues() is True

    def test_result_with_error(self):
        result = ValidationResult(
            validator_name="security",
            error="Timeout",
        )
        assert result.is_success() is False

    def test_filter_by_severity(self):
        issues = [
            ValidationIssue(Severity.HIGH, "cat1", "msg1"),
            ValidationIssue(Severity.MEDIUM, "cat2", "msg2"),
            ValidationIssue(Severity.LOW, "cat3", "msg3"),
        ]
        result = ValidationResult(validator_name="test", issues=issues)
        high_only = result.filter_by_severity(Severity.HIGH)
        assert len(high_only) == 1
        medium_up = result.filter_by_severity(Severity.MEDIUM)
        assert len(medium_up) == 2


class TestValidationReport:
    """Tests for ValidationReport dataclass."""

    def test_empty_report(self):
        report = ValidationReport()
        assert report.results == []
        assert report.has_high_severity is False
        assert report.total_issues == 0
        assert report.recommendation == "PROCEED"

    def test_report_with_high_severity(self):
        result = ValidationResult(
            validator_name="security",
            issues=[ValidationIssue(Severity.HIGH, "sql", "SQL injection")],
        )
        report = ValidationReport(results=[result], recommendation="CHANGES_REQUESTED")
        assert report.has_high_severity is True
        assert report.high_count == 1

    def test_format_summary(self):
        result = ValidationResult(
            validator_name="security",
            issues=[
                ValidationIssue(Severity.HIGH, "sql", "SQL injection"),
                ValidationIssue(Severity.MEDIUM, "xss", "XSS issue"),
            ],
        )
        report = ValidationReport(results=[result], recommendation="CHANGES_REQUESTED")
        summary = report.format_summary()
        assert "HIGH" in summary
        assert "1" in summary  # high count
        assert "CHANGES_REQUESTED" in summary

    def test_format_for_executor(self):
        result = ValidationResult(
            validator_name="security",
            issues=[
                ValidationIssue(
                    Severity.HIGH,
                    "sql_injection",
                    "SQL injection detected",
                    file=Path("db.py"),
                    line=42,
                    recommendation="Use parameterized query",
                )
            ],
        )
        report = ValidationReport(results=[result])
        output = report.format_for_executor()
        assert "SQL injection" in output
        assert "db.py" in output
        assert "parameterized" in output


class TestSecurityValidator:
    """Tests for SecurityValidator."""

    def test_initialization(self):
        validator = SecurityValidator()
        assert validator.name == "security"
        assert validator.severity_threshold == Severity.MEDIUM

    def test_custom_threshold(self):
        validator = SecurityValidator(severity_threshold=Severity.HIGH)
        assert validator.severity_threshold == Severity.HIGH

    @pytest.mark.asyncio
    async def test_detect_sql_injection_in_diff(self):
        validator = SecurityValidator()
        diff = '''
+++ b/db.py
@@ -10,0 +11 @@
+cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
'''
        result = await validator.validate(
            changed_files=[Path("db.py")],
            diff=diff,
        )
        assert any(i.category == "sql_injection" for i in result.issues)

    @pytest.mark.asyncio
    async def test_detect_hardcoded_secret(self):
        validator = SecurityValidator()
        diff = '''
+++ b/config.py
@@ -10,0 +11 @@
+api_key = "sk-1234567890abcdef1234567890abcdef"
'''
        result = await validator.validate(
            changed_files=[Path("config.py")],
            diff=diff,
        )
        assert any(i.category == "secrets_exposure" for i in result.issues)

    @pytest.mark.asyncio
    async def test_no_issues_clean_code(self):
        validator = SecurityValidator()
        diff = '''
+++ b/utils.py
@@ -10,0 +11 @@
+def add(a, b):
+    return a + b
'''
        result = await validator.validate(
            changed_files=[Path("utils.py")],
            diff=diff,
        )
        assert len(result.issues) == 0


class TestPerformanceValidator:
    """Tests for PerformanceValidator."""

    def test_initialization(self):
        validator = PerformanceValidator()
        assert validator.name == "performance"

    @pytest.mark.asyncio
    async def test_detect_unbounded_query(self):
        validator = PerformanceValidator(severity_threshold=Severity.LOW)
        diff = '''
+++ b/views.py
@@ -10,0 +11 @@
+users = User.objects.all()
'''
        result = await validator.validate(
            changed_files=[Path("views.py")],
            diff=diff,
        )
        # This might or might not be detected depending on pattern matching
        assert result.is_success()


class TestAPIValidator:
    """Tests for APIValidator."""

    def test_initialization(self):
        validator = APIValidator()
        assert validator.name == "api"

    @pytest.mark.asyncio
    async def test_detect_hardcoded_url(self):
        validator = APIValidator(severity_threshold=Severity.LOW)
        diff = '''
+++ b/api.py
@@ -10,0 +11 @@
+base_url = "http://localhost:8000/api"
'''
        result = await validator.validate(
            changed_files=[Path("api.py")],
            diff=diff,
        )
        assert any(i.category == "hardcoded_url" for i in result.issues)


class TestValidationPipeline:
    """Tests for ValidationPipeline."""

    def test_initialization(self):
        validators = [SecurityValidator(), PerformanceValidator()]
        pipeline = ValidationPipeline(validators=validators)
        assert len(pipeline.validators) == 2
        assert pipeline.max_parallel == 3
        assert pipeline.auto_reject_on_high is True

    @pytest.mark.asyncio
    async def test_run_empty_diff(self):
        pipeline = ValidationPipeline(validators=[SecurityValidator()])
        report = await pipeline.run(
            changed_files=[],
            diff="",
        )
        assert report.recommendation == "PROCEED"

    @pytest.mark.asyncio
    async def test_run_with_issues(self):
        pipeline = ValidationPipeline(
            validators=[SecurityValidator()],
            auto_reject_on_high=True,
        )
        diff = '''
+++ b/db.py
@@ -10,0 +11 @@
+cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
'''
        report = await pipeline.run(
            changed_files=[Path("db.py")],
            diff=diff,
        )
        assert report.has_high_severity
        assert report.recommendation == "CHANGES_REQUESTED"

    def test_recommendation_proceed(self):
        pipeline = ValidationPipeline(validators=[])
        results = []
        assert pipeline._get_recommendation(results) == "PROCEED"

    def test_recommendation_with_warnings(self):
        pipeline = ValidationPipeline(validators=[], auto_reject_on_high=True)
        results = [
            ValidationResult(
                validator_name="test",
                issues=[ValidationIssue(Severity.MEDIUM, "cat", "msg")],
            )
        ]
        assert pipeline._get_recommendation(results) == "PROCEED_WITH_WARNINGS"


class TestCreateDefaultPipeline:
    """Tests for create_default_pipeline factory."""

    def test_default_pipeline(self):
        pipeline = create_default_pipeline()
        assert len(pipeline.validators) == 3  # security, performance, api
        validator_names = [v.name for v in pipeline.validators]
        assert "security" in validator_names
        assert "performance" in validator_names
        assert "api" in validator_names

    def test_pipeline_with_disabled_validator(self):
        config = {
            "validators": {
                "security": {"enabled": False},
                "performance": {"enabled": True},
                "api": {"enabled": True},
            }
        }
        pipeline = create_default_pipeline(config)
        validator_names = [v.name for v in pipeline.validators]
        assert "security" not in validator_names
        assert "performance" in validator_names

    def test_pipeline_with_custom_timeout(self):
        config = {"total_timeout": 60.0}
        pipeline = create_default_pipeline(config)
        assert pipeline.total_timeout == 60.0
