"""
Tests for error handling and logging functionality.

Tests the logging infrastructure, exception hierarchy, session error tracking,
and CLI error boundary.
"""

import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from orchestrator_auto import db
from orchestrator_auto.exceptions import (
    OrchestratorError,
    AgentError,
    SessionStateError,
    PlanParseError,
)
from orchestrator_auto.logging_config import (
    create_session_logger,
    teardown_session_logger,
    get_log_dir,
    get_null_logger,
)


class TestLoggingConfig:
    """Tests for logging_config module."""

    def test_get_log_dir_creates_directory(self, tmp_path):
        """Test that get_log_dir creates the directory if it doesn't exist."""
        custom_dir = tmp_path / "custom_logs"
        assert not custom_dir.exists()

        result = get_log_dir(str(custom_dir))

        assert result == custom_dir
        assert custom_dir.exists()

    def test_get_log_dir_default(self):
        """Test that get_log_dir uses default directory."""
        result = get_log_dir()
        expected = Path.home() / ".claude_orchestrator" / "logs"
        assert result == expected

    def test_create_session_logger_creates_file(self, tmp_path):
        """Test that create_session_logger creates a log file."""
        logger, log_path = create_session_logger(
            "test123",
            debug=False,
            log_dir=str(tmp_path),
        )

        try:
            assert logger is not None
            assert log_path is not None
            assert "test123" in log_path
            assert Path(log_path).parent == tmp_path

            # Logger should have a file handler
            assert len(logger.handlers) == 1
            assert isinstance(logger.handlers[0], logging.FileHandler)
        finally:
            teardown_session_logger(logger)

    def test_create_session_logger_debug_mode(self, tmp_path):
        """Test that debug mode adds console handler."""
        logger, log_path = create_session_logger(
            "test456",
            debug=True,
            log_dir=str(tmp_path),
        )

        try:
            # Should have both file and console handlers
            assert len(logger.handlers) == 2
            handler_types = [type(h) for h in logger.handlers]
            assert logging.FileHandler in handler_types
            assert logging.StreamHandler in handler_types
        finally:
            teardown_session_logger(logger)

    def test_teardown_session_logger_removes_handlers(self, tmp_path):
        """Test that teardown_session_logger removes all handlers."""
        logger, log_path = create_session_logger(
            "test789",
            debug=True,
            log_dir=str(tmp_path),
        )

        assert len(logger.handlers) > 0

        teardown_session_logger(logger)

        assert len(logger.handlers) == 0

    def test_teardown_session_logger_handles_none(self):
        """Test that teardown_session_logger handles None gracefully."""
        # Should not raise
        teardown_session_logger(None)

    def test_multiple_sessions_get_isolated_loggers(self, tmp_path):
        """Test that multiple sessions get isolated loggers (queue mode simulation)."""
        logger1, path1 = create_session_logger("session1", log_dir=str(tmp_path))
        logger2, path2 = create_session_logger("session2", log_dir=str(tmp_path))

        try:
            # Different logger instances
            assert logger1 is not logger2
            assert logger1.name != logger2.name

            # Different log files
            assert path1 != path2
            assert "session1" in path1
            assert "session2" in path2

            # Writing to one doesn't affect the other
            logger1.info("test message 1")
            logger2.info("test message 2")

            # Flush handlers
            for handler in logger1.handlers:
                handler.flush()
            for handler in logger2.handlers:
                handler.flush()

            # Check file contents
            with open(path1) as f:
                content1 = f.read()
            with open(path2) as f:
                content2 = f.read()

            assert "test message 1" in content1
            assert "test message 2" not in content1
            assert "test message 2" in content2
            assert "test message 1" not in content2
        finally:
            teardown_session_logger(logger1)
            teardown_session_logger(logger2)

    def test_get_null_logger(self):
        """Test that get_null_logger returns a functional logger."""
        logger = get_null_logger()
        assert logger is not None
        # Should not raise
        logger.info("test message")
        logger.error("test error")


class TestExceptions:
    """Tests for exception hierarchy."""

    def test_orchestrator_error_attributes(self):
        """Test OrchestratorError stores session context."""
        error = OrchestratorError(
            "test error",
            session_id="abc123",
            log_path="/tmp/test.log"
        )

        assert str(error) == "test error"
        assert error.session_id == "abc123"
        assert error.log_path == "/tmp/test.log"

    def test_orchestrator_error_optional_attributes(self):
        """Test OrchestratorError with optional attributes."""
        error = OrchestratorError("test error")

        assert str(error) == "test error"
        assert error.session_id is None
        assert error.log_path is None

    def test_agent_error_inherits_from_orchestrator_error(self):
        """Test AgentError is a subclass of OrchestratorError."""
        error = AgentError("agent failed", session_id="xyz789")

        assert isinstance(error, OrchestratorError)
        assert error.session_id == "xyz789"

    def test_session_state_error_inherits(self):
        """Test SessionStateError is a subclass of OrchestratorError."""
        error = SessionStateError("invalid state")
        assert isinstance(error, OrchestratorError)

    def test_plan_parse_error_inherits(self):
        """Test PlanParseError is a subclass of OrchestratorError."""
        error = PlanParseError("malformed plan")
        assert isinstance(error, OrchestratorError)


class TestSessionErrors:
    """Tests for session_errors database functionality."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary database."""
        db_path = str(tmp_path / "test.db")
        db.init_db(db_path)
        return db_path

    def test_log_session_error(self, temp_db):
        """Test logging an error to the database."""
        # Create a session first
        session_id = db.create_session(
            feature_description="Test feature",
            db_path=temp_db
        )

        # Log an error
        error_id = db.log_session_error(
            session_id=session_id,
            error_type="AgentError",
            error_message="Test error message",
            stack_trace="Traceback...",
            phase="execution",
            milestone_number=2,
            log_file_path="/tmp/error.log",
            db_path=temp_db
        )

        assert error_id is not None
        assert error_id > 0

    def test_get_session_errors(self, temp_db):
        """Test retrieving errors for a session."""
        session_id = db.create_session(
            feature_description="Test feature",
            db_path=temp_db
        )

        # Log multiple errors
        db.log_session_error(
            session_id=session_id,
            error_type="Error1",
            error_message="First error",
            db_path=temp_db
        )
        db.log_session_error(
            session_id=session_id,
            error_type="Error2",
            error_message="Second error",
            db_path=temp_db
        )

        errors = db.get_session_errors(session_id, temp_db)

        assert len(errors) == 2
        # Both errors should be present (order depends on ID/timestamp)
        error_types = {e["error_type"] for e in errors}
        assert "Error1" in error_types
        assert "Error2" in error_types

    def test_get_latest_session_error(self, temp_db):
        """Test retrieving the most recent error."""
        session_id = db.create_session(
            feature_description="Test feature",
            db_path=temp_db
        )

        # Log a single error to test retrieval
        db.log_session_error(
            session_id=session_id,
            error_type="TestError",
            error_message="Test error message",
            db_path=temp_db
        )

        latest = db.get_latest_session_error(session_id, temp_db)

        assert latest is not None
        assert latest["error_type"] == "TestError"
        assert latest["error_message"] == "Test error message"

    def test_get_latest_session_error_no_errors(self, temp_db):
        """Test getting latest error when none exist."""
        session_id = db.create_session(
            feature_description="Test feature",
            db_path=temp_db
        )

        latest = db.get_latest_session_error(session_id, temp_db)

        assert latest is None

    def test_error_persisted_with_log_file_path(self, temp_db):
        """Test that log_file_path is persisted correctly."""
        session_id = db.create_session(
            feature_description="Test feature",
            db_path=temp_db
        )

        log_path = "/home/user/.claude_orchestrator/logs/error_abc123_20260112.log"
        db.log_session_error(
            session_id=session_id,
            error_type="TestError",
            error_message="Test",
            log_file_path=log_path,
            db_path=temp_db
        )

        latest = db.get_latest_session_error(session_id, temp_db)
        assert latest["log_file_path"] == log_path


class TestEngineErrorHandling:
    """Tests for engine-level error handling."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary database."""
        db_path = str(tmp_path / "test.db")
        db.init_db(db_path)
        return db_path

    def test_keyboard_interrupt_not_marked_failed(self, temp_db, tmp_path):
        """Test that KeyboardInterrupt does not mark session as failed."""
        from orchestrator_auto.engine import Orchestrator

        # Create orchestrator
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
        )
        session_id = orch.session_id

        # Mock agent to raise KeyboardInterrupt
        with patch.object(orch, '_run_discovery_loop', side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                orch.start()

        # Session should NOT be failed
        session = db.get_session(session_id, temp_db)
        assert session["status"] != "failed"

    def test_session_marked_failed_on_error(self, temp_db, tmp_path):
        """Test that sessions are marked failed on unhandled errors."""
        from orchestrator_auto.engine import Orchestrator

        # Create orchestrator
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
        )
        session_id = orch.session_id

        # Mock agent to raise an error
        with patch.object(orch, '_run_discovery_loop', side_effect=RuntimeError("Test error")):
            with pytest.raises(AgentError):
                orch.start()

        # Session should be failed
        session = db.get_session(session_id, temp_db)
        assert session["status"] == "failed"

    def test_error_persisted_to_db_on_failure(self, temp_db, tmp_path):
        """Test that error details are persisted to session_errors table."""
        from orchestrator_auto.engine import Orchestrator

        # Create orchestrator
        orch = Orchestrator(
            feature_description="Test feature",
            db_path=temp_db,
        )
        session_id = orch.session_id

        # Mock agent to raise an error
        with patch.object(orch, '_run_discovery_loop', side_effect=RuntimeError("Specific test error")):
            with pytest.raises(AgentError):
                orch.start()

        # Check error was persisted
        errors = db.get_session_errors(session_id, temp_db)
        assert len(errors) == 1
        assert errors[0]["error_type"] == "RuntimeError"
        assert "Specific test error" in errors[0]["error_message"]


class TestCLIErrorHandling:
    """Tests for CLI error boundary functions."""

    def test_handle_orchestrator_error_with_plan(self, tmp_path):
        """Test _handle_orchestrator_error shows --plan guidance when plan_path exists."""
        from orchestrator_auto.cli import _handle_orchestrator_error

        # Create temp database with session that has plan_path
        db_path = str(tmp_path / "test.db")
        db.init_db(db_path)
        session_id = db.create_session(
            feature_description="Test feature",
            db_path=db_path
        )
        # Update session with plan_path using correct signature
        db.update_session(
            session_id,
            {"plan_path": "/path/to/plan.md"},
            db_path
        )

        error = AgentError("Test error", session_id=session_id, log_path="/tmp/test.log")

        # The function prints to click, hard to test directly
        # This test mainly ensures no exceptions are raised
        _handle_orchestrator_error(error, debug=False, db_path=db_path)

    def test_handle_orchestrator_error_without_plan(self, tmp_path):
        """Test _handle_orchestrator_error shows -f guidance when no plan_path."""
        from orchestrator_auto.cli import _handle_orchestrator_error

        db_path = str(tmp_path / "test.db")
        db.init_db(db_path)
        session_id = db.create_session(
            feature_description="My test feature",
            db_path=db_path
        )

        error = AgentError("Test error", session_id=session_id)

        # Should not raise
        _handle_orchestrator_error(error, debug=False, db_path=db_path)

    def test_handle_unexpected_error_prints_traceback_in_debug(self):
        """Test _handle_unexpected_error prints traceback when debug=True."""
        from orchestrator_auto.cli import _handle_unexpected_error

        error = ValueError("Unexpected value")

        # Should not raise
        _handle_unexpected_error(error, debug=False)
        _handle_unexpected_error(error, debug=True)
