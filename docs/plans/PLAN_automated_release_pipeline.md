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
        ├─ 4. Publish to PyPI (via OIDC Trusted Publishing)
        ├─ 5. Fetch new SHA256 from PyPI JSON API
        └─ 6. Push formula update to homebrew-orchestrator-auto
                    │
                    ▼
        brew upgrade orchestrator-auto  ✓
```

---

## Milestones

### Milestone 1: Secrets & Trusted Publishing Setup (manual, one-time)

#### PyPI — Trusted Publishing (primary)

PyPI Trusted Publishing uses GitHub OIDC — no long-lived token to store or rotate. The workflow authenticates directly via its GitHub identity.

**Setup in PyPI:**
- pypi.org → `orchestrator-auto` project → Publishing → Add a trusted publisher
- Publisher: GitHub Actions
- Owner: `ailabph`
- Repository: `claude-ai-workflows`
- Workflow filename: `release.yml`
- Environment name: `pypi` (optional but recommended for protection rules)

No secret is stored in GitHub for publishing. The workflow uses `id-token: write` permission and the `pypa/gh-action-pypi-publish` action.

**Fallback — `PYPI_TOKEN` secret (emergency manual use only):**
- Keep `orchestrator-auto/scripts/publish_pypi.sh` available for out-of-band emergency publishes
- Store `PYPI_TOKEN` in GitHub secrets if needed for manual runs, but it is not used by the automated workflow

#### Homebrew tap — `HOMEBREW_TAP_TOKEN`

A **fine-grained GitHub PAT** (not a classic PAT) scoped to the tap repo only:

- GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens**
- Resource owner: `ailabph`
- Repository access: **Only `ailabph/homebrew-orchestrator-auto`**
- Permissions: **Contents → Read and Write** (nothing else)
- Store as secret `HOMEBREW_TAP_TOKEN` in `ailabph/claude-ai-workflows` → Settings → Secrets → Actions

This milestone has no code — just the two setups above, confirmed done before proceeding.

---

### Milestone 2: Release workflow (`release.yml`)

Create `.github/workflows/release.yml` in this repo.

**Trigger:** Push to `main`, path filter `orchestrator-auto/pyproject.toml`.

**Permissions (workflow-level):**
```yaml
permissions:
  contents: read
  id-token: write   # required for OIDC Trusted Publishing
```

**Jobs:**

#### Job 1: `detect`
- Reads version from `orchestrator-auto/pyproject.toml`
- Checks PyPI JSON API: `https://pypi.org/pypi/orchestrator-auto/<version>/json`
- Sets output `should_publish=true` if 404 (version is new), `false` if already published
- This makes the workflow idempotent — safe to re-run without double-publishing

#### Job 2: `publish` (needs: detect, if: should_publish == 'true')
- Checkout repo
- Set up Python 3.13
- Build in isolated venv (mirrors existing `publish_pypi.sh` logic)
- Verify `theme.tcss` is present in both wheel and sdist (existing integrity check — fail hard if missing)
- Publish via `pypa/gh-action-pypi-publish` using OIDC (no token needed)
- Poll PyPI JSON API (up to 90s, 10s intervals) until new version appears — fail loudly if timeout exceeded

#### Job 3: `update-homebrew` (needs: publish)
- Fetch SHA256 of new sdist from PyPI JSON API
- Clone `ailabph/homebrew-orchestrator-auto` using `HOMEBREW_TAP_TOKEN`
- Update `Formula/orchestrator-auto.rb`:
  - `url` line → new PyPI sdist URL
  - `sha256` line → new SHA256
- Commit with message: `orchestrator-auto <version>`
- Push to `main` of `homebrew-orchestrator-auto`
- **On failure:** workflow exits non-zero with a clear message:
  ```
  PyPI publish succeeded (orchestrator-auto <version> is live).
  Homebrew tap update FAILED. Run the manual recovery steps in docs/RELEASE.md.
  ```

**No PR — direct push to tap `main`.** Formula updates are mechanical, not code review candidates.

---

### Milestone 3: Formula resource pinning strategy

The current formula has 45 `resource` blocks (all Python deps pinned to exact versions + SHA256). These do not auto-update — they stay pinned until manually regenerated.

**Two strategies:**

| Strategy | Pros | Cons |
|----------|------|------|
| **A) Regenerate resources on every release** | Always matches exact dep tree; safest for brew audit | Adds significant CI complexity (`homebrew-pypi-poet` + `pip download` in runner) |
| **B) Update top-level url + sha256 only; leave resources pinned** | Simple; sufficient for dependency-static releases | Breaks if dep specs, extras, or transitive pins change between formula refreshes |

**Decision: Strategy B, scoped correctly.**

Strategy B is safe only for **dependency-static releases** — releases where nothing in the following has changed:
- `orchestrator-auto/pyproject.toml` `[project.dependencies]`
- `orchestrator-auto/pyproject.toml` `[project.optional-dependencies]` (tui, telegram extras)
- No transitive dep has released a breaking update since the last resource regeneration

For all other releases (dep additions, spec changes, extras changes, major/minor bumps), resources must be regenerated manually before or immediately after the automated workflow runs.

**Release author checklist item (added to `docs/RELEASE.md`):**
> Before pushing: did any dep or extra change? If yes → run `scripts/regenerate_brew_resources.sh` first, commit the updated formula to `homebrew-orchestrator-auto`, then push the version bump.

Add `scripts/regenerate_brew_resources.sh` — a documented local helper (not run in CI) that:
1. Creates a fresh venv
2. Installs `homebrew-pypi-poet` + `orchestrator-auto[tui]=={version}` from PyPI
3. Runs `poet orchestrator-auto` to regenerate resource stanzas
4. Prints the stanzas for manual insertion into the formula

---

### Milestone 4: Release checklist, failure recovery, scripts cleanup

#### `docs/RELEASE.md`

Full step-by-step release process:

```
Normal release (dependency-static):
  1. Confirm no dep/extras changes since last resource regeneration
  2. Bump version in orchestrator-auto/pyproject.toml
  3. Add CHANGELOG entry
  4. git push main
  5. Watch Actions tab — publish + homebrew jobs (~2 min)
  6. Verify: pip install orchestrator-auto==<version>
  7. Verify: brew upgrade orchestrator-auto

Release with dep/extras changes:
  1. Run scripts/regenerate_brew_resources.sh
  2. Commit updated Formula/orchestrator-auto.rb to homebrew-orchestrator-auto
  3. Then follow normal release steps above
```

**Manual recovery — "PyPI published, tap update failed":**
```
1. Confirm the new version is live: pip install orchestrator-auto==<version>
2. Get the sdist SHA256:
   curl -s https://pypi.org/pypi/orchestrator-auto/<version>/json \
     | python3 -c "import sys,json; d=json.load(sys.stdin); \
       [print(f['digests']['sha256']) for f in d['urls'] if f['packagetype']=='sdist']"
3. In ailabph/homebrew-orchestrator-auto, edit Formula/orchestrator-auto.rb:
   - Update url to new sdist URL
   - Update sha256 to value from step 2
4. git commit -m "orchestrator-auto <version>" && git push
5. Verify: brew upgrade orchestrator-auto
```

#### Other changes
- `orchestrator-auto/scripts/publish_pypi.sh` — add notice at top: automated via GitHub Actions (OIDC); this script is for emergency out-of-band use only
- `docs/brew-tap-setup-progress.md` — mark as superseded by this plan and `docs/RELEASE.md`

---

## Files to create / modify

| File | Action |
|------|--------|
| `.github/workflows/release.yml` | **Create** — core automation |
| `docs/RELEASE.md` | **Create** — release checklist + recovery |
| `scripts/regenerate_brew_resources.sh` | **Create** — manual dep refresh helper |
| `orchestrator-auto/scripts/publish_pypi.sh` | **Modify** — add emergency-use notice |
| `docs/brew-tap-setup-progress.md` | **Modify** — mark superseded |

External repo (updated by the workflow automatically, or manually during recovery):
- `ailabph/homebrew-orchestrator-auto` → `Formula/orchestrator-auto.rb` (url + sha256)

---

## What this does NOT automate

- **Resource block regeneration** — kept manual; must be done before pushing when deps change
- **GitHub Release / git tag** — out of scope; `pyproject.toml` version is the source of truth
- **Pre-release testing** — workflow assumes tests pass before push to `main`

---

## Implementation order

1. Milestone 1 — PyPI Trusted Publishing setup + `HOMEBREW_TAP_TOKEN` secret (manual, ~10 min)
2. Milestones 2–4 — can be implemented in a single pass once secrets are confirmed
