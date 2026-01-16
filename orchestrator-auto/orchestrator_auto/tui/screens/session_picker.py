"""
Session picker screen for resuming workflows.

Displays a list of resumable sessions for the current project.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, Label, ListView, ListItem
from typing import Optional, List, Dict, Any, Callable


class SessionItem(ListItem):
    """A session item in the picker list."""

    def __init__(self, session: Dict[str, Any]) -> None:
        super().__init__()
        self.session = session
        self.session_id = session.get("id", "")
        self.feature = session.get("feature_description", "")[:40]
        self.phase = session.get("phase", "")
        self.status = session.get("status", "")
        self._update_classes()

    def _update_classes(self) -> None:
        """Update CSS classes based on status."""
        if self.status == "paused":
            self.add_class("session-paused")
        elif self.status == "active":
            self.add_class("session-active")

    def compose(self) -> ComposeResult:
        short_id = self.session_id[:8] if self.session_id else "—"
        status_icon = "⏸" if self.status == "paused" else "▶" if self.status == "active" else "○"
        yield Label(f"{status_icon} [{short_id}] {self.feature} ({self.phase})")


class SessionPickerScreen(ModalScreen[Optional[str]]):
    """
    Modal screen for selecting a session to resume.

    Returns the selected session ID or None if cancelled.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("enter", "select", "Select", priority=True),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
    ]

    CSS = """
    SessionPickerScreen {
        align: center middle;
    }

    SessionPickerScreen > Vertical {
        width: 70;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: heavy $primary;
        padding: 1 2;
    }

    SessionPickerScreen .picker-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    SessionPickerScreen .picker-empty {
        text-align: center;
        color: $text-muted;
        text-style: italic;
        margin: 1 0;
    }

    SessionPickerScreen ListView {
        background: transparent;
        height: auto;
        max-height: 15;
        margin: 1 0;
    }

    SessionPickerScreen ListItem {
        padding: 0 1;
    }

    SessionPickerScreen ListItem:hover {
        background: $secondary;
    }

    SessionPickerScreen ListItem.--highlight {
        background: $primary;
        color: $background;
    }

    SessionPickerScreen .session-paused Label {
        color: $warning;
    }

    SessionPickerScreen .session-active Label {
        color: $primary;
    }

    SessionPickerScreen .picker-footer {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        sessions: List[Dict[str, Any]],
        on_select: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Initialize session picker.

        Args:
            sessions: List of session dicts with id, feature_description, phase, status
            on_select: Optional callback when session is selected
        """
        super().__init__()
        self.sessions = sessions
        self.on_select_callback = on_select
        self._selected_session_id: Optional[str] = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("SELECT SESSION TO RESUME", classes="picker-title")

            if not self.sessions:
                yield Label("No resumable sessions found", classes="picker-empty")
            else:
                list_view = ListView(id="session-list")
                for session in self.sessions:
                    list_view.compose_add_child(SessionItem(session))
                yield list_view

            yield Label("Enter=Select  Escape=Cancel", classes="picker-footer")

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(None)

    def action_select(self) -> None:
        """Select the highlighted session."""
        try:
            list_view = self.query_one("#session-list", ListView)
            if list_view.highlighted_child is not None:
                item = list_view.highlighted_child
                if isinstance(item, SessionItem):
                    session_id = item.session_id
                    if self.on_select_callback:
                        self.on_select_callback(session_id)
                    self.dismiss(session_id)
        except Exception:
            self.dismiss(None)

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        try:
            list_view = self.query_one("#session-list", ListView)
            list_view.action_cursor_up()
        except Exception:
            pass

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        try:
            list_view = self.query_one("#session-list", ListView)
            list_view.action_cursor_down()
        except Exception:
            pass
