# Plan: `orchestrator helper` Command

AI-powered documentation assistant that answers questions about orchestrator-auto by referencing bundled documentation.

## Feature Description

Add a new CLI command `orchestrator helper "your question"` that uses Claude Haiku to answer user questions about orchestrator-auto, using bundled documentation as context.

**Example usage:**
```bash
orchestrator helper "how do I use queue mode?"
orchestrator helper how do I use queue mode        # Unquoted also works
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
- [ ] Copy essential docs to bundle (source → destination):
  - `orchestrator-auto/README.md` → `orchestrator_auto/resources/README.md`
  - `orchestrator-auto/docs/CLI_REFERENCE.md` → `orchestrator_auto/resources/CLI_REFERENCE.md`
  - `orchestrator-auto/docs/CONFIGURATION.md` → `orchestrator_auto/resources/CONFIGURATION.md`
  - `orchestrator-auto/docs/TROUBLESHOOTING.md` → `orchestrator_auto/resources/TROUBLESHOOTING.md`
- [ ] Update `pyproject.toml` to include `resources/*.md` as package data
- [ ] Create `orchestrator_auto/resources/__init__.py` with `load_docs()` function using `importlib.resources`
  - Return tuple: `(docs_text, included_files)` for verbose mode testability
  - Use explicit `encoding="utf-8"` in `read_text()` for cross-platform safety
- [ ] Add `helper` command to `cli.py` with Click decorators:
  - `@click.argument('question', nargs=-1, required=True)` for unquoted questions
  - Join question parts: `question_text = " ".join(question)`
  - `-m/--model` option (default: `haiku`)
  - `-v/--verbose` flag to show included doc filenames
- [ ] Use `resolve_model()` from `orchestrator_auto.config` for model alias resolution
- [ ] Use `create_chat_agent(..., allowed_tools=[])` from `agents.py` for docs-only safety
- [ ] Construct prompt with guardrails: "Answer using only the provided documentation. If the answer is not found, say so and suggest where the user might look."
- [ ] Check auth before running; if missing, show same guidance as `check` command
- [ ] Print response to stdout

### Deliverables
- `orchestrator_auto/resources/` with bundled docs
- Updated `pyproject.toml` with package data
- Working `orchestrator helper "question"` command
- Supports unquoted questions: `orchestrator helper how do I resume`
- Uses Haiku by default, supports aliases and full model IDs

### Validation
```bash
# Basic usage (quoted and unquoted)
orchestrator helper "how do I start a workflow?"
orchestrator helper how do I start a workflow

# Model selection (alias and full ID)
orchestrator helper "explain queue mode" -m sonnet
orchestrator helper "explain queue mode" -m claude-haiku-3-5-20241022

# Verbose mode (shows included files)
orchestrator helper "how do I resume?" -v
# Should output: "Including: README.md, CLI_REFERENCE.md, ..."

# Help
orchestrator helper --help

# Test installed package (outside repo)
pip install -e . && cd /tmp && orchestrator helper "how do I use --tui?"
```

### Risks / Notes
- Bundled docs must be kept in sync with source docs (see sync process below)
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
  - Test model alias resolution via `resolve_model()`
  - Test verbose flag outputs included filenames
  - Test unquoted question handling (`nargs=-1`)
  - Test missing auth error handling
- [ ] Update source README (`orchestrator-auto/README.md`):
  - Add helper command to Quick Reference table
  - Add helper section after Direct Chat section
- [ ] Re-copy updated README to bundle: `orchestrator-auto/README.md` → `orchestrator_auto/resources/README.md`

### Deliverables
- Test coverage for helper command
- README documentation (source updated, then copied to bundle)

### Validation
```bash
pytest tests/test_helper.py -v
grep -A2 "helper" orchestrator-auto/README.md
```

### Risks / Notes
- Tests must mock API calls to avoid actual charges
- Keep README section brief - it's a simple feature
- Always update source README first, then copy to bundle

---

## Implementation Details

### Package Structure
```
orchestrator-auto/
├── README.md                    # Source of truth
├── docs/
│   ├── CLI_REFERENCE.md         # Source of truth
│   ├── CONFIGURATION.md         # Source of truth
│   └── TROUBLESHOOTING.md       # Source of truth
└── orchestrator_auto/
    ├── resources/
    │   ├── __init__.py          # load_docs() using importlib.resources
    │   ├── README.md            # Copied from orchestrator-auto/README.md
    │   ├── CLI_REFERENCE.md     # Copied from orchestrator-auto/docs/
    │   ├── CONFIGURATION.md     # Copied from orchestrator-auto/docs/
    │   └── TROUBLESHOOTING.md   # Copied from orchestrator-auto/docs/
    ├── cli.py                   # Add helper command
    └── config.py                # resolve_model() at line 240
```

### Docs Sync Process
Source files are the single source of truth. Bundled copies are derived:

```bash
# Manual sync (or add to CI/Makefile)
cp orchestrator-auto/README.md orchestrator_auto/resources/README.md
cp orchestrator-auto/docs/CLI_REFERENCE.md orchestrator_auto/resources/
cp orchestrator-auto/docs/CONFIGURATION.md orchestrator_auto/resources/
cp orchestrator-auto/docs/TROUBLESHOOTING.md orchestrator_auto/resources/
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
from typing import Tuple, List

def load_docs() -> Tuple[str, List[str]]:
    """Load bundled documentation for helper command.

    Returns:
        Tuple of (combined_docs_text, list_of_included_filenames)
    """
    docs = []
    included = []
    for filename in ["README.md", "CLI_REFERENCE.md", "CONFIGURATION.md", "TROUBLESHOOTING.md"]:
        try:
            content = resources.files(__package__).joinpath(filename).read_text(encoding="utf-8")
            docs.append(f"# {filename}\n\n{content}")
            included.append(filename)
        except FileNotFoundError:
            pass
    return "\n\n---\n\n".join(docs), included
```

### CLI Command
```python
@cli.command('helper')
@click.argument('question', nargs=-1, required=True)
@click.option('-m', '--model', default='haiku', help='Model: opus, sonnet, haiku (default: haiku)')
@click.option('-v', '--verbose', is_flag=True, help='Show included documentation files')
def helper(question: tuple, model: str, verbose: bool):
    """Ask questions about orchestrator-auto (AI-powered)."""
    from .resources import load_docs
    from .config import resolve_model

    question_text = " ".join(question)
    # ... rest of implementation
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
| Model resolution | Via `resolve_model()` from `config.py` | Correct function, consistency with other commands |
| Question input | `nargs=-1` | Allows unquoted questions for better UX |
| Verbose output | Return included filenames | Deterministic, testable output |
| Text encoding | Explicit `utf-8` | Cross-platform safety |
| Docs sync | Source → bundle copy | Single source of truth in repo root |
