"""
Agent wrappers for Claude SDK integration.

Provides PlannerAgent and ExecutorAgent classes that wrap the Claude SDK Client
with appropriate system prompts and tool permissions.
"""

import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path
from claude_agent_sdk import query, ClaudeSDKClient
from claude_agent_sdk.types import (
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

from .prompts import PLANNER_SYSTEM_PROMPT, EXECUTOR_SYSTEM_PROMPT


# Tool permissions for both agents (list of tool names)
DEFAULT_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
]


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
        """
        self.system_prompt = system_prompt
        self.allowed_tools = allowed_tools or DEFAULT_TOOLS
        self.model = model
        self.session_id = session_id
        self.hooks = hooks
        self.cwd = cwd or Path.cwd()
        self._options: Optional[ClaudeAgentOptions] = None

    def _get_options(self) -> ClaudeAgentOptions:
        """Get or create agent options."""
        if self._options is None:
            self._options = ClaudeAgentOptions(
                system_prompt=self.system_prompt,
                tools=self.allowed_tools,
                model=self.model,
                cwd=self.cwd,
            )
        return self._options

    async def send_message_async(self, content: str) -> str:
        """
        Send a message to the agent and get response (async).

        Args:
            content: Message content to send

        Returns:
            String response from agent
        """
        options = self._get_options()
        response_text = ""
        result_message = None

        async for message in query(prompt=content, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text
            elif isinstance(message, ResultMessage):
                result_message = message

        return response_text

    def send_message(self, content: str) -> str:
        """
        Send a message to the agent and get response (sync wrapper).

        Args:
            content: Message content to send

        Returns:
            String response from agent
        """
        return asyncio.run(self.send_message_async(content))

    def get_session_id(self) -> str:
        """Get the current session ID."""
        return self.session_id

    def close(self) -> None:
        """Close the agent session (no-op for query-based approach)."""
        pass


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
        **kwargs
    ):
        """
        Initialize the Planner agent.

        Args:
            model: Claude model to use (default: Opus for planning)
            session_id: Session ID for the agent
            **kwargs: Additional arguments for BaseAgent
        """
        super().__init__(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            model=model,
            session_id=session_id,
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
        **kwargs
    ):
        """
        Initialize the Executor agent.

        Args:
            model: Claude model to use (default: Sonnet for execution)
            session_id: Session ID for the agent
            **kwargs: Additional arguments for BaseAgent
        """
        super().__init__(
            system_prompt=EXECUTOR_SYSTEM_PROMPT,
            model=model,
            session_id=session_id,
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
) -> PlannerAgent:
    """
    Factory function to create a Planner agent.

    Args:
        model: Claude model to use (default: Opus)
        session_id: Session ID for the agent
        hooks: Optional hooks configuration
        cwd: Working directory

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

    return PlannerAgent(**kwargs)


def create_executor_agent(
    model: Optional[str] = None,
    session_id: str = "executor",
    hooks: Optional[Dict[str, Any]] = None,
    cwd: Optional[Path] = None,
) -> ExecutorAgent:
    """
    Factory function to create an Executor agent.

    Args:
        model: Claude model to use (default: Sonnet)
        session_id: Session ID for the agent
        hooks: Optional hooks configuration
        cwd: Working directory

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

    return ExecutorAgent(**kwargs)
