"""
Unit tests for input handler with paste support.
"""

import pytest
from unittest.mock import patch, MagicMock

from orchestrator_auto.input_handler import (
    PasteAwareInput,
    prompt_with_paste_support,
    simple_input,
    get_input_handler,
)


class TestPasteAwareInput:
    """Test PasteAwareInput class."""

    def test_initialization(self):
        """Test handler initializes correctly."""
        handler = PasteAwareInput()
        assert handler._paste_count == 0
        assert handler._session is None
        assert handler._last_paste_content is None

    def test_single_line_input(self):
        """Test single line input returns same for display and content."""
        handler = PasteAwareInput()

        with patch.object(handler, '_get_session') as mock_session:
            mock_prompt = MagicMock(return_value="single line input")
            mock_session.return_value.prompt = mock_prompt

            display, content = handler.prompt("Test: ")

            assert display == "single line input"
            assert content == "single line input"
            assert handler._paste_count == 0

    def test_multi_line_paste_detection(self):
        """Test multi-line paste is detected and collapsed."""
        handler = PasteAwareInput()

        multi_line = "line 1\nline 2\nline 3\nline 4"

        with patch.object(handler, '_get_session') as mock_session:
            mock_prompt = MagicMock(return_value=multi_line)
            mock_session.return_value.prompt = mock_prompt

            display, content = handler.prompt("Test: ")

            assert content == multi_line
            assert "[Pasted text #1:" in display
            assert "+3 lines]" in display
            assert handler._paste_count == 1
            assert handler._last_paste_content == multi_line

    def test_paste_count_increments(self):
        """Test paste count increments with each paste."""
        handler = PasteAwareInput()

        multi_line = "line 1\nline 2"

        with patch.object(handler, '_get_session') as mock_session:
            mock_prompt = MagicMock(return_value=multi_line)
            mock_session.return_value.prompt = mock_prompt

            handler.prompt("Test: ")
            assert handler._paste_count == 1

            handler.prompt("Test: ")
            assert handler._paste_count == 2

    def test_reset_paste_count(self):
        """Test paste count can be reset."""
        handler = PasteAwareInput()
        handler._paste_count = 5

        handler.reset_paste_count()

        assert handler._paste_count == 0

    def test_get_last_paste(self):
        """Test retrieving last paste content."""
        handler = PasteAwareInput()

        multi_line = "pasted content\nmore content"

        with patch.object(handler, '_get_session') as mock_session:
            mock_prompt = MagicMock(return_value=multi_line)
            mock_session.return_value.prompt = mock_prompt

            handler.prompt("Test: ")

            assert handler.get_last_paste() == multi_line

    def test_long_first_line_truncated(self):
        """Test long first line is truncated in display."""
        handler = PasteAwareInput()

        long_line = "x" * 100 + "\nline 2"

        with patch.object(handler, '_get_session') as mock_session:
            mock_prompt = MagicMock(return_value=long_line)
            mock_session.return_value.prompt = mock_prompt

            display, content = handler.prompt("Test: ")

            assert content == long_line
            assert "..." in display
            assert len(display) < len(long_line)

    def test_empty_input(self):
        """Test empty input returns empty strings."""
        handler = PasteAwareInput()

        with patch.object(handler, '_get_session') as mock_session:
            mock_prompt = MagicMock(return_value="")
            mock_session.return_value.prompt = mock_prompt

            display, content = handler.prompt("Test: ")

            assert display == ""
            assert content == ""

    def test_eof_handled(self):
        """Test EOF is handled gracefully."""
        handler = PasteAwareInput()

        with patch.object(handler, '_get_session') as mock_session:
            mock_session.return_value.prompt = MagicMock(side_effect=EOFError)

            display, content = handler.prompt("Test: ")

            assert display == ""
            assert content == ""

    def test_keyboard_interrupt_handled(self):
        """Test KeyboardInterrupt is handled gracefully."""
        handler = PasteAwareInput()

        with patch.object(handler, '_get_session') as mock_session:
            mock_session.return_value.prompt = MagicMock(side_effect=KeyboardInterrupt)

            display, content = handler.prompt("Test: ")

            assert display == ""
            assert content == ""


class TestModuleFunctions:
    """Test module-level convenience functions."""

    def test_get_input_handler_singleton(self):
        """Test get_input_handler returns same instance."""
        handler1 = get_input_handler()
        handler2 = get_input_handler()

        assert handler1 is handler2

    @patch('orchestrator_auto.input_handler.get_input_handler')
    def test_prompt_with_paste_support(self, mock_get_handler):
        """Test convenience function delegates to handler."""
        mock_handler = MagicMock()
        mock_handler.prompt.return_value = ("display", "content")
        mock_get_handler.return_value = mock_handler

        display, content = prompt_with_paste_support("Test: ")

        mock_handler.prompt.assert_called_once_with("Test: ")
        assert display == "display"
        assert content == "content"

    def test_simple_input_fallback(self):
        """Test simple_input uses standard input."""
        with patch('builtins.input', return_value="  user input  "):
            result = simple_input("Prompt: ")

            assert result == "user input"

    def test_simple_input_eof(self):
        """Test simple_input handles EOF."""
        with patch('builtins.input', side_effect=EOFError):
            result = simple_input("Prompt: ")

            assert result == ""

    def test_simple_input_keyboard_interrupt(self):
        """Test simple_input handles KeyboardInterrupt."""
        with patch('builtins.input', side_effect=KeyboardInterrupt):
            result = simple_input("Prompt: ")

            assert result == ""
