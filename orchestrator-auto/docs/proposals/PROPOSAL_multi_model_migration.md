# Proposal: Multi-Model Provider Support for orchestrator-auto

**Status:** Draft
**Date:** 2026-02-28
**Author:** Engineering
**Scope:** Replace or abstract `claude-agent-sdk` dependency to support multiple LLM providers

---

## Context & Motivation

### Business Continuity Risk

The primary driver for this proposal is **resilience against catastrophic failure of centralized/private LLM providers**. Scenarios include:

- **Provider shutdown or bankruptcy** — a major LLM company ceases operations, API goes offline permanently
- **Regulatory action** — government restrictions block access to specific providers in certain regions
- **Prolonged outage** — extended multi-day API downtime (beyond normal incident windows)
- **Pricing shock** — sudden, unsustainable price increases that make current workflows unviable
- **Terms of service changes** — provider restricts agentic/autonomous usage, code generation, or specific industries
- **Geopolitical disruption** — sanctions, trade restrictions, or data sovereignty laws cut off provider access

If Anthropic's API becomes unavailable for any reason, orchestrator-auto currently has **zero fallback capability**. Every workflow, every session, every in-progress milestone stops. There is no degraded mode, no failover, no local alternative.

This is not a theoretical risk. The AI industry is young, heavily funded by venture capital, and subject to rapid regulatory and market shifts. A responsible engineering posture requires that critical tooling not depend on a single provider's continued availability and goodwill.

### Secondary Benefits

Beyond catastrophic scenarios, multi-model support also enables:

1. **Cost optimization** — route simple tasks to cheaper providers (GPT-4o-mini, local models)
2. **Performance tuning** — use the best model per task type (e.g., Claude for planning, GPT for boilerplate)
3. **Privacy/compliance** — run air-gapped with local models (Ollama, LM Studio) for sensitive codebases
4. **Competitive leverage** — not locked into a single provider's pricing or roadmap decisions

---

## Problem Statement

orchestrator-auto is tightly coupled to `claude-agent-sdk` (≥0.1.25), which only supports Anthropic Claude models (direct API, AWS Bedrock, Google Vertex AI). This creates:

1. **Vendor lock-in** — cannot use OpenAI, Gemini, or local models
2. **Cost inflexibility** — cannot route cheaper tasks to cheaper providers
3. **Single point of failure** — Anthropic outages block all workflows
4. **Privacy constraints** — cannot run air-gapped with local models

### Goal

Support multiple LLM providers (Claude, OpenAI, Gemini, local/Ollama) without sacrificing the core orchestration features that make orchestrator-auto work: tool use, conversation continuity, file checkpoint/rewind, MCP integration, and token tracking. The minimum viable outcome is the ability to **continue operating orchestrator-auto workflows using open-source/local models if all centralized providers become unavailable**.

---

## Current SDK Dependency Audit

### Integration Surface

orchestrator-auto uses `claude-agent-sdk` across **6 files** with **~25 integration points**:

| File | SDK Usage | Complexity |
|------|-----------|------------|
| `agents.py` | Core agent loop, conversation continuity, checkpoint/rewind, MCP, tool tracking, token callbacks | **High** — 70% of all SDK usage |
| `explore.py` | Read-only sub-agent with governance (max_turns, timeout) | Medium |
| `todo.py` | Fresh agent per task, tool use, MCP | Medium |
| `commit_ai.py` | One-shot text generation (no tools needed) | Low |
| `convert.py` | One-shot text generation (no tools needed) | Low |
| `cli.py` | Health checks, MCP status queries | Low |

### SDK Classes & Types Used

```python
from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import (
    ClaudeAgentOptions,   # system_prompt, tools, model, cwd, permission_mode, mcp_servers, max_turns
    UserMessage,          # .uuid, .tool_use_result
    AssistantMessage,     # .content (List[TextBlock])
    ResultMessage,        # .usage (dict), .total_cost_usd (float)
    TextBlock,            # .text
)
```

### Critical SDK Features

| Feature | Where Used | Replaceable? |
|---------|-----------|-------------|
| Agentic tool loop (Read/Write/Edit/Bash/Glob/Grep) | agents.py, explore.py, todo.py | **Hard** — this is the agent runtime |
| Conversation continuity (reuse client across turns) | agents.py (Planner/Executor) | Medium — need stateful sessions |
| File checkpoint/rewind (`rewind_files()`) | agents.py + engine.py | **Hard** — no equivalent in other SDKs |
| MCP server lifecycle | agents.py, cli.py | Medium — OpenCode and others support MCP |
| Permission bypass mode | agents.py, explore.py, todo.py | Claude-specific concept |
| Token/cost tracking (per-model, cache, thinking) | agents.py, explore.py | Provider-specific formats |
| Tool invocation audit trail | agents.py | SDK 0.1.22+ feature |

### Claude-Specific Assumptions in Code

1. Response always yields `AssistantMessage` → `ResultMessage` sequence
2. `ResultMessage.usage` contains `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `thinking_tokens`
3. `ResultMessage.total_cost_usd` is always a float
4. `UserMessage.uuid` persists across rewinds for checkpoint integrity
5. MCP servers auto-initialize from config dict passed to options
6. `permission_mode="bypassPermissions"` auto-approves all tool calls

---

## Options Evaluated

### Option A: Adapter Layer over claude-agent-sdk (Incremental)

**Approach:** Abstract `agents.py` behind an `AgentBackend` interface. Keep `claude-agent-sdk` as the default backend. Add alternative backends later.

```python
# Proposed interface
class AgentBackend(ABC):
    async def query(self, prompt: str) -> AsyncIterator[AgentMessage]
    async def rewind(self, checkpoint_id: str) -> bool
    async def get_mcp_status(self) -> dict
    def supports_rewind(self) -> bool
    def supports_mcp(self) -> bool

class ClaudeBackend(AgentBackend):     # Wraps claude-agent-sdk (existing behavior)
class OpenAIBackend(AgentBackend):     # Future: wraps openai SDK + custom tool loop
class PydanticAIBackend(AgentBackend): # Future: wraps pydantic-ai
```

| Pros | Cons |
|------|------|
| Zero disruption to working code | Still runs on claude-agent-sdk day 1 |
| Swap backends per-agent (planner=Claude, executor=GPT) | Full multi-model requires implementing tool loops per backend |
| Incremental — add backends one at a time | Adapter may leak abstractions for provider-specific features |
| ~2-3 days for the interface + Claude backend | |

**Effort:** ~2-3 days (interface + refactor agents.py)
**Risk:** Low

---

### Option B: Replace with OpenCode (via SDK or subprocess)

**Approach:** Replace `claude-agent-sdk` with OpenCode as the agent runtime. OpenCode handles the tool loop, model routing, and MCP internally.

**Architecture:**

```
orchestrator-auto (Python)
    ↓ HTTP/SSE
OpenCode Server (Go/JS)
    ↓ Provider API
Claude / OpenAI / Gemini / Ollama
```

**Two sub-options:**

**B1: OpenCode Python SDK (`pip install opencode-ai`)**

The SDK exposes session management via REST:

| Resource | Key Methods |
|----------|-------------|
| `Session` | `create()`, `chat(id, prompt)`, `messages(id)`, `abort(id)`, `revert(id)` |
| `File` | `read()`, `status()` |
| `Find` | `files()`, `symbols()`, `text()` |
| `Event` | `list()` — SSE streaming |
| `App` | `providers()`, `modes()` |

**B2: Subprocess to OpenCode CLI**

```bash
opencode "Implement milestone 1: Add user model and migrations"
```

| Pros | Cons |
|------|------|
| 75+ model providers out of the box | Client/server architecture — not embeddable as a library |
| OpenCode handles full tool loop (read/write/edit/bash/glob/grep) | One server process per project |
| MCP support built-in | Lose file checkpoint/rewind (OpenCode uses git snapshots instead) |
| LSP integration for real-time diagnostics | Lose per-token cost tracking granularity |
| Air-gapped mode with local models | SDK is beta (`--pre` flag required) |
| Active project (48K+ GitHub stars, 2.5M monthly users) | Lose conversation continuity control (sessions are server-managed) |
| | Go/JS core — can't debug or extend in Python |
| | Adds external process dependency to deployment |

**Effort:** ~3-4 weeks (rearchitect from embedded to client/server)
**Risk:** High — fundamental architecture change

**Key technical gaps:**
- `rewind_files(uuid)` → OpenCode uses git-based snapshots, not UUID-based rewind
- `permission_mode="bypassPermissions"` → OpenCode has its own permission system
- Token usage callback → must poll OpenCode's session API instead of inline callbacks
- Conversation continuity → managed by OpenCode server, less control from orchestrator

---

### Option C: Replace with Pydantic AI

**Approach:** Replace `claude-agent-sdk` with [Pydantic AI](https://ai.pydantic.dev/) as the multi-model agent framework. Implement custom tool loop for file operations.

**Pydantic AI supports:**
- All major providers: OpenAI, Anthropic, Google Gemini, AWS Bedrock, Groq, Mistral, Ollama, and more
- `FallbackModel` for automatic failover across providers
- `ConcurrencyLimitedModel` for rate limiting
- Type-safe structured outputs via Pydantic
- Multi-agent delegation with per-agent model selection
- OpenTelemetry observability via Pydantic Logfire
- `UsageLimits` for cost control

```python
from pydantic_ai import Agent

planner = Agent('anthropic:claude-opus-4-5-20251101', system_prompt="...")
executor = Agent('openai:gpt-4o', system_prompt="...")
```

| Pros | Cons |
|------|------|
| Pure Python, pip-installable | **No built-in coding tools** (Read/Write/Edit/Bash/Glob/Grep) |
| All major providers + local models | Must implement entire tool dispatch loop from scratch |
| Type-safe, Pydantic-native | No file checkpoint/rewind |
| FallbackModel for provider resilience | No MCP support (must add separately) |
| Production-ready (v0.0.x but actively maintained) | No permission system |
| Clean multi-agent patterns | Significant effort to reach feature parity |

**Effort:** ~4-6 weeks (tool loop implementation + testing)
**Risk:** Medium-high — reimplementing the agent runtime

---

### Option D: Microsoft Agent Framework + Claude Agent SDK

**Approach:** Keep `claude-agent-sdk` for Claude agents. Use [Microsoft Agent Framework](https://devblogs.microsoft.com/semantic-kernel/build-ai-agents-with-claude-agent-sdk-and-microsoft-agent-framework/) (Semantic Kernel) to compose Claude agents alongside OpenAI/Copilot agents.

```python
from semantic_kernel.agents import ClaudeAgent, AzureOpenAIAgent, SequentialBuilder

planner = ClaudeAgent(instructions="...", tools=[...])  # Uses claude-agent-sdk under the hood
executor = AzureOpenAIAgent(instructions="...", tools=[...])

pipeline = SequentialBuilder()
pipeline.add(planner)
pipeline.add(executor)
```

| Pros | Cons |
|------|------|
| Official Claude integration (same tools, permissions) | Microsoft ecosystem dependency |
| Multi-provider orchestration (OpenAI, Copilot, Claude) | Additional abstraction layer |
| Built-in sequential, concurrent, handoff patterns | Less control than direct SDK usage |
| MCP support via Semantic Kernel | Learning curve for SK concepts |
| Production-ready, Microsoft-backed | Tool loop still Claude-specific for Claude agents |

**Effort:** ~2-3 weeks
**Risk:** Medium

---

### Option E: Raw Multi-SDK + Custom Tool Loop

**Approach:** Use `anthropic` and `openai` Python SDKs directly. Implement your own tool dispatch loop (Read/Write/Edit/Bash/Glob/Grep).

```python
# Simplified concept
class ToolLoop:
    async def run(self, provider: LLMProvider, prompt: str) -> str:
        while True:
            response = await provider.chat(messages)
            if response.has_tool_calls:
                results = await self.execute_tools(response.tool_calls)
                messages.append(tool_results(results))
            else:
                return response.text
```

| Pros | Cons |
|------|------|
| Full control over everything | Reimplementing what claude-agent-sdk already does |
| No framework dependencies | Tool security (command injection, path traversal) is your problem |
| Exactly the features you need, nothing more | ~2000+ lines of tool dispatch code |
| | Ongoing maintenance as provider APIs evolve |
| | No file rewind (must implement via git) |

**Effort:** ~4-6 weeks
**Risk:** High — maintaining your own agent runtime

---

## Comparison Matrix

| Criteria | A: Adapter | B: OpenCode | C: Pydantic AI | D: MS Framework | E: Raw SDKs |
|----------|-----------|-------------|----------------|-----------------|-------------|
| **Effort** | 2-3 days | 3-4 weeks | 4-6 weeks | 2-3 weeks | 4-6 weeks |
| **Risk** | Low | High | Medium-high | Medium | High |
| **Multi-model day 1** | No (later) | Yes | Yes | Yes | Yes |
| **Keep rewind** | Yes | No (git-based) | No | Partial | No |
| **Keep tool loop** | Yes | Yes (OpenCode's) | No (rebuild) | Partial | No (rebuild) |
| **Keep MCP** | Yes | Yes | No (add manually) | Yes | No (add manually) |
| **Keep token tracking** | Yes | Partial | Provider-specific | Partial | Provider-specific |
| **Local/Ollama models** | No | Yes | Yes | No | Yes |
| **Air-gapped** | No | Yes | Yes | No | Yes |
| **Embeddable (in-process)** | Yes | No (client/server) | Yes | Yes | Yes |
| **Maintenance burden** | Low | Medium | High | Medium | High |

---

## Recommendation

Given the business continuity motivation — **surviving a catastrophic collapse of centralized LLM providers** — the recommendation prioritizes reaching a state where orchestrator-auto can operate on local/open-source models as a fallback, while preserving Claude as the primary runtime for day-to-day use.

### Phase 1: Adapter Layer (Option A) — Immediate

**Timeline:** 2-3 days
**Priority:** Critical — this is the prerequisite for everything else

1. Define `AgentBackend` abstract interface in `agents.py`
2. Extract current claude-agent-sdk usage into `ClaudeBackend`
3. Update `BaseAgent`, `PlannerAgent`, `ExecutorAgent` to use the interface
4. No behavior change — pure refactor

This immediately decouples orchestrator logic from the SDK. All future backend work becomes additive, not destructive.

### Phase 2: Local/Open-Source Backend — Next Priority

**Timeline:** 3-5 weeks after Phase 1
**Purpose:** The survivability layer — ensures orchestrator-auto works when no cloud API is available

Implement an `OllamaBackend` or `OpenCodeBackend` that can run workflows against local models (Llama, Mistral, DeepSeek, Qwen, etc.). This is the minimum viable disaster recovery capability.

| Approach | Pros | Cons | Recommended? |
|----------|------|------|-------------|
| **Pydantic AI + Ollama** | Pure Python, embeddable, supports Ollama natively, clean multi-model patterns | Must build tool dispatch loop (~2000 lines) | Yes — best long-term foundation |
| **OpenCode sidecar + Ollama** | Tool loop included, MCP support, minimal custom code | External process dependency, less control | Viable alternative |
| **Raw `ollama` SDK + custom tools** | No framework overhead | Maximum maintenance burden | Only if frameworks fail |

**Recommended path:** Pydantic AI backend with a minimal tool loop (Read, Write, Edit, Bash, Glob, Grep). Accept the upfront cost of building the tool loop — it makes the system fully self-contained with zero external dependencies beyond a local model server.

**Acceptable feature degradation in disaster mode:**

| Feature | Normal (Claude) | Degraded (Local) | Acceptable? |
|---------|----------------|-------------------|-------------|
| Tool use (Read/Write/Edit/Bash) | Full | Full (custom loop) | Yes |
| Planning quality | Opus-grade | Reduced (model-dependent) | Yes — functional, not optimal |
| File checkpoint/rewind | UUID-based | Git-based fallback | Yes |
| MCP integration | Full | None initially | Yes — add later |
| Token/cost tracking | Granular | Basic (in/out only) | Yes |
| Conversation continuity | Built-in | Manual message history | Yes |
| Prompt caching | Yes | No | Yes — performance hit, not a blocker |

### Phase 3: Multi-Provider Optimization — Future

Once the adapter and local backend exist, add cloud provider backends for cost/performance optimization:

| Backend | Use Case |
|---------|----------|
| OpenAI backend | Cheaper executor (GPT-4o-mini) for simple milestones |
| Gemini backend | Alternative cloud provider for redundancy |
| Microsoft Agent Framework | Enterprise integration (Azure, Copilot) |

This phase is purely additive — no urgency unless a specific provider advantage emerges.

### What NOT to do

- **Don't do a full rewrite now.** The tool loop (Read/Write/Edit/Bash/Glob/Grep) is the hardest part to replace and `claude-agent-sdk` handles it well for the primary path.
- **Don't adopt OpenCode as the core.** The client/server architecture is fundamentally different from the embedded model. It adds an external process dependency — the opposite of self-contained resilience.
- **Don't build a custom tool loop (Option E) from scratch without a framework.** Use Pydantic AI's agent primitives and only build the tool dispatch layer.
- **Don't delay Phase 1.** The adapter layer is 2-3 days of work with zero risk. Every day without it means the codebase is harder to migrate later.

---

## Migration Path (If Proceeding with Phase 1)

### Step 1: Define the interface

```python
# orchestrator_auto/backends/base.py
class AgentMessage:
    text: str
    usage: Optional[TokenUsage]
    is_final: bool

class TokenUsage:
    input_tokens: int
    output_tokens: int
    cost_usd: Optional[float]
    model: str

class AgentBackend(ABC):
    @abstractmethod
    async def send(self, prompt: str) -> AsyncIterator[AgentMessage]: ...

    @abstractmethod
    async def close(self) -> None: ...

    # Optional capabilities (not all backends support these)
    async def set_checkpoint(self) -> Optional[str]:
        return None  # Default: not supported

    async def rewind(self, checkpoint_id: str) -> bool:
        return False  # Default: not supported

    async def get_mcp_status(self) -> dict:
        return {}  # Default: not supported
```

### Step 2: Wrap existing SDK

```python
# orchestrator_auto/backends/claude.py
class ClaudeBackend(AgentBackend):
    """Wraps claude-agent-sdk — preserves all existing behavior."""
    # Move current agents.py SDK code here
```

### Step 3: Update agents.py

```python
# orchestrator_auto/agents.py
class BaseAgent:
    def __init__(self, backend: AgentBackend, ...):
        self._backend = backend
```

### Step 4: Config-driven backend selection

```yaml
# .claude_orchestrator/config.yaml
planner:
  backend: claude
  model: opus
executor:
  backend: claude  # or "openai", "pydantic-ai", "opencode" in the future
  model: sonnet
```

---

## Open Questions

1. **Which local models to target first?** Llama 3.3 70B, Mistral Large, DeepSeek-V3, Qwen 2.5 — each has different tool-calling capabilities. Need to benchmark which handles the orchestrator's structured tag protocol (`[PLAN_READY]`, `[PROGRESS_REPORT]`, etc.) reliably.
2. **Hardware requirements for local fallback?** Running 70B models locally requires significant GPU (48GB+ VRAM) or quantized versions. Define minimum viable hardware spec for disaster mode.
3. **Should the tool loop be shared or per-backend?** A shared tool dispatcher works across all backends but may not leverage provider-specific optimizations. Per-backend tool loops are more work but more resilient.
4. **Trigger mechanism for failover?** Automatic (detect API failure → switch to local) or manual (`orchestrator start --backend ollama`)? Automatic is better for true disaster scenarios but harder to implement safely.
5. **What's the RTO (Recovery Time Objective)?** How quickly must orchestrator-auto be operational on local models after a provider goes down? This determines whether we pre-configure local models or set them up on-demand.
6. **Should Phase 1 adapter include a "dry run" mode?** Run the same prompt through two backends and compare outputs — useful for validating that local models produce usable results before an actual disaster.

---

## References

### Claude Agent SDK
- [Agent SDK Overview — Claude API Docs](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Agent SDK Python Reference](https://platform.claude.com/docs/en/agent-sdk/python)
- [GitHub — anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)
- [PyPI — claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/)
- [Claude Code Multiple Agent Systems Guide (2026)](https://www.eesel.ai/blog/claude-code-multiple-agent-systems-complete-2026-guide)

### OpenCode
- [OpenCode Official Site](https://opencode.ai/)
- [OpenCode Docs — Server](https://opencode.ai/docs/server/)
- [OpenCode Docs — SDK](https://opencode.ai/docs/sdk/)
- [OpenCode Docs — Agents](https://opencode.ai/docs/agents/)
- [OpenCode Docs — CLI](https://opencode.ai/docs/cli/)
- [GitHub — anomalyco/opencode](https://github.com/anomalyco/opencode)
- [GitHub — anomalyco/opencode-sdk-python](https://github.com/anomalyco/opencode-sdk-python)
- [How Coding Agents Actually Work: Inside OpenCode](https://cefboud.com/posts/coding-agents-internals-opencode-deepdive/)
- [Building Agent Teams in OpenCode](https://dev.to/uenyioha/porting-claude-codes-agent-teams-to-opencode-4hol)
- [OpenCode vs Claude Code — DataCamp](https://www.datacamp.com/blog/opencode-vs-claude-code)
- [OpenCode vs Claude Code — Builder.io](https://www.builder.io/blog/opencode-vs-claude-code)
- [OpenCode vs Claude Code — Morpheus](https://www.morphllm.com/comparisons/opencode-vs-claude-code)

### OpenCode / Crush Split
- [Crush (ex-OpenCode) Review — The New Stack](https://thenewstack.io/terminal-user-interfaces-review-of-crush-ex-opencode-al/)
- [Christian Rocha (Charm CEO) Statement on X](https://x.com/meowgorithm/status/1933593074820891062)
- [Dax (SST) Response on X](https://x.com/thdxr/status/1933561254481666466)

### Microsoft Agent Framework
- [Build AI Agents with Claude Agent SDK and Microsoft Agent Framework](https://devblogs.microsoft.com/semantic-kernel/build-ai-agents-with-claude-agent-sdk-and-microsoft-agent-framework/)
- [Semantic Kernel MCP Support for Python](https://devblogs.microsoft.com/semantic-kernel/semantic-kernel-adds-model-context-protocol-mcp-support-for-python/)
- [GitHub — microsoft/semantic-kernel](https://github.com/microsoft/semantic-kernel)

### Pydantic AI
- [Pydantic AI Official Docs](https://ai.pydantic.dev/)
- [Pydantic AI — Models Overview](https://ai.pydantic.dev/models/overview/)
- [Pydantic AI — Multi-Agent Patterns](https://ai.pydantic.dev/multi-agent-applications/)
- [GitHub — pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai)

### LangChain
- [LangChain: Comparison with OpenCode and Claude Agent SDK](https://docs.langchain.com/oss/python/deepagents/comparison)
- [Agent Frameworks, Runtimes, and Harnesses (LangChain Blog)](https://blog.langchain.com/agent-frameworks-runtimes-and-harnesses-oh-my/)
- [Orchestration Wars: LangChain vs. Claude-Flow vs. Custom](https://www.sitepoint.com/agent-orchestration-framework-comparison-2026/)

### Vercel AI SDK
- [AI SDK by Vercel — Official Docs](https://ai-sdk.dev/docs/introduction)
- [AI SDK 6 Announcement](https://vercel.com/blog/ai-sdk-6)
- [GitHub — python-ai-sdk/sdk (Community Python Port)](https://github.com/python-ai-sdk/sdk)

### General Comparisons
- [OpenCode vs Claude Code vs OpenAI Codex (Medium)](https://bytebridge.medium.com/opencode-vs-claude-code-vs-openai-codex-a-comprehensive-comparison-of-ai-coding-assistants-bd5078437c01)
- [Claude Code vs OpenCode (Infralovers)](https://www.infralovers.com/blog/2026-01-29-claude-code-vs-opencode/)
- [Comparing Claude Code vs OpenCode — Testing Different Models](https://www.andreagrandi.it/posts/comparing-claude-code-vs-opencode-testing-different-models/)

---

### Implementation Examples & Tutorials

#### Pydantic AI — Tool Calling & Local Models
- [Pydantic AI — Function Tools (Official Docs)](https://ai.pydantic.dev/tools/) — tool registration via decorators, schema generation, retry on validation errors
- [Pydantic AI — Agents (Official Docs)](https://ai.pydantic.dev/agent/) — agent creation, system prompts, structured outputs, RunContext
- [Pydantic AI Beginner's Guide with Practical Examples — DataCamp](https://www.datacamp.com/tutorial/pydantic-ai-guide) — end-to-end tutorial with tool calling
- [Pydantic AI Agents Tutorial with Local Models + Ollama (GitHub)](https://github.com/abdallah-ali-abdallah/pydantic-ai-agents-tutorial) — step-by-step: structured agents, vision, tools, all on local Ollama models
- [Build Self-Hosted AI Agent with Ollama, Pydantic AI and Django Ninja](https://blog.devops.dev/build-self-hosted-ai-agent-with-ollama-pydantic-ai-and-django-ninja-65214a3afb35) — full self-hosted stack, no cloud APIs
- [Pydantic Agent with Local Ollama + MCP Server (GitHub)](https://github.com/jageenshukla/ollama-pydantic-project) — Pydantic AI + Ollama + MCP integration example
- [Building a Local AI Chatbot Using Ollama and Pydantic AI (Medium)](https://medium.com/@zerogavty/building-a-local-ai-chatbot-using-ollama-and-pydantic-ai-5e4aeb4eacc0) — local-only setup walkthrough
- [Comprehensive Guide: Agent Development with Pydantic AI — Beginner to Advanced (Medium)](https://szeyusim.medium.com/a-comprehensive-guide-on-agent-development-with-pydantic-ai-beginner-to-advanced-12d90e0ba1a6)

#### OpenCode SDK — Programmatic Usage
- [OpenCode SDK Python — DeepWiki (Full API walkthrough)](https://deepwiki.com/sst/opencode-sdk-python) — client classes, session management, streaming, error handling
- [OpenCode SDK Python — Getting Started (DeepWiki)](https://deepwiki.com/sst/opencode-sdk-python/2-getting-started) — installation, sync/async clients, configuration
- [OpenCode SDK as Promptfoo Provider](https://www.promptfoo.dev/docs/providers/opencode-sdk/) — using OpenCode SDK for automated prompt testing

#### Microsoft Agent Framework — Multi-Model Orchestration
- [Build AI Agents with Claude Agent SDK + Microsoft Agent Framework (Official)](https://devblogs.microsoft.com/semantic-kernel/build-ai-agents-with-claude-agent-sdk-and-microsoft-agent-framework/) — ClaudeAgent class, multi-provider composition, code examples
- [Semantic Kernel Multi-Agent Orchestration (Official)](https://devblogs.microsoft.com/semantic-kernel/semantic-kernel-multi-agent-orchestration/) — sequential, concurrent, handoff patterns with code
- [Build an Agent Orchestrator in Python with Semantic Kernel (Medium)](https://medium.com/@speaktoharisudhan/build-an-agent-orchestrator-in-python-with-semantic-kernel-bb271d8f32e1) — step-by-step Python implementation
- [Designing Multi-Agent AI Systems with Semantic Kernel](https://amgadmadkour.com/blog/2025/semantickernel/) — architecture patterns and design decisions
- [Orchestrating Multi-Agent AI with Semantic Kernel (Digital Bricks)](https://www.digitalbricks.ai/blog-posts/orchestrating-multi-agent-ai-with-semantic-kernel) — real-world orchestration patterns

#### OpenAgentsControl — Plan-First Agent Framework on OpenCode
- [GitHub — OpenAgentsControl](https://github.com/darrenhinde/OpenAgentsControl) — plan-first development workflows with approval-based execution, multi-language (TS, Python, Go, Rust), built on OpenCode
- [OpenAgentsControl Agent System Blueprint](https://github.com/darrenhinde/OpenAgentsControl/blob/main/docs/features/agent-system-blueprint.md) — agent architecture and context management design

#### Building Custom Tool Loops from Scratch
- [Build a Coding Agent from Scratch: Complete Python Tutorial](https://www.siddharthbharath.com/build-a-coding-agent-python-tutorial/) — ~400 lines, ReAct loop, file tools, bash execution, search, edit
- [How to Build a General Purpose AI Agent in 131 Lines of Python](https://hugobowne.substack.com/p/how-to-build-a-general-purpose-ai) — minimal agent loop implementation
- [Building an AI Agent from Scratch in Python](https://www.leoniemonigatti.com/blog/ai-agent-from-scratch-in-python.html) — tool loop, state management, decision making
- [Create Your Own Bash Computer Use Agent — NVIDIA Tutorial](https://developer.nvidia.com/blog/create-your-own-bash-computer-use-agent-with-nvidia-nemotron-in-one-hour/) — bash tool agent with safety constraints
- [Basic Agentic Loop with Tool Calling — Temporal Docs](https://docs.temporal.io/ai-cookbook/agentic-loop-tool-call-openai-python) — durable tool loop with OpenAI, applicable to any provider
- [How Coding Agents Actually Work: Inside OpenCode (Deep Dive)](https://cefboud.com/posts/coding-agents-internals-opencode-deepdive/) — tool dispatch, permission system, LSP feedback loop internals
