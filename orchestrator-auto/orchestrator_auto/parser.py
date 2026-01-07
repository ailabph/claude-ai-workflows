"""
Response parsers for extracting structured information from agent responses.

Parses planner and executor responses to detect response format tags
and extract relevant information.
"""

import re
from typing import Tuple, Dict, Any, Optional, List


# Response type constants
PLANNER_APPROVED = "approved"
PLANNER_CHANGES_REQUESTED = "changes_requested"
PLANNER_BLOCKED = "blocked"
PLANNER_PLAN_READY = "plan_ready"

EXECUTOR_REPORT = "report"
EXECUTOR_CLARIFICATION = "clarification"
EXECUTOR_BLOCKED = "blocked"

UNKNOWN = "unknown"


def parse_planner_response(content: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parse planner response for structured tags.

    Detects and extracts:
    - [MILESTONE_APPROVED] → ("approved", {"milestone": N})
    - [CHANGES_REQUESTED] → ("changes_requested", {"issues": [...]})
    - [HUMAN_INPUT_NEEDED] → ("blocked", {"question": "..."})
    - [PLAN_READY] → ("plan_ready", {"path": "...", "milestones": N})

    Args:
        content: Planner's response text

    Returns:
        Tuple of (response_type, extracted_data)
    """
    # Check for MILESTONE_APPROVED
    milestone_approved_pattern = r'\[MILESTONE_APPROVED\].*?Milestone\s+(\d+)\s+approved'
    match = re.search(milestone_approved_pattern, content, re.IGNORECASE | re.DOTALL)
    if match:
        milestone_num = int(match.group(1))
        return PLANNER_APPROVED, {"milestone": milestone_num}

    # Check for CHANGES_REQUESTED
    changes_pattern = r'\[CHANGES_REQUESTED\]\s*(.*?)(?:\[|$)'
    match = re.search(changes_pattern, content, re.IGNORECASE | re.DOTALL)
    if match:
        changes_text = match.group(1).strip()
        # Extract issues (lines starting with -, bullet points)
        issues = re.findall(r'[-•*]\s*(.+)', changes_text)
        if not issues:
            # If no bullet points, take the whole text
            issues = [changes_text]
        return PLANNER_CHANGES_REQUESTED, {"issues": issues, "text": changes_text}

    # Check for HUMAN_INPUT_NEEDED
    human_input_pattern = r'\[HUMAN_INPUT_NEEDED\]\s*(.+?)(?:\[|$)'
    match = re.search(human_input_pattern, content, re.IGNORECASE | re.DOTALL)
    if match:
        question = match.group(1).strip()
        return PLANNER_BLOCKED, {"question": question}

    # Check for PLAN_READY
    plan_ready_pattern = r'\[PLAN_READY\]'
    if re.search(plan_ready_pattern, content, re.IGNORECASE):
        # Extract path
        path_pattern = r'Path:\s*([^\s\n]+)'
        path_match = re.search(path_pattern, content, re.IGNORECASE)
        plan_path = path_match.group(1).strip() if path_match else None

        # Try to extract milestone count
        milestone_count_pattern = r'Milestones?:\s*(\d+)'
        milestone_match = re.search(milestone_count_pattern, content, re.IGNORECASE)
        milestones = int(milestone_match.group(1)) if milestone_match else 0

        # Extract plan content from [PLAN_CONTENT]...[/PLAN_CONTENT] tags
        plan_content = extract_plan_content(content)

        return PLANNER_PLAN_READY, {
            "path": plan_path,
            "milestones": milestones,
            "content": plan_content
        }

    return UNKNOWN, {}


def extract_plan_content(content: str) -> Optional[str]:
    """
    Extract plan content from [PLAN_CONTENT]...[/PLAN_CONTENT] tags.

    Args:
        content: Text containing plan content tags

    Returns:
        Plan content string or None if not found
    """
    pattern = r'\[PLAN_CONTENT\](.*?)\[/PLAN_CONTENT\]'
    match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def parse_plan_file(plan_path: str) -> Dict[str, Any]:
    """
    Parse a plan file and extract metadata.

    Args:
        plan_path: Path to plan markdown file

    Returns:
        Dict with:
        - valid: bool - whether plan is valid
        - milestones: int - number of milestones
        - milestone_names: List[str] - milestone names
        - error: Optional[str] - error message if invalid
    """
    from pathlib import Path

    path = Path(plan_path)
    if not path.exists():
        return {"valid": False, "error": f"Plan file not found: {plan_path}"}

    content = path.read_text()

    # Extract milestones using regex
    # Pattern: ### Milestone N: Name
    milestone_pattern = r'###\s*Milestone\s*(\d+):\s*(.+)'
    matches = re.findall(milestone_pattern, content, re.IGNORECASE)

    if not matches:
        return {"valid": False, "error": "No milestones found in plan file"}

    milestone_names = [name.strip() for _, name in matches]

    return {
        "valid": True,
        "milestones": len(matches),
        "milestone_names": milestone_names,
        "error": None
    }


def parse_executor_response(content: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parse executor response for structured tags.

    Detects and extracts:
    - [PROGRESS_REPORT]...[/PROGRESS_REPORT] → ("report", {"content": "..."})
    - [CLARIFICATION_NEEDED] → ("clarification", {"question": "..."})
    - [BLOCKED] → ("blocked", {"reason": "..."})

    Args:
        content: Executor's response text

    Returns:
        Tuple of (response_type, extracted_data)
    """
    # Check for PROGRESS_REPORT
    report_pattern = r'\[PROGRESS_REPORT\](.*?)\[/PROGRESS_REPORT\]'
    match = re.search(report_pattern, content, re.IGNORECASE | re.DOTALL)
    if match:
        report_content = match.group(1).strip()

        # Try to extract milestone number
        milestone_pattern = r'##\s*Milestone\s+(\d+):\s*([^\n-]+)'
        milestone_match = re.search(milestone_pattern, report_content)

        milestone_num = None
        milestone_name = None
        if milestone_match:
            milestone_num = int(milestone_match.group(1))
            milestone_name = milestone_match.group(2).strip()

        return EXECUTOR_REPORT, {
            "content": report_content,
            "milestone": milestone_num,
            "name": milestone_name
        }

    # Check for CLARIFICATION_NEEDED
    clarification_pattern = r'\[CLARIFICATION_NEEDED\]\s*(.+?)(?:\[|$)'
    match = re.search(clarification_pattern, content, re.IGNORECASE | re.DOTALL)
    if match:
        question = match.group(1).strip()
        return EXECUTOR_CLARIFICATION, {"question": question}

    # Check for BLOCKED
    # Pattern is flexible: matches "[BLOCKED] reason" or "[BLOCKED] Cannot proceed: reason"
    blocked_pattern = r'\[BLOCKED\]\s*(?:Cannot proceed:\s*)?(.+?)(?:\[|$)'
    match = re.search(blocked_pattern, content, re.IGNORECASE | re.DOTALL)
    if match:
        reason = match.group(1).strip()
        return EXECUTOR_BLOCKED, {"reason": reason}

    return UNKNOWN, {}


def extract_milestone_number(text: str) -> Optional[int]:
    """
    Extract milestone number from text.

    Args:
        text: Text containing milestone reference

    Returns:
        Milestone number or None
    """
    pattern = r'[Mm]ilestone\s+(\d+)'
    match = re.search(pattern, text)
    if match:
        return int(match.group(1))
    return None


def extract_file_paths(text: str) -> List[str]:
    """
    Extract file paths from progress report.

    Looks for patterns like:
    - path/to/file (created)
    - path/to/file (modified)

    Args:
        text: Progress report text

    Returns:
        List of file paths
    """
    pattern = r'^\s*[-•*]\s+([^\s]+)\s+\((created|modified)\)'
    matches = re.findall(pattern, text, re.MULTILINE)
    return [match[0] for match in matches]


def is_response_tag_present(content: str, tag: str) -> bool:
    """
    Check if a response tag is present in content.

    Args:
        content: Text to search
        tag: Tag to look for (e.g., "MILESTONE_APPROVED")

    Returns:
        True if tag is found
    """
    pattern = rf'\[{re.escape(tag)}\]'
    return bool(re.search(pattern, content, re.IGNORECASE))


def extract_all_tags(content: str) -> List[str]:
    """
    Extract all response format tags from content.

    Args:
        content: Text to search

    Returns:
        List of tag names found
    """
    pattern = r'\[([A-Z_]+)\]'
    matches = re.findall(pattern, content)
    return matches


def parse_response(content: str, agent_type: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parse response based on agent type.

    Convenience function that routes to the appropriate parser.

    Args:
        content: Response text
        agent_type: "planner" or "executor"

    Returns:
        Tuple of (response_type, extracted_data)
    """
    if agent_type.lower() == "planner":
        return parse_planner_response(content)
    elif agent_type.lower() == "executor":
        return parse_executor_response(content)
    else:
        return UNKNOWN, {}


def extract_feature_from_plan(plan_path: str) -> str:
    """
    Extract a human-friendly feature label from a plan file.

    Tries multiple extraction strategies in order:
    1. YAML frontmatter: `feature: <description>`
    2. Markdown header: `# Feature: <description>`
    3. H1 title with "Implementation Plan:": `# Implementation Plan: <description>` → `<description>`
    4. Plain H1 title: `# <description>`
    5. Filename stem as fallback

    Args:
        plan_path: Path to plan markdown file

    Returns:
        Extracted feature description (falls back to filename stem)
    """
    from pathlib import Path

    path = Path(plan_path)

    # Fallback: filename stem (remove .md extension)
    filename_fallback = path.stem.replace('_', ' ').replace('-', ' ')

    # Handle missing/unreadable file
    if not path.exists():
        return filename_fallback

    try:
        content = path.read_text()
    except Exception:
        # If file is unreadable, fall back to filename
        return filename_fallback

    lines = content.split('\n')

    # Strategy 1: Check for YAML frontmatter (first ~20 lines)
    if lines and lines[0].strip() == '---':
        # Look for closing ---
        yaml_end = -1
        for i in range(1, min(len(lines), 20)):
            if lines[i].strip() == '---':
                yaml_end = i
                break

        if yaml_end > 0:
            # Parse YAML frontmatter
            yaml_section = lines[1:yaml_end]
            for line in yaml_section:
                # Match "feature: description"
                match = re.match(r'^\s*feature:\s*(.+)', line, re.IGNORECASE)
                if match:
                    return match.group(1).strip()

    # Strategy 2-4: Check markdown headers in first ~20 lines
    for i, line in enumerate(lines[:20]):
        # Strategy 2: # Feature: description
        match = re.match(r'^\s*#\s+Feature:\s*(.+)', line, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Strategy 3: # Implementation Plan: description
        match = re.match(r'^\s*#\s+Implementation Plan:\s*(.+)', line, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Strategy 4: Plain # Title (first H1 found)
        match = re.match(r'^\s*#\s+([^#].+)', line)
        if match:
            title = match.group(1).strip()
            # Remove trailing patterns like " - Implementation Plan"
            title = re.sub(r'\s*-?\s*Implementation Plan\s*$', '', title, flags=re.IGNORECASE)
            return title

    # Strategy 5: Fallback to filename stem
    return filename_fallback
