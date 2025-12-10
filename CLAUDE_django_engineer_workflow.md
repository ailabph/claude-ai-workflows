# Django Engineer Workflow (v1)

---

## Overview

A **Django backend development workflow** with strict conventions for environment management, testing, API documentation, and code style.

**Core principles:**
- Conda environment per project
- pytest with mocks (no database in tests)
- OpenAPI/Swagger documentation everywhere
- Black-formatted code

---

## Question vs Implementation Mode

**CRITICAL:** Detect whether human is asking a question or requesting implementation.

### Question Mode (Read-Only)

**Triggers:** Human message contains question words or investigation requests:
- "How does...", "What is...", "Where is...", "Why does..."
- "Can you explain...", "Show me...", "Find..."
- "Is there...", "Does this...", "Which..."
- "Investigate...", "Check...", "Look at..."

**Agent behavior:**
- Investigate codebase (read files, grep, search)
- Answer the question with findings
- **DO NOT** edit any files
- **DO NOT** implement anything
- **DO NOT** create new files

**Response format:**
```markdown
## Investigation: [Topic]

### Question
[Restate the human's question]

### Findings
[What you discovered from investigating]

### Files Reviewed
- `path/to/file.py` - [what you found]
- `path/to/other.py` - [what you found]

### Answer
[Clear answer to the question]

### Related
[Optional: related files or concepts they might want to know about]
```

### Implementation Mode

**Triggers:** Human message contains action requests:
- "Create...", "Add...", "Build...", "Implement..."
- "Fix...", "Update...", "Change...", "Modify..."
- "Refactor...", "Delete...", "Remove..."

**Agent behavior:**
- Follow full workflow (environment, implement, validate, report)
- Edit/create files as needed
- Run tests and formatters

### Examples

| Human Says | Mode | Agent Does |
|------------|------|------------|
| "How does authentication work in this project?" | Question | Investigates, explains, NO edits |
| "Where are the product serializers?" | Question | Finds files, shows locations, NO edits |
| "Why is this test failing?" | Question | Investigates, explains cause, NO edits |
| "What endpoints do we have for users?" | Question | Lists endpoints, NO edits |
| "Create a new endpoint for orders" | Implementation | Full workflow with edits |
| "Fix the failing test in test_views.py" | Implementation | Edits code to fix |
| "Add validation to the product serializer" | Implementation | Edits serializer |

### Ambiguous Cases

If unclear, **ask for clarification**:

```
Agent: "I found the issue with the test. Would you like me to:
1. Just explain what's wrong (no changes)
2. Fix it for you (will edit files)

Which do you prefer?"
```

---

## Environment Management

### Conda Environment Convention

**Environment name = Project directory name**

```bash
# If project is in /projects/myapp/
# Conda env name should be: myapp
```

### Agent Startup Sequence

Before any Python/Django command, agent MUST:

```bash
# 1. Get project name from current directory
PROJECT_NAME=$(basename $(pwd))

# 2. Check if conda env exists
conda env list | grep "^${PROJECT_NAME} "

# 3a. If NOT exists - Create and activate
conda create -n ${PROJECT_NAME} python=3.11 -y
conda activate ${PROJECT_NAME}
pip install -r requirements.txt

# 3b. If exists - Activate
conda activate ${PROJECT_NAME}
```

### Environment Verification

After activation, verify:
```bash
# Confirm correct environment
echo $CONDA_DEFAULT_ENV  # Should match project name

# Confirm Django is available
python -c "import django; print(django.VERSION)"
```

### Report Format

```markdown
## Environment
- Project: myapp
- Conda env: myapp (activated)
- Python: 3.11.x
- Django: 4.2.x
```

---

## Testing Conventions

### Framework: pytest

Always use pytest, never Django's test runner directly.

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_views.py

# Run with coverage
pytest --cov=myapp --cov-report=term-missing

# Run with verbose output
pytest -v
```

### Test Structure

```
project/
├── myapp/
│   ├── models.py
│   ├── views.py
│   └── serializers.py
└── tests/
    ├── __init__.py
    ├── conftest.py          # Shared fixtures
    ├── test_models.py
    ├── test_views.py
    └── test_serializers.py
```

### Unit Tests Only (No Database)

**CRITICAL:** Tests must NOT require database setup.

```python
# GOOD - Using mocks
from unittest.mock import Mock, patch

@patch('myapp.views.User.objects.get')
def test_get_user(mock_get):
    mock_get.return_value = Mock(id=1, username='testuser')
    # ... test logic

# BAD - Requires database
def test_get_user(self):
    user = User.objects.create(username='testuser')  # Don't do this
```

### Mock Patterns

```python
# Mock a model queryset
@patch('myapp.views.Product.objects')
def test_list_products(mock_objects):
    mock_objects.filter.return_value = [
        Mock(id=1, name='Product 1'),
        Mock(id=2, name='Product 2'),
    ]

# Mock a serializer
@patch('myapp.views.ProductSerializer')
def test_create_product(mock_serializer):
    mock_serializer.return_value.is_valid.return_value = True
    mock_serializer.return_value.data = {'id': 1, 'name': 'New Product'}

# Mock external service
@patch('myapp.services.external_api.fetch_data')
def test_sync_data(mock_fetch):
    mock_fetch.return_value = {'status': 'success'}
```

### Test Naming Convention

```python
# Pattern: test_<action>_<condition>_<expected_result>

def test_create_user_with_valid_data_returns_201():
    pass

def test_create_user_with_missing_email_returns_400():
    pass

def test_get_user_when_not_found_returns_404():
    pass
```

---

## API Conventions

### Serializer Convention

**Every serializer field MUST have OpenAPI description via help_text:**

```python
from rest_framework import serializers

class UserSerializer(serializers.Serializer):
    """
    Serializer for User resource.
    Used for user registration and profile updates.
    """
    id = serializers.IntegerField(
        read_only=True,
        help_text="Unique identifier for the user"
    )
    username = serializers.CharField(
        max_length=150,
        help_text="Unique username for login (3-150 characters)"
    )
    email = serializers.EmailField(
        help_text="User's email address for notifications"
    )
    is_active = serializers.BooleanField(
        default=True,
        help_text="Whether the user account is active"
    )
```

### ModelSerializer Convention

```python
class ProductSerializer(serializers.ModelSerializer):
    """
    Serializer for Product model.
    Handles product CRUD operations.
    """
    class Meta:
        model = Product
        fields = ['id', 'name', 'price', 'stock', 'created_at']
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {
            'name': {'help_text': 'Product display name (max 200 chars)'},
            'price': {'help_text': 'Price in USD (decimal, 2 places)'},
            'stock': {'help_text': 'Available inventory count'},
        }
```

### View Convention

**Every view/viewset MUST have OpenAPI decorators:**

```python
from rest_framework import viewsets
from drf_spectacular.utils import extend_schema, extend_schema_view

@extend_schema_view(
    list=extend_schema(
        summary="List all products",
        description="Returns a paginated list of all active products.",
        tags=["Products"],
    ),
    retrieve=extend_schema(
        summary="Get product details",
        description="Returns detailed information for a specific product.",
        tags=["Products"],
    ),
    create=extend_schema(
        summary="Create a new product",
        description="Creates a new product. Requires admin permissions.",
        tags=["Products"],
    ),
)
class ProductViewSet(viewsets.ModelViewSet):
    """ViewSet for Product CRUD operations."""
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
```

### URL Convention

```python
# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')

urlpatterns = [
    path('api/v1/', include(router.urls)),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
```

---

## Code Style

### Black Formatter

**All Python code MUST be formatted with Black.**

```bash
# Format single file
black myapp/views.py

# Format entire project
black .

# Check without modifying
black --check .
```

### Agent Behavior

Before committing or reporting changes:
```bash
# Always format
black .

# Then run tests
pytest
```

---

## Workflow Phases

### Phase 1: Environment Setup

Agent checks/creates conda environment:

```
Agent: "Checking environment...

- Project directory: /projects/myapp
- Expected conda env: myapp
- Status: Environment exists and activated
- Python: 3.11.4
- Django: 4.2.7

Ready for your task."
```

### Phase 2: Understand Task

Agent clarifies if needed:
- What resource/model is involved?
- What methods/actions needed?
- Any existing code to integrate with?

### Phase 3: Implementation

Agent implements following conventions:
1. Model (if needed)
2. Serializer (with help_text)
3. View (with OpenAPI decorators)
4. URL routing
5. Tests (with mocks)

### Phase 4: Validation

Before reporting, agent runs:
```bash
# Format code
black .

# Run tests
pytest

# Check OpenAPI schema generates
python manage.py spectacular --validate
```

### Phase 5: Report

```markdown
## Changes Made

### Files Created:
- `myapp/serializers/product.py` - ProductSerializer with OpenAPI descriptions
- `myapp/views/product.py` - ProductViewSet with extend_schema decorators
- `tests/test_product_views.py` - Unit tests with mocks

### Files Modified:
- `myapp/urls.py` - Added product routes

### Validation:
- Black formatted
- All tests pass (12 passed)
- OpenAPI schema valid

### API Endpoints Added:
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/products/ | List all products |
| POST | /api/v1/products/ | Create product |
| GET | /api/v1/products/{id}/ | Get product detail |
| PUT | /api/v1/products/{id}/ | Update product |
| DELETE | /api/v1/products/{id}/ | Delete product |
```

---

## Git Integration

### Commit Message Format

```
api(<type>): <short description>
```

| Type | When |
|------|------|
| `api(feat)` | New endpoint or feature |
| `api(fix)` | Bug fix |
| `api(test)` | Adding/updating tests |
| `api(refactor)` | Code restructure |
| `api(docs)` | Documentation/OpenAPI updates |

### Examples

```bash
git commit -m "api(feat): add product CRUD endpoints with OpenAPI docs"
git commit -m "api(test): add unit tests for product views"
git commit -m "api(fix): correct validation on product price field"
```

---

## Quick Reference: OpenAPI Checklist

Before completing any API task:

- [ ] Serializer has docstring
- [ ] All serializer fields have help_text
- [ ] View/ViewSet has docstring
- [ ] All actions have @extend_schema decorator
- [ ] Schema includes: summary, description, tags
- [ ] python manage.py spectacular --validate passes
