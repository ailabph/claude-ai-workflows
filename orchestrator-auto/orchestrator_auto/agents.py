"""
Agent wrappers for Claude SDK integration.

Provides PlannerAgent and ExecutorAgent classes that wrap the Claude SDK Client
with appropriate system prompts and tool permissions.
"""

import asyncio
from typing import Optional, Dict, Any, List, Callable, Union
from pathlib import Path
from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import (
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    UserMessage,
)

from .prompts import PLANNER_SYSTEM_PROMPT, EXECUTOR_SYSTEM_PROMPT, DEFAULT_CHAT_PROMPT


# Tool permissions for both agents (list of tool names)
DEFAULT_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
]

# MCP configuration types (matches Claude SDK)
McpServerConfig = Dict[str, Any]  # {"command": str, "args": list, "env": dict}
McpServersConfig = Dict[str, McpServerConfig]  # {"playwright": {...}, "figma": {...}}


def build_allowed_tools(
    base_tools: Optional[List[str]] = None,
    mcp_tools: Optional[List[str]] = None,
) -> List[str]:
    """
    Build the allowed tools list by combining base tools with MCP tools.

    This helper ensures clean import boundaries - engine.py doesn't need
    to import DEFAULT_TOOLS directly.

    Args:
        base_tools: Base tool list (default: DEFAULT_TOOLS)
        mcp_tools: Additional MCP tool patterns to add

    Returns:
        Combined list of allowed tools
    """
    tools = list(base_tools or DEFAULT_TOOLS)
    if mcp_tools:
        tools.extend(mcp_tools)
    return tools


class BaseAgent:
    """Base class for orchestrator agents."""

    def __init__(
        self,
        system_prompt: str,
        allowed_tools: Optional[List[str]] = None,
        model: str = "claude-sonnet-4-5-20250929",
        session_id: str = "default",
        hooks: Optional[Dict[str, Any]] = None,
        cwd: Optional[Path] = None,
        mcp_servers: Optional[Union[McpServersConfig, str]] = None,
        on_token_usage: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """
        Initialize the agent.

        Args:
            system_prompt: System prompt defining agent role and behavior
            allowed_tools: List of allowed tools (default: Read, Write, Edit, Bash, Glob, Grep)
            model: Claude model to use
            session_id: Session ID for the agent
            hooks: Optional hooks configuration
            cwd: Working directory for agent (default: current directory)
            mcp_servers: MCP server configuration dict or path to .mcp.json file
            on_token_usage: Optional callback for token usage reporting
        """
        self.system_prompt = system_prompt
        self.allowed_tools = allowed_tools or DEFAULT_TOOLS
        self.model = model
        self.session_id = session_id
        self.hooks = hooks
        self.cwd = cwd or Path.cwd()
        self.mcp_servers = mcp_servers
        self.on_token_usage = on_token_usage
        self._options: Optional[ClaudeAgentOptions] = None

        # Client for conversation continuity
        self._client: Optional[ClaudeSDKClient] = None
        self._client_entered: bool = False

        # Persistent event loop for async operations (required for client lifecycle)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # File checkpoint/rewind support (SDK 0.1.17+)
        self._checkpoint_uuid: Optional[str] = None  # Last checkpoint before milestone
        self._last_message_uuid: Optional[str] = None  # Most recent message UUID

        # Tool invocation tracking (SDK 0.1.22+)
        self._tool_invocations: List[Dict[str, Any]] = []

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """
        Get or create a persistent event loop for this agent.

        FIX: Don't set as global event loop to avoid conflicts when multiple
        agents are active (planner + executor). Each agent manages its own loop.
        """
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            # FIX: Removed asyncio.set_event_loop(self._loop) to prevent
            # global event loop conflicts between planner and executor agents
        return self._loop

    def _get_options(self) -> ClaudeAgentOptions:
        """Get or create agent options."""
        if self._options is None:
            options_kwargs = {
                "system_prompt": self.system_prompt,
                "tools": self.allowed_tools,
                "model": self.model,
                "cwd": self.cwd,
                "permission_mode": "bypassPermissions",  # Auto-approve all operations including Bash
            }

            # Add MCP servers if configured
            if self.mcp_servers:
                options_kwargs["mcp_servers"] = self.mcp_servers

            self._options = ClaudeAgentOptions(**options_kwargs)
        return self._options

    async def _get_client(self) -> ClaudeSDKClient:
        """Get or create the SDK client with conversation continuity."""
        if self._client is None:
            self._client = ClaudeSDKClient(self._get_options())
            await self._client.__aenter__()
            self._client_entered = True
        return self._client

    async def send_message_async(
        self,
        content: str,
        on_chunk: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Send a message to the agent and get response (async).

        Maintains conversation continuity across multiple calls using ClaudeSDKClient.

        Args:
            content: Message content to send
            on_chunk: Optional callback for each text chunk (for streaming indicators)

        Returns:
            String response from agent
        """
        client = await self._get_client()
        response_text = ""

        # Send query and receive response
        await client.query(content)
        async for message in client.receive_messages():
            # Capture UUID from UserMessage (SDK 0.1.17+)
            if isinstance(message, UserMessage):
                if hasattr(message, 'uuid') and message.uuid:
                    self._last_message_uuid = message.uuid
                # Capture tool results (SDK 0.1.22+)
                if hasattr(message, 'tool_use_result') and message.tool_use_result:
                    self._tool_invocations.append(message.tool_use_result)
            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text
                        if on_chunk:
                            on_chunk(block.text)
            elif isinstance(message, ResultMessage):
                # Response complete - extract token usage
                if self.on_token_usage and message.usage:
                    usage_data = {
                        "input_tokens": message.usage.get("input_tokens", 0),
                        "output_tokens": message.usage.get("output_tokens", 0),
                        "cache_creation_input_tokens": message.usage.get("cache_creation_input_tokens", 0),
                        "cache_read_input_tokens": message.usage.get("cache_read_input_tokens", 0),
                        # Extended thinking tokens (Claude with extended_thinking enabled)
                        "thinking_tokens": message.usage.get("thinking_tokens", 0),
                        "model": self.model,
                        "cost_usd": message.total_cost_usd,
                    }
                    self.on_token_usage(usage_data)
                break

        return response_text

    def send_message(
        self,
        content: str,
        on_chunk: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Send a message to the agent and get response (sync wrapper).

        Args:
            content: Message content to send
            on_chunk: Optional callback for each text chunk (for streaming indicators)

        Returns:
            String response from agent
        """
        loop = self._get_loop()
        return loop.run_until_complete(self.send_message_async(content, on_chunk=on_chunk))

    def get_session_id(self) -> str:
        """Get the current session ID."""
        return self.session_id

    async def close_async(self) -> None:
        """Close the client connection (async)."""
        if self._client and self._client_entered:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                # Ignore cleanup errors (e.g., task scope issues)
                pass
            finally:
                self._client = None
                self._client_entered = False

    def close(self) -> None:
        """Close the agent session and cleanup resources."""
        if self._client and self._client_entered:
            try:
                loop = self._get_loop()
                loop.run_until_complete(self.close_async())
            except Exception:
                # Ignore cleanup errors - just clear state
                self._client = None
                self._client_entered = False

        # Close the event loop
        if self._loop and not self._loop.is_closed():
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None

    # ─────────────────────────────────────────────────────────────────────────
    # File Checkpoint/Rewind (SDK 0.1.17+)
    # ─────────────────────────────────────────────────────────────────────────

    def set_checkpoint(self) -> Optional[str]:
        """
        Mark current state as a checkpoint for potential rewind.

        Call this before starting a milestone to enable rollback if the
        milestone is rejected.

        Returns:
            The checkpoint UUID, or None if no message UUID is available
        """
        self._checkpoint_uuid = self._last_message_uuid
        return self._checkpoint_uuid

    def get_checkpoint(self) -> Optional[str]:
        """Get the current checkpoint UUID."""
        return self._checkpoint_uuid

    def clear_checkpoint(self) -> None:
        """Clear the current checkpoint (call after milestone is approved)."""
        self._checkpoint_uuid = None

    async def rewind_to_checkpoint_async(self) -> bool:
        """
        Rewind files to the last checkpoint (async).

        This reverts all file changes made since set_checkpoint() was called.

        Returns:
            True if rewind was successful, False otherwise
        """
        if not self._checkpoint_uuid:
            return False
        if not self._client:
            return False
        try:
            await self._client.rewind_files(self._checkpoint_uuid)
            return True
        except Exception:
            # Rewind is best-effort - don't fail if it doesn't work
            return False

    def rewind_to_checkpoint(self) -> bool:
        """
        Rewind files to the last checkpoint (sync wrapper).

        Returns:
            True if rewind was successful, False otherwise
        """
        if not self._checkpoint_uuid:
            return False
        loop = self._get_loop()
        return loop.run_until_complete(self.rewind_to_checkpoint_async())

    # ─────────────────────────────────────────────────────────────────────────
    # MCP Status (SDK 0.1.23+)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_mcp_status_async(self) -> Dict[str, Any]:
        """
        Get MCP server connection status (async).

        Returns:
            Dict mapping server names to their connection status
        """
        if not self._client:
            return {}
        try:
            return await self._client.get_mcp_status()
        except Exception:
            return {}

    def get_mcp_status(self) -> Dict[str, Any]:
        """
        Get MCP server connection status (sync wrapper).

        Returns:
            Dict mapping server names to their connection status
        """
        loop = self._get_loop()
        return loop.run_until_complete(self.get_mcp_status_async())

    # ─────────────────────────────────────────────────────────────────────────
    # Tool Invocation Tracking (SDK 0.1.22+)
    # ─────────────────────────────────────────────────────────────────────────

    def get_tool_invocations(self) -> List[Dict[str, Any]]:
        """
        Get all tool invocations captured during this agent's session.

        Returns:
            List of tool invocation results
        """
        return self._tool_invocations.copy()

    def clear_tool_invocations(self) -> None:
        """Clear the tool invocation history."""
        self._tool_invocations.clear()


class PlannerAgent(BaseAgent):
    """
    Planner/Reviewer agent for discovery, planning, and milestone validation.

    Responsibilities:
    - Phase 1: Discovery - Discuss feature requirements with user
    - Phase 2: Planning - Create implementation plan and define milestones
    - Phase 3: Execution Review - Validate executor progress reports
    """

    def __init__(
        self,
        model: str = "claude-opus-4-5-20251101",  # Use Opus for strategic planning
        session_id: str = "planner",
        mcp_servers: Optional[Union[McpServersConfig, str]] = None,
        **kwargs
    ):
        """
        Initialize the Planner agent.

        Args:
            model: Claude model to use (default: Opus for planning)
            session_id: Session ID for the agent
            mcp_servers: MCP server configuration dict or path to .mcp.json file
            **kwargs: Additional arguments for BaseAgent
        """
        super().__init__(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            model=model,
            session_id=session_id,
            mcp_servers=mcp_servers,
            **kwargs
        )

    def validate_milestone_report(self, report: str) -> str:
        """
        Send a milestone report for validation.

        Args:
            report: Executor's progress report

        Returns:
            Planner's validation response
        """
        validation_prompt = f"""Review this milestone progress report from the Executor:

{report}

Please validate:
1. Are all deliverables completed?
2. Do tests pass?
3. Does the code follow project conventions?
4. Are there any issues that need to be addressed?

Respond with [MILESTONE_APPROVED], [CHANGES_REQUESTED], or [HUMAN_INPUT_NEEDED] tags.
"""
        return self.send_message(validation_prompt)


class ExecutorAgent(BaseAgent):
    """
    Executor agent for implementing milestones.

    Responsibilities:
    - Execute ONE milestone at a time
    - Generate structured progress reports
    - Stop and wait for approval after each milestone
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",  # Use Sonnet for implementation
        session_id: str = "executor",
        mcp_servers: Optional[Union[McpServersConfig, str]] = None,
        **kwargs
    ):
        """
        Initialize the Executor agent.

        Args:
            model: Claude model to use (default: Sonnet for execution)
            session_id: Session ID for the agent
            mcp_servers: MCP server configuration dict or path to .mcp.json file
            **kwargs: Additional arguments for BaseAgent
        """
        super().__init__(
            system_prompt=EXECUTOR_SYSTEM_PROMPT,
            model=model,
            session_id=session_id,
            mcp_servers=mcp_servers,
            **kwargs
        )

    def execute_milestone(self, milestone_prompt: str) -> str:
        """
        Send a milestone prompt for execution.

        Args:
            milestone_prompt: Formatted milestone task prompt

        Returns:
            Executor's progress report
        """
        return self.send_message(milestone_prompt)

    def continue_milestone(self, feedback: str) -> str:
        """
        Continue working on a milestone after receiving feedback.

        Args:
            feedback: Planner's feedback or approval to continue

        Returns:
            Executor's response
        """
        return self.send_message(feedback)


def create_planner_agent(
    model: Optional[str] = None,
    session_id: str = "planner",
    hooks: Optional[Dict[str, Any]] = None,
    cwd: Optional[Path] = None,
    mcp_servers: Optional[Union[McpServersConfig, str]] = None,
    allowed_tools: Optional[List[str]] = None,
    on_token_usage: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> PlannerAgent:
    """
    Factory function to create a Planner agent.

    Args:
        model: Claude model to use (default: Opus)
        session_id: Session ID for the agent
        hooks: Optional hooks configuration
        cwd: Working directory
        mcp_servers: MCP server configuration dict or path to .mcp.json file
        allowed_tools: List of allowed tools (default: DEFAULT_TOOLS)
        on_token_usage: Optional callback for token usage reporting

    Returns:
        PlannerAgent instance
    """
    kwargs = {"session_id": session_id}
    if model:
        kwargs["model"] = model
    if hooks:
        kwargs["hooks"] = hooks
    if cwd:
        kwargs["cwd"] = cwd
    if mcp_servers:
        kwargs["mcp_servers"] = mcp_servers
    if allowed_tools:
        kwargs["allowed_tools"] = allowed_tools
    if on_token_usage:
        kwargs["on_token_usage"] = on_token_usage

    return PlannerAgent(**kwargs)


def create_executor_agent(
    model: Optional[str] = None,
    session_id: str = "executor",
    hooks: Optional[Dict[str, Any]] = None,
    cwd: Optional[Path] = None,
    mcp_servers: Optional[Union[McpServersConfig, str]] = None,
    allowed_tools: Optional[List[str]] = None,
    on_token_usage: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> ExecutorAgent:
    """
    Factory function to create an Executor agent.

    Args:
        model: Claude model to use (default: Sonnet)
        session_id: Session ID for the agent
        hooks: Optional hooks configuration
        cwd: Working directory
        mcp_servers: MCP server configuration dict or path to .mcp.json file
        allowed_tools: List of allowed tools (default: DEFAULT_TOOLS)
        on_token_usage: Optional callback for token usage reporting

    Returns:
        ExecutorAgent instance
    """
    kwargs = {"session_id": session_id}
    if model:
        kwargs["model"] = model
    if hooks:
        kwargs["hooks"] = hooks
    if cwd:
        kwargs["cwd"] = cwd
    if mcp_servers:
        kwargs["mcp_servers"] = mcp_servers
    if allowed_tools:
        kwargs["allowed_tools"] = allowed_tools
    if on_token_usage:
        kwargs["on_token_usage"] = on_token_usage

    return ExecutorAgent(**kwargs)


def create_chat_agent(
    model: str = "claude-sonnet-4-5-20250929",
    system_prompt: Optional[str] = None,
    allowed_tools: Optional[List[str]] = None,
    cwd: Optional[Path] = None,
) -> BaseAgent:
    """
    Factory function to create a direct chat agent.

    Unlike ExecutorAgent, this uses a custom system prompt suitable
    for general-purpose chat rather than milestone-based execution.

    Args:
        model: Claude model to use
        system_prompt: Custom system prompt (default: DEFAULT_CHAT_PROMPT)
        allowed_tools: List of allowed tools (default: all tools, empty list = no tools)
        cwd: Working directory

    Returns:
        BaseAgent instance configured for direct chat
    """
    return BaseAgent(
        system_prompt=system_prompt or DEFAULT_CHAT_PROMPT,
        allowed_tools=allowed_tools if allowed_tools is not None else DEFAULT_TOOLS,
        model=model,
        session_id="chat",
        cwd=cwd,
    )
