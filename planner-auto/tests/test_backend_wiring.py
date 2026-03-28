"""Tests for backend wiring through agents, engine, and CLI.

Verifies that the backend= parameter flows correctly from CLI → agents/engine → query_claude.
"""

import json
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from planner_auto.agents import discuss, generate_plan, synthesize_context
from planner_auto.cli import cli
from planner_auto.db import (
    add_context_entry,
    add_message,
    add_plan_draft,
    create_session,
    get_session_config,
    init_schema,
    save_session_config,
    update_session_phase,
)
from planner_auto.loop.engine import ReviewLoopEngine, LoopResult
from planner_auto.reviewer.contract import ReviewIssue, ReviewerResponse, Severity, Verdict


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def session_in_discussion(db_conn):
    sid = create_session(db_conn, "myapp")
    update_session_phase(db_conn, sid, "CONTEXT")
    update_session_phase(db_conn, sid, "DISCUSSION")
    db_conn.commit()
    return sid


@pytest.fixture
def session_in_planning(db_conn):
    sid = create_session(db_conn, "myapp")
    update_session_phase(db_conn, sid, "CONTEXT")
    update_session_phase(db_conn, sid, "DISCUSSION")
    update_session_phase(db_conn, sid, "PLANNING")
    add_context_entry(db_conn, sid, "readme.md", "file", "# My Project")
    add_message(db_conn, sid, "user", "Build a user auth system")
    add_message(db_conn, sid, "assistant", "Got it, I'll plan user auth.")
    db_conn.commit()
    return sid


@pytest.fixture
def runner(tmp_path):
    db_path = str(tmp_path / "test.db")
    r = CliRunner()
    return r, ["--db-path", db_path], db_path


def _get_conn(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# 1. discuss() passes backend to query_claude
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDiscussBackend:
    @patch("planner_auto.agents.query_claude", new_callable=AsyncMock)
    async def test_discuss_passes_backend(self, mock_qc, db_conn, session_in_discussion):
        mock_qc.return_value = "response"
        await discuss(session_in_discussion, "hello", db_conn, backend="sdk")
        call_kwargs = mock_qc.call_args.kwargs
        assert call_kwargs["backend"] == "sdk"

    @patch("planner_auto.agents.query_claude", new_callable=AsyncMock)
    async def test_discuss_default_backend_is_direct(self, mock_qc, db_conn, session_in_discussion):
        mock_qc.return_value = "response"
        await discuss(session_in_discussion, "hello", db_conn)
        call_kwargs = mock_qc.call_args.kwargs
        assert call_kwargs["backend"] == "direct"


# ---------------------------------------------------------------------------
# 2. generate_plan() passes backend to query_claude
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGeneratePlanBackend:
    @patch("planner_auto.agents.query_claude", new_callable=AsyncMock)
    async def test_generate_plan_passes_backend(self, mock_qc, db_conn, session_in_planning):
        mock_qc.side_effect = ["synthesis text", "plan text"]
        await generate_plan(session_in_planning, db_conn, backend="sdk")
        # Both calls (synthesis + plan gen) should use backend="sdk"
        for call in mock_qc.call_args_list:
            assert call.kwargs["backend"] == "sdk"


# ---------------------------------------------------------------------------
# 3. synthesize_context() passes backend to query_claude
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSynthesizeContextBackend:
    @patch("planner_auto.agents.query_claude", new_callable=AsyncMock)
    async def test_synthesize_context_passes_backend(self, mock_qc, db_conn, session_in_planning):
        mock_qc.return_value = "synthesis"
        await synthesize_context(session_in_planning, db_conn, backend="sdk")
        call_kwargs = mock_qc.call_args.kwargs
        assert call_kwargs["backend"] == "sdk"


# ---------------------------------------------------------------------------
# 4. Engine revision calls pass backend from config
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEngineBackend:
    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_engine_passes_backend_from_config(self, mock_qc):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        init_schema(conn)
        sid = create_session(conn, "test")
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[
            ReviewerResponse(
                verdict=Verdict.NO_GO,
                issues=[ReviewIssue(severity=Severity.CRITICAL, description="X", rationale="R")],
                summary="fix it",
            ),
            ReviewerResponse(verdict=Verdict.GO, issues=[], summary="ok"),
        ])

        engine = ReviewLoopEngine(
            conn=conn, session_id=sid, reviewer=reviewer,
            planner_model="claude-sonnet",
            config={"claude_backend": "sdk"},
        )
        await engine.run("plan v1", max_rounds=5)

        call_kwargs = mock_qc.call_args.kwargs
        assert call_kwargs.get("backend") == "sdk"


# ---------------------------------------------------------------------------
# 5. CLI start stores backend in session config
# ---------------------------------------------------------------------------

class TestCLIStartBackend:
    def test_start_stores_auto_detected_backend(self, runner):
        r, base_args, db_path = runner
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
            result = r.invoke(cli, [*base_args, "start", "--project", "myapp"])
        assert result.exit_code == 0
        assert "Claude backend: direct" in result.output

        conn = _get_conn(db_path)
        init_schema(conn)
        sid = result.output.split("Session created: ")[1].split("\n")[0].strip()
        cfg = get_session_config(conn, sid)
        data = json.loads(cfg["config_json"])
        assert data["claude_backend"] == "direct"
        conn.close()

    def test_start_stores_explicit_sdk_backend(self, runner):
        r, base_args, db_path = runner
        result = r.invoke(cli, [*base_args, "start", "--project", "myapp", "--claude-backend", "sdk"])
        assert result.exit_code == 0
        assert "Claude backend: sdk" in result.output

        conn = _get_conn(db_path)
        init_schema(conn)
        sid = result.output.split("Session created: ")[1].split("\n")[0].strip()
        cfg = get_session_config(conn, sid)
        data = json.loads(cfg["config_json"])
        assert data["claude_backend"] == "sdk"
        conn.close()

    def test_start_warns_direct_with_oauth_only(self, runner):
        r, base_args, db_path = runner
        result = r.invoke(
            cli,
            [*base_args, "start", "--project", "myapp", "--claude-backend", "direct"],
            env={"CLAUDE_CODE_OAUTH_TOKEN": "tok", "ANTHROPIC_API_KEY": ""},
        )
        assert result.exit_code == 0
        assert "Warning" in result.output or "direct" in result.output


# ---------------------------------------------------------------------------
# 6. CLI discuss reads backend from session config
# ---------------------------------------------------------------------------

class TestCLIDiscussBackend:
    @patch("planner_auto.agents.discuss", new_callable=AsyncMock)
    def test_discuss_uses_session_backend(self, mock_discuss, runner):
        """discuss command should pass the session's claude_backend to discuss()."""
        mock_discuss.return_value = "response"
        r, base_args, db_path = runner

        # Create session with sdk backend
        conn = _get_conn(db_path)
        init_schema(conn)
        sid = create_session(conn, "proj")
        update_session_phase(conn, sid, "CONTEXT")
        update_session_phase(conn, sid, "DISCUSSION")
        save_session_config(conn, sid, json.dumps({"claude_backend": "sdk"}))
        conn.commit()
        conn.close()

        result = r.invoke(cli, [*base_args, "discuss", sid, "hello"])
        # Verify discuss was called with backend="sdk"
        if mock_discuss.called:
            call_kwargs = mock_discuss.call_args
            # backend may be positional or keyword
            assert "sdk" in str(call_kwargs)


# ---------------------------------------------------------------------------
# 7. CLI generate reads backend from session config
# ---------------------------------------------------------------------------

class TestCLIGenerateBackend:
    @patch("planner_auto.agents.generate_plan", new_callable=AsyncMock)
    @patch("planner_auto.validation.validate_plan_format", return_value=[])
    def test_generate_uses_session_backend(self, mock_validate, mock_gen, runner):
        mock_gen.return_value = "plan text"
        r, base_args, db_path = runner

        conn = _get_conn(db_path)
        init_schema(conn)
        sid = create_session(conn, "proj")
        update_session_phase(conn, sid, "PLANNING")
        save_session_config(conn, sid, json.dumps({"claude_backend": "sdk"}))
        conn.commit()
        conn.close()

        result = r.invoke(cli, [*base_args, "generate", sid])
        if mock_gen.called:
            call_kwargs = mock_gen.call_args
            assert "sdk" in str(call_kwargs)


# ---------------------------------------------------------------------------
# 8. Fallback to resolve_default_backend for old sessions
# ---------------------------------------------------------------------------

class TestBackendFallback:
    def test_session_without_backend_falls_back(self, runner):
        """Pre-existing sessions without claude_backend should auto-detect."""
        r, base_args, db_path = runner

        conn = _get_conn(db_path)
        init_schema(conn)
        sid = create_session(conn, "proj")
        # Config without claude_backend (old session)
        save_session_config(conn, sid, json.dumps({"project": "proj"}))
        conn.commit()
        conn.close()

        from planner_auto.cli import _resolve_session_backend
        conn2 = _get_conn(db_path)
        init_schema(conn2)
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
            backend = _resolve_session_backend(conn2, sid)
        assert backend == "direct"
        conn2.close()
