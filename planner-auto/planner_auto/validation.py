"""
Plan format validation for planner-auto.

Validates that generated plans conform to the expected milestone structure.
"""

import re


def validate_plan_format(content: str) -> list[str]:
    """Validate a plan's format against the expected structure.

    Checks:
    1. Has `## Milestone N:` headers
    2. 3-5 milestones
    3. Sequential numbering starting from 1
    4. Each milestone has `### Tasks` and `### Deliverables` sections
    5. Tasks and Deliverables contain `- [ ]` checklist items

    Args:
        content: The plan text to validate.

    Returns:
        List of error strings. Empty list means the plan is valid.
    """
    errors = []

    # Find all milestone headers
    milestone_pattern = re.compile(r"^## Milestone (\d+):", re.MULTILINE)
    matches = list(milestone_pattern.finditer(content))

    if not matches:
        errors.append("No milestone headers found. Expected '## Milestone N: [Name]' format.")
        return errors

    milestone_count = len(matches)

    # Check count (3-5)
    if milestone_count < 3:
        errors.append(f"Too few milestones: found {milestone_count}, expected 3-5.")
    elif milestone_count > 5:
        errors.append(f"Too many milestones: found {milestone_count}, expected 3-5.")

    # Check sequential numbering from 1
    numbers = [int(m.group(1)) for m in matches]
    expected = list(range(1, milestone_count + 1))
    if numbers != expected:
        errors.append(
            f"Milestone numbering is not sequential from 1. "
            f"Found: {numbers}, expected: {expected}."
        )

    # Check each milestone has ### Tasks and ### Deliverables with checklist items
    for i, match in enumerate(matches):
        milestone_num = int(match.group(1))
        start = match.start()

        # Determine the end of this milestone section
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(content)

        section = content[start:end]

        # Check for ### Tasks
        if "### Tasks" not in section:
            errors.append(f"Milestone {milestone_num}: missing '### Tasks' section.")
        else:
            # Check for checklist items in Tasks section
            tasks_match = re.search(r"### Tasks(.*?)(?=###|\Z)", section, re.DOTALL)
            if tasks_match:
                tasks_text = tasks_match.group(1)
                if "- [ ]" not in tasks_text:
                    errors.append(
                        f"Milestone {milestone_num}: '### Tasks' section has no '- [ ]' checklist items."
                    )

        # Check for ### Deliverables
        if "### Deliverables" not in section:
            errors.append(f"Milestone {milestone_num}: missing '### Deliverables' section.")
        else:
            # Check for checklist items in Deliverables section
            deliv_match = re.search(r"### Deliverables(.*?)(?=###|\Z)", section, re.DOTALL)
            if deliv_match:
                deliv_text = deliv_match.group(1)
                if "- [ ]" not in deliv_text:
                    errors.append(
                        f"Milestone {milestone_num}: '### Deliverables' section has no '- [ ]' checklist items."
                    )

    return errors
