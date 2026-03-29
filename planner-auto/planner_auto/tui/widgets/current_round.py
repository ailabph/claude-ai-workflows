"""Current round widget — shows live sub-phase with elapsed timer."""

from __future__ import annotations

from textual.widgets import Static, Label, ProgressBar
from textual.containers import Vertical


class CurrentRound(Static):
    """Shows the current review sub-phase with elapsed timer.

    Sub-phase transitions are driven by messages:
    - ``RoundStarted``       → GPT reviewing phase
    - ``ReviewComplete``     → brief pause
    - ``FeedbackValidated``  → disposition summary
    - ``RevisionStarted``    → Claude revising phase
    - ``RevisionComplete``   → idle
    """

    DEFAULT_CSS = """
    CurrentRound {
        height: auto;
        padding: 1;
        margin-top: 1;
    }
    CurrentRound .cr-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    CurrentRound .cr-phase {
        color: $accent;
    }
    CurrentRound .cr-elapsed {
        color: $text-muted;
    }
    CurrentRound .cr-idle {
        color: $text-muted;
    }
    CurrentRound .cr-retry {
        color: $warning;
    }
    """

    PHASE_IDLE = "idle"
    PHASE_GPT_REVIEW = "gpt_review"
    PHASE_FEEDBACK = "feedback"
    PHASE_REVISION = "revision"
    PHASE_RETRY = "retry"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._phase: str = self.PHASE_IDLE
        self._round_num: int = 0
        self._elapsed_seconds: int = 0
        self._disposition_summary: str = ""
        self._retry_info: str = ""
        # For estimating revision progress.
        self._prior_revision_latencies: list[int] = []

    def compose(self):
        yield Label("Current", classes="cr-title")
        with Vertical():
            yield Label("Idle", id="cr-phase-label", classes="cr-phase cr-idle")
            yield Label("", id="cr-elapsed-label", classes="cr-elapsed")

    def set_gpt_review(self, round_num: int) -> None:
        """Enter GPT reviewing phase."""
        self._phase = self.PHASE_GPT_REVIEW
        self._round_num = round_num
        self._elapsed_seconds = 0
        self._update_display()

    def set_feedback(self, accepted: int, deferred: int, rejected: int) -> None:
        """Show disposition summary briefly."""
        self._phase = self.PHASE_FEEDBACK
        parts = []
        if accepted:
            parts.append(f"{accepted} ACCEPT")
        if deferred:
            parts.append(f"{deferred} DEFER")
        if rejected:
            parts.append(f"{rejected} REJECT")
        self._disposition_summary = ", ".join(parts) if parts else "no dispositions"
        self._update_display()

    def set_revision(self, round_num: int) -> None:
        """Enter Claude revising phase."""
        self._phase = self.PHASE_REVISION
        self._round_num = round_num
        self._elapsed_seconds = 0
        self._update_display()

    def set_retry(self, round_num: int, timeout_sec: int, retry_count: int) -> None:
        """Show retry status after timeout."""
        self._phase = self.PHASE_RETRY
        self._round_num = round_num
        self._retry_info = f"RETRY #{retry_count} after {timeout_sec}s timeout"
        self._update_display()

    def record_revision_latency(self, latency_ms: int) -> None:
        """Record a revision latency for progress estimation."""
        self._prior_revision_latencies.append(latency_ms)

    def clear(self) -> None:
        """Reset to idle state."""
        self._phase = self.PHASE_IDLE
        self._elapsed_seconds = 0
        self._disposition_summary = ""
        self._retry_info = ""
        self._update_display()

    def tick(self) -> None:
        """Called every 1s to update the elapsed timer."""
        if self._phase in (self.PHASE_GPT_REVIEW, self.PHASE_REVISION):
            self._elapsed_seconds += 1
            self._update_display()

    def _update_display(self) -> None:
        """Re-render the phase and elapsed labels."""
        try:
            phase_label = self.query_one("#cr-phase-label", Label)
            elapsed_label = self.query_one("#cr-elapsed-label", Label)
        except Exception:
            return

        if self._phase == self.PHASE_IDLE:
            phase_label.update("Idle")
            phase_label.remove_class("cr-phase")
            phase_label.add_class("cr-idle")
            elapsed_label.update("")
        elif self._phase == self.PHASE_GPT_REVIEW:
            phase_label.update(f"R{self._round_num}: GPT reviewing...")
            phase_label.remove_class("cr-idle", "cr-retry")
            phase_label.add_class("cr-phase")
            elapsed_label.update(f"  {self._elapsed_seconds}s elapsed")
        elif self._phase == self.PHASE_FEEDBACK:
            phase_label.update(f"R{self._round_num}: {self._disposition_summary}")
            phase_label.remove_class("cr-idle", "cr-retry")
            phase_label.add_class("cr-phase")
            elapsed_label.update("")
        elif self._phase == self.PHASE_REVISION:
            avg_ms = (
                sum(self._prior_revision_latencies) // len(self._prior_revision_latencies)
                if self._prior_revision_latencies
                else 0
            )
            est = f" (est ~{avg_ms // 1000}s)" if avg_ms else ""
            phase_label.update(f"R{self._round_num}: Claude revising...{est}")
            phase_label.remove_class("cr-idle", "cr-retry")
            phase_label.add_class("cr-phase")
            elapsed_label.update(f"  {self._elapsed_seconds}s elapsed")
        elif self._phase == self.PHASE_RETRY:
            phase_label.update(f"R{self._round_num}: {self._retry_info}")
            phase_label.remove_class("cr-idle", "cr-phase")
            phase_label.add_class("cr-retry")
            elapsed_label.update("")
