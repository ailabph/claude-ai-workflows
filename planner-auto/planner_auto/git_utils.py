"""Git utility helpers for planner-auto."""

import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


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
