"""
TUI widgets for orchestrator-auto.

Provides reusable UI components for the TUI application.
"""

from .status_panel import StatusPanel
from .milestone_list import MilestoneList
from .agent_output import AgentOutput
from .log_panel import LogPanel
from .input_modal import InputModal
from .queue_panel import QueuePanel
from .watch_panel import WatchPanel
from .git_panel import GitStatusPanel
from .task_list import TaskListPanel
# Compact mode widgets
from .compact_sidebar import CompactSidebar
from .compact_milestone_row import CompactMilestoneRow
from .agent_toggle_panel import AgentTogglePanel
from .status_bar import StatusBar

__all__ = [
    "StatusPanel",
    "MilestoneList",
    "AgentOutput",
    "LogPanel",
    "InputModal",
    "QueuePanel",
    "WatchPanel",
    "GitStatusPanel",
    "TaskListPanel",
    # Compact mode widgets
    "CompactSidebar",
    "CompactMilestoneRow",
    "AgentTogglePanel",
    "StatusBar",
]
