"""
Unit tests for plan conversion functionality.

Tests use mocked Claude SDK responses to avoid actual API calls.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
import sys
import asyncio
import tempfile

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto.convert import (
    convert_plan,
    convert_plan_async,
    validate_plan_content,
    ConversionError,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_MILESTONES,
    _build_prompt,
    _strip_outer_code_fences,
    _extract_feature,
)


class TestValidatePlanContent:
    """Test plan content validation."""

    def test_valid_plan_single_milestone(self):
        """Test validation of plan with single milestone."""
        content = """# My Plan

### Milestone 1: Setup
- Task 1
- Task 2
"""
        is_valid, details = validate_plan_content(content)

        assert is_valid is True
        assert details["milestones"] == 1
        assert details["milestone_names"] == ["Setup"]
        assert details["error"] is None

    def test_valid_plan_multiple_milestones(self):
        """Test validation of plan with multiple milestones."""
        content = """# Implementation Plan

### Milestone 1: Setup Database
Tasks here

### Milestone 2: Build API
More tasks

### Milestone 3: Testing
Test tasks
"""
        is_valid, details = validate_plan_content(content)

        assert is_valid is True
        assert details["milestones"] == 3
        assert details["milestone_names"] == ["Setup Database", "Build API", "Testing"]
        assert details["error"] is None

    def test_invalid_plan_no_milestones(self):
        """Test validation fails when no milestones present."""
        content = """# My Plan

## Step 1
Do something

## Step 2
Do more
"""
        is_valid, details = validate_plan_content(content)

        assert is_valid is False
        assert details["milestones"] == 0
        assert details["milestone_names"] == []
        assert "No milestones found" in details["error"]

    def test_valid_plan_double_hash_header(self):
        """Test validation accepts ## milestone headers (matches parse_plan_file)."""
        content = """# My Plan

## Milestone 1: Setup
Tasks

## Milestone 2: Implementation
More tasks
"""
        is_valid, details = validate_plan_content(content)

        assert is_valid is True
        assert details["milestones"] == 2
        assert details["milestone_names"] == ["Setup", "Implementation"]

    def test_valid_plan_mixed_header_levels(self):
        """Test validation accepts mix of ## and ### milestone headers."""
        content = """# My Plan

## Milestone 1: Setup with double hash
Tasks

### Milestone 2: Build with triple hash
More tasks
"""
        is_valid, details = validate_plan_content(content)

        assert is_valid is True
        assert details["milestones"] == 2
        assert details["milestone_names"] == ["Setup with double hash", "Build with triple hash"]

    def test_invalid_plan_single_hash_header(self):
        """Test validation fails with single hash (# Milestone)."""
        content = """# My Plan

# Milestone 1: Setup
Tasks
"""
        is_valid, details = validate_plan_content(content)

        assert is_valid is False
        assert details["milestones"] == 0

    def test_invalid_plan_four_hash_header(self):
        """Test validation fails with four hashes (#### Milestone)."""
        content = """# My Plan

#### Milestone 1: Setup
Tasks
"""
        is_valid, details = validate_plan_content(content)

        assert is_valid is False
        assert details["milestones"] == 0

    def test_invalid_plan_missing_colon(self):
        """Test validation fails when colon is missing."""
        content = """# My Plan

### Milestone 1 Setup
Tasks
"""
        is_valid, details = validate_plan_content(content)

        assert is_valid is False
        assert details["milestones"] == 0

    def test_case_insensitive_milestone(self):
        """Test that milestone matching is case insensitive."""
        content = """# My Plan

### MILESTONE 1: Setup
Tasks

### milestone 2: Build
More tasks
"""
        is_valid, details = validate_plan_content(content)

        assert is_valid is True
        assert details["milestones"] == 2

    def test_empty_content(self):
        """Test validation of empty content."""
        is_valid, details = validate_plan_content("")

        assert is_valid is False
        assert details["milestones"] == 0


class TestBuildPrompt:
    """Test prompt building function."""

    def test_build_prompt_basic(self):
        """Test basic prompt building."""
        content = "# My simple plan\n1. Do this\n2. Do that"
        prompt = _build_prompt(content, max_milestones=5)

        assert "My simple plan" in prompt
        assert "5 milestones" in prompt
        assert "### Milestone N: Name" in prompt

    def test_build_prompt_retry(self):
        """Test retry prompt is different."""
        content = "# My plan"
        normal_prompt = _build_prompt(content, max_milestones=5, is_retry=False)
        retry_prompt = _build_prompt(content, max_milestones=5, is_retry=True)

        assert normal_prompt != retry_prompt
        assert "CRITICAL" in retry_prompt
        assert "previous conversion did not produce valid" in retry_prompt

    def test_build_prompt_custom_max_milestones(self):
        """Test prompt with custom max milestones."""
        content = "# Plan"
        prompt = _build_prompt(content, max_milestones=3)

        assert "3 milestones" in prompt


class TestStripOuterCodeFences:
    """Test code fence stripping."""

    def test_strip_markdown_code_fence(self):
        """Test stripping markdown code fences."""
        text = "```markdown\n# Plan\n### Milestone 1: Test\n```"
        result = _strip_outer_code_fences(text)
        assert result == "# Plan\n### Milestone 1: Test"

    def test_strip_md_code_fence(self):
        """Test stripping md code fences."""
        text = "```md\n# Plan\n```"
        result = _strip_outer_code_fences(text)
        assert result == "# Plan"

    def test_strip_plain_code_fence(self):
        """Test stripping plain code fences."""
        text = "```\n# Plan\n```"
        result = _strip_outer_code_fences(text)
        assert result == "# Plan"

    def test_no_code_fence(self):
        """Test text without code fences."""
        text = "# Plan\n### Milestone 1: Test"
        result = _strip_outer_code_fences(text)
        assert result == "# Plan\n### Milestone 1: Test"

    def test_preserves_internal_code_blocks(self):
        """Test that internal code blocks are preserved."""
        text = """# Plan

### Milestone 1: Test
```python
def test():
    pass
```
"""
        result = _strip_outer_code_fences(text)
        assert "```python" in result
        assert "def test():" in result


class TestExtractFeature:
    """Test feature extraction from converted plan."""

    def test_extract_from_yaml_frontmatter(self):
        """Test extraction from YAML frontmatter."""
        content = """---
feature: User Authentication System
---

# Implementation Plan
"""
        result = _extract_feature(content)
        assert result == "User Authentication System"

    def test_extract_from_feature_header(self):
        """Test extraction from Feature header."""
        content = """# Feature: Payment Gateway Integration

## Overview
"""
        result = _extract_feature(content)
        assert result == "Payment Gateway Integration"

    def test_extract_from_implementation_plan_header(self):
        """Test extraction from Implementation Plan header."""
        content = """# Implementation Plan: API Rate Limiting

## Overview
"""
        result = _extract_feature(content)
        assert result == "API Rate Limiting"

    def test_extract_from_plain_h1(self):
        """Test extraction from plain H1."""
        content = """# Database Migration Tools

## Overview
"""
        result = _extract_feature(content)
        assert result == "Database Migration Tools"

    def test_strips_implementation_plan_suffix(self):
        """Test that Implementation Plan suffix is stripped."""
        content = """# User Dashboard - Implementation Plan

## Overview
"""
        result = _extract_feature(content)
        assert result == "User Dashboard"

    def test_returns_none_for_no_feature(self):
        """Test returns None when no feature found."""
        content = """Some content without headers"""
        result = _extract_feature(content)
        assert result is None


class TestConversionError:
    """Test ConversionError exception."""

    def test_conversion_error_is_exception(self):
        """Test that ConversionError is an Exception."""
        assert issubclass(ConversionError, Exception)

    def test_conversion_error_message(self):
        """Test that ConversionError has message."""
        error = ConversionError("Test error message")
        assert str(error) == "Test error message"


class TestDefaults:
    """Test default constants."""

    def test_default_model(self):
        """Test default model is Sonnet."""
        assert DEFAULT_MODEL == "claude-sonnet-4-6"

    def test_default_timeout(self):
        """Test default timeout is 60 seconds."""
        assert DEFAULT_TIMEOUT == 60

    def test_default_max_milestones(self):
        """Test default max milestones is 5."""
        assert DEFAULT_MAX_MILESTONES == 5


class TestConvertPlanAsync:
    """Test async plan conversion with mocked SDK."""

    @pytest.mark.asyncio
    async def test_converts_simple_plan(self):
        """Test conversion of simple plan."""
        content = """# My Feature
1. Setup
2. Build
3. Test
"""
        expected_output = """---
feature: My Feature
---

# Implementation Plan: My Feature

### Milestone 1: Setup
**Tasks:**
1. Initial setup

### Milestone 2: Build
**Tasks:**
1. Build implementation

### Milestone 3: Test
**Tasks:**
1. Run tests
"""
        with patch("orchestrator_auto.convert.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            # Create mock response
            mock_text = Mock()
            mock_text.text = expected_output

            mock_assistant = Mock()
            mock_assistant.content = [mock_text]

            mock_result = Mock()

            # Setup receive_messages
            async def mock_receive():
                with patch("orchestrator_auto.convert.AssistantMessage", type(mock_assistant)):
                    with patch("orchestrator_auto.convert.TextBlock", type(mock_text)):
                        with patch("orchestrator_auto.convert.ResultMessage", type(mock_result)):
                            yield mock_assistant
                            yield mock_result

            mock_client.receive_messages = mock_receive

            converted, metadata = await convert_plan_async(content)

        assert "### Milestone 1:" in converted
        assert metadata["milestones"] >= 1

    @pytest.mark.asyncio
    async def test_raises_on_empty_content(self):
        """Test that empty content raises ConversionError."""
        with pytest.raises(ConversionError, match="Empty content"):
            await convert_plan_async("")

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self):
        """Test that timeout raises ConversionError."""
        with patch("orchestrator_auto.convert.ClaudeSDKClient") as mock_client_class:
            async def slow_enter(self):
                await asyncio.sleep(100)
                return Mock()

            mock_client_class.return_value.__aenter__ = slow_enter

            with pytest.raises(ConversionError, match="timed out"):
                await convert_plan_async("# Plan", timeout=1)

    @pytest.mark.asyncio
    async def test_retries_on_invalid_output(self):
        """Test that invalid output triggers retry."""
        content = "# My Plan\n1. Step 1\n2. Step 2"

        # First response is invalid (no milestones), second is valid
        invalid_output = "Here is your plan:\n- Step 1\n- Step 2"
        valid_output = "### Milestone 1: Setup\nTasks"

        call_count = [0]

        with patch("orchestrator_auto.convert.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            async def mock_receive():
                call_count[0] += 1
                output = invalid_output if call_count[0] == 1 else valid_output

                mock_text = Mock()
                mock_text.text = output

                mock_assistant = Mock()
                mock_assistant.content = [mock_text]

                mock_result = Mock()

                with patch("orchestrator_auto.convert.AssistantMessage", type(mock_assistant)):
                    with patch("orchestrator_auto.convert.TextBlock", type(mock_text)):
                        with patch("orchestrator_auto.convert.ResultMessage", type(mock_result)):
                            yield mock_assistant
                            yield mock_result

            mock_client.receive_messages = mock_receive

            converted, metadata = await convert_plan_async(content)

        # Should have called twice (initial + retry)
        assert call_count[0] == 2
        assert metadata["retry_used"] is True

    @pytest.mark.asyncio
    async def test_raises_after_both_attempts_fail(self):
        """Test that error is raised when both attempts fail."""
        content = "# My Plan"
        invalid_output = "Not a valid plan format"

        with patch("orchestrator_auto.convert.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            async def mock_receive():
                mock_text = Mock()
                mock_text.text = invalid_output

                mock_assistant = Mock()
                mock_assistant.content = [mock_text]

                mock_result = Mock()

                with patch("orchestrator_auto.convert.AssistantMessage", type(mock_assistant)):
                    with patch("orchestrator_auto.convert.TextBlock", type(mock_text)):
                        with patch("orchestrator_auto.convert.ResultMessage", type(mock_result)):
                            yield mock_assistant
                            yield mock_result

            mock_client.receive_messages = mock_receive

            with pytest.raises(ConversionError, match="invalid output after retry"):
                await convert_plan_async(content)


class TestConvertPlanSync:
    """Test sync wrapper for plan conversion."""

    def test_sync_wrapper_calls_async(self):
        """Test that sync wrapper calls async function."""
        with patch("orchestrator_auto.convert.asyncio.run") as mock_run:
            mock_run.return_value = ("### Milestone 1: Test", {"milestones": 1, "milestone_names": ["Test"], "feature": None, "model_used": "test", "retry_used": False})

            converted, metadata = convert_plan("# Plan")

        mock_run.assert_called_once()
        assert "### Milestone 1" in converted


class TestCliConvert:
    """Test CLI convert command."""

    def test_convert_validate_only_valid(self, tmp_path):
        """Test --validate-only on valid plan."""
        from click.testing import CliRunner
        from orchestrator_auto.cli import cli

        # Create valid plan file
        plan_file = tmp_path / "valid_plan.md"
        plan_file.write_text("""# Plan

### Milestone 1: Setup
Tasks here

### Milestone 2: Build
More tasks
""")

        runner = CliRunner()
        result = runner.invoke(cli, ["convert", str(plan_file), "--validate-only"])

        assert result.exit_code == 0
        assert "Valid orchestrator plan" in result.output
        assert "Milestones: 2" in result.output

    def test_convert_validate_only_invalid(self, tmp_path):
        """Test --validate-only on invalid plan."""
        from click.testing import CliRunner
        from orchestrator_auto.cli import cli

        # Create invalid plan file
        plan_file = tmp_path / "invalid_plan.md"
        plan_file.write_text("""# Plan

## Step 1
Do something
""")

        runner = CliRunner()
        result = runner.invoke(cli, ["convert", str(plan_file), "--validate-only"])

        assert result.exit_code == 1
        assert "Not a valid orchestrator plan" in result.output

    def test_convert_already_valid_skips(self, tmp_path):
        """Test that already valid plans are skipped."""
        from click.testing import CliRunner
        from orchestrator_auto.cli import cli

        # Create valid plan file
        plan_file = tmp_path / "valid_plan.md"
        plan_file.write_text("""### Milestone 1: Test
Tasks
""")

        runner = CliRunner()
        result = runner.invoke(cli, ["convert", str(plan_file)])

        assert result.exit_code == 0
        assert "already orchestrator-compatible" in result.output

    def test_convert_mutual_exclusion(self, tmp_path):
        """Test --output and --in-place are mutually exclusive."""
        from click.testing import CliRunner
        from orchestrator_auto.cli import cli

        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Plan")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "convert", str(plan_file),
            "--output", "out.md",
            "--in-place"
        ])

        assert result.exit_code != 0
        assert "Cannot use both" in result.output

    def test_convert_to_file(self, tmp_path):
        """Test conversion with --output flag."""
        from click.testing import CliRunner
        from orchestrator_auto.cli import cli

        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Simple plan\n1. Step one")
        output_file = tmp_path / "converted.md"

        # Mock the conversion - patch where it's imported from
        with patch("orchestrator_auto.convert.convert_plan") as mock_convert:
            mock_convert.return_value = (
                "### Milestone 1: Step One\nTasks",
                {"milestones": 1, "milestone_names": ["Step One"], "feature": "Simple plan", "retry_used": False}
            )

            runner = CliRunner()
            result = runner.invoke(cli, [
                "convert", str(plan_file),
                "--output", str(output_file)
            ])

        assert result.exit_code == 0
        assert output_file.exists()
        assert "### Milestone 1" in output_file.read_text()

    def test_convert_in_place_creates_backup(self, tmp_path):
        """Test --in-place creates backup."""
        from click.testing import CliRunner
        from orchestrator_auto.cli import cli

        plan_file = tmp_path / "plan.md"
        original_content = "# Simple plan\n1. Step one"
        plan_file.write_text(original_content)

        with patch("orchestrator_auto.convert.convert_plan") as mock_convert:
            mock_convert.return_value = (
                "### Milestone 1: Step One\nTasks",
                {"milestones": 1, "milestone_names": ["Step One"], "feature": None, "retry_used": False}
            )

            runner = CliRunner()
            result = runner.invoke(cli, [
                "convert", str(plan_file),
                "--in-place"
            ])

        assert result.exit_code == 0

        # Check backup was created
        backup_file = tmp_path / "plan.md.bak"
        assert backup_file.exists()
        assert backup_file.read_text() == original_content

        # Check original was modified
        assert "### Milestone 1" in plan_file.read_text()

    def test_convert_in_place_no_backup(self, tmp_path):
        """Test --in-place --no-backup skips backup."""
        from click.testing import CliRunner
        from orchestrator_auto.cli import cli

        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Simple plan")

        with patch("orchestrator_auto.convert.convert_plan") as mock_convert:
            mock_convert.return_value = (
                "### Milestone 1: Test\nTasks",
                {"milestones": 1, "milestone_names": ["Test"], "feature": None, "retry_used": False}
            )

            runner = CliRunner()
            result = runner.invoke(cli, [
                "convert", str(plan_file),
                "--in-place", "--no-backup"
            ])

        assert result.exit_code == 0

        # Check no backup was created
        backup_file = tmp_path / "plan.md.bak"
        assert not backup_file.exists()

    def test_convert_dry_run(self, tmp_path):
        """Test --dry-run shows preview."""
        from click.testing import CliRunner
        from orchestrator_auto.cli import cli

        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Simple plan")

        with patch("orchestrator_auto.convert.convert_plan") as mock_convert:
            mock_convert.return_value = (
                "### Milestone 1: Test\n**Tasks:**\n1. Do something",
                {"milestones": 1, "milestone_names": ["Test"], "feature": "Simple plan", "retry_used": False}
            )

            runner = CliRunner()
            result = runner.invoke(cli, [
                "convert", str(plan_file),
                "--dry-run"
            ])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "### Milestone 1: Test" in result.output

    def test_convert_nonexistent_file(self, tmp_path):
        """Test error handling for nonexistent file."""
        from click.testing import CliRunner
        from orchestrator_auto.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["convert", "/nonexistent/file.md"])

        assert result.exit_code != 0


class TestIntegration:
    """Integration tests for convert functionality."""

    def test_converted_plan_is_valid(self, tmp_path):
        """Test that converted output passes validation."""
        # Create a plan that looks like it came from AI conversion
        converted_content = """---
feature: Test Feature
---

# Implementation Plan: Test Feature

## Overview
A simple test feature.

### Milestone 1: Setup
**Prerequisites:** None

**Tasks:**
1. Create initial structure
2. Set up dependencies

**Deliverables:**
- [ ] Project initialized
- [ ] Dependencies installed

### Milestone 2: Implementation
**Prerequisites:** Milestone 1

**Tasks:**
1. Write core logic
2. Add error handling

**Deliverables:**
- [ ] Core logic complete
- [ ] Error handling in place

### Milestone 3: Testing
**Prerequisites:** Milestone 2

**Tasks:**
1. Write unit tests
2. Run integration tests

**Deliverables:**
- [ ] All tests passing
- [ ] Coverage > 80%
"""
        is_valid, details = validate_plan_content(converted_content)

        assert is_valid is True
        assert details["milestones"] == 3
        assert details["milestone_names"] == ["Setup", "Implementation", "Testing"]
