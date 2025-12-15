"""
Agent wrappers for Claude SDK integration.

Provides PlannerAgent and ExecutorAgent classes that wrap the Claude SDK Client
with appropriate system prompts and tool permissions.
"""

from typing import Optional, Dict, Any, List
from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import (
    ClaudeAgentOptions,
    ResultMessage,
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
    ):
        """
        Initialize the agent.

        Args:
            system_prompt: System prompt defining agent role and behavior
            allowed_tools: List of allowed tools (default: Read, Write, Edit, Bash, Glob, Grep)
            model: Claude model to use
            session_id: Session ID for the agent
            hooks: Optional hooks configuration
        """
        self.system_prompt = system_prompt
        self.allowed_tools = allowed_tools or DEFAULT_TOOLS
        self.model = model
        self.session_id = session_id
        self.hooks = hooks
        self._client: Optional[ClaudeSDKClient] = None

    def initialize(self) -> None:
        """Initialize the SDK client and start a session."""
        if self._client is not None:
            raise RuntimeError("Agent already initialized")

        # Create agent options
        options = ClaudeAgentOptions(
            system_prompt=self.system_prompt,
            allowed_tools=self.allowed_tools,
            model=self.model,
            hooks=self.hooks,
        )

        # Create SDK client
        self._client = ClaudeSDKClient(options=options)
        self._client.connect()

    @property
    def client(self) -> ClaudeSDKClient:
        """Get the SDK client, initializing if necessary."""
        if self._client is None:
            self.initialize()
        return self._client

    def send_message(self, content: str) -> ResultMessage:
        """
        Send a message to the agent and get response.

        Args:
            content: Message content to send

        Returns:
            ResultMessage with agent's response
        """
        # Send query and receive response
        self.client.query(content, session_id=self.session_id)
        result = self.client.receive_response(session_id=self.session_id)
        return result

    def get_session_id(self) -> str:
        """Get the current session ID."""
        return self.session_id

    def close(self) -> None:
        """Close the agent session."""
        if self._client is not None:
            self._client.disconnect()
            self._client = None


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

    def validate_milestone_report(self, report: str) -> ResultMessage:
        """
        Send a milestone report for validation.

        Args:
            report: Executor's progress report

        Returns:
            ResultMessage with planner's validation response
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

    def execute_milestone(self, milestone_prompt: str) -> ResultMessage:
        """
        Send a milestone prompt for execution.

        Args:
            milestone_prompt: Formatted milestone task prompt

        Returns:
            ResultMessage with executor's progress report
        """
        return self.send_message(milestone_prompt)

    def continue_milestone(self, feedback: str) -> ResultMessage:
        """
        Continue working on a milestone after receiving feedback.

        Args:
            feedback: Planner's feedback or approval to continue

        Returns:
            ResultMessage with executor's response
        """
        return self.send_message(feedback)


def create_planner_agent(
    model: Optional[str] = None,
    session_id: str = "planner",
    hooks: Optional[Dict[str, Any]] = None
) -> PlannerAgent:
    """
    Factory function to create a Planner agent.

    Args:
        model: Claude model to use (default: Opus)
        session_id: Session ID for the agent
        hooks: Optional hooks configuration

    Returns:
        Initialized PlannerAgent
    """
    kwargs = {"session_id": session_id}
    if model:
        kwargs["model"] = model
    if hooks:
        kwargs["hooks"] = hooks

    agent = PlannerAgent(**kwargs)
    agent.initialize()
    return agent


def create_executor_agent(
    model: Optional[str] = None,
    session_id: str = "executor",
    hooks: Optional[Dict[str, Any]] = None
) -> ExecutorAgent:
    """
    Factory function to create an Executor agent.

    Args:
        model: Claude model to use (default: Sonnet)
        session_id: Session ID for the agent
        hooks: Optional hooks configuration

    Returns:
        Initialized ExecutorAgent
    """
    kwargs = {"session_id": session_id}
    if model:
        kwargs["model"] = model
    if hooks:
        kwargs["hooks"] = hooks

    agent = ExecutorAgent(**kwargs)
    agent.initialize()
    return agent
