"""
Unit tests for output utilities.
"""

import pytest
import time
from unittest.mock import Mock, patch
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto.output import (
    StreamingIndicator,
    create_activity_indicator,
)


class TestStreamingIndicator:
    """Test StreamingIndicator class."""

    def test_initialization(self):
        """Test StreamingIndicator initialization."""
        indicator = StreamingIndicator(
            interval=2.0,
            snippet_length=40,
            show_tokens=False,
        )

        assert indicator.interval == 2.0
        assert indicator.snippet_length == 40
        assert indicator.show_tokens is False
        assert indicator.buffer == ""
        assert indicator.token_count == 0

    def test_on_chunk_accumulates_text(self):
        """Test that on_chunk accumulates text in buffer."""
        indicator = StreamingIndicator(interval=10.0)  # Long interval to prevent output

        indicator.on_chunk("Hello ")
        indicator.on_chunk("world!")

        assert indicator.buffer == "Hello world!"
        assert indicator.token_count == 2

    def test_on_chunk_counts_tokens(self):
        """Test that on_chunk counts tokens correctly."""
        indicator = StreamingIndicator(interval=10.0)

        indicator.on_chunk("This is a test with multiple words")

        assert indicator.token_count == 7

    def test_on_chunk_triggers_output_at_interval(self):
        """Test that on_chunk triggers output at the specified interval."""
        output_calls = []

        def mock_output(text):
            output_calls.append(text)

        indicator = StreamingIndicator(
            interval=0.0,  # Immediate output
            output_func=mock_output,
        )

        indicator.on_chunk("First chunk")
        indicator.on_chunk("Second chunk")

        # Should have output at least once
        assert len(output_calls) >= 1

    def test_finish_clears_line(self):
        """Test that finish clears the indicator line."""
        output_calls = []

        def mock_output(text):
            output_calls.append(text)

        indicator = StreamingIndicator(output_func=mock_output)
        indicator._active = True

        indicator.finish()

        # Should output a clear line sequence
        assert len(output_calls) == 1
        assert "\r" in output_calls[0]

    def test_finish_does_nothing_if_not_active(self):
        """Test that finish does nothing if indicator wasn't used."""
        output_calls = []

        def mock_output(text):
            output_calls.append(text)

        indicator = StreamingIndicator(output_func=mock_output)
        # _active is False by default

        indicator.finish()

        assert len(output_calls) == 0

    def test_reset_clears_state(self):
        """Test that reset clears all state."""
        indicator = StreamingIndicator()
        indicator.buffer = "some text"
        indicator.token_count = 10
        indicator.last_output_time = 123.456
        indicator._active = True

        indicator.reset()

        assert indicator.buffer == ""
        assert indicator.token_count == 0
        assert indicator.last_output_time == 0
        assert indicator._active is False

    def test_display_snippet_with_tokens(self):
        """Test display output format with tokens."""
        output_calls = []

        def mock_output(text):
            output_calls.append(text)

        indicator = StreamingIndicator(
            show_tokens=True,
            snippet_length=20,
            output_func=mock_output,
        )
        indicator.buffer = "This is a longer text that should be truncated"
        indicator.token_count = 9

        indicator._display_snippet()

        assert len(output_calls) == 1
        assert "[9 tokens]" in output_calls[0]
        assert "⏳" in output_calls[0]

    def test_display_snippet_without_tokens(self):
        """Test display output format without tokens."""
        output_calls = []

        def mock_output(text):
            output_calls.append(text)

        indicator = StreamingIndicator(
            show_tokens=False,
            output_func=mock_output,
        )
        indicator.buffer = "Some text"

        indicator._display_snippet()

        assert len(output_calls) == 1
        assert "tokens" not in output_calls[0]
        assert "⏳" in output_calls[0]

    def test_snippet_removes_newlines(self):
        """Test that newlines are removed from snippet."""
        output_calls = []

        def mock_output(text):
            output_calls.append(text)

        indicator = StreamingIndicator(output_func=mock_output)
        indicator.buffer = "Line 1\nLine 2\nLine 3"

        indicator._display_snippet()

        assert "\n" not in output_calls[0]


class TestCreateActivityIndicator:
    """Test create_activity_indicator factory function."""

    def test_creates_indicator_when_enabled(self):
        """Test that factory creates indicator when enabled."""
        indicator = create_activity_indicator(enabled=True)

        assert indicator is not None
        assert isinstance(indicator, StreamingIndicator)

    def test_returns_none_when_disabled(self):
        """Test that factory returns None when disabled."""
        indicator = create_activity_indicator(enabled=False)

        assert indicator is None

    def test_passes_parameters(self):
        """Test that factory passes parameters to indicator."""
        indicator = create_activity_indicator(
            enabled=True,
            interval=3.0,
            show_tokens=False,
        )

        assert indicator.interval == 3.0
        assert indicator.show_tokens is False


class TestStreamingIndicatorIntegration:
    """Integration tests for StreamingIndicator with simulated streaming."""

    def test_simulated_streaming(self):
        """Test indicator with simulated streaming chunks."""
        output_calls = []

        def mock_output(text):
            output_calls.append(text)

        indicator = StreamingIndicator(
            interval=0.0,  # Immediate output for testing
            output_func=mock_output,
        )

        # Simulate streaming chunks
        chunks = [
            "def ",
            "hello",
            "()",
            ":\n",
            "    ",
            "print",
            "('Hello')",
        ]

        for chunk in chunks:
            indicator.on_chunk(chunk)

        indicator.finish()

        # Should have accumulated all text
        assert indicator.buffer == "def hello():\n    print('Hello')"

        # Should have output multiple times (due to interval=0)
        assert len(output_calls) > 1

    def test_throttled_output(self):
        """Test that output is throttled by interval."""
        output_calls = []

        def mock_output(text):
            output_calls.append(text)

        indicator = StreamingIndicator(
            interval=0.5,  # 500ms between outputs
            output_func=mock_output,
        )

        # Send many chunks quickly
        for i in range(10):
            indicator.on_chunk(f"chunk{i} ")

        # Should have limited outputs due to throttling
        # At most 2-3 outputs for immediate calls
        assert len(output_calls) <= 3
