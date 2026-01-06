# Error Codes Reference

> Standard error codes, HTTP status mappings, and error response formats.

## Table of Contents

- [Error Response Structure](#error-response-structure)
- [HTTP Status Codes](#http-status-codes)
- [Application Error Codes](#application-error-codes)
- [Validation Errors](#validation-errors)
- [Framework Examples](#framework-examples)

---

## Error Response Structure

All errors follow this consistent format:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": { }
  },
  "meta": {
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req_abc123"
  }
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | string | Yes | Machine-readable error code (UPPER_SNAKE_CASE) |
| `message` | string | Yes | Human-readable description |
| `details` | object/array | No | Additional context (field errors, constraints, etc.) |

---

## HTTP Status Codes

### Client Errors (4xx)

| Code | Name | When to Use |
|------|------|-------------|
| `400` | Bad Request | Malformed request syntax, invalid JSON |
| `401` | Unauthorized | Missing or invalid authentication |
| `403` | Forbidden | Valid auth but insufficient permissions |
| `404` | Not Found | Resource doesn't exist |
| `405` | Method Not Allowed | HTTP method not supported for endpoint |
| `409` | Conflict | Resource state conflict (duplicate, version mismatch) |
| `422` | Unprocessable Entity | Valid syntax but semantic validation failed |
| `429` | Too Many Requests | Rate limit exceeded |

### Server Errors (5xx)

| Code | Name | When to Use |
|------|------|-------------|
| `500` | Internal Server Error | Unexpected server error |
| `502` | Bad Gateway | Upstream service failure |
| `503` | Service Unavailable | Maintenance or overload |
| `504` | Gateway Timeout | Upstream service timeout |

---

## Application Error Codes

### Authentication Errors (401)

| Code | Message | Details |
|------|---------|---------|
| `AUTH_TOKEN_MISSING` | Authentication required | - |
| `AUTH_TOKEN_INVALID` | Invalid authentication token | - |
| `AUTH_TOKEN_EXPIRED` | Authentication token has expired | `{ "expired_at": "..." }` |
| `AUTH_TOKEN_REVOKED` | Authentication token has been revoked | - |

### Authorization Errors (403)

| Code | Message | Details |
|------|---------|---------|
| `FORBIDDEN` | Access denied | - |
| `PERMISSION_DENIED` | Insufficient permissions | `{ "required": "admin", "current": "user" }` |
| `RESOURCE_ACCESS_DENIED` | Cannot access this resource | `{ "resource_id": "..." }` |
| `ACCOUNT_SUSPENDED` | Account has been suspended | `{ "reason": "...", "suspended_at": "..." }` |

### Resource Errors (404)

| Code | Message | Details |
|------|---------|---------|
| `RESOURCE_NOT_FOUND` | Resource not found | `{ "resource_type": "user", "id": "..." }` |
| `ENDPOINT_NOT_FOUND` | Endpoint does not exist | - |

### Validation Errors (422)

| Code | Message | Details |
|------|---------|---------|
| `VALIDATION_ERROR` | Invalid request data | `[{ "field": "...", "message": "..." }]` |
| `INVALID_FORMAT` | Invalid data format | `{ "field": "...", "expected": "..." }` |
| `MISSING_REQUIRED_FIELD` | Required field missing | `{ "field": "..." }` |
| `INVALID_ENUM_VALUE` | Invalid enum value | `{ "field": "...", "allowed": [...] }` |

### Conflict Errors (409)

| Code | Message | Details |
|------|---------|---------|
| `DUPLICATE_RESOURCE` | Resource already exists | `{ "field": "email", "value": "..." }` |
| `VERSION_CONFLICT` | Resource was modified | `{ "current_version": 5, "your_version": 3 }` |
| `STATE_CONFLICT` | Invalid state transition | `{ "current": "completed", "attempted": "pending" }` |

### Business Logic Errors (422)

| Code | Message | Details |
|------|---------|---------|
| `INSUFFICIENT_BALANCE` | Insufficient balance | `{ "required": 100, "available": 50 }` |
| `LIMIT_EXCEEDED` | Limit exceeded | `{ "limit": 10, "current": 10 }` |
| `OPERATION_NOT_ALLOWED` | Operation not allowed | `{ "reason": "..." }` |
| `EXPIRED` | Resource has expired | `{ "expired_at": "..." }` |

### Rate Limiting (429)

| Code | Message | Details |
|------|---------|---------|
| `RATE_LIMIT_EXCEEDED` | Too many requests | `{ "retry_after": 60, "limit": 1000 }` |

### Server Errors (5xx)

| Code | Message | Details |
|------|---------|---------|
| `INTERNAL_ERROR` | An unexpected error occurred | - |
| `SERVICE_UNAVAILABLE` | Service temporarily unavailable | `{ "retry_after": 300 }` |
| `UPSTREAM_ERROR` | External service error | `{ "service": "payment_provider" }` |
| `DATABASE_ERROR` | Database operation failed | - |

---

## Validation Errors

### Field-Level Errors

Return an array of field errors for 422 responses:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request data",
    "details": [
      {
        "field": "email",
        "code": "INVALID_FORMAT",
        "message": "Invalid email format"
      },
      {
        "field": "password",
        "code": "TOO_SHORT",
        "message": "Password must be at least 8 characters",
        "constraints": { "min_length": 8 }
      },
      {
        "field": "age",
        "code": "OUT_OF_RANGE",
        "message": "Age must be between 18 and 120",
        "constraints": { "min": 18, "max": 120 }
      }
    ]
  }
}
```

### Common Field Validation Codes

| Code | Description | Constraints |
|------|-------------|-------------|
| `REQUIRED` | Field is required | - |
| `INVALID_FORMAT` | Format doesn't match expected pattern | `{ "pattern": "..." }` |
| `INVALID_TYPE` | Wrong data type | `{ "expected": "string" }` |
| `TOO_SHORT` | Below minimum length | `{ "min_length": N }` |
| `TOO_LONG` | Exceeds maximum length | `{ "max_length": N }` |
| `TOO_SMALL` | Below minimum value | `{ "min": N }` |
| `TOO_LARGE` | Exceeds maximum value | `{ "max": N }` |
| `OUT_OF_RANGE` | Outside allowed range | `{ "min": N, "max": N }` |
| `INVALID_CHOICE` | Not in allowed values | `{ "choices": [...] }` |
| `NOT_UNIQUE` | Value already exists | - |
| `INVALID_REFERENCE` | Referenced resource not found | `{ "resource_type": "..." }` |

---

## Framework Examples

### Python (FastAPI/Pydantic)

```python
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Optional, List, Any

class ErrorDetail(BaseModel):
    field: Optional[str] = None
    code: str
    message: str
    constraints: Optional[dict] = None

class ErrorResponse(BaseModel):
    code: str
    message: str
    details: Optional[List[ErrorDetail] | dict] = None

class APIException(HTTPException):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any = None
    ):
        super().__init__(
            status_code=status_code,
            detail={
                "code": code,
                "message": message,
                "details": details
            }
        )

# Usage
raise APIException(
    status_code=404,
    code="RESOURCE_NOT_FOUND",
    message="User not found",
    details={"resource_type": "user", "id": user_id}
)
```

### Python (Django REST Framework)

```python
from rest_framework.exceptions import APIException
from rest_framework import status

class ResourceNotFound(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "RESOURCE_NOT_FOUND"
    default_detail = "Resource not found"

    def __init__(self, resource_type: str, resource_id: str):
        detail = {
            "code": self.default_code,
            "message": self.default_detail,
            "details": {
                "resource_type": resource_type,
                "id": resource_id
            }
        }
        super().__init__(detail)

# Usage
raise ResourceNotFound("user", user_id)
```

### Node.js (Express)

```typescript
class APIError extends Error {
  constructor(
    public statusCode: number,
    public code: string,
    public message: string,
    public details?: Record<string, any>
  ) {
    super(message);
  }

  toJSON() {
    return {
      success: false,
      error: {
        code: this.code,
        message: this.message,
        details: this.details,
      },
    };
  }
}

// Usage
throw new APIError(
  404,
  "RESOURCE_NOT_FOUND",
  "User not found",
  { resource_type: "user", id: userId }
);

// Error handler middleware
app.use((err, req, res, next) => {
  if (err instanceof APIError) {
    return res.status(err.statusCode).json(err.toJSON());
  }
  // Handle unexpected errors
  res.status(500).json({
    success: false,
    error: {
      code: "INTERNAL_ERROR",
      message: "An unexpected error occurred",
    },
  });
});
```

---

## Error Logging

### What to Log (Server-Side)

| Level | When | Include |
|-------|------|---------|
| `ERROR` | 5xx errors | Full stack trace, request context |
| `WARN` | 4xx errors (except 404) | Request context, user ID |
| `INFO` | 404 errors | Request path only |

### What NOT to Include in Responses

- Stack traces (production)
- Database query details
- Internal service names
- File paths
- Sensitive data (passwords, tokens, PII)

### Request Context for Debugging

Always include `request_id` in responses for log correlation:

```json
{
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```
