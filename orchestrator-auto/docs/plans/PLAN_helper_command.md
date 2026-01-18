# Plan: `orchestrator helper` Command

AI-powered documentation assistant that answers questions about orchestrator-auto by referencing bundled documentation.

## Feature Description

Add a new CLI command `orchestrator helper "your question"` that uses Claude Haiku to answer user questions about orchestrator-auto, using bundled documentation as context.

**Example usage:**
```bash
orchestrator helper "how do I use queue mode?"
orchestrator helper "what's the difference between -pm and -em?"
orchestrator helper "how do I set up telegram notifications?"
orchestrator helper "what models are available?" -m sonnet
```

---

## Milestone 1: Core CLI Command with Bundled Docs

### Goal
Implement the `helper` command with properly packaged documentation that works when installed via pip outside the repo.

### Tasks
- [ ] Create `orchestrator_auto/resources/` directory for bundled docs
- [ ] Copy essential docs to bundle: `README.md`, `CLI_REFERENCE.md`, `CONFIGURATION.md`, `TROUBLESHOOTING.md`
- [ ] Update `pyproject.toml` to include `resources/*.md` as package data
- [ ] Create `orchestrator_auto/resources/__init__.py` with `load_docs()` function using `importlib.resources`
- [ ] Add `helper` command to `cli.py` with Click decorators:
  - Positional `question` argument
  - `-m/--model` option (default: `haiku`)
  - `-v/--verbose` flag to show included docs
- [ ] Use `get_model_id()` from `config.py` for model alias resolution
- [ ] Use `create_chat_agent(..., allowed_tools=[])` from `agents.py` for docs-only safety
- [ ] Construct prompt with guardrails: "Answer using only the provided documentation. If the answer is not found, say so and suggest where the user might look."
- [ ] Check auth before running; if missing, show same guidance as `check` command
- [ ] Print response to stdout

### Deliverables
- `orchestrator_auto/resources/` with bundled docs
- Updated `pyproject.toml` with package data
- Working `orchestrator helper "question"` command
- Uses Haiku by default, supports aliases and full model IDs

### Validation
```bash
# Basic usage
orchestrator helper "how do I start a workflow?"
orchestrator helper "what options does todo have?"

# Model selection (alias and full ID)
orchestrator helper "explain queue mode" -m sonnet
orchestrator helper "explain queue mode" -m claude-haiku-3-5-20241022

# Verbose mode
orchestrator helper "how do I resume?" -v

# Help
orchestrator helper --help

# Test installed package (outside repo)
pip install -e . && cd /tmp && orchestrator helper "how do I use --tui?"
```

### Risks / Notes
- Bundled docs must be kept in sync with source docs (consider a sync script or CI check)
- Total docs size ~50KB, well within context limits
- `allowed_tools=[]` ensures agent cannot read arbitrary files - answers come only from provided context

---

## Milestone 2: Documentation and Testing

### Goal
Add tests following established patterns and update README with the new command.

### Tasks
- [ ] Create `tests/test_helper.py` following pattern from `tests/test_cli_chat.py`:
  - Patch `create_chat_agent` to return mock agent
  - Stub `send_message()` to return test response
  - Assert prompt includes docs content + user question
  - Assert `allowed_tools=[]` is passed for safety
  - Test model alias resolution
  - Test verbose flag output
  - Test missing auth error handling
- [ ] Add helper command to README.md Quick Reference table
- [ ] Add helper section to README.md (after Direct Chat section)
- [ ] Add helper to bundled `resources/README.md`

### Deliverables
- Test coverage for helper command
- README documentation (source and bundled)

### Validation
```bash
pytest tests/test_helper.py -v
grep -A2 "helper" orchestrator-auto/README.md
```

### Risks / Notes
- Tests must mock API calls to avoid actual charges
- Keep README section brief - it's a simple feature

---

## Implementation Details

### Package Structure
```
orchestrator_auto/
├── resources/
│   ├── __init__.py      # load_docs() using importlib.resources
│   ├── README.md        # Bundled copy
│   ├── CLI_REFERENCE.md
│   ├── CONFIGURATION.md
│   └── TROUBLESHOOTING.md
├── cli.py               # Add helper command
└── ...
```

### pyproject.toml Addition
```toml
[tool.setuptools.package-data]
orchestrator_auto = ["resources/*.md"]
```

### load_docs() Function
```python
# orchestrator_auto/resources/__init__.py
from importlib import resources

def load_docs() -> str:
    """Load bundled documentation for helper command."""
    docs = []
    for filename in ["README.md", "CLI_REFERENCE.md", "CONFIGURATION.md", "TROUBLESHOOTING.md"]:
        try:
            content = resources.files(__package__).joinpath(filename).read_text()
            docs.append(f"# {filename}\n\n{content}")
        except FileNotFoundError:
            pass
    return "\n\n---\n\n".join(docs)
```

### Prompt Template
```
You are a helpful assistant answering questions about orchestrator-auto.

Answer the user's question using ONLY the documentation provided below.
If the answer is not found in the documentation, say so clearly and suggest
where the user might look (e.g., --help, GitHub issues, or the docs/ folder).

<documentation>
{docs_content}
</documentation>

Question: {question}
```

---

## Summary

| Milestone | Effort | Description |
|-----------|--------|-------------|
| M1 | ~1.5 hours | Core command with bundled docs and safety |
| M2 | ~30 min | Tests and documentation |

**Total estimated effort: ~2 hours**

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Docs packaging | `importlib.resources` | Works when installed via pip outside repo |
| API client | `create_chat_agent(..., allowed_tools=[])` | Reuses existing code, no new deps, docs-only safety |
| Default model | Haiku | Cheapest, fast enough for Q&A |
| Streaming | No | Single response is fine for short answers |
| Context sources | Bundled README + docs/*.md | Rich context without dynamic CLI introspection |
| Model resolution | Via `get_model_id()` | Consistency with other commands |
