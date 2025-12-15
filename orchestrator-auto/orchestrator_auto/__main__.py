"""
Entry point for running orchestrator-auto as a module.

Usage:
    python -m orchestrator_auto --help
"""

from .cli import cli

if __name__ == '__main__':
    cli()
