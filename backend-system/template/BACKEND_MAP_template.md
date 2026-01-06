# Backend Map

> **Purpose:** Token-efficient "where to look first" map for AI agents working on backend code.
> Reduces exploratory searching by mapping domains/features to specific files.

---

## 0) Agent Contract (Defaults)

- Use this map to reduce exploratory searching
- Verify with targeted searches (to catch duplicates or moved files)
- Prefer existing services and patterns over creating new ones
- If a task requires a new pattern, document it in **Exceptions** and update reference docs

---

## 1) Stack Bindings (Fill In)

| Concept | This Repo Uses | Location | Notes |
|---------|----------------|----------|-------|
| Framework | `<FastAPI/Django/Express/etc.>` | `<entrypoint>` | `<version>` |
| ORM / DB | `<SQLAlchemy/Django ORM/Prisma>` | `<config path>` | `<DB type>` |
| Migrations | `<Alembic/Django/Prisma>` | `<migrations dir>` | |
| Auth | `<JWT/Session/OAuth>` | `<middleware path>` | |
| Validation | `<Pydantic/DRF/Zod>` | `<base schemas>` | |
| Background Jobs | `<Celery/Bull/none>` | `<tasks dir>` | |
| Caching | `<Redis/Memcached/none>` | `<config>` | |
| Testing | `<pytest/jest>` | `<tests dir>` | |

---

## 2) Project Structure

```
<root>/
├── src/                    # or app/, api/, etc.
│   ├── api/               # Route handlers / controllers
│   │   └── routes/        # Endpoint definitions
│   ├── services/          # Business logic
│   ├── models/            # Database models / entities
│   ├── schemas/           # Request/response schemas (DTOs)
│   ├── repositories/      # Data access layer (if separate)
│   ├── middleware/        # Auth, logging, error handling
│   ├── utils/             # Shared utilities
│   └── config/            # App configuration
├── tests/
├── migrations/            # or alembic/, prisma/migrations/
└── <config files>         # pyproject.toml, package.json, etc.
```

---

## 3) Fast Map — Domain → Files

> For each domain: list primary files and targeted search queries.

### Auth Domain

| Layer | Path | Description |
|-------|------|-------------|
| Routes | `<src/api/routes/auth.py>` | Login, register, refresh endpoints |
| Service | `<src/services/auth_service.py>` | Token generation, validation |
| Middleware | `<src/middleware/auth.py>` | JWT verification, permission checks |
| Schemas | `<src/schemas/auth.py>` | LoginRequest, TokenResponse |
| Models | `<src/models/user.py>` | User, Session, RefreshToken |

**Targeted searches:**
```bash
rg "def login" -t py
rg "@require_auth" -t py
rg "verify_token" -t py
```

---

### Users Domain

| Layer | Path | Description |
|-------|------|-------------|
| Routes | `<src/api/routes/users.py>` | CRUD endpoints |
| Service | `<src/services/user_service.py>` | User business logic |
| Schemas | `<src/schemas/user.py>` | CreateUserRequest, UserResponse |
| Models | `<src/models/user.py>` | User model |

**Targeted searches:**
```bash
rg "class User" -t py
rg "UserService" -t py
rg "/users" -t py
```

---

### [Domain Name] (Template)

| Layer | Path | Description |
|-------|------|-------------|
| Routes | `<path>` | |
| Service | `<path>` | |
| Schemas | `<path>` | |
| Models | `<path>` | |
| Repository | `<path>` | (if applicable) |

**Targeted searches:**
```bash
rg "<pattern>" -t py
```

---

## 4) Shared Services (Blast Radius)

> Services used across multiple domains. Changes here have wide impact.

| Service | Path | Used By | Risk | Find Usages |
|---------|------|---------|------|-------------|
| AuthService | `<path>` | All protected routes | High | `rg "AuthService" -t py` |
| EmailService | `<path>` | Users, Orders, Notifications | High | `rg "EmailService" -t py` |
| CacheService | `<path>` | Multiple services | Medium | `rg "CacheService" -t py` |
| BaseRepository | `<path>` | All repositories | High | `rg "BaseRepository" -t py` |

---

## 5) Canonical Recipes

### Add New Endpoint

1. Create/update route in `src/api/routes/<domain>.py`
2. Create/update service method in `src/services/<domain>_service.py`
3. Create request/response schemas in `src/schemas/<domain>.py`
4. Add tests in `tests/test_<domain>.py`
5. Update `backend-system/ENDPOINT_AUDIT.md`

```python
# Route template
@router.post("/<resources>", response_model=ResourceResponse, status_code=201)
async def create_resource(
    input: CreateResourceRequest,
    service: ResourceService = Depends(get_resource_service),
):
    result = await service.create(input)
    return {"success": True, "data": result}
```

### Add New Model

1. Create model in `src/models/<name>.py`
2. Create migration: `alembic revision --autogenerate -m "add <name> table"`
3. Review migration file in `migrations/versions/`
4. Apply migration: `alembic upgrade head`
5. Add to `src/models/__init__.py` exports

```python
# Model template
class Resource(Base):
    __tablename__ = "resources"

    id = Column(UUID, primary_key=True, default=uuid4)
    # ... fields
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at = Column(DateTime, nullable=True)  # soft delete
```

### Add New Service

1. Create service in `src/services/<name>_service.py`
2. Add to dependency injection container (if using DI)
3. Create service tests in `tests/services/test_<name>_service.py`

```python
# Service template
class ResourceService:
    def __init__(self, repo: ResourceRepository, event_bus: EventBus):
        self.repo = repo
        self.event_bus = event_bus

    async def create(self, input: CreateResourceInput) -> ResourceOutput:
        # validation, business logic
        resource = await self.repo.create(Resource(**input.dict()))
        await self.event_bus.publish(ResourceCreated(resource_id=resource.id))
        return ResourceOutput.from_orm(resource)
```

### Add Background Job

1. Create task in `src/tasks/<name>.py`
2. Register in task configuration
3. Add tests in `tests/tasks/test_<name>.py`

```python
# Celery task template
@celery_app.task(bind=True, max_retries=3)
def process_resource(self, resource_id: str):
    try:
        # task logic
    except Exception as exc:
        self.retry(exc=exc, countdown=60)
```

---

## 6) Known Gotchas

> Mismatches between expected and actual patterns.

| Area | Gotcha | Workaround |
|------|--------|------------|
| `<area>` | `<unexpected behavior>` | `<how to handle>` |

**Examples:**
- Some older endpoints don't use the standard response envelope
- Legacy user model has `is_active` instead of `deleted_at`
- V1 routes don't require authentication (deprecated)

---

## 7) Exceptions (Allowlist)

> Documented deviations from standard patterns.

| File/Area | Exception | Reason | Standard Pattern |
|-----------|-----------|--------|------------------|
| `<path>` | `<what deviates>` | `<why>` | `<normal approach>` |

---

## 8) Quick Reference Commands

```bash
# Run tests
pytest tests/ -v

# Run single test file
pytest tests/test_users.py -v

# Run with coverage
pytest --cov=src tests/

# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1

# Start dev server
uvicorn src.main:app --reload

# Check types (if using mypy)
mypy src/

# Lint
ruff check src/
```
