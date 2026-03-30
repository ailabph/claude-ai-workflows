#!/usr/bin/env bash
# Regenerate Homebrew resource stanzas for planner-auto.
#
# PURPOSE
#   The Homebrew formula (ailabph/homebrew-orchestrator-auto) pins all Python
#   deps as resource blocks with exact versions and SHA256 hashes. The automated
#   release pipeline (release-planner.yml) updates the top-level url + sha256
#   only — it does NOT regenerate these resource blocks.
#
#   Run this script manually when any of the following have changed since the
#   last resource regeneration:
#     • planner-auto/pyproject.toml [project.dependencies]
#     • planner-auto/pyproject.toml [project.optional-dependencies]
#       (tui extra — includes textual and its transitive deps)
#     • A transitive dep has released a breaking update that the formula
#       must track
#
# USAGE
#   ./scripts/regenerate_brew_resources_planner.sh        # installs from local source
#
# OUTPUT
#   Prints all resource stanzas to stdout. Redirect or copy-paste them into
#   Formula/planner-auto.rb in ailabph/homebrew-orchestrator-auto,
#   replacing the existing resource blocks, then commit and push.
#
# WORKFLOW (when deps changed)
#   1. Bump version in planner-auto/pyproject.toml
#   2. Run this script → copy resource stanzas
#   3. In ailabph/homebrew-orchestrator-auto:
#        edit Formula/planner-auto.rb → replace resource blocks
#        git commit -m "planner-auto <version> — regenerate resources"
#        git push
#   4. Push version bump to main in this repo
#      (the automated pipeline handles url + sha256 from there)
#
# REQUIREMENTS
#   • Python 3.10+ on PATH
#   • Internet access (to resolve transitive deps from PyPI)
#   • No need to publish to PyPI first — installs from local source

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG_DIR="$REPO_ROOT/planner-auto"
PYPROJECT="$PKG_DIR/pyproject.toml"

# ── Resolve version (display only — not used for install) ─────────────────────

VERSION=$(grep '^version = ' "$PYPROJECT" | sed 's/^version = "\(.*\)"$/\1/')
if [[ -z "$VERSION" ]]; then
    echo "Error: could not parse version from $PYPROJECT" >&2
    exit 1
fi
echo "==> Package version: $VERSION" >&2

# ── Create isolated venv ───────────────────────────────────────────────────────

VENV_DIR="$(mktemp -d)/poet-venv"
echo "==> Creating isolated venv at $VENV_DIR..." >&2
python3 -m venv "$VENV_DIR"
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# Install from local source so this works before publishing to PyPI.
# Transitive deps are still resolved from PyPI — only the top-level package
# itself comes from the local checkout.
echo "==> Installing homebrew-pypi-poet and planner-auto[tui] from local source..." >&2
pip install -q --upgrade pip
pip install -q homebrew-pypi-poet
pip install -q "$PKG_DIR[tui]"

# ── Run poet ───────────────────────────────────────────────────────────────────

echo "==> Running poet planner-auto..." >&2
echo "" >&2
echo "──────────────────────────────────────────────────────────────────────────" >&2
echo " RESOURCE STANZAS — paste into Formula/planner-auto.rb" >&2
echo "──────────────────────────────────────────────────────────────────────────" >&2
echo "" >&2

# poet writes stanzas to stdout; all our progress messages go to stderr
poet planner-auto

echo "" >&2
echo "──────────────────────────────────────────────────────────────────────────" >&2
echo "==> Done. Copy the stanzas above into Formula/planner-auto.rb," >&2
echo "    replacing all existing resource blocks, then commit and push." >&2
echo "" >&2
echo "    Commit message suggestion:" >&2
echo "      planner-auto ${VERSION} — regenerate resources" >&2
echo "──────────────────────────────────────────────────────────────────────────" >&2
