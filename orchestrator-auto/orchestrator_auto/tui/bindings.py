"""
Keyboard bindings for the TUI.

Defines the keyboard shortcuts available in the TUI.
"""

from textual.binding import Binding


# Global bindings available throughout the app
GLOBAL_BINDINGS = [
    Binding("q", "quit", "Quit", priority=True),
    Binding("?", "show_help", "Help"),
    Binding("escape", "back", "Back", show=False),
]

# Session mode bindings
SESSION_BINDINGS = [
    Binding("l", "toggle_logs", "Logs"),
    Binding("m", "toggle_milestones", "Milestones"),
    Binding("s", "show_status", "Status"),
]

# Queue mode bindings
QUEUE_BINDINGS = [
    Binding("n", "next_item", "Next"),
    Binding("k", "skip_item", "Skip"),
    Binding("r", "refresh", "Refresh"),
    Binding("c", "clear_queue", "Clear Queue"),
]

# Watch mode bindings
WATCH_BINDINGS = [
    Binding("r", "refresh", "Refresh"),
    Binding("c", "clear", "Clear"),
    Binding("g", "show_git_diff", "Git Diff"),
]

# Input modal bindings
INPUT_BINDINGS = [
    Binding("enter", "submit", "Submit", priority=True),
    Binding("escape", "cancel", "Cancel", priority=True),
    Binding("ctrl+v", "paste", "Paste", show=False),
]


def get_bindings_for_mode(mode: str) -> list:
    """
    Get the appropriate bindings for a given mode.

    Args:
        mode: One of "session", "queue", "watch", "input"

    Returns:
        List of Binding objects.
    """
    bindings = list(GLOBAL_BINDINGS)

    if mode == "session":
        bindings.extend(SESSION_BINDINGS)
    elif mode == "queue":
        bindings.extend(QUEUE_BINDINGS)
    elif mode == "watch":
        bindings.extend(WATCH_BINDINGS)
    elif mode == "input":
        bindings.extend(INPUT_BINDINGS)

    return bindings
