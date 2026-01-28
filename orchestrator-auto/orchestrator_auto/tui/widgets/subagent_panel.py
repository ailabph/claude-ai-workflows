"""
Sub-agent panel widget for Layout B - shows exploration and validation status.
"""

from dataclasses import dataclass
from typing import List, Optional
from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.containers import Vertical


@dataclass
class ExplorationQuery:
    """Exploration query with status."""
    query: str
    status: str = "pending"  # "pending", "running", "completed", "failed"
    tokens_used: int = 0
    is_partial: bool = False


@dataclass
class ValidatorStatus:
    """Validator status with issue counts."""
    name: str
    status: str = "pending"  # "pending", "running", "passed", "issues", "failed"
    issue_count: int = 0
    high_count: int = 0
    medium_count: int = 0


class SubAgentPanel(Static, can_focus=True):
    """
    Panel showing exploration and validation sub-agent status.

    Displays two sections:
    - EXPLORE: List of exploration queries with status icons
    - VALIDATE: List of validators with status and issue counts
    """

    DEFAULT_CSS = """
    SubAgentPanel {
        height: 100%;
        width: 100%;
        padding: 0 1;
    }

    SubAgentPanel > Vertical {
        height: 100%;
    }

    SubAgentPanel .section-box {
        border: round $border;
        padding: 0 1;
        margin-bottom: 1;
        height: auto;
    }

    SubAgentPanel .section-title {
        height: 1;
        text-style: bold;
        color: $text;
        background: $primary 30%;
        text-align: center;
        margin-bottom: 1;
    }

    SubAgentPanel .section-content {
        height: auto;
        padding: 0;
    }

    SubAgentPanel .query-item {
        height: 1;
        color: $text;
    }

    SubAgentPanel .validator-item {
        height: 1;
        color: $text;
    }

    SubAgentPanel .status-pending { color: $text-muted; }
    SubAgentPanel .status-running { color: $warning; }
    SubAgentPanel .status-completed { color: $success; }
    SubAgentPanel .status-passed { color: $success; }
    SubAgentPanel .status-issues { color: $warning; }
    SubAgentPanel .status-failed { color: $error; }

    SubAgentPanel .empty-message {
        color: $text-muted;
        text-style: italic;
    }
    """

    # Status icons for exploration
    EXPLORE_ICONS = {
        "pending": "[dim]○[/dim]",
        "running": "[yellow]◐[/yellow]",
        "completed": "[green]✓[/green]",
        "failed": "[red]✗[/red]",
    }

    # Status icons for validation
    VALIDATE_ICONS = {
        "pending": "[dim]○[/dim]",
        "running": "[yellow]◐[/yellow]",
        "passed": "[green]✓[/green]",
        "issues": "[yellow]![/yellow]",
        "failed": "[red]✗[/red]",
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._explore_queries: List[ExplorationQuery] = []
        self._validators: List[ValidatorStatus] = []
        self._explore_status: str = "idle"  # "idle", "running", "completed"
        self._validate_status: str = "idle"
        self._explore_enabled: bool = True
        self._validate_enabled: bool = True

    def compose(self) -> ComposeResult:
        with Vertical():
            # Explore section
            with Vertical(classes="section-box", id="explore-box"):
                yield Label("EXPLORE", classes="section-title")
                yield Label(
                    self._format_explore_content(),
                    classes="section-content",
                    id="explore-content",
                )

            # Validate section
            with Vertical(classes="section-box", id="validate-box"):
                yield Label("VALIDATE", classes="section-title")
                yield Label(
                    self._format_validate_content(),
                    classes="section-content",
                    id="validate-content",
                )

    def set_enabled(self, explore: bool = True, validate: bool = True) -> None:
        """
        Set which sub-agents are enabled.

        Args:
            explore: Whether exploration is enabled
            validate: Whether validation is enabled
        """
        self._explore_enabled = explore
        self._validate_enabled = validate
        self._refresh_display()

    def set_explore_queries(self, queries: List[ExplorationQuery]) -> None:
        """
        Set exploration queries to display.

        Args:
            queries: List of ExplorationQuery objects
        """
        self._explore_queries = queries
        self._refresh_display()

    def update_explore_query(self, index: int, status: str, tokens: int = 0, partial: bool = False, query: str = "") -> None:
        """
        Update status of a specific exploration query (upsert semantics).

        If the index doesn't exist, placeholder queries are added up to that index.
        This handles out-of-order event delivery gracefully.

        Args:
            index: Query index (0-based)
            status: New status
            tokens: Tokens used (optional)
            partial: Whether result is partial (optional)
            query: Query text (used when upserting)
        """
        # Upsert: extend list with placeholders if index doesn't exist
        while index >= len(self._explore_queries):
            self._explore_queries.append(ExplorationQuery(query="(pending)"))

        self._explore_queries[index].status = status
        self._explore_queries[index].tokens_used = tokens
        self._explore_queries[index].is_partial = partial
        if query:
            self._explore_queries[index].query = query
        self._refresh_display()

    def add_explore_query(self, query: str, status: str = "pending") -> None:
        """
        Add a new exploration query.

        Args:
            query: Query text
            status: Initial status
        """
        self._explore_queries.append(ExplorationQuery(query=query, status=status))
        self._refresh_display()

    def clear_explore_queries(self) -> None:
        """Clear all exploration queries."""
        self._explore_queries = []
        self._refresh_display()

    def set_explore_status(self, status: str) -> None:
        """
        Set overall exploration phase status.

        Args:
            status: "idle", "running", or "completed"
        """
        self._explore_status = status
        self._refresh_display()

    def set_validators(self, validators: List[ValidatorStatus]) -> None:
        """
        Set validators to display.

        Args:
            validators: List of ValidatorStatus objects
        """
        self._validators = validators
        self._refresh_display()

    def update_validator(
        self,
        name: str,
        status: str,
        issue_count: int = 0,
        high_count: int = 0,
        medium_count: int = 0,
    ) -> None:
        """
        Update status of a specific validator.

        Args:
            name: Validator name
            status: New status
            issue_count: Total issues found
            high_count: High severity issues
            medium_count: Medium severity issues
        """
        for v in self._validators:
            if v.name == name:
                v.status = status
                v.issue_count = issue_count
                v.high_count = high_count
                v.medium_count = medium_count
                break
        else:
            # Validator not found, add it
            self._validators.append(ValidatorStatus(
                name=name,
                status=status,
                issue_count=issue_count,
                high_count=high_count,
                medium_count=medium_count,
            ))
        self._refresh_display()

    def set_validate_status(self, status: str) -> None:
        """
        Set overall validation phase status.

        Args:
            status: "idle", "running", or "completed"
        """
        self._validate_status = status
        self._refresh_display()

    def reset(self) -> None:
        """Reset all sub-agent status."""
        self._explore_queries = []
        self._validators = []
        self._explore_status = "idle"
        self._validate_status = "idle"
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh all display elements."""
        if not self.is_mounted:
            return

        try:
            self.query_one("#explore-content", Label).update(
                self._format_explore_content()
            )
            self.query_one("#validate-content", Label).update(
                self._format_validate_content()
            )
        except Exception:
            pass

    def _format_explore_content(self) -> str:
        """Format the exploration section content."""
        if not self._explore_enabled:
            return "[dim italic]Not enabled[/dim italic]"

        if not self._explore_queries:
            if self._explore_status == "idle":
                return "[dim italic]Waiting...[/dim italic]"
            elif self._explore_status == "running":
                return "[yellow]Starting...[/yellow]"
            else:
                return "[dim italic]No queries[/dim italic]"

        lines = []
        for q in self._explore_queries[:5]:  # Limit display to 5 queries
            icon = self.EXPLORE_ICONS.get(q.status, self.EXPLORE_ICONS["pending"])
            # Truncate long queries
            query_text = q.query[:25] + "..." if len(q.query) > 28 else q.query
            # Add partial indicator if result was truncated/timed out
            partial_indicator = " [dim](partial)[/dim]" if q.is_partial else ""
            lines.append(f"{icon} {query_text}{partial_indicator}")

        if len(self._explore_queries) > 5:
            lines.append(f"[dim]... +{len(self._explore_queries) - 5} more[/dim]")

        return "\n".join(lines)

    def _format_validate_content(self) -> str:
        """Format the validation section content."""
        if not self._validate_enabled:
            return "[dim italic]Not enabled[/dim italic]"

        if not self._validators:
            if self._validate_status == "idle":
                return "[dim italic]Pending[/dim italic]"
            elif self._validate_status == "running":
                return "[yellow]Running...[/yellow]"
            else:
                return "[dim italic]No validators[/dim italic]"

        lines = []
        for v in self._validators:
            icon = self.VALIDATE_ICONS.get(v.status, self.VALIDATE_ICONS["pending"])

            # Format issue count
            if v.status == "passed":
                count_str = ""
            elif v.issue_count > 0:
                if v.high_count > 0:
                    count_str = f" [red]{v.high_count}H[/red]"
                elif v.medium_count > 0:
                    count_str = f" [yellow]{v.medium_count}M[/yellow]"
                else:
                    count_str = f" {v.issue_count}"
            else:
                count_str = ""

            # Capitalize validator name for display
            name = v.name.capitalize()
            lines.append(f"{icon} {name}{count_str}")

        return "\n".join(lines)
