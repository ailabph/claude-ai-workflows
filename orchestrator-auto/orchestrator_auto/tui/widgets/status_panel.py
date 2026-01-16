"""
Status panel widget for displaying workflow status and stats.
"""

import re
from datetime import datetime
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Label
from textual.timer import Timer
from typing import Optional, Dict, Any


class StatusPanel(Static):
    """
    Panel showing current workflow status and statistics.

    Displays:
    - Phase and status
    - Session ID
    - Feature name (truncated)
    - Milestone progress (current/total)
    - Models being used (planner/executor)
    - Estimated API call count
    - Estimated token count
    - Estimated cost
    - Elapsed time

    Note: API calls, tokens, and cost are estimates based on heuristics,
    not actual values from the API.
    """

    # CSS is defined in theme.tcss to avoid duplication

    # Pricing per 1M tokens (in USD)
    # Using average of input/output pricing since we don't track separately
    PRICING = {
        "opus": 45.0,      # Average of $15 input + $75 output
        "sonnet": 9.0,     # Average of $3 input + $15 output
        "haiku": 0.75,     # Average of $0.25 input + $1.25 output
    }

    # Animation settings
    ANIMATION_DURATION = 0.4  # seconds
    ANIMATION_STEPS = 12  # number of steps in animation

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.phase = "—"
        self.status = "—"
        self.session_id = "—"
        self.feature = "—"
        self.planner_model = "—"
        self.executor_model = "—"
        self.api_calls = 0
        self.token_count = 0
        self.estimated_cost = 0.0
        self._use_actual_cost = False  # True when we have actual cost from API
        self._start_time: Optional[datetime] = None
        self.current_milestone = 0
        self.total_milestones = 0

        # Animation state
        self._token_animation: Optional[Timer] = None
        self._cost_animation: Optional[Timer] = None
        self._displayed_tokens = 0  # Currently displayed (animated) value
        self._displayed_cost = 0.0
        self._token_step = 0
        self._cost_step = 0
        self._token_start = 0
        self._cost_start = 0.0

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
                yield Label("Feature:", classes="stat-label")
                yield Label(self.feature, id="feature-value", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("Milestone:", classes="stat-label")
                yield Label(self._format_milestone_progress(), id="milestone-value", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("Models:", classes="stat-label")
                yield Label(f"{self.planner_model}/{self.executor_model}", id="models-value", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("Est. Calls:", classes="stat-label")
                yield Label(str(self.api_calls), id="api-calls-value", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("Est. Tokens:", classes="stat-label")
                yield Label(self._format_tokens(), id="tokens-value", classes="stat-value")
            with Horizontal(classes="stat-row"):
                yield Label("Est. Cost:", classes="stat-label")
                yield Label(self._format_cost(), id="cost-value", classes="stat-value")
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

    def update_feature(self, name: str) -> None:
        """
        Update the feature name display.

        Args:
            name: Feature name to display (will be truncated to ~25 chars)
        """
        if not name:
            self.feature = "—"
        else:
            # Truncate to 25 chars with ellipsis if needed
            self.feature = name[:25] + "..." if len(name) > 25 else name

        if self.is_mounted:
            self.query_one("#feature-value", Label).update(self.feature)

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
        """Add to the token counter with smooth animation."""
        old_tokens = self.token_count
        self.token_count += count
        # Only estimate cost if we don't have actual cost from API
        if not self._use_actual_cost:
            self._update_cost_estimate()
        if self.is_mounted:
            self._animate_tokens(old_tokens, self.token_count)
            # Also animate cost if we're estimating
            if not self._use_actual_cost:
                self._animate_cost(self._displayed_cost, self.estimated_cost)

    def add_cost(self, cost_usd: float) -> None:
        """Add to the actual cost (from API) with smooth animation."""
        self._use_actual_cost = True  # We have actual cost, stop estimating
        old_cost = self.estimated_cost
        self.estimated_cost += cost_usd
        if self.is_mounted:
            self._animate_cost(old_cost, self.estimated_cost)

    def _animate_tokens(self, from_val: int, to_val: int) -> None:
        """Animate token count from one value to another."""
        # Cancel existing animation
        if self._token_animation:
            self._token_animation.stop()
            self._token_animation = None

        self._token_start = from_val
        self._token_step = 0
        interval = self.ANIMATION_DURATION / self.ANIMATION_STEPS

        def step_tokens() -> None:
            self._token_step += 1
            # Ease-out: faster at start, slower at end
            progress = self._ease_out(self._token_step / self.ANIMATION_STEPS)
            self._displayed_tokens = int(self._token_start + (to_val - self._token_start) * progress)

            if self.is_mounted:
                self.query_one("#tokens-value", Label).update(self._format_tokens_value(self._displayed_tokens))

            if self._token_step >= self.ANIMATION_STEPS:
                self._displayed_tokens = to_val
                if self.is_mounted:
                    self.query_one("#tokens-value", Label).update(self._format_tokens())
                if self._token_animation:
                    self._token_animation.stop()
                    self._token_animation = None

        self._token_animation = self.set_interval(interval, step_tokens)

    def _animate_cost(self, from_val: float, to_val: float) -> None:
        """Animate cost from one value to another."""
        # Cancel existing animation
        if self._cost_animation:
            self._cost_animation.stop()
            self._cost_animation = None

        self._cost_start = from_val
        self._cost_step = 0
        interval = self.ANIMATION_DURATION / self.ANIMATION_STEPS

        def step_cost() -> None:
            self._cost_step += 1
            # Ease-out: faster at start, slower at end
            progress = self._ease_out(self._cost_step / self.ANIMATION_STEPS)
            self._displayed_cost = self._cost_start + (to_val - self._cost_start) * progress

            if self.is_mounted:
                self.query_one("#cost-value", Label).update(self._format_cost_value(self._displayed_cost))

            if self._cost_step >= self.ANIMATION_STEPS:
                self._displayed_cost = to_val
                if self.is_mounted:
                    self.query_one("#cost-value", Label).update(self._format_cost())
                if self._cost_animation:
                    self._cost_animation.stop()
                    self._cost_animation = None

        self._cost_animation = self.set_interval(interval, step_cost)

    def _ease_out(self, t: float) -> float:
        """Ease-out curve: fast start, slow end. t is 0-1, returns 0-1."""
        return 1 - (1 - t) ** 3  # Cubic ease-out

    def _format_tokens_value(self, value: int) -> str:
        """Format a specific token value with K/M suffixes."""
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        elif value >= 1_000:
            return f"{value / 1_000:.1f}K"
        return str(value)

    def _format_cost_value(self, value: float) -> str:
        """Format a specific cost value as '$X.XX'."""
        if value < 0.01:
            return "$0.00"
        return f"${value:.2f}"

    def start_timer(self) -> None:
        """Start the elapsed time timer."""
        self._start_time = datetime.now()

    def reset_stats(self) -> None:
        """Reset all statistics for a new session."""
        # Cancel any running animations
        if self._token_animation:
            self._token_animation.stop()
            self._token_animation = None
        if self._cost_animation:
            self._cost_animation.stop()
            self._cost_animation = None

        # Reset values
        self.token_count = 0
        self.estimated_cost = 0.0
        self._use_actual_cost = False
        self._displayed_tokens = 0
        self._displayed_cost = 0.0
        self._token_step = 0
        self._cost_step = 0

        # Update display
        if self.is_mounted:
            self.query_one("#tokens-value", Label).update(self._format_tokens())
            self.query_one("#cost-value", Label).update(self._format_cost())

    def update_elapsed(self) -> None:
        """Update the elapsed time display."""
        if self.is_mounted:
            self.query_one("#elapsed-value", Label).update(self._format_elapsed())

    def update_milestone_progress(self, current: int, total: int) -> None:
        """
        Update the milestone progress display.

        Args:
            current: Current milestone number (1-indexed)
            total: Total number of milestones
        """
        self.current_milestone = current
        self.total_milestones = total
        if self.is_mounted:
            self.query_one("#milestone-value", Label).update(self._format_milestone_progress())

    def _format_milestone_progress(self) -> str:
        """Format milestone progress as 'current/total' or '—' if no milestones."""
        if self.total_milestones == 0:
            return "—"
        return f"{self.current_milestone}/{self.total_milestones}"

    def _format_tokens(self) -> str:
        """Format token count with K/M suffixes."""
        if self.token_count >= 1_000_000:
            return f"{self.token_count / 1_000_000:.1f}M"
        elif self.token_count >= 1_000:
            return f"{self.token_count / 1_000:.1f}K"
        return str(self.token_count)

    def _update_cost_estimate(self) -> None:
        """Update the estimated cost based on current token count and models."""
        # Determine which model to use for pricing (use executor model as primary)
        model_key = self.executor_model.lower()

        # Find matching pricing tier
        price_per_million = 9.0  # Default to sonnet pricing
        for key in self.PRICING:
            if key in model_key:
                price_per_million = self.PRICING[key]
                break

        # Calculate cost: (tokens / 1M) * price_per_million
        self.estimated_cost = (self.token_count / 1_000_000) * price_per_million

    def _format_cost(self) -> str:
        """Format estimated cost as '$X.XX'."""
        if self.estimated_cost < 0.01:
            return "$0.00"
        elif self.estimated_cost < 1.0:
            return f"${self.estimated_cost:.2f}"
        elif self.estimated_cost < 10.0:
            return f"${self.estimated_cost:.2f}"
        else:
            return f"${self.estimated_cost:.2f}"

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

        model_lower = model.lower()

        # Handle common Claude model families
        if "opus" in model_lower:
            return "opus"
        elif "sonnet" in model_lower:
            return "sonnet"
        elif "haiku" in model_lower:
            return "haiku"

        # Try to extract version-like pattern (e.g., "claude-3-5" -> "3.5")
        # Use specific pattern to avoid matching dates like 2024-10-22
        version_match = re.search(r'(?:claude|gpt|llama)[-_](\d+)[-_](\d+)', model_lower)
        if version_match:
            return f"v{version_match.group(1)}.{version_match.group(2)}"

        # Fallback version match, but filter out year-like numbers (2020-2030)
        version_match = re.search(r'(\d+)[.-](\d+)', model)
        if version_match:
            first_num = int(version_match.group(1))
            # Skip if it looks like a year (2020-2030)
            if not (2020 <= first_num <= 2030):
                return f"v{version_match.group(1)}.{version_match.group(2)}"

        # Fallback: find the most descriptive segment
        # Skip common prefixes like "claude", "gpt", "anthropic"
        skip_prefixes = {"claude", "gpt", "anthropic", "openai", "meta", "llama"}
        parts = model.split("-")

        for part in parts:
            if part.lower() not in skip_prefixes and not part.isdigit():
                return part[:8]

        # Last resort: first 8 chars of the whole model
        return model[:8]
