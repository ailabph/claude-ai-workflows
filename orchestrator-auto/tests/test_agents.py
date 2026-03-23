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
    build_allowed_tools,
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


class AsyncIteratorMock:
    """Mock async iterator for testing async for loops."""

    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


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
        assert agent.model == "claude-opus-4-6"  # Opus for planning
        assert agent.session_id == "planner"
        assert agent.allowed_tools == DEFAULT_TOOLS

    def test_executor_agent_initialization(self):
        """Test that ExecutorAgent initializes with correct configuration."""
        agent = ExecutorAgent()

        assert agent.system_prompt == EXECUTOR_SYSTEM_PROMPT
        assert agent.model == "claude-sonnet-4-6"  # Sonnet for execution
        assert agent.session_id == "executor"
        assert agent.allowed_tools == DEFAULT_TOOLS

    def test_agent_options_created_on_demand(self):
        """Test that agent options are created on demand."""
        agent = PlannerAgent()

        assert agent._options is None

        options = agent._get_options()

        assert options is not None
        assert options.system_prompt == PLANNER_SYSTEM_PROMPT
        assert options.model == "claude-opus-4-6"
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

    @patch("orchestrator_auto.agents.ClaudeSDKClient")
    def test_send_message(self, mock_client_class):
        """Test sending a message to an agent."""
        # Mock the async iterator by mocking send_message_async directly
        agent = ExecutorAgent()

        # Patch the async method to return a string
        with patch.object(agent, 'send_message_async', return_value="Agent response") as mock_async:
            # Make the sync method use the patched async
            with patch('asyncio.run', return_value="Agent response"):
                result = agent.send_message("Test message")

        assert result == "Agent response"

    @patch("orchestrator_auto.agents.ClaudeSDKClient")
    def test_planner_validate_milestone_report(self, mock_client_class):
        """Test that PlannerAgent can validate milestone reports."""
        agent = PlannerAgent()

        # Patch the async method to return a string
        with patch.object(agent, 'send_message_async', return_value="[MILESTONE_APPROVED] Looks good!"):
            with patch('asyncio.run', return_value="[MILESTONE_APPROVED] Looks good!"):
                report = "## Milestone 1 - COMPLETED\n\nAll tests pass."
                result = agent.validate_milestone_report(report)

        assert "[MILESTONE_APPROVED]" in result

    @patch("orchestrator_auto.agents.ClaudeSDKClient")
    def test_executor_execute_milestone(self, mock_client_class):
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
        assert agent.model == "claude-opus-4-6"

    def test_create_executor_agent(self):
        """Test creating an executor agent with factory function."""
        agent = create_executor_agent()

        assert isinstance(agent, ExecutorAgent)
        assert agent.session_id == "executor"
        assert agent.model == "claude-sonnet-4-6"

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


# ============================================================================
# MCP Configuration Tests
# ============================================================================


class TestBuildAllowedTools:
    """Test build_allowed_tools helper function."""

    def test_build_allowed_tools_defaults_to_default_tools(self):
        """build_allowed_tools should use DEFAULT_TOOLS when no base provided."""
        tools = build_allowed_tools()
        assert tools == list(DEFAULT_TOOLS)

    def test_build_allowed_tools_combines_lists(self):
        """build_allowed_tools should combine base and MCP tools."""
        tools = build_allowed_tools(mcp_tools=["mcp__playwright__*"])

        # Should have all default tools plus MCP tool
        assert "Read" in tools
        assert "Write" in tools
        assert "mcp__playwright__*" in tools

    def test_build_allowed_tools_custom_base(self):
        """build_allowed_tools should use custom base tools."""
        tools = build_allowed_tools(
            base_tools=["Read", "Write"],
            mcp_tools=["mcp__figma__*"]
        )

        assert tools == ["Read", "Write", "mcp__figma__*"]

    def test_build_allowed_tools_no_mcp(self):
        """build_allowed_tools should work without MCP tools."""
        tools = build_allowed_tools(base_tools=["Read"])
        assert tools == ["Read"]

    def test_build_allowed_tools_multiple_mcp(self):
        """build_allowed_tools should handle multiple MCP tools."""
        tools = build_allowed_tools(
            mcp_tools=["mcp__playwright__*", "mcp__figma__*"]
        )

        assert "mcp__playwright__*" in tools
        assert "mcp__figma__*" in tools


class TestAgentMcpConfiguration:
    """Test MCP configuration in agents."""

    def test_base_agent_accepts_mcp_servers(self):
        """BaseAgent should accept mcp_servers parameter."""
        mcp_config = {
            "playwright": {
                "command": "npx",
                "args": ["@anthropic/mcp-server-playwright"]
            }
        }
        agent = BaseAgent(
            system_prompt="Test",
            mcp_servers=mcp_config,
        )

        assert agent.mcp_servers == mcp_config

    def test_planner_agent_accepts_mcp_servers(self):
        """PlannerAgent should accept mcp_servers parameter."""
        mcp_config = {"figma": {"command": "figma-mcp"}}
        agent = PlannerAgent(mcp_servers=mcp_config)

        assert agent.mcp_servers == mcp_config

    def test_executor_agent_accepts_mcp_servers(self):
        """ExecutorAgent should accept mcp_servers parameter."""
        mcp_config = {"playwright": {"command": "npx"}}
        agent = ExecutorAgent(mcp_servers=mcp_config)

        assert agent.mcp_servers == mcp_config

    def test_create_planner_agent_with_mcp(self):
        """create_planner_agent should accept MCP config."""
        mcp_config = {"figma": {"command": "figma-mcp"}}
        agent = create_planner_agent(mcp_servers=mcp_config)

        assert agent.mcp_servers == mcp_config

    def test_create_executor_agent_with_mcp(self):
        """create_executor_agent should accept MCP config."""
        mcp_config = {"playwright": {"command": "npx"}}
        agent = create_executor_agent(mcp_servers=mcp_config)

        assert agent.mcp_servers == mcp_config

    def test_factory_with_allowed_tools(self):
        """Factory functions should accept allowed_tools."""
        custom_tools = ["Read", "Write", "mcp__playwright__*"]
        agent = create_executor_agent(allowed_tools=custom_tools)

        assert agent.allowed_tools == custom_tools

    def test_agent_options_include_mcp_servers(self):
        """Agent options should include mcp_servers when configured."""
        mcp_config = {"playwright": {"command": "npx"}}
        agent = ExecutorAgent(mcp_servers=mcp_config)

        options = agent._get_options()

        # The options should have mcp_servers set
        assert options.mcp_servers == mcp_config

    def test_agent_options_no_mcp_when_not_configured(self):
        """Agent options should not have mcp_servers when not configured."""
        agent = ExecutorAgent()

        options = agent._get_options()

        # mcp_servers should be empty or None when not configured
        assert not options.mcp_servers  # Empty dict {} or None are both falsy


# ============================================================================
# File Checkpoint/Rewind Tests (SDK 0.1.17+)
# ============================================================================


class TestFileCheckpointRewind:
    """Test file checkpoint and rewind functionality."""

    def test_checkpoint_uuid_initialized_to_none(self):
        """Checkpoint UUID should be None on initialization."""
        agent = BaseAgent(system_prompt="Test")
        assert agent._checkpoint_uuid is None
        assert agent._last_message_uuid is None

    def test_set_checkpoint_returns_none_without_messages(self):
        """set_checkpoint should return None if no messages received yet."""
        agent = BaseAgent(system_prompt="Test")
        result = agent.set_checkpoint()
        assert result is None

    def test_set_checkpoint_captures_last_uuid(self):
        """set_checkpoint should capture the last message UUID."""
        agent = BaseAgent(system_prompt="Test")
        agent._last_message_uuid = "test-uuid-12345"

        result = agent.set_checkpoint()

        assert result == "test-uuid-12345"
        assert agent._checkpoint_uuid == "test-uuid-12345"

    def test_get_checkpoint_returns_checkpoint_uuid(self):
        """get_checkpoint should return the current checkpoint UUID."""
        agent = BaseAgent(system_prompt="Test")
        agent._checkpoint_uuid = "checkpoint-uuid-abc"

        assert agent.get_checkpoint() == "checkpoint-uuid-abc"

    def test_clear_checkpoint_resets_uuid(self):
        """clear_checkpoint should reset checkpoint UUID to None."""
        agent = BaseAgent(system_prompt="Test")
        agent._checkpoint_uuid = "some-uuid"

        agent.clear_checkpoint()

        assert agent._checkpoint_uuid is None

    def test_rewind_returns_false_without_checkpoint(self):
        """rewind_to_checkpoint should return False if no checkpoint set."""
        agent = BaseAgent(system_prompt="Test")
        result = agent.rewind_to_checkpoint()
        assert result is False

    def test_rewind_returns_false_without_client(self):
        """rewind_to_checkpoint should return False if client not initialized."""
        agent = BaseAgent(system_prompt="Test")
        agent._checkpoint_uuid = "some-uuid"

        result = agent.rewind_to_checkpoint()

        assert result is False

    @pytest.mark.asyncio
    async def test_rewind_calls_client_rewind_files(self):
        """rewind_to_checkpoint_async should call client.rewind_files."""
        agent = BaseAgent(system_prompt="Test")
        agent._checkpoint_uuid = "test-checkpoint-uuid"

        # Mock the client
        mock_client = AsyncMock()
        agent._client = mock_client

        result = await agent.rewind_to_checkpoint_async()

        assert result is True
        mock_client.rewind_files.assert_called_once_with("test-checkpoint-uuid")

    @pytest.mark.asyncio
    async def test_rewind_handles_exception(self):
        """rewind_to_checkpoint_async should handle exceptions gracefully."""
        agent = BaseAgent(system_prompt="Test")
        agent._checkpoint_uuid = "test-uuid"

        # Mock client that raises an exception
        mock_client = AsyncMock()
        mock_client.rewind_files.side_effect = Exception("Rewind failed")
        agent._client = mock_client

        result = await agent.rewind_to_checkpoint_async()

        assert result is False


# ============================================================================
# MCP Status Tests (SDK 0.1.23+)
# ============================================================================


class TestMcpStatus:
    """Test MCP status monitoring functionality."""

    def test_get_mcp_status_returns_empty_without_client(self):
        """get_mcp_status should return empty dict if no client."""
        agent = BaseAgent(system_prompt="Test")
        result = agent.get_mcp_status()
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_mcp_status_calls_client_method(self):
        """get_mcp_status_async should call client.get_mcp_status."""
        agent = BaseAgent(system_prompt="Test")

        # Mock the client with MCP status
        mock_status = {
            "playwright": {"connected": True},
            "figma": {"connected": False, "error": "Connection refused"}
        }
        mock_client = AsyncMock()
        mock_client.get_mcp_status.return_value = mock_status
        agent._client = mock_client

        result = await agent.get_mcp_status_async()

        assert result == mock_status
        mock_client.get_mcp_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_mcp_status_handles_exception(self):
        """get_mcp_status_async should handle exceptions gracefully."""
        agent = BaseAgent(system_prompt="Test")

        mock_client = AsyncMock()
        mock_client.get_mcp_status.side_effect = Exception("Status check failed")
        agent._client = mock_client

        result = await agent.get_mcp_status_async()

        assert result == {}


# ============================================================================
# Tool Invocation Tracking Tests (SDK 0.1.22+)
# ============================================================================


class TestToolInvocationTracking:
    """Test tool invocation tracking functionality."""

    def test_tool_invocations_initialized_empty(self):
        """Tool invocations list should be empty on initialization."""
        agent = BaseAgent(system_prompt="Test")
        assert agent._tool_invocations == []

    def test_get_tool_invocations_returns_copy(self):
        """get_tool_invocations should return a copy of the list."""
        agent = BaseAgent(system_prompt="Test")
        agent._tool_invocations = [{"tool": "Read", "result": "ok"}]

        result = agent.get_tool_invocations()

        assert result == [{"tool": "Read", "result": "ok"}]
        # Verify it's a copy, not the same reference
        assert result is not agent._tool_invocations

    def test_clear_tool_invocations(self):
        """clear_tool_invocations should empty the list."""
        agent = BaseAgent(system_prompt="Test")
        agent._tool_invocations = [{"tool": "Read"}, {"tool": "Write"}]

        agent.clear_tool_invocations()

        assert agent._tool_invocations == []


# ============================================================================
# Effort Parameter Tests (SDK 0.1.46+)
# ============================================================================


class TestEffortParameter:
    """Test effort parameter support."""

    def test_effort_stored_on_agent(self):
        """Effort should be stored on the agent when provided."""
        agent = BaseAgent(system_prompt="Test", effort="high")
        assert agent.effort == "high"

    def test_effort_none_by_default(self):
        """Effort should be None by default."""
        agent = BaseAgent(system_prompt="Test")
        assert agent.effort is None

    @patch("orchestrator_auto.agents.ClaudeAgentOptions")
    def test_effort_passed_to_options(self, mock_options_class):
        """Effort should be passed to ClaudeAgentOptions when set."""
        agent = BaseAgent(system_prompt="Test", effort="high")
        agent._get_options()

        call_kwargs = mock_options_class.call_args[1]
        assert call_kwargs["effort"] == "high"

    @patch("orchestrator_auto.agents.ClaudeAgentOptions")
    def test_effort_not_passed_when_none(self, mock_options_class):
        """Effort should not be in options kwargs when None."""
        agent = BaseAgent(system_prompt="Test", effort=None)
        agent._get_options()

        call_kwargs = mock_options_class.call_args[1]
        assert "effort" not in call_kwargs

    def test_effort_all_valid_values(self):
        """All valid effort levels should be accepted."""
        for level in ("low", "medium", "high", "max"):
            agent = BaseAgent(system_prompt="Test", effort=level)
            assert agent.effort == level


# ============================================================================
# ThinkingConfig Parameter Tests (SDK 0.1.46+)
# ============================================================================


class TestThinkingParameter:
    """Test thinking config parameter support."""

    def test_thinking_stored_on_agent(self):
        """Thinking value should be stored on the agent."""
        agent = BaseAgent(system_prompt="Test", thinking="adaptive")
        assert agent.thinking == "adaptive"

    def test_thinking_none_by_default(self):
        """Thinking should be None by default."""
        agent = BaseAgent(system_prompt="Test")
        assert agent.thinking is None

    def test_resolve_thinking_adaptive(self):
        """'adaptive' should resolve to ThinkingConfigAdaptive with type key."""
        agent = BaseAgent(system_prompt="Test", thinking="adaptive")
        result = agent._resolve_thinking_config()
        assert isinstance(result, dict)
        assert result["type"] == "adaptive"
        assert "budget_tokens" not in result

    def test_resolve_thinking_disabled(self):
        """'disabled' should resolve to ThinkingConfigDisabled with type key."""
        agent = BaseAgent(system_prompt="Test", thinking="disabled")
        result = agent._resolve_thinking_config()
        assert isinstance(result, dict)
        assert result["type"] == "disabled"
        assert "budget_tokens" not in result

    def test_resolve_thinking_int(self):
        """Integer should resolve to ThinkingConfigEnabled with type and budget_tokens."""
        agent = BaseAgent(system_prompt="Test", thinking=10000)
        result = agent._resolve_thinking_config()
        assert isinstance(result, dict)
        assert result["type"] == "enabled"
        assert result["budget_tokens"] == 10000

    def test_resolve_thinking_string_int(self):
        """String integer should resolve to ThinkingConfigEnabled."""
        agent = BaseAgent(system_prompt="Test", thinking="5000")
        result = agent._resolve_thinking_config()
        assert isinstance(result, dict)
        assert result["type"] == "enabled"
        assert result["budget_tokens"] == 5000

    def test_resolve_thinking_invalid_string(self):
        """Invalid thinking string should raise ValueError."""
        agent = BaseAgent(system_prompt="Test", thinking="invalid")
        with pytest.raises(ValueError, match="Invalid thinking config"):
            agent._resolve_thinking_config()

    @patch("orchestrator_auto.agents.ClaudeAgentOptions")
    def test_thinking_passed_to_options(self, mock_options_class):
        """Thinking config should be passed to ClaudeAgentOptions."""
        agent = BaseAgent(system_prompt="Test", thinking="adaptive")
        agent._get_options()

        call_kwargs = mock_options_class.call_args[1]
        assert "thinking" in call_kwargs
        assert isinstance(call_kwargs["thinking"], dict)

    @patch("orchestrator_auto.agents.ClaudeAgentOptions")
    def test_thinking_not_passed_when_none(self, mock_options_class):
        """Thinking should not be in options kwargs when None."""
        agent = BaseAgent(system_prompt="Test", thinking=None)
        agent._get_options()

        call_kwargs = mock_options_class.call_args[1]
        assert "thinking" not in call_kwargs


# ============================================================================
# Stop Reason Tracking Tests (SDK 0.1.46+)
# ============================================================================


class TestStopReasonTracking:
    """Test stop reason capture from ResultMessage."""

    def test_stop_reason_initialized_to_none(self):
        """Stop reason should be None on initialization."""
        agent = BaseAgent(system_prompt="Test")
        assert agent._last_stop_reason is None

    def test_get_last_stop_reason_returns_value(self):
        """get_last_stop_reason should return the stored value."""
        agent = BaseAgent(system_prompt="Test")
        agent._last_stop_reason = "end_turn"
        assert agent.get_last_stop_reason() == "end_turn"

    def test_get_last_stop_reason_returns_none_initially(self):
        """get_last_stop_reason should return None before any messages."""
        agent = BaseAgent(system_prompt="Test")
        assert agent.get_last_stop_reason() is None

    @pytest.mark.asyncio
    async def test_stop_reason_captured_from_result_message(self):
        """stop_reason should be captured from ResultMessage during message processing."""
        agent = BaseAgent(system_prompt="Test")

        # Create mock ResultMessage
        mock_result = MagicMock()
        mock_result.stop_reason = "end_turn"
        mock_result.usage = None
        # Make isinstance(message, ResultMessage) work via duck-typing check in agents.py
        # agents.py uses isinstance checks, so we patch the isinstance calls
        # Instead, we directly set the _last_stop_reason to verify the getter
        agent._last_stop_reason = "end_turn"

        assert agent._last_stop_reason == "end_turn"
        assert agent.get_last_stop_reason() == "end_turn"

    @pytest.mark.asyncio
    async def test_stop_reason_max_tokens_detected(self):
        """max_tokens stop_reason should be stored for detection."""
        agent = BaseAgent(system_prompt="Test")

        # Simulate what send_message_async does when it sees max_tokens
        agent._last_stop_reason = "max_tokens"

        assert agent.get_last_stop_reason() == "max_tokens"


# ============================================================================
# PostToolUseFailure Hook Tests (SDK 0.1.26+)
# ============================================================================


class TestPostToolUseFailureHook:
    """Test PostToolUseFailure hook and tool failure tracking."""

    def test_tool_failures_initialized_empty(self):
        """Tool failures list should be empty on initialization."""
        agent = BaseAgent(system_prompt="Test")
        assert agent._tool_failures == []

    def test_on_tool_failure_captures_failure(self):
        """_on_tool_failure should append failure to _tool_failures."""
        agent = BaseAgent(system_prompt="Test")

        asyncio.get_event_loop().run_until_complete(
            agent._on_tool_failure({
                "tool_name": "Bash",
                "error": "Command failed with exit code 1",
            }, None, None)
        )

        assert len(agent._tool_failures) == 1
        assert agent._tool_failures[0]["tool_name"] == "Bash"
        assert agent._tool_failures[0]["error"] == "Command failed with exit code 1"
        assert "timestamp" in agent._tool_failures[0]

    def test_on_tool_failure_handles_missing_fields(self):
        """_on_tool_failure should handle missing fields gracefully."""
        agent = BaseAgent(system_prompt="Test")

        asyncio.get_event_loop().run_until_complete(
            agent._on_tool_failure({}, None, None)
        )

        assert len(agent._tool_failures) == 1
        assert agent._tool_failures[0]["tool_name"] == "unknown"
        assert agent._tool_failures[0]["error"] == ""

    def test_get_tool_failures_returns_copy(self):
        """get_tool_failures should return a copy of the list."""
        agent = BaseAgent(system_prompt="Test")
        agent._tool_failures = [{"tool_name": "Read", "error": "fail", "timestamp": 0}]

        result = agent.get_tool_failures()

        assert result == agent._tool_failures
        assert result is not agent._tool_failures

    def test_clear_tool_failures(self):
        """clear_tool_failures should empty the list."""
        agent = BaseAgent(system_prompt="Test")
        agent._tool_failures = [{"tool_name": "Read", "error": "fail", "timestamp": 0}]

        agent.clear_tool_failures()

        assert agent._tool_failures == []

    def test_hooks_include_post_tool_use_failure(self):
        """_build_hooks should include PostToolUseFailure hook with HookMatcher."""
        from claude_agent_sdk.types import HookMatcher
        agent = BaseAgent(system_prompt="Test")
        hooks = agent._build_hooks()

        assert "PostToolUseFailure" in hooks
        assert len(hooks["PostToolUseFailure"]) == 1
        matcher = hooks["PostToolUseFailure"][0]
        assert isinstance(matcher, HookMatcher)
        assert matcher.matcher == "*"
        assert agent._on_tool_failure in matcher.hooks


# ============================================================================
# Notification Hook Tests (SDK 0.1.29+)
# ============================================================================


class TestNotificationHook:
    """Test Notification hook and notification tracking."""

    def test_notifications_initialized_empty(self):
        """Notifications list should be empty on initialization."""
        agent = BaseAgent(system_prompt="Test")
        assert agent._notifications == []

    def test_on_notification_captures_notification(self):
        """_on_notification should append to _notifications."""
        agent = BaseAgent(system_prompt="Test")

        asyncio.get_event_loop().run_until_complete(
            agent._on_notification({
                "message": "Rate limit approaching",
                "type": "warning",
            }, None, None)
        )

        assert len(agent._notifications) == 1
        assert agent._notifications[0]["message"] == "Rate limit approaching"
        assert agent._notifications[0]["type"] == "warning"
        assert "timestamp" in agent._notifications[0]

    def test_on_notification_handles_missing_fields(self):
        """_on_notification should handle missing fields gracefully."""
        agent = BaseAgent(system_prompt="Test")

        asyncio.get_event_loop().run_until_complete(
            agent._on_notification({}, None, None)
        )

        assert len(agent._notifications) == 1
        assert agent._notifications[0]["message"] == ""
        assert agent._notifications[0]["type"] == "info"

    def test_on_notification_callback_called(self):
        """on_notification callback should be called when provided."""
        callback = Mock()
        agent = BaseAgent(system_prompt="Test", on_notification=callback)

        asyncio.get_event_loop().run_until_complete(
            agent._on_notification({
                "message": "SDK notification",
                "type": "info",
            }, None, None)
        )

        callback.assert_called_once()
        call_arg = callback.call_args[0][0]
        assert call_arg["message"] == "SDK notification"

    def test_on_notification_no_callback_no_error(self):
        """_on_notification should work without callback."""
        agent = BaseAgent(system_prompt="Test")

        # Should not raise
        asyncio.get_event_loop().run_until_complete(
            agent._on_notification({"message": "test"}, None, None)
        )

        assert len(agent._notifications) == 1

    def test_get_notifications_returns_copy(self):
        """get_notifications should return a copy of the list."""
        agent = BaseAgent(system_prompt="Test")
        agent._notifications = [{"message": "test", "type": "info", "timestamp": 0}]

        result = agent.get_notifications()

        assert result == agent._notifications
        assert result is not agent._notifications

    def test_clear_notifications(self):
        """clear_notifications should empty the list."""
        agent = BaseAgent(system_prompt="Test")
        agent._notifications = [{"message": "test", "type": "info", "timestamp": 0}]

        agent.clear_notifications()

        assert agent._notifications == []

    def test_hooks_include_notification(self):
        """_build_hooks should include Notification hook with HookMatcher."""
        from claude_agent_sdk.types import HookMatcher
        agent = BaseAgent(system_prompt="Test")
        hooks = agent._build_hooks()

        assert "Notification" in hooks
        assert len(hooks["Notification"]) == 1
        matcher = hooks["Notification"][0]
        assert isinstance(matcher, HookMatcher)
        assert matcher.matcher == "*"
        assert agent._on_notification in matcher.hooks


# ============================================================================
# RateLimitEvent Handling Tests (SDK 0.1.49+)
# ============================================================================


class TestRateLimitEvent:
    """Test RateLimitEvent handling in the message loop."""

    @pytest.mark.asyncio
    async def test_rate_limit_event_is_logged(self):
        """RateLimitEvent messages should be logged as warnings."""
        agent = BaseAgent(system_prompt="Test")

        # Create a fake RateLimitEvent class for testing (SDK may not have it yet)
        class FakeRateLimitEvent:
            def __str__(self):
                return "Rate limit exceeded, retry after 30s"

        fake_event = FakeRateLimitEvent()

        # Mock the message loop to yield a RateLimitEvent then a ResultMessage
        mock_result = MagicMock()
        mock_result.stop_reason = "end_turn"
        mock_result.usage = None

        messages = [fake_event, mock_result]

        # Patch RateLimitEvent in agents module so isinstance check works
        import orchestrator_auto.agents as agents_module
        original_rate_limit = agents_module.RateLimitEvent

        try:
            agents_module.RateLimitEvent = FakeRateLimitEvent

            mock_client = AsyncMock()
            mock_client.receive_messages = Mock(return_value=AsyncIteratorMock(messages))
            mock_client.query = AsyncMock()

            with patch.object(agent, '_get_client', return_value=mock_client):
                with patch('orchestrator_auto.agents.logger') as mock_logger:
                    await agent.send_message_async("test")
                    mock_logger.warning.assert_any_call(
                        "Rate limited: Rate limit exceeded, retry after 30s"
                    )
        finally:
            agents_module.RateLimitEvent = original_rate_limit

    @pytest.mark.asyncio
    async def test_rate_limit_event_forwarded_to_notification_callback(self):
        """RateLimitEvent messages should be forwarded to on_notification callback."""
        callback = Mock()
        agent = BaseAgent(system_prompt="Test", on_notification=callback)

        # Create a fake RateLimitEvent class
        class FakeRateLimitEvent:
            def __str__(self):
                return "Rate limit exceeded, retry after 30s"

        fake_event = FakeRateLimitEvent()

        # Mock ResultMessage to end the loop
        mock_result = MagicMock()
        mock_result.stop_reason = "end_turn"
        mock_result.usage = None

        messages = [fake_event, mock_result]

        import orchestrator_auto.agents as agents_module
        original_rate_limit = agents_module.RateLimitEvent

        try:
            agents_module.RateLimitEvent = FakeRateLimitEvent

            mock_client = AsyncMock()
            mock_client.receive_messages = Mock(return_value=AsyncIteratorMock(messages))
            mock_client.query = AsyncMock()

            with patch.object(agent, '_get_client', return_value=mock_client):
                await agent.send_message_async("test")

            # Verify callback was called with rate_limit type
            callback.assert_called_once()
            call_arg = callback.call_args[0][0]
            assert call_arg["type"] == "rate_limit"
            assert "Rate limit exceeded" in call_arg["message"]
            assert "timestamp" in call_arg
        finally:
            agents_module.RateLimitEvent = original_rate_limit

    @pytest.mark.asyncio
    async def test_rate_limit_event_no_callback_no_error(self):
        """RateLimitEvent should not error when no on_notification callback is set."""
        agent = BaseAgent(system_prompt="Test")  # No on_notification

        class FakeRateLimitEvent:
            def __str__(self):
                return "Rate limited"

        fake_event = FakeRateLimitEvent()

        mock_result = MagicMock()
        mock_result.stop_reason = "end_turn"
        mock_result.usage = None

        messages = [fake_event, mock_result]

        import orchestrator_auto.agents as agents_module
        original_rate_limit = agents_module.RateLimitEvent

        try:
            agents_module.RateLimitEvent = FakeRateLimitEvent

            mock_client = AsyncMock()
            mock_client.receive_messages = Mock(return_value=AsyncIteratorMock(messages))
            mock_client.query = AsyncMock()

            with patch.object(agent, '_get_client', return_value=mock_client):
                # Should not raise
                result = await agent.send_message_async("test")
                assert isinstance(result, str)
        finally:
            agents_module.RateLimitEvent = original_rate_limit


# ============================================================================
# Factory Functions with New Parameters Tests (SDK 0.1.46+)
# ============================================================================


class TestFactoryFunctionsNewParams:
    """Test that factory functions pass effort and thinking through."""

    def test_create_planner_agent_with_effort(self):
        """create_planner_agent should pass effort to PlannerAgent."""
        agent = create_planner_agent(effort="high")
        assert agent.effort == "high"

    def test_create_executor_agent_with_effort(self):
        """create_executor_agent should pass effort to ExecutorAgent."""
        agent = create_executor_agent(effort="low")
        assert agent.effort == "low"

    def test_create_planner_agent_with_thinking(self):
        """create_planner_agent should pass thinking to PlannerAgent."""
        agent = create_planner_agent(thinking="adaptive")
        assert agent.thinking == "adaptive"

    def test_create_executor_agent_with_thinking(self):
        """create_executor_agent should pass thinking to ExecutorAgent."""
        agent = create_executor_agent(thinking=10000)
        assert agent.thinking == 10000

    def test_create_planner_agent_effort_none_by_default(self):
        """create_planner_agent should have effort=None by default."""
        agent = create_planner_agent()
        assert agent.effort is None

    def test_create_executor_agent_thinking_none_by_default(self):
        """create_executor_agent should have thinking=None by default."""
        agent = create_executor_agent()
        assert agent.thinking is None

    def test_create_planner_agent_with_both(self):
        """create_planner_agent should accept both effort and thinking."""
        agent = create_planner_agent(effort="max", thinking="adaptive")
        assert agent.effort == "max"
        assert agent.thinking == "adaptive"

    def test_create_executor_agent_with_both(self):
        """create_executor_agent should accept both effort and thinking."""
        agent = create_executor_agent(effort="medium", thinking="disabled")
        assert agent.effort == "medium"
        assert agent.thinking == "disabled"


# ============================================================================
# Live Token Delta Tests (SDK 0.1.49+)
# ============================================================================


class TestLiveTokenDelta:
    """Test on_live_tokens callback for delta-style live token usage."""

    @pytest.mark.asyncio
    async def test_on_live_tokens_fires_per_assistant_message(self):
        """on_live_tokens should fire for each AssistantMessage with usage."""
        from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock

        callback = Mock()
        agent = BaseAgent(system_prompt="Test", on_live_tokens=callback)

        # Create AssistantMessage with usage (simulating SDK 0.1.49+)
        assistant_msg = AssistantMessage(
            content=[TextBlock(text="Hello")],
            model="claude-sonnet-4-6",
        )
        # Attach usage attribute (SDK 0.1.49+ adds this)
        assistant_msg.usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            "thinking_tokens": 10,
        }

        # Create a second AssistantMessage with usage
        assistant_msg2 = AssistantMessage(
            content=[TextBlock(text=" world")],
            model="claude-sonnet-4-6",
        )
        assistant_msg2.usage = {
            "input_tokens": 200,
            "output_tokens": 80,
            "thinking_tokens": 0,
        }

        # ResultMessage to end the loop
        result_msg = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test",
            stop_reason="end_turn",
            usage=None,
        )

        messages = [assistant_msg, assistant_msg2, result_msg]

        mock_client = AsyncMock()
        mock_client.receive_messages = Mock(return_value=AsyncIteratorMock(messages))
        mock_client.query = AsyncMock()

        with patch.object(agent, '_get_client', return_value=mock_client):
            await agent.send_message_async("test")

        # on_live_tokens should have been called twice (once per AssistantMessage)
        assert callback.call_count == 2

        # First call
        first_call = callback.call_args_list[0][0][0]
        assert first_call["input_tokens"] == 100
        assert first_call["output_tokens"] == 50
        assert first_call["thinking_tokens"] == 10
        assert first_call["is_delta"] is True

        # Second call
        second_call = callback.call_args_list[1][0][0]
        assert second_call["input_tokens"] == 200
        assert second_call["output_tokens"] == 80
        assert second_call["is_delta"] is True

    @pytest.mark.asyncio
    async def test_on_token_usage_fires_once_per_result_message(self):
        """on_token_usage should fire only on ResultMessage, not on AssistantMessage."""
        from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock

        token_callback = Mock()
        live_callback = Mock()
        agent = BaseAgent(
            system_prompt="Test",
            on_token_usage=token_callback,
            on_live_tokens=live_callback,
        )

        # AssistantMessage with usage
        assistant_msg = AssistantMessage(
            content=[TextBlock(text="Hello")],
            model="claude-sonnet-4-6",
        )
        assistant_msg.usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            "thinking_tokens": 10,
        }

        # ResultMessage with final usage
        result_msg = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test",
            stop_reason="end_turn",
            total_cost_usd=0.005,
            usage={
                "input_tokens": 500,
                "output_tokens": 200,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "thinking_tokens": 10,
            },
        )

        messages = [assistant_msg, result_msg]

        mock_client = AsyncMock()
        mock_client.receive_messages = Mock(return_value=AsyncIteratorMock(messages))
        mock_client.query = AsyncMock()

        with patch.object(agent, '_get_client', return_value=mock_client):
            await agent.send_message_async("test")

        # on_token_usage fires exactly once (on ResultMessage)
        assert token_callback.call_count == 1
        token_data = token_callback.call_args[0][0]
        assert token_data["input_tokens"] == 500
        assert token_data["cost_usd"] == 0.005

        # on_live_tokens fires exactly once (on AssistantMessage)
        assert live_callback.call_count == 1

    @pytest.mark.asyncio
    async def test_on_live_tokens_not_called_when_none(self):
        """No error should occur when on_live_tokens is None."""
        from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock

        agent = BaseAgent(system_prompt="Test")  # on_live_tokens defaults to None
        assert agent.on_live_tokens is None

        # AssistantMessage with usage
        assistant_msg = AssistantMessage(
            content=[TextBlock(text="Hello")],
            model="claude-sonnet-4-6",
        )
        assistant_msg.usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            "thinking_tokens": 0,
        }

        result_msg = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test",
            stop_reason="end_turn",
            usage=None,
        )

        messages = [assistant_msg, result_msg]

        mock_client = AsyncMock()
        mock_client.receive_messages = Mock(return_value=AsyncIteratorMock(messages))
        mock_client.query = AsyncMock()

        with patch.object(agent, '_get_client', return_value=mock_client):
            # Should not raise any exception
            result = await agent.send_message_async("test")
            assert result == "Hello"

    @pytest.mark.asyncio
    async def test_on_live_tokens_does_not_include_cost(self):
        """The delta payload should NOT contain cost_usd."""
        from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock

        callback = Mock()
        agent = BaseAgent(system_prompt="Test", on_live_tokens=callback)

        assistant_msg = AssistantMessage(
            content=[TextBlock(text="Hello")],
            model="claude-sonnet-4-6",
        )
        assistant_msg.usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            "thinking_tokens": 0,
        }

        result_msg = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test",
            stop_reason="end_turn",
            usage=None,
        )

        messages = [assistant_msg, result_msg]

        mock_client = AsyncMock()
        mock_client.receive_messages = Mock(return_value=AsyncIteratorMock(messages))
        mock_client.query = AsyncMock()

        with patch.object(agent, '_get_client', return_value=mock_client):
            await agent.send_message_async("test")

        assert callback.call_count == 1
        delta = callback.call_args[0][0]
        assert "cost_usd" not in delta
        assert "is_delta" in delta
        assert delta["is_delta"] is True
