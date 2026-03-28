"""Tests for planner_auto/inspect.py formatting functions.

Verifies:
  - format_reviews_table output contains expected headers and values
  - format_dispositions handles single-round and all-round queries
  - format_config renders config keys correctly
  - reconstruct_history note text and delegation to build_review_context
  - format_raw_response includes the security warning
  - dump_session_json includes the security warning and all table data
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch

import pytest

from planner_auto.db import (
    add_disposition,
    add_plan_draft,
    add_review_v2,
    create_session,
    init_schema,
    save_session_config,
)
from planner_auto.inspect import (
    _SECURITY_WARNING,
    dump_session_json,
    format_config,
    format_dispositions,
    format_raw_response,
    format_reviews_table,
    reconstruct_history,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    init_schema(c)
    yield c
    c.close()


@pytest.fixture()
def session_with_reviews(conn):
    """Session with 2 rounds, dispositions, and a config snapshot."""
    session_id = create_session(conn, "test-project")

    # Config
    save_session_config(conn, session_id, json.dumps({"project": "test-project", "max_rounds": 5}))

    # Plan draft
    add_plan_draft(conn, session_id, "Initial plan content", "claude-test")

    # Round 1 review
    issues1 = json.dumps([
        {"severity": "critical", "description": "Missing auth"},
        {"severity": "major", "description": "No error handling"},
    ])
    rev1_id = add_review_v2(
        conn, session_id, 1, "NO_GO", issues1,
        "Needs work", '{"verdict":"NO_GO","issues":[]}', "gpt-4o-mini",
        0.01, 200, 80,
    )
    add_disposition(conn, rev1_id, 0, "ACCEPT", "Will fix auth")
    add_disposition(conn, rev1_id, 1, "DEFER", "Low priority")

    # Round 2 review
    issues2 = json.dumps([{"severity": "minor", "description": "Style issue"}])
    add_review_v2(
        conn, session_id, 2, "GO", issues2,
        "Looks good", None, "gpt-4o-mini", 0.005, 150, 60,
    )

    conn.commit()
    return session_id, conn


# ---------------------------------------------------------------------------
# format_reviews_table
# ---------------------------------------------------------------------------

class TestFormatReviewsTable:
    def test_table_has_header_columns(self, session_with_reviews):
        session_id, conn = session_with_reviews
        output = format_reviews_table(conn, session_id)
        assert "Rnd" in output
        assert "Verdict" in output
        assert "Issues" in output
        assert "Model" in output

    def test_table_shows_both_rounds(self, session_with_reviews):
        session_id, conn = session_with_reviews
        output = format_reviews_table(conn, session_id)
        assert "NO_GO" in output
        assert "GO" in output
        # Both round numbers
        lines = output.splitlines()
        round_lines = [ln for ln in lines if "NO_GO" in ln or "GO" in ln]
        assert len(round_lines) >= 2

    def test_table_shows_issue_count(self, session_with_reviews):
        session_id, conn = session_with_reviews
        output = format_reviews_table(conn, session_id)
        # Round 1 has 2 issues, round 2 has 1
        assert "2" in output
        assert "1" in output

    def test_empty_session_returns_no_reviews_message(self, conn):
        session_id = create_session(conn, "empty-project")
        conn.commit()
        output = format_reviews_table(conn, session_id)
        assert "No reviews" in output


# ---------------------------------------------------------------------------
# format_dispositions
# ---------------------------------------------------------------------------

class TestFormatDispositions:
    def test_single_round_shows_dispositions(self, session_with_reviews):
        session_id, conn = session_with_reviews
        output = format_dispositions(conn, session_id, round_num=1)
        assert "ACCEPT" in output
        assert "DEFER" in output

    def test_single_round_includes_descriptions(self, session_with_reviews):
        session_id, conn = session_with_reviews
        output = format_dispositions(conn, session_id, round_num=1)
        assert "Missing auth" in output
        assert "No error handling" in output

    def test_all_rounds_includes_both_rounds(self, session_with_reviews):
        session_id, conn = session_with_reviews
        output = format_dispositions(conn, session_id)
        assert "ACCEPT" in output
        assert "DEFER" in output

    def test_missing_round_returns_not_found(self, conn):
        session_id = create_session(conn, "empty")
        conn.commit()
        output = format_dispositions(conn, session_id, round_num=99)
        assert "No review found" in output or "not found" in output.lower()

    def test_no_dispositions_returns_empty_message(self, conn):
        session_id = create_session(conn, "nodisps")
        add_plan_draft(conn, session_id, "plan", "m")
        add_review_v2(conn, session_id, 1, "GO", "[]", "ok", None, None, None, None, None)
        conn.commit()
        output = format_dispositions(conn, session_id, round_num=1)
        assert "No dispositions" in output


# ---------------------------------------------------------------------------
# format_config
# ---------------------------------------------------------------------------

class TestFormatConfig:
    def test_config_shows_keys(self, session_with_reviews):
        session_id, conn = session_with_reviews
        output = format_config(conn, session_id)
        assert "max_rounds" in output
        assert "project" in output

    def test_config_shows_values(self, session_with_reviews):
        session_id, conn = session_with_reviews
        output = format_config(conn, session_id)
        assert "test-project" in output

    def test_no_config_returns_message(self, conn):
        session_id = create_session(conn, "nocfg")
        conn.commit()
        output = format_config(conn, session_id)
        assert "No config found" in output


# ---------------------------------------------------------------------------
# reconstruct_history
# ---------------------------------------------------------------------------

class TestReconstructHistory:
    def test_round_1_returns_no_history_message(self, conn):
        session_id = create_session(conn, "hist-test")
        conn.commit()
        output = reconstruct_history(conn, session_id, 1)
        assert "no prior history" in output or "first round" in output

    def test_includes_reconstructed_note(self, conn):
        """All outputs include the 'not stored' note."""
        session_id = create_session(conn, "hist-test2")
        conn.commit()
        # Round 1: trivially returns "not stored" note
        output = reconstruct_history(conn, session_id, 1)
        assert "not stored" in output

    def test_round_2_with_prior_review_returns_context(self, session_with_reviews):
        session_id, conn = session_with_reviews
        output = reconstruct_history(conn, session_id, 2)
        # Should contain history context from round 1
        assert "Round 1" in output or "Previous Round" in output
        assert "not stored" in output

    def test_missing_prior_review_returns_explanation(self, conn):
        """When round 2 is requested but round 1 review is absent, explain."""
        session_id = create_session(conn, "no-prior")
        conn.commit()
        output = reconstruct_history(conn, session_id, 2)
        # No prior review exists → either explanation or None from build_review_context
        assert session_id in output or "not available" in output or "missing" in output.lower()


# ---------------------------------------------------------------------------
# format_raw_response
# ---------------------------------------------------------------------------

class TestFormatRawResponse:
    def test_includes_security_warning(self, session_with_reviews):
        session_id, conn = session_with_reviews
        output = format_raw_response(conn, session_id, 1)
        assert "⚠" in output
        assert "redaction" in output or "sensitive" in output or "Do not share" in output

    def test_contains_raw_response_text(self, session_with_reviews):
        session_id, conn = session_with_reviews
        output = format_raw_response(conn, session_id, 1)
        # Round 1 raw_response is '{"verdict":"NO_GO","issues":[]}'
        assert "NO_GO" in output

    def test_missing_round_returns_not_found(self, conn):
        session_id = create_session(conn, "noraw")
        conn.commit()
        output = format_raw_response(conn, session_id, 5)
        assert "No review found" in output

    def test_null_raw_response_returns_message(self, conn):
        session_id = create_session(conn, "nullraw")
        add_plan_draft(conn, session_id, "plan", "m")
        add_review_v2(conn, session_id, 1, "GO", "[]", "ok", None, None, None, None, None)
        conn.commit()
        output = format_raw_response(conn, session_id, 1)
        assert "No raw response" in output


# ---------------------------------------------------------------------------
# dump_session_json
# ---------------------------------------------------------------------------

class TestDumpSessionJson:
    def test_returns_pure_json(self, session_with_reviews):
        """dump_session_json returns pure JSON (no warning prefix)."""
        session_id, conn = session_with_reviews
        output = dump_session_json(conn, session_id)
        # Should be parseable as-is without stripping a warning line
        data = json.loads(output)
        assert "session" in data

    def test_contains_session_metadata(self, session_with_reviews):
        session_id, conn = session_with_reviews
        output = dump_session_json(conn, session_id)
        data = json.loads(output)
        assert data["session"]["id"] == session_id
        assert data["session"]["project"] == "test-project"

    def test_contains_reviews(self, session_with_reviews):
        session_id, conn = session_with_reviews
        output = dump_session_json(conn, session_id)
        data = json.loads(output)
        assert len(data["reviews"]) == 2

    def test_contains_dispositions(self, session_with_reviews):
        session_id, conn = session_with_reviews
        output = dump_session_json(conn, session_id)
        data = json.loads(output)
        assert len(data["dispositions"]) == 2

    def test_contains_blockers(self, session_with_reviews):
        """dump_session_json includes a blockers key with open and resolved."""
        session_id, conn = session_with_reviews
        output = dump_session_json(conn, session_id)
        data = json.loads(output)
        assert "blockers" in data
        assert "open" in data["blockers"]
        assert "resolved" in data["blockers"]

    def test_nonexistent_session_returns_error_json(self, conn):
        output = dump_session_json(conn, "nonexistent")
        data = json.loads(output)
        assert "error" in data
