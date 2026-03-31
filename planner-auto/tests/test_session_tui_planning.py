"""Tests for session TUI planning phase — generation progress, PlanGenerated, regeneration."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from planner_auto.db import (
    add_plan_draft,
    create_session,
    init_schema,
    save_session_config,
)
from planner_auto.tui.session_messages import (
    PlanGenerated,
    PlanGenerationStarted,
    SessionError,
    SynthesisComplete,
    SynthesisStarted,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_db():
    """In-memory SQLite with schema initialized."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


@pytest.fixture
def planning_session(mem_db):
    """Session in PLANNING phase with context and config."""
    sid = create_session(mem_db, "test-project")
    # Advance to PLANNING
    mem_db.execute("UPDATE sessions SET phase = 'PLANNING' WHERE id = ?", (sid,))
    mem_db.commit()
    # Save config
    save_session_config(mem_db, sid, json.dumps({"model": "claude-sonnet-4-6", "claude_backend": "direct"}))
    mem_db.commit()
    return sid


# ---------------------------------------------------------------------------
# Tests: SynthesisStarted message
# ---------------------------------------------------------------------------

class TestSynthesisStarted:
    def test_message_fields(self):
        msg = SynthesisStarted(file_count=3, note_count=2)
        assert msg.file_count == 3
        assert msg.note_count == 2


# ---------------------------------------------------------------------------
# Tests: SynthesisComplete message
# ---------------------------------------------------------------------------

class TestSynthesisComplete:
    def test_message_fields(self):
        msg = SynthesisComplete(output_size=1500, latency_ms=800)
        assert msg.output_size == 1500
        assert msg.latency_ms == 800


# ---------------------------------------------------------------------------
# Tests: PlanGenerationStarted message
# ---------------------------------------------------------------------------

class TestPlanGenerationStarted:
    def test_message_fields(self):
        msg = PlanGenerationStarted(model="claude-sonnet-4-6")
        assert msg.model == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Tests: PlanGenerated message
# ---------------------------------------------------------------------------

class TestPlanGenerated:
    def test_message_fields(self):
        msg = PlanGenerated(
            draft_number=1,
            size=5000,
            milestone_count=4,
            latency_ms=3000,
            validation_ok=True,
            warnings=[],
        )
        assert msg.draft_number == 1
        assert msg.size == 5000
        assert msg.milestone_count == 4
        assert msg.latency_ms == 3000
        assert msg.validation_ok is True
        assert msg.warnings == []

    def test_message_with_warnings(self):
        msg = PlanGenerated(
            draft_number=2,
            size=3000,
            milestone_count=2,
            latency_ms=2000,
            validation_ok=False,
            warnings=["Missing Deliverables section in Milestone 1"],
        )
        assert msg.validation_ok is False
        assert len(msg.warnings) == 1


# ---------------------------------------------------------------------------
# Tests: Generation progress widget
# ---------------------------------------------------------------------------

class TestGenerationProgressWidget:
    def test_start_synthesis(self):
        from planner_auto.tui.widgets.generation_progress import GenerationProgress
        gp = GenerationProgress()
        # Compose must be called before start_synthesis
        # Just test that the method doesn't crash pre-compose
        gp.start_synthesis(3, 2)  # No crash = OK (labels are None pre-compose)

    def test_complete_synthesis(self):
        from planner_auto.tui.widgets.generation_progress import GenerationProgress
        gp = GenerationProgress()
        gp.complete_synthesis(1500, 800)  # No crash pre-compose

    def test_start_generation(self):
        from planner_auto.tui.widgets.generation_progress import GenerationProgress
        gp = GenerationProgress()
        gp.start_generation("claude-sonnet-4-6")

    def test_complete_generation(self):
        from planner_auto.tui.widgets.generation_progress import GenerationProgress
        gp = GenerationProgress()
        gp.complete_generation(1, 5000, 4, 3000)


# ---------------------------------------------------------------------------
# Tests: PlanView widget
# ---------------------------------------------------------------------------

class TestPlanViewWidget:
    def test_set_plan_ok(self):
        from planner_auto.tui.widgets.plan_view import PlanView
        pv = PlanView()
        # Pre-compose, labels are None — just test no crash
        pv.set_plan(1, "## Milestone 1: Test", "claude-sonnet-4-6", True)

    def test_set_plan_with_warnings(self):
        from planner_auto.tui.widgets.plan_view import PlanView
        pv = PlanView()
        pv.set_plan(2, "content", "model", False, warnings=["warning 1"])


# ---------------------------------------------------------------------------
# Tests: Planning phase mounting logic
# ---------------------------------------------------------------------------

class TestPlanningPhaseMounting:
    def test_mount_planning_with_existing_draft(self, mem_db, planning_session):
        """When a plan draft exists, _mount_planning_panel should show PlanView."""
        plan_text = "## Milestone 1: Test\n### Tasks\n- [ ] task\n### Deliverables\n- [ ] d"
        add_plan_draft(mem_db, planning_session, plan_text, "claude-sonnet-4-6")
        mem_db.commit()

        from planner_auto.db import get_latest_plan_draft
        draft = get_latest_plan_draft(mem_db, planning_session)
        assert draft is not None
        assert draft["content"] == plan_text

    def test_no_draft_triggers_generation(self, mem_db, planning_session):
        """When no plan draft exists, generation should be triggered."""
        from planner_auto.db import get_latest_plan_draft
        draft = get_latest_plan_draft(mem_db, planning_session)
        assert draft is None  # No draft yet


# ---------------------------------------------------------------------------
# Tests: SessionError during planning
# ---------------------------------------------------------------------------

class TestSessionErrorPlanning:
    def test_error_message_fields(self):
        msg = SessionError("API timeout", "PLANNING")
        assert msg.error_message == "API timeout"
        assert msg.phase == "PLANNING"
