# Homebrew Installer Proposal for planner-auto v0.5.0

## Goal

`brew install planner-auto` installs a working CLI with all core dependencies. Users run `planner-auto start --project my-app` immediately after install. TUI is a separate optional install via `pip install planner-auto[tui]` (Homebrew formula covers core deps only).

---

## Current State

| Item | Status |
|------|--------|
| PyPI package | **Not published** — `pip install planner-auto` does not work yet |
| Homebrew formula | **Not created** — `brew install planner-auto` does not work yet |
| Homebrew tap | **Exists** — `ailabph/homebrew-orchestrator-auto` has orchestrator-auto formula |
| Release workflow | **Exists for orchestrator-auto** — `.github/workflows/release.yml` (detect → publish → update-homebrew) |
| Resource script | **Exists for orchestrator-auto** — `scripts/regenerate_brew_resources.sh` |
| Release guide | **Exists for orchestrator-auto** — `docs/RELEASE.md` |

**Key insight:** The orchestrator-auto pipeline is mature and proven. planner-auto should mirror it exactly — same tap, same 3-job workflow, same resource strategy.

---

## Prerequisites (Must Fix Before Publishing)

### P1: Add `[tool.setuptools.package-data]` for theme.tcss

The TUI's `theme.tcss` file will NOT be included in sdist/wheel without explicit package-data config. The orchestrator-auto pyproject.toml has:

```toml
[tool.setuptools.package-data]
orchestrator_auto = ["resources/*.md", "tui/styles/*.tcss"]
```

planner-auto needs the equivalent:

```toml
[tool.setuptools.package-data]
planner_auto = ["tui/styles/*.tcss"]
```

Without this, `pip install planner-auto[tui]` will crash at runtime when Textual tries to load the theme.

### P2: Add PyPI metadata to pyproject.toml

Missing fields required for PyPI:

```toml
[project]
authors = [
    {name = "Danny Almaden", email = "dan@ailab.ph"},
]
readme = "README.md"
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
]
keywords = ["planning", "claude", "ai", "orchestration", "milestone", "gpt", "review"]

[project.urls]
Homepage = "https://github.com/ailabph/claude-ai-workflows"
Repository = "https://github.com/ailabph/claude-ai-workflows"
Changelog = "https://github.com/ailabph/claude-ai-workflows/blob/main/planner-auto/CHANGELOG.md"
```

### P3: Configure PyPI Trusted Publishing

Set up OIDC Trusted Publishing for `planner-auto` on PyPI (same mechanism as orchestrator-auto):

1. Create `planner-auto` project on PyPI (first-time manual upload with `twine`, or pre-register via PyPI UI)
2. Configure Trusted Publisher: GitHub Actions from `ailabph/claude-ai-workflows`, workflow `release-planner.yml`, environment `pypi`
3. No long-lived API tokens needed after setup

### P4: Verify `HOMEBREW_TAP_TOKEN` scope

The existing `HOMEBREW_TAP_TOKEN` secret (fine-grained PAT scoped to `ailabph/homebrew-orchestrator-auto`) should already work for pushing a new formula file to the same tap. Verify it has write access to repo contents.

---

## What Gets Installed

### Core formula (Homebrew)

Covers `[project.dependencies]` — everything needed for CLI use:

| Dependency | Version | Purpose |
|-----------|---------|---------|
| `click` | >=8.0 | CLI framework |
| `claude-agent-sdk` | >=0.1.50,<0.2.0 | Claude SDK (subprocess backend) |
| `anthropic` | >=0.40.0 | Direct API backend |
| `prompt_toolkit` | >=3.0 | Interactive discuss mode |
| `openai` | >=2.0 | GPT-5.4 reviewer |
| `python-dotenv` | >=1.0 | .env auto-loading |

**NOT included in formula:** `textual` (TUI is optional). Users who want `--tui` run `pip install planner-auto[tui]` after brew install. This matches orchestrator-auto's pattern — the formula includes TUI resources but textual is a core dep there because the TUI is the primary interface. For planner-auto, the CLI is the primary interface.

**Decision point:** Include `textual` in the formula or not?

| Option | Pros | Cons |
|--------|------|------|
| **A: Core deps only** | Smaller install, faster, fewer resource blocks (~25 vs ~45) | `--tui` requires separate `pip install` step |
| **B: Include textual** | `--tui` works out of the box | 20+ extra resource blocks for textual's transitive deps, bigger install |

**Recommendation:** Option A (core only) for v1. The review loop works fine without TUI — it's an enhancement. Users who discover `--tui` are comfortable running `pip install`.

---

## Approach: Same Tap, Second Formula

Add `Formula/planner-auto.rb` alongside `Formula/orchestrator-auto.rb` in the existing `ailabph/homebrew-orchestrator-auto` tap.

**Why same tap:**
- Both tools are part of the same AI workflow pipeline (planner feeds orchestrator)
- Users likely install both
- One `brew tap` command covers both tools
- Simpler maintenance — one tap repo, shared `HOMEBREW_TAP_TOKEN`

**Tap rename consideration:** The tap is named `homebrew-orchestrator-auto`. With two formulas, renaming to `homebrew-ai-workflows` would be cleaner. This is a breaking change for existing orchestrator-auto users (`brew untap` + `brew tap`). Defer until a third tool is added.

---

## Formula

File: `Formula/planner-auto.rb` in `ailabph/homebrew-orchestrator-auto` tap.

```ruby
class PlannerAuto < Formula
  include Language::Python::Virtualenv

  desc "AI planning session manager with Claude planner and GPT reviewer"
  homepage "https://github.com/ailabph/claude-ai-workflows"
  url "https://files.pythonhosted.org/packages/source/p/planner-auto/planner_auto-0.5.0.tar.gz"
  sha256 "REPLACE_WITH_ACTUAL_SHA256"
  license "MIT"

  depends_on "python@3.13"

  # --- Resource stanzas generated by:
  # ./scripts/regenerate_brew_resources_planner.sh
  # --- Do NOT edit manually. Regenerate when deps change.

  # REPLACE with output of: poet planner-auto

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "Usage:", shell_output("#{bin}/planner-auto --help")
  end
end
```

---

## Release Workflow

File: `.github/workflows/release-planner.yml`

Mirrors `release.yml` exactly, scoped to planner-auto:

```
Trigger: push to main when planner-auto/pyproject.toml changes

Job 1: detect
  - Read version from planner-auto/pyproject.toml
  - Check PyPI: curl https://pypi.org/pypi/planner-auto/${VERSION}/json
  - 404 → should_publish=true, 200 → skip

Job 2: publish (if should_publish)
  - Build sdist + wheel from planner-auto/
  - Verify theme.tcss in both artifacts
  - Publish via OIDC Trusted Publishing
  - Poll PyPI for 90s until version is live

Job 3: update-homebrew
  - Fetch sdist SHA256 from PyPI JSON API
  - Clone ailabph/homebrew-orchestrator-auto
  - Update Formula/planner-auto.rb url + sha256 (top-level only, 2-space indent)
  - Commit and push to tap
```

**Key differences from orchestrator-auto workflow:**
- Trigger path: `planner-auto/pyproject.toml` (not `orchestrator-auto/`)
- PyPI package name: `planner-auto` (not `orchestrator-auto`)
- Formula file: `Formula/planner-auto.rb`
- Working directory: `planner-auto/` for build steps
- Environment name: `pypi` (same — or create `pypi-planner` for separate OIDC config)

Both workflows can coexist — they trigger on different paths.

---

## Resource Regeneration Script

File: `scripts/regenerate_brew_resources_planner.sh`

```bash
#!/usr/bin/env bash
# Regenerate Homebrew resource stanzas for planner-auto.
#
# Run when [project.dependencies] change in planner-auto/pyproject.toml.
# Core deps only — TUI extras (textual) not included in formula.
#
# USAGE
#   ./scripts/regenerate_brew_resources_planner.sh
#
# OUTPUT
#   Prints resource stanzas to stdout. Copy into Formula/planner-auto.rb.

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
pip install -q "$PKG_DIR"    # Core deps only, no [tui] extra

echo "==> Running poet planner-auto..." >&2
echo "" >&2
echo "────────────────────────────────────────────────────────────────────────" >&2
echo " RESOURCE STANZAS — paste into Formula/planner-auto.rb" >&2
echo "────────────────────────────────────────────────────────────────────────" >&2
echo "" >&2

poet planner-auto

echo "" >&2
echo "────────────────────────────────────────────────────────────────────────" >&2
echo "==> Done. Copy the stanzas above into Formula/planner-auto.rb," >&2
echo "    replacing all existing resource blocks, then commit and push." >&2
echo "" >&2
echo "    Commit message suggestion:" >&2
echo "      planner-auto ${VERSION} — regenerate resources" >&2
echo "────────────────────────────────────────────────────────────────────────" >&2
```

---

## Installation Flow (User)

```bash
# Tap (one-time, covers both tools)
brew tap ailabph/orchestrator-auto

# Install
brew install planner-auto

# Auth setup
export ANTHROPIC_API_KEY="sk-ant-api03-..."
export OPENAI_API_KEY="sk-..."    # For GPT reviewer

# Verify
planner-auto --help
planner-auto check

# Optional: TUI support
pip install planner-auto[tui]
planner-auto review <session-id> --tui
```

Or one-liner:
```bash
brew install ailabph/orchestrator-auto/planner-auto
```

---

## Release Flow (Developer)

### Normal release (no dep changes)

```
1. Bump version in planner-auto/pyproject.toml
2. Update planner-auto/__init__.py __version__
3. Add CHANGELOG entry
4. git push main
5. Watch Actions → "Release planner-auto" (detect → publish → update-homebrew)
6. Verify: pip install planner-auto==<version>
7. Verify: brew upgrade planner-auto
```

~2 minutes end-to-end.

### Release with dep changes

```
1. Run: ./scripts/regenerate_brew_resources_planner.sh
2. Copy stanzas into Formula/planner-auto.rb in the tap repo
3. Commit + push to tap: "planner-auto <version> — regenerate resources"
4. Then follow normal release steps above
```

### Manual recovery (publish succeeded, tap update failed)

```
1. pip install planner-auto==<version>   # Confirm PyPI is live
2. curl -s https://pypi.org/pypi/planner-auto/<version>/json | \
     python3 -c "import sys,json; d=json.load(sys.stdin); \
       [print(f['digests']['sha256']) for f in d['urls'] if f['packagetype']=='sdist']"
3. Edit Formula/planner-auto.rb: update url + sha256
4. git commit && git push
5. brew upgrade planner-auto
```

---

## Dependencies to Watch

| Dependency | Shared with orchestrator-auto? | Notes |
|-----------|-------------------------------|-------|
| `click` | Yes | Stable, rarely changes |
| `claude-agent-sdk` | Yes | Pinned to `<0.2.0`. When SDK upgrades, BOTH formulas need resource regeneration |
| `anthropic` | Yes | Shared dep. Minor version bumps usually safe |
| `prompt_toolkit` | Yes | Stable |
| `openai` | No (orchestrator doesn't use it) | GPT reviewer. Major version bumps may need resource regeneration |
| `python-dotenv` | No | Stable, minimal transitive deps |

**Shared dep upgrade strategy:** When `claude-agent-sdk` or `anthropic` bumps, regenerate resources for BOTH formulas in the same tap commit.

---

## Differences from the Old Brew Plan

The existing `docs/planner-auto/plans/brew-installer-plan.md` was written at v0.3.0. Key changes:

| Aspect | Old plan (v0.3.0) | This proposal (v0.5.0) |
|--------|-------------------|----------------------|
| Version | 0.3.0 | 0.5.0 |
| Dependencies | Missing `anthropic`, `python-dotenv` | All 6 core deps listed |
| TUI | Not mentioned | Explicitly excluded from formula (optional `[tui]` extra) |
| Release workflow | Used `twine upload` with stored secret | OIDC Trusted Publishing (no stored PyPI secret) |
| Tap update | Used `mislav/bump-homebrew-formula-action` | Inline Python script (matches orchestrator-auto) |
| Theme.tcss | Not mentioned | Explicit `package-data` prerequisite |
| Tag convention | `planner-v0.1.0` | Path-based trigger (no tags needed) |
| Resource strategy | Not specified | Strategy B: top-level url+sha256 auto-updated, resources manually regenerated |

---

## Checklist

### Prerequisites
- [ ] Add `[tool.setuptools.package-data]` for `tui/styles/*.tcss` to `pyproject.toml`
- [ ] Add PyPI metadata (authors, readme, classifiers, urls) to `pyproject.toml`
- [ ] Verify `theme.tcss` included in `python -m build` output (both sdist and wheel)
- [ ] Configure PyPI Trusted Publishing for `planner-auto` project
- [ ] Verify `HOMEBREW_TAP_TOKEN` has write access to tap repo

### First publish
- [ ] Build and publish to PyPI: `cd planner-auto && python -m build && twine upload dist/*`
- [ ] Verify: `pip install planner-auto==0.5.0 && planner-auto --help`
- [ ] Run `scripts/regenerate_brew_resources_planner.sh` → copy stanzas
- [ ] Create `Formula/planner-auto.rb` in tap repo with resource stanzas
- [ ] `brew audit --strict Formula/planner-auto.rb`
- [ ] `brew install --build-from-source ailabph/orchestrator-auto/planner-auto`
- [ ] `brew test planner-auto`
- [ ] Push formula to tap repo

### Automation
- [ ] Create `.github/workflows/release-planner.yml`
- [ ] Create `scripts/regenerate_brew_resources_planner.sh`
- [ ] Update `docs/RELEASE.md` to cover both packages
- [ ] Test full automated flow: bump version → push → verify PyPI + brew

### Verification
- [ ] `brew tap ailabph/orchestrator-auto && brew install planner-auto`
- [ ] `planner-auto --help` shows CLI help
- [ ] `planner-auto check` validates environment
- [ ] `pip install planner-auto[tui] && planner-auto review <id> --tui` works alongside brew install

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| theme.tcss missing from sdist | High (if P1 skipped) | High — TUI crashes | P1 is a hard prerequisite; build step verifies |
| PyPI name collision | Low | High | `planner-auto` is not currently registered |
| Tap token scope insufficient | Low | Medium | Verify before first publish |
| Resource block count too high | Low | Low | Core-only formula has ~25 resources (manageable) |
| Dual workflow conflicts | Low | Low | Path-based triggers ensure independence |
| claude-agent-sdk upgrade breaks both formulas | Medium | Medium | Regenerate both formulas in same tap commit |

---

## Timeline

**The "Timing" section in the old plan said "wait for Plan 2."** Plan 2 shipped in v0.2.0. The reviewer loop, direct API backend, and TUI are all complete. There is no reason to wait further — v0.5.0 is the right version to publish.
