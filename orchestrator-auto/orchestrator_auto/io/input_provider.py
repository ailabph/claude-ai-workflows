"""
Input provider abstraction for orchestrator.

Provides an abstract interface for user input that can be implemented
by different UI backends (CLI, TUI, etc.).
"""

from abc import ABC, abstractmethod
from typing import Tuple, Optional, List


class InputProvider(ABC):
    """
    Abstract input provider for orchestrator.

    Implementations must provide methods for getting user input
    in various contexts (prompts, choices, confirmations).
    """

    @abstractmethod
    def prompt(
        self,
        prompt_text: str,
        return_none_on_eof: bool = False,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Get user input.

        Args:
            prompt_text: Text to display as prompt
            return_none_on_eof: If True, return (None, None) on EOF.
                               If False, return ("", "").

        Returns:
            Tuple of (display_text, actual_input)
            - display_text may be truncated for long pastes
            - actual_input is the full content
            - (None, None) on EOF if return_none_on_eof=True
            - ("", "") on EOF if return_none_on_eof=False
        """
        pass

    @abstractmethod
    def prompt_choice(
        self,
        prompt_text: str,
        choices: List[str],
        default: Optional[str] = None,
    ) -> str:
        """
        Get user choice from options.

        Args:
            prompt_text: Text to display as prompt
            choices: List of valid choices
            default: Default choice if user just presses Enter

        Returns:
            Selected choice string
        """
        pass

    def prompt_confirm(
        self,
        prompt_text: str,
        default: bool = True,
    ) -> bool:
        """
        Get yes/no confirmation from user.

        Args:
            prompt_text: Text to display as prompt
            default: Default value if user just presses Enter

        Returns:
            True for yes, False for no
        """
        choices = ["y", "n"]
        default_choice = "y" if default else "n"
        result = self.prompt_choice(prompt_text, choices, default_choice)
        return result.lower() in ("y", "yes")


class CLIInputProvider(InputProvider):
    """
    Terminal-based input using prompt_toolkit.

    Wraps the existing prompt_with_paste_support functionality
    for backward compatibility with CLI usage.
    """

    def prompt(
        self,
        prompt_text: str,
        return_none_on_eof: bool = False,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Get user input using prompt_toolkit with paste detection.

        Args:
            prompt_text: Text to display as prompt
            return_none_on_eof: If True, return (None, None) on EOF

        Returns:
            Tuple of (display_text, actual_input)
        """
        from ..input_handler import prompt_with_paste_support
        return prompt_with_paste_support(prompt_text, return_none_on_eof)

    def prompt_choice(
        self,
        prompt_text: str,
        choices: List[str],
        default: Optional[str] = None,
    ) -> str:
        """
        Get user choice using click's prompt.

        Args:
            prompt_text: Text to display as prompt
            choices: List of valid choices
            default: Default choice if user just presses Enter

        Returns:
            Selected choice string
        """
        import click
        return click.prompt(
            prompt_text,
            type=click.Choice(choices),
            default=default,
        )
