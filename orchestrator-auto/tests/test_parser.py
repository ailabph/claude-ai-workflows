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
    is_response_truncated,
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


class TestExtractFeatureFromPlan:
    """Test extract_feature_from_plan function for queue feature."""

    def test_extract_from_yaml_frontmatter(self, tmp_path):
        """Test extracting feature from YAML frontmatter."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """---
title: User Authentication
feature: Add JWT-based user authentication
author: Developer
---

# Implementation Plan

Some content here.
"""
        plan_file = tmp_path / "auth-plan.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        assert result == "Add JWT-based user authentication"

    def test_extract_from_feature_header(self, tmp_path):
        """Test extracting feature from # Feature: header."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """# Feature: Implement payment gateway integration

## Overview
This plan describes the payment gateway implementation.

## Milestones
### Milestone 1: Setup
"""
        plan_file = tmp_path / "payment-plan.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        assert result == "Implement payment gateway integration"

    def test_extract_from_implementation_plan_header(self, tmp_path):
        """Test extracting from # Implementation Plan: header."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """# Implementation Plan: API Rate Limiting

## Overview
Add rate limiting to API endpoints.
"""
        plan_file = tmp_path / "rate-limit-plan.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        assert result == "API Rate Limiting"

    def test_extract_from_plain_h1_title(self, tmp_path):
        """Test extracting from plain H1 title."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """# Database Migration Tools

## Description
Tools for managing database migrations.

### Milestone 1: Schema
"""
        plan_file = tmp_path / "db-migration.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        assert result == "Database Migration Tools"

    def test_extract_strips_implementation_plan_suffix(self, tmp_path):
        """Test that 'Implementation Plan' suffix is stripped from H1."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """# User Dashboard - Implementation Plan

## Overview
Create user dashboard.
"""
        plan_file = tmp_path / "dashboard.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        assert result == "User Dashboard"
        assert "Implementation Plan" not in result

    def test_extract_fallback_to_filename(self, tmp_path):
        """Test fallback to filename when no headers found."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """Some plan content without any H1 headers.

Just regular text here.

## Milestone 1
Some milestone content.
"""
        plan_file = tmp_path / "user-profile-feature.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        assert result == "user profile feature"

    def test_extract_fallback_to_filename_with_hyphens(self, tmp_path):
        """Test filename fallback converts hyphens to spaces."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """No H1 headers here."""

        plan_file = tmp_path / "oauth-2-integration.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        assert result == "oauth 2 integration"

    def test_extract_fallback_to_filename_with_underscores(self, tmp_path):
        """Test filename fallback converts underscores to spaces."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """No headers."""

        plan_file = tmp_path / "user_auth_flow.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        assert result == "user auth flow"

    def test_extract_missing_file_returns_filename(self, tmp_path):
        """Test that missing file returns filename as fallback."""
        from orchestrator_auto.parser import extract_feature_from_plan

        nonexistent_path = tmp_path / "nonexistent-plan.md"

        result = extract_feature_from_plan(str(nonexistent_path))

        assert result == "nonexistent plan"

    def test_extract_case_insensitive_feature_header(self, tmp_path):
        """Test that feature header matching is case insensitive."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """# FEATURE: Case Insensitive Test

## Overview
Test case insensitivity.
"""
        plan_file = tmp_path / "test.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        assert result == "Case Insensitive Test"

    def test_extract_yaml_case_insensitive(self, tmp_path):
        """Test YAML frontmatter feature key is case insensitive."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """---
FEATURE: YAML Case Test
---

# Plan
"""
        plan_file = tmp_path / "yaml-test.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        assert result == "YAML Case Test"

    def test_extract_first_h1_wins(self, tmp_path):
        """Test that first H1 is used when multiple exist."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """Some intro text.

# First Feature Title

More content.

# Second Feature Title

Even more content.
"""
        plan_file = tmp_path / "multiple-h1.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        assert result == "First Feature Title"

    def test_extract_ignores_h2_h3_headers(self, tmp_path):
        """Test that H2/H3 headers are ignored, only H1 counts."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """## This is an H2

### This is an H3

# This is the H1

## Another H2
"""
        plan_file = tmp_path / "header-levels.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        assert result == "This is the H1"

    def test_extract_yaml_priority_over_headers(self, tmp_path):
        """Test that YAML frontmatter takes priority over headers."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """---
feature: YAML Feature Description
---

# Header Feature Description

Content here.
"""
        plan_file = tmp_path / "priority-test.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        assert result == "YAML Feature Description"

    def test_extract_feature_header_priority_over_implementation_plan(self, tmp_path):
        """Test that # Feature: takes priority over # Implementation Plan:."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """# Feature: Specific Feature

Some intro.

# Implementation Plan: Generic Plan

More content.
"""
        plan_file = tmp_path / "priority2.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        assert result == "Specific Feature"

    def test_extract_handles_whitespace_in_headers(self, tmp_path):
        """Test extraction handles extra whitespace in headers."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """#     Feature:     Lots of Spaces

Content.
"""
        plan_file = tmp_path / "whitespace.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        assert result == "Lots of Spaces"

    def test_extract_empty_file_returns_filename(self, tmp_path):
        """Test that empty file returns filename fallback."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_file = tmp_path / "empty-plan.md"
        plan_file.write_text("")

        result = extract_feature_from_plan(str(plan_file))

        assert result == "empty plan"

    def test_extract_only_whitespace_returns_filename(self, tmp_path):
        """Test that file with only whitespace returns filename."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_file = tmp_path / "whitespace-only.md"
        plan_file.write_text("\n\n   \n\t\n   ")

        result = extract_feature_from_plan(str(plan_file))

        assert result == "whitespace only"

    def test_extract_searches_first_20_lines(self, tmp_path):
        """Test that search is limited to first ~20 lines for performance."""
        from orchestrator_auto.parser import extract_feature_from_plan

        # Create content with H1 on line 25
        lines = ["Line content"] * 24
        lines.append("# Late Header")
        plan_content = "\n".join(lines)

        plan_file = tmp_path / "late-header.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        # Should fall back to filename since H1 is after line 20
        assert result == "late header"

    def test_extract_real_world_plan_format(self, tmp_path):
        """Test with real-world plan format from PLAN_queue_feature.md."""
        from orchestrator_auto.parser import extract_feature_from_plan

        plan_content = """# Plan: Plan Queue Feature (GO-Ready)

Queue multiple plan files for sequential execution with automatic advancement on completion.

## Feature Description

Add a `--queue` mode to `orchestrator start` to enqueue multiple plan files for sequential execution, automatically starting the next workflow when the current one completes.

Queue state is persisted in SQLite for crash recovery and for resuming mid-queue.
"""
        plan_file = tmp_path / "PLAN_queue_feature.md"
        plan_file.write_text(plan_content)

        result = extract_feature_from_plan(str(plan_file))

        # Should extract just the feature name, not the "Plan:" prefix
        assert result == "Plan: Plan Queue Feature (GO-Ready)"


class TestIsResponseTruncated:
    """Test truncation detection for auto-continue feature."""

    # Tests for responses that should NOT be detected as truncated
    # (valid response tags present)

    def test_not_truncated_with_progress_report(self):
        """Response with PROGRESS_REPORT tag is not truncated."""
        content = """
        [PROGRESS_REPORT]
        ## Milestone 1 - COMPLETED
        All tasks done.
        [/PROGRESS_REPORT]
        """
        assert not is_response_truncated(content)

    def test_not_truncated_with_blocked(self):
        """Response with BLOCKED tag is not truncated."""
        content = "[BLOCKED] Cannot proceed: missing credentials"
        assert not is_response_truncated(content)

    def test_not_truncated_with_milestone_approved(self):
        """Response with MILESTONE_APPROVED tag is not truncated."""
        content = "[MILESTONE_APPROVED] Milestone 3 approved. Proceed."
        assert not is_response_truncated(content)

    def test_not_truncated_with_changes_requested(self):
        """Response with CHANGES_REQUESTED tag is not truncated."""
        content = """
        [CHANGES_REQUESTED] Milestone 2 needs changes:
        - Fix failing tests
        - Add error handling
        """
        assert not is_response_truncated(content)

    def test_not_truncated_with_human_input_needed(self):
        """Response with HUMAN_INPUT_NEEDED tag is not truncated."""
        content = "[HUMAN_INPUT_NEEDED] Should we use OAuth or JWT?"
        assert not is_response_truncated(content)

    def test_not_truncated_with_plan_ready(self):
        """Response with PLAN_READY tag is not truncated."""
        content = """
        [PLAN_READY]
        Path: docs/plan.md
        Milestones: 3 total
        """
        assert not is_response_truncated(content)

    def test_not_truncated_with_clarification_needed(self):
        """Response with CLARIFICATION_NEEDED tag is not truncated."""
        content = "[CLARIFICATION_NEEDED] Which database should I use?"
        assert not is_response_truncated(content)

    def test_not_truncated_case_insensitive_tag(self):
        """Tag detection is case insensitive."""
        content = "[blocked] Cannot proceed"
        assert not is_response_truncated(content)

    # Tests for responses that SHOULD be detected as truncated
    # (incomplete responses without valid tags)

    def test_truncated_ends_with_colon(self):
        """Response ending with colon is truncated."""
        content = "Let me navigate the second tab to the dashboard:"
        assert is_response_truncated(content)

    def test_truncated_ends_with_let_me(self):
        """Response with incomplete 'Let me...' is truncated."""
        content = "Let me start by reading the configuration"
        assert is_response_truncated(content)

    def test_truncated_ends_with_ill(self):
        """Response with incomplete \"I'll...\" is truncated."""
        content = "I'll implement the authentication logic"
        assert is_response_truncated(content)

    def test_truncated_ends_with_i_will(self):
        """Response with incomplete 'I will...' is truncated."""
        content = "I will create the database schema"
        assert is_response_truncated(content)

    def test_truncated_ends_with_im_going_to(self):
        """Response with incomplete \"I'm going to...\" is truncated."""
        content = "I'm going to update the test file"
        assert is_response_truncated(content)

    def test_truncated_no_sentence_ending(self):
        """Response without sentence ending punctuation is truncated."""
        content = "Working on the implementation of the user interface component"
        assert is_response_truncated(content)

    def test_truncated_empty_content(self):
        """Empty content is not considered truncated (special case)."""
        assert not is_response_truncated("")
        assert not is_response_truncated(None)

    # Tests for edge cases and complete responses

    def test_not_truncated_complete_sentence_with_period(self):
        """Complete sentence with period is not truncated."""
        content = "I've completed the implementation."
        assert not is_response_truncated(content)

    def test_not_truncated_complete_sentence_with_exclamation(self):
        """Complete sentence with exclamation is not truncated."""
        content = "The tests are passing!"
        assert not is_response_truncated(content)

    def test_not_truncated_complete_sentence_with_question(self):
        """Complete sentence with question mark is not truncated."""
        content = "Should I proceed with the next milestone?"
        assert not is_response_truncated(content)

    def test_not_truncated_ends_with_closing_bracket(self):
        """Response ending with ] is not truncated."""
        content = "All tests passing [10/10]"
        assert not is_response_truncated(content)

    def test_truncated_long_incomplete_response(self):
        """Long response that is incomplete is truncated."""
        content = """
        I've been working on the milestone and made significant progress.
        The authentication module is now complete and I've added tests.

        Now let me proceed with the next step which involves updating
        """
        assert is_response_truncated(content)

    def test_not_truncated_with_tag_despite_incomplete_ending(self):
        """Valid tag takes precedence over incomplete-looking ending."""
        # Even though this ends with incomplete text, the BLOCKED tag should
        # make it not considered truncated
        content = """
        [BLOCKED] Cannot proceed
        I was trying to continue but hit a blocker
        Let me explain the issue
        """
        assert not is_response_truncated(content)
