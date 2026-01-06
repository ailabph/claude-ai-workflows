# Authentication & Authorization Patterns

> Standard patterns for authentication, authorization, and access control.

## Table of Contents

- [Authentication Methods](#authentication-methods)
- [JWT Patterns](#jwt-patterns)
- [Session Patterns](#session-patterns)
- [API Key Patterns](#api-key-patterns)
- [Authorization Patterns](#authorization-patterns)
- [Permission Models](#permission-models)
- [Security Headers](#security-headers)

---

## Authentication Methods

### Method Comparison

| Method | Use Case | Stateless | Revocable |
|--------|----------|-----------|-----------|
| JWT | API, SPA, Mobile | Yes | With blacklist |
| Session | Web apps, SSR | No | Yes |
| API Key | Service-to-service, SDKs | Yes | Yes |
| OAuth 2.0 | Third-party access | Yes | Yes |

### Header Format

```
Authorization: Bearer <token>
Authorization: ApiKey <key>
```

---

## JWT Patterns

### Token Structure

```json
// Header
{
  "alg": "RS256",
  "typ": "JWT"
}

// Payload
{
  "sub": "usr_abc123",
  "iat": 1705312200,
  "exp": 1705315800,
  "iss": "https://api.example.com",
  "aud": "https://api.example.com",
  "type": "access",
  "roles": ["user"],
  "permissions": ["read:profile", "write:profile"]
}
```

### Token Types

| Type | Lifetime | Storage | Purpose |
|------|----------|---------|---------|
| Access Token | 15-60 min | Memory | API requests |
| Refresh Token | 7-30 days | HttpOnly cookie / secure storage | Get new access token |
| ID Token | 15-60 min | Memory | User info (OpenID Connect) |

### Refresh Token Flow

```
1. Client sends expired access token
2. Server returns 401 AUTH_TOKEN_EXPIRED
3. Client sends refresh token to /auth/refresh
4. Server validates refresh token
5. Server issues new access + refresh tokens
6. Server invalidates old refresh token (rotation)
```

### Token Refresh Endpoint

```
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "..."
}

Response 200:
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_in": 3600
}
```

### JWT Validation Checklist

1. Verify signature (use public key for RS256)
2. Check `exp` claim (not expired)
3. Check `iat` claim (not issued in future)
4. Check `iss` claim (expected issuer)
5. Check `aud` claim (expected audience)
6. Check `type` claim (access vs refresh)
7. Check token not in blacklist (if revocable)

### Framework Example (Python)

```python
from datetime import datetime, timedelta
from jose import jwt, JWTError

SECRET_KEY = "your-secret-key"  # Use RS256 in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_access_token(user_id: str, roles: list[str]) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
        "roles": roles,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise ValueError("Invalid token type")
        return payload
    except JWTError:
        raise ValueError("Invalid token")
```

---

## Session Patterns

### Session Storage Options

| Storage | Pros | Cons |
|---------|------|------|
| Redis | Fast, TTL support, scalable | Additional infrastructure |
| Database | Persistent, queryable | Slower, cleanup needed |
| Memory | Simple | Lost on restart, not scalable |

### Session Data Structure

```json
{
  "session_id": "sess_abc123",
  "user_id": "usr_xyz789",
  "created_at": "2024-01-15T10:00:00Z",
  "expires_at": "2024-01-15T22:00:00Z",
  "last_active": "2024-01-15T10:30:00Z",
  "ip_address": "192.168.1.1",
  "user_agent": "Mozilla/5.0...",
  "data": {}
}
```

### Session Cookie Settings

```python
response.set_cookie(
    key="session_id",
    value=session_id,
    httponly=True,      # Not accessible via JavaScript
    secure=True,        # HTTPS only
    samesite="lax",     # CSRF protection
    max_age=86400,      # 24 hours
    path="/",
    domain=".example.com"
)
```

---

## API Key Patterns

### Key Format

```
# Prefixed for easy identification
pk_live_abc123def456...  # Production
pk_test_xyz789ghi012...  # Test/sandbox

# Or with checksum
api_abc123_def456ghi789jkl012mno345
```

### Key Storage

```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY,
    key_hash VARCHAR(64) NOT NULL,      -- SHA-256 hash, never store plain
    key_prefix VARCHAR(12) NOT NULL,    -- For identification: "pk_live_abc"
    user_id UUID REFERENCES users(id),
    name VARCHAR(100),
    permissions TEXT[],
    rate_limit INTEGER DEFAULT 1000,
    last_used_at TIMESTAMP,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    revoked_at TIMESTAMP
);

CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);
```

### Key Validation Flow

```
1. Extract key from Authorization header
2. Extract prefix from key
3. Look up key by prefix
4. Hash incoming key
5. Compare hash with stored hash
6. Check not revoked and not expired
7. Update last_used_at
8. Return associated permissions
```

---

## Authorization Patterns

### Middleware/Decorator Pattern

```python
# Python example
from functools import wraps

def require_permissions(*required: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            user = request.state.user
            if not user:
                raise AuthenticationError()

            user_permissions = set(user.permissions)
            if not all(p in user_permissions for p in required):
                raise PermissionDenied(
                    required=list(required),
                    current=list(user_permissions)
                )

            return await func(request, *args, **kwargs)
        return wrapper
    return decorator

# Usage
@router.delete("/users/{user_id}")
@require_permissions("users:delete")
async def delete_user(user_id: str):
    ...
```

### Resource-Level Authorization

```python
async def authorize_resource(user: User, resource: Resource, action: str) -> bool:
    """
    Check if user can perform action on specific resource.
    """
    # Owner can do anything
    if resource.owner_id == user.id:
        return True

    # Check explicit permissions
    permission = f"{resource.type}:{action}"
    if permission in user.permissions:
        return True

    # Check role-based access
    if user.role == "admin":
        return True

    # Check resource-specific sharing
    share = await get_resource_share(resource.id, user.id)
    if share and action in share.allowed_actions:
        return True

    return False
```

---

## Permission Models

### Role-Based Access Control (RBAC)

```yaml
roles:
  admin:
    permissions:
      - "*"  # All permissions

  manager:
    permissions:
      - "users:read"
      - "users:write"
      - "orders:*"
      - "reports:read"

  user:
    permissions:
      - "profile:read"
      - "profile:write"
      - "orders:read"
      - "orders:create"
```

### Permission String Format

```
{resource}:{action}

# Examples
users:read
users:write
users:delete
orders:*          # All actions on orders
*:read            # Read any resource (use sparingly)
```

### Database Schema (RBAC)

```sql
CREATE TABLE roles (
    id UUID PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE permissions (
    id UUID PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,  -- e.g., "users:delete"
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE role_permissions (
    role_id UUID REFERENCES roles(id),
    permission_id UUID REFERENCES permissions(id),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE user_roles (
    user_id UUID REFERENCES users(id),
    role_id UUID REFERENCES roles(id),
    granted_at TIMESTAMP DEFAULT NOW(),
    granted_by UUID REFERENCES users(id),
    PRIMARY KEY (user_id, role_id)
);
```

### Attribute-Based Access Control (ABAC)

For complex policies:

```python
@dataclass
class AccessRequest:
    subject: User           # Who is requesting
    resource: Resource      # What they're accessing
    action: str             # What they want to do
    environment: dict       # Context (time, IP, etc.)

def evaluate_policy(request: AccessRequest) -> bool:
    """
    Example ABAC policy evaluation.
    """
    # Policy: Users can only edit their own resources during business hours
    if request.action == "edit":
        if request.resource.owner_id != request.subject.id:
            return False

        current_hour = datetime.now().hour
        if not (9 <= current_hour < 17):
            return False

    return True
```

---

## Security Headers

### Required Response Headers

```python
# Add to all responses
headers = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'",
    "Cache-Control": "no-store",  # For authenticated responses
    "Pragma": "no-cache",
}
```

### CORS Configuration

```python
# Development
CORS_ORIGINS = ["http://localhost:3000"]

# Production
CORS_ORIGINS = ["https://app.example.com"]

cors_config = {
    "allow_origins": CORS_ORIGINS,
    "allow_methods": ["GET", "POST", "PUT", "PATCH", "DELETE"],
    "allow_headers": ["Authorization", "Content-Type", "X-Request-ID"],
    "allow_credentials": True,
    "max_age": 600,  # Preflight cache time
}
```

---

## Authentication Endpoints

### Standard Auth Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/register` | POST | Create new account |
| `/auth/login` | POST | Authenticate, get tokens |
| `/auth/logout` | POST | Invalidate tokens |
| `/auth/refresh` | POST | Refresh access token |
| `/auth/forgot-password` | POST | Request password reset |
| `/auth/reset-password` | POST | Set new password |
| `/auth/verify-email` | POST | Verify email address |
| `/auth/me` | GET | Get current user info |

### Login Request/Response

```
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "..."
}

Response 200:
{
  "success": true,
  "data": {
    "user": {
      "id": "usr_abc123",
      "email": "user@example.com",
      "roles": ["user"]
    },
    "access_token": "...",
    "refresh_token": "...",
    "expires_in": 3600
  }
}
```

---

## Security Checklist

### Password Handling

- [ ] Hash with bcrypt/argon2 (cost factor 12+)
- [ ] Never log passwords
- [ ] Enforce minimum complexity
- [ ] Check against breached password lists
- [ ] Rate limit login attempts

### Token Security

- [ ] Use RS256 for JWT in production
- [ ] Short access token lifetime (15-60 min)
- [ ] Rotate refresh tokens on use
- [ ] Store refresh tokens securely
- [ ] Implement token revocation

### Session Security

- [ ] Regenerate session ID on login
- [ ] HttpOnly, Secure, SameSite cookies
- [ ] Session timeout (idle + absolute)
- [ ] Bind session to IP/User-Agent (optional)
