# Backend Glossary

> Standard terminology and definitions for backend development.

## Table of Contents

- [Architecture Terms](#architecture-terms)
- [API Terms](#api-terms)
- [Authentication & Security](#authentication--security)
- [Database Terms](#database-terms)
- [Patterns & Concepts](#patterns--concepts)
- [Infrastructure Terms](#infrastructure-terms)

---

## Architecture Terms

### Controller / Handler
The layer that receives HTTP requests, extracts parameters, calls services, and formats responses. Should not contain business logic.

### Service Layer
Contains business logic and orchestrates operations across multiple repositories. Handles validation, authorization, and domain rules.

### Repository
Data access layer that abstracts database operations. Provides CRUD methods and queries without exposing database implementation details.

### Domain Model / Entity
Core business objects that represent concepts in the problem domain. Contains business rules and state.

### DTO (Data Transfer Object)
Object used to transfer data between layers. Separates internal domain models from external API contracts.

### Middleware
Code that runs before/after request handlers. Used for cross-cutting concerns like authentication, logging, and error handling.

---

## API Terms

### Endpoint
A specific URL path combined with an HTTP method that accepts requests and returns responses.

### Resource
A domain object exposed via the API (e.g., User, Order). Typically corresponds to a database entity.

### Collection
A set of resources accessed at a plural endpoint (e.g., `/users`). Supports listing, filtering, and pagination.

### CRUD
Create, Read, Update, Delete - the four basic operations on resources.

### Idempotent
An operation that produces the same result regardless of how many times it's executed. GET, PUT, DELETE are idempotent; POST is not.

### Pagination
Dividing large result sets into pages. Offset-based uses `page` + `page_size`; cursor-based uses an opaque cursor token.

### Rate Limiting
Restricting the number of API requests a client can make within a time period to prevent abuse.

### Webhook
HTTP callback triggered by an event. Server pushes data to a client-specified URL.

---

## Authentication & Security

### Authentication (AuthN)
Verifying the identity of a user or system. "Who are you?"

### Authorization (AuthZ)
Determining what actions an authenticated user can perform. "What can you do?"

### JWT (JSON Web Token)
A compact, URL-safe token format containing claims. Self-contained - can be verified without database lookup.

### Access Token
Short-lived token (15-60 min) used to authenticate API requests.

### Refresh Token
Long-lived token (days-weeks) used to obtain new access tokens without re-authentication.

### OAuth 2.0
Authorization framework for third-party access. Defines flows for different client types (web, mobile, server).

### RBAC (Role-Based Access Control)
Permission model where users are assigned roles, and roles have permissions.

### ABAC (Attribute-Based Access Control)
Permission model where access decisions are based on attributes of users, resources, and environment.

### API Key
Static credential for authenticating applications (not users). Typically used for server-to-server communication.

### CORS (Cross-Origin Resource Sharing)
Security mechanism that controls which domains can make requests to your API from browsers.

### CSRF (Cross-Site Request Forgery)
Attack where a malicious site tricks a user's browser into making unintended requests to your API.

---

## Database Terms

### Primary Key
Unique identifier for a record. Commonly UUID, auto-increment integer, or prefixed ID.

### Foreign Key
Column that references a primary key in another table, establishing a relationship.

### Index
Data structure that improves query performance by providing fast lookup paths.

### Transaction
A unit of work that either completes entirely or is rolled back. Ensures data consistency.

### ACID
Atomicity, Consistency, Isolation, Durability - properties that guarantee database transactions are reliable.

### Migration
Version-controlled changes to database schema. Allows schema to evolve with the application.

### Soft Delete
Marking records as deleted (via `deleted_at` timestamp) rather than physically removing them.

### Audit Trail
Record of all changes to data, including who made the change and when.

### N+1 Query Problem
Performance issue where fetching N records results in N+1 database queries due to lazy loading of relationships.

### Connection Pool
Cache of database connections that can be reused, avoiding the overhead of creating new connections.

---

## Patterns & Concepts

### Dependency Injection (DI)
Design pattern where dependencies are provided to a class rather than created by it. Improves testability.

### Unit of Work
Pattern that maintains a list of objects affected by a transaction and coordinates writing changes.

### Repository Pattern
Abstraction that provides collection-like interface for accessing domain objects from the database.

### Domain-Driven Design (DDD)
Approach that focuses on modeling software around the business domain and its rules.

### Event-Driven Architecture
Pattern where components communicate through events rather than direct calls. Enables loose coupling.

### CQRS (Command Query Responsibility Segregation)
Pattern that separates read and write operations into different models for scalability and optimization.

### Saga Pattern
Sequence of local transactions where each step publishes events that trigger the next step. Used for distributed transactions.

### Circuit Breaker
Pattern that prevents cascading failures by failing fast when a downstream service is unhealthy.

### Retry with Backoff
Pattern for handling transient failures by retrying with exponentially increasing delays.

### Idempotency Key
Client-generated unique identifier to ensure an operation is only executed once, even if requested multiple times.

---

## Infrastructure Terms

### Load Balancer
Distributes incoming traffic across multiple server instances for scalability and reliability.

### Reverse Proxy
Server that sits in front of application servers, handling SSL termination, caching, and request routing.

### CDN (Content Delivery Network)
Geographically distributed network of servers that cache and serve static content closer to users.

### Container
Lightweight, isolated environment for running applications. Docker is the most common container runtime.

### Orchestration
Managing multiple containers across multiple hosts. Kubernetes is the most common orchestration platform.

### Horizontal Scaling
Adding more server instances to handle increased load (scaling out).

### Vertical Scaling
Adding more resources (CPU, RAM) to existing servers (scaling up).

### Queue / Message Broker
System for asynchronous communication between services. Examples: RabbitMQ, Redis, SQS.

### Cache
Fast storage layer (usually in-memory) for frequently accessed data. Examples: Redis, Memcached.

### Read Replica
Database copy that handles read queries, reducing load on the primary database.

---

## HTTP Status Code Quick Reference

| Code | Name | Meaning |
|------|------|---------|
| 200 | OK | Request succeeded |
| 201 | Created | Resource created successfully |
| 204 | No Content | Success with no response body |
| 400 | Bad Request | Malformed request syntax |
| 401 | Unauthorized | Authentication required |
| 403 | Forbidden | Authenticated but not authorized |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | State conflict (duplicate, version) |
| 422 | Unprocessable Entity | Validation failed |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Unexpected server error |
| 502 | Bad Gateway | Upstream service error |
| 503 | Service Unavailable | Maintenance/overload |

---

## Acronyms

| Acronym | Full Form |
|---------|-----------|
| API | Application Programming Interface |
| REST | Representational State Transfer |
| CRUD | Create, Read, Update, Delete |
| ORM | Object-Relational Mapping |
| SQL | Structured Query Language |
| NoSQL | Non-relational databases |
| JWT | JSON Web Token |
| UUID | Universally Unique Identifier |
| ULID | Universally Unique Lexicographically Sortable Identifier |
| TLS | Transport Layer Security |
| SSL | Secure Sockets Layer (deprecated, use TLS) |
| HTTPS | HTTP Secure |
| DNS | Domain Name System |
| CI/CD | Continuous Integration / Continuous Deployment |
| SLA | Service Level Agreement |
| SLO | Service Level Objective |
| RPS | Requests Per Second |
| TTL | Time To Live |
