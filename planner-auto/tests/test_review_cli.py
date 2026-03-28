"""Tests for the 'planner-auto review' CLI subcommand."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from planner_auto.cli import cli
from planner_auto.db import (
    add_plan_draft,
    create_session,
    get_open_blockers,
    get_session,
    get_session_config,
    init_schema,
    update_session_phase,
)
from planner_auto.loop.engine import LoopResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runner(tmp_path):
    """CliRunner + temp DB path."""
    db_path = str(tmp_path / "test.db")
    r = CliRunner()
    return r, ["--db-path", db_path], db_path


def _get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _make_planning_session(db_path: str) -> str:
    """Create a session in PLANNING phase with one plan draft."""
    conn = _get_conn(db_path)
    init_schema(conn)
    sid = create_session(conn, "test-project")
    # Advance to PLANNING
    update_session_phase(conn, sid, "PLANNING")
    # Add a plan draft
    add_plan_draft(conn, sid, "# My Plan\n\nMilestone 1: Do something.", "claude-sonnet")
    # Save initial config
    conn.execute(
        "INSERT INTO session_config (session_id, config_json) VALUES (?, ?)",
        (sid, json.dumps({"project": "test-project", "model_default": "claude-sonnet-4-6"})),
    )
    conn.commit()
    conn.close()
    return sid


def _converged_result() -> LoopResult:
    return LoopResult(
        converged=True,
        rounds=2,
        final_plan="final plan text",
        final_draft_number=2,
        total_cost=0.0,
        round_details=[
            {"round": 1, "verdict": "NO_GO", "issue_count": 1},
            {"round": 2, "verdict": "GO", "issue_count": 0},
        ],
        stop_reason="go",
        final_round_number=2,
    )


def _cap_criticals_result() -> LoopResult:
    return LoopResult(
        converged=False,
        rounds=2,
        final_plan="plan with issues",
        final_draft_number=2,
        total_cost=0.0,
        round_details=[
            {"round": 1, "verdict": "NO_GO", "issue_count": 1},
            {"round": 2, "verdict": "NO_GO", "issue_count": 1},
        ],
        stop_reason="cap_with_criticals",
        final_round_number=2,
    )


# ---------------------------------------------------------------------------
# 1. Phase validation
# ---------------------------------------------------------------------------

class TestReviewPhaseValidation:
    def test_review_from_setup_is_rejected(self, runner):
        r, base_args, db_path = runner
        # Create a session in SETUP phase (no plan draft).
        conn = _get_conn(db_path)
        init_schema(conn)
        sid = create_session(conn, "proj")
        conn.commit()
        conn.close()

        result = r.invoke(cli, [*base_args, "review", sid])
        assert result.exit_code != 0 or "Error" in result.output

    def test_review_from_planning_advances_phase(self, runner):
        r, base_args, db_path = runner
        sid = _make_planning_session(db_path)

        converged = _converged_result()
        with (
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.cli.DirectAPIAdapter"),
            patch("planner_auto.cli.export_review_artifacts", return_value=[]),
            patch("planner_auto.cli.kafra_handoff", return_value=None),
        ):
            mock_run = AsyncMock(return_value=converged)
            MockEngine.return_value.run = mock_run
            result = r.invoke(cli, [*base_args, "review", sid])

        assert "Phase advanced to REVIEW" in result.output


# ---------------------------------------------------------------------------
# 2. Fast mode config
# ---------------------------------------------------------------------------

class TestReviewFastMode:
    def test_fast_flag_sets_config_values(self, runner):
        r, base_args, db_path = runner
        sid = _make_planning_session(db_path)

        converged = _converged_result()
        with (
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.cli.DirectAPIAdapter"),
            patch("planner_auto.cli.export_review_artifacts", return_value=[]),
            patch("planner_auto.cli.kafra_handoff", return_value=None),
        ):
            mock_run = AsyncMock(return_value=converged)
            MockEngine.return_value.run = mock_run
            r.invoke(cli, [*base_args, "review", "--fast", sid])

        # Check config snapshot was saved with fast_mode=True
        conn = _get_conn(db_path)
        init_schema(conn)
        cfg_row = get_session_config(conn, sid)
        conn.close()
        assert cfg_row is not None
        cfg = json.loads(cfg_row["config_json"])
        assert cfg["fast_mode"] is True
        assert cfg["review_history"] is False
        assert cfg["validate_feedback"] is False
        assert cfg["max_rounds"] == 4

    def test_fast_mode_output_says_fast(self, runner):
        r, base_args, db_path = runner
        sid = _make_planning_session(db_path)

        converged = _converged_result()
        with (
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.cli.DirectAPIAdapter"),
            patch("planner_auto.cli.export_review_artifacts", return_value=[]),
            patch("planner_auto.cli.kafra_handoff", return_value=None),
        ):
            mock_run = AsyncMock(return_value=converged)
            MockEngine.return_value.run = mock_run
            result = r.invoke(cli, [*base_args, "review", "--fast", sid])

        assert "fast=True" in result.output


# ---------------------------------------------------------------------------
# 3. Convergence → COMPLETE
# ---------------------------------------------------------------------------

class TestReviewConvergence:
    def test_convergence_advances_session_to_complete(self, runner):
        r, base_args, db_path = runner
        sid = _make_planning_session(db_path)

        converged = _converged_result()
        with (
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.cli.DirectAPIAdapter"),
            patch("planner_auto.cli.export_review_artifacts", return_value=["/tmp/a.md"]),
            patch("planner_auto.cli.kafra_handoff", return_value=None),
        ):
            MockEngine.return_value.run = AsyncMock(return_value=converged)
            result = r.invoke(cli, [*base_args, "review", sid])

        assert result.exit_code == 0
        conn = _get_conn(db_path)
        init_schema(conn)
        session = get_session(conn, sid)
        conn.close()
        assert session["phase"] == "COMPLETE"
        assert session["status"] == "COMPLETE"

    def test_convergence_prints_complete_message(self, runner):
        r, base_args, db_path = runner
        sid = _make_planning_session(db_path)

        converged = _converged_result()
        with (
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.cli.DirectAPIAdapter"),
            patch("planner_auto.cli.export_review_artifacts", return_value=[]),
            patch("planner_auto.cli.kafra_handoff", return_value=None),
        ):
            MockEngine.return_value.run = AsyncMock(return_value=converged)
            result = r.invoke(cli, [*base_args, "review", sid])

        assert "completed" in result.output.lower() or "complete" in result.output.lower()


# ---------------------------------------------------------------------------
# 4. Cap-hit → blocker
# ---------------------------------------------------------------------------

class TestReviewCapHit:
    def test_cap_with_criticals_pauses_session(self, runner):
        r, base_args, db_path = runner
        sid = _make_planning_session(db_path)

        cap_result = _cap_criticals_result()
        with (
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.cli.DirectAPIAdapter"),
        ):
            MockEngine.return_value.run = AsyncMock(return_value=cap_result)
            r.invoke(cli, [*base_args, "review", sid])

        conn = _get_conn(db_path)
        init_schema(conn)
        session = get_session(conn, sid)
        blockers = get_open_blockers(conn, sid)
        conn.close()

        assert session["status"] == "PAUSED"
        assert len(blockers) >= 1

    def test_cap_with_criticals_prints_blocker_message(self, runner):
        r, base_args, db_path = runner
        sid = _make_planning_session(db_path)

        cap_result = _cap_criticals_result()
        with (
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.cli.DirectAPIAdapter"),
        ):
            MockEngine.return_value.run = AsyncMock(return_value=cap_result)
            result = r.invoke(cli, [*base_args, "review", sid])

        assert "paused" in result.output.lower() or "blocker" in result.output.lower()


# ---------------------------------------------------------------------------
# 5. --repo-root flag
# ---------------------------------------------------------------------------

class TestReviewRepoRootFlag:
    def test_repo_root_flag_stored_in_config(self, runner, tmp_path):
        r, base_args, db_path = runner
        sid = _make_planning_session(db_path)
        fake_repo = str(tmp_path / "my_repo")

        converged = _converged_result()
        with (
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.cli.DirectAPIAdapter"),
            patch("planner_auto.cli.export_review_artifacts", return_value=[]),
            patch("planner_auto.cli.kafra_handoff", return_value=None),
        ):
            MockEngine.return_value.run = AsyncMock(return_value=converged)
            r.invoke(cli, [*base_args, "review", "--repo-root", fake_repo, sid])

        conn = _get_conn(db_path)
        init_schema(conn)
        cfg_row = get_session_config(conn, sid)
        conn.close()
        assert cfg_row is not None
        cfg = json.loads(cfg_row["config_json"])
        # repo_root should be an absolute path matching fake_repo
        assert cfg["repo_root"] is not None
        assert fake_repo in cfg["repo_root"] or cfg["repo_root"].endswith(
            fake_repo.lstrip("/")
        )
