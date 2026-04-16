"""Planner-auto: Interactive planning session manager with SQLite persistence."""

__version__ = "0.6.1"


def load_env() -> bool:
    """Load .env file if python-dotenv is available.

    Call this explicitly before using planner-auto components that read
    env vars (sdk_wrapper, reviewer adapter). The CLI calls this at startup.
    Library consumers can call it manually or set env vars directly.

    Returns True if .env was loaded, False if dotenv not installed.
    """
    try:
        from dotenv import load_dotenv
        return load_dotenv()
    except ImportError:
        return False
