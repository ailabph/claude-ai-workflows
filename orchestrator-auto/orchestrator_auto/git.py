"""
Git operations for orchestrator-auto.

Provides utilities for auto-commit on workflow completion.
"""

import subprocess
from pathlib import Path
from typing import Optional, Tuple, List


def is_git_repo(path: Optional[str] = None) -> bool:
    """Check if the current or specified directory is a git repository."""
    try:
        cmd = ["git", "rev-parse", "--is-inside-work-tree"]
        result = subprocess.run(
            cmd,
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def has_changes(path: Optional[str] = None) -> bool:
    """Check if there are any uncommitted changes (staged or unstaged)."""
    try:
        # Check for any changes (staged + unstaged + untracked)
        cmd = ["git", "status", "--porcelain"]
        result = subprocess.run(
            cmd,
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10
        )
        return bool(result.stdout.strip())
    except (subprocess.SubprocessError, OSError):
        return False


def get_changed_files(path: Optional[str] = None) -> List[str]:
    """Get list of changed files (staged, unstaged, and untracked)."""
    try:
        cmd = ["git", "status", "--porcelain"]
        result = subprocess.run(
            cmd,
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return []

        files = []
        for line in result.stdout.strip().split('\n'):
            if line:
                # Format is "XY filename" where XY is status
                files.append(line[3:].strip())
        return files
    except (subprocess.SubprocessError, OSError):
        return []


def stage_all(path: Optional[str] = None) -> Tuple[bool, str]:
    """Stage all changes. Returns (success, message)."""
    try:
        cmd = ["git", "add", "-A"]
        result = subprocess.run(
            cmd,
            cwd=path,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return True, "All changes staged"
        return False, result.stderr.strip() or "Failed to stage changes"
    except subprocess.TimeoutExpired:
        return False, "Git add timed out"
    except (subprocess.SubprocessError, OSError) as e:
        return False, str(e)


def create_commit(message: str, path: Optional[str] = None) -> Tuple[bool, str]:
    """
    Create a commit with the given message.

    IMPORTANT: Does NOT include any author/co-author information.
    Uses the git user's configured identity.

    Returns (success, message/error).
    """
    try:
        cmd = ["git", "commit", "-m", message]
        result = subprocess.run(
            cmd,
            cwd=path,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            # Extract commit hash from output
            output = result.stdout.strip()
            return True, output
        return False, result.stderr.strip() or "Failed to create commit"
    except subprocess.TimeoutExpired:
        return False, "Git commit timed out"
    except (subprocess.SubprocessError, OSError) as e:
        return False, str(e)


def generate_commit_message(
    feature_description: str,
    milestones: List[dict],
    max_length: int = 500
) -> str:
    """
    Generate a commit message from workflow context.

    Args:
        feature_description: The feature that was implemented
        milestones: List of milestone dicts with 'name' and 'status' keys
        max_length: Maximum message length

    Returns:
        Formatted commit message (NO author information included)
    """
    # Create title from feature description
    title = feature_description.strip()
    if len(title) > 72:
        title = title[:69] + "..."

    # Build body with milestone summary
    body_lines = []

    completed = [m for m in milestones if m.get('status') == 'completed']
    if completed:
        body_lines.append("Completed milestones:")
        for m in completed:
            name = m.get('name', 'Unnamed milestone')
            body_lines.append(f"- {name}")

    # Combine title and body
    if body_lines:
        body = "\n".join(body_lines)
        message = f"{title}\n\n{body}"
    else:
        message = title

    # Truncate if needed
    if len(message) > max_length:
        message = message[:max_length - 3] + "..."

    return message


def auto_commit(
    feature_description: str,
    milestones: List[dict],
    path: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Perform auto-commit after workflow completion.

    Args:
        feature_description: The feature that was implemented
        milestones: List of completed milestones
        path: Working directory (optional)

    Returns:
        (success, message) tuple
    """
    # Check if we're in a git repo
    if not is_git_repo(path):
        return False, "Not a git repository"

    # Check for changes
    if not has_changes(path):
        return False, "No changes to commit"

    # Stage all changes
    success, msg = stage_all(path)
    if not success:
        return False, f"Failed to stage: {msg}"

    # Generate commit message (NO author info)
    commit_msg = generate_commit_message(feature_description, milestones)

    # Create commit
    success, msg = create_commit(commit_msg, path)
    if not success:
        return False, f"Failed to commit: {msg}"

    return True, msg
