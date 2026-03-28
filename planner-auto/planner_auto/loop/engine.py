"""Review-fix loop engine for planner-auto Plan 2.

``ReviewLoopEngine.run()`` executes the GPT review → feedback validation →
Claude revision cycle until one of the three stop conditions is met:

1. Reviewer returns GO             → stop_reason = "go"          (converged)
2. Round cap hit, zero criticals   → stop_reason = "cap_no_criticals"  (converged)
3. Round cap hit, criticals remain → stop_reason = "cap_with_criticals" (not converged)

Each round exports interleaved artifact files:
  ``a-{2N:02d}-review.md``  (reviewer output)
  ``a-{2N+1:02d}-plan.md``  (revised plan)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from planner_auto.db import (
    add_plan_draft,
    add_review_v2,
    get_latest_plan_draft,
)
from planner_auto.export import DEFAULT_SESSIONS_DIR
from planner_auto.loop.feedback import validate_feedback
from planner_auto.loop.history import build_review_context, filter_issues
from planner_auto.reviewer.contract import ReviewerContract, ReviewerResponse, Severity, Verdict
from planner_auto.sdk_wrapper import query_claude

logger = logging.getLogger("planner-auto.loop.engine")

# ---------------------------------------------------------------------------
# Revision prompt templates
# ---------------------------------------------------------------------------

_REVISION_SYSTEM_PROMPT = """\
You are an expert software architect revising an implementation plan based
on peer-review feedback.

Your goal is to address each issue listed below while keeping the plan
concise and well-scoped.  Do NOT add features or milestones that are not
required to fix the listed issues.  Preserve all existing milestones that
are not affected by the issues.

Return the complete revised plan text only — no preamble, no commentary."""

_REVISION_USER_TEMPLATE = """\
## Current Plan

{current_plan}

## Issues to Address

{issues_block}
{keep_block}{trim_block}
## Instructions

Address each issue above. Do not add scope beyond what's needed to address \
accepted issues. Keep the plan concise."""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class LoopResult:
    """Result of a completed ``ReviewLoopEngine.run()`` call.

    Attributes:
        converged: ``True`` if the loop ended with GO or cap-with-no-criticals;
            ``False`` if critical issues remain at the cap.
        rounds: Number of review rounds executed.
        final_plan: Text of the final (best) plan draft.
        final_draft_number: ``plan_drafts.draft_number`` of the final draft.
        total_cost: Estimated total API cost in USD (reviewer + revisions).
        round_details: List of per-round dicts with keys ``round``,
            ``verdict``, ``issue_count``, ``review_id``.
        stop_reason: One of ``"go"``, ``"cap_no_criticals"``,
            ``"cap_with_criticals"``.
    """
    converged: bool
    rounds: int
    final_plan: str
    final_draft_number: int
    total_cost: float
    round_details: list = field(default_factory=list)
    stop_reason: str = "cap_with_criticals"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ReviewLoopEngine:
    """Orchestrates the GPT review → feedback validation → Claude revision loop.

    Args:
        conn: SQLite connection (must have schema v2 applied).
        session_id: Session ID whose drafts and reviews are managed.
        reviewer: Any :class:`ReviewerContract` implementation.
        planner_model: Claude model identifier used for plan revisions.
        config: Optional configuration dict.  Recognised keys:

            ``validate_feedback`` (bool, default ``False``)
              Whether to run :func:`validate_feedback` after each review.

            ``filter_severity`` (list[str], default ``["critical", "major"]``)
              Which severity levels to pass to the revision prompt.

            ``effort`` (str, optional)
              Passed to :func:`query_claude` for revision calls.

            ``thinking`` (bool, default ``False``)
              Passed to :func:`query_claude` for revision calls.

            ``max_turns`` (int, optional)
              Passed to :func:`query_claude` for revision calls.

            ``output_dir`` (str, optional)
              Directory to write artifact files.  Defaults to
              ``~/.planner-auto/sessions/<session_id>/``.
    """

    def __init__(
        self,
        conn,
        session_id: str,
        reviewer: ReviewerContract,
        planner_model: str,
        config: Optional[dict] = None,
    ) -> None:
        self.conn = conn
        self.session_id = session_id
        self.reviewer = reviewer
        self.planner_model = planner_model
        self.config: dict = config or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, current_plan: str, max_rounds: int) -> LoopResult:
        """Execute the review-fix loop.

        Args:
            current_plan: Text of the plan to review in round 1.
            max_rounds: Maximum number of review rounds before stopping.

        Returns:
            :class:`LoopResult` describing why and how the loop ended.
        """
        total_cost = 0.0
        round_details: list[dict] = []
        stop_reason = "cap_with_criticals"
        final_plan = current_plan
        final_draft_number = self._latest_draft_number()
        prev_plan_text: Optional[str] = None  # plan reviewed in the previous round

        for round_num in range(1, max_rounds + 1):
            logger.info(
                "Session %s — starting review round %d/%d",
                self.session_id, round_num, max_rounds,
            )

            # --- Step 1: build history context (None for round 1) ----------
            if self.config.get("review_history", True):
                history_context = build_review_context(
                    self.conn, self.session_id, round_num,
                    prev_plan_text=prev_plan_text,
                )
            else:
                history_context = None

            # --- Step 2: call reviewer -------------------------------------
            review_response: ReviewerResponse = await self.reviewer.review(
                current_plan, history_context
            )
            logger.info(
                "Round %d verdict: %s (%d issues)",
                round_num, review_response.verdict.value, len(review_response.issues),
            )

            # --- Step 3: store review in DB --------------------------------
            issues_json = json.dumps(
                [i.to_dict() for i in review_response.issues], ensure_ascii=False
            )
            review_id = add_review_v2(
                self.conn,
                session_id=self.session_id,
                round_number=round_num,
                verdict=review_response.verdict.value,
                issues_json=issues_json,
                summary=review_response.summary,
                raw_response=review_response.to_json(),
                reviewer_model=None,
                cost=None,
                input_tokens=None,
                output_tokens=None,
            )
            self.conn.commit()

            # --- Step 4: export review artifact ----------------------------
            self._write_review_artifact(round_num, review_response)

            # --- Step 5: record round detail -------------------------------
            round_detail: dict = {
                "round": round_num,
                "verdict": review_response.verdict.value,
                "issue_count": len(review_response.issues),
                "review_id": review_id,
            }

            # --- Step 6: apply stop policy ---------------------------------
            if review_response.verdict == Verdict.GO:
                stop_reason = "go"
                round_details.append(round_detail)
                break

            if round_num == max_rounds:
                has_criticals = any(
                    i.severity == Severity.CRITICAL for i in review_response.issues
                )
                stop_reason = (
                    "cap_with_criticals" if has_criticals else "cap_no_criticals"
                )
                round_details.append(round_detail)
                break

            # --- Step 7: filter issues by severity -------------------------
            filtered_issues = filter_issues(
                review_response.issues,
                self.config.get("filter_severity", ["critical", "major"]),
            )

            # --- Step 8: optional feedback validation ----------------------
            if self.config.get("validate_feedback", False):
                validated = await validate_feedback(
                    current_plan,
                    ReviewerResponse(
                        verdict=review_response.verdict,
                        issues=filtered_issues,  # validate only filtered issues
                        summary=review_response.summary,
                        keep=review_response.keep,
                        trim=review_response.trim,
                    ),
                    self.planner_model,
                    self.conn,
                    review_id,
                )
                self.conn.commit()
                filtered_issues = validated.issues  # only ACCEPT issues

            # --- Step 9: build revision prompt -----------------------------
            revision_prompt = _build_revision_user_prompt(
                current_plan, filtered_issues, review_response
            )

            # --- Step 10: call Claude for revision -------------------------
            revised_text = await query_claude(
                messages=[{"role": "user", "content": revision_prompt}],
                system_prompt=_REVISION_SYSTEM_PROMPT,
                model=self.planner_model,
                effort=self.config.get("effort"),
                thinking=self.config.get("thinking", False),
                max_turns=self.config.get("max_turns"),
            )

            # --- Step 11: store revised draft ------------------------------
            draft_row_id = add_plan_draft(
                self.conn, self.session_id, revised_text, self.planner_model
            )
            self.conn.commit()

            # Retrieve the draft_number for the newly stored draft.
            draft_row = self.conn.execute(
                "SELECT draft_number FROM plan_drafts WHERE id = ?", (draft_row_id,)
            ).fetchone()
            new_draft_number: int = draft_row["draft_number"] if draft_row else 0
            final_draft_number = new_draft_number
            final_plan = revised_text

            # --- Step 12: export revised plan artifact ---------------------
            self._write_plan_artifact(round_num, revised_text)

            # Advance loop state.
            prev_plan_text = current_plan
            current_plan = revised_text
            round_detail["draft_number"] = new_draft_number
            round_details.append(round_detail)

        return LoopResult(
            converged=(stop_reason in ("go", "cap_no_criticals")),
            rounds=len(round_details),
            final_plan=final_plan,
            final_draft_number=final_draft_number,
            total_cost=total_cost,
            round_details=round_details,
            stop_reason=stop_reason,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _latest_draft_number(self) -> int:
        """Return the draft_number of the most recent plan draft, or 0."""
        draft = get_latest_plan_draft(self.conn, self.session_id)
        return draft["draft_number"] if draft else 0

    def _output_dir(self) -> Optional[str]:
        """Resolve the output directory for artifact files."""
        output_dir = self.config.get("output_dir")
        if output_dir:
            return str(output_dir)
        return os.path.join(DEFAULT_SESSIONS_DIR, self.session_id)

    def _write_review_artifact(self, round_num: int, review: ReviewerResponse) -> None:
        """Write ``a-{2*round_num:02d}-review.md`` to the output directory."""
        out_dir = self._output_dir()
        if not out_dir:
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
            filename = f"a-{2 * round_num:02d}-review.md"
            path = os.path.join(out_dir, filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write(_format_review_artifact(round_num, review))
            logger.debug("Wrote review artifact: %s", path)
        except OSError as exc:
            logger.warning("Failed to write review artifact: %s", exc)

    def _write_plan_artifact(self, round_num: int, plan_text: str) -> None:
        """Write ``a-{2*round_num+1:02d}-plan.md`` to the output directory."""
        out_dir = self._output_dir()
        if not out_dir:
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
            filename = f"a-{2 * round_num + 1:02d}-plan.md"
            path = os.path.join(out_dir, filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write(plan_text)
            logger.debug("Wrote plan artifact: %s", path)
        except OSError as exc:
            logger.warning("Failed to write plan artifact: %s", exc)


# ---------------------------------------------------------------------------
# Prompt / artifact formatting helpers
# ---------------------------------------------------------------------------

def _build_revision_user_prompt(
    current_plan: str,
    filtered_issues: list,
    review: ReviewerResponse,
) -> str:
    """Build the user-turn message for the Claude revision call."""
    if not filtered_issues:
        issues_block = "(No specific issues — reviewer suggested minor improvements only.)"
    else:
        issue_lines: list[str] = []
        for idx, issue in enumerate(filtered_issues, 1):
            guidance = (
                f"\n   → {issue.resolution_guidance}" if issue.resolution_guidance else ""
            )
            issue_lines.append(
                f"{idx}. [{issue.severity.value.upper()}] {issue.description}"
                f"\n   Rationale: {issue.rationale}{guidance}"
            )
        issues_block = "\n".join(issue_lines)

    keep_block = ""
    if review.keep:
        keep_lines = "\n".join(f"  - {k}" for k in review.keep)
        keep_block = f"\n## Strengths to Preserve\n{keep_lines}\n"

    trim_block = ""
    if review.trim:
        trim_lines = "\n".join(f"  - {t}" for t in review.trim)
        trim_block = f"\n## Scope to Trim\n{trim_lines}\n"

    return _REVISION_USER_TEMPLATE.format(
        current_plan=current_plan,
        issues_block=issues_block,
        keep_block=keep_block,
        trim_block=trim_block,
    )


def _format_review_artifact(round_num: int, review: ReviewerResponse) -> str:
    """Format a review response as a Markdown artifact file."""
    lines = [
        f"# Review — Round {round_num}",
        "",
        f"**Verdict:** {review.verdict.value}",
        "",
    ]
    if review.summary:
        lines += ["## Summary", "", review.summary, ""]

    if review.issues:
        lines.append("## Issues")
        lines.append("")
        for i, issue in enumerate(review.issues, 1):
            lines.append(
                f"### {i}. [{issue.severity.value.upper()}] {issue.description}"
            )
            lines.append(f"**Rationale:** {issue.rationale}")
            if issue.resolution_guidance:
                lines.append(f"**Guidance:** {issue.resolution_guidance}")
            if issue.target_section:
                lines.append(f"**Section:** {issue.target_section}")
            lines.append("")

    if review.keep:
        lines += ["## Keep", ""] + [f"- {k}" for k in review.keep] + [""]
    if review.trim:
        lines += ["## Trim", ""] + [f"- {t}" for t in review.trim] + [""]

    return "\n".join(lines)
