"""Tests for planner_auto/logging.py — shared root logger architecture."""

from __future__ import annotations

import logging
import os

import pytest

from planner_auto.logging import (
    LOG_FORMAT,
    SessionFilter,
    setup_session_logging,
)


# ---------------------------------------------------------------------------
# SessionFilter tests
# ---------------------------------------------------------------------------


class TestSessionFilter:
    def test_filter_injects_session_id(self):
        """SessionFilter sets session_id on the log record."""
        f = SessionFilter("sess-abc")
        record = logging.LogRecord(
            name="planner_auto.test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        result = f.filter(record)
        assert result is True
        assert record.session_id == "sess-abc"

    def test_filter_returns_true(self):
        """SessionFilter always returns True (never suppresses records)."""
        f = SessionFilter("any-id")
        record = logging.LogRecord(
            name="planner_auto.db",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="debug msg",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True

    def test_filter_different_session_ids(self):
        """Different SessionFilter instances inject their own session_id."""
        f1 = SessionFilter("session-1")
        f2 = SessionFilter("session-2")

        record = logging.LogRecord(
            name="planner_auto.x", level=logging.WARNING,
            pathname="", lineno=0, msg="x", args=(), exc_info=None,
        )
        f1.filter(record)
        assert record.session_id == "session-1"

        f2.filter(record)
        assert record.session_id == "session-2"


# ---------------------------------------------------------------------------
# setup_session_logging tests
# ---------------------------------------------------------------------------


class TestSetupSessionLogging:
    def _clear_root(self):
        """Remove all handlers from the planner_auto root logger."""
        root = logging.getLogger("planner_auto")
        root.handlers.clear()

    def test_creates_file_handler(self, tmp_path, monkeypatch):
        """setup_session_logging creates a file handler at DEBUG level."""
        monkeypatch.setattr(
            "planner_auto.logging.DEFAULT_LOG_DIR", str(tmp_path)
        )
        self._clear_root()

        setup_session_logging("test-sess-1")

        root = logging.getLogger("planner_auto")
        file_handlers = [
            h for h in root.handlers if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) == 1
        assert file_handlers[0].level == logging.DEBUG

    def test_log_file_path(self, tmp_path, monkeypatch):
        """Log file is created at <log_dir>/<session_id>.log."""
        monkeypatch.setattr(
            "planner_auto.logging.DEFAULT_LOG_DIR", str(tmp_path)
        )
        self._clear_root()

        setup_session_logging("my-session-id")

        expected = tmp_path / "my-session-id.log"
        assert expected.exists()

    def test_no_stderr_handler_by_default(self, tmp_path, monkeypatch):
        """Without verbose/debug, no StreamHandler is attached."""
        monkeypatch.setattr(
            "planner_auto.logging.DEFAULT_LOG_DIR", str(tmp_path)
        )
        self._clear_root()

        setup_session_logging("quiet-sess")

        root = logging.getLogger("planner_auto")
        stream_handlers = [
            h for h in root.handlers if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        assert stream_handlers == []

    def test_verbose_adds_stderr_handler_at_info(self, tmp_path, monkeypatch):
        """verbose=True adds a StreamHandler at INFO level."""
        monkeypatch.setattr(
            "planner_auto.logging.DEFAULT_LOG_DIR", str(tmp_path)
        )
        self._clear_root()

        setup_session_logging("verbose-sess", verbose=True)

        root = logging.getLogger("planner_auto")
        stream_handlers = [
            h for h in root.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 1
        assert stream_handlers[0].level == logging.INFO

    def test_debug_adds_stderr_handler_at_debug(self, tmp_path, monkeypatch):
        """debug=True adds a StreamHandler at DEBUG level."""
        monkeypatch.setattr(
            "planner_auto.logging.DEFAULT_LOG_DIR", str(tmp_path)
        )
        self._clear_root()

        setup_session_logging("debug-sess", debug=True)

        root = logging.getLogger("planner_auto")
        stream_handlers = [
            h for h in root.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 1
        assert stream_handlers[0].level == logging.DEBUG

    def test_re_attach_clears_old_handlers(self, tmp_path, monkeypatch):
        """Calling setup_session_logging twice does not duplicate handlers."""
        monkeypatch.setattr(
            "planner_auto.logging.DEFAULT_LOG_DIR", str(tmp_path)
        )
        self._clear_root()

        setup_session_logging("dup-sess")
        setup_session_logging("dup-sess")

        root = logging.getLogger("planner_auto")
        # Should still be exactly one file handler, not two.
        file_handlers = [
            h for h in root.handlers if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) == 1

    def test_module_loggers_flow_to_root(self, tmp_path, monkeypatch, caplog):
        """Child module loggers propagate records to the planner_auto root."""
        monkeypatch.setattr(
            "planner_auto.logging.DEFAULT_LOG_DIR", str(tmp_path)
        )
        self._clear_root()
        setup_session_logging("flow-sess")

        child_logger = logging.getLogger("planner_auto.db")
        with caplog.at_level(logging.DEBUG, logger="planner_auto"):
            child_logger.info("test message from db module")

        assert any("test message from db module" in r.message for r in caplog.records)

    def test_session_id_injected_in_file_log(self, tmp_path, monkeypatch):
        """Session ID appears in every log line written to the file."""
        monkeypatch.setattr(
            "planner_auto.logging.DEFAULT_LOG_DIR", str(tmp_path)
        )
        self._clear_root()

        session_id = "file-check-session"
        setup_session_logging(session_id)

        logger = logging.getLogger("planner_auto.test_module")
        logger.info("checking session id injection")

        # Flush handlers
        root = logging.getLogger("planner_auto")
        for h in root.handlers:
            h.flush()

        log_file = tmp_path / f"{session_id}.log"
        content = log_file.read_text(encoding="utf-8")
        assert session_id in content
        assert "checking session id injection" in content
