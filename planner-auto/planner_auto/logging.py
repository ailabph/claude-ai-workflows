"""Session-scoped logging configuration for planner-auto.

Provides a shared root logger (``planner_auto``) with session-id context
injection via :class:`SessionFilter`.  All child module loggers (e.g.
``planner_auto.db``, ``planner_auto.loop.engine``) inherit handlers
attached here.
"""

import logging
import os
import sys


DEFAULT_LOG_DIR = os.path.join(os.path.expanduser("~"), ".planner-auto", "logs")

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s (%(session_id)s): %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class SessionFilter(logging.Filter):
    """Injects ``session_id`` into every log record.

    Attach to any handler on the ``planner_auto`` root logger so that all
    child-module log records include the current session identifier.

    Args:
        session_id: The session identifier to inject.
    """

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.session_id = self.session_id
        return True


def setup_session_logging(
    session_id: str,
    verbose: bool = False,
    debug: bool = False,
) -> None:
    """Configure the shared ``planner_auto`` root logger for a session.

    Attaches a file handler (always at DEBUG level) to
    ``~/.planner-auto/logs/<session-id>.log``.  Optionally attaches a
    stderr handler at INFO (``verbose=True``) or DEBUG (``debug=True``).

    Clears existing handlers before attaching to prevent duplicates on
    re-attach.

    Args:
        session_id: Session ID used for the log filename and injected into
            every log record via :class:`SessionFilter`.
        verbose: If True, add a stderr handler at INFO level.
        debug: If True, add a stderr handler at DEBUG level (overrides
            *verbose*).
    """
    os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)

    log_path = os.path.join(DEFAULT_LOG_DIR, f"{session_id}.log")

    root = logging.getLogger("planner_auto")
    root.setLevel(logging.DEBUG)

    # Clear existing handlers to prevent duplicates on re-attach.
    root.handlers.clear()

    session_filter = SessionFilter(session_id)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # File handler — always at DEBUG.
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    fh.addFilter(session_filter)
    root.addHandler(fh)

    # Optional stderr handler.
    if debug or verbose:
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(logging.DEBUG if debug else logging.INFO)
        sh.setFormatter(formatter)
        sh.addFilter(session_filter)
        root.addHandler(sh)


# ---------------------------------------------------------------------------
# Backward-compat alias so existing call-sites don't break during the
# migration.  New code should call setup_session_logging() instead.
# ---------------------------------------------------------------------------

def setup_session_logger(
    session_id: str,
    verbose: bool = False,
    debug: bool = False,
) -> logging.Logger:
    """Backward-compatible wrapper around :func:`setup_session_logging`.

    Configures the shared root logger and returns it.

    .. deprecated::
        Use :func:`setup_session_logging` instead.
    """
    setup_session_logging(session_id, verbose=verbose, debug=debug)
    return logging.getLogger("planner_auto")
