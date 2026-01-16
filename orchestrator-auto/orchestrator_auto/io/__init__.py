"""
I/O abstraction layer for orchestrator.

This package provides abstractions for input/output handling,
allowing the orchestrator to work with different UI backends
(CLI, TUI, etc.) without modification.
"""

from .input_provider import InputProvider, CLIInputProvider
from .events import ChunkEvent, StateChangeEvent, OutputEvent, InputRequestedEvent

__all__ = [
    "InputProvider",
    "CLIInputProvider",
    "ChunkEvent",
    "StateChangeEvent",
    "OutputEvent",
    "InputRequestedEvent",
]
