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
import sys
import time
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

logger = logging.getLogger(__name__)

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
        final_round_number: The absolute round number of the last review
            executed (accounts for resumed sessions).
    """
    converged: bool
    rounds: int
    final_plan: str
    final_draft_number: int
    total_cost: float
    round_details: list = field(default_factory=list)
    stop_reason: str = "cap_with_criticals"
    final_round_number: int = 0


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

        # Determine the starting round: if resuming after a cap-hit pause,
        # skip already-stored rounds to avoid UNIQUE constraint violations.
        existing_max = self.conn.execute(
            "SELECT MAX(round_number) as max_round FROM reviews "
            "WHERE session_id = ? AND round_number IS NOT NULL",
            (self.session_id,),
        ).fetchone()
        start_round = ((existing_max["max_round"] or 0) + 1) if existing_max else 1

        for round_num in range(start_round, start_round + max_rounds):
            logger.info("Round %d starting (session=%s)", round_num, self.session_id)

            # --- Step 1: build history context (None for round 1) ----------
            if self.config.get("review_history", True):
                history_context = build_review_context(
                    self.conn, self.session_id, round_num,
                    prev_plan_text=prev_plan_text,
                )
            else:
                history_context = None

            history_context_size = len(history_context) if history_context else 0

            # --- Step 2: call reviewer (timed) -----------------------------
            _review_t0 = time.monotonic()
            review_response: ReviewerResponse = await self.reviewer.review(
                current_plan, history_context
            )
            review_latency_ms = int((time.monotonic() - _review_t0) * 1000)
            logger.info(
                "Round %d: %s, %d issues",
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
                raw_response=review_response.raw_text or review_response.to_json(),
                reviewer_model=getattr(review_response, "reviewer_model", None),
                cost=getattr(review_response, "cost", None),
                input_tokens=getattr(review_response, "input_tokens", None),
                output_tokens=getattr(review_response, "output_tokens", None),
            )
            self.conn.commit()

            # Accumulate review cost.
            round_review_cost = getattr(review_response, "cost", None) or 0.0
            total_cost += round_review_cost

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
            is_final_round = (
                review_response.verdict == Verdict.GO
                or round_num == start_round + max_rounds - 1
            )
            if review_response.verdict == Verdict.GO:
                stop_reason = "go"
                self._emit_progress(
                    round_num=round_num,
                    verdict=review_response.verdict.value,
                    issue_count=len(review_response.issues),
                    reviewer_model=getattr(review_response, "reviewer_model", None),
                    review_latency_ms=review_latency_ms,
                    input_tokens=getattr(review_response, "input_tokens", None),
                    output_tokens=getattr(review_response, "output_tokens", None),
                    review_cost=round_review_cost,
                    keep_count=len(review_response.keep),
                    trim_count=len(review_response.trim),
                    dispositions=None,
                    revision_model=None,
                    revision_latency_ms=None,
                    revision_cost=None,
                    prev_draft_size=len(current_plan),
                    new_draft_size=None,
                    history_context_size=history_context_size,
                    raw_gpt_response=review_response.raw_text,
                    history_context_text=history_context,
                    revision_prompt_text=None,
                    is_go=True,
                )
                round_details.append(round_detail)
                break

            if round_num == start_round + max_rounds - 1:
                has_criticals = any(
                    i.severity == Severity.CRITICAL for i in review_response.issues
                )
                stop_reason = (
                    "cap_with_criticals" if has_criticals else "cap_no_criticals"
                )
                self._emit_progress(
                    round_num=round_num,
                    verdict=review_response.verdict.value,
                    issue_count=len(review_response.issues),
                    reviewer_model=getattr(review_response, "reviewer_model", None),
                    review_latency_ms=review_latency_ms,
                    input_tokens=getattr(review_response, "input_tokens", None),
                    output_tokens=getattr(review_response, "output_tokens", None),
                    review_cost=round_review_cost,
                    keep_count=len(review_response.keep),
                    trim_count=len(review_response.trim),
                    dispositions=None,
                    revision_model=None,
                    revision_latency_ms=None,
                    revision_cost=None,
                    prev_draft_size=len(current_plan),
                    new_draft_size=None,
                    history_context_size=history_context_size,
                    raw_gpt_response=review_response.raw_text,
                    history_context_text=history_context,
                    revision_prompt_text=None,
                    is_go=False,
                )
                round_details.append(round_detail)
                break

            # --- Step 7: optional feedback validation ----------------------
            # Validate on the FULL issue list first so disposition indices
            # match the stored issues_json (see history.py:137).
            issues_for_revision = review_response.issues
            disposition_list: Optional[list[dict]] = None
            if self.config.get("validate_feedback", False):
                validated = await validate_feedback(
                    current_plan,
                    review_response,  # full issue list — indices match DB
                    self.planner_model,
                    self.conn,
                    review_id,
                    backend=self.config.get("claude_backend"),
                )
                self.conn.commit()
                issues_for_revision = validated.issues  # only ACCEPT issues
                # Build disposition list for verbose output.
                accept_descs = {i.description for i in validated.issues}
                disposition_list = [
                    {
                        "description": issue.description,
                        "disposition": "ACCEPT" if issue.description in accept_descs else "DEFER/REJECT",
                    }
                    for issue in review_response.issues
                ]

            # --- Step 8: filter issues by severity -------------------------
            filtered_issues = filter_issues(
                issues_for_revision,
                self.config.get("filter_severity", ["critical", "major"]),
            )

            # --- Step 9: build revision prompt -----------------------------
            revision_prompt = _build_revision_user_prompt(
                current_plan, filtered_issues, review_response
            )

            # --- Step 10: call Claude for revision (timed) -----------------
            _revision_t0 = time.monotonic()
            revised_text = await query_claude(
                messages=[{"role": "user", "content": revision_prompt}],
                system_prompt=_REVISION_SYSTEM_PROMPT,
                model=self.planner_model,
                effort=self.config.get("effort"),
                thinking=self.config.get("thinking", False),
                max_turns=self.config.get("max_turns"),
                backend=self.config.get("claude_backend", "direct"),
            )
            revision_latency_ms = int((time.monotonic() - _revision_t0) * 1000)

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

            # --- Step 13: emit per-round progress --------------------------
            self._emit_progress(
                round_num=round_num,
                verdict=review_response.verdict.value,
                issue_count=len(review_response.issues),
                reviewer_model=getattr(review_response, "reviewer_model", None),
                review_latency_ms=review_latency_ms,
                input_tokens=getattr(review_response, "input_tokens", None),
                output_tokens=getattr(review_response, "output_tokens", None),
                review_cost=round_review_cost,
                keep_count=len(review_response.keep),
                trim_count=len(review_response.trim),
                dispositions=disposition_list,
                revision_model=self.planner_model,
                revision_latency_ms=revision_latency_ms,
                revision_cost=None,  # SDK doesn't return cost directly
                prev_draft_size=len(current_plan),
                new_draft_size=len(revised_text),
                history_context_size=history_context_size,
                raw_gpt_response=review_response.raw_text,
                history_context_text=history_context,
                revision_prompt_text=revision_prompt,
                is_go=False,
            )

            # Advance loop state.
            prev_plan_text = current_plan
            current_plan = revised_text
            round_detail["draft_number"] = new_draft_number
            round_details.append(round_detail)

        final_round_num = round_details[-1]["round"] if round_details else 0
        logger.info("Loop stopped: %s", stop_reason)
        logger.info("Loop complete: %d rounds, $%.4f", len(round_details), total_cost)
        self._emit_final(
            stop_reason=stop_reason,
            total_rounds=len(round_details),
            total_cost=total_cost,
        )

        return LoopResult(
            converged=(stop_reason in ("go", "cap_no_criticals")),
            rounds=len(round_details),
            final_plan=final_plan,
            final_draft_number=final_draft_number,
            total_cost=total_cost,
            round_details=round_details,
            stop_reason=stop_reason,
            final_round_number=final_round_num,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Progress output
    # ------------------------------------------------------------------

    def _verbosity(self) -> str:
        """Return the configured verbosity level: 'quiet', 'verbose', or 'debug'."""
        return self.config.get("verbosity", "quiet")

    def _emit_progress(
        self,
        round_num: int,
        verdict: str,
        issue_count: int,
        *,
        reviewer_model: Optional[str] = None,
        review_latency_ms: Optional[int] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        review_cost: Optional[float] = None,
        keep_count: int = 0,
        trim_count: int = 0,
        dispositions: Optional[list] = None,
        revision_model: Optional[str] = None,
        revision_latency_ms: Optional[int] = None,
        revision_cost: Optional[float] = None,
        prev_draft_size: Optional[int] = None,
        new_draft_size: Optional[int] = None,
        history_context_size: int = 0,
        raw_gpt_response: Optional[str] = None,
        history_context_text: Optional[str] = None,
        revision_prompt_text: Optional[str] = None,
        is_go: bool = False,
    ) -> None:
        """Emit per-round progress to stdout.

        Output format depends on ``self.config["verbosity"]``:

        * ``"quiet"`` (default) — one line per round, headless-safe.
        * ``"verbose"`` — full round block with metrics and dispositions.
        * ``"debug"`` — all of verbose plus raw API content with warning.
        """
        v = self._verbosity()
        suffix = "" if is_go else " → revising..."
        headless_line = f"Round {round_num}: {verdict} ({issue_count} issues){suffix}"
        print(headless_line, flush=True)

        if v not in ("verbose", "debug"):
            return

        # --- Verbose block -------------------------------------------------
        print("─" * 60, flush=True)

        # Reviewer metrics
        model_str = reviewer_model or "unknown"
        latency_str = f"{review_latency_ms}ms" if review_latency_ms is not None else "?"
        tok_str = (
            f"{input_tokens}in/{output_tokens}out"
            if input_tokens is not None and output_tokens is not None
            else "?"
        )
        cost_str = f"${review_cost:.4f}" if review_cost is not None else "$?"
        print(
            f"  Reviewer: model={model_str}, latency={latency_str}, "
            f"tokens={tok_str}, cost={cost_str}",
            flush=True,
        )

        # Keep/trim counts
        print(f"  Keep: {keep_count} items  Trim: {trim_count} items", flush=True)

        # Per-issue dispositions
        if dispositions:
            for d in dispositions:
                disp = d.get("disposition", "")
                desc = d.get("description", "")[:80]
                print(f"    [{disp}] {desc}", flush=True)

        # Revision metrics (only when revision happened)
        if revision_model is not None:
            rev_latency_str = f"{revision_latency_ms}ms" if revision_latency_ms is not None else "?"
            rev_cost_str = f"${revision_cost:.4f}" if revision_cost is not None else "n/a"
            print(
                f"  Revision: model={revision_model}, latency={rev_latency_str}, "
                f"cost={rev_cost_str}",
                flush=True,
            )

        # Draft size change
        if prev_draft_size is not None and new_draft_size is not None:
            delta = new_draft_size - prev_draft_size
            sign = "+" if delta >= 0 else ""
            print(
                f"  Draft: {prev_draft_size} → {new_draft_size} chars ({sign}{delta})",
                flush=True,
            )

        # History context size
        print(f"  History context: {history_context_size} chars", flush=True)

        if v != "debug":
            return

        # --- Debug block ---------------------------------------------------
        _DEBUG_WARN = "⚠ DEBUG OUTPUT — may contain sensitive content"

        if raw_gpt_response:
            print(f"\n{_DEBUG_WARN}", flush=True)
            print("  [Raw GPT response]", flush=True)
            print(raw_gpt_response, flush=True)

        if history_context_text:
            print(f"\n{_DEBUG_WARN}", flush=True)
            print("  [History context sent to GPT]", flush=True)
            print(history_context_text, flush=True)

        if revision_prompt_text:
            print(f"\n{_DEBUG_WARN}", flush=True)
            print("  [Revision prompt sent to Claude]", flush=True)
            print(revision_prompt_text, flush=True)

    def _emit_final(
        self,
        stop_reason: str,
        total_rounds: int,
        total_cost: float,
    ) -> None:
        """Emit the final summary line to stdout."""
        cost_str = f"${total_cost:.4f}"
        if stop_reason in ("go", "cap_no_criticals"):
            print(f"Converged in {total_rounds} rounds. {cost_str} total.", flush=True)
        else:
            print(f"Cap reached after {total_rounds} rounds. {cost_str} total.", flush=True)

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

    def _fast_mode_header(self) -> str:
        """Return the fast mode HTML comment prefix if fast mode is active."""
        if self.config.get("fast_mode", False):
            return "<!-- [FAST MODE] -->\n"
        return ""

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
                f.write(self._fast_mode_header() + _format_review_artifact(round_num, review))
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
                f.write(self._fast_mode_header() + plan_text)
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
