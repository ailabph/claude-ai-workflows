"""
Agent wrappers for Claude SDK integration.

Provides PlannerAgent and ExecutorAgent classes that wrap the Claude SDK Client
with appropriate system prompts and tool permissions.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List, Callable, Union
from pathlib import Path
from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import (
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    UserMessage,
    ThinkingConfigAdaptive,
    ThinkingConfigEnabled,
    ThinkingConfigDisabled,
    HookMatcher,
)

from .prompts import PLANNER_SYSTEM_PROMPT, EXECUTOR_SYSTEM_PROMPT, DEFAULT_CHAT_PROMPT

logger = logging.getLogger(__name__)


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


def read_claude_md(project_root: Optional[Path] = None) -> Optional[str]:
    """
    Read CLAUDE.md from the project root if it exists.

    Looks for CLAUDE.md (case-insensitive) in the project root directory.
    This file contains project-specific instructions that should be included
    in agent system prompts.

    Args:
        project_root: Project root directory (default: current directory)

    Returns:
        Contents of CLAUDE.md if found, None otherwise
    """
    root = project_root or Path.cwd()

    # Try common variations
    for filename in ["CLAUDE.md", "claude.md", "Claude.md"]:
        claude_md_path = root / filename
        if claude_md_path.exists():
            try:
                content = claude_md_path.read_text(encoding="utf-8")
                # Limit size to prevent prompt bloat (max 50KB)
                if len(content) > 50000:
                    content = content[:50000] + "\n\n[CLAUDE.md truncated due to size]"
                return content
            except Exception:
                return None

    return None


def build_system_prompt_with_claude_md(
    base_prompt: str,
    project_root: Optional[Path] = None,
) -> str:
    """
    Build a system prompt that includes CLAUDE.md content if available.

    The CLAUDE.md content is prepended to the base prompt with a clear header.

    Args:
        base_prompt: The base system prompt for the agent
        project_root: Project root directory to look for CLAUDE.md

    Returns:
        Combined system prompt with CLAUDE.md content (if found)
    """
    claude_md_content = read_claude_md(project_root)

    if claude_md_content:
        return f"""# Project Instructions (from CLAUDE.md)

{claude_md_content}

---

# Agent Instructions

{base_prompt}"""
    else:
        return base_prompt


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
        include_claude_md: bool = True,
        effort: Optional[str] = None,
        thinking: Optional[Union[str, int]] = None,
        on_notification: Optional[Callable[[Dict[str, Any]], None]] = None,
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
            include_claude_md: Whether to include CLAUDE.md in system prompt (default: True)
            effort: Effort level ("low", "medium", "high", "max")
            thinking: Thinking config ("adaptive", "disabled", or int for budget_tokens)
            on_notification: Optional callback for SDK notification events
        """
        # Build system prompt with CLAUDE.md if enabled
        effective_cwd = cwd or Path.cwd()
        if include_claude_md:
            self.system_prompt = build_system_prompt_with_claude_md(system_prompt, effective_cwd)
        else:
            self.system_prompt = system_prompt
        self.allowed_tools = allowed_tools if allowed_tools is not None else DEFAULT_TOOLS
        self.model = model
        self.session_id = session_id
        self.hooks = hooks
        self.cwd = cwd or Path.cwd()
        self.mcp_servers = mcp_servers
        self.on_token_usage = on_token_usage
        self.effort = effort
        self.thinking = thinking
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

        # Stop reason tracking (SDK 0.1.46+)
        self._last_stop_reason: Optional[str] = None

        # Tool failure tracking (SDK 0.1.26+)
        self._tool_failures: List[Dict[str, Any]] = []

        # Notification tracking (SDK 0.1.29+)
        self._notifications: List[Dict[str, Any]] = []
        self.on_notification = on_notification

        # Tool event callback (PostToolUse success hook, SDK 0.1.29+)
        self.on_tool_event: Optional[Callable[[str, Dict[str, Any], Any], None]] = None

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

            # Add effort if configured (SDK 0.1.46+)
            if self.effort:
                options_kwargs["effort"] = self.effort

            # Add thinking config if configured (SDK 0.1.46+)
            if self.thinking is not None:
                options_kwargs["thinking"] = self._resolve_thinking_config()

            # Set up hooks (SDK 0.1.26+)
            hooks = self._build_hooks()
            if hooks:
                options_kwargs["hooks"] = hooks

            self._options = ClaudeAgentOptions(**options_kwargs)
        return self._options

    def _resolve_thinking_config(self):
        """Resolve thinking parameter to SDK ThinkingConfig object."""
        if isinstance(self.thinking, int):
            return ThinkingConfigEnabled(type="enabled", budget_tokens=self.thinking)
        if isinstance(self.thinking, str):
            if self.thinking == "adaptive":
                return ThinkingConfigAdaptive(type="adaptive")
            elif self.thinking == "disabled":
                return ThinkingConfigDisabled(type="disabled")
            else:
                try:
                    return ThinkingConfigEnabled(type="enabled", budget_tokens=int(self.thinking))
                except ValueError:
                    raise ValueError(f"Invalid thinking config: {self.thinking}")
        return None

    def _build_hooks(self) -> Optional[Dict[str, Any]]:
        """Build hooks configuration for ClaudeAgentOptions."""
        hooks: Dict[str, Any] = {}

        hooks["PostToolUseFailure"] = [
            HookMatcher(matcher="*", hooks=[self._on_tool_failure])
        ]

        hooks["Notification"] = [
            HookMatcher(matcher="*", hooks=[self._on_notification])
        ]

        if self.on_tool_event is not None:
            hooks["PostToolUse"] = [
                HookMatcher(matcher="*", hooks=[self._on_tool_use])
            ]

        # Merge user-provided hooks if any
        if self.hooks:
            for event, matchers in self.hooks.items():
                if event in hooks:
                    hooks[event].extend(matchers)
                else:
                    hooks[event] = matchers

        return hooks

    async def _on_tool_failure(self, input_data, tool_use_id, context):
        """Handle PostToolUseFailure hook events."""
        tool_name = getattr(input_data, "tool_name", "unknown") if not isinstance(input_data, dict) else input_data.get("tool_name", "unknown")
        error = getattr(input_data, "error", "") if not isinstance(input_data, dict) else input_data.get("error", "")
        self._tool_failures.append({
            "tool_name": tool_name,
            "error": error,
            "timestamp": time.time(),
        })
        logger.warning("Tool failure: %s — %s", tool_name, error)
        return {}

    async def _on_tool_use(self, input_data, tool_use_id, context):
        """Handle PostToolUse success hook events."""
        tool_name = getattr(input_data, "tool_name", "unknown") if not isinstance(input_data, dict) else input_data.get("tool_name", "unknown")
        tool_input = getattr(input_data, "tool_input", {}) if not isinstance(input_data, dict) else input_data.get("tool_input", {})
        tool_response = getattr(input_data, "tool_response", None) if not isinstance(input_data, dict) else input_data.get("tool_response", None)
        if self.on_tool_event:
            self.on_tool_event(tool_name, tool_input, tool_response)
        return {}

    async def _on_notification(self, input_data, tool_use_id, context):
        """Handle Notification hook events."""
        message = getattr(input_data, "message", "") if not isinstance(input_data, dict) else input_data.get("message", "")
        ntype = getattr(input_data, "type", "info") if not isinstance(input_data, dict) else input_data.get("type", "info")
        notification = {
            "message": message,
            "type": ntype,
            "timestamp": time.time(),
        }
        self._notifications.append(notification)
        if self.on_notification:
            self.on_notification(notification)
        return {}

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
                # Capture stop reason (SDK 0.1.46+)
                if hasattr(message, 'stop_reason'):
                    self._last_stop_reason = message.stop_reason
                    if message.stop_reason == "max_tokens":
                        logger.warning("Agent response truncated (stop_reason=max_tokens)")
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

    # ─────────────────────────────────────────────────────────────────────────
    # Stop Reason Tracking (SDK 0.1.46+)
    # ─────────────────────────────────────────────────────────────────────────

    def get_last_stop_reason(self) -> Optional[str]:
        """
        Get the stop reason from the most recent agent response.

        Returns:
            Stop reason string (e.g. "end_turn", "max_tokens"), or None
        """
        return self._last_stop_reason

    # ─────────────────────────────────────────────────────────────────────────
    # Tool Failure Tracking (SDK 0.1.26+)
    # ─────────────────────────────────────────────────────────────────────────

    def get_tool_failures(self) -> List[Dict[str, Any]]:
        """
        Get all tool failures captured during this agent's session.

        Returns:
            List of tool failure dicts with tool_name, error, timestamp
        """
        return self._tool_failures.copy()

    def clear_tool_failures(self) -> None:
        """Clear the tool failure history."""
        self._tool_failures.clear()

    # ─────────────────────────────────────────────────────────────────────────
    # Notification Tracking (SDK 0.1.29+)
    # ─────────────────────────────────────────────────────────────────────────

    def get_notifications(self) -> List[Dict[str, Any]]:
        """
        Get all notifications captured during this agent's session.

        Returns:
            List of notification dicts with message, type, timestamp
        """
        return self._notifications.copy()

    def clear_notifications(self) -> None:
        """Clear the notification history."""
        self._notifications.clear()


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
    effort: Optional[str] = None,
    thinking: Optional[Union[str, int]] = None,
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
        effort: Effort level ("low", "medium", "high", "max")
        thinking: Thinking config ("adaptive", "disabled", or int for budget_tokens)

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
    if effort:
        kwargs["effort"] = effort
    if thinking is not None:
        kwargs["thinking"] = thinking

    return PlannerAgent(**kwargs)


def create_executor_agent(
    model: Optional[str] = None,
    session_id: str = "executor",
    hooks: Optional[Dict[str, Any]] = None,
    cwd: Optional[Path] = None,
    mcp_servers: Optional[Union[McpServersConfig, str]] = None,
    allowed_tools: Optional[List[str]] = None,
    on_token_usage: Optional[Callable[[Dict[str, Any]], None]] = None,
    effort: Optional[str] = None,
    thinking: Optional[Union[str, int]] = None,
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
        effort: Effort level ("low", "medium", "high", "max")
        thinking: Thinking config ("adaptive", "disabled", or int for budget_tokens)

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
    if effort:
        kwargs["effort"] = effort
    if thinking is not None:
        kwargs["thinking"] = thinking

    return ExecutorAgent(**kwargs)


def create_planner_chat_agent(
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    session_id: str = "planner-chat",
    allowed_tools: Optional[List[str]] = None,
    on_token_usage: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_notification: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_tool_event: Optional[Callable[[str, Dict[str, Any], Any], None]] = None,
    cwd: Optional[Path] = None,
) -> BaseAgent:
    """
    Create a freeform chat agent using the planner-chat prompt.

    Uses Opus by default (via get_planner_model). Unlike create_planner_agent(),
    this uses PLANNER_CHAT_PROMPT which has no workflow phases or response tags.

    Args:
        model: Model alias or full ID (default: opus via get_planner_model)
        system_prompt: Custom system prompt (default: PLANNER_CHAT_PROMPT)
        session_id: Session ID for the agent
        allowed_tools: Tool list. None = DEFAULT_TOOLS, [] = no tools
        on_token_usage: Optional callback for token usage reporting
        on_notification: Optional callback for SDK notification events
        on_tool_event: Optional callback for PostToolUse success events (tool_name, tool_input, tool_response)
        cwd: Working directory

    Returns:
        BaseAgent instance configured for freeform chat
    """
    from .prompts import PLANNER_CHAT_PROMPT
    from .config import get_planner_model

    resolved_model = get_planner_model(model)
    prompt = system_prompt or PLANNER_CHAT_PROMPT

    agent = BaseAgent(
        system_prompt=prompt,
        allowed_tools=allowed_tools,
        model=resolved_model,
        session_id=session_id,
        on_token_usage=on_token_usage,
        on_notification=on_notification,
        cwd=cwd,
    )
    agent.on_tool_event = on_tool_event
    return agent


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
