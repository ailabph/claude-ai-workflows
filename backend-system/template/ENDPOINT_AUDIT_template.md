# Endpoint Audit Checklist

> Track API endpoint compliance with backend standards. Update this file as endpoints are reviewed/implemented.

## Audit Status Legend

| Status | Meaning |
|--------|---------|
| :white_check_mark: | Compliant |
| :warning: | Partial - needs fixes |
| :x: | Non-compliant |
| :construction: | In progress |
| `-` | Not applicable |

---

## Summary

| Module | Total | Compliant | Partial | Non-Compliant | Coverage |
|--------|-------|-----------|---------|---------------|----------|
| Auth | 0 | 0 | 0 | 0 | 0% |
| Users | 0 | 0 | 0 | 0 | 0% |
| Orders | 0 | 0 | 0 | 0 | 0% |
| **Total** | **0** | **0** | **0** | **0** | **0%** |

---

## Auth Endpoints

| Endpoint | Method | Response Envelope | Error Codes | Auth | Validation | Rate Limit | Tests | Notes |
|----------|--------|-------------------|-------------|------|------------|------------|-------|-------|
| `/auth/register` | POST | - | - | - | - | - | - | |
| `/auth/login` | POST | - | - | - | - | - | - | |
| `/auth/logout` | POST | - | - | - | - | - | - | |
| `/auth/refresh` | POST | - | - | - | - | - | - | |
| `/auth/forgot-password` | POST | - | - | - | - | - | - | |
| `/auth/reset-password` | POST | - | - | - | - | - | - | |
| `/auth/verify-email` | POST | - | - | - | - | - | - | |
| `/auth/me` | GET | - | - | - | - | - | - | |

---

## User Endpoints

| Endpoint | Method | Response Envelope | Error Codes | Auth | Validation | Pagination | Tests | Notes |
|----------|--------|-------------------|-------------|------|------------|------------|-------|-------|
| `/users` | GET | - | - | - | - | - | - | |
| `/users` | POST | - | - | - | - | - | - | |
| `/users/{id}` | GET | - | - | - | - | - | - | |
| `/users/{id}` | PUT | - | - | - | - | - | - | |
| `/users/{id}` | PATCH | - | - | - | - | - | - | |
| `/users/{id}` | DELETE | - | - | - | - | - | - | |

---

## Order Endpoints

| Endpoint | Method | Response Envelope | Error Codes | Auth | Validation | Pagination | Tests | Notes |
|----------|--------|-------------------|-------------|------|------------|------------|-------|-------|
| `/orders` | GET | - | - | - | - | - | - | |
| `/orders` | POST | - | - | - | - | - | - | |
| `/orders/{id}` | GET | - | - | - | - | - | - | |
| `/orders/{id}` | PATCH | - | - | - | - | - | - | |
| `/orders/{id}/cancel` | POST | - | - | - | - | - | - | |
| `/orders/{id}/refund` | POST | - | - | - | - | - | - | |

---

## Compliance Criteria

### Response Envelope

- [ ] Success response uses `{ success: true, data: ... }` format
- [ ] Error response uses `{ success: false, error: { code, message, details } }` format
- [ ] Meta object includes `timestamp` and `request_id`
- [ ] List endpoints include `pagination` object

### Error Codes

- [ ] Uses standard HTTP status codes (400, 401, 403, 404, 422, 500)
- [ ] Error codes are UPPER_SNAKE_CASE
- [ ] Error messages are human-readable
- [ ] Validation errors include field-level details

### Authentication

- [ ] Protected endpoints require valid token
- [ ] Returns 401 for missing/invalid token
- [ ] Returns 403 for insufficient permissions
- [ ] Token validation follows JWT patterns

### Validation

- [ ] Request body validation with clear error messages
- [ ] Query parameter validation (type, range, enum)
- [ ] Path parameter validation (format, existence)
- [ ] Sanitization for user-provided strings

### Pagination

- [ ] Uses `page` and `page_size` query parameters
- [ ] Returns `pagination` object in response
- [ ] Enforces maximum page size (e.g., 100)
- [ ] Handles empty results gracefully

### Rate Limiting

- [ ] Rate limit headers in response
- [ ] Returns 429 when limit exceeded
- [ ] Includes `Retry-After` header

### Tests

- [ ] Unit tests for service layer
- [ ] Integration tests for endpoint
- [ ] Tests for error cases (validation, not found, unauthorized)
- [ ] Tests for edge cases (empty, max limits)

---

## Audit Log

| Date | Endpoint | Auditor | Changes |
|------|----------|---------|---------|
| YYYY-MM-DD | `/endpoint` | Name | Initial audit |

---

## How to Use This Document

1. **Before implementing** - Review criteria for the endpoint type
2. **After implementing** - Fill in audit status for each column
3. **Code review** - Reference this document to verify compliance
4. **Periodic review** - Re-audit endpoints quarterly

### Adding New Endpoints

When adding a new endpoint:

1. Add row to appropriate section
2. Fill in endpoint path and method
3. Mark all columns as `-` initially
4. Update status as you implement each aspect
5. Add notes for any deviations from standards
