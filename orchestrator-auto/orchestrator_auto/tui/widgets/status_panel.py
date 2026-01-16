"""
Status panel widget for displaying workflow status and stats.
"""

from datetime import datetime
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Label
from typing import Optional


class StatusPanel(Static):
    """
    Panel showing current workflow status and statistics.

    Displays:
    - Phase and status
    - Session ID
    - Models being used (planner/executor)
    - API call count
    - Token count (estimated)
    - Elapsed time
    """

    DEFAULT_CSS = """
    StatusPanel {
        height: auto;
        min-height: 8;
        border: solid $primary;
        padding: 0 1;
        background: $surface;
    }

    StatusPanel .title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    StatusPanel .stat-row {
        height: 1;
    }

    StatusPanel .stat-label {
        color: $text-muted;
        width: 12;
    }

    StatusPanel .stat-value {
        color: $text;
    }

    StatusPanel .stat-value.phase-active {
        color: $primary;
        text-style: bold;
    }

    StatusPanel .stat-value.phase-paused {
        color: $warning;
    }

    StatusPanel .stat-value.phase-completed {
        color: $accent;
    }

    StatusPanel .stat-value.phase-failed {
        color: $error;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.phase = "—"
        self.status = "—"
        self.session_id = "—"
        self.planner_model = "—"
        self.executor_model = "—"
        self.api_calls = 0
        self.token_count = 0
        self._start_time: Optional[datetime] = None

    def compose(self) -> ComposeResult:
        yield Label("[b]STATUS[/b]", classes="title")
        with Vertical():
            with Horizontal(classes="stat-row"):
                yield Label("Phase:", classes="stat-label")
                yield Label(self.phase, id="phase-value", classes="stat-value phase-active")
            with Horizontal(classes="stat-row"):
                yield Label("Status:", classes="stat-label")
                yield Label(self.status, id="status-value", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("Session:", classes="stat-label")
                yield Label(self.session_id, id="session-value", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("Models:", classes="stat-label")
                yield Label(f"{self.planner_model}/{self.executor_model}", id="models-value", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("API Calls:", classes="stat-label")
                yield Label(str(self.api_calls), id="api-calls-value", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("Tokens:", classes="stat-label")
                yield Label(self._format_tokens(), id="tokens-value", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("Elapsed:", classes="stat-label")
                yield Label(self._format_elapsed(), id="elapsed-value", classes="stat-value")

    def update_phase(self, phase: str, status: str) -> None:
        """Update the phase and status display."""
        self.phase = phase.upper() if phase else "—"
        self.status = status.upper() if status else "—"

        if self.is_mounted:
            phase_label = self.query_one("#phase-value", Label)
            status_label = self.query_one("#status-value", Label)

            # Update text
            phase_label.update(self.phase)
            status_label.update(self.status)

            # Update phase styling
            phase_label.remove_class("phase-active", "phase-paused", "phase-completed", "phase-failed")
            if self.phase in ("DISCOVERY", "PLANNING", "EXECUTION"):
                phase_label.add_class("phase-active")
            elif self.phase == "PAUSED":
                phase_label.add_class("phase-paused")
            elif self.phase == "COMPLETED":
                if self.status == "FAILED":
                    phase_label.add_class("phase-failed")
                else:
                    phase_label.add_class("phase-completed")

    def update_session(self, session_id: str) -> None:
        """Update the session ID display."""
        self.session_id = session_id[:8] if session_id else "—"
        if self.is_mounted:
            self.query_one("#session-value", Label).update(self.session_id)

    def update_models(self, planner_model: str, executor_model: str) -> None:
        """Update the models display."""
        # Extract short model names
        self.planner_model = self._short_model_name(planner_model)
        self.executor_model = self._short_model_name(executor_model)
        if self.is_mounted:
            self.query_one("#models-value", Label).update(
                f"{self.planner_model}/{self.executor_model}"
            )

    def increment_api_calls(self, count: int = 1) -> None:
        """Increment the API call counter."""
        self.api_calls += count
        if self.is_mounted:
            self.query_one("#api-calls-value", Label).update(str(self.api_calls))

    def add_tokens(self, count: int) -> None:
        """Add to the token counter."""
        self.token_count += count
        if self.is_mounted:
            self.query_one("#tokens-value", Label).update(self._format_tokens())

    def start_timer(self) -> None:
        """Start the elapsed time timer."""
        self._start_time = datetime.now()

    def update_elapsed(self) -> None:
        """Update the elapsed time display."""
        if self.is_mounted:
            self.query_one("#elapsed-value", Label).update(self._format_elapsed())

    def _format_tokens(self) -> str:
        """Format token count with K/M suffixes."""
        if self.token_count >= 1_000_000:
            return f"{self.token_count / 1_000_000:.1f}M"
        elif self.token_count >= 1_000:
            return f"{self.token_count / 1_000:.1f}K"
        return str(self.token_count)

    def _format_elapsed(self) -> str:
        """Format elapsed time as HH:MM:SS."""
        if not self._start_time:
            return "00:00:00"
        elapsed = datetime.now() - self._start_time
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _short_model_name(self, model: str) -> str:
        """Extract short model name from full model ID."""
        if not model:
            return "—"
        # Handle common patterns
        if "opus" in model.lower():
            return "opus"
        elif "sonnet" in model.lower():
            return "sonnet"
        elif "haiku" in model.lower():
            return "haiku"
        # Return last part after any hyphens, limited to 8 chars
        parts = model.split("-")
        return parts[0][:8] if parts else model[:8]
