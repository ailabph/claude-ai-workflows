"""Tests for planner_auto.validation — plan format validation."""

import pytest

from planner_auto.validation import validate_plan_format


VALID_PLAN = """\
# Implementation Plan

## Milestone 1: Setup

### Tasks
- [ ] Create project structure
- [ ] Set up database

### Deliverables
- [ ] Project runs without errors

## Milestone 2: Core Logic

### Tasks
- [ ] Implement business logic
- [ ] Add error handling

### Deliverables
- [ ] All unit tests pass

## Milestone 3: API Layer

### Tasks
- [ ] Create REST endpoints
- [ ] Add authentication

### Deliverables
- [ ] API integration tests pass
"""


class TestValidatePlanFormat:
    """Tests for validate_plan_format()."""

    def test_valid_plan_returns_no_errors(self):
        errors = validate_plan_format(VALID_PLAN)
        assert errors == []

    def test_no_milestones(self):
        errors = validate_plan_format("Just some text without milestones.")
        assert len(errors) == 1
        assert "No milestone headers" in errors[0]

    def test_too_few_milestones(self):
        plan = """\
## Milestone 1: Only One

### Tasks
- [ ] Task

### Deliverables
- [ ] Deliverable
"""
        errors = validate_plan_format(plan)
        assert any("Too few milestones" in e for e in errors)

    def test_too_many_milestones(self):
        milestones = []
        for i in range(1, 7):  # 6 milestones
            milestones.append(f"""\
## Milestone {i}: M{i}

### Tasks
- [ ] Task {i}

### Deliverables
- [ ] Deliverable {i}
""")
        plan = "\n".join(milestones)
        errors = validate_plan_format(plan)
        assert any("Too many milestones" in e for e in errors)

    def test_wrong_numbering(self):
        plan = """\
## Milestone 1: First

### Tasks
- [ ] Task

### Deliverables
- [ ] Deliverable

## Milestone 3: Third (skipped 2)

### Tasks
- [ ] Task

### Deliverables
- [ ] Deliverable

## Milestone 4: Fourth

### Tasks
- [ ] Task

### Deliverables
- [ ] Deliverable
"""
        errors = validate_plan_format(plan)
        assert any("not sequential" in e for e in errors)

    def test_missing_tasks_section(self):
        plan = """\
## Milestone 1: First

### Deliverables
- [ ] Deliverable

## Milestone 2: Second

### Tasks
- [ ] Task

### Deliverables
- [ ] Deliverable

## Milestone 3: Third

### Tasks
- [ ] Task

### Deliverables
- [ ] Deliverable
"""
        errors = validate_plan_format(plan)
        assert any("Milestone 1" in e and "Tasks" in e for e in errors)

    def test_missing_deliverables_section(self):
        plan = """\
## Milestone 1: First

### Tasks
- [ ] Task

## Milestone 2: Second

### Tasks
- [ ] Task

### Deliverables
- [ ] Deliverable

## Milestone 3: Third

### Tasks
- [ ] Task

### Deliverables
- [ ] Deliverable
"""
        errors = validate_plan_format(plan)
        assert any("Milestone 1" in e and "Deliverables" in e for e in errors)

    def test_missing_checklist_items_in_tasks(self):
        plan = """\
## Milestone 1: First

### Tasks
Some text without checklist

### Deliverables
- [ ] Deliverable

## Milestone 2: Second

### Tasks
- [ ] Task

### Deliverables
- [ ] Deliverable

## Milestone 3: Third

### Tasks
- [ ] Task

### Deliverables
- [ ] Deliverable
"""
        errors = validate_plan_format(plan)
        assert any("Milestone 1" in e and "Tasks" in e and "checklist" in e for e in errors)

    def test_five_milestones_valid(self):
        """5 milestones should be valid (upper bound)."""
        milestones = []
        for i in range(1, 6):
            milestones.append(f"""\
## Milestone {i}: M{i}

### Tasks
- [ ] Task {i}

### Deliverables
- [ ] Deliverable {i}
""")
        plan = "\n".join(milestones)
        errors = validate_plan_format(plan)
        assert errors == []
