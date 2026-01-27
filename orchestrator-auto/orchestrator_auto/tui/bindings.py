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
    Binding("r", "respond", "Respond"),
    Binding("R", "refresh", "Refresh"),
    Binding("c", "clear", "Clear"),
    Binding("g", "show_git_diff", "Git Diff"),
    Binding("y", "copy_session_id", "Copy ID"),
    Binding("b", "show_blocker", "Blocker"),
    # Phase 2: Panel navigation
    Binding("tab", "focus_next", "Next Panel", show=False),
    Binding("shift+tab", "focus_prev", "Prev Panel", show=False),
    Binding("j", "scroll_down", "Scroll Down", show=False),
    Binding("k", "scroll_up", "Scroll Up", show=False),
    # Phase 2: Log filter
    Binding("1", "filter_errors", "Errors", show=False),
    Binding("2", "filter_warnings", "Warnings", show=False),
    Binding("3", "filter_all", "All Logs", show=False),
    # Phase 3: Execution control
    Binding("p", "toggle_pause", "Pause"),
    # Compact mode: Agent toggle ([ for planner, ] for executor)
    Binding("[", "show_planner", "Planner", show=True),
    Binding("]", "show_executor", "Executor", show=True),
]

# Todo mode bindings
TODO_BINDINGS = [
    Binding("l", "toggle_logs", "Logs"),
    Binding("t", "toggle_tasks", "Tasks"),
    Binding("s", "show_status", "Status"),
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
        mode: One of "session", "queue", "watch", "todo", "input"

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
    elif mode == "todo":
        bindings.extend(TODO_BINDINGS)
    elif mode == "input":
        bindings.extend(INPUT_BINDINGS)

    return bindings
