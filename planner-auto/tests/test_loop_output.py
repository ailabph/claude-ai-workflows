"""Tests for ReviewLoopEngine three-tier stdout output.

Verifies:
  - headless (quiet) default: exactly one line per round, no extra output.
  - verbose: full block including model/tokens/dispositions.
  - debug: all of verbose plus raw response warning.

All tests use ``capsys`` and mock the reviewer + query_claude so no real API
calls are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from planner_auto.loop.engine import ReviewLoopEngine
from planner_auto.reviewer.contract import ReviewIssue, Severity




# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHeadlessOutput:
    """Default (quiet) mode: one line per round, no verbose block."""

    def _make_quiet_engine(self) -> ReviewLoopEngine:
        return ReviewLoopEngine(
            conn=MagicMock(), session_id="s1",
            reviewer=MagicMock(), planner_model="claude-test",
            config={"verbosity": "quiet"},
        )

    def test_one_line_per_round_on_go(self, capsys):
        """GO result: _emit_progress produces exactly one line (no separator)."""
        engine = self._make_quiet_engine()
        engine._emit_progress(
            round_num=1, verdict="GO", issue_count=0, is_go=True,
        )
        out = capsys.readouterr().out
        lines = [ln for ln in out.strip().splitlines() if ln.strip()]
        assert len(lines) == 1
        assert "Round 1" in lines[0]
        assert "GO" in lines[0]
        # No verbose separator
        assert not any("─" in ln for ln in lines)

    def test_headless_no_verbose_block(self, capsys):
        """Quiet mode: no separator or verbose details in output."""
        engine = self._make_quiet_engine()
        engine._emit_progress(
            round_num=1, verdict="NO_GO", issue_count=2,
            reviewer_model="gpt-test",
            review_latency_ms=1000,
            input_tokens=100, output_tokens=50,
        )
        out = capsys.readouterr().out
        assert "─" not in out
        assert "model=" not in out
        assert "tokens=" not in out

    def test_headless_line_format_nogo(self, capsys):
        """Default round line: 'Round N: VERDICT (M issues) → revising...'"""
        engine = self._make_quiet_engine()
        engine._emit_progress(
            round_num=3, verdict="NO_GO", issue_count=2, is_go=False,
        )
        out = capsys.readouterr().out
        assert "Round 3:" in out
        assert "NO_GO" in out
        assert "2 issues" in out
        assert "→ revising" in out

    def test_final_line_converged(self, capsys):
        """_emit_final: says 'Converged' when stop_reason is 'go'."""
        engine = self._make_quiet_engine()
        engine._emit_final(stop_reason="go", total_rounds=3, total_cost=0.05)
        out = capsys.readouterr().out
        assert "Converged" in out
        assert "3 rounds" in out
        assert "$" in out

    def test_final_line_cap_reached(self, capsys):
        """_emit_final: says 'Cap reached' when stop_reason is cap-based."""
        engine = self._make_quiet_engine()
        engine._emit_final(
            stop_reason="cap_with_criticals", total_rounds=8, total_cost=0.12,
        )
        out = capsys.readouterr().out
        assert "Cap reached" in out
        assert "8 rounds" in out


class TestVerboseOutput:
    """Verbose mode: includes model/tokens/dispositions in each round block."""

    def test_verbose_includes_separator(self, capsys):
        """Verbose output includes a separator line (─) after the round line."""
        engine = ReviewLoopEngine(
            conn=MagicMock(), session_id="s1",
            reviewer=MagicMock(), planner_model="claude-test",
            config={"verbosity": "verbose"},
        )
        engine._emit_progress(
            round_num=1, verdict="NO_GO", issue_count=2,
            reviewer_model="gpt-test",
            review_latency_ms=1500,
            input_tokens=100, output_tokens=50,
            review_cost=0.01,
            keep_count=1, trim_count=1,
        )
        out = capsys.readouterr().out
        assert "─" in out

    def test_verbose_includes_model_and_tokens(self, capsys):
        """Verbose output includes reviewer model and token counts."""
        engine = ReviewLoopEngine(
            conn=MagicMock(), session_id="s1",
            reviewer=MagicMock(), planner_model="claude-test",
            config={"verbosity": "verbose"},
        )
        engine._emit_progress(
            round_num=1, verdict="NO_GO", issue_count=1,
            reviewer_model="gpt-5.4",
            review_latency_ms=2000,
            input_tokens=300, output_tokens=120,
            review_cost=0.05,
        )
        out = capsys.readouterr().out
        assert "gpt-5.4" in out
        assert "300in/120out" in out
        assert "$0.0500" in out

    def test_verbose_includes_dispositions(self, capsys):
        """Verbose output shows per-issue disposition when provided."""
        engine = ReviewLoopEngine(
            conn=MagicMock(), session_id="s1",
            reviewer=MagicMock(), planner_model="claude-test",
            config={"verbosity": "verbose"},
        )
        dispositions = [
            {"description": "Missing error handling", "disposition": "ACCEPT"},
            {"description": "Unnecessary complexity", "disposition": "DEFER/REJECT"},
        ]
        engine._emit_progress(
            round_num=2, verdict="NO_GO", issue_count=2,
            dispositions=dispositions,
        )
        out = capsys.readouterr().out
        assert "ACCEPT" in out
        assert "Missing error handling" in out
        assert "DEFER/REJECT" in out

    def test_verbose_includes_history_context_size(self, capsys):
        """Verbose output shows history context size."""
        engine = ReviewLoopEngine(
            conn=MagicMock(), session_id="s1",
            reviewer=MagicMock(), planner_model="claude-test",
            config={"verbosity": "verbose"},
        )
        engine._emit_progress(
            round_num=1, verdict="NO_GO", issue_count=0,
            history_context_size=1234,
        )
        out = capsys.readouterr().out
        assert "1234" in out
        assert "History context" in out


class TestDebugOutput:
    """Debug mode: includes raw response + history context with security warning."""

    def test_debug_includes_raw_response_warning(self, capsys):
        """Debug output prepends security warning before raw GPT response."""
        engine = ReviewLoopEngine(
            conn=MagicMock(), session_id="s1",
            reviewer=MagicMock(), planner_model="claude-test",
            config={"verbosity": "debug"},
        )
        engine._emit_progress(
            round_num=1, verdict="GO", issue_count=0,
            raw_gpt_response='{"verdict":"GO","issues":[]}',
            is_go=True,
        )
        out = capsys.readouterr().out
        assert "⚠ DEBUG OUTPUT" in out
        assert "sensitive content" in out
        assert '{"verdict":"GO"' in out

    def test_debug_includes_history_context(self, capsys):
        """Debug output includes full history context string."""
        engine = ReviewLoopEngine(
            conn=MagicMock(), session_id="s1",
            reviewer=MagicMock(), planner_model="claude-test",
            config={"verbosity": "debug"},
        )
        engine._emit_progress(
            round_num=2, verdict="NO_GO", issue_count=1,
            history_context_text="## Previous Round (Round 1) Context\nSome history...",
        )
        out = capsys.readouterr().out
        assert "⚠ DEBUG OUTPUT" in out
        assert "Previous Round" in out

    def test_debug_includes_revision_prompt(self, capsys):
        """Debug output includes the full revision prompt sent to Claude."""
        engine = ReviewLoopEngine(
            conn=MagicMock(), session_id="s1",
            reviewer=MagicMock(), planner_model="claude-test",
            config={"verbosity": "debug"},
        )
        engine._emit_progress(
            round_num=1, verdict="NO_GO", issue_count=1,
            revision_prompt_text="## Current Plan\nSome plan...\n## Issues\n1. Fix this",
        )
        out = capsys.readouterr().out
        assert "⚠ DEBUG OUTPUT" in out
        assert "Current Plan" in out or "Fix this" in out

    def test_debug_includes_verbose_content_too(self, capsys):
        """Debug output also contains all verbose content (model/tokens/etc)."""
        engine = ReviewLoopEngine(
            conn=MagicMock(), session_id="s1",
            reviewer=MagicMock(), planner_model="claude-test",
            config={"verbosity": "debug"},
        )
        engine._emit_progress(
            round_num=1, verdict="NO_GO", issue_count=2,
            reviewer_model="gpt-5.4",
            review_latency_ms=1000,
            input_tokens=200, output_tokens=80,
            review_cost=0.03,
            keep_count=2, trim_count=1,
            history_context_size=500,
        )
        out = capsys.readouterr().out
        # verbose content
        assert "gpt-5.4" in out
        assert "200in/80out" in out
        # debug warning (if raw_gpt_response is provided elsewhere)
        assert "─" in out  # verbose separator present


class TestVerbosityConfig:
    """Verify verbosity is correctly read from config."""

    def test_default_verbosity_is_quiet(self):
        """Engine defaults to 'quiet' when verbosity is not in config."""
        engine = ReviewLoopEngine(
            conn=MagicMock(), session_id="s1",
            reviewer=MagicMock(), planner_model="m",
            config={},
        )
        assert engine._verbosity() == "quiet"

    def test_verbosity_verbose(self):
        engine = ReviewLoopEngine(
            conn=MagicMock(), session_id="s1",
            reviewer=MagicMock(), planner_model="m",
            config={"verbosity": "verbose"},
        )
        assert engine._verbosity() == "verbose"

    def test_verbosity_debug(self):
        engine = ReviewLoopEngine(
            conn=MagicMock(), session_id="s1",
            reviewer=MagicMock(), planner_model="m",
            config={"verbosity": "debug"},
        )
        assert engine._verbosity() == "debug"
