"""Review-fix loop sub-package for planner-auto Plan 2.

Provides the ``ReviewLoopEngine``, feedback validation, history context
building, severity filtering, and complexity detection.
"""

from planner_auto.loop.convergence import detect_complexity, get_max_rounds
from planner_auto.loop.engine import LoopResult, ReviewLoopEngine
from planner_auto.loop.history import build_review_context, filter_issues

__all__ = [
    "ReviewLoopEngine",
    "LoopResult",
    "build_review_context",
    "filter_issues",
    "detect_complexity",
    "get_max_rounds",
]
