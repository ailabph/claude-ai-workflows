"""Keybinding definitions for the review TUI."""

from __future__ import annotations

# Each tuple: (key, action_name, description)
REVIEW_BINDINGS: list[tuple[str, str, str]] = [
    ("d", "dispositions", "Dispositions"),
    ("p", "plan", "Plan"),
    ("l", "log_filter", "Log filter"),
    ("q", "quit", "Quit"),
    ("question_mark", "help", "Help"),
    ("enter", "select_round", "Round detail"),
    ("escape", "back", "Back"),
    ("n", "next_round", "Next round"),
    ("r", "raw_response", "Raw response"),
]
