from typing import Generator, Optional
from fastapi import Depends
from sqlalchemy.orm import Session
from core.database import database
from infrastructure.database.rlsContext import RLSContext
from api.dependencies.auth import getCurrentUser

def getDb() -> Generator[Session, None, None]:
    """Get database session without RLS context.

    Use this only for operations that don't require user context,
    such as admin operations or public endpoints.
    """
    yield from database.getDb()


def getDbWithRLS(
    userId: str = Depends(getCurrentUser)
) -> Generator[Session, None, None]:
    """Get database session with Row Level Security context.

    This dependency authenticates the user AND sets the PostgreSQL
    session variable that enables RLS policies to filter data.

    All queries using this session will automatically be filtered
    to only return rows owned by or accessible to the authenticated user.

    Args:
        userId: The authenticated user's ID from JWT token

    Yields:
        SQLAlchemy Session with RLS context set

    Example:
        @router.get("/streaks")
        def getStreaks(db: Session = Depends(getDbWithRLS)):
            # This query will only return the current user's streaks
            return db.query(StreakModel).all()
    """
    db = database.session
    try:
        RLSContext.setUserId(db, userId)
        yield db
    finally:
        db.close()