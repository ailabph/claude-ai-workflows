"""
Text User Interface (TUI) for orchestrator-auto.

This package provides a Textual-based TUI for running orchestrator
workflows with rich visual feedback.

Usage:
    pip install orchestrator-auto[tui]
    orchestrator start -f "Feature" --tui
"""

try:
    from textual import __version__ as textual_version
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    textual_version = None


def check_textual_available():
    """Check if Textual is available, raise helpful error if not."""
    if not TEXTUAL_AVAILABLE:
        raise ImportError(
            "Textual is not installed. Install with: pip install orchestrator-auto[tui]"
        )


# Lazy imports to avoid loading Textual if not needed
def get_app_class():
    """Get the OrchestratorTUI app class."""
    check_textual_available()
    from .app import OrchestratorTUI
    return OrchestratorTUI


def get_adapter_classes():
    """Get the TUI adapter classes."""
    check_textual_available()
    from .adapter import TUIInputProvider, TUIOutputAdapter
    return TUIInputProvider, TUIOutputAdapter


__all__ = [
    "TEXTUAL_AVAILABLE",
    "check_textual_available",
    "get_app_class",
    "get_adapter_classes",
]
