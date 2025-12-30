"""
Git operations for orchestrator-auto.

Provides utilities for auto-commit on workflow completion.
Includes smart commit message generation using AI with secrets detection.
"""

import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Callable

# Maximum diff size to send to AI (in characters)
MAX_DIFF_SIZE = 8000


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


def has_head_commit(path: Optional[str] = None) -> bool:
    """
    Check if the repository has at least one commit (HEAD exists).

    Returns False for newly initialized repos with no commits.
    """
    try:
        cmd = ["git", "rev-parse", "HEAD"]
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


def get_staged_diff(path: Optional[str] = None) -> str:
    """
    Get the diff of staged changes only.

    Returns empty string if no staged changes or on error.
    """
    try:
        cmd = ["git", "diff", "--cached"]
        result = subprocess.run(
            cmd,
            cwd=path,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return result.stdout
        return ""
    except (subprocess.SubprocessError, OSError):
        return ""


def get_full_diff(path: Optional[str] = None, max_size: int = MAX_DIFF_SIZE) -> str:
    """
    Get the full diff of all changes (staged + unstaged).

    For new repos without HEAD, shows staged changes only.
    Large diffs are truncated with an indicator.

    Args:
        path: Working directory (optional)
        max_size: Maximum diff size in characters (default 8000)

    Returns:
        Diff string, truncated if necessary, or empty string on error.
    """
    try:
        if has_head_commit(path):
            # Normal case: diff against HEAD
            cmd = ["git", "diff", "HEAD"]
        else:
            # New repo without commits: show staged changes
            cmd = ["git", "diff", "--cached"]

        result = subprocess.run(
            cmd,
            cwd=path,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return ""

        diff = result.stdout

        # Truncate if too large
        if len(diff) > max_size:
            truncated_diff = diff[:max_size]
            truncated_diff += f"\n\n... [TRUNCATED: diff exceeded {max_size} characters] ..."
            return truncated_diff

        return diff
    except (subprocess.SubprocessError, OSError):
        return ""


def get_diff_stats(path: Optional[str] = None) -> Dict[str, int]:
    """
    Get diff statistics using git diff --shortstat.

    Returns dict with keys: files_changed, insertions, deletions.
    All values default to 0 if parsing fails.

    For new repos without HEAD, shows stats for staged changes.
    """
    stats = {"files_changed": 0, "insertions": 0, "deletions": 0}

    try:
        if has_head_commit(path):
            cmd = ["git", "diff", "--shortstat", "HEAD"]
        else:
            cmd = ["git", "diff", "--shortstat", "--cached"]

        result = subprocess.run(
            cmd,
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0 or not result.stdout.strip():
            return stats

        # Parse shortstat output
        # Examples:
        # " 2 files changed, 10 insertions(+), 3 deletions(-)"
        # " 1 file changed, 5 insertions(+)"
        # " 1 file changed, 2 deletions(-)"
        output = result.stdout.strip()

        # Parse files changed
        files_match = re.search(r'(\d+)\s+files?\s+changed', output)
        if files_match:
            stats["files_changed"] = int(files_match.group(1))

        # Parse insertions
        insertions_match = re.search(r'(\d+)\s+insertions?\(\+\)', output)
        if insertions_match:
            stats["insertions"] = int(insertions_match.group(1))

        # Parse deletions
        deletions_match = re.search(r'(\d+)\s+deletions?\(-\)', output)
        if deletions_match:
            stats["deletions"] = int(deletions_match.group(1))

        return stats
    except (subprocess.SubprocessError, OSError):
        return stats


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
    path: Optional[str] = None,
    use_smart_commit: bool = True,
    on_status: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Perform auto-commit after workflow completion.

    Smart commit mode uses AI to analyze the diff and generate a meaningful
    commit message following Conventional Commits format. Falls back to
    static message generation if:
    - Secrets are detected in the diff
    - AI generation fails for any reason
    - use_smart_commit is False

    IMPORTANT: Never pushes to remote. Only creates local commits.

    Args:
        feature_description: The feature that was implemented
        milestones: List of completed milestones
        path: Working directory (optional)
        use_smart_commit: Use AI to generate commit message (default: True)
        on_status: Optional callback for status updates (for CLI feedback)

    Returns:
        (success, message, fallback_reason) tuple
        - success: Whether commit was created
        - message: Commit output or error message
        - fallback_reason: Why fallback was used (None if smart commit worked)
            - "secrets_detected" - Diff contains potential secrets
            - "ai_generation_failed" - AI failed to generate valid message
            - "smart_commit_disabled" - Smart commit was disabled
            - None - Smart commit was used successfully
    """
    fallback_reason: Optional[str] = None

    def status(msg: str) -> None:
        """Send status update if callback provided."""
        if on_status:
            on_status(msg)

    # Check if we're in a git repo
    if not is_git_repo(path):
        return False, "Not a git repository", None

    # Check for changes
    if not has_changes(path):
        return False, "No changes to commit", None

    # Stage all changes
    success, msg = stage_all(path)
    if not success:
        return False, f"Failed to stage: {msg}", None

    # Determine commit message
    commit_msg: Optional[str] = None

    if use_smart_commit:
        status("Analyzing changes...")

        # Get diff and stats for AI analysis
        diff = get_staged_diff(path)
        stats = get_diff_stats(path)

        if diff:
            # SECURITY: Check for secrets BEFORE sending to AI
            from .secrets import contains_secrets
            has_secrets, secret_patterns = contains_secrets(diff)

            if has_secrets:
                # Block AI generation - use fallback
                status(f"Secrets detected ({', '.join(secret_patterns)}), using fallback message")
                fallback_reason = "secrets_detected"
            else:
                # Safe to call AI
                status("Generating commit message with AI...")
                try:
                    from .commit_ai import generate_smart_commit_message
                    commit_msg = generate_smart_commit_message(
                        diff=diff,
                        stats=stats,
                        feature_hint=feature_description,
                    )
                    if commit_msg is None:
                        fallback_reason = "ai_generation_failed"
                        status("AI generation failed, using fallback message")
                except Exception:
                    fallback_reason = "ai_generation_failed"
                    status("AI generation error, using fallback message")
        else:
            # No diff available, can't use smart commit
            fallback_reason = "ai_generation_failed"
    else:
        fallback_reason = "smart_commit_disabled"

    # Use fallback message if smart commit didn't produce one
    if commit_msg is None:
        commit_msg = generate_commit_message(feature_description, milestones)

    # Create commit (NEVER push)
    success, msg = create_commit(commit_msg, path)
    if not success:
        return False, f"Failed to commit: {msg}", fallback_reason

    return True, msg, fallback_reason


# Legacy wrapper for backward compatibility
def auto_commit_legacy(
    feature_description: str,
    milestones: List[dict],
    path: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Legacy auto_commit function for backward compatibility.

    Returns only (success, message) tuple without fallback_reason.
    """
    success, msg, _ = auto_commit(
        feature_description=feature_description,
        milestones=milestones,
        path=path,
        use_smart_commit=False,  # Disable smart commit for legacy behavior
    )
    return success, msg
