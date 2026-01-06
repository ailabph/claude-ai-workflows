# Validation Patterns Reference

> Standard patterns for request validation, data serialization, and input sanitization.

## Table of Contents

- [Validation Strategy](#validation-strategy)
- [Request Validation](#request-validation)
- [Field Validators](#field-validators)
- [Custom Validators](#custom-validators)
- [Serialization Patterns](#serialization-patterns)
- [File Upload Validation](#file-upload-validation)
- [Sanitization](#sanitization)

---

## Validation Strategy

### Validation Layers

```
┌─────────────────────────────────────────────┐
│  1. Schema Validation (Request)             │  ← Type, format, required fields
├─────────────────────────────────────────────┤
│  2. Business Validation (Service)           │  ← Uniqueness, permissions, state
├─────────────────────────────────────────────┤
│  3. Database Constraints                    │  ← Final safety net
└─────────────────────────────────────────────┘
```

| Layer | Examples | Fails Fast |
|-------|----------|------------|
| Schema | Type errors, missing fields, format | Yes (400/422) |
| Business | Duplicate email, insufficient balance | No (422) |
| Database | Unique constraint, FK violation | No (500 → 409/422) |

---

## Request Validation

### Pydantic Models (Python)

```python
from pydantic import BaseModel, Field, EmailStr, validator
from typing import Optional
from datetime import date
from decimal import Decimal

class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: Optional[str] = Field(None, max_length=100)
    birth_date: Optional[date] = None

    @validator("password")
    def password_complexity(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain digit")
        return v

    @validator("birth_date")
    def valid_birth_date(cls, v):
        if v and v > date.today():
            raise ValueError("Birth date cannot be in the future")
        return v

    class Config:
        # Strip whitespace from strings
        anystr_strip_whitespace = True
        # Example for docs
        schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123",
                "name": "John Doe",
            }
        }
```

### Request with Nested Objects

```python
class AddressRequest(BaseModel):
    street: str = Field(..., max_length=200)
    city: str = Field(..., max_length=100)
    postal_code: str = Field(..., pattern=r"^\d{5}(-\d{4})?$")
    country: str = Field(..., min_length=2, max_length=2)  # ISO 3166-1 alpha-2

class CreateOrderRequest(BaseModel):
    items: list[OrderItemRequest] = Field(..., min_items=1, max_items=100)
    shipping_address: AddressRequest
    billing_address: Optional[AddressRequest] = None
    notes: Optional[str] = Field(None, max_length=500)

    @validator("billing_address", always=True)
    def default_billing_address(cls, v, values):
        # Default billing to shipping if not provided
        return v or values.get("shipping_address")

class OrderItemRequest(BaseModel):
    product_id: str
    quantity: int = Field(..., ge=1, le=1000)
    price: Decimal = Field(..., ge=0, decimal_places=2)
```

### Query Parameter Validation

```python
from fastapi import Query
from enum import Enum

class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"

class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

@router.get("/orders")
async def list_orders(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[OrderStatus] = Query(None, description="Filter by status"),
    sort_by: str = Query("created_at", pattern=r"^[a-z_]+$"),
    sort_order: SortOrder = Query(SortOrder.DESC),
    created_after: Optional[date] = Query(None, description="Filter by creation date"),
):
    ...
```

---

## Field Validators

### Common Field Patterns

```python
from pydantic import Field, validator
import re

# Email
email: EmailStr

# Password
password: str = Field(..., min_length=8, max_length=128)

# Phone (E.164 format)
phone: str = Field(..., pattern=r"^\+[1-9]\d{1,14}$")

# URL
website: HttpUrl

# UUID
user_id: UUID4

# Slug
slug: str = Field(..., pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)

# Username
username: str = Field(..., pattern=r"^[a-zA-Z][a-zA-Z0-9_]{2,29}$")

# Currency amount
amount: Decimal = Field(..., ge=0, decimal_places=2, max_digits=12)

# Percentage
percentage: float = Field(..., ge=0, le=100)

# Date range
start_date: date
end_date: date

@validator("end_date")
def end_after_start(cls, v, values):
    if "start_date" in values and v < values["start_date"]:
        raise ValueError("end_date must be after start_date")
    return v
```

### Enum Validation

```python
from enum import Enum

class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"

class PaymentMethod(str, Enum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    BANK_TRANSFER = "bank_transfer"
    CRYPTO = "crypto"

class CreateUserRequest(BaseModel):
    role: UserRole = UserRole.USER
    preferred_payment: Optional[PaymentMethod] = None
```

### Conditional Validation

```python
from pydantic import root_validator

class PaymentRequest(BaseModel):
    method: PaymentMethod
    card_number: Optional[str] = None
    card_expiry: Optional[str] = None
    bank_account: Optional[str] = None

    @root_validator
    def validate_payment_details(cls, values):
        method = values.get("method")

        if method in [PaymentMethod.CREDIT_CARD, PaymentMethod.DEBIT_CARD]:
            if not values.get("card_number"):
                raise ValueError("card_number required for card payments")
            if not values.get("card_expiry"):
                raise ValueError("card_expiry required for card payments")

        elif method == PaymentMethod.BANK_TRANSFER:
            if not values.get("bank_account"):
                raise ValueError("bank_account required for bank transfers")

        return values
```

---

## Custom Validators

### Reusable Validators

```python
from pydantic import validator
from typing import TypeVar, Callable

T = TypeVar("T")

def not_empty_string(field_name: str) -> Callable:
    """Validate string is not empty or whitespace-only."""
    @validator(field_name, pre=True)
    def validate(cls, v):
        if isinstance(v, str) and not v.strip():
            raise ValueError(f"{field_name} cannot be empty")
        return v.strip() if isinstance(v, str) else v
    return validate

def valid_json(field_name: str) -> Callable:
    """Validate string is valid JSON."""
    import json

    @validator(field_name)
    def validate(cls, v):
        if v is not None:
            try:
                json.loads(v)
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON")
        return v
    return validate

# Usage
class ConfigRequest(BaseModel):
    name: str
    settings: str  # JSON string

    _validate_name = not_empty_string("name")
    _validate_settings = valid_json("settings")
```

### Async Validation (Business Layer)

```python
class UserValidator:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def validate_create(self, input: CreateUserInput) -> list[ValidationError]:
        errors = []

        # Check email uniqueness
        existing = await self.user_repo.find_by_email(input.email)
        if existing:
            errors.append(ValidationError(
                field="email",
                code="NOT_UNIQUE",
                message="Email already registered",
            ))

        # Check username uniqueness
        if input.username:
            existing = await self.user_repo.find_by_username(input.username)
            if existing:
                errors.append(ValidationError(
                    field="username",
                    code="NOT_UNIQUE",
                    message="Username already taken",
                ))

        return errors

# Usage in service
class UserService:
    async def create_user(self, input: CreateUserInput) -> UserOutput:
        errors = await self.validator.validate_create(input)
        if errors:
            raise ValidationException(errors)
        ...
```

---

## Serialization Patterns

### Response Models

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Generic, TypeVar, Optional

T = TypeVar("T")

class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str]
    created_at: datetime

    class Config:
        # Allow ORM objects
        orm_mode = True
        # Serialize datetime to ISO format
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    pagination: PaginationMeta

class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int

class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    meta: Optional[dict] = None
```

### Field Aliases & Transformation

```python
from pydantic import BaseModel, Field

class ExternalApiResponse(BaseModel):
    """Model for external API with different field names."""
    user_id: str = Field(..., alias="userId")
    full_name: str = Field(..., alias="fullName")
    email_address: str = Field(..., alias="emailAddress")

    class Config:
        # Allow both alias and field name
        allow_population_by_field_name = True

class InternalUser(BaseModel):
    """Transform external response to internal format."""
    id: str
    name: str
    email: str

    @classmethod
    def from_external(cls, external: ExternalApiResponse) -> "InternalUser":
        return cls(
            id=external.user_id,
            name=external.full_name,
            email=external.email_address,
        )
```

### Excluding Fields

```python
class UserResponse(BaseModel):
    id: str
    email: str
    password_hash: str = Field(..., exclude=True)  # Never serialize
    internal_notes: Optional[str] = None

# Or exclude at serialization time
user.dict(exclude={"password_hash", "internal_notes"})
user.dict(include={"id", "email"})
```

---

## File Upload Validation

### File Validation

```python
from fastapi import UploadFile, HTTPException

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

async def validate_image_upload(file: UploadFile) -> UploadFile:
    # Check content type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_FILE_TYPE",
                "message": f"File type {file.content_type} not allowed",
                "details": {"allowed": list(ALLOWED_IMAGE_TYPES)},
            }
        )

    # Check file size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "FILE_TOO_LARGE",
                "message": f"File exceeds maximum size",
                "details": {"max_size_bytes": MAX_FILE_SIZE},
            }
        )

    # Reset file position for later use
    await file.seek(0)
    return file

# Usage
@router.post("/upload/avatar")
async def upload_avatar(
    file: UploadFile = Depends(validate_image_upload),
):
    ...
```

### Magic Number Validation

```python
import magic

MAGIC_NUMBERS = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/gif": [b"GIF87a", b"GIF89a"],
    "application/pdf": [b"%PDF"],
}

async def validate_file_magic(file: UploadFile, expected_type: str) -> bool:
    """Validate file content matches claimed type."""
    header = await file.read(8)
    await file.seek(0)

    expected_magic = MAGIC_NUMBERS.get(expected_type, [])
    return any(header.startswith(m) for m in expected_magic)
```

---

## Sanitization

### String Sanitization

```python
import re
import html
from typing import Optional

def sanitize_string(value: str, max_length: int = 1000) -> str:
    """Basic string sanitization."""
    # Strip whitespace
    value = value.strip()

    # Normalize whitespace
    value = re.sub(r"\s+", " ", value)

    # Truncate
    if len(value) > max_length:
        value = value[:max_length]

    return value

def sanitize_html(value: str) -> str:
    """Escape HTML entities."""
    return html.escape(value)

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage."""
    # Remove path components
    filename = filename.split("/")[-1].split("\\")[-1]

    # Remove special characters
    filename = re.sub(r"[^\w\-_\.]", "_", filename)

    # Limit length
    name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
    name = name[:200]

    return f"{name}.{ext}" if ext else name

def sanitize_slug(value: str) -> str:
    """Convert string to URL-safe slug."""
    import unicodedata

    # Normalize unicode
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")

    # Convert to lowercase
    value = value.lower()

    # Replace spaces and special chars with hyphens
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[-\s]+", "-", value)

    # Remove leading/trailing hyphens
    return value.strip("-")
```

### SQL Injection Prevention

```python
# NEVER do this
query = f"SELECT * FROM users WHERE email = '{email}'"  # DANGEROUS

# ALWAYS use parameterized queries
# SQLAlchemy
session.execute(
    text("SELECT * FROM users WHERE email = :email"),
    {"email": email}
)

# Raw psycopg2
cursor.execute(
    "SELECT * FROM users WHERE email = %s",
    (email,)
)

# ORM (safest)
session.query(User).filter(User.email == email).first()
```

### XSS Prevention

```python
# For HTML output
from markupsafe import escape

def render_user_content(content: str) -> str:
    """Safely render user-provided content."""
    return escape(content)

# For JSON API responses, ensure proper Content-Type
from fastapi.responses import JSONResponse

@router.get("/user")
async def get_user():
    return JSONResponse(
        content={"name": user.name},
        headers={"Content-Type": "application/json"},
    )
```

---

## Validation Error Response

### Consistent Error Format

```python
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"][1:])  # Skip 'body'
        errors.append({
            "field": field,
            "code": error["type"].upper().replace(".", "_"),
            "message": error["msg"],
        })

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request data",
                "details": errors,
            }
        }
    )
```

### Example Error Response

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request data",
    "details": [
      {
        "field": "email",
        "code": "VALUE_ERROR",
        "message": "value is not a valid email address"
      },
      {
        "field": "password",
        "code": "VALUE_ERROR",
        "message": "ensure this value has at least 8 characters"
      },
      {
        "field": "items.0.quantity",
        "code": "VALUE_ERROR",
        "message": "ensure this value is greater than or equal to 1"
      }
    ]
  }
}
```
