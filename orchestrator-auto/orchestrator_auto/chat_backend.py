"""
Callback-driven agent wrapper for the TUI chat path.

ChatBackend wraps create_planner_chat_agent() and exposes a simple
send()/reset() interface with callbacks for streaming chunks,
response completion, and notifications.
"""

import logging
from typing import Optional, Dict, Any, Callable, List

from .agents import create_planner_chat_agent, BaseAgent, DEFAULT_TOOLS

logger = logging.getLogger(__name__)


class ChatBackend:
    """Callback-driven agent wrapper for the TUI chat path."""

    def __init__(
        self,
        model: str = "opus",
        system_prompt: Optional[str] = None,
        tools_enabled: bool = True,
        on_chunk: Optional[Callable[[str], None]] = None,
        on_response_complete: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_notification: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_tool_event: Optional[Callable[[str, Dict[str, Any], Any], None]] = None,
    ) -> None:
        """
        Initialize the chat backend.

        Args:
            model: Model alias or full ID (resolved via get_planner_model)
            system_prompt: Custom system prompt (default: PLANNER_CHAT_PROMPT)
            tools_enabled: Whether to enable file/bash tools
            on_chunk: Callback fired for each text chunk during streaming
            on_response_complete: Callback fired with (full_text, usage_dict) after response
            on_notification: Callback fired on SDK notification events
            on_tool_event: Callback fired on PostToolUse success events (tool_name, tool_input, tool_response)
        """
        self.model = model
        self.system_prompt = system_prompt
        self.tools_enabled = tools_enabled
        self.on_chunk = on_chunk
        self.on_response_complete = on_response_complete
        self.on_notification = on_notification
        self.on_tool_event = on_tool_event

        self._agent: Optional[BaseAgent] = None
        self._usage: Dict[str, Any] = {}

    def _get_agent(self) -> BaseAgent:
        """Get or create the agent (lazy initialization)."""
        if self._agent is None:
            allowed_tools: Optional[List[str]] = None if self.tools_enabled else []
            # Use forwarding lambdas so callbacks resolve at call time,
            # allowing the TUI to swap adapters per-message.
            self._agent = create_planner_chat_agent(
                model=self.model,
                system_prompt=self.system_prompt,
                allowed_tools=allowed_tools,
                on_token_usage=self._on_token_usage,
                on_notification=lambda n: self.on_notification(n) if self.on_notification else None,
                on_tool_event=lambda name, inp, resp: self.on_tool_event(name, inp, resp) if self.on_tool_event else None,
            )
        return self._agent

    def _on_token_usage(self, usage: Dict[str, Any]) -> None:
        """Capture token usage from the agent."""
        self._usage = usage

    def send(
        self,
        content: str,
        on_chunk: Optional[Callable[[str], None]] = None,
        on_response_complete: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> str:
        """
        Send a message and return the full response.

        Fires on_chunk for each text chunk during streaming, then
        on_response_complete with the full text and usage dict.

        Args:
            content: User message text
            on_chunk: Per-request chunk callback (overrides instance attribute)
            on_response_complete: Per-request completion callback (overrides instance attribute)

        Returns:
            Full response text
        """
        agent = self._get_agent()
        self._usage = {}

        chunk_cb = on_chunk or self.on_chunk
        complete_cb = on_response_complete or self.on_response_complete

        response = agent.send_message(content, on_chunk=chunk_cb)

        if complete_cb:
            complete_cb(response, self._usage)

        return response

    def reset(self) -> None:
        """Destroy agent; next send() creates a fresh one (context cleared)."""
        if self._agent is not None:
            try:
                self._agent.close()
            except Exception:
                pass
            self._agent = None
