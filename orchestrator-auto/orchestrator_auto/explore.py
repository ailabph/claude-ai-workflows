"""
Exploration sub-agent for codebase discovery before milestone execution.

Provides ExploreSubAgent that spawns read-only sub-agents with Glob/Grep/Read tools
to gather context before implementation. Returns structured findings (file paths,
patterns, snippets) with light compaction.

This is distinct from Research agents (Phase 2) which perform full summarization.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import (
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)


# Read-only tools for exploration
EXPLORE_TOOLS = ["Glob", "Grep", "Read"]

# Default governance limits
DEFAULT_MAX_TOKENS = 25_000
DEFAULT_MAX_TURNS = 5
DEFAULT_TIMEOUT = 30.0  # seconds


EXPLORATION_SYSTEM_PROMPT = """You are an exploration agent focused on quickly gathering codebase context.

## Your Role
You perform read-only exploration to find:
- Existing implementations of similar functionality
- Naming conventions and patterns
- File structure and organization
- Test patterns and locations

## Constraints
- You can ONLY use read-only tools: Glob, Grep, Read
- You cannot modify any files
- Focus on patterns and locations, not implementation details
- Be efficient - find what's needed quickly

## Output Format
When you've gathered sufficient context, output your findings in this format:

[EXPLORATION_COMPLETE]
### Files Found
- path/to/file.py - brief description

### Patterns Identified
- Pattern name: description

### Key Snippets
```language
// relevant code snippet
```

### Recommendations
- What to follow/use for implementation
[/EXPLORATION_COMPLETE]

If you cannot find what was requested or hit limits, output:

[EXPLORATION_PARTIAL]
### Found So Far
- what was found

### Not Found
- what couldn't be located
[/EXPLORATION_PARTIAL]
"""


@dataclass
class ExplorationResult:
    """Result from exploration sub-agent."""

    query: str
    findings: str  # Structured findings text
    sources_consulted: List[str] = field(default_factory=list)
    tokens_used: int = 0
    duration_ms: int = 0
    is_partial: bool = False
    error: Optional[str] = None

    def is_success(self) -> bool:
        """Check if exploration completed successfully."""
        return self.error is None and bool(self.findings)


class ExplorationError(Exception):
    """Exception raised when exploration fails."""

    def __init__(
        self,
        query: str,
        cause: Exception,
        partial_results: Optional[str] = None
    ):
        self.query = query
        self.cause = cause
        self.partial_results = partial_results
        super().__init__(f"Exploration failed for '{query}': {cause}")


class ExploreSubAgent:
    """
    Sub-agent for read-only codebase exploration.

    Spawns isolated sub-agents that can only use Glob, Grep, and Read tools
    to gather context before milestone execution. Returns structured findings
    with light compaction (not full summarization like Research agents).
    """

    def __init__(
        self,
        model: str = "claude-3-5-haiku-20241022",  # Cost-effective for exploration
        cwd: Optional[Path] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_turns: int = DEFAULT_MAX_TURNS,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the exploration sub-agent.

        Args:
            model: Claude model to use (default: Haiku for cost efficiency)
            cwd: Working directory for exploration
            max_tokens: Maximum tokens per exploration (governance limit)
            max_turns: Maximum turns per exploration (governance limit)
            timeout: Timeout in seconds (governance limit)
        """
        self.model = model
        self.cwd = cwd or Path.cwd()
        self.max_tokens = max_tokens
        self.max_turns = max_turns
        self.timeout = timeout

    async def explore_async(
        self,
        query: str,
        scope: Optional[str] = None,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> ExplorationResult:
        """
        Perform exploration for a given query (async).

        Args:
            query: What to explore (e.g., "Find existing auth implementations")
            scope: Optional directory scope (e.g., "src/auth/")
            on_progress: Optional callback for progress updates

        Returns:
            ExplorationResult with structured findings
        """
        import time
        start_time = time.time()

        # Build exploration prompt
        prompt = self._build_prompt(query, scope)

        # Create isolated client for this exploration
        options = ClaudeAgentOptions(
            system_prompt=EXPLORATION_SYSTEM_PROMPT,
            tools=EXPLORE_TOOLS,
            model=self.model,
            cwd=self.cwd,
            permission_mode="bypassPermissions",
            max_tokens=self.max_tokens,
        )

        findings = ""
        sources: List[str] = []
        tokens_used = 0
        is_partial = False
        error = None
        turns = 0

        try:
            async with ClaudeSDKClient(options) as client:
                # Apply timeout
                try:
                    await asyncio.wait_for(
                        self._run_exploration(
                            client, prompt, on_progress,
                            lambda s: sources.append(s),
                            lambda t: None,  # Token tracking handled in result
                        ),
                        timeout=self.timeout
                    )
                except asyncio.TimeoutError:
                    is_partial = True
                    if on_progress:
                        on_progress("[Exploration timeout - returning partial results]")

                # Extract response
                findings, tokens_used, turns = await self._extract_response(
                    client, prompt
                )

                # Check if we hit turn limit
                if turns >= self.max_turns:
                    is_partial = True

        except Exception as e:
            error = str(e)
            # Don't raise - return result with error

        duration_ms = int((time.time() - start_time) * 1000)

        return ExplorationResult(
            query=query,
            findings=findings,
            sources_consulted=sources,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            is_partial=is_partial,
            error=error,
        )

    def explore(
        self,
        query: str,
        scope: Optional[str] = None,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> ExplorationResult:
        """
        Perform exploration for a given query (sync wrapper).

        Args:
            query: What to explore
            scope: Optional directory scope
            on_progress: Optional callback for progress updates

        Returns:
            ExplorationResult with structured findings
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.explore_async(query, scope, on_progress)
            )
        finally:
            loop.close()

    async def explore_multiple_async(
        self,
        queries: List[str],
        scope: Optional[str] = None,
    ) -> List[ExplorationResult]:
        """
        Explore multiple queries sequentially (Phase 1: no parallel).

        Args:
            queries: List of exploration queries
            scope: Optional directory scope

        Returns:
            List of ExplorationResult for each query
        """
        results = []
        for query in queries:
            result = await self.explore_async(query, scope)
            results.append(result)
        return results

    def _build_prompt(self, query: str, scope: Optional[str] = None) -> str:
        """Build the exploration prompt."""
        prompt = f"Explore the codebase to find: {query}"
        if scope:
            prompt += f"\n\nFocus on the directory: {scope}"
        prompt += "\n\nProvide structured findings using the [EXPLORATION_COMPLETE] format."
        return prompt

    async def _run_exploration(
        self,
        client: ClaudeSDKClient,
        prompt: str,
        on_progress: Optional[Callable[[str], None]],
        on_source: Callable[[str], None],
        on_tokens: Callable[[int], None],
    ) -> None:
        """Run the exploration query."""
        await client.query(prompt)

        turns = 0
        async for message in client.receive_messages():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        if on_progress:
                            on_progress(block.text[:100])
            elif isinstance(message, ResultMessage):
                # Capture token usage
                if message.usage:
                    on_tokens(message.usage.get("output_tokens", 0))
                break

            turns += 1
            if turns >= self.max_turns:
                break

    async def _extract_response(
        self,
        client: ClaudeSDKClient,
        prompt: str,
    ) -> tuple:
        """
        Extract response from a fresh query.

        Returns:
            Tuple of (findings_text, tokens_used, turns)
        """
        findings = ""
        tokens_used = 0
        turns = 0

        await client.query(prompt)

        async for message in client.receive_messages():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        findings += block.text
            elif isinstance(message, ResultMessage):
                if message.usage:
                    tokens_used = (
                        message.usage.get("input_tokens", 0) +
                        message.usage.get("output_tokens", 0)
                    )
                break

            turns += 1
            if turns >= self.max_turns:
                break

        return findings, tokens_used, turns


def compact_findings(results: List[ExplorationResult]) -> str:
    """
    Compact multiple exploration results into a single context string.

    This performs light compaction (formatting, deduplication) rather than
    full summarization. The output is suitable for injecting into executor
    context.

    Args:
        results: List of ExplorationResult objects

    Returns:
        Compacted findings string
    """
    if not results:
        return ""

    sections = []
    sections.append("## Exploration Context\n")

    for result in results:
        if result.is_success():
            sections.append(f"### Query: {result.query}")
            sections.append(result.findings)
            if result.is_partial:
                sections.append("_(partial results due to limits)_")
            sections.append("")
        else:
            sections.append(f"### Query: {result.query}")
            sections.append(f"_Exploration failed: {result.error}_")
            sections.append("")

    return "\n".join(sections)


def generate_exploration_queries(milestone: str) -> List[str]:
    """
    Auto-generate exploration queries from milestone text.

    Analyzes the milestone description to identify what context would be
    helpful before implementation.

    Args:
        milestone: Milestone description text

    Returns:
        List of exploration queries
    """
    queries = []
    milestone_lower = milestone.lower()

    # Pattern matching for common exploration needs
    patterns = [
        # Existing implementations
        ("implement", "Find existing implementations of similar functionality"),
        ("add", "Find existing patterns for adding new features"),
        ("create", "Find existing patterns for creating similar components"),

        # API/Endpoint patterns
        ("endpoint", "Find existing API endpoint implementations"),
        ("route", "Find existing route patterns"),
        ("controller", "Find existing controller implementations"),

        # Database patterns
        ("model", "Find existing model definitions"),
        ("migration", "Find existing migration patterns"),
        ("database", "Find database access patterns"),

        # Test patterns
        ("test", "Find existing test patterns and fixtures"),

        # Auth patterns
        ("auth", "Find existing authentication patterns"),
        ("permission", "Find existing permission/authorization patterns"),
    ]

    for keyword, query in patterns:
        if keyword in milestone_lower:
            queries.append(query)

    # Always add general structure query if we have specific queries
    if queries:
        # Deduplicate while preserving order
        seen = set()
        queries = [q for q in queries if not (q in seen or seen.add(q))]

    # If no patterns matched, add a generic query
    if not queries:
        queries.append("Find relevant files and patterns for: " + milestone[:100])

    # Limit to 3 queries to control costs
    return queries[:3]
