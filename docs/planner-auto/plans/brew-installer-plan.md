# Homebrew Installation Plan for planner-auto

**Goal:** `brew install planner-auto` → `planner-auto start --project my-app`

---

## Package Info

From `planner-auto/pyproject.toml`:

| Field | Value |
|-------|-------|
| Name | `planner-auto` |
| Version | `0.3.0` (Plan 1 + Plan 2 + Observability) |
| Python requirement | `>=3.10` |
| Entry point | `planner-auto = "planner_auto.cli:cli"` |
| Core deps | `claude-agent-sdk>=0.1.50,<0.2.0`, `click>=8.0`, `prompt_toolkit>=3.0`, `openai>=2.0` |
| Optional deps | None |

---

## Prerequisites (Before Brew Setup)

### 1. Publish to PyPI

planner-auto is not yet on PyPI. Must publish first.

```bash
cd planner-auto/
pip install build twine

# Build sdist + wheel
python -m build

# Upload to PyPI
twine upload dist/*
```

**Verify after publishing:**
```bash
pip install planner-auto  # Should work from PyPI
planner-auto --help       # Should show CLI help
```

### 2. pyproject.toml Updates Before Publishing

Add missing metadata required by PyPI:

```toml
[project]
name = "planner-auto"
version = "0.1.0"
description = "Interactive planning session manager with SQLite persistence and artifact export"
license = "MIT"
requires-python = ">=3.10"
authors = [
    {name = "Danny Almaden", email = "dan@ailab.ph"},
]
readme = "README.md"
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]
keywords = ["planning", "claude", "ai", "orchestration", "milestone"]

[project.urls]
Homepage = "https://github.com/ailabph/claude-ai-workflows"
Repository = "https://github.com/ailabph/claude-ai-workflows"
```

---

## Approach: Same Tap, Separate Formula

Reuse the existing `ailabph/homebrew-orchestrator-auto` tap. Add a second formula for planner-auto.

**Why same tap:**
- Both tools are part of the same AI workflow pipeline
- Users likely install both
- One `brew tap` command covers both tools
- Simpler maintenance

**Tap rename consideration:** The tap is currently named `homebrew-orchestrator-auto`. With two tools, consider renaming to `homebrew-ai-workflows` or `homebrew-ailabph`. This is a breaking change for existing users — defer until planner-auto is stable.

**For now:** Add `Formula/planner-auto.rb` alongside `Formula/orchestrator-auto.rb` in the existing tap.

---

## Formula

File: `Formula/planner-auto.rb` in `ailabph/homebrew-orchestrator-auto` tap repo.

```ruby
class PlannerAuto < Formula
  include Language::Python::Virtualenv

  desc "Automated planning session manager with Claude AI and GPT review"
  homepage "https://github.com/ailabph/claude-ai-workflows"
  url "https://files.pythonhosted.org/packages/source/p/planner-auto/planner_auto-0.1.0.tar.gz"
  sha256 "REPLACE_WITH_ACTUAL_SHA256"
  license "MIT"

  depends_on "python@3.13"

  # --- Core dependencies ---
  # Run `poet planner-auto` to get real URLs + sha256s

  resource "claude-agent-sdk" do
    url "https://files.pythonhosted.org/packages/.../claude_agent_sdk-0.1.50.tar.gz"
    sha256 "REPLACE"
  end

  resource "click" do
    url "https://files.pythonhosted.org/packages/.../click-8.1.8.tar.gz"
    sha256 "REPLACE"
  end

  resource "prompt_toolkit" do
    url "https://files.pythonhosted.org/packages/.../prompt_toolkit-3.0.50.tar.gz"
    sha256 "REPLACE"
  end

  # Plan 2 will add:
  # resource "openai" do ... end  (for GPT reviewer)

  def install
    virtualenv_install_with_resources
  end

  test do
    system bin/"planner-auto", "--help"
  end
end
```

---

## Resource Stanza Generation

Create `scripts/regenerate_brew_resources_planner.sh` (modeled on the orchestrator version):

```bash
#!/usr/bin/env bash
# Regenerate Homebrew resource stanzas for planner-auto.
#
# USAGE
#   ./scripts/regenerate_brew_resources_planner.sh
#
# OUTPUT
#   Prints all resource stanzas to stdout.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG_DIR="$REPO_ROOT/planner-auto"
PYPROJECT="$PKG_DIR/pyproject.toml"

VERSION=$(grep '^version = ' "$PYPROJECT" | sed 's/^version = "\(.*\)"$/\1/')
echo "==> Package version: $VERSION" >&2

VENV_DIR="$(mktemp -d)/poet-venv"
echo "==> Creating isolated venv at $VENV_DIR..." >&2
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "==> Installing homebrew-pypi-poet and planner-auto from local source..." >&2
pip install -q --upgrade pip
pip install -q homebrew-pypi-poet
pip install -q "$PKG_DIR"

echo "==> Running poet planner-auto..." >&2
poet planner-auto

echo "" >&2
echo "==> Done. Copy stanzas into Formula/planner-auto.rb" >&2
```

---

## Installation Flow (User)

```bash
# Tap (one-time, covers both tools)
brew tap ailabph/orchestrator-auto

# Install
brew install planner-auto

# Auth setup
export ANTHROPIC_API_KEY="sk-ant-api03-your-key"
# OR
export CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat01-your-token"

# Verify
planner-auto --help
```

Or one-liner:
```bash
brew install ailabph/orchestrator-auto/planner-auto
```

---

## Automated Release Pipeline

Model after orchestrator-auto's `release.yml`:

```yaml
# .github/workflows/release-planner.yml
name: Release planner-auto

on:
  push:
    tags:
      - 'planner-v*'

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Build and publish to PyPI
        run: |
          cd planner-auto
          pip install build twine
          python -m build
          twine upload dist/*
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN_PLANNER }}

      - name: Update Homebrew formula
        uses: mislav/bump-homebrew-formula-action@v3
        with:
          formula-name: planner-auto
          homebrew-tap: ailabph/homebrew-orchestrator-auto
          tag-name: ${{ github.ref_name }}
        env:
          COMMITTER_TOKEN: ${{ secrets.HOMEBREW_TAP_TOKEN }}
```

**Tag convention:** `planner-v0.1.0` (separate from orchestrator's `v1.10.0` tags)

---

## Dependencies to Watch

| Dependency | Notes |
|-----------|-------|
| `claude-agent-sdk` | Shared with orchestrator-auto. Pin to `>=0.1.50,<0.2.0`. When SDK upgrades, both formulas need resource regeneration. |
| `click` | Stable. Shared with orchestrator-auto. |
| `prompt_toolkit` | Stable. Shared with orchestrator-auto. |
| `openai` (Plan 2) | Will be added when reviewer is implemented. Resource regeneration needed. |

---

## Monorepo Considerations

Same caveat as orchestrator-auto: GitHub release tarballs unpack as `claude-ai-workflows-<tag>/planner-auto/...`. If using GitHub tarball instead of PyPI:

```ruby
def install
  venv = virtualenv_create(libexec, "python3.13")
  venv.pip_install resources
  venv.pip_install_and_link buildpath/"planner-auto"
end
```

**Recommendation:** Use PyPI sdist (same as orchestrator-auto). Cleaner, no monorepo workaround needed.

---

## Checklist

- [ ] Update pyproject.toml with PyPI metadata (authors, readme, classifiers, urls)
- [ ] Build and publish to PyPI (`python -m build && twine upload dist/*`)
- [ ] Verify `pip install planner-auto` works from PyPI
- [ ] Create `scripts/regenerate_brew_resources_planner.sh`
- [ ] Run poet to generate resource stanzas
- [ ] Add `Formula/planner-auto.rb` to `ailabph/homebrew-orchestrator-auto` tap
- [ ] `brew audit --strict Formula/planner-auto.rb`
- [ ] `brew install --build-from-source ailabph/orchestrator-auto/planner-auto`
- [ ] `brew test planner-auto`
- [ ] Push formula to tap repo
- [ ] Set up `release-planner.yml` GitHub Action
- [ ] Test full flow: `brew tap ailabph/orchestrator-auto && brew install planner-auto`

---

## Timing

**Wait for Plan 2** before publishing to PyPI / Homebrew. Reason:
- Plan 1 alone is useful but limited (no reviewer loop)
- Publishing v0.1.0 then immediately releasing v0.2.0 with the reviewer creates churn
- Better to publish v1.0.0 with the full feature set (session core + reviewer)

**Exception:** If Plan 1 is needed as a standalone tool before Plan 2 is ready, publish as v0.1.0-alpha or v0.1.0 with a clear note that the reviewer is coming.
