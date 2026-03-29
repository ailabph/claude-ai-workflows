"""Review workflow orchestration — shared between CLI and TUI.

Extracts the review setup/run/finalize lifecycle from ``cli.py`` into a
reusable ``ReviewWorkflow`` class with three phases:

- ``prepare()``  — validates session, resolves config, builds reviewer
- ``run()``      — calls ``engine.run()`` via ``asyncio.run()``
- ``finalize()`` — advances phase, exports artifacts, .kafra handoff

No stdout in any method — callers decide how to present results.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from typing import Optional

from planner_auto.db import (
    get_latest_plan_draft,
    get_review_by_round,
    get_session,
    get_session_config,
    save_session_config,
    update_session_status,
)
from planner_auto.errors import CommandNotAllowedError, SessionNotFoundError
from planner_auto.export import export_review_artifacts, kafra_handoff
from planner_auto.loop.convergence import detect_complexity, get_max_rounds
from planner_auto.loop.engine import LoopResult, ReviewLoopEngine
from planner_auto.reviewer.direct_api import DirectAPIAdapter
from planner_auto.session import SessionManager
from planner_auto.state import Phase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ReviewOpts:
    """Options for the review command, mirroring CLI flags."""

    fast: bool = False
    max_rounds: Optional[int] = None
    no_review_history: bool = False
    reviewer_model: str = "gpt-5.4"
    reviewer_reasoning: str = "high"
    complexity_override: Optional[str] = None
    repo_root: Optional[str] = None
    verbosity: str = "quiet"
    debug: bool = False


@dataclass
class PreparedReview:
    """All resolved values from ``prepare()`` — everything needed to run the loop."""

    engine_config: dict
    current_plan: str
    max_rounds: int
    complexity: str
    base_config: dict
    resolved_repo_root: Optional[str]
    fast: bool
    reviewer: DirectAPIAdapter
    planner_model: str
    db_path: Optional[str] = None
    session_id: str = ""


@dataclass
class FinalizeResult:
    """Result of ``finalize()``."""

    converged: bool
    phase: str
    export_paths: list[str] = field(default_factory=list)
    kafra_path: Optional[str] = None
    blocker_text: Optional[str] = None
    total_cost: float = 0.0
    total_rounds: int = 0
    stop_reason: str = ""


# ---------------------------------------------------------------------------
# ReviewWorkflow
# ---------------------------------------------------------------------------

class ReviewWorkflow:
    """Shared review orchestration logic for CLI and TUI.

    All methods are stateless — they operate on the provided ``conn`` and
    parameters, producing return values with no stdout.
    """

    @staticmethod
    def prepare(
        conn: sqlite3.Connection,
        session_id: str,
        opts: ReviewOpts,
        *,
        claude_backend: str = "direct",
    ) -> PreparedReview:
        """Validate session and resolve all config for the review loop.

        Uses the caller's ``conn`` for DB access.  Does NOT create the engine.

        Args:
            conn: SQLite connection (caller-owned).
            session_id: Session ID.
            opts: Review options.
            claude_backend: Backend for Claude revision calls.

        Returns:
            ``PreparedReview`` with all resolved values.

        Raises:
            SessionNotFoundError: If session doesn't exist.
            CommandNotAllowedError: If review is not allowed.
            ValueError: If no plan draft exists.
        """
        session = get_session(conn, session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        sm = SessionManager(conn)
        sm.check_command(session_id, "review")

        # Advance PLANNING → REVIEW if needed.
        if session["phase"] == Phase.PLANNING.value:
            sm.advance_phase(session_id, Phase.REVIEW.value)

        # Require a plan draft.
        draft = get_latest_plan_draft(conn, session_id)
        if draft is None:
            raise ValueError("No plan draft found. Run 'generate' first.")
        current_plan = draft["content"]

        # Determine complexity and max rounds.
        complexity = opts.complexity_override or detect_complexity(conn, session_id)
        max_rounds = opts.max_rounds
        if max_rounds is None:
            max_rounds = get_max_rounds(complexity, fast=opts.fast)

        # Prompt mode: fast uses "basic", normal uses "keep_trim".
        prompt_mode = "basic" if opts.fast else "keep_trim"
        review_history_enabled = not opts.no_review_history
        validate_fb = True

        if opts.fast:
            review_history_enabled = False
            validate_fb = False

        # Load existing config.
        base_config: dict = {}
        existing_config_row = get_session_config(conn, session_id)
        if existing_config_row:
            try:
                base_config = json.loads(existing_config_row["config_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        # Resolve repo_root.
        resolved_repo_root = (
            os.path.abspath(opts.repo_root)
            if opts.repo_root is not None
            else base_config.get("repo_root")
        )

        # Save review config snapshot.
        review_config = {
            **base_config,
            "reviewer_model": opts.reviewer_model,
            "reasoning_effort": opts.reviewer_reasoning,
            "prompt_mode": prompt_mode,
            "review_history": review_history_enabled,
            "validate_feedback": validate_fb,
            "filter_severity": ["critical", "major"],
            "keep_trim": not opts.fast,
            "fast_mode": opts.fast,
            "complexity": complexity,
            "max_rounds": max_rounds,
            "mode": "fast" if opts.fast else "standard",
            "repo_root": resolved_repo_root,
        }
        save_session_config(conn, session_id, json.dumps(review_config))
        conn.commit()

        # Build reviewer adapter.
        reviewer = DirectAPIAdapter(
            model=opts.reviewer_model,
            reasoning_effort=opts.reviewer_reasoning,
            prompt_mode=prompt_mode,
        )

        # Resolve planner model.
        planner_model = base_config.get("model") or base_config.get(
            "model_default", "claude-sonnet-4-6"
        )

        # Build engine config.
        engine_config: dict = {
            "validate_feedback": validate_fb,
            "filter_severity": ["critical", "major"],
            "review_history": review_history_enabled,
            "effort": "medium",
            "thinking": True,
            "max_turns": 0,
            "verbosity": opts.verbosity,
            "claude_backend": claude_backend,
        }

        # Resolve db_path from the connection (for TUI worker thread).
        db_path: Optional[str] = None
        try:
            # file-based connections expose the path; :memory: does not
            cursor = conn.execute("PRAGMA database_list")
            for row in cursor:
                if row[1] == "main" and row[2]:
                    db_path = row[2]
                    break
        except Exception:
            pass

        return PreparedReview(
            engine_config=engine_config,
            current_plan=current_plan,
            max_rounds=max_rounds,
            complexity=complexity,
            base_config=base_config,
            resolved_repo_root=resolved_repo_root,
            fast=opts.fast,
            reviewer=reviewer,
            planner_model=planner_model,
            db_path=db_path,
            session_id=session_id,
        )

    @staticmethod
    def run(engine: ReviewLoopEngine, current_plan: str, max_rounds: int) -> LoopResult:
        """Execute the review loop synchronously via ``asyncio.run()``.

        The caller provides the engine (with its own connection).

        Args:
            engine: A fully configured ``ReviewLoopEngine``.
            current_plan: Plan text to review.
            max_rounds: Maximum review rounds.

        Returns:
            ``LoopResult`` from the engine.
        """
        return asyncio.run(engine.run(current_plan, max_rounds=max_rounds))

    @staticmethod
    def finalize(
        conn: sqlite3.Connection,
        session_id: str,
        result: LoopResult,
        prepared: PreparedReview,
    ) -> FinalizeResult:
        """Post-loop finalization: advance phase, export, handoff.

        Uses the caller's ``conn``.

        Args:
            conn: SQLite connection (caller-owned).
            session_id: Session ID.
            result: The ``LoopResult`` from the engine run.
            prepared: The ``PreparedReview`` from ``prepare()``.

        Returns:
            ``FinalizeResult`` with phase, paths, and blocker info.
        """
        sm = SessionManager(conn)

        if result.converged:
            # Advance REVIEW → COMPLETE.
            try:
                sm.advance_phase(session_id, Phase.COMPLETE.value)
            except Exception:
                logger.warning("Failed to advance phase to COMPLETE", exc_info=True)

            update_session_status(conn, session_id, "COMPLETE")
            conn.commit()

            # Export review artifacts.
            export_paths = export_review_artifacts(
                session_id, conn, fast_mode=prepared.fast
            )

            # .kafra handoff.
            project = prepared.base_config.get("project", session_id)
            kafra_path = kafra_handoff(
                session_id,
                conn,
                result.final_plan,
                project,
                repo_root=prepared.resolved_repo_root,
            )

            return FinalizeResult(
                converged=True,
                phase=Phase.COMPLETE.value,
                export_paths=export_paths,
                kafra_path=kafra_path,
                total_cost=result.total_cost,
                total_rounds=result.rounds,
                stop_reason=result.stop_reason,
            )
        else:
            # cap_with_criticals: pause with a blocker.
            blocker_q = "Review cap reached with critical issues remaining."
            final_review = get_review_by_round(
                conn, session_id, result.final_round_number
            )
            if final_review and final_review["issues_json"]:
                try:
                    issues = json.loads(final_review["issues_json"])
                    criticals = [
                        i.get("description", "")
                        for i in issues
                        if i.get("severity") == "critical"
                    ]
                    if criticals:
                        blocker_q = (
                            "Review cap reached. Critical issues remaining:\n"
                            + "\n".join(f"- {c}" for c in criticals)
                        )
                except (json.JSONDecodeError, TypeError):
                    pass

            sm.pause_with_blocker(session_id, "reviewer", blocker_q)

            return FinalizeResult(
                converged=False,
                phase=Phase.REVIEW.value,
                blocker_text=blocker_q,
                total_cost=result.total_cost,
                total_rounds=result.rounds,
                stop_reason=result.stop_reason,
            )
