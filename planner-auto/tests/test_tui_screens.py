"""Tests for TUI modal screens (Milestone 4).

Tests verify that disposition screen, plan screen, and help screen
render correctly with appropriate data.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from planner_auto.tui.bindings import REVIEW_BINDINGS
from planner_auto.tui.screens.disposition_screen import DispositionScreen
from planner_auto.tui.screens.help_screen import HelpScreen, _EXTRA_BINDINGS
from planner_auto.tui.screens.plan_screen import PlanScreen

from textual.app import App, ComposeResult
from textual.widgets import Static


class ScreenTestApp(App):
    """Minimal app for testing modal screens."""

    CSS_PATH = None

    def compose(self) -> ComposeResult:
        yield Static("base")


@pytest.mark.asyncio
class TestDispositionScreen:
    """Test disposition screen renders with mock DB data."""

    async def test_renders_rows_from_round_data(self):
        """Verify row count matches in-memory round data."""
        round_data = {
            1: {
                "issues": [
                    {"description": "Missing tests", "disposition": "ACCEPT", "rationale": "Good point"},
                    {"description": "Typo in doc", "disposition": "REJECT", "rationale": "Not important"},
                ],
            },
            2: {
                "issues": [
                    {"description": "Security flaw", "disposition": "DEFER", "rationale": "Later"},
                ],
            },
        }

        app = ScreenTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = DispositionScreen(
                conn=None,
                session_id="test-session",
                round_data=round_data,
            )
            app.push_screen(screen)
            await pilot.pause()

            from textual.widgets import DataTable
            table = screen.query_one("#disp-table", DataTable)
            assert table.row_count == 3

    async def test_renders_empty_message_with_no_data(self):
        """Verify empty message shows when no dispositions exist."""
        app = ScreenTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = DispositionScreen(
                conn=None,
                session_id="test-session",
                round_data={},
            )
            app.push_screen(screen)
            await pilot.pause()

            empty_label = screen.query_one("#disp-empty", Static)
            text = str(empty_label.render())
            assert "No dispositions" in text

    async def test_renders_from_db(self):
        """Verify disposition screen reads from DB when available."""
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY, project TEXT, phase TEXT, status TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE plan_drafts (
                id INTEGER PRIMARY KEY, session_id TEXT, draft_number INTEGER,
                content TEXT, model TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE reviews (
                id INTEGER PRIMARY KEY, session_id TEXT, draft_id INTEGER,
                round_number INTEGER, verdict TEXT, content TEXT,
                raw_response TEXT, cost REAL, input_tokens INTEGER,
                output_tokens INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE review_dispositions (
                id INTEGER PRIMARY KEY, review_id INTEGER,
                issue_index INTEGER, disposition TEXT, rationale TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("INSERT INTO sessions VALUES ('s1', 'proj', 'REVIEW', 'active')")
        conn.execute("""
            INSERT INTO reviews (id, session_id, draft_id, round_number, verdict)
            VALUES (1, 's1', NULL, 1, 'NO_GO')
        """)
        conn.execute("""
            INSERT INTO review_dispositions (review_id, issue_index, disposition, rationale)
            VALUES (1, 0, 'ACCEPT', 'Agreed'), (1, 1, 'DEFER', 'Later')
        """)
        conn.commit()

        app = ScreenTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = DispositionScreen(conn=conn, session_id="s1")
            app.push_screen(screen)
            await pilot.pause()

            from textual.widgets import DataTable
            table = screen.query_one("#disp-table", DataTable)
            assert table.row_count == 2

        conn.close()


@pytest.mark.asyncio
class TestPlanScreen:
    """Test plan screen shows correct draft content."""

    async def test_shows_fallback_plan(self):
        """Verify fallback plan text is shown when DB is unavailable."""
        app = ScreenTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = PlanScreen(
                conn=None,
                session_id="test-session",
                fallback_plan="## Milestone 1\nBuild the thing",
            )
            app.push_screen(screen)
            await pilot.pause()

            from textual.widgets import TextArea, Label
            text_area = screen.query_one("#plan-text", TextArea)
            assert "Build the thing" in text_area.text

            title = screen.query_one("#plan-title-label", Label)
            title_text = str(title.render())
            assert "Draft #1" in title_text

    async def test_shows_db_plan(self):
        """Verify plan screen reads latest draft from DB."""
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE plan_drafts (
                id INTEGER PRIMARY KEY, session_id TEXT, draft_number INTEGER,
                content TEXT, model TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO plan_drafts (session_id, draft_number, content, model)
            VALUES ('s1', 1, 'Draft 1 content', 'claude'),
                   ('s1', 3, 'Draft 3 content - latest', 'claude')
        """)
        conn.commit()

        app = ScreenTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = PlanScreen(
                conn=conn,
                session_id="s1",
                fallback_plan="fallback text",
            )
            app.push_screen(screen)
            await pilot.pause()

            from textual.widgets import TextArea, Label
            text_area = screen.query_one("#plan-text", TextArea)
            assert "Draft 3 content" in text_area.text

            title = screen.query_one("#plan-title-label", Label)
            title_text = str(title.render())
            assert "Draft #3" in title_text

        conn.close()


@pytest.mark.asyncio
class TestHelpScreen:
    """Test help screen lists all keybindings."""

    async def test_lists_all_bindings(self):
        """Verify help screen contains all REVIEW_BINDINGS entries."""
        app = ScreenTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = HelpScreen()
            app.push_screen(screen)
            await pilot.pause()

            # Each binding description should appear as a Static widget.
            all_statics = screen.query(".help-row")
            # Total rows = REVIEW_BINDINGS + _EXTRA_BINDINGS
            expected_count = len(REVIEW_BINDINGS) + len(_EXTRA_BINDINGS)
            assert len(all_statics) == expected_count

    async def test_contains_key_descriptions(self):
        """Verify key descriptions from REVIEW_BINDINGS appear."""
        app = ScreenTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = HelpScreen()
            app.push_screen(screen)
            await pilot.pause()

            all_text = []
            for widget in screen.query(".help-row"):
                all_text.append(str(widget.render()))

            combined = " ".join(all_text)
            # Check a few expected descriptions.
            assert "Dispositions" in combined
            assert "Quit" in combined
            assert "Help" in combined
