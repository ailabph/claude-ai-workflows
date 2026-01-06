# Backend System

AI-agent context documentation for consistent backend implementation. Contains standard patterns for API design, database schemas, service architecture, and validation.

## Directory Structure

```
backend-system/
├── README.md                 ← You are here
├── BACKEND_MAP.md            ← Fast navigation map (domain → files)
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

### File Purposes

| File | Purpose |
|------|---------|
| `BACKEND_MAP.md` | **Navigation** - "Where do I find feature X?" |
| `*_PATTERNS.md` | **Standards** - "How should I write this?" |
| `ENDPOINT_AUDIT.md` | **Compliance** - "Are we following standards?" |
| `GLOSSARY.md` | **Definitions** - "What does X mean?" |

---

## Setup Prompts

### Prompt: Populate from Existing Repo

Copy-paste this prompt to have Claude analyze your codebase and populate the backend-system files:

```
Analyze this codebase and populate the backend-system/ documentation files with our actual patterns.

For each file, examine the codebase to extract real examples:

1. **BACKEND_MAP.md** - Map our project structure: identify domains, list routes/services/models per domain, document stack bindings (framework, ORM, auth), add targeted search queries.

2. **API_PATTERNS.md** - Find our response envelope format, pagination structure, error responses. Look at existing API handlers/views.

3. **ERROR_CODES.md** - Extract error codes from exception handlers, error classes, and API responses.

4. **AUTH_PATTERNS.md** - Document our JWT claims, permission decorators, auth middleware, RBAC structure.

5. **DATABASE_PATTERNS.md** - Analyze models/migrations for naming conventions, common columns, relationship patterns, index strategies.

6. **SERVICE_PATTERNS.md** - Find a representative service class, document our DI approach, transaction patterns.

7. **VALIDATION_PATTERNS.md** - Extract Pydantic/serializer patterns, common validators, request/response models.

8. **ENDPOINT_AUDIT.md** - List all current API endpoints and audit them against the criteria.

9. **GLOSSARY.md** - Add domain-specific terms from our business logic.

Use the templates in backend-system/template/ as structure guides, but replace placeholder values with our actual code patterns. Include real code snippets from our codebase as examples.
```

### Prompt: Populate Backend Map (Priority)

Start with the navigation map - it helps with all other files:

```
Read backend-system/template/BACKEND_MAP_template.md for the structure.

Analyze this codebase and populate backend-system/BACKEND_MAP.md:
1. Identify the tech stack (framework, ORM, auth, validation, etc.)
2. Map the project directory structure
3. List each domain (users, orders, auth, etc.) with its routes, services, models, schemas
4. Identify shared services with high blast radius
5. Add targeted search queries for each domain
6. Document any known gotchas or exceptions

This is the navigation foundation - do this first before other files.
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
Before implementing, read:
1. backend-system/BACKEND_MAP.md - Find relevant files for this feature
2. backend-system/API_PATTERNS.md - Response format and conventions
3. backend-system/SERVICE_PATTERNS.md - Service layer structure

Use BACKEND_MAP.md to navigate directly to the right files instead of searching.
Follow our patterns for consistency with the existing codebase.
```

### Prompt: New Endpoint Implementation

```
Implement [describe endpoint] in the [domain] domain.

1. Read backend-system/BACKEND_MAP.md to find the [domain] section - it lists the exact files to modify
2. Follow backend-system/API_PATTERNS.md for response envelope format
3. Follow backend-system/SERVICE_PATTERNS.md for service structure
4. Follow backend-system/VALIDATION_PATTERNS.md for request validation

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

Backend documentation is in `backend-system/`.

**Start here:** `BACKEND_MAP.md` - maps domains to files, reduces searching.

| File | When to Read |
|------|--------------|
| `BACKEND_MAP.md` | **First** - find files for your feature/domain |
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

- **New domain/feature added** → Add to BACKEND_MAP.md
- **New pattern adopted** → Update relevant pattern file
- **New endpoint added** → Add to ENDPOINT_AUDIT.md
- **Files moved/renamed** → Update BACKEND_MAP.md paths
- **Pattern changed** → Update docs, note breaking change
- **New domain term** → Add to GLOSSARY.md

### Quarterly Review

```
Review backend-system/ documentation:
1. Is BACKEND_MAP.md current? Any new domains, moved files, or stale paths?
2. Are the patterns still accurate?
3. Are there new patterns not documented?
4. Is ENDPOINT_AUDIT.md current?
5. Any deprecated patterns to remove?
```
