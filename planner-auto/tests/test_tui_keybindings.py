"""Tests for TUI keybinding actions (Milestone 4).

Tests verify that keybindings push/pop screens correctly and
that round detail navigation works.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from planner_auto.tui.messages import (
    ReviewComplete,
    RoundStarted,
)
from planner_auto.tui.widgets.round_detail import RoundDetail
from planner_auto.tui.widgets.current_round import CurrentRound
from planner_auto.tui.widgets.log_panel import LogPanel


def _make_prepared():
    """Create a minimal PreparedReview-like mock for ReviewTUI."""
    prepared = MagicMock()
    prepared.current_plan = "## Milestone 1\nBuild the thing\n## Milestone 2\nTest the thing"
    prepared.complexity = "medium"
    prepared.max_rounds = 6
    prepared.engine_config = {"claude_backend": "direct", "verbosity": "tui"}
    prepared.reviewer = MagicMock()
    prepared.planner_model = "gpt-4o"
    prepared.db_path = None
    return prepared


def _make_app(**kwargs):
    """Create a ReviewTUI instance with disabled worker thread."""
    from planner_auto.tui.review_app import ReviewTUI

    prepared = _make_prepared()

    class TestReviewTUI(ReviewTUI):
        """Subclass that disables the worker thread and CSS for testing."""

        CSS_PATH = None

        def run_review_loop(self):
            """No-op — tests post messages directly."""
            pass

    app = TestReviewTUI(
        prepared=prepared,
        session_id="test-session-1234",
        db_path=None,
        **kwargs,
    )
    return app


@pytest.mark.asyncio
class TestDispositionKeybinding:
    """Test d key pushes disposition screen, Escape pops it."""

    async def test_d_pushes_disposition_screen(self):
        app = _make_app()

        async with app.run_test(size=(120, 40)) as pilot:
            # Press d to push disposition screen.
            await pilot.press("d")
            await pilot.pause()

            # Verify the disposition screen is the active screen.
            from planner_auto.tui.screens.disposition_screen import DispositionScreen
            assert isinstance(app.screen, DispositionScreen)

    async def test_escape_pops_disposition_screen(self):
        app = _make_app()

        async with app.run_test(size=(120, 40)) as pilot:
            # Push disposition screen.
            await pilot.press("d")
            await pilot.pause()

            from planner_auto.tui.screens.disposition_screen import DispositionScreen
            assert isinstance(app.screen, DispositionScreen)

            # Press Escape to pop it.
            await pilot.press("escape")
            await pilot.pause()

            # Should be back on the main screen.
            assert not isinstance(app.screen, DispositionScreen)


@pytest.mark.asyncio
class TestPlanKeybinding:
    """Test p key pushes plan screen."""

    async def test_p_pushes_plan_screen(self):
        app = _make_app()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("p")
            await pilot.pause()

            from planner_auto.tui.screens.plan_screen import PlanScreen
            assert isinstance(app.screen, PlanScreen)


@pytest.mark.asyncio
class TestHelpKeybinding:
    """Test ? key pushes help screen."""

    async def test_question_mark_pushes_help_screen(self):
        app = _make_app()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("?")
            await pilot.pause()

            from planner_auto.tui.screens.help_screen import HelpScreen
            assert isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
class TestLogFilterKeybinding:
    """Test l key cycles log filter."""

    async def test_l_cycles_log_filter(self):
        app = _make_app()

        async with app.run_test(size=(120, 40)) as pilot:
            log_panel = app.query_one("#log-panel", LogPanel)
            assert log_panel.filter_level == "all"

            await pilot.press("l")
            await pilot.pause()
            assert log_panel.filter_level == "warn+"

            await pilot.press("l")
            await pilot.pause()
            assert log_panel.filter_level == "error"

            await pilot.press("l")
            await pilot.pause()
            assert log_panel.filter_level == "all"


@pytest.mark.asyncio
class TestRoundDetailKeybinding:
    """Test Enter on round_list shows round_detail, Escape returns."""

    async def test_enter_shows_round_detail(self):
        app = _make_app()

        async with app.run_test(size=(120, 40)) as pilot:
            # Simulate a completed round.
            app.post_message(RoundStarted(round_num=1, max_rounds=6))
            await pilot.pause()

            app.post_message(ReviewComplete(
                round_num=1, verdict="NO_GO", issue_count=2,
                latency_ms=1500, input_tokens=400, output_tokens=600,
                cost=0.03, keep_count=1, trim_count=0,
                issues=[{"severity": "critical", "description": "Missing auth"}],
            ))
            await pilot.pause()

            # Press Enter to show round detail.
            await pilot.press("enter")
            await pilot.pause()

            # Verify detail view is shown.
            assert app._detail_round == 1

            # Verify RoundDetail widget exists in main panel.
            detail = app.query_one("#round-detail", RoundDetail)
            assert detail._round_num == 1

    async def test_escape_returns_to_dashboard(self):
        app = _make_app()

        async with app.run_test(size=(120, 40)) as pilot:
            # Set up a round.
            app.post_message(RoundStarted(round_num=1, max_rounds=6))
            await pilot.pause()
            app.post_message(ReviewComplete(
                round_num=1, verdict="NO_GO", issue_count=2,
                latency_ms=1500, input_tokens=400, output_tokens=600,
                cost=0.03, keep_count=0, trim_count=0, issues=[],
            ))
            await pilot.pause()

            # Enter detail view.
            await pilot.press("enter")
            await pilot.pause()
            assert app._detail_round == 1

            # Press Escape to go back.
            await pilot.press("escape")
            await pilot.pause()

            assert app._detail_round is None

            # Verify CurrentRound is back.
            cr = app.query_one("#current-round", CurrentRound)
            assert cr is not None

    async def test_n_navigates_to_next_round(self):
        app = _make_app()

        async with app.run_test(size=(120, 40)) as pilot:
            # Set up two rounds.
            for rn in (1, 2):
                app.post_message(RoundStarted(round_num=rn, max_rounds=6))
                await pilot.pause()
                app.post_message(ReviewComplete(
                    round_num=rn, verdict="NO_GO", issue_count=1,
                    latency_ms=1000, input_tokens=300, output_tokens=500,
                    cost=0.02, keep_count=0, trim_count=0, issues=[],
                ))
                await pilot.pause()

            # Enter detail for round 1.
            await app._show_round_detail(1)
            await pilot.pause()
            assert app._detail_round == 1

            # Press n to go to round 2.
            await pilot.press("n")
            await pilot.pause()
            assert app._detail_round == 2
