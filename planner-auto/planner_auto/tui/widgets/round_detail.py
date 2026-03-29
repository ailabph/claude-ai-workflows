"""Round detail widget — shows full metrics for a selected round."""

from __future__ import annotations

from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Label


# Disposition badge markup.
_BADGE = {
    "ACCEPT": "[green][ACCEPT][/green]",
    "DEFER": "[yellow][DEFER][/yellow]",
    "REJECT": "[red][REJECT][/red]",
}


class RoundDetail(Static):
    """Full detail view for a single review round.

    Displays:
    - Verdict and round number
    - GPT latency, tokens, cost
    - Claude revision latency (tokens/cost as n/a)
    - Keep items (prefixed ``+``)
    - Trim items (prefixed ``-``)
    - Issues with disposition badges
    - Draft size change with percentage
    - History context size
    """

    DEFAULT_CSS = """
    RoundDetail {
        height: auto;
        padding: 1 2;
    }
    RoundDetail .rd-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    RoundDetail .rd-section {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }
    RoundDetail .rd-metric {
        padding: 0 0 0 2;
    }
    RoundDetail .rd-item {
        padding: 0 0 0 2;
    }
    RoundDetail .rd-keep {
        color: #00ff41;
        padding: 0 0 0 2;
    }
    RoundDetail .rd-trim {
        color: $warning;
        padding: 0 0 0 2;
    }
    RoundDetail .rd-note {
        color: $text-muted;
        padding: 0 0 0 2;
    }
    """

    def __init__(self, round_num: int, round_data: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self._round_num = round_num
        self._data = round_data

    def compose(self):
        d = self._data
        verdict = d.get("verdict", "?")
        issue_count = d.get("issue_count", 0)

        yield Label(
            f"Round {self._round_num} — {verdict} ({issue_count} issues)",
            classes="rd-title",
        )

        # --- GPT Review Metrics ---
        yield Label("GPT Review", classes="rd-section")
        latency = d.get("latency_ms", 0)
        yield Static(f"Latency: {latency:,}ms", classes="rd-metric")
        in_tok = d.get("input_tokens")
        out_tok = d.get("output_tokens")
        tok_str = f"{in_tok:,} in / {out_tok:,} out" if in_tok is not None else "n/a"
        yield Static(f"Tokens: {tok_str}", classes="rd-metric")
        cost = d.get("cost")
        cost_str = f"${cost:.4f}" if cost is not None else "n/a"
        yield Static(f"Cost: {cost_str}", classes="rd-metric")

        # --- Claude Revision Metrics ---
        yield Label("Claude Revision", classes="rd-section")
        rev_latency = d.get("revision_latency_ms")
        if rev_latency is not None:
            yield Static(f"Latency: {rev_latency:,}ms", classes="rd-metric")
        else:
            yield Static("Latency: n/a", classes="rd-metric")
        yield Static("Tokens: n/a", classes="rd-note")
        yield Static("Cost: n/a", classes="rd-note")
        yield Static(
            "(Claude revision metrics require plumbing work, see proposal)",
            classes="rd-note",
        )

        # --- Draft Size Change ---
        prev_size = d.get("prev_size")
        new_size = d.get("new_size")
        if prev_size is not None and new_size is not None:
            delta = new_size - prev_size
            pct = (delta / prev_size * 100) if prev_size > 0 else 0
            sign = "+" if delta >= 0 else ""
            yield Label("Draft Size", classes="rd-section")
            yield Static(
                f"{prev_size:,} → {new_size:,} chars ({sign}{delta:,}, {sign}{pct:.1f}%)",
                classes="rd-metric",
            )

        # --- History Context ---
        ctx_size = d.get("history_context_size")
        if ctx_size is not None:
            yield Static(f"History context: {ctx_size:,} chars", classes="rd-metric")

        # --- Keep Items ---
        keep_count = d.get("keep_count", 0)
        if keep_count:
            yield Label(f"Keep ({keep_count})", classes="rd-section")
            keep_items = d.get("keep_items", [])
            for item in keep_items[:20]:  # Cap display
                text = item if isinstance(item, str) else str(item)
                yield Static(f"+ {text}", classes="rd-keep")
            if not keep_items:
                yield Static(f"+ ({keep_count} items)", classes="rd-keep")

        # --- Trim Items ---
        trim_count = d.get("trim_count", 0)
        if trim_count:
            yield Label(f"Trim ({trim_count})", classes="rd-section")
            trim_items = d.get("trim_items", [])
            for item in trim_items[:20]:
                text = item if isinstance(item, str) else str(item)
                yield Static(f"- {text}", classes="rd-trim")
            if not trim_items:
                yield Static(f"- ({trim_count} items)", classes="rd-trim")

        # --- Issues with Disposition Badges ---
        issues = d.get("issues", [])
        if issues:
            yield Label(f"Issues ({len(issues)})", classes="rd-section")
            for i, issue in enumerate(issues):
                sev = issue.get("severity", "")
                desc = issue.get("description", issue.get("summary", f"Issue #{i + 1}"))
                disp = issue.get("disposition", "")
                badge = _BADGE.get(disp, f"[{disp}]") if disp else ""
                sev_prefix = f"[{sev}] " if sev else ""
                yield Static(
                    f"  {sev_prefix}{desc} {badge}",
                    classes="rd-item",
                )

        # --- Navigation hint ---
        yield Static("")
        yield Static(
            "[dim]n/p: next/prev round  r: raw response  Escape: back[/dim]",
            classes="rd-note",
        )
