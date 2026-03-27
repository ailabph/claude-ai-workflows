"""Session-scoped logging configuration for planner-auto."""

import logging
import os
import sys


DEFAULT_LOG_DIR = os.path.join(os.path.expanduser("~"), ".planner-auto", "logs")


def setup_session_logger(
    session_id: str,
    verbose: bool = False,
    debug: bool = False,
) -> logging.Logger:
    """Configure a session-scoped logger with file and optional stderr handlers.

    Creates a log file at ~/.planner-auto/logs/<session-id>.log.

    Args:
        session_id: Session ID used for the log filename.
        verbose: If True, add a stderr handler at INFO level.
        debug: If True, add a stderr handler at DEBUG level (overrides verbose).

    Returns:
        Configured logger instance.
    """
    os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)

    log_path = os.path.join(DEFAULT_LOG_DIR, f"{session_id}.log")

    logger = logging.getLogger(f"planner-auto.{session_id}")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler always at DEBUG
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Optional stderr handler
    if debug or verbose:
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(logging.DEBUG if debug else logging.INFO)
        sh.setFormatter(formatter)
        logger.addHandler(sh)

    return logger
