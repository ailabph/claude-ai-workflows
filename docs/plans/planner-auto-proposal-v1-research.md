# Planner-Auto Research Findings

Research conducted 2026-03-26 using Kagi API (search + summarize), plus targeted doc and issue validation.

---

## 1. OpenCode CLI Programmatic Invocation (POC 1)

### Non-Interactive Mode

OpenCode supports non-interactive execution:

```bash
opencode run "your prompt here"
# or
opencode -p "your prompt"
```

This is the simplest CLI path for scripting and automation, but current issue reports make it a poor primary foundation for planner-auto.

### Known Issues

- **`opencode run` can hang after tool calls complete**: [opencode/issues/17516](https://github.com/anomalyco/opencode/issues/17516) — a March 2026 report shows `opencode run` finishing Read/Write work and then never exiting, which breaks subprocess-driven automation loops.
- **Non-interactive pipeline limitations**: [opencode/issues/13851](https://github.com/anomalyco/opencode/issues/13851) — `opencode run` in non-interactive mode may fail to execute repo-changing tools (write/edit) reliably in CI-like flows because of permission/bootstrap behavior. The issue also reports `run --attach` problems for headless server usage in that version.

### Alternative: HTTP Server Mode

OpenCode has a `serve` command that starts a headless HTTP API:

```bash
opencode serve
# Set OPENCODE_SERVER_PASSWORD for auth
```

This avoids subprocess issues entirely — planner-auto could POST prompts to the local server and read responses via HTTP. The official server docs confirm:

- OpenAPI spec at `/doc`
- session/message APIs for programmatic control
- HTTP basic auth via `OPENCODE_SERVER_PASSWORD`
- SSE/event endpoints for streaming updates

This makes `opencode serve` a real automation surface, not just an undocumented workaround.

### Alternative: Direct API Call

Skip OpenCode entirely and call the OpenAI/GPT API directly from Python. This removes the OpenCode dependency but loses tool access (file reading, code execution) that OpenCode provides.

### POC 1 Verdict

Three approaches to test, in priority order:
1. `opencode serve` + HTTP requests — documented automation API, avoids subprocess hang risk
2. Direct GPT API call — simplest reliable fallback if reviewer only needs plan text
3. `opencode run "prompt" > output.md` — simplest shell path, but should be treated as experimental only

---

## 2. Claude Code Headless/Programmatic Mode

### Agent SDK (Python)

Claude Code can be invoked programmatically via the Agent SDK:

```python
from claude_agent_sdk import ClaudeSDKClient

client = ClaudeSDKClient(system_prompt={"type": "text", "text": "..."})
result = client.run(prompt="your prompt")
```

### CLI Headless Mode

```bash
claude -p "your prompt" --output-format json --bare
```

Key flags:
- `-p` — non-interactive, single prompt
- `--bare` — skips hooks, plugins, MCP servers (faster startup, good for CI/CD)
- `--output-format json` — structured response with metadata
- `--allowedTools` — auto-approve specific tools (prefix matching with trailing `*`)
- `--continue` / `--resume <session-id>` — conversation persistence
- `--append-system-prompt` — add custom instructions

**Relevance to planner-auto**: The planner agent (Claude) side can use the Agent SDK directly since orchestrator-auto already depends on it. No subprocess needed for the Claude half.

Source: [code.claude.com/docs/en/headless](https://code.claude.com/docs/en/headless)

---

## 3. Prior Art: ARIS (Auto-Research-In-Sleep)

**Highly relevant project** — does cross-model review loops for ML research.

Repository: [github.com/wanshuiyin/Auto-claude-code-research-in-sleep](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)

### What ARIS Does

- Claude Code executes research tasks
- GPT-5.4 (via Codex MCP) acts as critical reviewer to avoid self-play blind spots
- `/auto-review-loop` skill: 4-round autonomous review → fix → re-review cycle
- Runs overnight, improves paper scores from 5/10 to 7.5/10
- **Two papers accepted** using this workflow (CS conference 8/10, AAAI 2026 7/10)

### Architecture Choices

| Aspect | ARIS Approach |
|--------|--------------|
| Cross-model invocation | Codex MCP server (`claude mcp add codex -- codex mcp-server`) |
| Skill format | Plain Markdown files in `~/.claude/skills/` |
| Configuration | `RESEARCH_BRIEF.md` document (no complex CLI args) |
| Human oversight | `AUTO_PROCEED` control for checkpoints |
| Dependencies | Zero — pure Markdown skills |

### Key Insight for planner-auto

ARIS uses **MCP server integration** rather than subprocess calls to bridge Claude ↔ GPT. This is cleaner than calling `opencode run` as a subprocess:

```bash
# ARIS setup
npm install -g @openai/codex
claude mcp add codex -s user -- codex mcp-server
```

Claude can then invoke GPT-5.4 through the Codex MCP tool directly within its agent loop — no subprocess management, and no dependence on `opencode run` batch behavior. Separately, OpenAI's Codex docs confirm first-class MCP configuration and `codex mcp` CLI support on the Codex side.

### Differences from planner-auto

| Aspect | ARIS | planner-auto |
|--------|------|-------------|
| Domain | ML research papers | Software implementation plans |
| Review target | Paper quality score | Plan feasibility (go/no-go) |
| Artifact format | LaTeX papers | Milestone markdown plans |
| Persistence | In-session only | SQLite canonical state plus exported audit artifacts (plan/review files, chat/context views) |
| Audit trail | Minimal | Full (every draft and review preserved) |

---

## 4. Approach Options for Cross-Model Review

Based on research, four viable approaches for invoking GPT from planner-auto:

### Option A: OpenCode subprocess

```python
subprocess.run(["opencode", "run", prompt], capture_output=True, text=True)
```

- **Pro**: Uses existing OpenCode setup, GPT has tool access
- **Con**: Known hanging issues, non-interactive tool limitations, weak fit for CI-style automation
- **Risk**: HIGH

### Option B: OpenCode HTTP server

```python
# Start once: opencode serve
# Then drive the documented session/message HTTP APIs
session = requests.post("http://localhost:4096/session", json={}).json()
requests.post(f"http://localhost:4096/session/{session['id']}/message", json={...})
```

- **Pro**: Avoids subprocess issues, GPT has tool access, documented OpenAPI/session APIs
- **Con**: Requires server lifecycle management and authentication/setup
- **Risk**: MEDIUM

### Option C: Codex MCP server (ARIS approach)

```bash
claude mcp add codex -s user -- codex mcp-server
```

Claude invokes GPT directly through MCP within its agent loop. No subprocess, no file handoff.

- **Pro**: Clean integration, proven by ARIS, no subprocess management, keeps review inside the planner agent loop
- **Con**: Requires Codex CLI installed, MCP setup, and confidence that planner-auto's Claude runtime can manage the needed MCP config cleanly
- **Risk**: MEDIUM-LOW

### Option D: Direct OpenAI API

```python
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(model="gpt-5.4", messages=[...])
```

- **Pro**: Most reliable, no CLI dependencies, easiest to test and ship as an initial reviewer adapter
- **Con**: GPT has no tool access (can't read repo files), just reviews plan text unless planner-auto injects more context explicitly
- **Risk**: LOW

### Recommendation

Do **not** make OpenCode subprocess the primary design.

Recommended rollout:

1. **If reviewer scope is plan-text review only, start with Option D (Direct API).** It is the fastest, most reliable way to prove the review loop and validate the reviewer contract.
2. **If reviewer tool access or repo inspection is a real requirement, Option C (Codex MCP) is the strongest full-capability path.** ARIS validates the pattern, and Codex has first-class MCP support.
3. **Keep Option B (OpenCode HTTP server) as a viable alternative** for teams already invested in OpenCode, especially now that the server API is documented.

In short: **ship with Direct API or Codex MCP; avoid centering the design on `opencode run`.**

---

## 5. Sub-Agent File Tracking (POC 3)

No specific external research found on this — it's an implementation pattern rather than an integration challenge. The Claude Agent SDK supports sub-agents via the `Task` tool, which can be used to spawn a tracking agent after each response.

Key considerations:
- Sub-agent starts with fresh context (no accumulated tokens)
- Can run in parallel with the main conversation
- Should be fire-and-forget to avoid blocking the user

orchestrator-auto's existing `ExploreSubAgent` pattern (explore.py) is a good reference for implementation.

---

## 6. Summary of Research Impact on Proposal

| Proposal Assumption | Research Finding | Impact |
|---------------------|-----------------|--------|
| "Invoke OpenCode via subprocess" | Known hanging issues, unreliable for non-interactive use | **Change approach**: do not use subprocess as the primary adapter |
| "GPT reviews plan via file handoff" | ARIS proves MCP integration works for cross-model review | **Optional simplification**: MCP removes handoff as a transport requirement, but exported artifacts are still useful for audit trail |
| "Numbered plan/review files" | ARIS doesn't use file-based handoff, keeps everything in-session | **Keep our approach**: export numbered artifacts for audit trail, but do not use them as canonical state |
| "Sub-agent updates after every response" | No blockers found, existing SDK patterns support this | **No change needed** |

### Recommended Changes to Proposal

1. **Replace "OpenCode subprocess" with either "Codex MCP" or "Direct API"** as the primary reviewer adapter, depending on whether reviewer tool access is actually required
2. **Keep OpenCode HTTP server as an alternative adapter** instead of treating it as a side note
3. **POC 1 should test reviewer contract + adapter seam**, not just subprocess invocation
4. **Reference ARIS** as prior art for cross-model review loops, while noting that its persistence model differs from planner-auto
5. **Update proposal language to reflect SQLite canonical state + exported audit artifacts**

---

## Sources

- [OpenCode CLI docs](https://opencode.ai/docs/cli/)
- [OpenCode server docs](https://opencode.ai/docs/server/)
- [OpenCode GitHub](https://github.com/opencode-ai/opencode)
- [OpenCode subprocess hang issue #11891](https://github.com/anomalyco/opencode/issues/11891)
- [OpenCode run hangs after tool calls issue #17516](https://github.com/anomalyco/opencode/issues/17516)
- [OpenCode non-interactive issue #13851](https://github.com/anomalyco/opencode/issues/13851)
- [Claude Code headless docs](https://code.claude.com/docs/en/headless)
- [Claude Agent SDK Python](https://github.com/anthropics/claude-agent-sdk-python)
- [OpenAI Codex MCP docs](https://developers.openai.com/codex/mcp)
- [ARIS — Auto-claude-code-research-in-sleep](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)
- [Adversarial collaboration between AI coding tools (Reddit)](https://www.reddit.com/r/LocalLLaMA/comments/1navnzc/adversarial_collaboration_between_ai_coding_tools/)
- [LLM-Collab: task planning via chain-of-thought](https://www.aimspress.com/article/doi/10.3934/aci.2024019)
