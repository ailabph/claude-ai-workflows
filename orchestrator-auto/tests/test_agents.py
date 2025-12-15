"""
Unit tests for agent management and SDK integration.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from pathlib import Path
import sys
import tempfile
import os
import asyncio

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_auto.agents import (
    BaseAgent,
    PlannerAgent,
    ExecutorAgent,
    create_planner_agent,
    create_executor_agent,
    DEFAULT_TOOLS,
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

    def test_planner_agent_initialization(self):
        """Test that PlannerAgent initializes with correct configuration."""
        agent = PlannerAgent()

        assert agent.system_prompt == PLANNER_SYSTEM_PROMPT
        assert agent.model == "claude-opus-4-5-20251101"  # Opus for planning
        assert agent.session_id == "planner"
        assert agent.allowed_tools == DEFAULT_TOOLS

    def test_executor_agent_initialization(self):
        """Test that ExecutorAgent initializes with correct configuration."""
        agent = ExecutorAgent()

        assert agent.system_prompt == EXECUTOR_SYSTEM_PROMPT
        assert agent.model == "claude-sonnet-4-5-20250929"  # Sonnet for execution
        assert agent.session_id == "executor"
        assert agent.allowed_tools == DEFAULT_TOOLS

    def test_agent_options_created_on_demand(self):
        """Test that agent options are created on demand."""
        agent = PlannerAgent()

        assert agent._options is None

        options = agent._get_options()

        assert options is not None
        assert options.system_prompt == PLANNER_SYSTEM_PROMPT
        assert options.model == "claude-opus-4-5-20251101"
        assert agent._options is not None  # Cached

    def test_agent_custom_model(self):
        """Test that agents can use custom models."""
        agent = PlannerAgent(model="claude-opus-4-0")

        assert agent.model == "claude-opus-4-0"

    def test_agent_custom_session_id(self):
        """Test that agents can use custom session IDs."""
        agent = ExecutorAgent(session_id="custom-session")

        assert agent.session_id == "custom-session"


class TestAgentMessaging:
    """Test agent message sending and receiving."""

    @patch("orchestrator_auto.agents.query")
    def test_send_message(self, mock_query):
        """Test sending a message to an agent."""
        # Mock the async iterator by mocking send_message_async directly
        agent = ExecutorAgent()

        # Patch the async method to return a string
        with patch.object(agent, 'send_message_async', return_value="Agent response") as mock_async:
            # Make the sync method use the patched async
            with patch('asyncio.run', return_value="Agent response"):
                result = agent.send_message("Test message")

        assert result == "Agent response"

    @patch("orchestrator_auto.agents.query")
    def test_planner_validate_milestone_report(self, mock_query):
        """Test that PlannerAgent can validate milestone reports."""
        agent = PlannerAgent()

        # Patch the async method to return a string
        with patch.object(agent, 'send_message_async', return_value="[MILESTONE_APPROVED] Looks good!"):
            with patch('asyncio.run', return_value="[MILESTONE_APPROVED] Looks good!"):
                report = "## Milestone 1 - COMPLETED\n\nAll tests pass."
                result = agent.validate_milestone_report(report)

        assert "[MILESTONE_APPROVED]" in result

    @patch("orchestrator_auto.agents.query")
    def test_executor_execute_milestone(self, mock_query):
        """Test that ExecutorAgent can execute milestone prompts."""
        agent = ExecutorAgent()

        # Patch the async method to return a string
        with patch.object(agent, 'send_message_async', return_value="[PROGRESS_REPORT]..."):
            with patch('asyncio.run', return_value="[PROGRESS_REPORT]..."):
                milestone_prompt = "Execute Milestone 1: Setup"
                result = agent.execute_milestone(milestone_prompt)

        assert "[PROGRESS_REPORT]" in result


class TestAgentFactories:
    """Test agent factory functions."""

    def test_create_planner_agent(self):
        """Test creating a planner agent with factory function."""
        agent = create_planner_agent()

        assert isinstance(agent, PlannerAgent)
        assert agent.session_id == "planner"
        assert agent.model == "claude-opus-4-5-20251101"

    def test_create_executor_agent(self):
        """Test creating an executor agent with factory function."""
        agent = create_executor_agent()

        assert isinstance(agent, ExecutorAgent)
        assert agent.session_id == "executor"
        assert agent.model == "claude-sonnet-4-5-20250929"

    def test_factory_custom_model(self):
        """Test factory functions with custom models."""
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

    def test_register_recovery_hook(self):
        """Test registering a recovery hook with an agent."""
        agent = PlannerAgent()

        register_recovery_hook(
            agent=agent,
            session_id="test-session",
            agent_role="PLANNER",
        )

        # Hook should be stored on the agent
        assert hasattr(agent, "_recovery_hook")
        assert hasattr(agent, "_session_id")
        assert agent._session_id == "test-session"
        assert agent._agent_role == "PLANNER"

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
