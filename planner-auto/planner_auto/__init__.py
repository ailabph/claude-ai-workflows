"""Planner-auto: Interactive planning session manager with SQLite persistence."""

__version__ = "0.4.0"

# Load .env at package import time so all components (CLI, SDK wrapper,
# reviewer adapter) see API keys without manual shell exports.
# Works for both CLI usage and programmatic imports.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional — env vars must be set manually
