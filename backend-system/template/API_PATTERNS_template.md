# API Patterns Reference

> Standard patterns for API design, request/response conventions, and endpoint structure.

## Table of Contents

- [Response Envelope](#response-envelope)
- [Pagination](#pagination)
- [Filtering & Sorting](#filtering--sorting)
- [HTTP Methods](#http-methods)
- [URL Conventions](#url-conventions)
- [Versioning](#versioning)
- [Rate Limiting Headers](#rate-limiting-headers)

---

## Response Envelope

All API responses follow a consistent envelope structure.

### Success Response

```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req_abc123"
  }
}
```

### Success Response (List)

```json
{
  "success": true,
  "data": [ ... ],
  "meta": {
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req_abc123"
  },
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_items": 150,
    "total_pages": 8
  }
}
```

### Error Response

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request data",
    "details": [
      { "field": "email", "message": "Invalid email format" }
    ]
  },
  "meta": {
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req_abc123"
  }
}
```

---

## Pagination

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number (1-indexed) |
| `page_size` | int | 20 | Items per page (max: 100) |

### Example Request

```
GET /api/v1/users?page=2&page_size=25
```

### Cursor-Based Pagination (Alternative)

For large datasets or real-time data:

| Parameter | Type | Description |
|-----------|------|-------------|
| `cursor` | string | Opaque cursor from previous response |
| `limit` | int | Items to return (max: 100) |

```json
{
  "data": [ ... ],
  "pagination": {
    "next_cursor": "eyJpZCI6MTAwfQ==",
    "has_more": true
  }
}
```

---

## Filtering & Sorting

### Filter Parameters

Filters use field-based query parameters:

```
GET /api/v1/orders?status=completed&created_after=2024-01-01
```

### Common Filter Patterns

| Pattern | Example | Description |
|---------|---------|-------------|
| Exact match | `?status=active` | Field equals value |
| Multiple values | `?status=active,pending` | Field in list |
| Range (after) | `?created_after=2024-01-01` | Greater than or equal |
| Range (before) | `?created_before=2024-12-31` | Less than or equal |
| Search | `?q=search+term` | Full-text search |

### Sorting

```
GET /api/v1/users?sort=created_at&order=desc
GET /api/v1/users?sort=-created_at  # Alternative: prefix with - for desc
```

| Parameter | Values | Default |
|-----------|--------|---------|
| `sort` | Field name | `created_at` |
| `order` | `asc`, `desc` | `desc` |

---

## HTTP Methods

| Method | Usage | Idempotent | Request Body |
|--------|-------|------------|--------------|
| `GET` | Retrieve resource(s) | Yes | No |
| `POST` | Create resource | No | Yes |
| `PUT` | Replace resource entirely | Yes | Yes |
| `PATCH` | Partial update | Yes | Yes |
| `DELETE` | Remove resource | Yes | No |

### Response Codes by Method

| Method | Success | Created | No Content |
|--------|---------|---------|------------|
| `GET` | 200 | - | - |
| `POST` | - | 201 | - |
| `PUT` | 200 | - | - |
| `PATCH` | 200 | - | - |
| `DELETE` | - | - | 204 |

---

## URL Conventions

### Resource Naming

- Use **plural nouns** for collections: `/users`, `/orders`, `/products`
- Use **kebab-case** for multi-word resources: `/order-items`, `/user-profiles`
- Nest resources for relationships: `/users/{id}/orders`

### Examples

```
# Collections
GET    /api/v1/users              # List users
POST   /api/v1/users              # Create user

# Single resource
GET    /api/v1/users/{id}         # Get user
PUT    /api/v1/users/{id}         # Replace user
PATCH  /api/v1/users/{id}         # Update user
DELETE /api/v1/users/{id}         # Delete user

# Nested resources
GET    /api/v1/users/{id}/orders  # User's orders

# Actions (when CRUD doesn't fit)
POST   /api/v1/orders/{id}/cancel
POST   /api/v1/users/{id}/verify-email
```

### ID Formats

| Type | Format | Example |
|------|--------|---------|
| UUID | `uuid4` | `550e8400-e29b-41d4-a716-446655440000` |
| Prefixed | `{type}_{nanoid}` | `usr_abc123`, `ord_xyz789` |
| Integer | Sequential | `12345` |

---

## Versioning

### URL Path Versioning (Recommended)

```
/api/v1/users
/api/v2/users
```

### Header Versioning (Alternative)

```
GET /api/users
Accept: application/vnd.api+json; version=1
```

### Deprecation Headers

When deprecating an endpoint version:

```
Deprecation: true
Sunset: Sat, 01 Jan 2025 00:00:00 GMT
Link: </api/v2/users>; rel="successor-version"
```

---

## Rate Limiting Headers

Include in all responses:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1705312200
```

### 429 Response

```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests",
    "details": {
      "retry_after": 60
    }
  }
}
```

```
Retry-After: 60
```

---

## Request Headers

### Required Headers

| Header | Value | Description |
|--------|-------|-------------|
| `Content-Type` | `application/json` | Request body format |
| `Accept` | `application/json` | Expected response format |

### Optional Headers

| Header | Description |
|--------|-------------|
| `Authorization` | Bearer token or API key |
| `X-Request-ID` | Client-generated request ID for tracing |
| `X-Idempotency-Key` | Prevent duplicate operations (POST/PATCH) |

---

## HATEOAS Links (Optional)

For discoverability, include related links:

```json
{
  "data": {
    "id": "usr_abc123",
    "email": "user@example.com"
  },
  "links": {
    "self": "/api/v1/users/usr_abc123",
    "orders": "/api/v1/users/usr_abc123/orders",
    "profile": "/api/v1/users/usr_abc123/profile"
  }
}
```
