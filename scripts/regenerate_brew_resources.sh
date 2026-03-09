#!/usr/bin/env bash
# Regenerate Homebrew resource stanzas for orchestrator-auto.
#
# PURPOSE
#   The Homebrew formula (ailabph/homebrew-orchestrator-auto) pins all Python
#   deps as resource blocks with exact versions and SHA256 hashes. The automated
#   release pipeline (release.yml) updates the top-level url + sha256 only —
#   it does NOT regenerate these resource blocks.
#
#   Run this script manually when any of the following have changed since the
#   last resource regeneration:
#     • orchestrator-auto/pyproject.toml [project.dependencies]
#     • orchestrator-auto/pyproject.toml [project.optional-dependencies]
#       (tui, telegram extras)
#     • A transitive dep has released a breaking update that the formula
#       must track
#
# USAGE
#   ./scripts/regenerate_brew_resources.sh              # uses version from pyproject.toml
#   ./scripts/regenerate_brew_resources.sh 1.9.2        # explicit version
#
# OUTPUT
#   Prints all resource stanzas to stdout. Redirect or copy-paste them into
#   Formula/orchestrator-auto.rb in ailabph/homebrew-orchestrator-auto,
#   replacing the existing resource blocks, then commit and push.
#
# WORKFLOW (when deps changed)
#   1. Run this script → copy resource stanzas
#   2. In ailabph/homebrew-orchestrator-auto:
#        edit Formula/orchestrator-auto.rb → replace resource blocks
#        git commit -m "orchestrator-auto <version> — regenerate resources"
#        git push
#   3. Then bump version in orchestrator-auto/pyproject.toml and push to main
#      (the automated pipeline handles url + sha256 from there)
#
# REQUIREMENTS
#   • Python 3.10+ on PATH
#   • Internet access (installs packages from PyPI)
#   • homebrew-pypi-poet is installed in the temp venv (no system dep needed)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYPROJECT="$REPO_ROOT/orchestrator-auto/pyproject.toml"

# ── Resolve version ────────────────────────────────────────────────────────────

if [[ "${1:-}" != "" ]]; then
    VERSION="$1"
    echo "==> Using explicit version: $VERSION" >&2
else
    VERSION=$(grep '^version = ' "$PYPROJECT" | sed 's/^version = "\(.*\)"$/\1/')
    if [[ -z "$VERSION" ]]; then
        echo "Error: could not parse version from $PYPROJECT" >&2
        exit 1
    fi
    echo "==> Detected version from pyproject.toml: $VERSION" >&2
fi

# ── Create isolated venv ───────────────────────────────────────────────────────

VENV_DIR="$(mktemp -d)/poet-venv"
echo "==> Creating isolated venv at $VENV_DIR..." >&2
python3 -m venv "$VENV_DIR"
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

echo "==> Installing homebrew-pypi-poet and orchestrator-auto[tui]==${VERSION} from PyPI..." >&2
pip install -q --upgrade pip
pip install -q homebrew-pypi-poet "orchestrator-auto[tui]==${VERSION}"

# ── Run poet ───────────────────────────────────────────────────────────────────

echo "==> Running poet orchestrator-auto..." >&2
echo "" >&2
echo "──────────────────────────────────────────────────────────────────────────" >&2
echo " RESOURCE STANZAS — paste into Formula/orchestrator-auto.rb" >&2
echo "──────────────────────────────────────────────────────────────────────────" >&2
echo "" >&2

# poet writes stanzas to stdout; all our progress messages go to stderr
poet orchestrator-auto

echo "" >&2
echo "──────────────────────────────────────────────────────────────────────────" >&2
echo "==> Done. Copy the stanzas above into Formula/orchestrator-auto.rb," >&2
echo "    replacing all existing resource blocks, then commit and push." >&2
echo "" >&2
echo "    Commit message suggestion:" >&2
echo "      orchestrator-auto ${VERSION} — regenerate resources" >&2
echo "──────────────────────────────────────────────────────────────────────────" >&2
