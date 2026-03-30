# Homebrew Installer - Implementation Plan

## Overview

Publish planner-auto v0.5.0 to PyPI and Homebrew. Formula includes textual (TUI works out of the box). Automated release pipeline mirrors orchestrator-auto's proven 3-job workflow. First release is a manual bootstrap; all subsequent releases are fully automated.

**Reference:** `docs/planner-auto/plans/proposal-brew-installer.md` (v2)

**Key decisions:**
- Formula installs `planner-auto[tui]` — textual included in resource blocks
- Same tap as orchestrator-auto (`ailabph/homebrew-orchestrator-auto`)
- OIDC Trusted Publishing (no stored PyPI secrets)
- Strategy B: automated url+sha256 updates, manual resource regeneration when deps change
- Path-based workflow trigger (`planner-auto/pyproject.toml`)

---

## Milestone 1: pyproject.toml Prerequisites + Build Verification

Fix pyproject.toml so the package builds correctly with theme.tcss included and PyPI accepts the metadata. Verify sdist and wheel integrity before publishing.

### Tasks
- [ ] `planner-auto/pyproject.toml`: Add `[tool.setuptools.package-data]` section to include TUI theme file:
  ```toml
  [tool.setuptools.package-data]
  planner_auto = ["tui/styles/*.tcss"]
  ```
- [ ] `planner-auto/pyproject.toml`: Add `authors` field under `[project]`:
  ```toml
  authors = [
      {name = "Danny Almaden", email = "dan@ailab.ph"},
  ]
  ```
- [ ] `planner-auto/pyproject.toml`: Add `readme = "README.md"` under `[project]`
- [ ] `planner-auto/pyproject.toml`: Add `classifiers` list under `[project]`: Development Status Beta, Intended Audience Developers, License MIT, Programming Language Python 3.10/3.11/3.12/3.13
- [ ] `planner-auto/pyproject.toml`: Add `keywords` list under `[project]`: `["planning", "claude", "ai", "orchestration", "milestone", "gpt", "review"]`
- [ ] `planner-auto/pyproject.toml`: Add `[project.urls]` section with Homepage, Repository, and Changelog URLs pointing to `github.com/ailabph/claude-ai-workflows`
- [ ] Build sdist + wheel locally: `cd planner-auto && python -m build`
- [ ] Verify `theme.tcss` is in the wheel: `unzip -l dist/*.whl | grep theme.tcss` — must show `planner_auto/tui/styles/theme.tcss`
- [ ] Verify `theme.tcss` is in the sdist: `tar -tzf dist/*.tar.gz | grep theme.tcss` — must show the file
- [ ] Verify wheel installs cleanly in a fresh venv: `python -m venv /tmp/pa-test && /tmp/pa-test/bin/pip install dist/*.whl && /tmp/pa-test/bin/planner-auto --help`
- [ ] Verify `[tui]` extra installs cleanly: `/tmp/pa-test/bin/pip install dist/*.whl"[tui]"` — textual installed, no import errors

### Deliverables
- [ ] `python -m build` produces both `planner_auto-0.5.0.tar.gz` and `planner_auto-0.5.0-py3-none-any.whl`
- [ ] `theme.tcss` present in both sdist and wheel
- [ ] `planner-auto --help` works from a fresh venv install
- [ ] `planner-auto[tui]` installs textual without errors
- [ ] All 464 existing tests still pass

---

## Milestone 2: First PyPI Publish + Resource Generation Script

Publish planner-auto v0.5.0 to PyPI (manual one-time bootstrap). Create the resource regeneration script for Homebrew formula maintenance. Configure Trusted Publishing for future automated releases.

### Tasks
- [ ] Upload to PyPI using twine: `cd planner-auto && twine upload dist/*` (interactive login or stored token for first upload only)
- [ ] Verify PyPI publish: `pip install planner-auto==0.5.0 && planner-auto --help` in a clean venv (not the repo venv)
- [ ] Verify PyPI TUI extra: `pip install "planner-auto[tui]==0.5.0"` in a clean venv — `planner-auto review --help` shows `--tui` flag
- [ ] Configure Trusted Publisher on PyPI: go to `pypi.org/manage/project/planner-auto/settings/publishing/`, add GitHub Actions publisher with repository `ailabph/claude-ai-workflows`, workflow name `release-planner.yml`, environment name `pypi`
- [ ] `scripts/regenerate_brew_resources_planner.sh` (new file): Create resource regeneration script that:
  - Creates isolated venv
  - Installs `homebrew-pypi-poet` and `planner-auto[tui]` from local source (includes textual deps)
  - Runs `poet planner-auto` and prints stanzas to stdout
  - Progress messages to stderr, stanzas to stdout (same pattern as orchestrator-auto script)
  - Includes usage header, workflow documentation, and commit message suggestion
- [ ] Make script executable: `chmod +x scripts/regenerate_brew_resources_planner.sh`
- [ ] Run the script and capture output: `./scripts/regenerate_brew_resources_planner.sh > /tmp/planner-resources.rb`
- [ ] Verify resource stanzas include textual and its transitive deps (rich, markdown-it-py, linkify-it-py, etc.)
- [ ] Count resource blocks — expect ~35-40 stanzas

### Deliverables
- [ ] `pip install planner-auto==0.5.0` works from PyPI
- [ ] `pip install "planner-auto[tui]==0.5.0"` installs textual from PyPI
- [ ] Trusted Publisher configured on PyPI for `release-planner.yml`
- [ ] `scripts/regenerate_brew_resources_planner.sh` exists and produces valid resource stanzas
- [ ] Resource stanzas include textual and its transitive deps

---

## Milestone 3: Homebrew Formula Creation

Create the formula in the existing tap repo, audit it, test installation from source, and push. After this milestone, `brew install planner-auto` works.

### Tasks
- [ ] Clone the tap repo: `git clone https://github.com/ailabph/homebrew-orchestrator-auto.git`
- [ ] Get the sdist SHA256 from PyPI:
  ```bash
  curl -s https://pypi.org/pypi/planner-auto/0.5.0/json | \
    python3 -c "import sys,json; d=json.load(sys.stdin); \
      [print(f['digests']['sha256']) for f in d['urls'] if f['packagetype']=='sdist']"
  ```
- [ ] Get the sdist URL from PyPI:
  ```bash
  curl -s https://pypi.org/pypi/planner-auto/0.5.0/json | \
    python3 -c "import sys,json; d=json.load(sys.stdin); \
      [print(f['url']) for f in d['urls'] if f['packagetype']=='sdist']"
  ```
- [ ] Create `Formula/planner-auto.rb` in the tap repo using the template from the proposal: class `PlannerAuto < Formula` with `include Language::Python::Virtualenv`, `depends_on "python@3.13"`, resource stanzas from M2, `virtualenv_install_with_resources` install block, test block asserting "Usage:" in `--help` output
- [ ] Paste resource stanzas from M2 output into the formula, replacing the placeholder comment
- [ ] Set the correct `url` (PyPI sdist URL) and `sha256` (from PyPI JSON API) in the formula
- [ ] Run Homebrew audit: `brew audit --strict Formula/planner-auto.rb` — fix any warnings
- [ ] Install from source: `brew install --build-from-source ailabph/orchestrator-auto/planner-auto`
- [ ] Run brew test: `brew test planner-auto`
- [ ] Verify CLI works: `planner-auto --help`
- [ ] Verify check command: `planner-auto check`
- [ ] Verify TUI flag exists: `planner-auto review --help` — output includes `--tui`
- [ ] Commit and push formula to tap: `git commit -m "planner-auto 0.5.0 — initial formula" && git push`
- [ ] Verify clean install from tap: `brew untap ailabph/orchestrator-auto && brew tap ailabph/orchestrator-auto && brew install planner-auto`

### Deliverables
- [ ] `Formula/planner-auto.rb` exists in `ailabph/homebrew-orchestrator-auto` tap
- [ ] `brew audit --strict` passes with no errors
- [ ] `brew install planner-auto` succeeds on a clean tap
- [ ] `brew test planner-auto` passes
- [ ] `planner-auto --help` works from the brewed binary
- [ ] `planner-auto review --help` shows the `--tui` flag (textual is installed in brew's virtualenv)

---

## Milestone 4: Automated Release Pipeline + Documentation

Create the GitHub Actions workflow for automated releases and update the release guide to cover both packages. Test the full automated flow with a version bump.

### Tasks
- [ ] `.github/workflows/release-planner.yml` (new file): Create 3-job workflow mirroring `release.yml`:
  - **Trigger:** push to `main` when `planner-auto/pyproject.toml` changes
  - **Permissions:** `contents: read`, `id-token: write` (OIDC)
  - **Job 1 (detect):** Read version from `planner-auto/pyproject.toml`, check PyPI JSON API (`https://pypi.org/pypi/planner-auto/${VERSION}/json`), set `should_publish=true` on 404
  - **Job 2 (publish):** Build sdist + wheel from `planner-auto/` working directory, verify `theme.tcss` in both artifacts (same check as orchestrator-auto), publish via `pypa/gh-action-pypi-publish` with OIDC, poll PyPI for 90s until version is live
  - **Job 3 (update-homebrew):** Fetch sdist SHA256 from PyPI JSON API, clone tap repo using `HOMEBREW_TAP_TOKEN`, update `Formula/planner-auto.rb` url + sha256 (top-level 2-space indent only, `count=1`), commit and push, report tap failure clearly if any step fails
- [ ] `.github/workflows/release-planner.yml`: Ensure Job 2 uses `environment: pypi` for OIDC Trusted Publishing
- [ ] `.github/workflows/release-planner.yml`: Ensure Job 3 updates `Formula/planner-auto.rb` (not `orchestrator-auto.rb`) — double-check the Python regex targets the correct formula file
- [ ] `docs/RELEASE.md`: Update to cover both packages — add a "planner-auto" section with the same structure (normal release, dep-change release, manual recovery), link to `release-planner.yml` and `regenerate_brew_resources_planner.sh`
- [ ] `docs/RELEASE.md`: Add a "Shared dependency upgrades" section explaining that `claude-agent-sdk`, `anthropic`, and `textual` bumps require resource regeneration for BOTH formulas in the same tap commit
- [ ] Verify `HOMEBREW_TAP_TOKEN` secret exists in the repo and has write access to the tap repo (it should — same secret used by orchestrator-auto workflow)
- [ ] Test the automated pipeline: bump planner-auto version to 0.5.1 in pyproject.toml + `__init__.py`, add a minimal CHANGELOG entry, push to main, watch the Actions tab
- [ ] Verify Job 1 (detect) correctly identifies 0.5.1 as new
- [ ] Verify Job 2 (publish) builds, verifies theme.tcss, publishes to PyPI, polls successfully
- [ ] Verify Job 3 (update-homebrew) updates `Formula/planner-auto.rb` url + sha256 in the tap
- [ ] Verify end-to-end: `pip install planner-auto==0.5.1` works, `brew upgrade planner-auto` picks up 0.5.1

### Deliverables
- [ ] `.github/workflows/release-planner.yml` exists and is syntactically valid
- [ ] Automated pipeline runs successfully on version 0.5.1: detect → publish → update-homebrew
- [ ] `pip install planner-auto==0.5.1` works after automated publish
- [ ] `brew upgrade planner-auto` installs 0.5.1 after automated tap update
- [ ] `docs/RELEASE.md` covers both orchestrator-auto and planner-auto release flows
- [ ] Both workflows (`release.yml` and `release-planner.yml`) can coexist — pushing `planner-auto/pyproject.toml` only triggers planner workflow, not orchestrator workflow
