# Django Engineer Workflow (v1)

---

## Cheat Sheet (Copy-Paste Prompts)

### New Django Task
```
Read CLAUDE_django_engineer_workflow.md and follow the workflow.

Task: [describe what you need - API endpoint, model, feature]
```

### With Existing Context
```
Read CLAUDE_django_engineer_workflow.md and CLAUDE_django_context.md.

Task: [describe task]
```

### Create New Endpoint
```
Read CLAUDE_django_engineer_workflow.md.

Create a new API endpoint:
- Resource: [e.g., User, Product, Order]
- Methods: [GET, POST, PUT, DELETE]
- Path: /api/v1/[resource]/

Include serializer, view, URL, and tests.
```

### Add Tests for Existing Code
```
Read CLAUDE_django_engineer_workflow.md.

Add unit tests for: [file or module path]
Focus on mocks, no database required.
```

### Fix Failing Tests
```
Read CLAUDE_django_engineer_workflow.md.

Tests are failing. Run pytest and fix issues.
[paste error output if available]
```

### Format and Lint
```
Read CLAUDE_django_engineer_workflow.md.

Run black formatter and fix any issues across the project.
```

---

## Overview

A **Django backend development workflow** with strict conventions for environment management, testing, API documentation, and code style.

**Core principles:**
- Conda environment per project
- pytest with mocks (no database in tests)
- OpenAPI/Swagger documentation everywhere
- Black-formatted code

---

## Question vs Implementation Mode

**CRITICAL:** Detect whether human is asking a question or requesting implementation.

### Question Mode (Read-Only)

**Triggers:** Human message contains question words or investigation requests:
- "How does...", "What is...", "Where is...", "Why does..."
- "Can you explain...", "Show me...", "Find..."
- "Is there...", "Does this...", "Which..."
- "Investigate...", "Check...", "Look at..."

**Agent behavior:**
- Investigate codebase (read files, grep, search)
- Answer the question with findings
- **DO NOT** edit any files
- **DO NOT** implement anything
- **DO NOT** create new files

**Response format:**
```markdown
## Investigation: [Topic]

### Question
[Restate the human's question]

### Findings
[What you discovered from investigating]

### Files Reviewed
- `path/to/file.py` - [what you found]
- `path/to/other.py` - [what you found]

### Answer
[Clear answer to the question]

### Related
[Optional: related files or concepts they might want to know about]
```

### Implementation Mode

**Triggers:** Human message contains action requests:
- "Create...", "Add...", "Build...", "Implement..."
- "Fix...", "Update...", "Change...", "Modify..."
- "Refactor...", "Delete...", "Remove..."

**Agent behavior:**
- Follow full workflow (environment, implement, validate, report)
- Edit/create files as needed
- Run tests and formatters

### Examples

| Human Says | Mode | Agent Does |
|------------|------|------------|
| "How does authentication work in this project?" | Question | Investigates, explains, NO edits |
| "Where are the product serializers?" | Question | Finds files, shows locations, NO edits |
| "Why is this test failing?" | Question | Investigates, explains cause, NO edits |
| "What endpoints do we have for users?" | Question | Lists endpoints, NO edits |
| "Create a new endpoint for orders" | Implementation | Full workflow with edits |
| "Fix the failing test in test_views.py" | Implementation | Edits code to fix |
| "Add validation to the product serializer" | Implementation | Edits serializer |

### Ambiguous Cases

If unclear, **ask for clarification**:

```markdown
Agent: "I found the issue with the test. Would you like me to:
1. Just explain what's wrong (no changes)
2. Fix it for you (will edit files)

Which do you prefer?"
```

### Chaining: Question then Implementation

Human might ask a question, then request implementation:

```
Human: "How does the product serializer handle pricing?"
Agent: [Investigates, explains, NO edits]