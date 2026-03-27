"""Tests for planner_auto.agents — discuss, synthesize_context, generate_plan."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from planner_auto.agents import discuss, generate_plan, synthesize_context
from planner_auto.db import (
    add_context_entry,
    add_message,
    create_session,
    get_all_plan_drafts,
    get_context_entries,
    get_messages,
    get_session_config,
    update_session_phase,
)
from planner_auto.errors import SDKResponseError


@pytest.fixture
def session_in_discussion(db_conn):
    """Create a session in DISCUSSION phase."""
    sid = create_session(db_conn, "myapp")
    update_session_phase(db_conn, sid, "CONTEXT")
    update_session_phase(db_conn, sid, "DISCUSSION")
    db_conn.commit()
    return sid


@pytest.fixture
def session_in_planning(db_conn):
    """Create a session in PLANNING phase with some context."""
    sid = create_session(db_conn, "myapp")
    update_session_phase(db_conn, sid, "CONTEXT")
    update_session_phase(db_conn, sid, "DISCUSSION")
    update_session_phase(db_conn, sid, "PLANNING")
    # Add some context
    add_context_entry(db_conn, sid, "readme.md", "file", "# My Project")
    add_context_entry(db_conn, sid, "note-1", "note", "Use PostgreSQL")
    add_message(db_conn, sid, "user", "Build a user auth system")
    add_message(db_conn, sid, "assistant", "Got it, I'll plan user auth.")
    db_conn.commit()
    return sid


@pytest.mark.asyncio
class TestDiscuss:
    """Tests for discuss()."""

    @patch("planner_auto.agents.query_claude", new_callable=AsyncMock)
    async def test_commits_both_messages_on_success(self, mock_query, db_conn, session_in_discussion):
        mock_query.return_value = "Sure, tell me more about the feature."
        sid = session_in_discussion

        response = await discuss(sid, "I want to build auth", db_conn)
        assert response == "Sure, tell me more about the feature."

        msgs = get_messages(db_conn, sid)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "I want to build auth"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "Sure, tell me more about the feature."

    @patch("planner_auto.agents.query_claude", new_callable=AsyncMock)
    async def test_commits_nothing_on_sdk_failure(self, mock_query, db_conn, session_in_discussion):
        mock_query.side_effect = SDKResponseError("Connection failed")
        sid = session_in_discussion

        with pytest.raises(SDKResponseError):
            await discuss(sid, "I want to build auth", db_conn)

        # Nothing should be committed
        msgs = get_messages(db_conn, sid)
        assert len(msgs) == 0

    @patch("planner_auto.agents.query_claude", new_callable=AsyncMock)
    async def test_includes_message_history(self, mock_query, db_conn, session_in_discussion):
        """Messages from prior turns should be included in SDK call."""
        mock_query.return_value = "Response 2"
        sid = session_in_discussion

        # Add prior messages
        add_message(db_conn, sid, "user", "First message")
        add_message(db_conn, sid, "assistant", "First response")
        db_conn.commit()

        await discuss(sid, "Second message", db_conn)

        # Check that query_claude was called with all messages
        call_args = mock_query.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 3  # 2 prior + 1 new
        assert messages[0]["content"] == "First message"
        assert messages[1]["content"] == "First response"
        assert messages[2]["content"] == "Second message"


@pytest.mark.asyncio
class TestSynthesizeContext:
    """Tests for synthesize_context()."""

    @patch("planner_auto.agents.query_claude", new_callable=AsyncMock)
    async def test_stores_synthesis_on_success(self, mock_query, db_conn, session_in_planning):
        mock_query.return_value = "Synthesis: user wants auth with PostgreSQL."
        sid = session_in_planning

        result = await synthesize_context(sid, db_conn)
        assert "Synthesis" in result

        syntheses = get_context_entries(db_conn, sid, entry_type="synthesis")
        assert len(syntheses) == 1
        assert syntheses[0]["entry_key"].startswith("synthesis-")
        assert syntheses[0]["content"] == "Synthesis: user wants auth with PostgreSQL."

    @patch("planner_auto.agents.query_claude", new_callable=AsyncMock)
    async def test_stores_nothing_on_failure(self, mock_query, db_conn, session_in_planning):
        mock_query.side_effect = SDKResponseError("Failed")
        sid = session_in_planning

        with pytest.raises(SDKResponseError):
            await synthesize_context(sid, db_conn)

        syntheses = get_context_entries(db_conn, sid, entry_type="synthesis")
        assert len(syntheses) == 0

    @patch("planner_auto.agents.query_claude", new_callable=AsyncMock)
    async def test_syntheses_accumulate(self, mock_query, db_conn, session_in_planning):
        """Multiple syntheses should accumulate (no UPSERT)."""
        mock_query.return_value = "Synthesis v1"
        sid = session_in_planning

        await synthesize_context(sid, db_conn)

        mock_query.return_value = "Synthesis v2"
        await synthesize_context(sid, db_conn)

        syntheses = get_context_entries(db_conn, sid, entry_type="synthesis")
        assert len(syntheses) == 2


@pytest.mark.asyncio
class TestGeneratePlan:
    """Tests for generate_plan()."""

    @patch("planner_auto.agents.query_claude", new_callable=AsyncMock)
    async def test_stores_draft_and_config_on_success(self, mock_query, db_conn, session_in_planning):
        # First call is synthesize_context, second is plan generation
        mock_query.side_effect = ["Context synthesis", "## Milestone 1: Setup\n### Tasks\n- [ ] task"]
        sid = session_in_planning

        plan = await generate_plan(sid, db_conn, model="claude-sonnet-4-6")
        assert "Milestone 1" in plan

        drafts = get_all_plan_drafts(db_conn, sid)
        assert len(drafts) == 1
        assert drafts[0]["draft_number"] == 1
        assert drafts[0]["model"] == "claude-sonnet-4-6"
        assert drafts[0]["config_snapshot_id"] is not None

        # Verify config snapshot
        cfg = get_session_config(db_conn, sid)
        data = json.loads(cfg["config_json"])
        assert data["model"] == "claude-sonnet-4-6"
        assert "planner" in data["prompt_hashes"]
        assert "synthesis" in data["prompt_hashes"]
        assert data["feature_description"] == "Build a user auth system"

    @patch("planner_auto.agents.query_claude", new_callable=AsyncMock)
    async def test_stores_nothing_on_plan_failure(self, mock_query, db_conn, session_in_planning):
        # Synthesis succeeds, plan generation fails
        mock_query.side_effect = ["Context synthesis", SDKResponseError("Plan gen failed")]
        sid = session_in_planning

        with pytest.raises(SDKResponseError):
            await generate_plan(sid, db_conn)

        drafts = get_all_plan_drafts(db_conn, sid)
        assert len(drafts) == 0

    @patch("planner_auto.agents.query_claude", new_callable=AsyncMock)
    async def test_draft_number_increments(self, mock_query, db_conn, session_in_planning):
        sid = session_in_planning

        mock_query.side_effect = ["Synthesis 1", "Plan v1"]
        await generate_plan(sid, db_conn)

        mock_query.side_effect = ["Synthesis 2", "Plan v2"]
        await generate_plan(sid, db_conn)

        drafts = get_all_plan_drafts(db_conn, sid)
        assert len(drafts) == 2
        assert drafts[0]["draft_number"] == 1
        assert drafts[1]["draft_number"] == 2
        assert drafts[0]["content"] == "Plan v1"
        assert drafts[1]["content"] == "Plan v2"

    @patch("planner_auto.agents.query_claude", new_callable=AsyncMock)
    async def test_stores_nothing_on_synthesis_failure(self, mock_query, db_conn, session_in_planning):
        """If synthesis fails, no plan draft or config should be stored."""
        mock_query.side_effect = SDKResponseError("Synthesis failed")
        sid = session_in_planning

        with pytest.raises(SDKResponseError):
            await generate_plan(sid, db_conn)

        drafts = get_all_plan_drafts(db_conn, sid)
        assert len(drafts) == 0
        # Only the initial config from session setup should exist (none in test fixture)
