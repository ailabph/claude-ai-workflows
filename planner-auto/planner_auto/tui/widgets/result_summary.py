"""Result summary widget — shows completion summary with artifacts."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Static


class ResultSummary(Static):
    """Completion summary using only currently-available data.

    Shows: checkmarks, review rounds, cost, artifacts, kafra path.
    """

    DEFAULT_CSS = """
    ResultSummary {
        height: auto;
        padding: 1 2;
    }
    ResultSummary .rs-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    ResultSummary .rs-check {
        color: #00ff41;
    }
    ResultSummary .rs-metric {
        color: $accent;
    }
    ResultSummary .rs-path {
        color: $text;
        padding: 0 0 0 2;
    }
    ResultSummary .rs-section {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Label("Session Complete", classes="rs-title")
        with Vertical(id="rs-content"):
            yield Label("Loading summary...", id="rs-loading")

    def set_summary(
        self,
        export_paths: list[str],
        kafra_path: str | None,
        total_cost: float,
        review_rounds: int = 0,
        draft_number: int = 0,
        plan_size: int = 0,
        milestone_count: int = 0,
    ) -> None:
        """Populate the summary with completion data."""
        content = self.query_one("#rs-content", Vertical)

        # Remove loading
        try:
            content.query_one("#rs-loading").remove()
        except Exception:
            pass

        # Checkmarks
        content.mount(Label("\u2713 Plan approved", classes="rs-check"))
        content.mount(Label(f"\u2713 Exported ({len(export_paths)} artifacts)", classes="rs-check"))
        if kafra_path:
            content.mount(Label("\u2713 .kafra handoff", classes="rs-check"))

        # Metrics
        content.mount(Label("Metrics", classes="rs-section"))
        if review_rounds > 0:
            content.mount(Label(f"  Review rounds: {review_rounds}", classes="rs-metric"))
        content.mount(Label(f"  Total GPT cost: ${total_cost:.4f}", classes="rs-metric"))
        if draft_number > 0:
            content.mount(Label(
                f"  Final plan: Draft #{draft_number}, {plan_size:,} chars, {milestone_count} milestones",
                classes="rs-metric",
            ))

        # Artifacts
        if export_paths:
            content.mount(Label("Artifacts", classes="rs-section"))
            for path in export_paths:
                content.mount(Label(f"  {path}", classes="rs-path"))
        if kafra_path:
            content.mount(Label(f"  .kafra: {kafra_path}", classes="rs-path"))
