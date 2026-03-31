"""TUI package for planner-auto review dashboard and session TUI.

Textual is an optional dependency.  Use ``get_review_app_class()`` or
``get_session_app_class()`` to lazily import the app class — this avoids
import errors when textual is not installed.
"""

from __future__ import annotations


def get_review_app_class():
    """Lazily import and return the ``ReviewTUI`` class.

    Raises:
        ImportError: If textual is not installed.
    """
    from planner_auto.tui.review_app import ReviewTUI

    return ReviewTUI


def get_session_app_class():
    """Lazily import and return the ``SessionTUI`` class.

    Raises:
        ImportError: If textual is not installed.
    """
    from planner_auto.tui.session_app import SessionTUI

    return SessionTUI
