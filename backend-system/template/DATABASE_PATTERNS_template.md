# Database Patterns Reference

> Standard patterns for database schema design, queries, and data management.

## Table of Contents

- [Naming Conventions](#naming-conventions)
- [Standard Columns](#standard-columns)
- [Primary Keys](#primary-keys)
- [Relationship Patterns](#relationship-patterns)
- [Indexing Strategies](#indexing-strategies)
- [Soft Delete Pattern](#soft-delete-pattern)
- [Audit Trail Pattern](#audit-trail-pattern)
- [Query Patterns](#query-patterns)
- [Migration Patterns](#migration-patterns)

---

## Naming Conventions

### Tables

| Convention | Example | Notes |
|------------|---------|-------|
| Plural, snake_case | `users`, `order_items` | Preferred |
| Singular, snake_case | `user`, `order_item` | Alternative |

### Columns

| Type | Convention | Example |
|------|------------|---------|
| Regular | snake_case | `first_name`, `created_at` |
| Foreign key | `{table}_id` | `user_id`, `order_id` |
| Boolean | `is_` or `has_` prefix | `is_active`, `has_verified_email` |
| Timestamps | `_at` suffix | `created_at`, `updated_at`, `deleted_at` |
| Counts | `_count` suffix | `order_count`, `login_count` |

### Indexes

```sql
-- Primary key (auto)
pk_{table}

-- Unique constraint
uq_{table}_{column(s)}

-- Foreign key
fk_{table}_{referenced_table}

-- Regular index
idx_{table}_{column(s)}

-- Examples
idx_users_email
idx_orders_user_id_created_at
uq_users_email
```

---

## Standard Columns

### Base Table Template

```sql
CREATE TABLE {table_name} (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Business columns here...

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    -- Soft delete (optional)
    deleted_at TIMESTAMP WITH TIME ZONE
);

-- Auto-update updated_at
CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON {table_name}
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

### Timestamp Trigger Function

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

---

## Primary Keys

### UUID (Recommended)

```sql
id UUID PRIMARY KEY DEFAULT gen_random_uuid()
```

**Pros:** Globally unique, no sequence contention, safe to expose
**Cons:** Larger storage, not sortable by creation time

### Prefixed IDs

```sql
-- Store as text, generate in application
id VARCHAR(30) PRIMARY KEY  -- e.g., "usr_abc123xyz789"
```

```python
import nanoid

def generate_id(prefix: str) -> str:
    """Generate prefixed ID like usr_abc123xyz789"""
    return f"{prefix}_{nanoid.generate(size=16)}"
```

### ULID (Sortable UUID Alternative)

```sql
id VARCHAR(26) PRIMARY KEY  -- e.g., "01ARZ3NDEKTSV4RRFFQ69G5FAV"
```

**Pros:** Sortable by creation time, globally unique
**Cons:** Requires library support

---

## Relationship Patterns

### One-to-Many

```sql
-- Parent
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE
);

-- Child (many orders per user)
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    total_amount DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_orders_user_id ON orders(user_id);
```

### Many-to-Many

```sql
-- Junction table
CREATE TABLE user_roles (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID REFERENCES roles(id) ON DELETE CASCADE,
    granted_at TIMESTAMP DEFAULT NOW(),
    granted_by UUID REFERENCES users(id),
    PRIMARY KEY (user_id, role_id)
);

CREATE INDEX idx_user_roles_role_id ON user_roles(role_id);
```

### Self-Referential (Hierarchy)

```sql
-- Tree structure (e.g., categories, org chart)
CREATE TABLE categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id UUID REFERENCES categories(id) ON DELETE SET NULL,
    name VARCHAR(100) NOT NULL,
    path TEXT,  -- Materialized path: "/root/parent/child"
    depth INTEGER DEFAULT 0
);

CREATE INDEX idx_categories_parent_id ON categories(parent_id);
CREATE INDEX idx_categories_path ON categories(path);
```

### Polymorphic Association

```sql
-- Option 1: Separate join tables (preferred)
CREATE TABLE comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    body TEXT NOT NULL,
    author_id UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE post_comments (
    comment_id UUID PRIMARY KEY REFERENCES comments(id) ON DELETE CASCADE,
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE
);

CREATE TABLE product_comments (
    comment_id UUID PRIMARY KEY REFERENCES comments(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE
);

-- Option 2: Type + ID columns (simpler but no FK constraint)
CREATE TABLE comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    commentable_type VARCHAR(50) NOT NULL,  -- 'post', 'product'
    commentable_id UUID NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_comments_commentable ON comments(commentable_type, commentable_id);
```

---

## Indexing Strategies

### Index Selection Guidelines

| Query Pattern | Index Type |
|---------------|------------|
| Equality lookup | B-tree (default) |
| Range queries | B-tree |
| Full-text search | GIN with tsvector |
| JSON queries | GIN |
| Array contains | GIN |
| Geospatial | GiST |

### Common Index Patterns

```sql
-- Single column (frequent WHERE clause)
CREATE INDEX idx_users_email ON users(email);

-- Composite (multi-column WHERE or ORDER BY)
CREATE INDEX idx_orders_user_status ON orders(user_id, status);

-- Partial (filtered subset)
CREATE INDEX idx_orders_pending ON orders(created_at)
WHERE status = 'pending';

-- Covering (include columns for index-only scan)
CREATE INDEX idx_users_email_name ON users(email) INCLUDE (first_name, last_name);

-- Expression (computed values)
CREATE INDEX idx_users_email_lower ON users(LOWER(email));
```

### Index for Soft Delete

```sql
-- Partial index excluding deleted records
CREATE INDEX idx_users_email_active ON users(email)
WHERE deleted_at IS NULL;

-- Always filter by deleted_at in queries
SELECT * FROM users WHERE email = ? AND deleted_at IS NULL;
```

---

## Soft Delete Pattern

### Schema

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Unique constraint that allows multiple deleted with same email
CREATE UNIQUE INDEX uq_users_email_active ON users(email)
WHERE deleted_at IS NULL;
```

### Query Patterns

```sql
-- List active records (default)
SELECT * FROM users WHERE deleted_at IS NULL;

-- Soft delete
UPDATE users SET deleted_at = NOW() WHERE id = ?;

-- Restore
UPDATE users SET deleted_at = NULL WHERE id = ?;

-- Hard delete (permanent)
DELETE FROM users WHERE id = ? AND deleted_at IS NOT NULL;

-- List deleted records (admin)
SELECT * FROM users WHERE deleted_at IS NOT NULL;
```

### ORM Implementation (SQLAlchemy)

```python
from sqlalchemy import Column, DateTime, event
from sqlalchemy.orm import Query

class SoftDeleteMixin:
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    def soft_delete(self):
        self.deleted_at = datetime.utcnow()

    def restore(self):
        self.deleted_at = None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

# Custom query class that filters by default
class SoftDeleteQuery(Query):
    def __new__(cls, *args, **kwargs):
        obj = super().__new__(cls)
        obj._with_deleted = kwargs.pop('_with_deleted', False)
        return obj

    def __init__(self, *args, **kwargs):
        kwargs.pop('_with_deleted', None)
        super().__init__(*args, **kwargs)

    def __iter__(self):
        return super().__iter__() if self._with_deleted else \
               super().filter_by(deleted_at=None).__iter__()

    def with_deleted(self):
        return self.__class__(self._entity, session=self.session, _with_deleted=True)
```

---

## Audit Trail Pattern

### Audit Table

```sql
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name VARCHAR(100) NOT NULL,
    record_id UUID NOT NULL,
    action VARCHAR(10) NOT NULL,  -- INSERT, UPDATE, DELETE
    old_values JSONB,
    new_values JSONB,
    changed_fields TEXT[],
    user_id UUID REFERENCES users(id),
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_audit_log_table_record ON audit_log(table_name, record_id);
CREATE INDEX idx_audit_log_user ON audit_log(user_id);
CREATE INDEX idx_audit_log_created ON audit_log(created_at);
```

### Audit Trigger (PostgreSQL)

```sql
CREATE OR REPLACE FUNCTION audit_trigger_func()
RETURNS TRIGGER AS $$
DECLARE
    old_row JSONB := NULL;
    new_row JSONB := NULL;
    changed TEXT[] := '{}';
BEGIN
    IF TG_OP = 'DELETE' THEN
        old_row := to_jsonb(OLD);
    ELSIF TG_OP = 'UPDATE' THEN
        old_row := to_jsonb(OLD);
        new_row := to_jsonb(NEW);
        -- Get changed fields
        SELECT array_agg(key) INTO changed
        FROM jsonb_each(old_row) o
        FULL OUTER JOIN jsonb_each(new_row) n USING (key)
        WHERE o.value IS DISTINCT FROM n.value;
    ELSIF TG_OP = 'INSERT' THEN
        new_row := to_jsonb(NEW);
    END IF;

    INSERT INTO audit_log (table_name, record_id, action, old_values, new_values, changed_fields)
    VALUES (TG_TABLE_NAME, COALESCE(NEW.id, OLD.id), TG_OP, old_row, new_row, changed);

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Apply to tables
CREATE TRIGGER audit_users
    AFTER INSERT OR UPDATE OR DELETE ON users
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();
```

---

## Query Patterns

### Pagination

```sql
-- Offset pagination (simple but slow for large offsets)
SELECT * FROM orders
WHERE user_id = ?
ORDER BY created_at DESC
LIMIT 20 OFFSET 40;

-- Cursor pagination (better for large datasets)
SELECT * FROM orders
WHERE user_id = ?
  AND created_at < ?  -- cursor from last item
ORDER BY created_at DESC
LIMIT 20;
```

### Filtering with Optional Parameters

```python
# Python with SQLAlchemy
def list_orders(
    user_id: str | None = None,
    status: str | None = None,
    created_after: datetime | None = None,
) -> list[Order]:
    query = select(Order)

    if user_id:
        query = query.where(Order.user_id == user_id)
    if status:
        query = query.where(Order.status == status)
    if created_after:
        query = query.where(Order.created_at >= created_after)

    return session.execute(query).scalars().all()
```

### Aggregations

```sql
-- Count by status
SELECT status, COUNT(*) as count
FROM orders
WHERE user_id = ?
GROUP BY status;

-- Sum with window function
SELECT
    id,
    amount,
    SUM(amount) OVER (ORDER BY created_at) as running_total
FROM transactions
WHERE user_id = ?;
```

### Upsert (INSERT ... ON CONFLICT)

```sql
INSERT INTO user_settings (user_id, key, value)
VALUES (?, ?, ?)
ON CONFLICT (user_id, key)
DO UPDATE SET
    value = EXCLUDED.value,
    updated_at = NOW();
```

---

## Migration Patterns

### Migration File Naming

```
{timestamp}_{description}.sql

# Examples
20240115100000_create_users_table.sql
20240115100001_add_email_index.sql
20240115100002_add_orders_table.sql
```

### Safe Migration Practices

```sql
-- Adding column (safe)
ALTER TABLE users ADD COLUMN phone VARCHAR(20);

-- Adding NOT NULL column (requires default or backfill)
ALTER TABLE users ADD COLUMN status VARCHAR(20) DEFAULT 'active' NOT NULL;

-- Adding index concurrently (doesn't lock table)
CREATE INDEX CONCURRENTLY idx_users_phone ON users(phone);

-- Renaming column (may break app - coordinate with deploy)
ALTER TABLE users RENAME COLUMN phone TO phone_number;

-- Dropping column (safe after code no longer references it)
ALTER TABLE users DROP COLUMN old_column;
```

### Data Migration Template

```sql
-- Up migration
BEGIN;

-- Schema changes
ALTER TABLE orders ADD COLUMN total_cents INTEGER;

-- Data migration
UPDATE orders SET total_cents = (total_amount * 100)::INTEGER;

-- Make non-nullable after backfill
ALTER TABLE orders ALTER COLUMN total_cents SET NOT NULL;

-- Drop old column (after code updated)
-- ALTER TABLE orders DROP COLUMN total_amount;

COMMIT;

-- Down migration
BEGIN;
ALTER TABLE orders DROP COLUMN IF EXISTS total_cents;
COMMIT;
```

---

## Performance Checklist

### Query Optimization

- [ ] Use `EXPLAIN ANALYZE` for slow queries
- [ ] Add indexes for WHERE and JOIN columns
- [ ] Avoid `SELECT *` - specify columns
- [ ] Use pagination for large result sets
- [ ] Consider denormalization for read-heavy data

### Schema Optimization

- [ ] Choose appropriate data types (don't over-size)
- [ ] Add constraints (NOT NULL, UNIQUE, CHECK)
- [ ] Use partial indexes for filtered queries
- [ ] Partition large tables by date/tenant

### Connection Management

- [ ] Use connection pooling (PgBouncer, built-in)
- [ ] Set appropriate pool size
- [ ] Handle connection timeouts gracefully
- [ ] Use read replicas for read-heavy workloads
