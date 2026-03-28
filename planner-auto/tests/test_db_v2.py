"""Tests for Plan-2 DB schema additions (schema versioning, v2 reviews,
review_dispositions, and new CRUD/query helpers)."""

import json
import sqlite3

import pytest

from planner_auto.db import (
    CURRENT_SCHEMA_VERSION,
    add_disposition,
    add_plan_draft,
    add_review,
    add_review_v2,
    create_session,
    get_all_dispositions,
    get_dispositions,
    get_review_by_round,
    get_schema_version,
    init_schema,
    set_schema_version,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn() -> sqlite3.Connection:
    """Return a fresh in-memory connection with schema initialised."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# 1. Fresh install creates v2 schema directly
# ---------------------------------------------------------------------------

class TestFreshInstallCreatesV2Schema:
    def test_schema_version_is_2_after_init(self, db_conn):
        """A freshly initialised DB should be at version 2."""
        assert get_schema_version(db_conn) == CURRENT_SCHEMA_VERSION

    def test_reviews_table_has_v2_columns(self, db_conn):
        """The reviews table must expose the new Plan-2 columns."""
        rows = db_conn.execute("PRAGMA table_info(reviews)").fetchall()
        col_names = {r["name"] for r in rows}
        expected = {
            "id", "session_id", "draft_id", "round_number", "verdict",
            "content", "issues_json", "summary", "raw_response",
            "reviewer_model", "cost", "input_tokens", "output_tokens",
            "created_at",
        }
        assert expected.issubset(col_names)

    def test_review_dispositions_table_exists(self, db_conn):
        """review_dispositions table must be present after init."""
        rows = db_conn.execute("PRAGMA table_info(review_dispositions)").fetchall()
        col_names = {r["name"] for r in rows}
        assert {"id", "review_id", "issue_index", "disposition", "rationale", "created_at"}.issubset(
            col_names
        )


# ---------------------------------------------------------------------------
# 2. Migration from v1 to v2 preserves existing review rows
# ---------------------------------------------------------------------------

class TestMigrationFromV1ToV2:
    def _build_v1_db(self) -> sqlite3.Connection:
        """Create a DB with the v1 schema (no schema_version table) and
        some seed data, then return the raw connection for migration testing."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        # Create v1 tables manually (no schema_version).
        conn.executescript("""
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                project TEXT NOT NULL,
                phase TEXT NOT NULL DEFAULT 'SETUP',
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE context_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                entry_key TEXT NOT NULL,
                entry_type TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, entry_key, entry_type)
            );
            CREATE TABLE session_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE plan_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                draft_number INTEGER NOT NULL,
                content TEXT NOT NULL,
                model TEXT NOT NULL,
                config_snapshot_id INTEGER REFERENCES session_config(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, draft_number)
            );
            CREATE TABLE reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                draft_id INTEGER NOT NULL REFERENCES plan_drafts(id),
                verdict TEXT,
                content TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE blockers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                source TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                resolved_at TEXT
            );
        """)

        # Seed a session, draft, and review.
        conn.execute("INSERT INTO sessions (id, project) VALUES ('aabb1122', 'legacy-proj')")
        conn.execute(
            "INSERT INTO plan_drafts (session_id, draft_number, content, model) "
            "VALUES ('aabb1122', 1, 'Legacy plan', 'sonnet')"
        )
        conn.execute(
            "INSERT INTO reviews (session_id, draft_id, verdict, content) "
            "VALUES ('aabb1122', 1, 'approve', 'Old review')"
        )
        conn.commit()
        return conn

    def test_migration_preserves_legacy_review_rows(self):
        """Migrating a v1 DB should keep all review rows with round_number=NULL."""
        conn = self._build_v1_db()
        # Running init_schema on an existing v1 DB triggers the migration.
        init_schema(conn)

        # Legacy row should survive.
        row = conn.execute("SELECT * FROM reviews WHERE session_id = 'aabb1122'").fetchone()
        assert row is not None
        assert row["verdict"] == "approve"
        assert row["content"] == "Old review"

    def test_migration_sets_round_number_null_on_legacy_rows(self):
        """Legacy review rows must have round_number=NULL after migration."""
        conn = self._build_v1_db()
        init_schema(conn)

        row = conn.execute("SELECT * FROM reviews WHERE session_id = 'aabb1122'").fetchone()
        assert row["round_number"] is None

    def test_migration_updates_schema_version_to_2(self):
        """After migration the schema version must be 2."""
        conn = self._build_v1_db()
        init_schema(conn)
        assert get_schema_version(conn) == 2


# ---------------------------------------------------------------------------
# 3. add_review_v2 round-trip with all fields
# ---------------------------------------------------------------------------

class TestAddReviewV2:
    def test_add_review_v2_roundtrip(self, db_conn):
        """add_review_v2 must persist all Plan-2 fields correctly."""
        sid = create_session(db_conn, "proj")
        draft_id = add_plan_draft(db_conn, sid, "plan content", "sonnet")
        db_conn.commit()

        rev_id = add_review_v2(
            db_conn,
            session_id=sid,
            round_number=1,
            verdict="NO_GO",
            issues_json='[{"severity":"critical","description":"Missing error handling"}]',
            summary="Plan needs error handling",
            raw_response="<verdict>NO_GO</verdict>",
            reviewer_model="gpt-5.4",
            cost=0.0042,
            input_tokens=1500,
            output_tokens=300,
            draft_id=draft_id,
        )
        db_conn.commit()
        assert rev_id is not None

        row = db_conn.execute("SELECT * FROM reviews WHERE id = ?", (rev_id,)).fetchone()
        assert row["session_id"] == sid
        assert row["round_number"] == 1
        assert row["verdict"] == "NO_GO"
        assert "Missing error handling" in row["issues_json"]
        assert row["summary"] == "Plan needs error handling"
        assert row["reviewer_model"] == "gpt-5.4"
        assert abs(row["cost"] - 0.0042) < 1e-9
        assert row["input_tokens"] == 1500
        assert row["output_tokens"] == 300
        assert row["draft_id"] == draft_id

    def test_add_review_v2_without_draft_id(self, db_conn):
        """draft_id is optional for v2 reviews."""
        sid = create_session(db_conn, "proj")
        db_conn.commit()

        rev_id = add_review_v2(
            db_conn,
            session_id=sid,
            round_number=1,
            verdict="GO",
            issues_json="[]",
            summary="Looks good",
            raw_response="GO",
            reviewer_model="gpt-5.4",
            cost=0.001,
            input_tokens=100,
            output_tokens=10,
        )
        db_conn.commit()
        row = db_conn.execute("SELECT * FROM reviews WHERE id = ?", (rev_id,)).fetchone()
        assert row["draft_id"] is None

    def test_add_review_v2_requires_round_number(self, db_conn):
        """Passing round_number=None must raise ValueError."""
        sid = create_session(db_conn, "proj")
        db_conn.commit()

        with pytest.raises(ValueError, match="round_number is required"):
            add_review_v2(
                db_conn,
                session_id=sid,
                round_number=None,
                verdict="GO",
                issues_json="[]",
                summary="",
                raw_response="",
                reviewer_model="gpt-5.4",
                cost=0,
                input_tokens=0,
                output_tokens=0,
            )


# ---------------------------------------------------------------------------
# 4. Old add_review still works (writes NULL new columns)
# ---------------------------------------------------------------------------

class TestLegacyAddReview:
    def test_old_add_review_writes_null_new_columns(self, db_conn):
        """The Plan-1 add_review function must still insert rows without error."""
        sid = create_session(db_conn, "proj")
        draft_id = add_plan_draft(db_conn, sid, "draft", "sonnet")
        db_conn.commit()

        rev_id = add_review(db_conn, sid, draft_id, "approve", "LGTM")
        db_conn.commit()

        row = db_conn.execute("SELECT * FROM reviews WHERE id = ?", (rev_id,)).fetchone()
        assert row["verdict"] == "approve"
        assert row["content"] == "LGTM"
        # New columns must be NULL.
        assert row["round_number"] is None
        assert row["issues_json"] is None
        assert row["reviewer_model"] is None


# ---------------------------------------------------------------------------
# 5. UNIQUE constraint on (session_id, round_number) — with multiple NULLs
# ---------------------------------------------------------------------------

class TestUniqueConstraint:
    def test_duplicate_round_number_raises(self, db_conn):
        """Two v2 reviews with the same session+round must raise IntegrityError."""
        sid = create_session(db_conn, "proj")
        db_conn.commit()

        add_review_v2(
            db_conn, sid, 1, "GO", "[]", "ok", "raw", "gpt-5.4", 0, 0, 0
        )
        db_conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            add_review_v2(
                db_conn, sid, 1, "NO_GO", "[]", "nope", "raw2", "gpt-5.4", 0, 0, 0
            )

    def test_multiple_null_round_numbers_are_allowed(self, db_conn):
        """Legacy rows (round_number=NULL) must not trigger the UNIQUE constraint."""
        sid = create_session(db_conn, "proj")
        draft_id = add_plan_draft(db_conn, sid, "d", "sonnet")
        db_conn.commit()

        # Insert multiple legacy rows (round_number=NULL).
        add_review(db_conn, sid, draft_id, "approve", "first")
        add_review(db_conn, sid, draft_id, "reject", "second")
        db_conn.commit()  # Must not raise.

        count = db_conn.execute(
            "SELECT COUNT(*) FROM reviews WHERE session_id = ? AND round_number IS NULL",
            (sid,),
        ).fetchone()[0]
        assert count == 2


# ---------------------------------------------------------------------------
# 6. review_dispositions CRUD
# ---------------------------------------------------------------------------

class TestReviewDispositionsCRUD:
    def _create_review(self, db_conn):
        sid = create_session(db_conn, "proj")
        db_conn.commit()
        rev_id = add_review_v2(
            db_conn, sid, 1, "NO_GO", "[]", "summary", "raw", "gpt-5.4", 0, 0, 0
        )
        db_conn.commit()
        return sid, rev_id

    def test_add_and_get_dispositions(self, db_conn):
        """Dispositions can be added and retrieved by review_id."""
        _, rev_id = self._create_review(db_conn)

        add_disposition(db_conn, rev_id, 0, "ACCEPT", "Will fix")
        add_disposition(db_conn, rev_id, 1, "DEFER", "Out of scope")
        add_disposition(db_conn, rev_id, 2, "REJECT", "Not applicable")
        db_conn.commit()

        disps = get_dispositions(db_conn, rev_id)
        assert len(disps) == 3
        assert disps[0]["disposition"] == "ACCEPT"
        assert disps[1]["disposition"] == "DEFER"
        assert disps[2]["disposition"] == "REJECT"
        assert disps[0]["rationale"] == "Will fix"

    def test_disposition_without_rationale(self, db_conn):
        """rationale is optional and may be None."""
        _, rev_id = self._create_review(db_conn)
        add_disposition(db_conn, rev_id, 0, "ACCEPT")
        db_conn.commit()

        disps = get_dispositions(db_conn, rev_id)
        assert disps[0]["rationale"] is None

    def test_invalid_disposition_value_raises(self, db_conn):
        """Disposition must be one of ACCEPT, DEFER, REJECT."""
        _, rev_id = self._create_review(db_conn)
        with pytest.raises(sqlite3.IntegrityError):
            add_disposition(db_conn, rev_id, 0, "IGNORE")
            db_conn.commit()


# ---------------------------------------------------------------------------
# 7. get_all_dispositions returns across rounds
# ---------------------------------------------------------------------------

class TestGetAllDispositions:
    def test_get_all_dispositions_across_rounds(self, db_conn):
        """get_all_dispositions must aggregate dispositions from all rounds."""
        sid = create_session(db_conn, "proj")
        db_conn.commit()

        rev1_id = add_review_v2(
            db_conn, sid, 1, "NO_GO", "[]", "r1", "raw", "gpt-5.4", 0, 0, 0
        )
        db_conn.commit()
        add_disposition(db_conn, rev1_id, 0, "ACCEPT", "round-1-accept")
        add_disposition(db_conn, rev1_id, 1, "DEFER", "round-1-defer")
        db_conn.commit()

        rev2_id = add_review_v2(
            db_conn, sid, 2, "GO", "[]", "r2", "raw", "gpt-5.4", 0, 0, 0
        )
        db_conn.commit()
        add_disposition(db_conn, rev2_id, 0, "ACCEPT", "round-2-accept")
        db_conn.commit()

        all_disps = get_all_dispositions(db_conn, sid)
        assert len(all_disps) == 3

        # Ordered by round_number then issue_index.
        assert all_disps[0]["round_number"] == 1
        assert all_disps[0]["issue_index"] == 0
        assert all_disps[1]["round_number"] == 1
        assert all_disps[1]["issue_index"] == 1
        assert all_disps[2]["round_number"] == 2

    def test_get_all_dispositions_empty_when_no_reviews(self, db_conn):
        sid = create_session(db_conn, "proj")
        db_conn.commit()
        assert get_all_dispositions(db_conn, sid) == []


# ---------------------------------------------------------------------------
# 8. get_review_by_round
# ---------------------------------------------------------------------------

class TestGetReviewByRound:
    def test_get_review_by_round_found(self, db_conn):
        sid = create_session(db_conn, "proj")
        db_conn.commit()
        add_review_v2(db_conn, sid, 1, "GO", "[]", "ok", "raw", "gpt-5.4", 0, 0, 0)
        db_conn.commit()

        row = get_review_by_round(db_conn, sid, 1)
        assert row is not None
        assert row["verdict"] == "GO"
        assert row["round_number"] == 1

    def test_get_review_by_round_not_found(self, db_conn):
        sid = create_session(db_conn, "proj")
        db_conn.commit()
        assert get_review_by_round(db_conn, sid, 99) is None


# ---------------------------------------------------------------------------
# 9. set_schema_version / get_schema_version helpers
# ---------------------------------------------------------------------------

class TestSchemaVersionHelpers:
    def test_get_schema_version_returns_current(self, db_conn):
        assert get_schema_version(db_conn) == CURRENT_SCHEMA_VERSION

    def test_set_and_get_schema_version(self, db_conn):
        set_schema_version(db_conn, 99)
        db_conn.commit()
        assert get_schema_version(db_conn) == 99
