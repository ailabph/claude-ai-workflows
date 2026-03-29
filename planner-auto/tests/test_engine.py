"""Tests for the ReviewLoopEngine, feedback validation, and history context.

All external calls (reviewer.review, query_claude) are mocked — no API keys needed.
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from planner_auto.db import (
    add_disposition,
    add_plan_draft,
    add_review_v2,
    create_session,
    get_all_dispositions,
    get_dispositions,
    get_review_by_round,
    init_schema,
)
from planner_auto.loop.engine import LoopResult, ReviewLoopEngine
from planner_auto.loop.feedback import validate_feedback
from planner_auto.loop.history import build_review_context, filter_issues
from planner_auto.reviewer.contract import (
    ReviewIssue,
    ReviewerResponse,
    Severity,
    Verdict,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    return conn


def _make_session(conn) -> str:
    session_id = create_session(conn, "test-project")
    conn.commit()
    return session_id


def _go_response() -> ReviewerResponse:
    return ReviewerResponse(verdict=Verdict.GO, issues=[], summary="Looks good.")


def _nogo_response(issues=None) -> ReviewerResponse:
    if issues is None:
        issues = [
            ReviewIssue(
                severity=Severity.CRITICAL,
                description="Missing error handling",
                rationale="Could crash",
            )
        ]
    return ReviewerResponse(verdict=Verdict.NO_GO, issues=issues, summary="Needs work.")


def _make_engine(conn, session_id, reviewer, config=None) -> ReviewLoopEngine:
    return ReviewLoopEngine(
        conn=conn,
        session_id=session_id,
        reviewer=reviewer,
        planner_model="claude-sonnet",
        config=config or {},
    )


# ---------------------------------------------------------------------------
# 1. Loop converges on GO — round 2
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestLoopConvergesOnGO:
    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_go_at_round_2_sets_converged_true(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        # Pre-seed a plan draft so engine has a draft_number baseline.
        add_plan_draft(conn, sid, "initial plan", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan text"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[
            _nogo_response(),   # round 1: NO_GO
            _go_response(),     # round 2: GO
        ])

        engine = _make_engine(conn, sid, reviewer)
        result = await engine.run("initial plan", max_rounds=5)

        assert result.converged is True
        assert result.stop_reason == "go"

    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_go_at_round_2_rounds_count_is_2(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "initial plan", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan text"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[
            _nogo_response(),
            _go_response(),
        ])

        engine = _make_engine(conn, sid, reviewer)
        result = await engine.run("initial plan", max_rounds=5)

        assert result.rounds == 2

    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_go_at_round_2_final_plan_is_revised(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "initial plan", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan text"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[
            _nogo_response(),
            _go_response(),
        ])

        engine = _make_engine(conn, sid, reviewer)
        result = await engine.run("initial plan", max_rounds=5)

        # The plan was revised after round 1; round 2 found it acceptable.
        assert result.final_plan == "revised plan text"


# ---------------------------------------------------------------------------
# 2. Loop hits cap with no criticals → cap_no_criticals
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCapNoCriticals:
    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_cap_no_criticals_stop_reason(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan"

        minor_issue = ReviewIssue(
            severity=Severity.MINOR,
            description="Minor style issue",
            rationale="Cosmetic",
        )
        reviewer = MagicMock()
        reviewer.review = AsyncMock(return_value=_nogo_response([minor_issue]))

        engine = _make_engine(conn, sid, reviewer)
        result = await engine.run("plan v1", max_rounds=2)

        assert result.stop_reason == "cap_no_criticals"

    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_cap_no_criticals_converged_true(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan"

        minor_issue = ReviewIssue(
            severity=Severity.MINOR,
            description="Minor style issue",
            rationale="Cosmetic",
        )
        reviewer = MagicMock()
        reviewer.review = AsyncMock(return_value=_nogo_response([minor_issue]))

        engine = _make_engine(conn, sid, reviewer)
        result = await engine.run("plan v1", max_rounds=2)

        assert result.converged is True


# ---------------------------------------------------------------------------
# 3. Loop hits cap with criticals → cap_with_criticals
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCapWithCriticals:
    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_cap_with_criticals_stop_reason(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(return_value=_nogo_response())

        engine = _make_engine(conn, sid, reviewer)
        result = await engine.run("plan v1", max_rounds=2)

        assert result.stop_reason == "cap_with_criticals"

    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_cap_with_criticals_converged_false(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(return_value=_nogo_response())

        engine = _make_engine(conn, sid, reviewer)
        result = await engine.run("plan v1", max_rounds=2)

        assert result.converged is False


# ---------------------------------------------------------------------------
# 4. Severity filter excludes minor issues from revision prompt
# ---------------------------------------------------------------------------

class TestSeverityFilter:
    def test_filter_issues_excludes_minor_by_default(self):
        issues = [
            ReviewIssue(severity=Severity.CRITICAL, description="C", rationale="R"),
            ReviewIssue(severity=Severity.MAJOR,    description="M", rationale="R"),
            ReviewIssue(severity=Severity.MINOR,    description="m", rationale="R"),
        ]
        result = filter_issues(issues)
        assert len(result) == 2
        descriptions = {i.description for i in result}
        assert "m" not in descriptions

    def test_filter_issues_custom_levels_include_minor(self):
        issues = [
            ReviewIssue(severity=Severity.CRITICAL, description="C", rationale="R"),
            ReviewIssue(severity=Severity.MINOR,    description="m", rationale="R"),
        ]
        result = filter_issues(issues, severity_levels=["critical", "minor"])
        assert len(result) == 2

    def test_filter_issues_case_insensitive(self):
        issues = [
            ReviewIssue(severity=Severity.CRITICAL, description="C", rationale="R"),
        ]
        result = filter_issues(issues, severity_levels=["CRITICAL"])
        assert len(result) == 1



@pytest.mark.asyncio
class TestSeverityFilterEngine:
    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_engine_only_passes_critical_major_to_revision(self, mock_qc):
        """Minor issues should NOT be forwarded to the revision prompt."""
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan"

        minor_only = [ReviewIssue(severity=Severity.MINOR, description="minor_desc", rationale="R")]
        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[
            _nogo_response(minor_only),
            _go_response(),
        ])

        engine = _make_engine(conn, sid, reviewer)
        await engine.run("plan v1", max_rounds=3)

        # The revision prompt content (first positional arg to query_claude messages)
        call_kwargs = mock_qc.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
        revision_content = messages[0]["content"]

        # Minor issue description should not appear (filtered) or "no specific issues" placeholder.
        assert (
            "minor_desc" not in revision_content
            or "no specific issues" in revision_content.lower()
        )


# ---------------------------------------------------------------------------
# 5. validate_feedback stores dispositions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestValidateFeedbackStoresDispositions:
    @patch("planner_auto.loop.feedback.query_claude", new_callable=AsyncMock)
    async def test_dispositions_stored_in_db(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        review_id = add_review_v2(
            conn, sid, round_number=1, verdict="NO_GO",
            issues_json=json.dumps([]),
            summary="x", raw_response="{}", reviewer_model=None,
            cost=None, input_tokens=None, output_tokens=None,
        )
        conn.commit()

        mock_qc.return_value = json.dumps([
            {"index": 0, "disposition": "ACCEPT", "rationale": "Fix it"},
            {"index": 1, "disposition": "DEFER",  "rationale": "Out of scope"},
        ])

        issues = [
            ReviewIssue(severity=Severity.CRITICAL, description="A", rationale="R"),
            ReviewIssue(severity=Severity.MAJOR,    description="B", rationale="R"),
        ]
        review = ReviewerResponse(verdict=Verdict.NO_GO, issues=issues)

        await validate_feedback("plan text", review, "claude-sonnet", conn, review_id)
        conn.commit()

        disps = get_dispositions(conn, review_id)
        assert len(disps) == 2
        disp_map = {d["issue_index"]: d["disposition"] for d in disps}
        assert disp_map[0] == "ACCEPT"
        assert disp_map[1] == "DEFER"

    @patch("planner_auto.loop.feedback.query_claude", new_callable=AsyncMock)
    async def test_only_accept_issues_returned(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        review_id = add_review_v2(
            conn, sid, round_number=1, verdict="NO_GO",
            issues_json=json.dumps([]),
            summary="x", raw_response="{}", reviewer_model=None,
            cost=None, input_tokens=None, output_tokens=None,
        )
        conn.commit()

        mock_qc.return_value = json.dumps([
            {"index": 0, "disposition": "ACCEPT", "rationale": ""},
            {"index": 1, "disposition": "REJECT", "rationale": "Not applicable"},
        ])

        issues = [
            ReviewIssue(severity=Severity.CRITICAL, description="Keep", rationale="R"),
            ReviewIssue(severity=Severity.MAJOR,    description="Drop", rationale="R"),
        ]
        review = ReviewerResponse(verdict=Verdict.NO_GO, issues=issues)

        result = await validate_feedback("plan text", review, "claude-sonnet", conn, review_id)

        assert len(result.issues) == 1
        assert result.issues[0].description == "Keep"

    @patch("planner_auto.loop.feedback.query_claude", new_callable=AsyncMock)
    async def test_validate_feedback_no_issues_returns_empty(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        review = ReviewerResponse(verdict=Verdict.NO_GO, issues=[])
        result = await validate_feedback("plan text", review, "claude-sonnet", conn, 999)
        assert result.issues == []
        mock_qc.assert_not_called()


# ---------------------------------------------------------------------------
# 6. History context includes cumulative DEFER from all prior rounds
# ---------------------------------------------------------------------------

class TestHistoryContextCumulativeDefers:
    def test_round_1_returns_none(self):
        conn = _make_conn()
        sid = _make_session(conn)
        result = build_review_context(conn, sid, current_round=1)
        assert result is None

    def test_round_2_returns_string(self):
        conn = _make_conn()
        sid = _make_session(conn)

        issue = {"severity": "major", "description": "Issue A", "rationale": "R"}
        add_review_v2(
            conn, sid, round_number=1, verdict="NO_GO",
            issues_json=json.dumps([issue]),
            summary="Needs work", raw_response="{}", reviewer_model=None,
            cost=None, input_tokens=None, output_tokens=None,
        )
        conn.commit()

        result = build_review_context(conn, sid, current_round=2)
        assert result is not None
        assert "Round 1" in result

    def test_deferred_issues_appear_in_cumulative_section(self):
        conn = _make_conn()
        sid = _make_session(conn)

        issue = {"severity": "major", "description": "Deferred Issue X", "rationale": "R"}
        review_id = add_review_v2(
            conn, sid, round_number=1, verdict="NO_GO",
            issues_json=json.dumps([issue]),
            summary="", raw_response="{}", reviewer_model=None,
            cost=None, input_tokens=None, output_tokens=None,
        )
        add_disposition(conn, review_id, issue_index=0, disposition="DEFER", rationale="out of scope")
        conn.commit()

        result = build_review_context(conn, sid, current_round=2)
        assert result is not None
        assert "DEFER" in result.upper() or "deferred" in result.lower()
        assert "Deferred Issue X" in result

    def test_defers_from_multiple_rounds_all_appear(self):
        """Defers from round 1 should still appear in context for round 3."""
        conn = _make_conn()
        sid = _make_session(conn)

        issue_r1 = {"severity": "major", "description": "R1 deferred issue", "rationale": "R"}
        r1_id = add_review_v2(
            conn, sid, round_number=1, verdict="NO_GO",
            issues_json=json.dumps([issue_r1]),
            summary="", raw_response="{}", reviewer_model=None,
            cost=None, input_tokens=None, output_tokens=None,
        )
        add_disposition(conn, r1_id, issue_index=0, disposition="DEFER", rationale="round 1 defer")
        conn.commit()

        # Add a draft between rounds.
        add_plan_draft(conn, sid, "revised plan", "claude-sonnet")

        issue_r2 = {"severity": "critical", "description": "R2 accepted issue", "rationale": "R"}
        r2_id = add_review_v2(
            conn, sid, round_number=2, verdict="NO_GO",
            issues_json=json.dumps([issue_r2]),
            summary="", raw_response="{}", reviewer_model=None,
            cost=None, input_tokens=None, output_tokens=None,
        )
        add_disposition(conn, r2_id, issue_index=0, disposition="ACCEPT", rationale="accept this")
        conn.commit()

        result = build_review_context(conn, sid, current_round=3)
        assert result is not None
        # The round-1 defer must appear in cumulative context.
        assert "R1 deferred issue" in result

    def test_context_contains_instructions_not_to_reraise(self):
        conn = _make_conn()
        sid = _make_session(conn)

        issue = {"severity": "major", "description": "Deferred", "rationale": "R"}
        review_id = add_review_v2(
            conn, sid, round_number=1, verdict="NO_GO",
            issues_json=json.dumps([issue]),
            summary="", raw_response="{}", reviewer_model=None,
            cost=None, input_tokens=None, output_tokens=None,
        )
        add_disposition(conn, review_id, issue_index=0, disposition="DEFER", rationale="")
        conn.commit()

        result = build_review_context(conn, sid, current_round=2)
        assert result is not None
        # Should contain instructions about deferred issues.
        assert "do not re-raise" in result.lower() or "not re-raise" in result.lower()


# ---------------------------------------------------------------------------
# 7. Round details tracked correctly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRoundDetails:
    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_round_details_contain_verdict(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[
            _nogo_response(),
            _go_response(),
        ])

        engine = _make_engine(conn, sid, reviewer)
        result = await engine.run("plan v1", max_rounds=5)

        assert len(result.round_details) == 2
        assert result.round_details[0]["verdict"] == "NO_GO"
        assert result.round_details[1]["verdict"] == "GO"

    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_round_details_contain_round_number(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[
            _nogo_response(),
            _go_response(),
        ])

        engine = _make_engine(conn, sid, reviewer)
        result = await engine.run("plan v1", max_rounds=5)

        rounds = [d["round"] for d in result.round_details]
        assert rounds == [1, 2]

    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_reviews_stored_in_db(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[
            _nogo_response(),
            _go_response(),
        ])

        engine = _make_engine(conn, sid, reviewer)
        await engine.run("plan v1", max_rounds=5)

        r1 = get_review_by_round(conn, sid, 1)
        r2 = get_review_by_round(conn, sid, 2)
        assert r1 is not None
        assert r1["verdict"] == "NO_GO"
        assert r2 is not None
        assert r2["verdict"] == "GO"


# ---------------------------------------------------------------------------
# 8. Revision calls use configured effort / thinking / max_turns
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRevisionCallConfig:
    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_effort_forwarded_to_query_claude(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[_nogo_response(), _go_response()])

        engine = _make_engine(conn, sid, reviewer, config={"effort": "high"})
        await engine.run("plan v1", max_rounds=5)

        call_kwargs = mock_qc.call_args.kwargs
        assert call_kwargs.get("effort") == "high"

    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_thinking_forwarded_to_query_claude(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[_nogo_response(), _go_response()])

        engine = _make_engine(conn, sid, reviewer, config={"thinking": True})
        await engine.run("plan v1", max_rounds=5)

        call_kwargs = mock_qc.call_args.kwargs
        assert call_kwargs.get("thinking") is True

    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_max_turns_forwarded_to_query_claude(self, mock_qc):
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[_nogo_response(), _go_response()])

        engine = _make_engine(conn, sid, reviewer, config={"max_turns": 3})
        await engine.run("plan v1", max_rounds=5)

        call_kwargs = mock_qc.call_args.kwargs
        assert call_kwargs.get("max_turns") == 3


# ---------------------------------------------------------------------------
# 9. validate_feedback integration with engine
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestValidateFeedbackIntegration:
    @patch("planner_auto.loop.feedback.query_claude", new_callable=AsyncMock)
    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_validate_feedback_enabled_stores_dispositions(
        self, mock_engine_qc, mock_feedback_qc
    ):
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_engine_qc.return_value = "revised plan"
        mock_feedback_qc.return_value = json.dumps([
            {"index": 0, "disposition": "ACCEPT", "rationale": "important fix"}
        ])

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[_nogo_response(), _go_response()])

        engine = _make_engine(
            conn, sid, reviewer,
            config={"validate_feedback": True}
        )
        await engine.run("plan v1", max_rounds=5)

        # Should have stored a disposition for round 1's review.
        r1 = get_review_by_round(conn, sid, 1)
        assert r1 is not None
        disps = get_all_dispositions(conn, sid)
        assert len(disps) >= 1
        assert disps[0]["disposition"] == "ACCEPT"


# ---------------------------------------------------------------------------
# 10. TUI verbosity suppresses all stdout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestTuiVerbosity:
    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_tui_verbosity_skips_all_stdout(self, mock_qc):
        """Engine with verbosity='tui' and callbacks should produce zero print calls."""
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[_nogo_response(), _go_response()])

        mock_callbacks = {
            "on_round_start": MagicMock(),
            "on_review_complete": MagicMock(),
            "on_feedback_validated": MagicMock(),
            "on_revision_start": MagicMock(),
            "on_revision_complete": MagicMock(),
            "on_loop_finished": MagicMock(),
            "on_revision_timeout": MagicMock(),
        }

        engine = ReviewLoopEngine(
            conn=conn,
            session_id=sid,
            reviewer=reviewer,
            planner_model="claude-sonnet",
            config={"verbosity": "tui"},
            callbacks=mock_callbacks,
        )

        with patch("builtins.print") as mock_print:
            await engine.run("plan v1", max_rounds=5)

        mock_print.assert_not_called()

    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_callbacks_none_does_not_crash(self, mock_qc):
        """Engine with verbosity='tui' and callbacks=None should not raise."""
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[_nogo_response(), _go_response()])

        engine = ReviewLoopEngine(
            conn=conn,
            session_id=sid,
            reviewer=reviewer,
            planner_model="claude-sonnet",
            config={"verbosity": "tui"},
            callbacks=None,
        )

        # Should not raise any exception.
        result = await engine.run("plan v1", max_rounds=5)
        assert result.converged is True

    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_callbacks_partial_dict(self, mock_qc):
        """Provide dict with only 4 of 7 keys — missing keys should be skipped."""
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[_nogo_response(), _go_response()])

        partial_callbacks = {
            "on_round_start": MagicMock(),
            "on_review_complete": MagicMock(),
            "on_loop_finished": MagicMock(),
            "on_revision_complete": MagicMock(),
        }

        engine = ReviewLoopEngine(
            conn=conn,
            session_id=sid,
            reviewer=reviewer,
            planner_model="claude-sonnet",
            config={"verbosity": "tui"},
            callbacks=partial_callbacks,
        )

        # Should not raise — missing keys are skipped.
        result = await engine.run("plan v1", max_rounds=5)
        assert result.converged is True

        # The provided callbacks should have been invoked.
        assert partial_callbacks["on_round_start"].call_count >= 1
        assert partial_callbacks["on_review_complete"].call_count >= 1
        assert partial_callbacks["on_loop_finished"].call_count == 1

    @patch("planner_auto.loop.engine.query_claude", new_callable=AsyncMock)
    async def test_on_revision_start_fires_before_revision(self, mock_qc):
        """on_revision_start should fire between on_feedback_validated and on_revision_complete."""
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "plan v1", "claude-sonnet")
        conn.commit()

        mock_qc.return_value = "revised plan"

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=[_nogo_response(), _go_response()])

        call_order: list[str] = []

        def track(name):
            def handler(*args, **kwargs):
                call_order.append(name)
            return handler

        callbacks = {
            "on_round_start": track("round_start"),
            "on_review_complete": track("review_complete"),
            "on_feedback_validated": track("feedback_validated"),
            "on_revision_start": track("revision_start"),
            "on_revision_complete": track("revision_complete"),
            "on_loop_finished": track("loop_finished"),
        }

        engine = ReviewLoopEngine(
            conn=conn,
            session_id=sid,
            reviewer=reviewer,
            planner_model="claude-sonnet",
            config={"verbosity": "tui"},
            callbacks=callbacks,
        )

        await engine.run("plan v1", max_rounds=5)

        # Verify ordering: feedback_validated before revision_start before revision_complete.
        assert "feedback_validated" in call_order
        assert "revision_start" in call_order
        assert "revision_complete" in call_order

        fb_idx = call_order.index("feedback_validated")
        rs_idx = call_order.index("revision_start")
        rc_idx = call_order.index("revision_complete")
        assert fb_idx < rs_idx < rc_idx
