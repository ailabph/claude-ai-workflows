"""Keybinding definitions for the session TUI, organized by phase.

Each phase maps to a list of (key, action_name, description) tuples.
The app swaps bindings when the phase changes.
"""

from __future__ import annotations

# Common bindings present in every phase
_COMMON: list[tuple[str, str, str]] = [
    ("e", "export", "Export"),
    ("l", "log_filter", "Log filter"),
    ("q", "quit", "Quit"),
    ("question_mark", "help", "Help"),
]

SESSION_BINDINGS: dict[str, list[tuple[str, str, str]]] = {
    "SETUP": [
        ("f", "add_file", "Add file"),
        ("n", "add_note", "Add note"),
        *_COMMON,
    ],
    "CONTEXT": [
        ("f", "add_file", "Add file"),
        ("n", "add_note", "Add note"),
        ("d", "advance_discussion", "Done \u2192 Discussion"),
        *_COMMON,
    ],
    "DISCUSSION": [
        ("ctrl+d", "advance_planning", "Done \u2192 Planning"),
        *_COMMON,
    ],
    "PLANNING": [
        ("g", "regenerate", "Generate/Regenerate plan"),
        ("r", "start_review", "Start review"),
        *_COMMON,
    ],
    "REVIEW": [
        ("d", "dispositions", "Dispositions"),
        ("p", "plan", "Plan"),
        ("r", "start_review", "Start/restart review"),
        *_COMMON,
    ],
    "COMPLETE": [
        ("p", "plan", "Plan"),
        ("c", "copy_plan_path", "Copy plan path"),
        *_COMMON,
    ],
    "PAUSED": [
        ("enter", "open_blocker", "Answer blocker"),
        *_COMMON,
    ],
}
