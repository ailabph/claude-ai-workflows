#!/usr/bin/env bash
# ⚠️  EMERGENCY USE ONLY — automated publishing is handled by GitHub Actions (OIDC).
#
# Normal releases are published automatically via .github/workflows/release.yml
# using PyPI Trusted Publishing (OIDC) — no token required and no manual steps
# needed. Use that workflow for all normal releases.
#
# Use this script ONLY for out-of-band emergency publishes (e.g. CI is down,
# OIDC is broken, or you need to publish from a local machine without waiting
# for the automated pipeline). A PYPI_TOKEN API token is required.
#
# See docs/RELEASE.md for the standard release process.
#
# Publish orchestrator-auto to PyPI using an API token.
# Usage:
#   PYPI_TOKEN=pypi-... ./scripts/publish_pypi.sh        # token via env
#   ./scripts/publish_pypi.sh                             # prompts for token

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Token ────────────────────────────────────────────────────────────────────
if [[ -z "${PYPI_TOKEN:-}" ]]; then
    read -rsp "PyPI API token (pypi-...): " PYPI_TOKEN
    echo
fi

if [[ "$PYPI_TOKEN" != pypi-* ]]; then
    echo "Error: token should start with 'pypi-'" >&2
    exit 1
fi

# ── Build venv (isolated from conda base to avoid urllib3/requests_toolbelt conflicts) ──
PUBLISH_VENV="$(mktemp -d)/publish-venv"
echo "==> Creating isolated publish venv at $PUBLISH_VENV..."
python -m venv "$PUBLISH_VENV"
source "$PUBLISH_VENV/bin/activate"
pip install -q --upgrade pip build twine

# ── Build ─────────────────────────────────────────────────────────────────────
echo "==> Cleaning previous dist/..."
rm -rf "$PKG_DIR/dist"

echo "==> Building sdist + wheel..."
cd "$PKG_DIR"
python -m build

echo ""
echo "Built artifacts:"
ls -lh dist/

# ── Verify theme.tcss is in wheel ─────────────────────────────────────────────
echo ""
echo "==> Verifying theme.tcss is packaged..."

# Extract directly from wheel — avoids grep pipefail interaction on macOS
WHL=$(ls dist/orchestrator_auto-*.whl)
TCSS_CONTENT=$(unzip -p "$WHL" "orchestrator_auto/tui/styles/theme.tcss" 2>/dev/null || true)
if [[ -n "$TCSS_CONTENT" ]]; then
    echo "    ✓ theme.tcss present in wheel"
else
    echo "    ✗ theme.tcss MISSING from wheel — aborting" >&2
    exit 1
fi

TARBALL=$(ls dist/orchestrator_auto-*.tar.gz)
TCSS_IN_SDIST=$(tar -tzf "$TARBALL" 2>/dev/null | { grep "theme.tcss" || true; })
if [[ -n "$TCSS_IN_SDIST" ]]; then
    echo "    ✓ theme.tcss present in sdist"
else
    echo "    ✗ theme.tcss MISSING from sdist — aborting" >&2
    exit 1
fi

# ── Upload ────────────────────────────────────────────────────────────────────
echo ""
echo "==> Uploading to PyPI..."
TWINE_USERNAME=__token__ \
TWINE_PASSWORD="$PYPI_TOKEN" \
    twine upload dist/*

echo ""
echo "✓ Published. Verify at: https://pypi.org/project/orchestrator-auto/"
