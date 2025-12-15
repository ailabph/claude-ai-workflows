"""
Unit tests for response parsers.
"""

import pytest
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto.parser import (
    parse_planner_response,
    parse_executor_response,
    parse_response,
    extract_milestone_number,
    extract_file_paths,
    is_response_tag_present,
    extract_all_tags,
    PLANNER_APPROVED,
    PLANNER_CHANGES_REQUESTED,
    PLANNER_BLOCKED,
    PLANNER_PLAN_READY,
    EXECUTOR_REPORT,
    EXECUTOR_CLARIFICATION,
    EXECUTOR_BLOCKED,
    UNKNOWN,
)


class TestPlannerResponseParser:
    """Test parsing planner responses."""

    def test_parse_milestone_approved(self):
        """Test parsing MILESTONE_APPROVED tag."""
        content = """
        [MILESTONE_APPROVED] Milestone 3 approved. Proceed to Milestone 4.

        Great work on the implementation! Tests are passing and code follows conventions.
        """

        response_type, data = parse_planner_response(content)

        assert response_type == PLANNER_APPROVED
        assert data["milestone"] == 3

    def test_parse_changes_requested(self):
        """Test parsing CHANGES_REQUESTED tag."""
        content = """
        [CHANGES_REQUESTED] Milestone 2 needs changes:
        - Fix failing test in test_authentication.py
        - Add error handling for network timeouts
        - Update docstrings for new methods

        Please address these issues and regenerate your progress report.
        """

        response_type, data = parse_planner_response(content)

        assert response_type == PLANNER_CHANGES_REQUESTED
        assert len(data["issues"]) == 3
        assert "Fix failing test" in data["issues"][0]
        assert "error handling" in data["issues"][1]

    def test_parse_human_input_needed(self):
        """Test parsing HUMAN_INPUT_NEEDED tag."""
        content = """
        [HUMAN_INPUT_NEEDED] I need clarification on: Should we use OAuth 2.0 or JWT for authentication?

        The plan doesn't specify which authentication method to use. Please provide guidance.
        """

        response_type, data = parse_planner_response(content)

        assert response_type == PLANNER_BLOCKED
        assert "OAuth" in data["question"]
        assert "JWT" in data["question"]

    def test_parse_plan_ready(self):
        """Test parsing PLAN_READY tag with new format."""
        content = """
        [PLAN_READY]
        Path: docs/user-auth/DOC_user_auth_plan.md
        Milestones: 5 total

        [PLAN_CONTENT]
        # Implementation Plan: User Authentication

        ## Overview
        Add user authentication with login, logout, and session management.

        ## Milestones

        ### Milestone 1: Setup
        **Deliverables:**
        - Database schema
        - User model

        ### Milestone 2: Login
        **Deliverables:**
        - Login endpoint
        - JWT tokens
        [/PLAN_CONTENT]

        Summary: The plan includes authentication, authorization, and session management.
        """

        response_type, data = parse_planner_response(content)

        assert response_type == PLANNER_PLAN_READY
        assert data["path"] == "docs/user-auth/DOC_user_auth_plan.md"
        assert data["milestones"] == 5
        assert data["content"] is not None
        assert "User Authentication" in data["content"]

    def test_parse_unknown_response(self):
        """Test parsing response without known tags."""
        content = """
        This is just regular text without any response format tags.
        The planner is discussing something without using structured tags.
        """

        response_type, data = parse_planner_response(content)

        assert response_type == UNKNOWN
        assert data == {}

    def test_parse_case_insensitive(self):
        """Test that parsing is case-insensitive."""
        content = "[milestone_approved] Milestone 1 approved."

        response_type, data = parse_planner_response(content)

        assert response_type == PLANNER_APPROVED
        assert data["milestone"] == 1


class TestExecutorResponseParser:
    """Test parsing executor responses."""

    def test_parse_progress_report(self):
        """Test parsing PROGRESS_REPORT tag."""
        content = """
        [PROGRESS_REPORT]
        ## Milestone 2: Database Schema - COMPLETED

        ### Files Created/Modified:
        - models/user.py (created)
        - models/session.py (created)
        - migrations/001_initial.sql (created)

        ### Test Results:
        All tests passing (15/15)

        ### Notes/Issues:
        None

        ### Ready for Review: YES
        [/PROGRESS_REPORT]
        """

        response_type, data = parse_executor_response(content)

        assert response_type == EXECUTOR_REPORT
        assert data["milestone"] == 2
        assert data["name"] == "Database Schema"
        assert "models/user.py" in data["content"]

    def test_parse_clarification_needed(self):
        """Test parsing CLARIFICATION_NEEDED tag."""
        content = """
        [CLARIFICATION_NEEDED] I need the planner to clarify: Which database should I use - PostgreSQL or MySQL?

        The plan mentions "SQL database" but doesn't specify which one.
        """

        response_type, data = parse_executor_response(content)

        assert response_type == EXECUTOR_CLARIFICATION
        assert "database" in data["question"].lower()
        assert "PostgreSQL" in data["question"]

    def test_parse_blocked(self):
        """Test parsing BLOCKED tag."""
        content = """
        [BLOCKED] Cannot proceed: Missing API credentials for external service

        I need the API key for the payment gateway to continue with integration.
        """

        response_type, data = parse_executor_response(content)

        assert response_type == EXECUTOR_BLOCKED
        assert "API credentials" in data["reason"]

    def test_parse_report_without_milestone_number(self):
        """Test parsing progress report without explicit milestone number."""
        content = """
        [PROGRESS_REPORT]
        ## Setup Complete - COMPLETED

        All dependencies installed and configured.
        [/PROGRESS_REPORT]
        """

        response_type, data = parse_executor_response(content)

        assert response_type == EXECUTOR_REPORT
        assert data["milestone"] is None
        assert "Setup Complete" in data["content"]

    def test_parse_unknown_response(self):
        """Test parsing response without known tags."""
        content = """
        Working on the implementation...
        Making progress on the feature.
        """

        response_type, data = parse_executor_response(content)

        assert response_type == UNKNOWN
        assert data == {}


class TestHelperFunctions:
    """Test helper parsing functions."""

    def test_extract_milestone_number(self):
        """Test extracting milestone number from text."""
        text = "Working on Milestone 3 implementation"

        milestone = extract_milestone_number(text)

        assert milestone == 3

    def test_extract_milestone_number_not_found(self):
        """Test when milestone number is not in text."""
        text = "Working on the implementation"

        milestone = extract_milestone_number(text)

        assert milestone is None

    def test_extract_file_paths(self):
        """Test extracting file paths from progress report."""
        text = """
        ### Files Created/Modified:
        - src/auth/login.py (created)
        - src/auth/session.py (modified)
        - tests/test_auth.py (created)
        """

        paths = extract_file_paths(text)

        assert len(paths) == 3
        assert "src/auth/login.py" in paths
        assert "src/auth/session.py" in paths
        assert "tests/test_auth.py" in paths

    def test_extract_file_paths_empty(self):
        """Test extracting file paths when none present."""
        text = "No files were modified in this milestone."

        paths = extract_file_paths(text)

        assert len(paths) == 0

    def test_is_response_tag_present(self):
        """Test checking if response tag is present."""
        content = "[MILESTONE_APPROVED] Great work!"

        assert is_response_tag_present(content, "MILESTONE_APPROVED")
        assert not is_response_tag_present(content, "CHANGES_REQUESTED")

    def test_extract_all_tags(self):
        """Test extracting all tags from content."""
        content = """
        [MILESTONE_APPROVED] Milestone 2 approved.
        [PROGRESS_REPORT] Report content [/PROGRESS_REPORT]
        Some text with [HUMAN_INPUT_NEEDED] tag.
        """

        tags = extract_all_tags(content)

        assert "MILESTONE_APPROVED" in tags
        assert "PROGRESS_REPORT" in tags
        assert "HUMAN_INPUT_NEEDED" in tags

    def test_parse_response_planner(self):
        """Test convenience function for planner."""
        content = "[MILESTONE_APPROVED] Milestone 1 approved."

        response_type, data = parse_response(content, "planner")

        assert response_type == PLANNER_APPROVED

    def test_parse_response_executor(self):
        """Test convenience function for executor."""
        content = "[BLOCKED] Cannot proceed: Missing dependency"

        response_type, data = parse_response(content, "executor")

        assert response_type == EXECUTOR_BLOCKED

    def test_parse_response_unknown_agent(self):
        """Test convenience function with unknown agent type."""
        content = "[MILESTONE_APPROVED] Test"

        response_type, data = parse_response(content, "unknown")

        assert response_type == UNKNOWN


class TestEdgeCases:
    """Test edge cases and malformed inputs."""

    def test_malformed_tag_no_closing(self):
        """Test handling of malformed tag without closing bracket."""
        content = "[MILESTONE_APPROVED Milestone 2 approved"

        response_type, data = parse_planner_response(content)

        # Should not match due to missing closing bracket
        assert response_type == UNKNOWN

    def test_multiple_tags_in_response(self):
        """Test response with multiple tags (first one wins)."""
        content = """
        [MILESTONE_APPROVED] Milestone 1 approved.
        [CHANGES_REQUESTED] But wait, there are some issues...
        """

        response_type, data = parse_planner_response(content)

        # Should parse the first tag found
        assert response_type == PLANNER_APPROVED

    def test_tag_in_middle_of_text(self):
        """Test tag that appears in middle of response."""
        content = """
        I've reviewed the milestone and everything looks good.

        [MILESTONE_APPROVED] Milestone 5 approved. Proceed to final testing.

        The implementation is solid and tests are comprehensive.
        """

        response_type, data = parse_planner_response(content)

        assert response_type == PLANNER_APPROVED
        assert data["milestone"] == 5

    def test_empty_content(self):
        """Test parsing empty content."""
        response_type, data = parse_planner_response("")

        assert response_type == UNKNOWN
        assert data == {}

    def test_whitespace_only(self):
        """Test parsing whitespace-only content."""
        response_type, data = parse_executor_response("   \n\n   \t  ")

        assert response_type == UNKNOWN

    def test_progress_report_nested_brackets(self):
        """Test progress report with nested brackets in content."""
        content = """
        [PROGRESS_REPORT]
        ## Milestone 1 - COMPLETED

        Added support for [markdown] syntax in comments.

        ### Test Results:
        All passing [10/10]
        [/PROGRESS_REPORT]
        """

        response_type, data = parse_executor_response(content)

        assert response_type == EXECUTOR_REPORT
        assert "[markdown]" in data["content"]
        assert "[10/10]" in data["content"]

    def test_changes_requested_no_bullets(self):
        """Test CHANGES_REQUESTED without bullet points."""
        content = """
        [CHANGES_REQUESTED] Please fix the timeout issue in the authentication module.
        """

        response_type, data = parse_planner_response(content)

        assert response_type == PLANNER_CHANGES_REQUESTED
        assert len(data["issues"]) == 1
        assert "timeout" in data["issues"][0]


class TestParsePlanFile:
    """Test parse_plan_file function."""

    def test_parse_valid_plan_file(self, tmp_path):
        """Test parsing a valid plan file."""
        from orchestrator_auto.parser import parse_plan_file

        plan_content = """# Implementation Plan: User Authentication

## Overview
Add user authentication with JWT.

## Milestones

### Milestone 1: Setup Database
**Deliverables:**
- User model
- Migration

### Milestone 2: Auth Endpoints
**Deliverables:**
- Login endpoint
- Logout endpoint

### Milestone 3: Testing
**Deliverables:**
- Unit tests
- Integration tests
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        result = parse_plan_file(str(plan_file))

        assert result["valid"] is True
        assert result["milestones"] == 3
        assert len(result["milestone_names"]) == 3
        assert "Setup Database" in result["milestone_names"][0]
        assert "Auth Endpoints" in result["milestone_names"][1]
        assert "Testing" in result["milestone_names"][2]
        assert result["error"] is None

    def test_parse_plan_file_not_found(self):
        """Test parsing non-existent file."""
        from orchestrator_auto.parser import parse_plan_file

        result = parse_plan_file("/nonexistent/path/plan.md")

        assert result["valid"] is False
        assert "not found" in result["error"]

    def test_parse_plan_file_no_milestones(self, tmp_path):
        """Test parsing file without milestones."""
        from orchestrator_auto.parser import parse_plan_file

        plan_content = """# Implementation Plan

## Overview
Some description without milestones.

## Notes
Just some notes here.
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        result = parse_plan_file(str(plan_file))

        assert result["valid"] is False
        assert "No milestones found" in result["error"]

    def test_parse_plan_file_single_milestone(self, tmp_path):
        """Test parsing file with single milestone."""
        from orchestrator_auto.parser import parse_plan_file

        plan_content = """# Quick Fix Plan

### Milestone 1: Fix Bug
**Deliverables:**
- Bug fix
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        result = parse_plan_file(str(plan_file))

        assert result["valid"] is True
        assert result["milestones"] == 1
        assert "Fix Bug" in result["milestone_names"][0]
