"""Tests for exploration sub-agent module."""

import pytest
from pathlib import Path

from orchestrator_auto.explore import (
    ExploreSubAgent,
    ExplorationResult,
    ExplorationError,
    compact_findings,
    generate_exploration_queries,
    EXPLORE_TOOLS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MAX_TURNS,
    DEFAULT_TIMEOUT,
)


class TestExplorationResult:
    """Tests for ExplorationResult dataclass."""

    def test_default_values(self):
        result = ExplorationResult(query="test query", findings="some findings")
        assert result.query == "test query"
        assert result.findings == "some findings"
        assert result.sources_consulted == []
        assert result.tokens_used == 0
        assert result.duration_ms == 0
        assert result.is_partial is False
        assert result.error is None

    def test_is_success_true(self):
        result = ExplorationResult(query="test", findings="found it")
        assert result.is_success() is True

    def test_is_success_false_with_error(self):
        result = ExplorationResult(query="test", findings="", error="timeout")
        assert result.is_success() is False

    def test_is_success_false_with_empty_findings(self):
        result = ExplorationResult(query="test", findings="")
        assert result.is_success() is False


class TestExplorationError:
    """Tests for ExplorationError exception."""

    def test_error_attributes(self):
        cause = ValueError("original error")
        error = ExplorationError("my query", cause, "partial data")
        assert error.query == "my query"
        assert error.cause == cause
        assert error.partial_results == "partial data"

    def test_error_message(self):
        cause = ValueError("original")
        error = ExplorationError("find auth", cause)
        assert "find auth" in str(error)
        assert "original" in str(error)


class TestExploreSubAgent:
    """Tests for ExploreSubAgent class."""

    def test_default_initialization(self):
        agent = ExploreSubAgent()
        assert agent.model == "claude-sonnet-4-5-20250929"
        assert agent.cwd == Path.cwd()
        assert agent.max_tokens == DEFAULT_MAX_TOKENS
        assert agent.max_turns == DEFAULT_MAX_TURNS
        assert agent.timeout == DEFAULT_TIMEOUT

    def test_custom_initialization(self):
        cwd = Path("/tmp")
        agent = ExploreSubAgent(
            model="claude-sonnet-4-5-20250929",
            cwd=cwd,
            max_tokens=10000,
            max_turns=3,
            timeout=15.0,
        )
        assert agent.model == "claude-sonnet-4-5-20250929"
        assert agent.cwd == cwd
        assert agent.max_tokens == 10000
        assert agent.max_turns == 3
        assert agent.timeout == 15.0

    def test_build_prompt_basic(self):
        agent = ExploreSubAgent()
        prompt = agent._build_prompt("Find auth patterns")
        assert "Find auth patterns" in prompt
        assert "EXPLORATION_COMPLETE" in prompt

    def test_build_prompt_with_scope(self):
        agent = ExploreSubAgent()
        prompt = agent._build_prompt("Find models", scope="src/models/")
        assert "Find models" in prompt
        assert "src/models/" in prompt


class TestExploreTools:
    """Tests for exploration tools configuration."""

    def test_explore_tools_are_read_only(self):
        assert "Glob" in EXPLORE_TOOLS
        assert "Grep" in EXPLORE_TOOLS
        assert "Read" in EXPLORE_TOOLS
        # Should NOT have write tools
        assert "Write" not in EXPLORE_TOOLS
        assert "Edit" not in EXPLORE_TOOLS
        assert "Bash" not in EXPLORE_TOOLS


class TestCompactFindings:
    """Tests for compact_findings function."""

    def test_empty_results(self):
        assert compact_findings([]) == ""

    def test_single_result(self):
        result = ExplorationResult(
            query="find auth",
            findings="Found auth.py",
        )
        output = compact_findings([result])
        assert "Exploration Context" in output
        assert "find auth" in output
        assert "Found auth.py" in output

    def test_partial_result(self):
        result = ExplorationResult(
            query="find all",
            findings="Partial data",
            is_partial=True,
        )
        output = compact_findings([result])
        assert "partial results" in output.lower()

    def test_failed_result(self):
        result = ExplorationResult(
            query="find broken",
            findings="",
            error="Connection timeout",
        )
        output = compact_findings([result])
        assert "failed" in output.lower()
        assert "Connection timeout" in output

    def test_multiple_results(self):
        results = [
            ExplorationResult(query="find A", findings="Found A"),
            ExplorationResult(query="find B", findings="Found B"),
        ]
        output = compact_findings(results)
        assert "find A" in output
        assert "find B" in output
        assert "Found A" in output
        assert "Found B" in output


class TestGenerateExplorationQueries:
    """Tests for generate_exploration_queries function."""

    def test_implement_keyword(self):
        queries = generate_exploration_queries("Implement user authentication")
        assert len(queries) > 0
        assert any("implement" in q.lower() or "similar" in q.lower() for q in queries)

    def test_endpoint_keyword(self):
        queries = generate_exploration_queries("Add new API endpoint for users")
        assert any("endpoint" in q.lower() for q in queries)

    def test_model_keyword(self):
        queries = generate_exploration_queries("Create User model with validation")
        assert any("model" in q.lower() for q in queries)

    def test_test_keyword(self):
        queries = generate_exploration_queries("Write tests for auth module")
        assert any("test" in q.lower() for q in queries)

    def test_auth_keyword(self):
        queries = generate_exploration_queries("Update authentication flow")
        assert any("auth" in q.lower() for q in queries)

    def test_no_keywords_fallback(self):
        queries = generate_exploration_queries("Do something random")
        assert len(queries) >= 1
        # Should have generic query
        assert any("Do something" in q for q in queries)

    def test_max_queries_limit(self):
        # Even with many keywords, should limit to 3
        queries = generate_exploration_queries(
            "Implement auth endpoint model test migration"
        )
        assert len(queries) <= 3

    def test_deduplication(self):
        # Auth appears twice, should not duplicate
        queries = generate_exploration_queries("auth authentication authorization")
        # Should not have exact duplicates
        assert len(queries) == len(set(queries))
