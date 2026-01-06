# Backend System

AI-agent context documentation for consistent backend implementation. Contains standard patterns for API design, database schemas, service architecture, and validation.

## Directory Structure

```
backend-system/
├── README.md                 ← You are here
├── API_PATTERNS.md           ← Your repo's actual patterns
├── AUTH_PATTERNS.md
├── DATABASE_PATTERNS.md
├── ENDPOINT_AUDIT.md
├── ERROR_CODES.md
├── GLOSSARY.md
├── SERVICE_PATTERNS.md
├── VALIDATION_PATTERNS.md
└── template/                 ← Reference templates
    └── *_template.md
```

---

## Setup Prompts

### Prompt: Populate from Existing Repo

Copy-paste this prompt to have Claude analyze your codebase and populate the backend-system files:

```
Analyze this codebase and populate the backend-system/ documentation files with our actual patterns.

For each file, examine the codebase to extract real examples:

1. **API_PATTERNS.md** - Find our response envelope format, pagination structure, error responses. Look at existing API handlers/views.

2. **ERROR_CODES.md** - Extract error codes from exception handlers, error classes, and API responses.

3. **AUTH_PATTERNS.md** - Document our JWT claims, permission decorators, auth middleware, RBAC structure.

4. **DATABASE_PATTERNS.md** - Analyze models/migrations for naming conventions, common columns, relationship patterns, index strategies.

5. **SERVICE_PATTERNS.md** - Find a representative service class, document our DI approach, transaction patterns.

6. **VALIDATION_PATTERNS.md** - Extract Pydantic/serializer patterns, common validators, request/response models.

7. **ENDPOINT_AUDIT.md** - List all current API endpoints and audit them against the criteria.

8. **GLOSSARY.md** - Add domain-specific terms from our business logic.

Use the templates in backend-system/template/ as structure guides, but replace placeholder values with our actual code patterns. Include real code snippets from our codebase as examples.
```

### Prompt: Populate Specific File

```
Read backend-system/template/API_PATTERNS_template.md for the structure.
Then analyze our codebase to find our actual API patterns.
Populate backend-system/API_PATTERNS.md with our real response format, pagination, and error handling.
Include actual code snippets from our codebase as examples.
```

---

## Session Prompts

### Prompt: Start of Backend Session

Copy-paste at the beginning of a session when working on backend features:

```
Before implementing, read the backend standards:
- backend-system/API_PATTERNS.md - Response format and conventions
- backend-system/SERVICE_PATTERNS.md - Service layer structure
- backend-system/DATABASE_PATTERNS.md - Schema conventions
- backend-system/VALIDATION_PATTERNS.md - Request validation

Follow these patterns for consistency with the existing codebase.
```

### Prompt: New Endpoint Implementation

```
Implement [describe endpoint].

Follow our backend patterns:
1. Read backend-system/API_PATTERNS.md for response envelope format
2. Read backend-system/ERROR_CODES.md for error handling
3. Read backend-system/SERVICE_PATTERNS.md for service structure
4. Read backend-system/VALIDATION_PATTERNS.md for request validation

After implementation, update backend-system/ENDPOINT_AUDIT.md with the new endpoint.
```

### Prompt: New Database Model

```
Create a new model for [describe entity].

Follow our database patterns in backend-system/DATABASE_PATTERNS.md:
- Use our naming conventions
- Include standard columns (id, created_at, updated_at, etc.)
- Add appropriate indexes
- Follow our relationship patterns
```

### Prompt: Code Review Against Standards

```
Review this code against our backend standards:
- backend-system/API_PATTERNS.md
- backend-system/ERROR_CODES.md
- backend-system/SERVICE_PATTERNS.md

List any deviations from our patterns and suggest fixes.
```

---

## CLAUDE.md Integration

Add this section to your repo's `CLAUDE.md`:

```markdown
## Backend Standards

Backend patterns are documented in `backend-system/`. Read before implementing:

| File | When to Read |
|------|--------------|
| `API_PATTERNS.md` | Creating/modifying endpoints |
| `ERROR_CODES.md` | Adding error handling |
| `AUTH_PATTERNS.md` | Working with authentication/authorization |
| `DATABASE_PATTERNS.md` | Creating models or migrations |
| `SERVICE_PATTERNS.md` | Writing business logic |
| `VALIDATION_PATTERNS.md` | Adding request/response validation |

Update `ENDPOINT_AUDIT.md` after adding new endpoints.
```

---

## Maintenance

### When to Update

- **New pattern adopted** → Update relevant file
- **New endpoint added** → Add to ENDPOINT_AUDIT.md
- **Pattern changed** → Update docs, note breaking change
- **New domain term** → Add to GLOSSARY.md

### Quarterly Review

```
Review backend-system/ documentation:
1. Are the patterns still accurate?
2. Are there new patterns not documented?
3. Is ENDPOINT_AUDIT.md current?
4. Any deprecated patterns to remove?
```
