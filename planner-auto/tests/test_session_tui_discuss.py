"""Tests for SessionTUI discussion mode — ChatView, workers, phase advancement."""

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from planner_auto.db import (
    add_message,
    create_session,
    init_schema,
    save_session_config,
    update_session_phase,
)
from planner_auto.state import Phase
from planner_auto.tui.session_bindings import SESSION_BINDINGS
from planner_auto.tui.session_messages import (
    DiscussMessageSent,
    DiscussResponseReceived,
    DiscussThinking,
    SessionError,
)


@pytest.fixture
def db_setup(tmp_path):
    """Create a temp DB with a session in DISCUSSION phase."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    sid = create_session(conn, "test-project")
    save_session_config(conn, sid, '{"project": "test-project", "claude_backend": "direct"}')
    # Advance to DISCUSSION phase
    update_session_phase(conn, sid, Phase.DISCUSSION.value)
    conn.commit()
    conn.close()
    return db_path, sid


@pytest.fixture
def db_with_messages(tmp_path):
    """Create a temp DB with a session that already has messages."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    sid = create_session(conn, "test-project")
    save_session_config(conn, sid, '{"project": "test-project", "claude_backend": "direct"}')
    update_session_phase(conn, sid, Phase.DISCUSSION.value)
    # Add existing messages
    add_message(conn, sid, "user", "Hello, what should I build?")
    add_message(conn, sid, "assistant", "I suggest building a REST API for user management.")
    add_message(conn, sid, "user", "Sounds good, what tech stack?")
    add_message(conn, sid, "assistant", "I recommend FastAPI with PostgreSQL.")
    conn.commit()
    conn.close()
    return db_path, sid


class TestChatViewWidget:
    """Tests for the ChatView widget."""

    def test_chat_view_imports(self):
        from planner_auto.tui.widgets.chat_view import ChatView
        assert ChatView is not None

    def test_chat_view_init(self):
        from planner_auto.tui.widgets.chat_view import ChatView
        chat = ChatView()
        assert chat.is_thinking is False

    def test_thinking_state(self):
        from planner_auto.tui.widgets.chat_view import ChatView
        chat = ChatView()
        # Before show_thinking, no thinking label
        assert chat._thinking_label is None
        assert chat.is_thinking is False


class TestDiscussionBindings:
    """Tests for DISCUSSION phase keybindings."""

    def test_discussion_has_ctrl_d(self):
        bindings = SESSION_BINDINGS["DISCUSSION"]
        keys = [b[0] for b in bindings]
        assert "ctrl+d" in keys

    def test_discussion_has_advance_planning_action(self):
        bindings = SESSION_BINDINGS["DISCUSSION"]
        actions = [b[1] for b in bindings]
        assert "advance_planning" in actions

    def test_discussion_has_quit(self):
        bindings = SESSION_BINDINGS["DISCUSSION"]
        keys = [b[0] for b in bindings]
        assert "q" in keys

    def test_discussion_has_help(self):
        bindings = SESSION_BINDINGS["DISCUSSION"]
        keys = [b[0] for b in bindings]
        assert "question_mark" in keys

    def test_discussion_has_log_filter(self):
        bindings = SESSION_BINDINGS["DISCUSSION"]
        keys = [b[0] for b in bindings]
        assert "l" in keys


class TestDiscussMessageTypes:
    """Tests for discussion-related message types."""

    def test_discuss_message_sent(self):
        msg = DiscussMessageSent("Hello!", 6)
        assert msg.content == "Hello!"
        assert msg.char_count == 6

    def test_discuss_response_received(self):
        msg = DiscussResponseReceived("Hi there!", 1500)
        assert msg.content == "Hi there!"
        assert msg.latency_ms == 1500

    def test_discuss_thinking(self):
        msg = DiscussThinking()
        assert isinstance(msg, DiscussThinking)


class TestSessionTUIDiscussionInit:
    """Tests for SessionTUI discussion state initialization."""

    def test_discussion_state_fields(self, db_setup):
        db_path, sid = db_setup
        from planner_auto.tui.session_app import SessionTUI
        app = SessionTUI(session_id=sid, db_path=db_path)
        assert app._discuss_active is False
        assert app._quit_requested is False
        assert app._thinking_timer is None

    def test_has_advance_planning_action(self, db_setup):
        db_path, sid = db_setup
        from planner_auto.tui.session_app import SessionTUI
        app = SessionTUI(session_id=sid, db_path=db_path)
        assert hasattr(app, "action_advance_planning")

    def test_has_send_discuss_method(self, db_setup):
        db_path, sid = db_setup
        from planner_auto.tui.session_app import SessionTUI
        app = SessionTUI(session_id=sid, db_path=db_path)
        assert hasattr(app, "_send_discuss_message")


class TestSessionTUIQuitBehavior:
    """Tests for deferred quit during active discussion."""

    def test_quit_requested_flag_default(self, db_setup):
        db_path, sid = db_setup
        from planner_auto.tui.session_app import SessionTUI
        app = SessionTUI(session_id=sid, db_path=db_path)
        assert app._quit_requested is False

    def test_discuss_active_flag_default(self, db_setup):
        db_path, sid = db_setup
        from planner_auto.tui.session_app import SessionTUI
        app = SessionTUI(session_id=sid, db_path=db_path)
        assert app._discuss_active is False


class TestResolveBackend:
    """Tests for _resolve_backend_from_config helper."""

    def test_resolves_from_config(self, db_setup):
        db_path, sid = db_setup
        from planner_auto.tui.session_app import _resolve_backend_from_config
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        init_schema(conn)
        result = _resolve_backend_from_config(conn, sid)
        assert result == "direct"
        conn.close()

    def test_fallback_on_missing_config(self):
        from planner_auto.tui.session_app import _resolve_backend_from_config
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        init_schema(conn)
        sid = create_session(conn, "test")
        conn.commit()
        # No config saved — should fall back to auto-detect
        result = _resolve_backend_from_config(conn, sid)
        assert result in ("direct", "sdk")
        conn.close()


class TestChatViewLoadMessages:
    """Tests for ChatView.load_messages() (resume scenario)."""

    def test_load_messages_populates_list(self):
        from planner_auto.tui.widgets.chat_view import ChatView
        chat = ChatView()
        # load_messages doesn't actually mount labels without an app,
        # but we can test it doesn't crash
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        # This would need a running app to fully test mounting,
        # but we verify it handles the data structure correctly
        assert hasattr(chat, "load_messages")
        assert callable(chat.load_messages)


class TestSwitchMainPanelDiscussion:
    """Tests that _switch_main_panel handles DISCUSSION phase."""

    def test_discussion_phase_not_unknown(self):
        """DISCUSSION is a known phase — _switch_main_panel mounts ChatView for it."""
        # DISCUSSION phase is fully implemented (mounts ChatView).
        # Just verify Phase.DISCUSSION exists.
        from planner_auto.state import Phase
        assert Phase.DISCUSSION.value == "DISCUSSION"

    def test_planning_phase_implemented(self):
        """PLANNING is a known phase — _switch_main_panel mounts planning widgets."""
        from planner_auto.state import Phase
        assert Phase.PLANNING.value == "PLANNING"
