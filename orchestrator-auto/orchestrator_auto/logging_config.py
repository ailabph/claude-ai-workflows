"""
Logging configuration for orchestrator-auto.

Provides per-session loggers with dedicated file handlers to support
queue/watch mode where multiple sessions run in one process.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# Default log directory
DEFAULT_LOG_DIR = Path.home() / ".claude_orchestrator" / "logs"


class LazyFileHandler(logging.FileHandler):
    """
    A FileHandler that delays file creation until the first log record.

    This prevents creating empty log files for successful sessions.
    The file is only created when emit() is called for the first time.
    """

    def __init__(self, filename: str, mode: str = "a", encoding: str = None, delay: bool = True):
        """
        Initialize the handler with delayed file creation.

        Args:
            filename: Path to the log file
            mode: File open mode
            encoding: File encoding
            delay: Always True for lazy creation (parameter kept for compatibility)
        """
        self._filename = filename
        self._mode = mode
        self._encoding = encoding
        self._file_created = False
        # Initialize without opening the file
        logging.Handler.__init__(self)
        self.stream = None

    def emit(self, record):
        """
        Emit a record, creating the file on first write.
        """
        if not self._file_created:
            # Create parent directory if needed
            Path(self._filename).parent.mkdir(parents=True, exist_ok=True)
            # Now open the file
            self.stream = open(self._filename, self._mode, encoding=self._encoding)
            self._file_created = True

        if self.stream:
            try:
                msg = self.format(record)
                self.stream.write(msg + self.terminator)
                self.stream.flush()
            except Exception:
                self.handleError(record)

    def close(self):
        """
        Close the handler and file stream.
        """
        self.acquire()
        try:
            if self.stream:
                try:
                    self.stream.flush()
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None
        finally:
            self.release()
        logging.Handler.close(self)

    @property
    def baseFilename(self):
        """Return the filename for compatibility with FileHandler interface."""
        return self._filename


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

    The file handler uses lazy creation - the log file is only created
    when the first error is logged, avoiding empty files for successful sessions.

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

    # Properly close and remove any existing handlers (prevents file descriptor leak)
    for handler in logger.handlers[:]:
        try:
            handler.close()
        except Exception:
            pass
        logger.removeHandler(handler)

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

    # Add lazy file handler (only creates file on first write)
    file_handler = LazyFileHandler(log_path, encoding="utf-8")
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
    logger.propagate = False  # Prevent bubbling to root logger
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger
