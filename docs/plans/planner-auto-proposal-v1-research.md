# Planner-Auto Research Findings

Research conducted 2026-03-26 using Kagi API (search + summarize).

---

## 1. OpenCode CLI Programmatic Invocation (POC 1)

### Non-Interactive Mode

OpenCode supports non-interactive execution:

```bash
opencode run "your prompt here"
# or
opencode -p "your prompt"
```

This is the primary path for scripting and automation.

### Known Issues

- **subprocess.Popen hangs**: [opencode/issues/11891](https://github.com/anomalyco/opencode/issues/11891) — launching OpenCode via Python subprocess.Popen causes indefinite hangs. This is a confirmed bug.
- **Non-interactive pipeline limitations**: [opencode/issues/13851](https://github.com/anomalyco/opencode/issues/13851) — `opencode run` in non-interactive mode cannot reliably execute repo-changing tools (write/edit) without user confirmation prompts. The `--force` / `-f` flag may help but is not fully resolved.

### Alternative: HTTP Server Mode

OpenCode has a `serve` command that starts a headless HTTP API:

```bash
opencode serve
# Set OPENCODE_SERVER_PASSWORD for auth
```

This avoids subprocess issues entirely — planner-auto could POST prompts to the local server and read responses via HTTP. **This may be more reliable than subprocess invocation.**

### Alternative: Direct API Call

Skip OpenCode entirely and call the OpenAI/GPT API directly from Python. This removes the OpenCode dependency but loses tool access (file reading, code execution) that OpenCode provides.

### POC 1 Verdict

Three approaches to test, in priority order:
1. `opencode run "prompt" > output.md` — simplest, but known hanging issues
2. `opencode serve` + HTTP requests — avoids subprocess, more reliable
3. Direct GPT API call — fallback if OpenCode integration is unreliable

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

Claude can then invoke GPT-5.4 through the Codex MCP tool directly within its agent loop — no file handoff, no subprocess, no hanging issues.

### Differences from planner-auto

| Aspect | ARIS | planner-auto |
|--------|------|-------------|
| Domain | ML research papers | Software implementation plans |
| Review target | Paper quality score | Plan feasibility (go/no-go) |
| Artifact format | LaTeX papers | Milestone markdown plans |
| Persistence | In-session only | Session folder with chat.csv, context tracker, numbered plan/review files |
| Audit trail | Minimal | Full (every draft and review preserved) |

---

## 4. Approach Options for Cross-Model Review

Based on research, four viable approaches for invoking GPT from planner-auto:

### Option A: OpenCode subprocess

```python
subprocess.run(["opencode", "run", prompt], capture_output=True, text=True)
```

- **Pro**: Uses existing OpenCode setup, GPT has tool access
- **Con**: Known hanging issues, non-interactive tool limitations
- **Risk**: HIGH

### Option B: OpenCode HTTP server

```python
# Start once: opencode serve
requests.post("http://localhost:PORT/api/run", json={"prompt": prompt})
```

- **Pro**: Avoids subprocess issues, GPT has tool access
- **Con**: Requires server running in background, extra setup
- **Risk**: MEDIUM

### Option C: Codex MCP server (ARIS approach)

```bash
claude mcp add codex -s user -- codex mcp-server
```

Claude invokes GPT directly through MCP within its agent loop. No subprocess, no file handoff.

- **Pro**: Clean integration, proven by ARIS, no process management
- **Con**: Requires Codex CLI installed, MCP setup
- **Risk**: LOW (proven in production by ARIS)

### Option D: Direct OpenAI API

```python
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(model="gpt-5.4", messages=[...])
```

- **Pro**: Most reliable, no CLI dependencies
- **Con**: GPT has no tool access (can't read repo files), just reviews plan text
- **Risk**: LOW (but limited capability)

### Recommendation

**Option C (Codex MCP)** is the strongest choice — proven by ARIS, avoids subprocess issues, and gives GPT tool access within Claude's agent loop. Option D is the simplest fallback if MCP setup is a barrier (GPT only needs to read the plan file, which can be passed as prompt content).

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
| "Invoke OpenCode via subprocess" | Known hanging issues, unreliable for non-interactive use | **Change approach**: use Codex MCP or HTTP server instead |
| "GPT reviews plan via file handoff" | ARIS proves MCP integration works for cross-model review | **Simplifies architecture**: no file handoff needed if using MCP |
| "Numbered plan/review files" | ARIS doesn't use file-based handoff, keeps everything in-session | **Keep our approach**: file-based audit trail is a differentiator |
| "Sub-agent updates after every response" | No blockers found, existing SDK patterns support this | **No change needed** |

### Recommended Changes to Proposal

1. **Replace "OpenCode subprocess" with "Codex MCP server"** as the primary cross-model integration method
2. **Add Option D (direct API) as fallback** for environments without Codex CLI
3. **POC 1 should test Codex MCP setup** rather than OpenCode subprocess
4. **Reference ARIS** as prior art and validation of the cross-model review pattern

---

## Sources

- [OpenCode CLI docs](https://opencode.ai/docs/cli/)
- [OpenCode GitHub](https://github.com/opencode-ai/opencode)
- [OpenCode subprocess hang issue #11891](https://github.com/anomalyco/opencode/issues/11891)
- [OpenCode non-interactive issue #13851](https://github.com/anomalyco/opencode/issues/13851)
- [Claude Code headless docs](https://code.claude.com/docs/en/headless)
- [Claude Agent SDK Python](https://github.com/anthropics/claude-agent-sdk-python)
- [ARIS — Auto-claude-code-research-in-sleep](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)
- [Adversarial collaboration between AI coding tools (Reddit)](https://www.reddit.com/r/LocalLLaMA/comments/1navnzc/adversarial_collaboration_between_ai_coding_tools/)
- [LLM-Collab: task planning via chain-of-thought](https://www.aimspress.com/article/doi/10.3934/aci.2024019)
