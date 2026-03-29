"""Session metadata panel widget."""

from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import Label, Static


class SessionPanel(Static):
    """Displays session metadata as field: value label pairs."""

    DEFAULT_CSS = """
    SessionPanel {
        height: auto;
        padding: 1;
    }
    SessionPanel .sp-field {
        color: $text-muted;
    }
    SessionPanel .sp-value {
        color: $text;
        margin-bottom: 1;
    }
    SessionPanel .sp-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._labels: dict[str, Label] = {}

    def compose(self):
        yield Label("Session", classes="sp-title")
        fields = [
            ("session_id", "ID"),
            ("phase", "Phase"),
            ("status", "Status"),
            ("project", "Project"),
            ("complexity", "Complexity"),
            ("max_rounds", "Round cap"),
            ("backend", "Backend"),
        ]
        with Vertical():
            for key, display_name in fields:
                lbl = Label(f"{display_name}: —", classes="sp-value", id=f"sp-{key}")
                self._labels[key] = lbl
                yield lbl

    def set_field(self, key: str, value: str) -> None:
        """Update a single field value."""
        field_names = {
            "session_id": "ID",
            "phase": "Phase",
            "status": "Status",
            "project": "Project",
            "complexity": "Complexity",
            "max_rounds": "Round cap",
            "backend": "Backend",
        }
        if key in self._labels:
            display = field_names.get(key, key)
            self._labels[key].update(f"{display}: {value}")

    def update_phase(self, phase: str) -> None:
        """Update the phase field."""
        self.set_field("phase", phase)

    def update_status(self, status: str) -> None:
        """Update the status field."""
        self.set_field("status", status)
