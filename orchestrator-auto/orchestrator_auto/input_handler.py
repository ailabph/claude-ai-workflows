"""
Input handling with multi-line paste support.

Uses prompt_toolkit to detect bracketed paste and display
collapsed previews for pasted content.
"""

from typing import Optional, Tuple
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.formatted_text import HTML


class PasteAwareInput:
    """
    Input handler that detects multi-line paste and shows collapsed previews.

    When content is pasted (detected via bracketed paste mode), it captures
    all lines and displays a summary like "[Pasted +19 lines]" instead of
    flooding the terminal.
    """

    def __init__(self):
        self._paste_count = 0
        self._session: Optional[PromptSession] = None
        self._last_paste_content: Optional[str] = None

    def _get_session(self) -> PromptSession:
        """Get or create prompt session."""
        if self._session is None:
            bindings = KeyBindings()

            # Handle Enter key - submit on Enter
            @bindings.add(Keys.Enter)
            def handle_enter(event):
                """Submit on Enter."""
                event.current_buffer.validate_and_handle()

            self._session = PromptSession(
                key_bindings=bindings,
                multiline=False,  # Single line mode, paste detected separately
                enable_open_in_editor=False,
            )
        return self._session

    def prompt(
        self,
        prompt_text: str = "You: ",
        return_none_on_eof: bool = False,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Prompt for user input with paste detection.

        Args:
            prompt_text: The prompt to display
            return_none_on_eof: If True, return (None, None) on EOF/Ctrl+D.
                               If False (default), return ("", "") for backward compatibility.

        Returns:
            Tuple of (display_text, full_content)
            - (None, None) on EOF/Ctrl+D when return_none_on_eof=True
            - ("", "") on EOF/Ctrl+D when return_none_on_eof=False (default)
            - ("", "") on empty input (just Enter)
            - (display, content) on normal input
        """
        session = self._get_session()

        try:
            # Get input - prompt_toolkit handles bracketed paste
            text = session.prompt(prompt_text)

            if not text:
                return "", ""

            # Check if this looks like a multi-line paste
            lines = text.split('\n')

            if len(lines) > 1:
                # Multi-line paste detected
                self._paste_count += 1
                first_line = lines[0][:50]
                if len(lines[0]) > 50:
                    first_line += "..."

                extra_lines = len(lines) - 1
                display = f"[Pasted text #{self._paste_count}: \"{first_line}\" +{extra_lines} lines]"

                self._last_paste_content = text
                return display, text
            else:
                # Single line input
                return text, text

        except EOFError:
            if return_none_on_eof:
                return None, None
            return "", ""
        except KeyboardInterrupt:
            # Always re-raise KeyboardInterrupt - let caller handle it
            # (orchestrator has signal handler, chat has try/except)
            raise

    def get_last_paste(self) -> Optional[str]:
        """Get the content of the last paste operation."""
        return self._last_paste_content

    def reset_paste_count(self):
        """Reset the paste counter."""
        self._paste_count = 0


# Global instance for convenience
_input_handler: Optional[PasteAwareInput] = None


def get_input_handler() -> PasteAwareInput:
    """Get the global input handler instance."""
    global _input_handler
    if _input_handler is None:
        _input_handler = PasteAwareInput()
    return _input_handler


def prompt_with_paste_support(
    prompt_text: str = "You: ",
    return_none_on_eof: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Prompt for input with multi-line paste support.

    Args:
        prompt_text: The prompt to display
        return_none_on_eof: If True, return (None, None) on EOF.
                           If False (default), return ("", "").

    Returns:
        Tuple of (display_text, full_content)
    """
    handler = get_input_handler()
    return handler.prompt(prompt_text, return_none_on_eof=return_none_on_eof)


def simple_input(prompt_text: str = "You: ") -> str:
    """
    Simple input fallback using standard input.

    Args:
        prompt_text: The prompt to display

    Returns:
        User input string
    """
    try:
        return input(prompt_text).strip()
    except (EOFError, KeyboardInterrupt):
        return ""
