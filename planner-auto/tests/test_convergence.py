"""Tests for planner_auto.loop.convergence: complexity detection and round caps."""

from __future__ import annotations

import sqlite3

import pytest

from planner_auto.db import (
    add_message,
    add_plan_draft,
    create_session,
    init_schema,
)
from planner_auto.loop.convergence import (
    COMPLEX_KEYWORDS,
    detect_complexity,
    get_max_rounds,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    return conn


def _make_session(conn) -> str:
    sid = create_session(conn, "test-project")
    conn.commit()
    return sid


# ---------------------------------------------------------------------------
# 1. detect_complexity — standard from user message
# ---------------------------------------------------------------------------

class TestDetectComplexityFromMessage:
    def test_simple_feature_desc_is_standard(self):
        conn = _make_conn()
        sid = _make_session(conn)
        add_message(conn, sid, "user", "Build a REST API for user management")
        conn.commit()

        result = detect_complexity(conn, sid)
        assert result == "standard"

    def test_complex_keyword_in_user_message_gives_complex(self):
        conn = _make_conn()
        sid = _make_session(conn)
        add_message(conn, sid, "user", "Build a retry backoff queue system")
        conn.commit()

        result = detect_complexity(conn, sid)
        assert result == "complex"

    def test_no_messages_no_drafts_is_standard(self):
        conn = _make_conn()
        sid = _make_session(conn)
        # No messages, no drafts
        result = detect_complexity(conn, sid)
        assert result == "standard"

    def test_returns_string(self):
        conn = _make_conn()
        sid = _make_session(conn)
        result = detect_complexity(conn, sid)
        assert isinstance(result, str)
        assert result in ("standard", "complex")


# ---------------------------------------------------------------------------
# 2. detect_complexity — complex keywords in plan content
# ---------------------------------------------------------------------------

class TestDetectComplexityFromPlanContent:
    def test_complex_keyword_in_plan_draft(self):
        conn = _make_conn()
        sid = _make_session(conn)
        # Simple user message, but plan mentions "state machine"
        add_message(conn, sid, "user", "Build authentication system")
        add_plan_draft(conn, sid, "Use a state machine to manage user sessions", "model")
        conn.commit()

        result = detect_complexity(conn, sid)
        assert result == "complex"

    def test_encrypt_keyword_in_plan(self):
        conn = _make_conn()
        sid = _make_session(conn)
        add_plan_draft(conn, sid, "Encrypt sensitive fields before storage", "model")
        conn.commit()

        result = detect_complexity(conn, sid)
        assert result == "complex"

    def test_keyword_detection_is_case_insensitive(self):
        conn = _make_conn()
        sid = _make_session(conn)
        add_message(conn, sid, "user", "Add HMAC signing to API requests")
        conn.commit()

        result = detect_complexity(conn, sid)
        assert result == "complex"


# ---------------------------------------------------------------------------
# 3. get_max_rounds
# ---------------------------------------------------------------------------

class TestGetMaxRounds:
    def test_standard_returns_8(self):
        assert get_max_rounds("standard") == 8

    def test_complex_returns_12(self):
        assert get_max_rounds("complex") == 12

    def test_fast_returns_4_regardless_of_standard(self):
        assert get_max_rounds("standard", fast=True) == 4

    def test_fast_overrides_complex(self):
        assert get_max_rounds("complex", fast=True) == 4

    def test_default_fast_is_false(self):
        assert get_max_rounds("standard", fast=False) == 8


# ---------------------------------------------------------------------------
# 4. COMPLEX_KEYWORDS list sanity
# ---------------------------------------------------------------------------

class TestComplexKeywordsList:
    def test_keywords_list_is_nonempty(self):
        assert len(COMPLEX_KEYWORDS) > 0

    def test_keywords_are_lowercase_strings(self):
        for kw in COMPLEX_KEYWORDS:
            assert isinstance(kw, str)
            assert kw == kw.lower()
