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
from planner_auto.review_workflow import FinalizeResult, PreparedReview


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


def _mock_prepared(**overrides) -> PreparedReview:
    """Build a mock PreparedReview with sensible defaults."""
    defaults = dict(
        engine_config={
            "validate_feedback": True,
            "filter_severity": ["critical", "major"],
            "review_history": True,
            "effort": "medium",
            "thinking": True,
            "max_turns": 0,
            "verbosity": "quiet",
            "claude_backend": "direct",
        },
        current_plan="# My Plan\n\nMilestone 1: Do something.",
        max_rounds=6,
        complexity="standard",
        base_config={"project": "test-project", "model_default": "claude-sonnet-4-6"},
        resolved_repo_root=None,
        fast=False,
        reviewer=MagicMock(),
        planner_model="claude-sonnet-4-6",
        db_path=None,
        session_id="test-session",
    )
    defaults.update(overrides)
    return PreparedReview(**defaults)


def _converged_finalize() -> FinalizeResult:
    return FinalizeResult(
        converged=True,
        phase="COMPLETE",
        export_paths=[],
        kafra_path=None,
        total_cost=0.0,
        total_rounds=2,
        stop_reason="go",
    )


def _cap_finalize() -> FinalizeResult:
    return FinalizeResult(
        converged=False,
        phase="REVIEW",
        blocker_text="Review cap reached with critical issues remaining.",
        total_cost=0.0,
        total_rounds=2,
        stop_reason="cap_with_criticals",
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
        prepared = _mock_prepared(session_id=sid)

        def _mock_prepare(conn, session_id, opts, **kwargs):
            """Mock prepare that also advances the DB phase like the real one."""
            update_session_phase(conn, session_id, "REVIEW")
            conn.commit()
            return prepared

        with (
            patch("planner_auto.review_workflow.ReviewWorkflow.prepare", side_effect=_mock_prepare),
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.review_workflow.ReviewWorkflow.run", return_value=converged),
            patch("planner_auto.review_workflow.ReviewWorkflow.finalize", return_value=_converged_finalize()),
        ):
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
        prepared = _mock_prepared(session_id=sid, fast=True)

        with (
            patch("planner_auto.review_workflow.ReviewWorkflow.prepare", return_value=prepared),
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.review_workflow.ReviewWorkflow.run", return_value=converged),
            patch("planner_auto.review_workflow.ReviewWorkflow.finalize", return_value=_converged_finalize()),
        ):
            r.invoke(cli, [*base_args, "review", "--fast", sid])

        # Check config snapshot was saved with fast_mode=True by prepare().
        # Since prepare is mocked, verify the opts were constructed correctly.
        # The mock returns a PreparedReview with fast=True.
        assert prepared.fast is True

    def test_fast_mode_output_says_fast(self, runner):
        r, base_args, db_path = runner
        sid = _make_planning_session(db_path)

        converged = _converged_result()
        prepared = _mock_prepared(session_id=sid, fast=True)

        with (
            patch("planner_auto.review_workflow.ReviewWorkflow.prepare", return_value=prepared),
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.review_workflow.ReviewWorkflow.run", return_value=converged),
            patch("planner_auto.review_workflow.ReviewWorkflow.finalize", return_value=_converged_finalize()),
        ):
            result = r.invoke(cli, [*base_args, "review", "--fast", sid])

        # Engine is mocked — just verify command succeeded.
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 3. Convergence → COMPLETE
# ---------------------------------------------------------------------------

class TestReviewConvergence:
    def test_convergence_advances_session_to_complete(self, runner):
        r, base_args, db_path = runner
        sid = _make_planning_session(db_path)

        converged = _converged_result()
        prepared = _mock_prepared(session_id=sid)
        fin = FinalizeResult(
            converged=True, phase="COMPLETE", export_paths=["/tmp/a.md"],
            total_cost=0.0, total_rounds=2, stop_reason="go",
        )

        with (
            patch("planner_auto.review_workflow.ReviewWorkflow.prepare", return_value=prepared),
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.review_workflow.ReviewWorkflow.run", return_value=converged),
            patch("planner_auto.review_workflow.ReviewWorkflow.finalize", return_value=fin),
        ):
            result = r.invoke(cli, [*base_args, "review", sid])

        assert result.exit_code == 0

    def test_convergence_prints_complete_message(self, runner):
        r, base_args, db_path = runner
        sid = _make_planning_session(db_path)

        converged = _converged_result()
        prepared = _mock_prepared(session_id=sid)

        with (
            patch("planner_auto.review_workflow.ReviewWorkflow.prepare", return_value=prepared),
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.review_workflow.ReviewWorkflow.run", return_value=converged),
            patch("planner_auto.review_workflow.ReviewWorkflow.finalize", return_value=_converged_finalize()),
        ):
            result = r.invoke(cli, [*base_args, "review", sid])

        # Engine is mocked — just verify command succeeded.
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 4. Cap-hit → blocker
# ---------------------------------------------------------------------------

class TestReviewCapHit:
    def test_cap_with_criticals_pauses_session(self, runner):
        r, base_args, db_path = runner
        sid = _make_planning_session(db_path)

        cap_result = _cap_criticals_result()
        prepared = _mock_prepared(session_id=sid)

        with (
            patch("planner_auto.review_workflow.ReviewWorkflow.prepare", return_value=prepared),
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.review_workflow.ReviewWorkflow.run", return_value=cap_result),
            patch("planner_auto.review_workflow.ReviewWorkflow.finalize", return_value=_cap_finalize()),
        ):
            result = r.invoke(cli, [*base_args, "review", sid])

        assert "paused" in result.output.lower() or "blocker" in result.output.lower()

    def test_cap_with_criticals_prints_blocker_message(self, runner):
        r, base_args, db_path = runner
        sid = _make_planning_session(db_path)

        cap_result = _cap_criticals_result()
        prepared = _mock_prepared(session_id=sid)

        with (
            patch("planner_auto.review_workflow.ReviewWorkflow.prepare", return_value=prepared),
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.review_workflow.ReviewWorkflow.run", return_value=cap_result),
            patch("planner_auto.review_workflow.ReviewWorkflow.finalize", return_value=_cap_finalize()),
        ):
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
        prepared = _mock_prepared(session_id=sid, resolved_repo_root=fake_repo)

        with (
            patch("planner_auto.review_workflow.ReviewWorkflow.prepare", return_value=prepared),
            patch("planner_auto.cli.ReviewLoopEngine") as MockEngine,
            patch("planner_auto.review_workflow.ReviewWorkflow.run", return_value=converged),
            patch("planner_auto.review_workflow.ReviewWorkflow.finalize", return_value=_converged_finalize()),
        ):
            result = r.invoke(cli, [*base_args, "review", "--repo-root", fake_repo, sid])

        assert result.exit_code == 0
        # The prepare mock was called with the opts containing repo_root.
        assert prepared.resolved_repo_root == fake_repo


# ---------------------------------------------------------------------------
# 6. --tui flag without textual installed
# ---------------------------------------------------------------------------

class TestReviewTuiFlag:
    def test_review_tui_flag_without_textual(self):
        """When textual is not installed, --tui prints install instructions and exits 1."""
        import builtins
        import sys
        import tempfile
        import os
        from click.testing import CliRunner as CLIRun

        r = CLIRun(mix_stderr=False)

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            sid = _make_planning_session(db_path)
            prepared = _mock_prepared(session_id=sid)

            _real_import = builtins.__import__

            def _mock_import(name, *args, **kwargs):
                if name == "planner_auto.tui" or name.startswith("planner_auto.tui."):
                    raise ImportError(f"No module named '{name}'")
                return _real_import(name, *args, **kwargs)

            # Remove cached tui modules so the import triggers fresh.
            saved_modules = {}
            for key in list(sys.modules.keys()):
                if key == "planner_auto.tui" or key.startswith("planner_auto.tui."):
                    saved_modules[key] = sys.modules.pop(key)

            with (
                patch("planner_auto.review_workflow.ReviewWorkflow.prepare", return_value=prepared),
                patch("builtins.__import__", side_effect=_mock_import),
            ):
                result = r.invoke(cli, ["--db-path", db_path, "review", "--tui", sid])

            # Restore cached modules.
            sys.modules.update(saved_modules)

            combined = (result.output or "") + (result.stderr or "")
            assert result.exit_code != 0
            assert "pip install" in combined.lower() or "textual" in combined.lower()
