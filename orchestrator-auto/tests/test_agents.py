"""
Unit tests for agent management and SDK integration.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
import sys
import tempfile
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto.agents import (
    PlannerAgent,
    ExecutorAgent,
    create_planner_agent,
    create_executor_agent,
)
from orchestrator_auto.prompts import (
    PLANNER_SYSTEM_PROMPT,
    EXECUTOR_SYSTEM_PROMPT,
)
from orchestrator_auto.recovery import (
    generate_recovery_prompt,
    create_compact_hook,
    register_recovery_hook,
    get_recovery_state,
)
from orchestrator_auto import db


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)

    # Initialize the database
    db.init_db(path)

    yield path

    # Cleanup
    os.unlink(path)


class TestAgentInitialization:
    """Test agent initialization and configuration."""

    @patch("orchestrator_auto.agents.ClaudeSDKClient")
    def test_planner_agent_initialization(self, mock_sdk_client):
        """Test that PlannerAgent initializes with correct configuration."""
        agent = PlannerAgent()

        assert agent.system_prompt == PLANNER_SYSTEM_PROMPT
        assert agent.model == "claude-opus-4-5-20251101"  # Opus for planning
        assert agent._client is None  # Not initialized yet

    @patch("orchestrator_auto.agents.ClaudeSDKClient")
    def test_executor_agent_initialization(self, mock_sdk_client):
        """Test that ExecutorAgent initializes with correct configuration."""
        agent = ExecutorAgent()

        assert agent.system_prompt == EXECUTOR_SYSTEM_PROMPT
        assert agent.model == "claude-sonnet-4-5-20250929"  # Sonnet for execution
        assert agent._client is None  # Not initialized yet

    @patch("orchestrator_auto.agents.ClaudeSDKClient")
    def test_agent_initialize_creates_client(self, mock_sdk_client):
        """Test that initialize() creates the SDK client."""
        mock_client_instance = Mock()
        mock_sdk_client.return_value = mock_client_instance

        agent = PlannerAgent()
        agent.initialize()

        assert agent._client is not None
        mock_sdk_client.assert_called_once()
        mock_client_instance.connect.assert_called_once()

        # Check that SDK client was called with ClaudeAgentOptions
        call_kwargs = mock_sdk_client.call_args[1]
        assert "options" in call_kwargs
        options = call_kwargs["options"]
        assert options.system_prompt == PLANNER_SYSTEM_PROMPT
        assert options.model == "claude-opus-4-5-20251101"
        assert options.allowed_tools is not None

    @patch("orchestrator_auto.agents.ClaudeSDKClient")
    def test_agent_custom_model(self, mock_sdk_client):
        """Test that agents can use custom models."""
        agent = PlannerAgent(model="claude-opus-4-0")

        assert agent.model == "claude-opus-4-0"

    @patch("orchestrator_auto.agents.ClaudeSDKClient")
    def test_agent_custom_session_id(self, mock_sdk_client):
        """Test that agents can use custom session IDs."""
        mock_client_instance = Mock()
        mock_sdk_client.return_value = mock_client_instance

        agent = ExecutorAgent(session_id="custom-session")

        assert agent.session_id == "custom-session"


class TestAgentMessaging:
    """Test agent message sending and receiving."""

    @patch("orchestrator_auto.agents.ClaudeSDKClient")
    def test_send_message(self, mock_sdk_client):
        """Test sending a message to an agent."""
        # Setup mock
        mock_client_instance = Mock()
        mock_result = Mock()
        mock_result.content = "Agent response"
        mock_client_instance.query.return_value = None
        mock_client_instance.receive_response.return_value = mock_result
        mock_sdk_client.return_value = mock_client_instance

        agent = ExecutorAgent()
        agent.initialize()

        result = agent.send_message("Test message")

        assert mock_client_instance.query.called
        assert mock_client_instance.receive_response.called
        assert result == mock_result

    @patch("orchestrator_auto.agents.ClaudeSDKClient")
    def test_planner_validate_milestone_report(self, mock_sdk_client):
        """Test that PlannerAgent can validate milestone reports."""
        # Setup mock
        mock_client_instance = Mock()
        mock_result = Mock()
        mock_result.content = "[MILESTONE_APPROVED] Looks good!"
        mock_client_instance.query.return_value = None
        mock_client_instance.receive_response.return_value = mock_result
        mock_sdk_client.return_value = mock_client_instance

        agent = PlannerAgent()
        agent.initialize()

        report = "## Milestone 1 - COMPLETED\n\nAll tests pass."
        result = agent.validate_milestone_report(report)

        assert mock_client_instance.query.called
        assert mock_client_instance.receive_response.called
        assert result == mock_result

    @patch("orchestrator_auto.agents.ClaudeSDKClient")
    def test_executor_execute_milestone(self, mock_sdk_client):
        """Test that ExecutorAgent can execute milestone prompts."""
        # Setup mock
        mock_client_instance = Mock()
        mock_result = Mock()
        mock_result.content = "[PROGRESS_REPORT]..."
        mock_client_instance.query.return_value = None
        mock_client_instance.receive_response.return_value = mock_result
        mock_sdk_client.return_value = mock_client_instance

        agent = ExecutorAgent()
        agent.initialize()

        milestone_prompt = "Execute Milestone 1: Setup"
        result = agent.execute_milestone(milestone_prompt)

        assert mock_client_instance.query.called
        assert mock_client_instance.receive_response.called
        assert result == mock_result


class TestAgentFactories:
    """Test agent factory functions."""

    @patch("orchestrator_auto.agents.ClaudeSDKClient")
    def test_create_planner_agent(self, mock_sdk_client):
        """Test creating a planner agent with factory function."""
        mock_client_instance = Mock()
        mock_sdk_client.return_value = mock_client_instance

        agent = create_planner_agent()

        assert isinstance(agent, PlannerAgent)
        assert agent._client is not None  # Should be initialized
        mock_client_instance.connect.assert_called_once()

    @patch("orchestrator_auto.agents.ClaudeSDKClient")
    def test_create_executor_agent(self, mock_sdk_client):
        """Test creating an executor agent with factory function."""
        mock_client_instance = Mock()
        mock_sdk_client.return_value = mock_client_instance

        agent = create_executor_agent()

        assert isinstance(agent, ExecutorAgent)
        assert agent._client is not None  # Should be initialized
        mock_client_instance.connect.assert_called_once()

    @patch("orchestrator_auto.agents.ClaudeSDKClient")
    def test_factory_custom_model(self, mock_sdk_client):
        """Test factory functions with custom models."""
        mock_client_instance = Mock()
        mock_sdk_client.return_value = mock_client_instance

        agent = create_planner_agent(model="claude-opus-4-0")

        assert agent.model == "claude-opus-4-0"


class TestRecoveryPrompts:
    """Test recovery prompt generation."""

    def test_generate_recovery_prompt_no_session(self, temp_db):
        """Test recovery prompt generation when session doesn't exist."""
        # Use a non-existent session ID
        prompt = generate_recovery_prompt(
            session_id="nonexistent",
            agent_role="PLANNER",
            db_path=temp_db
        )

        assert "Error" in prompt or "not found" in prompt

    def test_create_compact_hook(self, temp_db):
        """Test creating a PreCompact hook callback."""
        hook = create_compact_hook(
            session_id="test-session",
            agent_role="PLANNER",
            db_path=temp_db
        )

        assert callable(hook)

        # Hook should return a string
        result = hook()
        assert isinstance(result, str)

    @patch("orchestrator_auto.agents.ClaudeSDKClient")
    def test_register_recovery_hook(self, mock_sdk_client):
        """Test registering a recovery hook with an agent."""
        mock_client_instance = Mock()
        mock_client_instance.register_precompact_hook = Mock()
        mock_sdk_client.return_value = mock_client_instance

        agent = PlannerAgent()
        agent.initialize()

        register_recovery_hook(
            agent=agent,
            session_id="test-session",
            agent_role="PLANNER",
        )

        # Should have attempted to register the hook
        # (exact method depends on SDK implementation)
        assert hasattr(agent, "_recovery_hook") or mock_client_instance.register_precompact_hook.called

    def test_get_recovery_state_no_session(self, temp_db):
        """Test getting recovery state for non-existent session."""
        state = get_recovery_state(
            session_id="nonexistent",
            db_path=temp_db
        )

        assert "error" in state


@pytest.fixture
def temp_db_with_session(temp_db):
    """Create a database with a test session."""
    # Create session
    session_id = db.create_session(
        feature_description="Test feature",
        db_path=temp_db
    )

    # Update session with progress
    db.update_session(
        session_id,
        {
            "phase": "execution",
            "plan_path": "docs/test/plan.md",
            "current_milestone": 2,
            "total_milestones": 5,
        },
        temp_db
    )

    # Create milestones
    db.create_milestone(session_id, 1, "Setup", temp_db)
    milestone1_id = 1
    db.update_milestone(
        milestone1_id,
        {"status": "completed"},
        temp_db
    )

    db.create_milestone(session_id, 2, "Implementation", temp_db)

    # Log some messages
    db.log_message(
        session_id, "discovery", "planner", "user",
        "Let's build this feature", db_path=temp_db
    )
    db.log_message(
        session_id, "planning", "planner", "assistant",
        "I've created the plan", db_path=temp_db
    )

    yield temp_db, session_id


class TestRecoveryWithDatabase:
    """Test recovery with actual database data."""

    def test_generate_recovery_prompt_with_data(self, temp_db_with_session):
        """Test recovery prompt generation with actual data."""
        temp_db, session_id = temp_db_with_session

        prompt = generate_recovery_prompt(
            session_id=session_id,
            agent_role="PLANNER",
            db_path=temp_db
        )

        # Check that key information is in the prompt
        assert session_id in prompt
        assert "Test feature" in prompt
        assert "execution" in prompt
        assert "Milestone 1" in prompt
        assert "PLANNER" in prompt

    def test_get_recovery_state_with_data(self, temp_db_with_session):
        """Test getting recovery state with actual data."""
        temp_db, session_id = temp_db_with_session

        state = get_recovery_state(session_id, temp_db)

        assert "session" in state
        assert state["session"]["id"] == session_id
        assert len(state["approved_milestones"]) == 1
        assert len(state["pending_milestones"]) >= 1
        assert state["message_count"] == 2
