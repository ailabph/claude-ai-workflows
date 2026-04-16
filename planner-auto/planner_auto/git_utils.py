"""Git utility helpers for planner-auto."""

import fnmatch
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# Extensions considered source code for auto-scan
SOURCE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
    ".rb", ".vue", ".svelte", ".swift", ".kt", ".cs", ".php",
}

# Config files matched by exact filename
CONFIG_FILENAMES = {
    "pyproject.toml", "setup.py", "setup.cfg", "package.json",
    "tsconfig.json", "Cargo.toml", "go.mod", "Makefile",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".env.example", "requirements.txt",
}

# Top-level docs to include
DOC_FILENAMES = {"README.md", "CLAUDE.md", "AGENTS.md"}

# Patterns to always exclude
DEFAULT_EXCLUDE_PATTERNS = [
    "*lock*", "*.min.js", "*.min.css", "*.generated.*",
    "node_modules/*", "dist/*", "build/*", "__pycache__/*",
    ".git/*", "*.egg-info/*", ".tox/*", ".venv/*", "venv/*",
]


def discover_repo_root(cwd: Optional[str] = None) -> Optional[str]:
    """Discover the root of the Git repository that contains *cwd*.

    Uses ``git rev-parse --show-toplevel`` to find the repository root.

    Args:
        cwd: Working directory to start the search from.  Defaults to the
             process working directory when ``None``.

    Returns:
        Absolute path to the repository root, or ``None`` if *cwd* is not
        inside a Git repository or if Git is not installed.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd,
        )
        if result.returncode == 0:
            repo_root = result.stdout.strip()
            logger.debug("Discovered repo root: %s", repo_root)
            return repo_root
        logger.debug(
            "git rev-parse failed (rc=%d): %s",
            result.returncode,
            result.stderr.strip(),
        )
        return None
    except FileNotFoundError:
        # Git is not installed.
        logger.debug("git not found; repo root discovery skipped")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("git rev-parse timed out; repo root discovery skipped")
        return None
    except Exception as exc:  # pragma: no cover
        logger.warning("Unexpected error during repo root discovery: %s", exc)
        return None


def list_tracked_files(
    cwd: Optional[str] = None,
    include_ext: Optional[set] = None,
    exclude_patterns: Optional[list] = None,
    max_files: int = 20,
) -> list:
    """Return tracked files from ``git ls-files``, filtered and priority-sorted.

    Args:
        cwd: Repository root to run from.
        include_ext: Set of extensions to include (e.g. ``{".py", ".ts"}``).
            Defaults to :data:`SOURCE_EXTENSIONS`.
        exclude_patterns: Extra glob patterns to exclude on top of
            :data:`DEFAULT_EXCLUDE_PATTERNS`.
        max_files: Maximum number of files to return.

    Returns:
        List of relative file paths, priority-sorted (configs first, then
        docs, then source by directory depth).
    """
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=cwd,
        )
        if result.returncode != 0:
            logger.debug("git ls-files failed (rc=%d)", result.returncode)
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.debug("git ls-files error: %s", exc)
        return []

    extensions = include_ext or SOURCE_EXTENSIONS
    excludes = DEFAULT_EXCLUDE_PATTERNS + (exclude_patterns or [])

    all_files = result.stdout.strip().splitlines()
    configs = []
    docs = []
    sources = []

    for f in all_files:
        basename = os.path.basename(f)

        # Exclude check
        if any(fnmatch.fnmatch(f, pat) for pat in excludes):
            continue

        # Categorize
        if basename in CONFIG_FILENAMES:
            configs.append(f)
        elif basename in DOC_FILENAMES and f.count(os.sep) == 0:
            # Top-level docs only
            docs.append(f)
        elif os.path.splitext(basename)[1] in extensions:
            sources.append(f)

    # Sort sources by directory depth (shallower first), then alphabetically
    sources.sort(key=lambda p: (p.count(os.sep), p))

    # Priority: configs → docs → source
    prioritized = configs + docs + sources
    return prioritized[:max_files]
