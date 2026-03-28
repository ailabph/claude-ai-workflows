"""Tests for export_review_artifacts and kafra_handoff."""

from __future__ import annotations

import json
import os
import sqlite3
from unittest.mock import patch

import pytest

from planner_auto.db import (
    add_plan_draft,
    add_review_v2,
    create_session,
    init_schema,
    save_session_config,
)
from planner_auto.export import export_review_artifacts, kafra_handoff


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    return conn


def _make_session(conn, project="test-project") -> str:
    sid = create_session(conn, project)
    conn.commit()
    return sid


def _seed_review_session(conn, sid):
    """Seed 2 reviews and 2 drafts to simulate a 2-round loop."""
    # Initial plan draft (reviewed in round 1)
    add_plan_draft(conn, sid, "initial plan content", "claude-sonnet")
    # Round 1: NO_GO
    add_review_v2(
        conn, sid, round_number=1, verdict="NO_GO",
        issues_json=json.dumps([{
            "severity": "critical", "description": "Missing auth", "rationale": "R",
            "resolution_guidance": "Add JWT", "target_section": "Security"
        }]),
        summary="Needs work",
        raw_response="{}",
        reviewer_model=None,
        cost=None, input_tokens=None, output_tokens=None,
    )
    # Round 1 revision draft
    add_plan_draft(conn, sid, "revised plan after round 1", "claude-sonnet")
    # Round 2: GO
    add_review_v2(
        conn, sid, round_number=2, verdict="GO",
        issues_json=json.dumps([]),
        summary="Looks good",
        raw_response="{}",
        reviewer_model=None,
        cost=None, input_tokens=None, output_tokens=None,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# 1. export_review_artifacts — interleaved naming
# ---------------------------------------------------------------------------

class TestExportReviewArtifactsNaming:
    def test_review_files_have_interleaved_naming(self, tmp_path):
        conn = _make_conn()
        sid = _make_session(conn)
        _seed_review_session(conn, sid)

        paths = export_review_artifacts(sid, conn, output_dir=str(tmp_path))
        filenames = {os.path.basename(p) for p in paths}

        # Round 1 review → a-02-review.md
        assert "a-02-review.md" in filenames
        # Round 2 review → a-04-review.md
        assert "a-04-review.md" in filenames

    def test_plan_files_have_correct_odd_numbers(self, tmp_path):
        conn = _make_conn()
        sid = _make_session(conn)
        _seed_review_session(conn, sid)

        paths = export_review_artifacts(sid, conn, output_dir=str(tmp_path))
        filenames = {os.path.basename(p) for p in paths}

        # Initial plan → a-01-plan.md
        assert "a-01-plan.md" in filenames
        # Round 1 revision → a-03-plan.md
        assert "a-03-plan.md" in filenames

    def test_review_file_contains_verdict(self, tmp_path):
        conn = _make_conn()
        sid = _make_session(conn)
        _seed_review_session(conn, sid)

        export_review_artifacts(sid, conn, output_dir=str(tmp_path))

        review_file = tmp_path / "a-02-review.md"
        assert review_file.exists()
        content = review_file.read_text()
        assert "NO_GO" in content

    def test_review_file_contains_issues(self, tmp_path):
        conn = _make_conn()
        sid = _make_session(conn)
        _seed_review_session(conn, sid)

        export_review_artifacts(sid, conn, output_dir=str(tmp_path))

        review_file = tmp_path / "a-02-review.md"
        content = review_file.read_text()
        assert "Missing auth" in content
        assert "CRITICAL" in content


# ---------------------------------------------------------------------------
# 2. export_review_artifacts — final plan
# ---------------------------------------------------------------------------

class TestExportReviewArtifactsFinalPlan:
    def test_plan_final_exists(self, tmp_path):
        conn = _make_conn()
        sid = _make_session(conn)
        _seed_review_session(conn, sid)

        export_review_artifacts(sid, conn, output_dir=str(tmp_path))

        # With 2 review rounds, final artifact number = 2*2+1 = 5 → a-05-plan-final.md
        assert (tmp_path / "a-05-plan-final.md").exists()

    def test_plan_final_contains_latest_draft_content(self, tmp_path):
        conn = _make_conn()
        sid = _make_session(conn)
        _seed_review_session(conn, sid)

        export_review_artifacts(sid, conn, output_dir=str(tmp_path))

        content = (tmp_path / "a-05-plan-final.md").read_text()
        # Latest draft is "revised plan after round 1"
        assert "revised plan after round 1" in content

    def test_fast_mode_prepends_header(self, tmp_path):
        conn = _make_conn()
        sid = _make_session(conn)
        _seed_review_session(conn, sid)

        export_review_artifacts(sid, conn, output_dir=str(tmp_path), fast_mode=True)

        for fname in ["a-01-plan.md", "a-02-review.md", "a-05-plan-final.md"]:
            path = tmp_path / fname
            if path.exists():
                content = path.read_text()
                assert content.startswith("[FAST MODE]")
                break


# ---------------------------------------------------------------------------
# 3. kafra_handoff — copy with explicit repo root
# ---------------------------------------------------------------------------

class TestKafraHandoffWithRepoRoot:
    def test_kafra_copy_writes_file(self, tmp_path):
        conn = _make_conn()
        sid = _make_session(conn, project="my-app")
        repo_root = str(tmp_path / "repo")
        os.makedirs(repo_root)

        result = kafra_handoff(sid, conn, "final plan text", "my-app", repo_root=repo_root)

        assert result is not None
        assert os.path.exists(result)
        assert open(result).read() == "final plan text"

    def test_kafra_file_path_follows_convention(self, tmp_path):
        conn = _make_conn()
        sid = _make_session(conn, project="my-app")
        repo_root = str(tmp_path / "repo")
        os.makedirs(repo_root)

        result = kafra_handoff(sid, conn, "plan", "my-app", repo_root=repo_root)

        expected = os.path.join(repo_root, ".kafra", "a-01-plans", "my-app.md")
        assert result == expected

    def test_kafra_creates_directory(self, tmp_path):
        conn = _make_conn()
        sid = _make_session(conn, project="proj")
        repo_root = str(tmp_path / "new_repo")
        # Don't create the directory — kafra_handoff should create it.

        result = kafra_handoff(sid, conn, "plan", "proj", repo_root=repo_root)

        kafra_dir = tmp_path / "new_repo" / ".kafra" / "a-01-plans"
        assert kafra_dir.exists()


# ---------------------------------------------------------------------------
# 4. kafra_handoff — skip without repo root
# ---------------------------------------------------------------------------

class TestKafraHandoffSkipWithoutRepoRoot:
    def test_returns_none_when_no_repo_root(self):
        conn = _make_conn()
        sid = _make_session(conn)
        # No session config, no explicit repo_root, discovery returns None.

        with patch("planner_auto.export.discover_repo_root", return_value=None):
            result = kafra_handoff(sid, conn, "plan", "proj")

        assert result is None

    def test_no_file_written_when_no_repo_root(self, tmp_path):
        conn = _make_conn()
        sid = _make_session(conn)

        with patch("planner_auto.export.discover_repo_root", return_value=None):
            kafra_handoff(sid, conn, "plan", "proj")

        # No file should be created.
        assert not any(tmp_path.rglob("*.md"))


# ---------------------------------------------------------------------------
# 5. kafra_handoff — fallback cwd discovery
# ---------------------------------------------------------------------------

class TestKafraHandoffFallbackDiscovery:
    def test_uses_session_config_repo_root(self, tmp_path):
        conn = _make_conn()
        sid = _make_session(conn)
        repo_root = str(tmp_path / "repo_from_config")
        os.makedirs(repo_root)

        # Store repo_root in session config.
        save_session_config(conn, sid, json.dumps({"project": "p", "repo_root": repo_root}))
        conn.commit()

        # No explicit repo_root argument — should fall back to session config.
        with patch("planner_auto.export.discover_repo_root", return_value=None):
            result = kafra_handoff(sid, conn, "plan", "p")

        assert result is not None
        assert repo_root in result

    def test_falls_back_to_discover_repo_root_when_config_null(self, tmp_path):
        conn = _make_conn()
        sid = _make_session(conn)
        repo_root = str(tmp_path / "discovered_repo")
        os.makedirs(repo_root)

        # Session config has repo_root=None.
        save_session_config(conn, sid, json.dumps({"project": "p", "repo_root": None}))
        conn.commit()

        with patch("planner_auto.export.discover_repo_root", return_value=repo_root):
            result = kafra_handoff(sid, conn, "plan content", "p")

        assert result is not None
        assert repo_root in result
        assert open(result).read() == "plan content"
