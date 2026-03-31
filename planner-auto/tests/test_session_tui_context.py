"""Tests for SessionTUI context management — file/note modals and phase advancement."""

import sqlite3

import pytest

from planner_auto.db import create_session, init_schema, save_session_config
from planner_auto.tui.session_bindings import SESSION_BINDINGS
from planner_auto.tui.session_messages import ContextAdded, PhaseAdvanced


@pytest.fixture
def db_setup(tmp_path):
    """Create a temp DB with a session and return (db_path, session_id)."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    sid = create_session(conn, "test-project")
    save_session_config(conn, sid, '{"project": "test-project"}')
    conn.commit()
    conn.close()
    return db_path, sid


class TestSessionBindings:
    """Tests for phase-aware keybindings."""

    def test_context_phase_has_file_and_note_keys(self):
        bindings = SESSION_BINDINGS["CONTEXT"]
        keys = [b[0] for b in bindings]
        assert "f" in keys
        assert "n" in keys
        assert "d" in keys

    def test_setup_phase_has_file_and_note_keys(self):
        bindings = SESSION_BINDINGS["SETUP"]
        keys = [b[0] for b in bindings]
        assert "f" in keys
        assert "n" in keys

    def test_discussion_phase_no_file_key(self):
        bindings = SESSION_BINDINGS["DISCUSSION"]
        keys = [b[0] for b in bindings]
        assert "f" not in keys
        assert "n" not in keys

    def test_all_phases_have_quit(self):
        for phase, bindings in SESSION_BINDINGS.items():
            keys = [b[0] for b in bindings]
            assert "q" in keys, f"Phase {phase} missing quit binding"

    def test_all_phases_have_help(self):
        for phase, bindings in SESSION_BINDINGS.items():
            keys = [b[0] for b in bindings]
            assert "question_mark" in keys, f"Phase {phase} missing help binding"

    def test_context_phase_has_advance_discussion(self):
        bindings = SESSION_BINDINGS["CONTEXT"]
        actions = [b[1] for b in bindings]
        assert "advance_discussion" in actions

    def test_setup_phase_no_advance_discussion(self):
        """SETUP phase shouldn't have advance to discussion — need context first."""
        bindings = SESSION_BINDINGS["SETUP"]
        actions = [b[1] for b in bindings]
        assert "advance_discussion" not in actions


class TestFileInputScreen:
    """Tests for FileInputScreen."""

    def test_screen_imports(self):
        """Verify FileInputScreen can be imported."""
        from planner_auto.tui.screens.file_input_screen import FileInputScreen
        screen = FileInputScreen()
        assert screen is not None

    def test_screen_has_dismiss_action(self):
        from planner_auto.tui.screens.file_input_screen import FileInputScreen
        screen = FileInputScreen()
        assert hasattr(screen, "action_dismiss_modal")


class TestNoteInputScreen:
    """Tests for NoteInputScreen."""

    def test_screen_imports(self):
        """Verify NoteInputScreen can be imported."""
        from planner_auto.tui.screens.note_input_screen import NoteInputScreen
        screen = NoteInputScreen()
        assert screen is not None

    def test_screen_has_dismiss_action(self):
        from planner_auto.tui.screens.note_input_screen import NoteInputScreen
        screen = NoteInputScreen()
        assert hasattr(screen, "action_dismiss_modal")


class TestSessionAppImport:
    """Tests for SessionTUI import and basic instantiation."""

    def test_session_tui_imports(self):
        from planner_auto.tui.session_app import SessionTUI
        assert SessionTUI is not None

    def test_session_tui_init(self, db_setup):
        db_path, sid = db_setup
        from planner_auto.tui.session_app import SessionTUI
        app = SessionTUI(session_id=sid, db_path=db_path)
        assert app._session_id == sid
        assert app.exit_code == 0

    def test_session_tui_from_init_module(self):
        from planner_auto.tui import get_session_app_class
        cls = get_session_app_class()
        assert cls.__name__ == "SessionTUI"
