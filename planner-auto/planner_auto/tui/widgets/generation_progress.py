"""Generation progress widget — shows 2-step synthesis + plan generation."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Static


class GenerationProgress(Static):
    """Widget showing 2-step generation progress.

    Step 1: Synthesizing context
    Step 2: Generating plan
    """

    DEFAULT_CSS = """
    GenerationProgress {
        height: auto;
        padding: 1 2;
    }
    GenerationProgress .gp-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    GenerationProgress .gp-step {
        margin-bottom: 1;
    }
    GenerationProgress .gp-active {
        color: $accent;
    }
    GenerationProgress .gp-done {
        color: #00ff41;
    }
    GenerationProgress .gp-pending {
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._step1_label: Label | None = None
        self._step2_label: Label | None = None
        self._step1_start: float | None = None
        self._step2_start: float | None = None

    def compose(self) -> ComposeResult:
        yield Label("Generating Plan", classes="gp-title")
        with Vertical():
            self._step1_label = Label(
                "  \u25cb Step 1: Synthesizing context...",
                classes="gp-step gp-pending",
            )
            yield self._step1_label
            self._step2_label = Label(
                "  \u25cb Step 2: Generating plan...",
                classes="gp-step gp-pending",
            )
            yield self._step2_label

    def start_synthesis(self, file_count: int, note_count: int) -> None:
        """Mark Step 1 as active."""
        self._step1_start = time.monotonic()
        if self._step1_label:
            self._step1_label.update(
                f"  \u25b6 Step 1: Synthesizing context ({file_count} files, {note_count} notes)..."
            )
            self._step1_label.remove_class("gp-pending")
            self._step1_label.add_class("gp-active")

    def complete_synthesis(self, output_size: int, latency_ms: int) -> None:
        """Mark Step 1 as complete."""
        if self._step1_label:
            self._step1_label.update(
                f"  \u2713 Step 1: Synthesis complete ({output_size:,} chars, {latency_ms}ms)"
            )
            self._step1_label.remove_class("gp-active")
            self._step1_label.add_class("gp-done")

    def start_generation(self, model: str) -> None:
        """Mark Step 2 as active."""
        self._step2_start = time.monotonic()
        if self._step2_label:
            self._step2_label.update(
                f"  \u25b6 Step 2: Generating plan ({model})..."
            )
            self._step2_label.remove_class("gp-pending")
            self._step2_label.add_class("gp-active")

    def complete_generation(
        self, draft_number: int, size: int, milestone_count: int, latency_ms: int
    ) -> None:
        """Mark Step 2 as complete."""
        if self._step2_label:
            self._step2_label.update(
                f"  \u2713 Step 2: Plan generated — Draft #{draft_number}, "
                f"{size:,} chars, {milestone_count} milestones ({latency_ms}ms)"
            )
            self._step2_label.remove_class("gp-active")
            self._step2_label.add_class("gp-done")

    def tick_elapsed(self) -> None:
        """Update elapsed time for active step."""
        now = time.monotonic()
        if self._step2_start and self._step2_label and "gp-active" in self._step2_label.classes:
            elapsed = int(now - self._step2_start)
            # Don't overwrite if already completed
            if "gp-active" in self._step2_label.classes:
                current = self._step2_label.renderable
                if isinstance(current, str) and "..." in current:
                    base = current.rsplit("...", 1)[0]
                    self._step2_label.update(f"{base}... {elapsed}s")
        elif self._step1_start and self._step1_label and "gp-active" in self._step1_label.classes:
            elapsed = int(now - self._step1_start)
            current = self._step1_label.renderable
            if isinstance(current, str) and "..." in current:
                base = current.rsplit("...", 1)[0]
                self._step1_label.update(f"{base}... {elapsed}s")
