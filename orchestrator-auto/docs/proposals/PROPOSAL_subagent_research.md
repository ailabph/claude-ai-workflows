# Proposal: Context-Isolated Research Agents

**Status:** Approved
**Phase:** 2 (Deferred)
**Author:** Engineering Team
**Created:** 2026-01-28
**Updated:** 2026-01-28
**Category:** Context Management

---

## Version Context

This proposal builds on **orchestrator-auto v1.2.0** (Claude Agent SDK 0.1.23) and requires Phase 1 subagent patterns (Exploration) to be stable before implementation.

| Component | Version | Relevant Feature |
|-----------|---------|------------------|
| orchestrator-auto | 1.2.0 | Subagent foundation from Phase 1 |
| claude-agent-sdk | 0.1.23 | Task tool, WebFetch, context isolation |

---

## Executive Summary

Implement context-isolated research sub-agents that perform deep-dive investigations without polluting the main agent's context window. These agents can explore external documentation, analyze complex codebases, or research solutions—returning only summarized, actionable findings to the parent agent.

## Problem Statement

Current agent architecture suffers from context pollution:

1. **Exploration bloat** - Reading many files fills context with potentially irrelevant content
2. **Research tangents** - Investigating solutions adds noise to implementation context
3. **Token accumulation** - Long sessions accumulate context that degrades performance
4. **Documentation overload** - External docs consume valuable context space

Example scenario:
```
Executor needs to implement OAuth2 integration
→ Reads 15 files to understand existing auth
→ Fetches OAuth2 documentation
→ Explores 3 different library options
→ Context now 80% research, 20% implementation
→ Agent loses focus, makes mistakes
```

## Proposed Solution

Introduce **Research Agents** with complete context isolation:

```
┌─────────────────────────────────────────────────────────────────┐
│  MAIN AGENT (Executor/Planner)                                  │
│  Context: Clean, focused on current milestone                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  "I need to understand OAuth2 implementation patterns"         │
│                         │                                       │
│                         ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  RESEARCH AGENT (Isolated Context)                          ││
│  │                                                             ││
│  │  1. Fetch OAuth2 documentation                              ││
│  │  2. Read existing auth implementation                       ││
│  │  3. Compare library options                                 ││
│  │  4. Analyze security considerations                         ││
│  │                                                             ││
│  │  Context: 50,000 tokens of research                         ││
│  └─────────────────────────────────────────────────────────────┘│
│                         │                                       │
│                         ▼                                       │
│  Research Summary (500 tokens):                                 │
│  - Use authlib library (most maintained)                        │
│  - Follow existing pattern in auth/oauth.py                     │
│  - Key methods: create_client(), get_token()                    │
│  - Security: validate redirect_uri, use PKCE                    │
│                                                                 │
│  Main agent continues with clean context + summary              │
└─────────────────────────────────────────────────────────────────┘
```

### Architecture

```python
class ResearchAgent:
    """Context-isolated agent for deep research tasks."""

    def __init__(
        self,
        model: str = "haiku",  # Cost-effective for research
        max_context: int = 100_000,
        summary_max_tokens: int = 1000
    ):
        self.client = ClaudeSDKClient(model=model)
        self.max_context = max_context
        self.summary_max_tokens = summary_max_tokens

    async def research(
        self,
        query: str,
        sources: List[ResearchSource],
        output_format: str = "summary"
    ) -> ResearchResult:
        """
        Perform isolated research and return summarized findings.

        Args:
            query: Research question or topic
            sources: Where to look (codebase, web, docs)
            output_format: summary | structured | raw
        """
        # Fresh context for each research task
        findings = await self._gather_findings(query, sources)

        # Compress findings to summary
        summary = await self._summarize(findings, output_format)

        return ResearchResult(
            query=query,
            summary=summary,
            sources_consulted=len(findings),
            tokens_processed=self._count_tokens(findings),
            tokens_returned=self._count_tokens(summary)
        )
```

### Research Source Types

```python
class ResearchSource(Enum):
    CODEBASE = "codebase"       # Local files via Glob/Grep/Read
    WEB_DOCS = "web_docs"       # External documentation
    WEB_SEARCH = "web_search"   # General web search
    GITHUB = "github"           # GitHub issues, PRs, discussions
    STACK_OVERFLOW = "stackoverflow"  # Q&A lookup

class ResearchRequest:
    query: str
    sources: List[ResearchSource]
    scope: Optional[str] = None  # e.g., "src/auth/" for codebase
    max_depth: int = 10          # Max files/pages to explore
    focus: Optional[str] = None  # e.g., "security considerations"
```

### Integration with Main Agents

```python
class ExecutorAgent(BaseAgent):
    def __init__(self, ...):
        super().__init__(...)
        self.research_agent = ResearchAgent(model="haiku")

    async def execute_with_research(
        self,
        milestone: str,
        research_queries: List[str] = None
    ) -> str:
        # Detect if milestone needs research
        if research_queries or self._needs_research(milestone):
            queries = research_queries or self._extract_research_needs(milestone)

            # Run research in parallel
            research_results = await asyncio.gather(
                *[self.research_agent.research(q) for q in queries]
            )

            # Inject summaries (not raw findings) into context
            context = self._format_research_context(research_results)
        else:
            context = ""

        # Execute with enriched but clean context
        return await self.query_async(f"{context}\n\n{milestone}")

    def _needs_research(self, milestone: str) -> bool:
        """Detect if milestone likely needs research."""
        research_indicators = [
            "integrate with",
            "implement according to",
            "follow the pattern",
            "like existing",
            "similar to",
            "documentation",
            "specification",
        ]
        return any(ind in milestone.lower() for ind in research_indicators)
```

### Configuration

```yaml
# config.yaml
research:
  enabled: true
  model: haiku                  # Cost-effective research
  max_parallel: 3               # Concurrent research queries
  summary_max_tokens: 1000      # Summary size limit

  sources:
    codebase:
      enabled: true
      max_files: 20
    web_docs:
      enabled: true
      allowed_domains:
        - docs.python.org
        - developer.mozilla.org
        - react.dev
    web_search:
      enabled: false            # Disabled by default
    github:
      enabled: true
      max_issues: 10

  auto_research:
    enabled: true
    triggers:
      - "integrate with"
      - "implement.*pattern"
      - "according to.*spec"
```

### CLI Integration

```bash
# Enable research (default when configured)
orchestrator start -f "Add OAuth2 login" --research

# Specify research sources
orchestrator start -f "Add OAuth2 login" --research-sources codebase,web_docs

# Disable for simple tasks
orchestrator start -f "Fix typo" --no-research

# Explicit research query
orchestrator start -f "Add caching" \
  --research-query "Redis vs Memcached for session storage"

# View research stats
orchestrator status <session-id>
# Output:
# Milestone 2: OAuth2 Integration
#   Research performed:
#     - "OAuth2 PKCE flow implementation" (3 sources, 45K tokens → 800 summary)
#     - "Existing auth patterns" (12 files, 28K tokens → 500 summary)
#   Context efficiency: 73K tokens researched → 1.3K tokens injected
```

## Implementation Plan

### Phase 1: Core Research Agent
- Implement ResearchAgent class with context isolation
- Add summarization pipeline
- Create research prompt templates

### Phase 2: Source Handlers
- Codebase source (Glob, Grep, Read)
- Web documentation fetcher
- GitHub API integration

### Phase 3: Integration
- Add research hooks to ExecutorAgent
- Implement auto-research detection
- Add research metrics tracking

### Phase 4: Optimization
- Research result caching
- Incremental research (build on prior findings)
- Cross-session research memory

## Benefits

| Benefit | Impact |
|---------|--------|
| Clean main context | 70-90% context reduction |
| Deeper research | Can explore more without limit |
| Cost optimization | Use Haiku for research, Sonnet for implementation |
| Better focus | Main agent stays on task |
| Reusable findings | Cache research across milestones |

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Summary loses important details | Structured summaries with key points |
| Research takes too long | Parallel queries, timeouts |
| Wrong research direction | Main agent can request clarification |
| API cost increase | Use Haiku, cache results |
| Hallucinated research | Always cite sources in summary |

## Cost Analysis

| Scenario | Without Research Agent | With Research Agent |
|----------|----------------------|---------------------|
| Context tokens | 80,000 (bloated) | 25,000 (clean) |
| Research tokens | 0 (inline) | 50,000 (Haiku) |
| Effective cost | High (Sonnet bloat) | Lower (Haiku research) |
| Quality | Degraded focus | Sharp focus |

**Trade-off:** More total tokens, but cheaper per token and better output quality.

## Success Metrics

- Context size reduction (main agent)
- Research reuse rate (cache hits)
- Implementation quality (fewer revisions)
- Token cost per milestone

## Effort Estimate

**Complexity:** Medium
**Files Modified:** 3-4 (agents.py, engine.py, config.py)
**New Files:** 4-6 (research.py, sources/, summarizer.py, cache.py)
**Testing:** Isolation tests, summary quality tests

---

## Appendix: Research Summary Format

```markdown
## Research Summary: OAuth2 PKCE Implementation

### Key Findings
1. **Library Choice**: Use `authlib` (most active, best docs)
2. **Existing Pattern**: See `src/auth/oauth_base.py` for provider pattern
3. **Security**: Always validate `redirect_uri`, implement PKCE for public clients

### Implementation Steps
1. Create `GoogleOAuthProvider(OAuthBase)` in `src/auth/providers/`
2. Add routes in `src/auth/routes.py` following existing pattern
3. Store tokens using existing `TokenStore` class

### Code Snippets
```python
# From existing oauth_base.py - follow this pattern
class OAuthBase:
    def create_client(self): ...
    def get_token(self, code): ...
```

### Sources Consulted
- `src/auth/oauth_base.py` (existing implementation)
- `src/auth/providers/github.py` (reference provider)
- https://docs.authlib.org/en/latest/client/oauth2.html
- https://oauth.net/2/pkce/

### Tokens: 45,231 processed → 892 returned (98% compression)
```

## Appendix: Auto-Research Trigger Examples

```python
RESEARCH_TRIGGERS = {
    # Pattern -> Research query template
    r"integrate with (\w+)": "How to integrate with {1} in this codebase",
    r"implement (\w+) pattern": "Best practices for {1} pattern implementation",
    r"like existing (\w+)": "Analyze existing {1} implementation patterns",
    r"according to (\w+) spec": "Key requirements from {1} specification",
    r"migrate from (\w+) to (\w+)": "Migration guide from {1} to {2}",
}

# Example detections:
# "integrate with Stripe" → Research: "How to integrate with Stripe in this codebase"
# "implement caching pattern" → Research: "Best practices for caching pattern implementation"
```
