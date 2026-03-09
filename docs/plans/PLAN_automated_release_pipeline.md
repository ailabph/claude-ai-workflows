# Plan: Automated Release Pipeline (PyPI + Homebrew)

**Goal:** Push a version bump to `main` → PyPI publishes automatically → Homebrew formula updates automatically → `brew install` / `brew upgrade` reflects the new version.

---

## Current State

| Component | Location | How updated |
|-----------|----------|-------------|
| Source code | `ailabph/claude-ai-workflows` (this repo) | Git push |
| PyPI package | `orchestrator-auto` on pypi.org | Manual: `scripts/publish_pypi.sh` |
| Brew formula | `ailabph/homebrew-orchestrator-auto` | Manual: edit `Formula/orchestrator-auto.rb` |

All three are disconnected. Brew stays pinned to whatever version was last manually set.

---

## Target State

```
git push main (with version bump in pyproject.toml)
        │
        ▼
GitHub Actions: .github/workflows/release.yml
        │
        ├─ 1. Detect version change
        ├─ 2. Build sdist + wheel
        ├─ 3. Verify theme.tcss is packaged (existing check)
        ├─ 4. Publish to PyPI
        ├─ 5. Fetch new SHA256 from PyPI JSON API
        └─ 6. Push formula update to homebrew-orchestrator-auto
                    │
                    ▼
        brew upgrade orchestrator-auto  ✓
```

---

## Milestones

### Milestone 1: GitHub Secrets Setup (manual, one-time)

Two secrets must be added to `ailabph/claude-ai-workflows` → Settings → Secrets and variables → Actions:

| Secret name | Value | Purpose |
|-------------|-------|---------|
| `PYPI_TOKEN` | PyPI API token (`pypi-...`) | Publish to PyPI |
| `HOMEBREW_TAP_TOKEN` | GitHub PAT with `repo` scope on `ailabph/homebrew-orchestrator-auto` | Push formula update |

**How to create `HOMEBREW_TAP_TOKEN`:**
- GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
- Repository access: `ailabph/homebrew-orchestrator-auto` only
- Permissions: Contents → Read and Write

This milestone has no code — just docs confirming what secrets are needed.

---

### Milestone 2: Release workflow (`release.yml`)

Create `.github/workflows/release.yml` in this repo.

**Trigger:** Push to `main` — but only runs the publish job when `orchestrator-auto/pyproject.toml` is among the changed files AND the version in that file does not already exist on PyPI (idempotent guard).

**Jobs:**

#### Job 1: `detect`
- Reads version from `orchestrator-auto/pyproject.toml`
- Checks PyPI JSON API: `https://pypi.org/pypi/orchestrator-auto/<version>/json`
- Sets output `should_publish=true` if version is new, `false` if already published
- This makes the workflow safe to re-run without double-publishing

#### Job 2: `publish` (needs: detect, if: should_publish)
- Checkout repo
- Set up Python 3.13
- Build in isolated venv (mirrors existing `publish_pypi.sh` logic)
- Verify `theme.tcss` is in wheel (existing integrity check)
- Publish via `twine` using `PYPI_TOKEN` secret
- Wait up to 60s for PyPI to make the new version available (poll JSON API)

#### Job 3: `update-homebrew` (needs: publish)
- Fetch SHA256 of new sdist from PyPI JSON API
- Clone `ailabph/homebrew-orchestrator-auto` using `HOMEBREW_TAP_TOKEN`
- Update `Formula/orchestrator-auto.rb`:
  - `url` line → new PyPI sdist URL
  - `sha256` line → new SHA256
  - `version` comment header (if present)
- Commit with message: `orchestrator-auto <version>`
- Push to `main` of `homebrew-orchestrator-auto`

**No PR — direct push to tap `main`.** Homebrew taps update from their `main` branch, so a PR would add unnecessary friction. The formula change is mechanical (url + sha256 only), not a code review candidate.

---

### Milestone 3: Formula resource pinning strategy

The current formula has 45 `resource` blocks (all Python deps pinned to exact versions + SHA256). These **do not** auto-update — they stay pinned until manually regenerated.

**Decision needed:** Two strategies:

| Strategy | Pros | Cons |
|----------|------|------|
| **A) Regenerate resources on every release** | Always matches exact dep tree; safest for brew audit | Adds complexity to `update-homebrew` job (needs `homebrew-pypi-poet` in CI) |
| **B) Only update top-level url + sha256, leave resources pinned** | Simple; works as long as dep versions haven't changed | Will break if a dep releases an incompatible update between formula refreshes |

**Recommendation: Strategy B for now, with a manual refresh step documented.**

Since orchestrator-auto has a tight dep spec (`claude-agent-sdk>=0.1.46,<0.2.0`, etc.), pinned resources will stay valid across patch releases. Add a note to the release checklist: regenerate resources when bumping minor/major versions.

Add `scripts/regenerate_brew_resources.sh` (documented helper, not run in CI) for when a manual resource refresh is needed.

---

### Milestone 4: Release checklist doc + scripts cleanup

1. **`docs/RELEASE.md`** — step-by-step release process:
   ```
   1. Bump version in orchestrator-auto/pyproject.toml
   2. Add CHANGELOG entry
   3. git push main
   4. Watch Actions tab — publish + homebrew jobs complete in ~2 min
   5. Verify: pip install orchestrator-auto==<version>
   6. Verify: brew upgrade orchestrator-auto
   ```
   Include a note on when to manually regenerate brew resources (minor/major bumps).

2. **`scripts/publish_pypi.sh`** — add deprecation notice at top: automated via GitHub Actions; this script is now for emergency manual publishes only.

3. **`docs/brew-tap-setup-progress.md`** — mark as superseded by this plan.

---

## Files to create / modify

| File | Action |
|------|--------|
| `.github/workflows/release.yml` | **Create** — core automation |
| `docs/RELEASE.md` | **Create** — release checklist |
| `scripts/regenerate_brew_resources.sh` | **Create** — manual helper |
| `orchestrator-auto/scripts/publish_pypi.sh` | **Modify** — add deprecation notice |
| `docs/brew-tap-setup-progress.md` | **Modify** — mark superseded |

External repo change (done by the workflow, not in this repo):
- `ailabph/homebrew-orchestrator-auto` → `Formula/orchestrator-auto.rb` (url + sha256 + version)

---

## What this does NOT automate

- **Resource block regeneration** — kept manual (see Milestone 3)
- **GitHub Release / git tag creation** — out of scope; version in `pyproject.toml` is the source of truth
- **Pre-release testing** — the workflow assumes tests pass before the push to `main`; add a separate `test.yml` workflow if CI testing is desired

---

## Implementation order

1. Milestone 1 — secrets (manual, ~5 min)
2. Milestone 2 — `release.yml` (core work)
3. Milestone 3 — decide resource strategy, add helper script
4. Milestone 4 — docs + cleanup

Milestones 2–4 can be implemented in a single pass.
