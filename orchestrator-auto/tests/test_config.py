"""
Unit tests for configuration management.
"""

import pytest
import tempfile
import os
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto import config


class TestModelAliases:
    """Test model alias resolution."""

    def test_resolve_opus_alias(self):
        """Test that 'opus' resolves to full model ID."""
        result = config.resolve_model("opus")
        assert result == "claude-opus-4-5-20251101"

    def test_resolve_sonnet_alias(self):
        """Test that 'sonnet' resolves to full model ID."""
        result = config.resolve_model("sonnet")
        assert result == "claude-sonnet-4-5-20250929"

    def test_resolve_haiku_alias(self):
        """Test that 'haiku' resolves to full model ID."""
        result = config.resolve_model("haiku")
        assert result == "claude-haiku-3-5-20241022"

    def test_resolve_alias_case_insensitive(self):
        """Test that alias resolution is case insensitive."""
        assert config.resolve_model("OPUS") == "claude-opus-4-5-20251101"
        assert config.resolve_model("Sonnet") == "claude-sonnet-4-5-20250929"
        assert config.resolve_model("HaIkU") == "claude-haiku-3-5-20241022"

    def test_resolve_full_model_id(self):
        """Test that full model IDs pass through unchanged."""
        full_id = "claude-opus-4-5-20251101"
        result = config.resolve_model(full_id)
        assert result == full_id

    def test_resolve_none(self):
        """Test that None input returns None."""
        result = config.resolve_model(None)
        assert result is None


class TestModelDisplayName:
    """Test model display name generation."""

    def test_display_name_opus(self):
        """Test display name for opus model."""
        result = config.get_model_display_name("claude-opus-4-5-20251101")
        assert result == "opus-4.5"

    def test_display_name_sonnet(self):
        """Test display name for sonnet model."""
        result = config.get_model_display_name("claude-sonnet-4-5-20250929")
        assert result == "sonnet-4.5"

    def test_display_name_haiku(self):
        """Test display name for haiku model."""
        result = config.get_model_display_name("claude-haiku-3-5-20241022")
        assert result == "haiku-3.5"

    def test_display_name_unknown_model(self):
        """Test display name for unknown model with 202x date."""
        # The function strips "claude-" prefix and cuts at "-202" pattern
        result = config.get_model_display_name("claude-future-model-20260101")
        assert result == "future-model"

    def test_display_name_unknown_model_no_date(self):
        """Test display name for model without date pattern."""
        result = config.get_model_display_name("claude-custom-model")
        assert result == "custom-model"


class TestDefaultModels:
    """Test default model getters."""

    def test_default_planner_model(self):
        """Test that default planner model is opus."""
        result = config.get_planner_model(None)
        assert result == "claude-opus-4-5-20251101"

    def test_default_executor_model(self):
        """Test that default executor model is sonnet."""
        result = config.get_executor_model(None)
        assert result == "claude-sonnet-4-5-20250929"

    def test_cli_planner_model_override(self):
        """Test that CLI model overrides default."""
        result = config.get_planner_model("haiku")
        assert result == "claude-haiku-3-5-20241022"

    def test_cli_executor_model_override(self):
        """Test that CLI model overrides default."""
        result = config.get_executor_model("opus")
        assert result == "claude-opus-4-5-20251101"


class TestListModels:
    """Test model listing."""

    def test_list_available_models(self):
        """Test that available models are listed."""
        models = config.list_available_models()

        assert "opus" in models
        assert "sonnet" in models
        assert "haiku" in models
        assert len(models) == 3
