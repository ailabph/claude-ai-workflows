# Release Guide — orchestrator-auto

This document covers the full release process for `orchestrator-auto`: pre-release checks, pushing a version bump, monitoring the automated pipeline, and recovering from failures.

---

## How the pipeline works

```
git push main (with version bump in pyproject.toml)
        │
        ▼
GitHub Actions: .github/workflows/release.yml
        │
        ├─ 1. detect   — reads version, checks PyPI (idempotent guard)
        ├─ 2. publish  — builds sdist + wheel, verifies theme.tcss,
        │               publishes via OIDC Trusted Publishing, polls until live
        └─ 3. update-homebrew — fetches new SHA256, updates
                               Formula/orchestrator-auto.rb url + sha256,
                               pushes directly to ailabph/homebrew-orchestrator-auto
                                   │
                                   ▼
                       brew upgrade orchestrator-auto  ✓
```

The workflow is **idempotent** — if the version already exists on PyPI the `detect` job sets `should_publish=false` and both `publish` and `update-homebrew` are skipped cleanly.

---

## Pre-release checklist

Before bumping the version, answer this question:

> **Did any dependency or extra change since the last resource regeneration?**

Check for changes to:
- `orchestrator-auto/pyproject.toml` → `[project.dependencies]`
- `orchestrator-auto/pyproject.toml` → `[project.optional-dependencies]` (tui, telegram extras)
- Any transitive dep that has released a breaking update since the formula's resource blocks were last regenerated

**If yes** → follow the [Release with dep/extras changes](#release-with-depextras-changes) path.
**If no** → follow the [Normal release (dependency-static)](#normal-release-dependency-static) path.

---

## Normal release (dependency-static)

Use this path when no deps or extras have changed since the last resource regeneration.

1. Confirm no dep/extras changes since last resource regeneration (see pre-release checklist above)
2. Bump version in `orchestrator-auto/pyproject.toml`
3. Add CHANGELOG entry
4. `git push main`
5. Watch the Actions tab — `publish` + `update-homebrew` jobs complete in ~2 min
6. Verify: `pip install orchestrator-auto==<version>`
7. Verify: `brew upgrade orchestrator-auto`

---

## Release with dep/extras changes

Use this path when `[project.dependencies]`, `[project.optional-dependencies]`, or any transitive dep has changed since the formula's resource blocks were last regenerated.

1. Run `scripts/regenerate_brew_resources.sh` (reads version from `pyproject.toml`, or pass an explicit version)
2. Copy the printed resource stanzas into `Formula/orchestrator-auto.rb` in `ailabph/homebrew-orchestrator-auto`, replacing all existing resource blocks
3. Commit and push to the tap:
   ```bash
   git commit -m "orchestrator-auto <version> — regenerate resources"
   git push
   ```
4. Then follow the normal release steps above (bump version → push to main)

> The automated pipeline updates only the top-level `url` + `sha256`. Resource blocks are intentionally kept static between manual regenerations — this is Strategy B, which is safe for dependency-static releases and requires the steps above for everything else.

---

## Monitoring the workflow

After pushing to `main`, watch: **ailabph/claude-ai-workflows → Actions → Release orchestrator-auto**

| Job | What to expect |
|-----|----------------|
| `detect` | Reads version, HTTP 404 from PyPI → `should_publish=true` |
| `publish` | Builds, verifies `theme.tcss`, uploads via OIDC, polls until live |
| `update-homebrew` | Clones tap, updates `url` + `sha256`, commits, pushes |

Typical total duration: ~2 minutes.

**If `detect` fails with "Unexpected HTTP …"** — this is a transient PyPI API error. Re-run the workflow from the Actions tab once PyPI recovers. No publish was attempted.

---

## Manual recovery — "PyPI published, tap update failed"

If the `update-homebrew` job fails after `publish` succeeds, the workflow exits with:

```
PyPI publish succeeded (orchestrator-auto <version> is live).
Homebrew tap update FAILED. Run the manual recovery steps in docs/RELEASE.md.
```

Recover manually:

1. Confirm the new version is live:
   ```bash
   pip install orchestrator-auto==<version>
   ```

2. Get the sdist SHA256 from the PyPI JSON API:
   ```bash
   curl -s https://pypi.org/pypi/orchestrator-auto/<version>/json \
     | python3 -c "import sys,json; d=json.load(sys.stdin); \
       [print(f['digests']['sha256']) for f in d['urls'] if f['packagetype']=='sdist']"
   ```

3. In `ailabph/homebrew-orchestrator-auto`, edit `Formula/orchestrator-auto.rb`:
   - Update the `url` line to the new sdist URL (`https://files.pythonhosted.org/...`)
   - Update the top-level `sha256` line to the value from step 2

4. Commit and push:
   ```bash
   git commit -m "orchestrator-auto <version>" && git push
   ```

5. Verify:
   ```bash
   brew upgrade orchestrator-auto
   ```

---

## Reference

| Resource | Location |
|----------|----------|
| Release workflow | `.github/workflows/release.yml` |
| Resource regeneration script | `scripts/regenerate_brew_resources.sh` |
| Emergency manual publish script | `orchestrator-auto/scripts/publish_pypi.sh` |
| Homebrew tap formula | `ailabph/homebrew-orchestrator-auto` → `Formula/orchestrator-auto.rb` |
| PyPI package | https://pypi.org/project/orchestrator-auto/ |
