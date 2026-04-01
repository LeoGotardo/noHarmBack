# PostgreSQL Row Level Security (RLS) Setup

This document explains how Row Level Security (RLS) is configured and how to use it in the application.

## Overview

RLS ensures that queries only return rows that the authenticated user is allowed to see. This is enforced at the database level, providing defense-in-depth even if application code has vulnerabilities.

## Tables with RLS Enabled

| Table | Code | Policy | Access Rule |
|-------|------|--------|-------------|
| users | tb_0 | users_own_data | Can only see own row (cl_0a = current_user) |
| streaks | tb_1 | streaks_own_data | Can only see own streaks (cl_1b = current_user) |
| friendships | tb_2 | friendships_participant_data | Can see if sender OR receiver |
| chats | tb_3 | chats_participant_data | Can see if sender OR receiver |
| messages | tb_4 | messages_sender_data | Can see messages where user is sender |
| badges | tb_5 | badges_read_all | Global read-only table |
| user_badges | tb_6 | user_badges_own_data | Can only see own badges |
| audit_logs | tb_7 | audit_logs_own_data | Can only see own audit logs |

## How It Works

1. When a request is made, the JWT token is validated and the userId is extracted
2. `getDbWithRLS` dependency sets `app.current_user_id` in PostgreSQL session
3. All queries automatically filter based on RLS policies
4. If no user is set, RLS policies return no rows (fail-closed)

## Usage in Routes

### Recommended: Use `getDbWithRLS` Dependency

Replace `getDb` with `getDbWithRLS` in your routes:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from api.dependencies.database import getDbWithRLS
from infrastructure.database.models.streakModel import StreakModel

router = APIRouter()

@router.get("/streaks")
def getMyStreaks(db: Session = Depends(getDbWithRLS)):
    """Returns only the current user's streaks."""
    # RLS automatically filters to current user's rows
    return db.query(StreakModel).all()
```

### For Public Endpoints

Use `getDb` without RLS for operations that don't require authentication:

```python
from api.dependencies.database import getDb

@router.get("/public/health")
def healthCheck(db: Session = Depends(getDb)):
    # No RLS context set - use for public/anonymous endpoints
    pass
```

## Usage in Services

When using services that accept a database session, pass the session from the route:

```python
@router.get("/streaks")
def getStreaks(db: Session = Depends(getDbWithRLS)):
    """Service receives RLS-enabled session."""
    service = StreakService(db)
    return service.getCurrentStreak()  # Will only see user's own streak
```

## Migration

To apply RLS policies to an existing database:

```bash
# Create the migration (already done)
# alembic/versions/dd9051ae5321_add_row_level_security.py

# Apply it
ENV=development alembic upgrade dd9051ae5321
```

## Bypassing RLS (Admin Operations)

To bypass RLS for admin operations, use a superuser role or explicitly disable RLS:

```python
from sqlalchemy import text

# In a route with admin authentication
db.execute(text("SET ROW_SECURITY OFF"))  # Caution: bypasses all policies
# ... admin queries ...
db.execute(text("SET ROW_SECURITY ON"))
```

Or use `getDb()` and apply filters manually:

```python
@router.get("/admin/users")
def adminGetAllUsers(
    db: Session = Depends(getDb),
    adminId: str = Depends(requireAdmin)  # Custom admin auth
):
    """Admin can see all users - uses getDb without RLS."""
    return db.query(UserModel).all()
```

## Testing RLS

To verify RLS is working:

```python
from infrastructure.database.rlsContext import RLSContext

def testRLS():
    db = next(getDb())

    # Without RLS context - should return empty
    count = db.query(StreakModel).count()
    assert count == 0, "Should return no rows without RLS context"

    # Set RLS context for a specific user
    RLSContext.setUserId(db, "user-uuid-here")
    count = db.query(StreakModel).count()
    # Now returns only that user's streaks
```

## Important Notes

1. **Bug Fix Required**: `userBedgesModel.py` has incorrect foreign key - badge_id references `tb_1.cl_1a` instead of `tb_5.cl_5a`

2. **Superuser Bypass**: Table owners and superusers bypass RLS by default. The application should use a non-superuser database role.

3. **Performance**: RLS policies add a WHERE clause to each query. Indexes on filtered columns (owner_id, sender, reciver) are essential for performance.

4. **Bulk Operations**: When updating/deleting multiple rows, RLS filters apply. Ensure your queries only target allowed rows.

## Security Considerations

- RLS is a defense-in-depth mechanism, not a replacement for application-level authorization
- Always validate permissions in application code as well
- Use `getDbWithRLS` as the default for all authenticated endpoints
- Never expose `getDb` (without RLS) to regular users

## Troubleshooting

### "permission denied" errors
- RLS is blocking access. Ensure `getDbWithRLS` is used and user is authenticated.

### Empty results when data exists
- RLS context not set. Check that `RLSContext.setUserId()` was called.

### Performance issues
- Ensure indexes exist on: `cl_1b`, `cl_2b`, `cl_2c`, `cl_3b`, `cl_3c`, `cl_4c`, `cl_6b`, `cl_7c`
