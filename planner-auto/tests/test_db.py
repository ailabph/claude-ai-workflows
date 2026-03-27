"""Tests for planner_auto.db — CRUD functions and query helpers."""

import json
import sqlite3
import time

import pytest

from planner_auto.db import (
    add_context_entry,
    add_message,
    add_plan_draft,
    add_review,
    create_blocker,
    create_session,
    get_all_plan_drafts,
    get_context_entries,
    get_latest_plan_draft,
    get_messages,
    get_open_blockers,
    get_session,
    get_session_config,
    resolve_blocker,
    save_session_config,
    update_session_phase,
    update_session_status,
)
from planner_auto.state import Phase, Status


class TestSessionCRUD:
    """Tests for session create/read/update."""

    def test_create_session(self, db_conn):
        sid = create_session(db_conn, "myapp")
        db_conn.commit()
        assert sid is not None
        assert len(sid) == 8

    def test_get_session(self, db_conn):
        sid = create_session(db_conn, "myapp")
        db_conn.commit()
        session = get_session(db_conn, sid)
        assert session is not None
        assert session["project"] == "myapp"
        assert session["phase"] == "SETUP"
        assert session["status"] == "ACTIVE"

    def test_get_session_not_found(self, db_conn):
        assert get_session(db_conn, "nonexistent") is None

    def test_update_session_phase(self, db_conn):
        sid = create_session(db_conn, "myapp")
        update_session_phase(db_conn, sid, Phase.CONTEXT.value)
        db_conn.commit()
        session = get_session(db_conn, sid)
        assert session["phase"] == "CONTEXT"

    def test_update_session_status(self, db_conn):
        sid = create_session(db_conn, "myapp")
        update_session_status(db_conn, sid, Status.PAUSED.value)
        db_conn.commit()
        session = get_session(db_conn, sid)
        assert session["status"] == "PAUSED"


class TestMessageCRUD:
    """Tests for message create/read."""

    def test_add_and_get_messages(self, db_conn):
        sid = create_session(db_conn, "myapp")
        add_message(db_conn, sid, "user", "Hello")
        add_message(db_conn, sid, "assistant", "Hi there")
        db_conn.commit()
        msgs = get_messages(db_conn, sid)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_messages_ordered_by_id_not_timestamp(self, db_conn):
        """Two messages with the same created_at should be ordered by id (insertion order)."""
        sid = create_session(db_conn, "myapp")
        # Insert both with the exact same timestamp
        fixed_ts = "2025-01-01T00:00:00"
        db_conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (sid, "user", "first", fixed_ts),
        )
        db_conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (sid, "assistant", "second", fixed_ts),
        )
        db_conn.commit()

        msgs = get_messages(db_conn, sid)
        assert len(msgs) == 2
        assert msgs[0]["content"] == "first"
        assert msgs[1]["content"] == "second"
        # Verify they share the same timestamp
        assert msgs[0]["created_at"] == msgs[1]["created_at"]
        # But IDs are sequential
        assert msgs[0]["id"] < msgs[1]["id"]


class TestContextEntryCRUD:
    """Tests for context entry create/read/upsert."""

    def test_add_context_entry(self, db_conn):
        sid = create_session(db_conn, "myapp")
        add_context_entry(db_conn, sid, "README.md", "file", "# Readme")
        db_conn.commit()
        entries = get_context_entries(db_conn, sid)
        assert len(entries) == 1
        assert entries[0]["entry_key"] == "README.md"
        assert entries[0]["content"] == "# Readme"

    def test_context_entry_upsert_replaces_content(self, db_conn):
        """Duplicate (session_id, entry_key, entry_type) should update content."""
        sid = create_session(db_conn, "myapp")
        add_context_entry(db_conn, sid, "README.md", "file", "v1")
        add_context_entry(db_conn, sid, "README.md", "file", "v2")
        db_conn.commit()
        entries = get_context_entries(db_conn, sid)
        assert len(entries) == 1
        assert entries[0]["content"] == "v2"

    def test_context_entry_filter_by_type(self, db_conn):
        sid = create_session(db_conn, "myapp")
        add_context_entry(db_conn, sid, "README.md", "file", "content")
        add_context_entry(db_conn, sid, "note-1", "note", "a note")
        db_conn.commit()
        files = get_context_entries(db_conn, sid, entry_type="file")
        notes = get_context_entries(db_conn, sid, entry_type="note")
        assert len(files) == 1
        assert len(notes) == 1


class TestPlanDraftCRUD:
    """Tests for plan draft create/read with auto-increment."""

    def test_add_plan_draft_auto_increments(self, db_conn):
        sid = create_session(db_conn, "myapp")
        add_plan_draft(db_conn, sid, "Draft 1", "sonnet")
        add_plan_draft(db_conn, sid, "Draft 2", "sonnet")
        db_conn.commit()
        drafts = get_all_plan_drafts(db_conn, sid)
        assert len(drafts) == 2
        assert drafts[0]["draft_number"] == 1
        assert drafts[1]["draft_number"] == 2

    def test_get_latest_plan_draft(self, db_conn):
        sid = create_session(db_conn, "myapp")
        add_plan_draft(db_conn, sid, "Draft 1", "sonnet")
        add_plan_draft(db_conn, sid, "Draft 2", "opus")
        db_conn.commit()
        latest = get_latest_plan_draft(db_conn, sid)
        assert latest is not None
        assert latest["draft_number"] == 2
        assert latest["content"] == "Draft 2"
        assert latest["model"] == "opus"

    def test_get_latest_plan_draft_none(self, db_conn):
        sid = create_session(db_conn, "myapp")
        db_conn.commit()
        assert get_latest_plan_draft(db_conn, sid) is None

    def test_plan_draft_with_config_snapshot(self, db_conn):
        sid = create_session(db_conn, "myapp")
        cfg_id = save_session_config(db_conn, sid, '{"model": "sonnet"}')
        add_plan_draft(db_conn, sid, "Draft 1", "sonnet", config_snapshot_id=cfg_id)
        db_conn.commit()
        draft = get_latest_plan_draft(db_conn, sid)
        assert draft["config_snapshot_id"] == cfg_id


class TestReviewCRUD:
    """Tests for review create."""

    def test_add_review(self, db_conn):
        sid = create_session(db_conn, "myapp")
        draft_id = add_plan_draft(db_conn, sid, "Draft 1", "sonnet")
        review_id = add_review(db_conn, sid, draft_id, "approve", "Looks good")
        db_conn.commit()
        assert review_id is not None

        row = db_conn.execute(
            "SELECT * FROM reviews WHERE id = ?", (review_id,)
        ).fetchone()
        assert row["verdict"] == "approve"
        assert row["content"] == "Looks good"


class TestBlockerCRUD:
    """Tests for blocker create/resolve lifecycle."""

    def test_create_and_resolve_blocker(self, db_conn):
        sid = create_session(db_conn, "myapp")
        bid = create_blocker(db_conn, sid, "planner", "Which DB?")
        db_conn.commit()
        blockers = get_open_blockers(db_conn, sid)
        assert len(blockers) == 1
        assert blockers[0]["question"] == "Which DB?"
        assert blockers[0]["status"] == "open"

        resolve_blocker(db_conn, bid, "PostgreSQL")
        db_conn.commit()
        blockers = get_open_blockers(db_conn, sid)
        assert len(blockers) == 0

        # Verify resolved state
        row = db_conn.execute(
            "SELECT * FROM blockers WHERE id = ?", (bid,)
        ).fetchone()
        assert row["status"] == "resolved"
        assert row["answer"] == "PostgreSQL"
        assert row["resolved_at"] is not None


class TestSessionConfigCRUD:
    """Tests for session config round-trip."""

    def test_save_and_get_session_config(self, db_conn):
        sid = create_session(db_conn, "myapp")
        config = {"project": "myapp", "model_default": "claude-sonnet-4-6"}
        save_session_config(db_conn, sid, json.dumps(config))
        db_conn.commit()

        row = get_session_config(db_conn, sid)
        assert row is not None
        loaded = json.loads(row["config_json"])
        assert loaded["project"] == "myapp"
        assert loaded["model_default"] == "claude-sonnet-4-6"

    def test_get_session_config_returns_latest(self, db_conn):
        sid = create_session(db_conn, "myapp")
        save_session_config(db_conn, sid, '{"v": 1}')
        save_session_config(db_conn, sid, '{"v": 2}')
        db_conn.commit()
        row = get_session_config(db_conn, sid)
        assert json.loads(row["config_json"])["v"] == 2


class TestForeignKeyEnforcement:
    """Test that foreign key constraints are enforced."""

    def test_message_requires_valid_session(self, db_conn):
        with pytest.raises(sqlite3.IntegrityError):
            add_message(db_conn, "nonexistent", "user", "Hello")

    def test_context_entry_requires_valid_session(self, db_conn):
        with pytest.raises(sqlite3.IntegrityError):
            add_context_entry(db_conn, "nonexistent", "key", "file", "content")

    def test_plan_draft_requires_valid_session(self, db_conn):
        with pytest.raises(sqlite3.IntegrityError):
            add_plan_draft(db_conn, "nonexistent", "content", "sonnet")

    def test_blocker_requires_valid_session(self, db_conn):
        with pytest.raises(sqlite3.IntegrityError):
            create_blocker(db_conn, "nonexistent", "planner", "question")
