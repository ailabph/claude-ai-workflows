"""
Logging configuration for orchestrator-auto.

Provides per-session loggers with dedicated file handlers to support
queue/watch mode where multiple sessions run in one process.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# Default log directory
DEFAULT_LOG_DIR = Path.home() / ".claude_orchestrator" / "logs"


def get_log_dir(custom_dir: Optional[str] = None) -> Path:
    """
    Get the log directory, creating it if needed.

    Args:
        custom_dir: Optional custom log directory path

    Returns:
        Path to log directory
    """
    if custom_dir:
        log_dir = Path(custom_dir).expanduser()
    else:
        log_dir = DEFAULT_LOG_DIR

    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def create_session_logger(
    session_id: str,
    debug: bool = False,
    log_dir: Optional[str] = None,
) -> Tuple[logging.Logger, str]:
    """
    Create a logger for a specific session.

    Each session gets its own logger instance with a dedicated file handler.
    This avoids handler accumulation in queue/watch mode where multiple
    sessions run in one process.

    Args:
        session_id: The session ID (used in logger name and file name)
        debug: If True, also add a console handler for immediate output
        log_dir: Optional custom log directory

    Returns:
        Tuple of (logger instance, log file path)
    """
    # Create unique logger name per session
    logger_name = f"orchestrator.{session_id}"
    logger = logging.getLogger(logger_name)

    # Clear any existing handlers (safety for reused session IDs)
    logger.handlers.clear()

    # Set level based on debug flag
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Prevent propagation to root logger
    logger.propagate = False

    # Generate log file path
    directory = get_log_dir(log_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = directory / f"error_{session_id}_{timestamp}.log"
    log_path = str(log_file)

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Add file handler
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)  # Capture everything to file
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Add console handler if debug mode
    if debug:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger, log_path


def teardown_session_logger(logger: logging.Logger) -> None:
    """
    Remove and close all handlers from a session logger.

    Call this in a finally block after session completes to prevent
    handler accumulation in queue/watch mode.

    Args:
        logger: The logger instance to tear down
    """
    if logger is None:
        return

    for handler in logger.handlers[:]:  # Copy list to avoid mutation during iteration
        try:
            handler.close()
        except Exception:
            pass  # Ignore errors during cleanup
        logger.removeHandler(handler)


def get_null_logger() -> logging.Logger:
    """
    Get a null logger that discards all messages.

    Useful as a fallback when session logger creation fails.

    Returns:
        Logger with NullHandler
    """
    logger = logging.getLogger("orchestrator.null")
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger
