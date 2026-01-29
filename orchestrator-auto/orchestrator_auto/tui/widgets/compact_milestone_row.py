"""
Compact milestone row widget for displaying milestone progress in a single row.
"""

from textual.widgets import Static
from typing import List, Optional


class CompactMilestoneRow(Static):
    """
    Single-row milestone display: ✓1 ✓2 ✓3 ▶4 ○5 ○6

    Compact representation of milestone progress using icons.
    Wraps to multiple rows if more than 6 milestones.
    """

    DEFAULT_CSS = """
    CompactMilestoneRow {
        height: auto;
        min-height: 1;
        max-height: 10;
        padding: 0;
    }
    """

    ICONS = {
        "completed": "✓",
        "active": "▶",
        "pending": "○",
        "failed": "✗",
    }

    STYLES = {
        "completed": "cyan",
        "active": "green bold",
        "pending": "dim",
        "failed": "red",
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._milestones: List[dict] = []
        self._current: int = 0

    def set_milestones(self, milestones: List[dict], current: int = 0) -> None:
        """
        Update milestone display.

        Args:
            milestones: List of milestone dicts with 'id', 'title', 'status'
            current: Current milestone number (1-indexed)
        """
        self._milestones = milestones
        self._current = current
        self._refresh_display()

    def set_current(self, current: int) -> None:
        """
        Set the current milestone number.

        Args:
            current: Current milestone number (1-indexed)
        """
        self._current = current
        # Update statuses based on current
        for m in self._milestones:
            m_id = m.get("id", 0)
            if m_id < current:
                if m.get("status") != "failed":
                    m["status"] = "completed"
            elif m_id == current:
                m["status"] = "active"
            else:
                if m.get("status") not in ("completed", "failed"):
                    m["status"] = "pending"
        self._refresh_display()

    def _format_row(self) -> str:
        """Format milestones as list with titles."""
        if not self._milestones:
            return "[dim]No milestones[/dim]"

        lines = []
        for m in self._milestones:
            m_id = m.get("id", 0)
            title = m.get("title", f"Milestone {m_id}")
            status = m.get("status", "pending")
            icon = self.ICONS.get(status, "○")
            style = self.STYLES.get(status, "")

            # Truncate title to fit (leave room for icon and number)
            max_title_len = 35
            if len(title) > max_title_len:
                title = title[:max_title_len] + ".."

            if style:
                lines.append(f"[{style}]{icon} {m_id}. {title}[/{style}]")
            else:
                lines.append(f"{icon} {m_id}. {title}")

        return "\n".join(lines)

    def _refresh_display(self) -> None:
        """Refresh the display with current milestone state."""
        self.update(self._format_row())

    @property
    def milestones(self) -> List[dict]:
        """Get the current list of milestones."""
        return self._milestones.copy()

    @property
    def current(self) -> int:
        """Get the current milestone number."""
        return self._current
