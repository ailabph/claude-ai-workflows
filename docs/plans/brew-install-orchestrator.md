# Homebrew Installation Plan for orchestrator-auto

**Goal:** `brew install orchestrator-auto` → `orchestrator watch .plans --tui --verbose --convert`

---

## How Homebrew Works (Python CLI)

- **Tap** — a GitHub repo named `homebrew-<something>` containing Ruby formula files
- **Formula** — a `.rb` file declaring source URL, SHA256, dependencies, and install steps
- **For Python tools** — Homebrew creates an isolated virtualenv, installs all `resource` blocks, symlinks CLI scripts into `/opt/homebrew/bin/`
- Key helper: `include Language::Python::Virtualenv` + `virtualenv_install_with_resources`
- `virtualenv_install_with_resources` installs from `buildpath` (the root of the extracted archive) — **this matters for monorepos**

---

## Package Info

From `orchestrator-auto/pyproject.toml`:

| Field | Value |
|-------|-------|
| Name | `orchestrator-auto` |
| Version | `1.9.0` |
| Python requirement | `>=3.10` (`environment.yml` pins `python=3.11` for local dev) |
| Entry point | `orchestrator = "orchestrator_auto.cli:cli"` |
| Core deps | `claude-agent-sdk>=0.1.46`, `click>=8.0`, `prompt_toolkit>=3.0`, `pyyaml>=6.0` |
| TUI extra | `textual>=0.80.0` (required for `--tui` flag, `cli.py:3664`) |
| Telegram extra | `httpx>=0.27` |

**watch command flags** (`cli.py:3651–3665`):
- `--tui/--no-tui` — launches Textual TUI dashboard (default: off)
- `--verbose/-v` — expanded dual-panel layout in TUI (default: compact)
- `--convert/--no-convert` — auto-convert invalid plans (default: **disabled**) — include this or watch silently skips non-conforming plan files

---

## Prerequisites

### Option A — Publish to PyPI (recommended)

PyPI sdist is the cleanest Homebrew source — the archive contains only the package, so `virtualenv_install_with_resources` works without subdirectory handling.

```bash
cd orchestrator-auto/
pip install build twine
python -m build
twine upload dist/*
```

### Option B — GitHub Release Tarball (monorepo caveat)

⚠️ **Monorepo warning:** A repo-root GitHub archive unpacks as `claude-ai-workflows-v1.9.0/orchestrator-auto/...`. The formula's `install` block must `cd` into the subdirectory before installing — `virtualenv_install_with_resources` alone will not work.

```
url "https://github.com/ailabph/claude-ai-workflows/archive/refs/tags/v1.9.0.tar.gz"
```

Required formula `install` override for this case:
```ruby
def install
  venv = virtualenv_create(libexec, "python3.11")
  venv.pip_install resources
  venv.pip_install_and_link buildpath/"orchestrator-auto"
end
```

---

## Step 1 — Create the Tap Repo

Create a GitHub repo named **`homebrew-orchestrator-auto`** (the `homebrew-` prefix is mandatory).

```bash
brew tap-new dannyalmaden/orchestrator-auto
# Creates: ~/Library/Taps/dannyalmaden/homebrew-orchestrator-auto/
```

---

## Step 2 — Generate Resource Stanzas

### Preferred: `brew update-python-resources` (post-publish only)

Once the formula file exists and the package is on PyPI:
```bash
brew update-python-resources Formula/orchestrator-auto.rb
```
This updates all `resource` blocks in-place with current PyPI URLs and SHA256s.

### Fallback: `homebrew-pypi-poet` (pre-publish or when above fails)

Must run in a **fresh venv**. Use the local path if the package is not yet on PyPI:

```bash
python -m venv /tmp/poet-env
source /tmp/poet-env/bin/activate

# Pre-publish (local install):
pip install "/path/to/claude-ai-workflows/orchestrator-auto[tui]"

# Post-publish (PyPI):
# pip install "orchestrator-auto[tui]"

pip install homebrew-pypi-poet
poet -f orchestrator-auto > /tmp/formula-draft.rb   # full formula with all resources
```

`poet` outputs real PyPI URLs + SHA256 hashes for every transitive dependency — source of truth for the formula's `resource` blocks.

---

## Step 3 — The Formula

File: `Formula/orchestrator-auto.rb` in the tap repo.

```ruby
class OrchestratorAuto < Formula
  include Language::Python::Virtualenv

  desc "Automated two-agent orchestrator workflow using Claude Agent SDK"
  homepage "https://github.com/ailabph/claude-ai-workflows"
  # PyPI sdist URL (get real sha256 after publishing):
  url "https://files.pythonhosted.org/packages/source/o/orchestrator-auto/orchestrator_auto-1.9.0.tar.gz"
  sha256 "REPLACE_WITH_ACTUAL_SHA256"
  license "MIT"

  depends_on "python@3.13"   # pin to currently maintained Homebrew Python (not local dev version)
                             # package requires >=3.10; update this when Homebrew moves to 3.14

  # --- Core dependencies ---
  # Run `poet -f orchestrator-auto` to get real URLs + sha256s for all of these

  resource "claude-agent-sdk" do
    url "https://files.pythonhosted.org/packages/.../claude_agent_sdk-0.1.48.tar.gz"
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

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/.../PyYAML-6.0.2.tar.gz"
    sha256 "REPLACE"
  end

  # --- TUI support (required for `orchestrator watch --tui`) ---
  resource "textual" do
    url "https://files.pythonhosted.org/packages/.../textual-0.89.1.tar.gz"
    sha256 "REPLACE"
  end

  # textual pulls in: rich, markdown-it-py, linkify-it-py, etc.
  # poet will enumerate all of them automatically

  def install
    virtualenv_install_with_resources  # works when url points to PyPI sdist
  end

  test do
    system bin/"orchestrator", "--version"
  end
end
```

---

## Step 4 — Push and Test

```bash
cd ~/Library/Taps/dannyalmaden/homebrew-orchestrator-auto/

# Audit and test before pushing
brew audit --strict Formula/orchestrator-auto.rb
brew install --build-from-source dannyalmaden/orchestrator-auto/orchestrator-auto
brew test orchestrator-auto   # runs the test do block

git add Formula/orchestrator-auto.rb
git commit -m "add orchestrator-auto formula v1.9.0"
git push
```

---

## User Installation

```bash
brew tap dannyalmaden/orchestrator-auto
brew install orchestrator-auto

# Auth setup (required before first use — brew install is not enough)

# Option A: Claude Pro/Max subscription
# Requires Claude Code CLI installed separately (brew install does NOT provide it):
#   npm install -g @anthropic-ai/claude-code
# Then:
claude login
claude setup-token
export CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat01-..."   # add to ~/.zshrc

# Option B: API key (no Claude Code CLI needed)
export ANTHROPIC_API_KEY="sk-ant-api03-..."          # add to ~/.zshrc

# Then run watch mode
orchestrator watch .plans --tui --verbose --convert
```

> `--convert` is off by default (`cli.py:3654`). Without it, invalid plan files are **quarantined** — renamed to `_orchestrator-skip__<filename>` in-place (`watch_controller.py:342`) — and skipped. They are not silently ignored; the rename is an active operation. Use `--convert` to attempt auto-conversion before quarantine.

Or one-liner install (tap auto-added):
```bash
brew install dannyalmaden/orchestrator-auto/orchestrator-auto
```

---

## Gotchas

| Issue | Fix |
|-------|-----|
| `textual` missing → `--tui` crashes | Include `textual` + all its recursive deps as `resource` blocks |
| SHA256 mismatch | Re-run `poet` in a fresh venv — never hand-edit hashes |
| `claude-agent-sdk` bundles a CLI binary | May need `bin.install` if it ships compiled binaries separately |
| GitHub tarball + monorepo → install fails | Use PyPI sdist, or override `install` with `venv.pip_install_and_link buildpath/"orchestrator-auto"` |
| `pip install "orchestrator-auto[tui]"` fails | Package not on PyPI yet — use local path `pip install "./orchestrator-auto[tui]"` for poet generation |
| Formula audit fails | Fix with `brew audit --strict` output before pushing |
| Python version | Pin to currently maintained Homebrew Python (e.g. `python@3.13`), not local dev env; update when Homebrew advances |
| Tool runs but auth fails | Set `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` — see `CONFIGURATION.md` |
| OAuth path needs Claude Code CLI | Install separately (`npm install -g @anthropic-ai/claude-code`); not bundled with this formula |
| Watch "skips" plan files | Invalid plans are quarantined as `_orchestrator-skip__<name>` (`watch_controller.py:342`), not silently ignored; add `--convert` to attempt conversion first |

---

## References

- [How to Create and Maintain a Tap — Homebrew Docs](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap)
- [Taps (Third-Party Repositories) — Homebrew Docs](https://docs.brew.sh/Taps)
- [Python for Formula Authors — Homebrew Docs](https://docs.brew.sh/Python-for-Formula-Authors)
- [Packaging a Python CLI tool for Homebrew — Simon Willison](https://til.simonwillison.net/homebrew/packaging-python-cli-for-homebrew)
- [homebrew-pypi-poet — GitHub](https://github.com/tdsmith/homebrew-pypi-poet)
- [claude-agent-sdk — PyPI](https://pypi.org/project/claude-agent-sdk/)
- [Formula Cookbook — Homebrew Docs](https://docs.brew.sh/Formula-Cookbook)
