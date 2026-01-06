# Service Layer Patterns

> Standard patterns for business logic organization, dependency injection, and service architecture.

## Table of Contents

- [Service Layer Overview](#service-layer-overview)
- [Service Structure](#service-structure)
- [Dependency Injection](#dependency-injection)
- [Transaction Management](#transaction-management)
- [Error Handling](#error-handling)
- [Event Patterns](#event-patterns)
- [Background Jobs](#background-jobs)
- [Testing Services](#testing-services)

---

## Service Layer Overview

### Layer Architecture

```
┌─────────────────────────────────────────────┐
│  Controller / Route Handler                 │  ← HTTP request/response
├─────────────────────────────────────────────┤
│  Service Layer                              │  ← Business logic
├─────────────────────────────────────────────┤
│  Repository / Data Access                   │  ← Database operations
├─────────────────────────────────────────────┤
│  Database                                   │
└─────────────────────────────────────────────┘
```

### Responsibilities

| Layer | Responsibilities |
|-------|------------------|
| Controller | Parse request, validate input, call service, format response |
| Service | Business logic, orchestration, authorization |
| Repository | Data access, queries, transactions |

---

## Service Structure

### Basic Service Class

```python
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

@dataclass
class CreateUserInput:
    email: str
    password: str
    name: Optional[str] = None

@dataclass
class UserOutput:
    id: str
    email: str
    name: Optional[str]
    created_at: datetime

class UserService:
    def __init__(
        self,
        user_repo: UserRepository,
        email_service: EmailService,
        password_hasher: PasswordHasher,
    ):
        self.user_repo = user_repo
        self.email_service = email_service
        self.password_hasher = password_hasher

    async def create_user(self, input: CreateUserInput) -> UserOutput:
        # Check for existing user
        existing = await self.user_repo.find_by_email(input.email)
        if existing:
            raise DuplicateResourceError("email", input.email)

        # Hash password
        password_hash = self.password_hasher.hash(input.password)

        # Create user
        user = User(
            email=input.email,
            password_hash=password_hash,
            name=input.name,
        )
        user = await self.user_repo.create(user)

        # Send welcome email (fire and forget)
        await self.email_service.send_welcome(user.email, user.name)

        return UserOutput(
            id=str(user.id),
            email=user.email,
            name=user.name,
            created_at=user.created_at,
        )

    async def get_user(self, user_id: str) -> UserOutput:
        user = await self.user_repo.find_by_id(user_id)
        if not user:
            raise ResourceNotFoundError("user", user_id)

        return UserOutput(
            id=str(user.id),
            email=user.email,
            name=user.name,
            created_at=user.created_at,
        )
```

### Service Method Patterns

```python
class OrderService:
    # Create - returns created entity
    async def create_order(self, input: CreateOrderInput) -> OrderOutput:
        ...

    # Read single - returns entity or raises NotFound
    async def get_order(self, order_id: str) -> OrderOutput:
        ...

    # Read list - returns list (empty if none)
    async def list_orders(
        self,
        user_id: str,
        filters: OrderFilters,
        pagination: Pagination,
    ) -> PaginatedResult[OrderOutput]:
        ...

    # Update - returns updated entity
    async def update_order(
        self,
        order_id: str,
        input: UpdateOrderInput,
    ) -> OrderOutput:
        ...

    # Delete - returns None or bool
    async def delete_order(self, order_id: str) -> None:
        ...

    # Action - verb-based method for non-CRUD operations
    async def cancel_order(self, order_id: str, reason: str) -> OrderOutput:
        ...

    async def refund_order(self, order_id: str, amount: Decimal) -> RefundOutput:
        ...
```

---

## Dependency Injection

### Container Setup (Python)

```python
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    # Configuration
    config = providers.Configuration()

    # Database
    db_session = providers.Singleton(
        create_session_factory,
        url=config.database.url,
    )

    # Repositories
    user_repo = providers.Factory(
        UserRepository,
        session=db_session,
    )

    order_repo = providers.Factory(
        OrderRepository,
        session=db_session,
    )

    # External services
    email_service = providers.Singleton(
        EmailService,
        api_key=config.email.api_key,
    )

    password_hasher = providers.Singleton(
        PasswordHasher,
        rounds=config.security.bcrypt_rounds,
    )

    # Services
    user_service = providers.Factory(
        UserService,
        user_repo=user_repo,
        email_service=email_service,
        password_hasher=password_hasher,
    )

    order_service = providers.Factory(
        OrderService,
        order_repo=order_repo,
        user_repo=user_repo,
    )
```

### FastAPI Integration

```python
from fastapi import Depends, FastAPI
from dependency_injector.wiring import Provide, inject

app = FastAPI()
container = Container()
container.wire(modules=[__name__])

@app.post("/users")
@inject
async def create_user(
    input: CreateUserRequest,
    user_service: UserService = Depends(Provide[Container.user_service]),
):
    result = await user_service.create_user(
        CreateUserInput(
            email=input.email,
            password=input.password,
            name=input.name,
        )
    )
    return {"data": result}
```

### Manual DI (Simple)

```python
# dependencies.py
def get_db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def get_user_repo(session: Session = Depends(get_db_session)):
    return UserRepository(session)

def get_user_service(
    user_repo: UserRepository = Depends(get_user_repo),
    email_service: EmailService = Depends(get_email_service),
):
    return UserService(user_repo=user_repo, email_service=email_service)

# routes.py
@router.post("/users")
async def create_user(
    input: CreateUserRequest,
    user_service: UserService = Depends(get_user_service),
):
    ...
```

---

## Transaction Management

### Unit of Work Pattern

```python
class UnitOfWork:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def __aenter__(self):
        self.session = self.session_factory()
        self.users = UserRepository(self.session)
        self.orders = OrderRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.session.rollback()
        await self.session.close()

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()

# Usage in service
class OrderService:
    def __init__(self, uow_factory):
        self.uow_factory = uow_factory

    async def create_order_with_items(
        self,
        user_id: str,
        items: list[OrderItemInput],
    ) -> OrderOutput:
        async with self.uow_factory() as uow:
            # All operations in same transaction
            user = await uow.users.find_by_id(user_id)
            if not user:
                raise ResourceNotFoundError("user", user_id)

            order = Order(user_id=user_id, status="pending")
            order = await uow.orders.create(order)

            for item in items:
                order_item = OrderItem(order_id=order.id, **item.dict())
                await uow.orders.create_item(order_item)

            await uow.commit()
            return self._to_output(order)
```

### Decorator Pattern

```python
from functools import wraps

def transactional(func):
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        async with self.session.begin():
            return await func(self, *args, **kwargs)
    return wrapper

class UserService:
    @transactional
    async def transfer_credits(
        self,
        from_user_id: str,
        to_user_id: str,
        amount: Decimal,
    ):
        # Both operations in same transaction
        await self.user_repo.deduct_credits(from_user_id, amount)
        await self.user_repo.add_credits(to_user_id, amount)
```

---

## Error Handling

### Service Exceptions

```python
class ServiceError(Exception):
    """Base exception for service layer errors."""
    pass

class ResourceNotFoundError(ServiceError):
    def __init__(self, resource_type: str, resource_id: str):
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(f"{resource_type} not found: {resource_id}")

class DuplicateResourceError(ServiceError):
    def __init__(self, field: str, value: str):
        self.field = field
        self.value = value
        super().__init__(f"Duplicate {field}: {value}")

class ValidationError(ServiceError):
    def __init__(self, errors: list[dict]):
        self.errors = errors
        super().__init__("Validation failed")

class BusinessRuleError(ServiceError):
    def __init__(self, code: str, message: str, details: dict = None):
        self.code = code
        self.details = details or {}
        super().__init__(message)

# Usage
raise BusinessRuleError(
    code="INSUFFICIENT_BALANCE",
    message="Insufficient balance for transfer",
    details={"required": 100, "available": 50}
)
```

### Exception Handler (Controller)

```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(ResourceNotFoundError)
async def handle_not_found(request: Request, exc: ResourceNotFoundError):
    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "error": {
                "code": "RESOURCE_NOT_FOUND",
                "message": str(exc),
                "details": {
                    "resource_type": exc.resource_type,
                    "id": exc.resource_id,
                }
            }
        }
    )

@app.exception_handler(BusinessRuleError)
async def handle_business_error(request: Request, exc: BusinessRuleError):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": str(exc),
                "details": exc.details,
            }
        }
    )
```

---

## Event Patterns

### Domain Events

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

@dataclass
class DomainEvent:
    occurred_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class UserCreated(DomainEvent):
    user_id: str
    email: str

@dataclass
class OrderCompleted(DomainEvent):
    order_id: str
    user_id: str
    total_amount: Decimal

class EventHandler(Protocol):
    async def handle(self, event: DomainEvent) -> None:
        ...

class EventBus:
    def __init__(self):
        self._handlers: dict[type, list[EventHandler]] = {}

    def subscribe(self, event_type: type, handler: EventHandler):
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent):
        handlers = self._handlers.get(type(event), [])
        for handler in handlers:
            await handler.handle(event)
```

### Event Handlers

```python
class SendWelcomeEmailHandler:
    def __init__(self, email_service: EmailService):
        self.email_service = email_service

    async def handle(self, event: UserCreated):
        await self.email_service.send_welcome(event.email)

class UpdateAnalyticsHandler:
    def __init__(self, analytics: AnalyticsService):
        self.analytics = analytics

    async def handle(self, event: OrderCompleted):
        await self.analytics.track_order(event.order_id, event.total_amount)

# Registration
event_bus = EventBus()
event_bus.subscribe(UserCreated, SendWelcomeEmailHandler(email_service))
event_bus.subscribe(OrderCompleted, UpdateAnalyticsHandler(analytics))

# Publishing in service
class UserService:
    def __init__(self, user_repo, event_bus):
        self.user_repo = user_repo
        self.event_bus = event_bus

    async def create_user(self, input: CreateUserInput) -> UserOutput:
        user = await self.user_repo.create(User(**input.dict()))

        await self.event_bus.publish(UserCreated(
            user_id=str(user.id),
            email=user.email,
        ))

        return self._to_output(user)
```

---

## Background Jobs

### Job Queue Pattern

```python
from enum import Enum
from dataclasses import dataclass

class JobPriority(Enum):
    LOW = 1
    NORMAL = 5
    HIGH = 10

@dataclass
class Job:
    name: str
    payload: dict
    priority: JobPriority = JobPriority.NORMAL
    max_retries: int = 3
    retry_delay: int = 60  # seconds

class JobQueue(Protocol):
    async def enqueue(self, job: Job) -> str:
        """Enqueue job, return job ID."""
        ...

    async def process(self, handler: Callable[[Job], Awaitable[None]]) -> None:
        """Process jobs from queue."""
        ...

# Service usage
class OrderService:
    def __init__(self, order_repo, job_queue: JobQueue):
        self.order_repo = order_repo
        self.job_queue = job_queue

    async def create_order(self, input: CreateOrderInput) -> OrderOutput:
        order = await self.order_repo.create(Order(**input.dict()))

        # Enqueue background jobs
        await self.job_queue.enqueue(Job(
            name="send_order_confirmation",
            payload={"order_id": str(order.id)},
        ))

        await self.job_queue.enqueue(Job(
            name="notify_warehouse",
            payload={"order_id": str(order.id)},
            priority=JobPriority.HIGH,
        ))

        return self._to_output(order)
```

### Scheduled Tasks

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('cron', hour=0, minute=0)
async def daily_cleanup():
    """Run daily at midnight."""
    async with uow_factory() as uow:
        await uow.sessions.delete_expired()
        await uow.commit()

@scheduler.scheduled_job('interval', minutes=5)
async def process_pending_webhooks():
    """Run every 5 minutes."""
    webhooks = await webhook_repo.find_pending()
    for webhook in webhooks:
        await webhook_service.deliver(webhook)

scheduler.start()
```

---

## Testing Services

### Unit Test Structure

```python
import pytest
from unittest.mock import AsyncMock, Mock

@pytest.fixture
def user_repo():
    return AsyncMock(spec=UserRepository)

@pytest.fixture
def email_service():
    return AsyncMock(spec=EmailService)

@pytest.fixture
def user_service(user_repo, email_service):
    return UserService(
        user_repo=user_repo,
        email_service=email_service,
        password_hasher=Mock(spec=PasswordHasher),
    )

class TestUserService:
    async def test_create_user_success(self, user_service, user_repo, email_service):
        # Arrange
        user_repo.find_by_email.return_value = None
        user_repo.create.return_value = User(
            id=uuid4(),
            email="test@example.com",
            name="Test User",
            created_at=datetime.utcnow(),
        )

        # Act
        result = await user_service.create_user(CreateUserInput(
            email="test@example.com",
            password="password123",
            name="Test User",
        ))

        # Assert
        assert result.email == "test@example.com"
        user_repo.create.assert_called_once()
        email_service.send_welcome.assert_called_once()

    async def test_create_user_duplicate_email(self, user_service, user_repo):
        # Arrange
        user_repo.find_by_email.return_value = User(id=uuid4(), email="test@example.com")

        # Act & Assert
        with pytest.raises(DuplicateResourceError) as exc:
            await user_service.create_user(CreateUserInput(
                email="test@example.com",
                password="password123",
            ))

        assert exc.value.field == "email"

    async def test_get_user_not_found(self, user_service, user_repo):
        # Arrange
        user_repo.find_by_id.return_value = None

        # Act & Assert
        with pytest.raises(ResourceNotFoundError) as exc:
            await user_service.get_user("nonexistent-id")

        assert exc.value.resource_type == "user"
```

### Integration Test

```python
@pytest.fixture
async def db_session(test_database):
    async with test_database.session() as session:
        yield session
        await session.rollback()

@pytest.fixture
def user_service(db_session):
    return UserService(
        user_repo=UserRepository(db_session),
        email_service=FakeEmailService(),  # Use fake for integration tests
        password_hasher=PasswordHasher(),
    )

class TestUserServiceIntegration:
    async def test_create_and_get_user(self, user_service):
        # Create user
        created = await user_service.create_user(CreateUserInput(
            email="integration@example.com",
            password="password123",
        ))

        # Retrieve user
        retrieved = await user_service.get_user(created.id)

        assert retrieved.email == "integration@example.com"
```
